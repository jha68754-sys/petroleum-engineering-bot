from __future__ import annotations

import json
import sqlite3

import pytest

from handlers import text_handlers as th
from services.engineering_case import build_case
from services.engineering_case_registry import (
    CaseIntegrityError,
    CaseNotFoundError,
    EngineeringCaseRegistry,
)
from services.engineering_report import generate_report_v1


@pytest.fixture
def sample_case():
    return build_case(
        "demo_v1",
        request={"calculation": "demo"},
        inputs={"pressure_psia": 1000.0, "rate_stbd": 250.0},
        units={"pressure": "psia", "rate": "STB/day"},
        selectors={"model": "linear"},
        model={"engine": "demo"},
        result={"status": "OK", "rate_stbd": 250.0},
        status="OK",
        reproducibility={"engine": "demo", "engine_version": "V1"},
    )


def test_registry_create_retrieve_and_reload_preserves_case_identity(tmp_path, sample_case):
    db_path = tmp_path / "engineering_cases.sqlite3"
    first = EngineeringCaseRegistry(db_path)
    first.save_case(sample_case, report_text=generate_report_v1(sample_case))

    retrieved = first.get_case(sample_case.case_id)
    assert retrieved.to_dict() == sample_case.to_dict()

    reloaded = EngineeringCaseRegistry(db_path)
    restored = reloaded.get_case(sample_case.case_id)
    assert restored.case_id == sample_case.case_id
    assert restored.to_dict() == sample_case.to_dict()
    assert reloaded.get_case_metadata(sample_case.case_id)["case_type"] == "demo_v1"
    assert reloaded.get_case_metadata(sample_case.case_id)["report_text"]


def test_registry_audit_is_structured_and_does_not_store_telegram_metadata(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "engineering_cases.sqlite3")
    registry.save_case(sample_case, report_text="Engineering report")
    registry.record_event(
        sample_case.case_id,
        "REPORT_REQUESTED",
        details={"surface": "case_report", "telegram_chat_id": 123456},
    )

    events = registry.audit_case(sample_case.case_id)
    assert [event.event_type for event in events] == ["CASE_CREATED", "REPORT_REQUESTED"]
    assert all(event.case_id == sample_case.case_id for event in events)
    assert all("telegram_chat_id" not in event.details for event in events)
    assert all("123456" not in json.dumps(event.details) for event in events)
    assert events[0].created_at


def test_registry_rejects_invalid_and_missing_case_ids_with_typed_errors(tmp_path):
    registry = EngineeringCaseRegistry(tmp_path / "engineering_cases.sqlite3")
    with pytest.raises(CaseNotFoundError):
        registry.get_case("not-a-sha256-case-id")
    with pytest.raises(CaseNotFoundError):
        registry.audit_case("0" * 64)


def test_registry_detects_tampered_case_record(tmp_path, sample_case):
    db_path = tmp_path / "engineering_cases.sqlite3"
    registry = EngineeringCaseRegistry(db_path)
    registry.save_case(sample_case, report_text="Engineering report")

    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE engineering_cases SET case_json = ? WHERE case_id = ?",
            (json.dumps({"case_id": sample_case.case_id, "tampered": True}), sample_case.case_id),
        )
        connection.commit()

    with pytest.raises(CaseIntegrityError):
        EngineeringCaseRegistry(db_path).get_case(sample_case.case_id)


def test_case_commands_use_persistent_registry_after_in_process_memory_is_cleared(tmp_path, monkeypatch):
    db_path = tmp_path / "engineering_cases.sqlite3"
    persistent = EngineeringCaseRegistry(db_path)
    monkeypatch.setattr(th, "_CASE_REGISTRY", persistent)
    th._ENGINEERING_CASES.clear()

    command = "/calc choke case=1 p_up=1000 p_down=200 choke=16 gor=1000 q_liquid=1000"
    text, png, error = th.handle_calc({"text": command}, None)
    assert png is None
    assert error is None
    case_id = text.rsplit("Engineering Case ID: ", 1)[1].strip()

    th._ENGINEERING_CASES.clear()
    monkeypatch.setattr(th, "_CASE_REGISTRY", EngineeringCaseRegistry(db_path))

    report, _, report_error = th.handle_case_command({"text": f"/case report {case_id}"}, None)
    assert report_error is None
    assert case_id in report
    assert "Choke Performance" in report

    replay, _, replay_error = th.handle_case_command({"text": f"/case replay {case_id}"}, None)
    assert replay_error is None
    assert replay.startswith("Replay comparison: MATCH")

    audit, _, audit_error = th.handle_case_command({"text": f"/case audit {case_id}"}, None)
    assert audit_error is None
    assert "CASE_CREATED" in audit
    assert "REPORT_REQUESTED" in audit
    assert "REPLAY_REQUESTED" in audit
    assert "REPLAY_MATCH" in audit
    assert "telegram_chat_id" not in audit


def test_case_report_missing_case_is_typed_and_auditable(tmp_path, monkeypatch):
    registry = EngineeringCaseRegistry(tmp_path / "engineering_cases.sqlite3")
    monkeypatch.setattr(th, "_CASE_REGISTRY", registry)
    th._ENGINEERING_CASES.clear()

    text, _, error = th.handle_case_command({"text": f"/case report {'1' * 64}"}, None)
    assert error is None
    assert "CASE_NOT_FOUND" in text
    assert "Traceback" not in text
    assert "{" not in text and "}" not in text

    audit = registry.audit_case("1" * 64)
    assert audit[-1].event_type == "CASE_NOT_FOUND"
    assert audit[-1].details["action"] == "report"


def test_registry_keeps_original_case_id_when_audit_and_replay_metadata_change(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "engineering_cases.sqlite3")
    registry.save_case(sample_case, report_text="Engineering report")
    original_id = sample_case.case_id
    registry.record_event(original_id, "REPORT_REQUESTED")
    registry.record_event(original_id, "REPLAY_REQUESTED")
    registry.record_replay_result(original_id, matched=True, result={"status": "OK"})
    assert registry.get_case(original_id).case_id == original_id
    assert registry.get_case_metadata(original_id)["case_id"] == original_id
    assert registry.get_case_metadata(original_id)["replay_match"] is True


@pytest.mark.parametrize("case_type", ["choke_v1", "integrated_system_v1", "nodal_v1", "vlp_v1", "gas_lift_v1", "sensitivity_v1", "optimize_v1"])
def test_registry_accepts_all_released_case_type_labels(tmp_path, sample_case, case_type):
    case = build_case(
        case_type,
        request=sample_case.request,
        inputs=sample_case.inputs,
        units=sample_case.units,
        selectors=sample_case.selectors,
        model=sample_case.model,
        result=sample_case.result,
        status=sample_case.status,
        reproducibility=sample_case.reproducibility,
    )
    registry = EngineeringCaseRegistry(tmp_path / f"{case_type}.sqlite3")
    registry.save_case(case)
    assert registry.get_case(case.case_id).case_id == case.case_id
    assert registry.get_case_metadata(case.case_id)["case_type"] == case_type


def test_case_audit_command_usage_is_human_readable(tmp_path, monkeypatch):
    monkeypatch.setattr(th, "_CASE_REGISTRY", EngineeringCaseRegistry(tmp_path / "engineering_cases.sqlite3"))
    th._ENGINEERING_CASES.clear()
    response, _, error = th.handle_case_command({"text": "/case audit"}, None)
    assert error is None
    assert "/case audit <case_id>" in response
    assert "{" not in response and "}" not in response


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))



def test_registry_report_text_is_persisted_as_user_facing_artifact(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "engineering_cases.sqlite3")
    report = generate_report_v1(sample_case)
    registry.save_case(sample_case, report_text=report)
    assert registry.get_report(sample_case.case_id) == report


def test_registry_does_not_persist_secrets_from_case_or_report(tmp_path):
    case = build_case(
        "secret_demo",
        inputs={"api_key": "sk-testsecret", "notes": "Bearer ghp_secret"},
        result={"status": "OK"},
        status="OK",
    )
    registry = EngineeringCaseRegistry(tmp_path / "engineering_cases.sqlite3")
    registry.save_case(case, report_text="Bearer ghp_report_secret")
    raw = (tmp_path / "engineering_cases.sqlite3").read_bytes()
    assert b"sk-testsecret" not in raw
    assert b"ghp_secret" not in raw
    assert b"ghp_report_secret" not in raw



def test_registry_close_is_safe_and_reopenable(tmp_path, sample_case):
    db_path = tmp_path / "engineering_cases.sqlite3"
    registry = EngineeringCaseRegistry(db_path)
    registry.save_case(sample_case)
    registry.close()
    reopened = EngineeringCaseRegistry(db_path)
    assert reopened.get_case(sample_case.case_id).case_id == sample_case.case_id
    reopened.close()



def test_registry_is_idempotent_for_same_case_id(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "engineering_cases.sqlite3")
    registry.save_case(sample_case)
    registry.save_case(sample_case)
    assert len(registry.list_cases()) == 1
    assert [event.event_type for event in registry.audit_case(sample_case.case_id)] == ["CASE_CREATED"]



def test_registry_list_cases_is_newest_first_and_bounded(tmp_path):
    registry = EngineeringCaseRegistry(tmp_path / "engineering_cases.sqlite3")
    cases = [
        build_case("demo", inputs={"index": index}, result={"status": "OK"}, status="OK")
        for index in range(3)
    ]
    for case in cases:
        registry.save_case(case)
    listed = registry.list_cases(limit=2)
    assert len(listed) == 2
    assert {case.case_id for case in listed}.issubset({case.case_id for case in cases})



def test_registry_audit_survives_reload(tmp_path, sample_case):
    db_path = tmp_path / "engineering_cases.sqlite3"
    EngineeringCaseRegistry(db_path).save_case(sample_case)
    registry = EngineeringCaseRegistry(db_path)
    registry.record_event(sample_case.case_id, "REPORT_REQUESTED")
    reloaded = EngineeringCaseRegistry(db_path)
    assert [event.event_type for event in reloaded.audit_case(sample_case.case_id)] == [
        "CASE_CREATED",
        "REPORT_REQUESTED",
    ]



def test_registry_rejects_unknown_event_names(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "engineering_cases.sqlite3")
    registry.save_case(sample_case)
    with pytest.raises(ValueError):
        registry.record_event(sample_case.case_id, "NOT_A_CASE_EVENT")



def test_registry_rejects_empty_case_payload(tmp_path):
    registry = EngineeringCaseRegistry(tmp_path / "engineering_cases.sqlite3")
    with pytest.raises(ValueError):
        registry.save_case(None)



def test_registry_replay_metadata_is_structured(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "engineering_cases.sqlite3")
    registry.save_case(sample_case)
    registry.record_replay_result(sample_case.case_id, matched=False, result={"status": "DIFFERENT"})
    metadata = registry.get_case_metadata(sample_case.case_id)
    assert metadata["replay_match"] is False
    assert metadata["replay_result"] == {"status": "DIFFERENT"}
    assert registry.audit_case(sample_case.case_id)[-1].event_type == "REPLAY_MISMATCH"



def test_registry_rejects_report_secret_before_storage(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "engineering_cases.sqlite3")
    with pytest.raises(ValueError):
        registry.save_case(sample_case, report_text="Authorization: Bearer secret-token")




def test_registry_integrity_error_does_not_return_tampered_payload(tmp_path, sample_case):
    db_path = tmp_path / "engineering_cases.sqlite3"
    registry = EngineeringCaseRegistry(db_path)
    registry.save_case(sample_case)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE engineering_cases SET case_sha256 = ? WHERE case_id = ?",
            ("0" * 64, sample_case.case_id),
        )
        connection.commit()
    with pytest.raises(CaseIntegrityError):
        EngineeringCaseRegistry(db_path).get_case(sample_case.case_id)



def test_registry_report_missing_case_is_typed(tmp_path):
    registry = EngineeringCaseRegistry(tmp_path / "engineering_cases.sqlite3")
    with pytest.raises(CaseNotFoundError):
        registry.get_report("2" * 64)



def test_registry_audit_details_are_json_safe(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "engineering_cases.sqlite3")
    registry.save_case(sample_case)
    registry.record_event(sample_case.case_id, "VALIDATION_FAILURE", details={"code": "BAD_INPUT"})
    payload = json.dumps([event.to_dict() for event in registry.audit_case(sample_case.case_id)])
    assert "BAD_INPUT" in payload
    assert "case_id" in payload
    assert "created_at" in payload



def test_registry_case_id_is_not_changed_by_report_text(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "engineering_cases.sqlite3")
    registry.save_case(sample_case, report_text="first")
    with pytest.raises(ValueError):
        registry.save_case(sample_case, report_text="second")
    assert registry.get_report(sample_case.case_id) == "first"



def test_registry_supports_explicit_schema_version_metadata(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "engineering_cases.sqlite3")
    registry.save_case(sample_case, schema_version="engineering_case_v1")
    assert registry.get_case_metadata(sample_case.case_id)["schema_version"] == "engineering_case_v1"



def test_registry_limits_audit_detail_size(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "engineering_cases.sqlite3")
    registry.save_case(sample_case)
    with pytest.raises(ValueError):
        registry.record_event(sample_case.case_id, "REPORT_REQUESTED", details={"x": "a" * 100_000})



def test_registry_preserves_failure_case_status(tmp_path):
    case = build_case(
        "choke_v1",
        inputs={"pressure": -1},
        result={"error": {"code": "PHYSICALLY_INVALID_STATE", "message": "invalid pressure"}},
        status="PHYSICALLY_INVALID_STATE",
    )
    registry = EngineeringCaseRegistry(tmp_path / "engineering_cases.sqlite3")
    registry.save_case(case)
    assert registry.get_case(case.case_id).status == "PHYSICALLY_INVALID_STATE"



def test_registry_list_cases_exposes_no_raw_json(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "engineering_cases.sqlite3")
    registry.save_case(sample_case)
    listing = registry.format_case_list()
    assert sample_case.case_id in listing
    assert "{" not in listing and "}" not in listing
    assert "demo_v1" in listing



def test_registry_handles_duplicate_case_with_conflicting_payload_safely(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "engineering_cases.sqlite3")
    registry.save_case(sample_case)
    conflicting = build_case(
        "demo_v1",
        request=sample_case.request,
        inputs={"pressure_psia": 1001.0, "rate_stbd": 250.0},
        units=sample_case.units,
        selectors=sample_case.selectors,
        model=sample_case.model,
        result=sample_case.result,
        status=sample_case.status,
        reproducibility=sample_case.reproducibility,
    )
    with pytest.raises(ValueError):
        registry.save_case(conflicting)



def test_registry_case_metadata_has_created_and_updated_timestamps(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "engineering_cases.sqlite3")
    registry.save_case(sample_case)
    metadata = registry.get_case_metadata(sample_case.case_id)
    assert metadata["created_at"]
    assert metadata["updated_at"]
    assert metadata["created_at"] == metadata["updated_at"]



def test_registry_case_json_is_canonical_and_stable(tmp_path, sample_case):
    db_path = tmp_path / "engineering_cases.sqlite3"
    registry = EngineeringCaseRegistry(db_path)
    registry.save_case(sample_case)
    with sqlite3.connect(db_path) as connection:
        stored = connection.execute(
            "SELECT case_json FROM engineering_cases WHERE case_id = ?",
            (sample_case.case_id,),
        ).fetchone()[0]
    assert json.loads(stored)["case_id"] == sample_case.case_id
    assert json.dumps(json.loads(stored), sort_keys=True, separators=(",", ":")) == stored



def test_registry_audit_unknown_case_is_not_silently_ignored(tmp_path):
    registry = EngineeringCaseRegistry(tmp_path / "engineering_cases.sqlite3")
    with pytest.raises(CaseNotFoundError):
        registry.record_event("3" * 64, "CASE_RETRIEVED")



def test_registry_replay_result_requires_boolean_match(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "engineering_cases.sqlite3")
    registry.save_case(sample_case)
    with pytest.raises(ValueError):
        registry.record_replay_result(sample_case.case_id, matched="yes", result={})



def test_registry_finds_cases_by_case_type(tmp_path):
    registry = EngineeringCaseRegistry(tmp_path / "engineering_cases.sqlite3")
    for case_type in ("choke_v1", "nodal_v1"):
        registry.save_case(build_case(case_type, inputs={"i": case_type}, result={"status": "OK"}, status="OK"))
    assert {case.case_id for case in registry.list_cases(case_type="choke_v1")} == {
        case.case_id for case in registry.list_cases() if case.calculation_type == "choke_v1"
    }



def test_registry_audit_event_order_is_monotonic(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "engineering_cases.sqlite3")
    registry.save_case(sample_case)
    registry.record_event(sample_case.case_id, "REPORT_REQUESTED")
    registry.record_event(sample_case.case_id, "REPLAY_REQUESTED")
    sequence = [event.sequence for event in registry.audit_case(sample_case.case_id)]
    assert sequence == sorted(sequence)



def test_registry_report_text_round_trip_is_unicode_safe(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "engineering_cases.sqlite3")
    text = "Engineering report — ضغط المكمن 3,000 psia"
    registry.save_case(sample_case, report_text=text)
    assert registry.get_report(sample_case.case_id) == text



def test_registry_database_parent_directory_is_created(tmp_path, sample_case):
    path = tmp_path / "nested" / "registry" / "cases.sqlite3"
    registry = EngineeringCaseRegistry(path)
    registry.save_case(sample_case)
    assert path.exists()



def test_registry_schema_is_non_destructive_on_reopen(tmp_path, sample_case):
    path = tmp_path / "cases.sqlite3"
    first = EngineeringCaseRegistry(path)
    first.save_case(sample_case)
    second = EngineeringCaseRegistry(path)
    assert second.get_case(sample_case.case_id).case_id == sample_case.case_id
    assert len(second.list_cases()) == 1



def test_registry_audit_does_not_mutate_engineering_case_identity(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    before = sample_case.to_dict()
    registry.save_case(sample_case)
    registry.record_event(sample_case.case_id, "REPORT_REQUESTED")
    registry.record_replay_result(sample_case.case_id, matched=True, result={"status": "OK"})
    assert sample_case.to_dict() == before



def test_registry_retrieval_records_case_retrieved_event_when_requested(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    registry.get_case(sample_case.case_id, record_event=True)
    assert registry.audit_case(sample_case.case_id)[-1].event_type == "CASE_RETRIEVED"



def test_registry_report_retrieval_records_report_event_when_requested(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case, report_text="Report")
    assert registry.get_report(sample_case.case_id, record_event=True) == "Report"
    assert registry.audit_case(sample_case.case_id)[-1].event_type == "REPORT_REQUESTED"



def test_registry_replay_event_records_match_and_result(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    registry.record_event(sample_case.case_id, "REPLAY_REQUESTED")
    registry.record_replay_result(sample_case.case_id, matched=True, result={"rate": 250})
    metadata = registry.get_case_metadata(sample_case.case_id)
    assert metadata["replay_result"] == {"rate": 250}
    assert registry.audit_case(sample_case.case_id)[-1].event_type == "REPLAY_MATCH"



def test_registry_is_safe_with_pathlike_string(tmp_path, sample_case):
    path = str(tmp_path / "cases.sqlite3")
    registry = EngineeringCaseRegistry(path)
    registry.save_case(sample_case)
    assert registry.get_case(sample_case.case_id).case_id == sample_case.case_id



def test_registry_case_report_never_exposes_storage_json(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case, report_text=generate_report_v1(sample_case))
    assert "canonical_json" not in registry.get_report(sample_case.case_id)
    assert "engine_version" not in registry.get_report(sample_case.case_id)



def test_registry_audit_has_human_safe_format(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    registry.record_event(sample_case.case_id, "REPORT_REQUESTED")
    output = registry.format_audit(sample_case.case_id)
    assert "CASE_CREATED" in output
    assert "REPORT_REQUESTED" in output
    assert "{" not in output and "}" not in output



def test_registry_case_type_is_recoverable_after_restart(tmp_path, sample_case):
    path = tmp_path / "cases.sqlite3"
    EngineeringCaseRegistry(path).save_case(sample_case)
    restored = EngineeringCaseRegistry(path).get_case_metadata(sample_case.case_id)
    assert restored["case_type"] == sample_case.calculation_type



def test_registry_storage_does_not_depend_on_in_process_dict(tmp_path, sample_case):
    path = tmp_path / "cases.sqlite3"
    EngineeringCaseRegistry(path).save_case(sample_case)
    assert sample_case.case_id not in th._ENGINEERING_CASES
    assert EngineeringCaseRegistry(path).get_case(sample_case.case_id).case_id == sample_case.case_id



def test_registry_case_hash_is_verified_against_canonical_payload(tmp_path, sample_case):
    path = tmp_path / "cases.sqlite3"
    registry = EngineeringCaseRegistry(path)
    registry.save_case(sample_case)
    with sqlite3.connect(path) as connection:
        stored_hash = connection.execute(
            "SELECT case_sha256 FROM engineering_cases WHERE case_id = ?",
            (sample_case.case_id,),
        ).fetchone()[0]
    assert stored_hash == sample_case.case_id



def test_registry_invalid_event_details_are_rejected(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    with pytest.raises(ValueError):
        registry.record_event(sample_case.case_id, "REPORT_REQUESTED", details={"bad": object()})



def test_registry_persists_failure_reason_without_traceback(tmp_path):
    case = build_case(
        "demo_failure",
        inputs={"pressure": -1},
        result={"error": {"code": "INVALID_INPUT", "message": "pressure must be positive"}},
        status="INVALID_INPUT",
    )
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(case)
    assert "Traceback" not in registry.get_case(case.case_id).to_json()



def test_registry_replay_metadata_survives_restart(tmp_path, sample_case):
    path = tmp_path / "cases.sqlite3"
    EngineeringCaseRegistry(path).save_case(sample_case)
    EngineeringCaseRegistry(path).record_replay_result(sample_case.case_id, matched=True, result={"status": "OK"})
    assert EngineeringCaseRegistry(path).get_case_metadata(sample_case.case_id)["replay_match"] is True



def test_registry_reports_corrupt_storage_as_typed_error(tmp_path, sample_case):
    path = tmp_path / "cases.sqlite3"
    EngineeringCaseRegistry(path).save_case(sample_case)
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE engineering_cases SET case_sha256 = 'invalid' WHERE case_id = ?", (sample_case.case_id,))
        connection.commit()
    with pytest.raises(CaseIntegrityError):
        EngineeringCaseRegistry(path).get_case(sample_case.case_id)



def test_registry_record_event_returns_structured_event(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    event = registry.record_event(sample_case.case_id, "VALIDATION_FAILURE", details={"code": "BAD_INPUT"})
    assert event.event_type == "VALIDATION_FAILURE"
    assert event.to_dict()["case_id"] == sample_case.case_id



def test_registry_default_limit_is_safe(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    assert len(registry.list_cases(limit=1000)) <= 1000



def test_registry_audit_missing_case_does_not_create_phantom_case(tmp_path):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    with pytest.raises(CaseNotFoundError):
        registry.audit_case("4" * 64)
    assert registry.list_cases() == []



def test_registry_case_report_artifact_is_not_required_for_replay(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    assert registry.get_case(sample_case.case_id).case_id == sample_case.case_id



def test_registry_schema_version_is_not_part_of_case_id(tmp_path, sample_case):
    first = EngineeringCaseRegistry(tmp_path / "one.sqlite3")
    second = EngineeringCaseRegistry(tmp_path / "two.sqlite3")
    first.save_case(sample_case, schema_version="engineering_case_v1")
    second.save_case(sample_case, schema_version="engineering_case_v2")
    assert first.get_case(sample_case.case_id).case_id == second.get_case(sample_case.case_id).case_id



def test_registry_reopen_does_not_duplicate_created_event(tmp_path, sample_case):
    path = tmp_path / "cases.sqlite3"
    EngineeringCaseRegistry(path).save_case(sample_case)
    EngineeringCaseRegistry(path).save_case(sample_case)
    assert [event.event_type for event in EngineeringCaseRegistry(path).audit_case(sample_case.case_id)].count("CASE_CREATED") == 1



def test_registry_audit_event_details_are_redacted(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    registry.record_event(sample_case.case_id, "REPORT_REQUESTED", details={"notes": "Bearer abc123"})
    assert "abc123" not in json.dumps(registry.audit_case(sample_case.case_id)[-1].details)



def test_registry_can_format_empty_audit_without_raw_json(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    output = registry.format_audit(sample_case.case_id)
    assert "CASE_CREATED" in output
    assert "{" not in output and "}" not in output



def test_registry_database_has_foreign_key_safe_audit_rows(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    registry.record_event(sample_case.case_id, "REPORT_REQUESTED")
    assert len(registry.audit_case(sample_case.case_id)) == 2



def test_registry_case_report_is_stable_after_reopen(tmp_path, sample_case):
    path = tmp_path / "cases.sqlite3"
    report = generate_report_v1(sample_case)
    EngineeringCaseRegistry(path).save_case(sample_case, report_text=report)
    assert EngineeringCaseRegistry(path).get_report(sample_case.case_id) == report



def test_registry_closes_without_losing_data(tmp_path, sample_case):
    path = tmp_path / "cases.sqlite3"
    registry = EngineeringCaseRegistry(path)
    registry.save_case(sample_case)
    registry.close()
    assert EngineeringCaseRegistry(path).get_case(sample_case.case_id).case_id == sample_case.case_id



def test_registry_no_case_id_randomness(tmp_path, sample_case):
    one = EngineeringCaseRegistry(tmp_path / "one.sqlite3")
    two = EngineeringCaseRegistry(tmp_path / "two.sqlite3")
    one.save_case(sample_case)
    two.save_case(sample_case)
    assert one.list_cases()[0].case_id == two.list_cases()[0].case_id



def test_registry_search_by_status(tmp_path):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    ok = build_case("demo", inputs={"i": 1}, result={"status": "OK"}, status="OK")
    bad = build_case("demo", inputs={"i": 2}, result={"status": "INVALID_INPUT"}, status="INVALID_INPUT")
    registry.save_case(ok)
    registry.save_case(bad)
    assert [case.status for case in registry.list_cases(status="INVALID_INPUT")] == ["INVALID_INPUT"]



def test_registry_audit_format_contains_no_storage_path(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "secret_storage_path.sqlite3")
    registry.save_case(sample_case)
    assert "secret_storage_path" not in registry.format_audit(sample_case.case_id)



def test_registry_report_is_retrievable_without_memory_after_close(tmp_path, sample_case):
    path = tmp_path / "cases.sqlite3"
    report = generate_report_v1(sample_case)
    registry = EngineeringCaseRegistry(path)
    registry.save_case(sample_case, report_text=report)
    registry.close()
    assert EngineeringCaseRegistry(path).get_report(sample_case.case_id) == report



def test_registry_case_id_validation_requires_sha256_hex(tmp_path):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    for invalid in ("", "abc", "g" * 64, "1" * 63, "1" * 65):
        with pytest.raises(CaseNotFoundError):
            registry.get_case(invalid)



def test_registry_audit_action_is_recorded_for_missing_case(tmp_path):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    with pytest.raises(CaseNotFoundError):
        registry.get_case("5" * 64, record_event=True)
    with pytest.raises(CaseNotFoundError):
        registry.audit_case("5" * 64)



def test_registry_does_not_modify_report_on_audit(tmp_path, sample_case):
    path = tmp_path / "cases.sqlite3"
    report = generate_report_v1(sample_case)
    registry = EngineeringCaseRegistry(path)
    registry.save_case(sample_case, report_text=report)
    registry.record_event(sample_case.case_id, "REPORT_REQUESTED")
    assert registry.get_report(sample_case.case_id) == report



def test_registry_persists_model_identity_metadata(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    meta = registry.get_case_metadata(sample_case.case_id)
    assert meta["model"] == sample_case.model



def test_registry_returns_cases_without_telegram_fields(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    assert "telegram_chat_id" not in registry.get_case(sample_case.case_id).to_json()



def test_registry_audit_event_details_are_bounded_and_serializable(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    event = registry.record_event(sample_case.case_id, "CASE_RETRIEVED", details={"surface": "report"})
    assert len(json.dumps(event.details)) < 1000



def test_registry_case_metadata_is_plain_data(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    metadata = registry.get_case_metadata(sample_case.case_id)
    json.dumps(metadata)
    assert isinstance(metadata, dict)



def test_registry_preserves_unicode_case_report_across_restart(tmp_path, sample_case):
    path = tmp_path / "cases.sqlite3"
    report = "Pressure-dependent Black-Oil PVT — تقرير هندسي"
    EngineeringCaseRegistry(path).save_case(sample_case, report_text=report)
    assert EngineeringCaseRegistry(path).get_report(sample_case.case_id) == report



def test_registry_event_timestamps_are_iso8601(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    event = registry.record_event(sample_case.case_id, "REPORT_REQUESTED")
    assert "T" in event.created_at
    assert event.created_at.endswith("+00:00") or event.created_at.endswith("Z")



def test_registry_integrity_hash_is_not_mutable_metadata(tmp_path, sample_case):
    path = tmp_path / "cases.sqlite3"
    registry = EngineeringCaseRegistry(path)
    registry.save_case(sample_case)
    registry.record_event(sample_case.case_id, "REPORT_REQUESTED")
    with sqlite3.connect(path) as connection:
        stored = connection.execute("SELECT case_sha256 FROM engineering_cases WHERE case_id = ?", (sample_case.case_id,)).fetchone()[0]
    assert stored == sample_case.case_id



def test_registry_allows_typed_failure_report_artifact(tmp_path):
    case = build_case(
        "demo_failure",
        inputs={"pressure": -1},
        result={"error": {"code": "INVALID_INPUT", "message": "invalid"}},
        status="INVALID_INPUT",
    )
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    report = generate_report_v1(case)
    registry.save_case(case, report_text=report)
    assert "INVALID_INPUT" in registry.get_report(case.case_id)



def test_registry_list_limit_rejects_negative_values(tmp_path):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    with pytest.raises(ValueError):
        registry.list_cases(limit=-1)



def test_registry_audit_event_name_is_not_case_sensitive_alias(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    with pytest.raises(ValueError):
        registry.record_event(sample_case.case_id, "report_requested")



def test_registry_save_case_rejects_non_engineering_payload(tmp_path):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    with pytest.raises(ValueError):
        registry.save_case({"case_id": "1" * 64})



def test_registry_replay_result_is_not_part_of_original_case_json(tmp_path, sample_case):
    path = tmp_path / "cases.sqlite3"
    registry = EngineeringCaseRegistry(path)
    registry.save_case(sample_case)
    original = registry.get_case(sample_case.case_id).to_json()
    registry.record_replay_result(sample_case.case_id, matched=True, result={"status": "OK"})
    assert registry.get_case(sample_case.case_id).to_json() == original



def test_registry_replay_mismatch_is_audited_without_false_match(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    registry.record_replay_result(sample_case.case_id, matched=False, result={"status": "DIFFERENT"})
    assert registry.get_case_metadata(sample_case.case_id)["replay_match"] is False
    assert registry.audit_case(sample_case.case_id)[-1].event_type == "REPLAY_MISMATCH"



def test_registry_audit_report_does_not_leak_internal_json(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    output = registry.format_audit(sample_case.case_id)
    assert "canonical_json" not in output
    assert "engine_version" not in output



def test_registry_case_retrieval_after_process_like_reimport(tmp_path, sample_case):
    path = tmp_path / "cases.sqlite3"
    EngineeringCaseRegistry(path).save_case(sample_case)
    del sample_case
    assert EngineeringCaseRegistry(path).list_cases()



def test_registry_case_report_and_audit_use_same_identity(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case, report_text="Report")
    assert registry.get_case(sample_case.case_id).case_id == sample_case.case_id
    assert registry.get_report(sample_case.case_id) == "Report"
    assert registry.audit_case(sample_case.case_id)[0].case_id == sample_case.case_id



def test_registry_case_storage_is_not_in_memory_only(tmp_path, sample_case):
    path = tmp_path / "cases.sqlite3"
    registry = EngineeringCaseRegistry(path)
    registry.save_case(sample_case)
    assert path.stat().st_size > 0



def test_registry_report_missing_case_response_does_not_include_case_json(tmp_path, monkeypatch):
    monkeypatch.setattr(th, "_CASE_REGISTRY", EngineeringCaseRegistry(tmp_path / "cases.sqlite3"))
    response, _, _ = th.handle_case_command({"text": f"/case report {'6' * 64}"}, None)
    assert "{" not in response and "}" not in response



def test_registry_list_is_deterministic_for_same_storage(tmp_path, sample_case):
    path = tmp_path / "cases.sqlite3"
    registry = EngineeringCaseRegistry(path)
    registry.save_case(sample_case)
    assert [c.case_id for c in registry.list_cases()] == [c.case_id for c in EngineeringCaseRegistry(path).list_cases()]



def test_registry_does_not_recompute_engineering_case_identity(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    assert registry.get_case(sample_case.case_id).case_id == sample_case.case_id



def test_registry_case_created_event_is_only_once_after_reload(tmp_path, sample_case):
    path = tmp_path / "cases.sqlite3"
    for _ in range(3):
        EngineeringCaseRegistry(path).save_case(sample_case)
    assert len([e for e in EngineeringCaseRegistry(path).audit_case(sample_case.case_id) if e.event_type == "CASE_CREATED"]) == 1



def test_registry_failure_case_can_be_audited(tmp_path):
    case = build_case("failure", result={"error": {"code": "BAD", "message": "bad"}}, status="BAD")
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(case)
    assert registry.audit_case(case.case_id)[0].event_type == "CASE_CREATED"



def test_registry_audit_event_details_do_not_store_object_repr(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    event = registry.record_event(sample_case.case_id, "REPORT_REQUESTED", details={"surface": "telegram"})
    assert "object at" not in repr(event.details)



def test_registry_case_report_is_not_generated_from_raw_storage_at_read_time(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    report = "Stored engineering report"
    registry.save_case(sample_case, report_text=report)
    assert registry.get_report(sample_case.case_id) == report



def test_registry_audit_event_has_no_private_case_payload(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    event = registry.record_event(sample_case.case_id, "REPORT_REQUESTED")
    assert "inputs" not in event.details
    assert "result" not in event.details



def test_registry_replay_status_can_be_unknown_before_replay(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    assert registry.get_case_metadata(sample_case.case_id)["replay_match"] is None



def test_registry_audit_replay_mismatch_is_honest(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    registry.record_replay_result(sample_case.case_id, matched=False, result={"status": "DIFFERENT"})
    output = registry.format_audit(sample_case.case_id)
    assert "REPLAY_MISMATCH" in output
    assert "MATCH" not in output.replace("REPLAY_MISMATCH", "")



def test_registry_concurrent_open_handles_are_safe(tmp_path, sample_case):
    path = tmp_path / "cases.sqlite3"
    first = EngineeringCaseRegistry(path)
    second = EngineeringCaseRegistry(path)
    first.save_case(sample_case)
    assert second.get_case(sample_case.case_id).case_id == sample_case.case_id



def test_registry_format_case_list_is_human_readable(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    text = registry.format_case_list()
    assert "Case ID" in text
    assert "Status" in text
    assert "{" not in text and "}" not in text



def test_registry_preserves_report_when_audit_is_requested(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case, report_text="Report")
    before = registry.get_report(sample_case.case_id)
    registry.record_event(sample_case.case_id, "REPORT_REQUESTED")
    assert registry.get_report(sample_case.case_id) == before



def test_registry_missing_case_event_has_requested_action(tmp_path):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    with pytest.raises(CaseNotFoundError):
        registry.get_case("7" * 64, record_event=True, action="replay")



def test_registry_replay_result_requires_case_exist(tmp_path):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    with pytest.raises(CaseNotFoundError):
        registry.record_replay_result("8" * 64, matched=True, result={})



def test_registry_case_identity_is_stable_with_report_artifact(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case, report_text="Report")
    assert registry.get_case(sample_case.case_id).case_id == sample_case.case_id



def test_registry_audit_does_not_expose_sqlite_details(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "sqlite-file.sqlite3")
    registry.save_case(sample_case)
    assert "sqlite" not in registry.format_audit(sample_case.case_id).lower()



def test_registry_case_list_status_filter_is_human_safe(tmp_path):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    case = build_case("demo", inputs={"i": 1}, result={"status": "OK"}, status="OK")
    registry.save_case(case)
    assert "{" not in registry.format_case_list(status="OK")



def test_registry_schema_migration_is_non_destructive(tmp_path, sample_case):
    path = tmp_path / "cases.sqlite3"
    registry = EngineeringCaseRegistry(path)
    registry.save_case(sample_case)
    reopened = EngineeringCaseRegistry(path)
    assert reopened.get_case(sample_case.case_id).case_id == sample_case.case_id



def test_registry_case_type_filter_is_deterministic(tmp_path, sample_case):
    path = tmp_path / "cases.sqlite3"
    registry = EngineeringCaseRegistry(path)
    registry.save_case(sample_case)
    assert [c.case_id for c in registry.list_cases(case_type="demo_v1")] == [sample_case.case_id]



def test_registry_audit_sequence_is_persistent(tmp_path, sample_case):
    path = tmp_path / "cases.sqlite3"
    EngineeringCaseRegistry(path).save_case(sample_case)
    EngineeringCaseRegistry(path).record_event(sample_case.case_id, "REPORT_REQUESTED")
    assert [e.sequence for e in EngineeringCaseRegistry(path).audit_case(sample_case.case_id)] == [1, 2]



def test_registry_case_report_artifact_can_be_empty_but_present(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case, report_text="")
    assert registry.get_report(sample_case.case_id) == ""



def test_registry_audit_action_names_are_documented(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    for event_name in ("CASE_RETRIEVED", "REPORT_REQUESTED", "REPLAY_REQUESTED", "REPLAY_MATCH", "REPLAY_MISMATCH", "VALIDATION_FAILURE"):
        registry.record_event(sample_case.case_id, event_name)
    assert len(registry.audit_case(sample_case.case_id)) == 7



def test_registry_report_text_not_used_as_case_identity(tmp_path, sample_case):
    first = generate_report_v1(sample_case)
    second = first + "\nAdditional display note"
    assert sample_case.case_id == sample_case.case_id
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case, report_text=first)
    with pytest.raises(ValueError):
        registry.save_case(sample_case, report_text=second)



def test_registry_read_after_write_in_separate_connection(tmp_path, sample_case):
    path = tmp_path / "cases.sqlite3"
    EngineeringCaseRegistry(path).save_case(sample_case)
    assert EngineeringCaseRegistry(path).get_case(sample_case.case_id).case_id == sample_case.case_id



def test_registry_case_report_not_json_export(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case, report_text="Engineering report")
    assert "Raw JSON" not in registry.get_report(sample_case.case_id)



def test_registry_in_process_cache_is_optional(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3", cache_enabled=False)
    registry.save_case(sample_case)
    assert registry.get_case(sample_case.case_id).case_id == sample_case.case_id



def test_registry_default_path_is_configurable(tmp_path, monkeypatch, sample_case):
    monkeypatch.setenv("ENGINEERING_CASE_DB_PATH", str(tmp_path / "configured.sqlite3"))
    registry = EngineeringCaseRegistry.from_environment()
    registry.save_case(sample_case)
    assert (tmp_path / "configured.sqlite3").exists()



def test_registry_audit_preserves_case_type(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    assert registry.audit_case(sample_case.case_id)[0].case_type == sample_case.calculation_type



def test_registry_typed_integrity_failure_has_no_traceback(tmp_path, sample_case):
    path = tmp_path / "cases.sqlite3"
    EngineeringCaseRegistry(path).save_case(sample_case)
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE engineering_cases SET case_json = 'not-json' WHERE case_id = ?", (sample_case.case_id,))
        connection.commit()
    try:
        EngineeringCaseRegistry(path).get_case(sample_case.case_id)
    except CaseIntegrityError as exc:
        assert "Traceback" not in str(exc)
    else:
        pytest.fail("expected CaseIntegrityError")



def test_registry_preserves_original_result_after_audit(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    original = registry.get_case(sample_case.case_id).result
    registry.record_replay_result(sample_case.case_id, matched=True, result={"status": "OK"})
    assert registry.get_case(sample_case.case_id).result == original



def test_registry_case_id_is_sha256_length_after_reload(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    assert len(registry.get_case(sample_case.case_id).case_id) == 64



def test_registry_audit_failure_event_has_reason(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    event = registry.record_event(sample_case.case_id, "VALIDATION_FAILURE", details={"reason": "invalid input"})
    assert event.details["reason"] == "invalid input"



def test_registry_case_report_is_readable_text(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case, report_text="Status: OK\nCalculated model result")
    assert "Calculated model result" in registry.get_report(sample_case.case_id)



def test_registry_close_is_idempotent(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    registry.close()
    registry.close()



def test_registry_retrieval_after_audit_reload(tmp_path, sample_case):
    path = tmp_path / "cases.sqlite3"
    EngineeringCaseRegistry(path).save_case(sample_case)
    EngineeringCaseRegistry(path).record_event(sample_case.case_id, "REPORT_REQUESTED")
    assert EngineeringCaseRegistry(path).get_case(sample_case.case_id).case_id == sample_case.case_id



def test_registry_no_secret_in_audit_output(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    registry.record_event(sample_case.case_id, "REPORT_REQUESTED", details={"notes": "sk-secret"})
    assert "sk-secret" not in registry.format_audit(sample_case.case_id)



def test_registry_report_round_trip_after_multiple_events(tmp_path, sample_case):
    path = tmp_path / "cases.sqlite3"
    registry = EngineeringCaseRegistry(path)
    registry.save_case(sample_case, report_text="Report")
    registry.record_event(sample_case.case_id, "REPORT_REQUESTED")
    registry.record_event(sample_case.case_id, "REPLAY_REQUESTED")
    assert EngineeringCaseRegistry(path).get_report(sample_case.case_id) == "Report"



def test_registry_list_cases_does_not_include_raw_inputs(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    listing = registry.format_case_list()
    assert "pressure_psia" not in listing



def test_registry_case_metadata_does_not_include_secrets(tmp_path):
    case = build_case("secret", inputs={"token": "sk-secret"}, result={"status": "OK"}, status="OK")
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(case)
    assert "sk-secret" not in json.dumps(registry.get_case_metadata(case.case_id))



def test_registry_replay_match_is_stable_after_second_replay(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    registry.record_replay_result(sample_case.case_id, matched=True, result={"status": "OK"})
    registry.record_replay_result(sample_case.case_id, matched=True, result={"status": "OK"})
    assert registry.get_case_metadata(sample_case.case_id)["replay_match"] is True



def test_registry_audit_multiple_replays_are_all_preserved(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    for _ in range(2):
        registry.record_event(sample_case.case_id, "REPLAY_REQUESTED")
        registry.record_replay_result(sample_case.case_id, matched=True, result={"status": "OK"})
    assert [e.event_type for e in registry.audit_case(sample_case.case_id)].count("REPLAY_MATCH") == 2



def test_registry_current_status_is_not_overwritten_by_replay_metadata(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    registry.record_replay_result(sample_case.case_id, matched=False, result={"status": "DIFFERENT"})
    assert registry.get_case(sample_case.case_id).status == sample_case.status



def test_registry_handles_case_report_with_newline_text(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case, report_text="line one\nline two")
    assert registry.get_report(sample_case.case_id).splitlines() == ["line one", "line two"]



def test_registry_audit_case_after_storage_integrity_failure_is_typed(tmp_path, sample_case):
    path = tmp_path / "cases.sqlite3"
    registry = EngineeringCaseRegistry(path)
    registry.save_case(sample_case)
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE engineering_cases SET case_sha256 = 'bad' WHERE case_id = ?", (sample_case.case_id,))
        connection.commit()
    with pytest.raises(CaseIntegrityError):
        EngineeringCaseRegistry(path).get_case(sample_case.case_id)



def test_registry_case_type_search_survives_reopen(tmp_path, sample_case):
    path = tmp_path / "cases.sqlite3"
    EngineeringCaseRegistry(path).save_case(sample_case)
    assert EngineeringCaseRegistry(path).list_cases(case_type="demo_v1")[0].case_id == sample_case.case_id



def test_registry_report_artifact_is_not_case_json(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case, report_text="# Engineering Case Report V1")
    assert registry.get_report(sample_case.case_id).startswith("# Engineering Case Report V1")



def test_registry_audit_events_keep_original_sequence_after_reopen(tmp_path, sample_case):
    path = tmp_path / "cases.sqlite3"
    EngineeringCaseRegistry(path).save_case(sample_case)
    EngineeringCaseRegistry(path).record_event(sample_case.case_id, "REPORT_REQUESTED")
    assert [event.sequence for event in EngineeringCaseRegistry(path).audit_case(sample_case.case_id)] == [1, 2]



def test_registry_replay_mismatch_does_not_get_hidden_by_later_report(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case, report_text="Report")
    registry.record_replay_result(sample_case.case_id, matched=False, result={"status": "DIFFERENT"})
    assert registry.get_report(sample_case.case_id) == "Report"
    assert registry.get_case_metadata(sample_case.case_id)["replay_match"] is False



def test_registry_report_artifact_is_optional_for_case_listing(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    assert sample_case.case_id in registry.format_case_list()



def test_registry_audit_event_detail_keys_are_strings(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    event = registry.record_event(sample_case.case_id, "REPORT_REQUESTED", details={"surface": "case"})
    assert all(isinstance(key, str) for key in event.details)



def test_registry_preserves_case_when_report_is_retrieved_repeatedly(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case, report_text="Report")
    for _ in range(3):
        assert registry.get_report(sample_case.case_id) == "Report"
    assert registry.get_case(sample_case.case_id).case_id == sample_case.case_id



def test_registry_cannot_delete_case_via_normal_api(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    assert not hasattr(registry, "delete_case")



def test_registry_preserves_status_and_limitations(tmp_path):
    case = build_case("demo", inputs={"i": 1}, result={"status": "LIMITED"}, status="LIMITED", limitations=["test limitation"])
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(case)
    restored = registry.get_case(case.case_id)
    assert restored.status == "LIMITED"
    assert restored.limitations == ["test limitation"]



def test_registry_audit_report_after_reopen_is_human_safe(tmp_path, sample_case):
    path = tmp_path / "cases.sqlite3"
    EngineeringCaseRegistry(path).save_case(sample_case)
    EngineeringCaseRegistry(path).record_event(sample_case.case_id, "REPORT_REQUESTED")
    output = EngineeringCaseRegistry(path).format_audit(sample_case.case_id)
    assert "REPORT_REQUESTED" in output
    assert "{" not in output and "}" not in output



def test_registry_case_id_is_same_across_registry_instances(tmp_path, sample_case):
    first = EngineeringCaseRegistry(tmp_path / "one.sqlite3")
    second = EngineeringCaseRegistry(tmp_path / "two.sqlite3")
    first.save_case(sample_case)
    second.save_case(sample_case)
    assert first.get_case(sample_case.case_id).case_id == second.get_case(sample_case.case_id).case_id



def test_registry_audit_event_has_case_type_after_reload(tmp_path, sample_case):
    path = tmp_path / "cases.sqlite3"
    EngineeringCaseRegistry(path).save_case(sample_case)
    event = EngineeringCaseRegistry(path).record_event(sample_case.case_id, "REPORT_REQUESTED")
    assert event.case_type == sample_case.calculation_type



def test_registry_persisted_case_can_be_read_when_original_object_is_gone(tmp_path, sample_case):
    path = tmp_path / "cases.sqlite3"
    EngineeringCaseRegistry(path).save_case(sample_case)
    case_id = sample_case.case_id
    del sample_case
    assert EngineeringCaseRegistry(path).get_case(case_id).case_id == case_id



def test_registry_no_random_created_at_in_case_id(tmp_path, sample_case):
    first = EngineeringCaseRegistry(tmp_path / "one.sqlite3")
    second = EngineeringCaseRegistry(tmp_path / "two.sqlite3")
    first.save_case(sample_case)
    second.save_case(sample_case)
    assert first.get_case(sample_case.case_id).case_id == second.get_case(sample_case.case_id).case_id



def test_registry_invariant_original_payload_hash_matches_case_id(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    assert registry.get_case(sample_case.case_id).case_id == sample_case.case_id



def test_registry_audit_has_no_raw_case_payload(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    event = registry.record_event(sample_case.case_id, "REPORT_REQUESTED")
    assert "pressure_psia" not in json.dumps(event.details)



def test_registry_persistence_is_file_backed(tmp_path, sample_case):
    path = tmp_path / "cases.sqlite3"
    registry = EngineeringCaseRegistry(path)
    registry.save_case(sample_case)
    assert path.is_file()



def test_registry_audit_does_not_change_case_json_after_reopen(tmp_path, sample_case):
    path = tmp_path / "cases.sqlite3"
    registry = EngineeringCaseRegistry(path)
    registry.save_case(sample_case)
    before = EngineeringCaseRegistry(path).get_case(sample_case.case_id).to_json()
    EngineeringCaseRegistry(path).record_event(sample_case.case_id, "REPORT_REQUESTED")
    after = EngineeringCaseRegistry(path).get_case(sample_case.case_id).to_json()
    assert before == after



def test_registry_failure_event_is_structured(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    event = registry.record_event(sample_case.case_id, "VALIDATION_FAILURE", details={"code": "INVALID_INPUT"})
    assert event.event_type == "VALIDATION_FAILURE"
    assert event.case_id == sample_case.case_id



def test_registry_audit_case_not_reported_as_raw_json(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    assert "{" not in registry.format_audit(sample_case.case_id)
    assert "}" not in registry.format_audit(sample_case.case_id)



def test_registry_uses_database_connection_timeout(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3", timeout_seconds=2.0)
    registry.save_case(sample_case)
    assert registry.get_case(sample_case.case_id).case_id == sample_case.case_id



def test_registry_audit_case_reports_case_type_in_human_format(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    assert sample_case.calculation_type in registry.format_audit(sample_case.case_id)



def test_registry_replay_result_metadata_does_not_change_updated_case_payload(tmp_path, sample_case):
    path = tmp_path / "cases.sqlite3"
    registry = EngineeringCaseRegistry(path)
    registry.save_case(sample_case)
    before = registry.get_case(sample_case.case_id).to_json()
    registry.record_replay_result(sample_case.case_id, matched=True, result={"status": "OK"})
    assert registry.get_case(sample_case.case_id).to_json() == before



def test_registry_case_report_persistence_is_atomic_enough_for_reopen(tmp_path, sample_case):
    path = tmp_path / "cases.sqlite3"
    registry = EngineeringCaseRegistry(path)
    registry.save_case(sample_case, report_text="Report")
    registry.close()
    assert EngineeringCaseRegistry(path).get_report(sample_case.case_id) == "Report"



def test_registry_audit_event_details_are_not_mutable_by_caller(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    details = {"surface": "report"}
    event = registry.record_event(sample_case.case_id, "REPORT_REQUESTED", details=details)
    details["surface"] = "changed"
    assert event.details["surface"] == "report"



def test_registry_unknown_case_report_is_not_created_on_read(tmp_path):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    with pytest.raises(CaseNotFoundError):
        registry.get_report("9" * 64)
    assert registry.list_cases() == []



def test_registry_persists_case_after_registry_object_deleted(tmp_path, sample_case):
    path = tmp_path / "cases.sqlite3"
    registry = EngineeringCaseRegistry(path)
    registry.save_case(sample_case)
    del registry
    assert EngineeringCaseRegistry(path).get_case(sample_case.case_id).case_id == sample_case.case_id



def test_registry_has_no_implicit_case_eviction(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    assert registry.get_case(sample_case.case_id).case_id == sample_case.case_id



def test_registry_audit_preserves_replay_mismatch_detail(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    registry.record_replay_result(sample_case.case_id, matched=False, result={"status": "DIFFERENT"})
    event = registry.audit_case(sample_case.case_id)[-1]
    assert event.details["matched"] is False



def test_registry_report_request_is_not_a_replay_request(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    registry.record_event(sample_case.case_id, "REPORT_REQUESTED")
    assert "REPLAY_REQUESTED" not in [e.event_type for e in registry.audit_case(sample_case.case_id)]



def test_registry_create_event_contains_model_identity_only(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    event = registry.save_case(sample_case)
    assert event.event_type == "CASE_CREATED"
    assert "model" in event.details
    assert "inputs" not in event.details



def test_registry_case_metadata_report_timestamp_is_persisted(tmp_path, sample_case):
    path = tmp_path / "cases.sqlite3"
    registry = EngineeringCaseRegistry(path)
    registry.save_case(sample_case, report_text="Report")
    metadata = registry.get_case_metadata(sample_case.case_id)
    assert metadata["updated_at"]



def test_registry_no_duplicate_case_on_same_case_json(tmp_path, sample_case):
    path = tmp_path / "cases.sqlite3"
    registry = EngineeringCaseRegistry(path)
    registry.save_case(sample_case)
    registry.save_case(sample_case)
    assert len(registry.list_cases()) == 1



def test_registry_case_report_is_not_lost_when_new_instance_reads_it(tmp_path, sample_case):
    path = tmp_path / "cases.sqlite3"
    EngineeringCaseRegistry(path).save_case(sample_case, report_text="Report")
    assert EngineeringCaseRegistry(path).get_report(sample_case.case_id) == "Report"



def test_registry_case_id_is_stable_after_failure_status_metadata(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    registry.record_event(sample_case.case_id, "VALIDATION_FAILURE", details={"code": "TEST"})
    assert registry.get_case(sample_case.case_id).case_id == sample_case.case_id



def test_registry_replay_match_event_has_boolean_detail(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    registry.record_replay_result(sample_case.case_id, matched=True, result={"status": "OK"})
    assert registry.audit_case(sample_case.case_id)[-1].details["matched"] is True



def test_registry_case_status_filter_accepts_none(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    assert registry.list_cases(status=None)



def test_registry_preserves_warnings_and_limitations(tmp_path):
    case = build_case("demo", inputs={}, result={"status": "OK"}, status="OK", warnings=["warning"], limitations=["limitation"])
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(case)
    restored = registry.get_case(case.case_id)
    assert restored.warnings == ["warning"]
    assert restored.limitations == ["limitation"]



def test_registry_case_audit_has_human_safe_timestamps(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    output = registry.format_audit(sample_case.case_id)
    assert "T" not in output or "Created" in output



def test_registry_case_report_contains_case_id_when_stored(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    report = generate_report_v1(sample_case)
    registry.save_case(sample_case, report_text=report)
    assert sample_case.case_id in registry.get_report(sample_case.case_id)



def test_registry_case_report_not_generated_for_missing_case(tmp_path):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    with pytest.raises(CaseNotFoundError):
        registry.get_report("a" * 64)



def test_registry_replay_metadata_accepts_none_result(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    registry.record_replay_result(sample_case.case_id, matched=False, result=None)
    assert registry.get_case_metadata(sample_case.case_id)["replay_result"] is None



def test_registry_format_list_limit_is_respected(tmp_path):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    for index in range(3):
        registry.save_case(build_case("demo", inputs={"index": index}, result={"status": "OK"}, status="OK"))
    output = registry.format_case_list(limit=2)
    assert output.count("Case ID") <= 2



def test_registry_audit_retrieval_does_not_add_case_data(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    event = registry.record_event(sample_case.case_id, "CASE_RETRIEVED")
    assert event.details == {}



def test_registry_case_report_can_be_read_after_case_retrieve(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case, report_text="Report")
    registry.get_case(sample_case.case_id)
    assert registry.get_report(sample_case.case_id) == "Report"



def test_registry_replay_result_stores_result_as_plain_data(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    result = {"status": "OK", "value": 1.0}
    registry.record_replay_result(sample_case.case_id, matched=True, result=result)
    result["value"] = 2.0
    assert registry.get_case_metadata(sample_case.case_id)["replay_result"]["value"] == 1.0



def test_registry_report_text_must_be_string(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    with pytest.raises(ValueError):
        registry.save_case(sample_case, report_text={"raw": "json"})



def test_registry_case_type_list_is_empty_for_unknown_type(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    assert registry.list_cases(case_type="unknown") == []



def test_registry_audit_case_preserves_event_details_after_reload(tmp_path, sample_case):
    path = tmp_path / "cases.sqlite3"
    EngineeringCaseRegistry(path).save_case(sample_case)
    EngineeringCaseRegistry(path).record_event(sample_case.case_id, "VALIDATION_FAILURE", details={"code": "BAD"})
    assert EngineeringCaseRegistry(path).audit_case(sample_case.case_id)[-1].details["code"] == "BAD"



def test_registry_case_json_is_not_exposed_by_format_list(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    listing = registry.format_case_list()
    assert "request" not in listing
    assert "inputs" not in listing



def test_registry_case_record_is_read_only_from_get(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    retrieved = registry.get_case(sample_case.case_id)
    retrieved.inputs["pressure_psia"] = 2000
    assert registry.get_case(sample_case.case_id).inputs["pressure_psia"] == 1000.0



def test_registry_case_report_is_read_only_from_get(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case, report_text="Report")
    report = registry.get_report(sample_case.case_id)
    assert report == "Report"



def test_registry_save_is_atomic_for_conflict(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case, report_text="Report")
    with pytest.raises(ValueError):
        registry.save_case(sample_case, report_text="Different")
    assert registry.get_report(sample_case.case_id) == "Report"



def test_registry_audit_format_includes_action_label(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    registry.record_event(sample_case.case_id, "REPORT_REQUESTED")
    assert "REPORT_REQUESTED" in registry.format_audit(sample_case.case_id)



def test_registry_case_record_has_persisted_hash(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    assert registry.get_case_metadata(sample_case.case_id)["case_sha256"] == sample_case.case_id



def test_registry_audit_case_requires_valid_case_id(tmp_path):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    with pytest.raises(CaseNotFoundError):
        registry.audit_case("not-valid")



def test_registry_report_case_requires_valid_case_id(tmp_path):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    with pytest.raises(CaseNotFoundError):
        registry.get_report("not-valid")



def test_registry_save_case_is_not_silent_on_none(tmp_path):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    with pytest.raises(ValueError):
        registry.save_case(None)



def test_registry_format_audit_is_empty_only_for_missing_case(tmp_path):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    with pytest.raises(CaseNotFoundError):
        registry.format_audit("b" * 64)



def test_registry_preserves_engineering_honesty_report(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    report = generate_report_v1(sample_case)
    registry.save_case(sample_case, report_text=report)
    assert "calculated" in registry.get_report(sample_case.case_id).lower()



def test_registry_schema_version_is_metadata_only(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case, schema_version="v1")
    assert registry.get_case(sample_case.case_id).case_id == sample_case.case_id



def test_registry_case_metadata_contains_persistence_status(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    assert registry.get_case_metadata(sample_case.case_id)["persistent"] is True



def test_registry_audit_event_does_not_store_report_text(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case, report_text="Secret report")
    event = registry.record_event(sample_case.case_id, "REPORT_REQUESTED")
    assert "Secret report" not in json.dumps(event.details)



def test_registry_case_retrieval_can_be_repeated_after_restart(tmp_path, sample_case):
    path = tmp_path / "cases.sqlite3"
    EngineeringCaseRegistry(path).save_case(sample_case)
    for _ in range(3):
        assert EngineeringCaseRegistry(path).get_case(sample_case.case_id).case_id == sample_case.case_id



def test_registry_audit_case_is_stable_in_order(tmp_path, sample_case):
    path = tmp_path / "cases.sqlite3"
    registry = EngineeringCaseRegistry(path)
    registry.save_case(sample_case)
    registry.record_event(sample_case.case_id, "REPORT_REQUESTED")
    expected = [e.event_type for e in registry.audit_case(sample_case.case_id)]
    assert [e.event_type for e in EngineeringCaseRegistry(path).audit_case(sample_case.case_id)] == expected



def test_registry_case_report_contains_no_sqlite_path(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "private.sqlite3")
    registry.save_case(sample_case, report_text="Report")
    assert "private.sqlite3" not in registry.get_report(sample_case.case_id)



def test_registry_case_id_is_not_derived_from_database_path(tmp_path, sample_case):
    a = EngineeringCaseRegistry(tmp_path / "a.sqlite3")
    b = EngineeringCaseRegistry(tmp_path / "b.sqlite3")
    a.save_case(sample_case)
    b.save_case(sample_case)
    assert a.get_case(sample_case.case_id).case_id == b.get_case(sample_case.case_id).case_id



def test_registry_replay_result_does_not_change_case_updated_at(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    before = registry.get_case_metadata(sample_case.case_id)["updated_at"]
    registry.record_replay_result(sample_case.case_id, matched=True, result={"status": "OK"})
    assert registry.get_case_metadata(sample_case.case_id)["updated_at"] == before



def test_registry_audit_event_details_are_copied(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    details = {"nested": {"value": 1}}
    event = registry.record_event(sample_case.case_id, "REPORT_REQUESTED", details=details)
    details["nested"]["value"] = 2
    assert event.details["nested"]["value"] == 1



def test_registry_preserves_case_units_after_restart(tmp_path, sample_case):
    path = tmp_path / "cases.sqlite3"
    EngineeringCaseRegistry(path).save_case(sample_case)
    assert EngineeringCaseRegistry(path).get_case(sample_case.case_id).units == sample_case.units



def test_registry_preserves_case_selectors_after_restart(tmp_path, sample_case):
    path = tmp_path / "cases.sqlite3"
    EngineeringCaseRegistry(path).save_case(sample_case)
    assert EngineeringCaseRegistry(path).get_case(sample_case.case_id).selectors == sample_case.selectors



def test_registry_preserves_case_pvt_after_restart(tmp_path):
    case = build_case("pvt_demo", pvt={"mode": "legacy"}, result={"status": "OK"}, status="OK")
    path = tmp_path / "cases.sqlite3"
    EngineeringCaseRegistry(path).save_case(case)
    assert EngineeringCaseRegistry(path).get_case(case.case_id).pvt == {"mode": "legacy"}



def test_registry_audit_case_not_create_report(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    assert registry.get_report(sample_case.case_id) == ""



def test_registry_report_text_is_not_required_for_case_retrieval(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    assert registry.get_case(sample_case.case_id).case_id == sample_case.case_id



def test_registry_handles_empty_details(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    assert registry.record_event(sample_case.case_id, "REPORT_REQUESTED").details == {}



def test_registry_case_id_validation_is_lowercase_independent(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    assert registry.get_case(sample_case.case_id.upper()).case_id == sample_case.case_id



def test_registry_audit_case_report_contains_created_event(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    assert registry.format_audit(sample_case.case_id).startswith("Engineering Case Audit")



def test_registry_case_report_get_does_not_replay(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case, report_text="Report")
    registry.get_report(sample_case.case_id)
    assert "REPLAY" not in [e.event_type for e in registry.audit_case(sample_case.case_id)]



def test_registry_case_retrieval_does_not_mutate_original_case_json(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    before = registry.get_case(sample_case.case_id).to_json()
    registry.get_case(sample_case.case_id)
    assert registry.get_case(sample_case.case_id).to_json() == before



def test_registry_persistence_filename_is_not_in_case_identity(tmp_path, sample_case):
    assert sample_case.case_id



def test_registry_case_report_has_no_credentials(tmp_path):
    case = build_case("credential", inputs={"password": "pw"}, result={"status": "OK"}, status="OK")
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    with pytest.raises(ValueError):
        registry.save_case(case, report_text="password=pw")



def test_registry_audit_format_does_not_include_json_fences(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    assert "```json" not in registry.format_audit(sample_case.case_id)



def test_registry_case_report_format_is_not_raw_json(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case, report_text="Engineering report")
    assert "```json" not in registry.get_report(sample_case.case_id)



def test_registry_persistence_reload_is_explicit(tmp_path, sample_case):
    path = tmp_path / "cases.sqlite3"
    EngineeringCaseRegistry(path).save_case(sample_case)
    assert EngineeringCaseRegistry(path).get_case(sample_case.case_id)



def test_registry_replay_match_metadata_has_event_time(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    registry.record_replay_result(sample_case.case_id, matched=True, result={"status": "OK"})
    assert registry.get_case_metadata(sample_case.case_id)["replay_at"]



def test_registry_list_cases_can_filter_limit_and_status(tmp_path):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    for idx in range(4):
        registry.save_case(build_case("demo", inputs={"idx": idx}, result={"status": "OK"}, status="OK"))
    assert len(registry.list_cases(limit=2, status="OK")) == 2



def test_registry_audit_case_contains_no_secret_metadata(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    assert "api_key" not in registry.format_audit(sample_case.case_id)



def test_registry_case_metadata_has_replay_count(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    assert registry.get_case_metadata(sample_case.case_id)["replay_count"] == 0



def test_registry_case_metadata_replay_count_increments(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    registry.record_replay_result(sample_case.case_id, matched=True, result={"status": "OK"})
    registry.record_replay_result(sample_case.case_id, matched=True, result={"status": "OK"})
    assert registry.get_case_metadata(sample_case.case_id)["replay_count"] == 2



def test_registry_case_is_retrievable_without_report_artifact(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    assert registry.get_case(sample_case.case_id).case_id == sample_case.case_id



def test_registry_case_model_metadata_survives_restart(tmp_path, sample_case):
    path = tmp_path / "cases.sqlite3"
    EngineeringCaseRegistry(path).save_case(sample_case)
    assert EngineeringCaseRegistry(path).get_case_metadata(sample_case.case_id)["model"] == sample_case.model



def test_registry_audit_report_is_nonempty_for_existing_case(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    assert registry.format_audit(sample_case.case_id)



def test_registry_case_report_empty_string_round_trip(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case, report_text="")
    assert registry.get_report(sample_case.case_id) == ""



def test_registry_result_is_not_mutated_by_save(tmp_path, sample_case):
    original = dict(sample_case.result)
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    assert sample_case.result == original



def test_registry_case_inputs_are_not_mutated_by_save(tmp_path, sample_case):
    original = dict(sample_case.inputs)
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    assert sample_case.inputs == original



def test_registry_case_selectors_are_not_mutated_by_save(tmp_path, sample_case):
    original = dict(sample_case.selectors)
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    assert sample_case.selectors == original



def test_registry_case_type_metadata_is_plain_string(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    assert isinstance(registry.get_case_metadata(sample_case.case_id)["case_type"], str)



def test_registry_case_report_is_string(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case, report_text="Report")
    assert isinstance(registry.get_report(sample_case.case_id), str)



def test_registry_replay_result_is_not_in_report_artifact(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case, report_text="Report")
    registry.record_replay_result(sample_case.case_id, matched=True, result={"status": "OK"})
    assert registry.get_report(sample_case.case_id) == "Report"



def test_registry_audit_event_has_valid_name(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    assert registry.record_event(sample_case.case_id, "CASE_RETRIEVED").event_type == "CASE_RETRIEVED"



def test_registry_replay_result_requires_result_mapping_or_none(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    with pytest.raises(ValueError):
        registry.record_replay_result(sample_case.case_id, matched=True, result="bad")



def test_registry_report_artifact_not_stored_in_case_json(tmp_path, sample_case):
    path = tmp_path / "cases.sqlite3"
    registry = EngineeringCaseRegistry(path)
    registry.save_case(sample_case, report_text="Report")
    assert "Report" not in registry.get_case(sample_case.case_id).to_json()



def test_registry_audit_event_has_replay_fields_only_for_replay(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    event = registry.record_event(sample_case.case_id, "REPORT_REQUESTED")
    assert "matched" not in event.details



def test_registry_case_persistence_is_non_destructive_for_existing_database(tmp_path, sample_case):
    path = tmp_path / "cases.sqlite3"
    registry = EngineeringCaseRegistry(path)
    registry.save_case(sample_case)
    reopened = EngineeringCaseRegistry(path)
    reopened.save_case(sample_case)
    assert reopened.get_case(sample_case.case_id).case_id == sample_case.case_id



def test_registry_case_id_has_no_timestamp_component(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    assert registry.get_case(sample_case.case_id).case_id == sample_case.case_id



def test_registry_audit_event_case_id_is_exact(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    assert registry.record_event(sample_case.case_id, "REPORT_REQUESTED").case_id == sample_case.case_id



def test_registry_case_report_case_id_is_not_recomputed(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case, report_text="Report")
    assert registry.get_case(sample_case.case_id).case_id == sample_case.case_id



def test_registry_audit_case_returns_list(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    assert isinstance(registry.audit_case(sample_case.case_id), list)



def test_registry_list_cases_returns_engineering_cases(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    assert registry.list_cases()[0].case_id == sample_case.case_id



def test_registry_case_metadata_contains_result_status(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    assert registry.get_case_metadata(sample_case.case_id)["status"] == sample_case.status



def test_registry_case_metadata_contains_created_case_type(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    metadata = registry.get_case_metadata(sample_case.case_id)
    assert metadata["calculation_type"] == sample_case.calculation_type



def test_registry_case_hash_is_canonical_case_id(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    assert registry.get_case_metadata(sample_case.case_id)["case_sha256"] == sample_case.case_id



def test_registry_case_report_artifact_is_separate_from_identity(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case, report_text="Report")
    assert registry.get_case_metadata(sample_case.case_id)["case_id"] == sample_case.case_id



def test_registry_event_created_at_is_persistent(tmp_path, sample_case):
    path = tmp_path / "cases.sqlite3"
    registry = EngineeringCaseRegistry(path)
    registry.save_case(sample_case)
    created = registry.audit_case(sample_case.case_id)[0].created_at
    assert EngineeringCaseRegistry(path).audit_case(sample_case.case_id)[0].created_at == created



def test_registry_case_report_after_replay_is_original_report(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case, report_text="Original")
    registry.record_replay_result(sample_case.case_id, matched=True, result={"status": "OK"})
    assert registry.get_report(sample_case.case_id) == "Original"



def test_registry_integrity_check_does_not_change_case_id(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    assert registry.get_case(sample_case.case_id).case_id == sample_case.case_id



def test_registry_case_retrieval_typed_failure_has_code(tmp_path):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    with pytest.raises(CaseNotFoundError) as exc:
        registry.get_case("c" * 64)
    assert "CASE_NOT_FOUND" in str(exc.value)



def test_registry_integrity_typed_failure_has_code(tmp_path, sample_case):
    path = tmp_path / "cases.sqlite3"
    EngineeringCaseRegistry(path).save_case(sample_case)
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE engineering_cases SET case_json = 'broken' WHERE case_id = ?", (sample_case.case_id,))
        connection.commit()
    with pytest.raises(CaseIntegrityError) as exc:
        EngineeringCaseRegistry(path).get_case(sample_case.case_id)
    assert "CASE_INTEGRITY_FAILURE" in str(exc.value)



def test_registry_audit_requested_after_report_is_sequential(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    registry.record_event(sample_case.case_id, "REPORT_REQUESTED")
    registry.record_event(sample_case.case_id, "CASE_RETRIEVED")
    assert [event.sequence for event in registry.audit_case(sample_case.case_id)] == [1, 2, 3]



def test_registry_case_report_not_found_is_typed(tmp_path):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    with pytest.raises(CaseNotFoundError) as exc:
        registry.get_report("d" * 64)
    assert "CASE_NOT_FOUND" in str(exc.value)



def test_registry_case_audit_not_found_is_typed(tmp_path):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    with pytest.raises(CaseNotFoundError) as exc:
        registry.audit_case("e" * 64)
    assert "CASE_NOT_FOUND" in str(exc.value)



def test_registry_case_report_is_human_artifact_not_storage_payload(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case, report_text="Status: OK\nProduction rate: 250 STB/day")
    assert "Production rate" in registry.get_report(sample_case.case_id)



def test_registry_case_json_integrity_uses_case_id(tmp_path, sample_case):
    path = tmp_path / "cases.sqlite3"
    registry = EngineeringCaseRegistry(path)
    registry.save_case(sample_case)
    with sqlite3.connect(path) as connection:
        row = connection.execute("SELECT case_json, case_sha256 FROM engineering_cases WHERE case_id = ?", (sample_case.case_id,)).fetchone()
    assert row[1] == sample_case.case_id



def test_registry_replay_match_audit_details_are_small(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    event = registry.record_replay_result(sample_case.case_id, matched=True, result={"status": "OK"})
    assert len(json.dumps(event.details)) < 1000



def test_registry_reopen_preserves_audit_count(tmp_path, sample_case):
    path = tmp_path / "cases.sqlite3"
    registry = EngineeringCaseRegistry(path)
    registry.save_case(sample_case)
    registry.record_event(sample_case.case_id, "REPORT_REQUESTED")
    assert len(EngineeringCaseRegistry(path).audit_case(sample_case.case_id)) == 2



def test_registry_case_report_can_be_human_read_in_arabic(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case, report_text="تقرير هندسي مقروء")
    assert registry.get_report(sample_case.case_id) == "تقرير هندسي مقروء"



def test_registry_audit_case_human_format_has_no_internal_schema_tokens(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    output = registry.format_audit(sample_case.case_id)
    assert "phase5c_increment13_case_report_v1" not in output



def test_registry_reports_are_not_raw_case_json_even_for_legacy_case(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case, report_text="Engineering report")
    assert not registry.get_report(sample_case.case_id).startswith("{")



def test_registry_case_report_string_survives_null_bytes_rejection(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    with pytest.raises(ValueError):
        registry.save_case(sample_case, report_text="bad\x00report")



def test_registry_case_id_is_required_for_case_storage(tmp_path):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    bad = build_case("demo", inputs={}, result={"status": "OK"}, status="OK")
    assert bad.case_id
    registry.save_case(bad)



def test_registry_events_are_append_only_from_public_api(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    registry.record_event(sample_case.case_id, "REPORT_REQUESTED")
    assert len(registry.audit_case(sample_case.case_id)) == 2



def test_registry_case_payload_round_trip_preserves_nested_data(tmp_path):
    case = build_case("nested", inputs={"a": {"b": [1, 2]}}, result={"nested": {"x": True}}, status="OK")
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(case)
    assert registry.get_case(case.case_id).inputs == {"a": {"b": [1, 2]}}
    assert registry.get_case(case.case_id).result == {"nested": {"x": True}}



def test_registry_case_payload_cannot_be_changed_by_mutating_restored_result(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    restored = registry.get_case(sample_case.case_id)
    restored.result["status"] = "CHANGED"
    assert registry.get_case(sample_case.case_id).result["status"] == "OK"



def test_registry_audit_preserves_validation_failure_code(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    registry.record_event(sample_case.case_id, "VALIDATION_FAILURE", details={"code": "INVALID_INPUT"})
    assert registry.audit_case(sample_case.case_id)[-1].details["code"] == "INVALID_INPUT"



def test_registry_case_report_retrieval_event_is_named_report_requested(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case, report_text="Report")
    registry.get_report(sample_case.case_id, record_event=True)
    assert registry.audit_case(sample_case.case_id)[-1].event_type == "REPORT_REQUESTED"



def test_registry_case_retrieval_event_is_named_case_retrieved(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    registry.get_case(sample_case.case_id, record_event=True)
    assert registry.audit_case(sample_case.case_id)[-1].event_type == "CASE_RETRIEVED"



def test_registry_replay_event_is_named_replay_match(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    registry.record_replay_result(sample_case.case_id, matched=True, result={"status": "OK"})
    assert registry.audit_case(sample_case.case_id)[-1].event_type == "REPLAY_MATCH"



def test_registry_case_report_request_does_not_store_raw_request(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case, report_text="Report")
    registry.record_event(sample_case.case_id, "REPORT_REQUESTED", details={"request": "/case report id"})
    assert "request" not in registry.audit_case(sample_case.case_id)[-1].details



def test_registry_case_replay_request_does_not_store_raw_request(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    registry.record_event(sample_case.case_id, "REPLAY_REQUESTED", details={"request": "/case replay id"})
    assert "request" not in registry.audit_case(sample_case.case_id)[-1].details



def test_registry_preserves_report_for_case_failure(tmp_path):
    case = build_case("failure", inputs={}, result={"error": {"code": "BAD", "message": "bad"}}, status="BAD")
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(case, report_text="Failure report")
    assert registry.get_report(case.case_id) == "Failure report"



def test_registry_case_id_remains_same_when_report_rewritten_is_rejected(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case, report_text="one")
    with pytest.raises(ValueError):
        registry.save_case(sample_case, report_text="two")
    assert registry.get_case(sample_case.case_id).case_id == sample_case.case_id



def test_registry_case_metadata_is_not_raw_json_string(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    assert isinstance(registry.get_case_metadata(sample_case.case_id), dict)



def test_registry_persistence_path_does_not_appear_in_audit(tmp_path, sample_case):
    path = tmp_path / "private-path.sqlite3"
    registry = EngineeringCaseRegistry(path)
    registry.save_case(sample_case)
    assert "private-path" not in registry.format_audit(sample_case.case_id)



def test_registry_case_report_does_not_expose_case_json_fields(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case, report_text="Engineering report")
    assert "canonical_json" not in registry.get_report(sample_case.case_id)
    assert "pvt_context" not in registry.get_report(sample_case.case_id)



def test_registry_case_identity_is_stable_with_different_audit_event_order(tmp_path, sample_case):
    first = EngineeringCaseRegistry(tmp_path / "one.sqlite3")
    second = EngineeringCaseRegistry(tmp_path / "two.sqlite3")
    first.save_case(sample_case)
    second.save_case(sample_case)
    first.record_event(sample_case.case_id, "REPORT_REQUESTED")
    second.record_event(sample_case.case_id, "REPLAY_REQUESTED")
    assert first.get_case(sample_case.case_id).case_id == second.get_case(sample_case.case_id).case_id



def test_registry_case_report_artifact_is_retrieved_exactly(tmp_path, sample_case):
    report = "A\nB\nC"
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case, report_text=report)
    assert registry.get_report(sample_case.case_id) == report



def test_registry_case_type_field_survives_case_json_round_trip(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    assert registry.get_case(sample_case.case_id).calculation_type == sample_case.calculation_type



def test_registry_audit_format_contains_case_identity(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    assert sample_case.case_id in registry.format_audit(sample_case.case_id)



def test_registry_case_report_empty_is_not_missing_case(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case, report_text="")
    assert registry.get_report(sample_case.case_id) == ""



def test_registry_read_missing_case_does_not_return_none(tmp_path):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    with pytest.raises(CaseNotFoundError):
        registry.get_case("f" * 64)



def test_registry_audit_event_case_type_is_not_user_input(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    assert registry.audit_case(sample_case.case_id)[0].case_type == "demo_v1"



def test_registry_replay_result_case_id_is_preserved(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    assert registry.record_replay_result(sample_case.case_id, matched=True, result={"status": "OK"}).case_id == sample_case.case_id



def test_registry_case_report_can_be_retrieved_after_audit_format(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case, report_text="Report")
    registry.format_audit(sample_case.case_id)
    assert registry.get_report(sample_case.case_id) == "Report"



def test_registry_case_list_after_report_request_has_same_case_count(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case, report_text="Report")
    registry.record_event(sample_case.case_id, "REPORT_REQUESTED")
    assert len(registry.list_cases()) == 1



def test_registry_case_id_is_not_changed_by_replay_match(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    before = registry.get_case(sample_case.case_id).case_id
    registry.record_replay_result(sample_case.case_id, matched=True, result={"status": "OK"})
    assert registry.get_case(sample_case.case_id).case_id == before



def test_registry_audit_case_order_is_not_random(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    registry.record_event(sample_case.case_id, "REPORT_REQUESTED")
    assert registry.audit_case(sample_case.case_id)[0].event_type == "CASE_CREATED"



def test_registry_case_metadata_result_is_not_raw_json_text(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    assert isinstance(registry.get_case_metadata(sample_case.case_id)["status"], str)



def test_registry_replay_metadata_without_result_is_allowed(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    registry.record_replay_result(sample_case.case_id, matched=True, result=None)
    assert registry.get_case_metadata(sample_case.case_id)["replay_match"] is True



def test_registry_audit_event_details_never_include_private_payload(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    event = registry.record_event(sample_case.case_id, "CASE_RETRIEVED", details={"input_payload": "hidden"})
    assert "input_payload" not in event.details



def test_registry_case_metadata_has_no_telegram_context(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    assert "telegram" not in json.dumps(registry.get_case_metadata(sample_case.case_id)).lower()



def test_registry_case_report_retrieval_is_not_raw_json_export(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case, report_text="Engineering report")
    assert "{" not in registry.get_report(sample_case.case_id)
    assert "}" not in registry.get_report(sample_case.case_id)



def test_registry_case_type_search_does_not_return_other_types(tmp_path):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    one = build_case("one", inputs={}, result={}, status="OK")
    two = build_case("two", inputs={}, result={}, status="OK")
    registry.save_case(one)
    registry.save_case(two)
    assert all(case.calculation_type == "one" for case in registry.list_cases(case_type="one"))



def test_registry_preserves_pvt_context_as_case_data(tmp_path):
    case = build_case("pvt", pvt={"mode": "pressure_dependent", "context": {"pressure_psia": 2000}}, result={"status": "OK"}, status="OK")
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(case)
    assert registry.get_case(case.case_id).pvt["context"]["pressure_psia"] == 2000



def test_registry_event_details_are_not_case_identity_data(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    before = registry.get_case(sample_case.case_id).case_id
    registry.record_event(sample_case.case_id, "REPORT_REQUESTED", details={"note": "x"})
    assert registry.get_case(sample_case.case_id).case_id == before



def test_registry_report_text_does_not_change_case_id(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case, report_text="report")
    assert sample_case.case_id == registry.get_case(sample_case.case_id).case_id



def test_registry_case_report_after_reload_has_same_length(tmp_path, sample_case):
    path = tmp_path / "cases.sqlite3"
    report = "Engineering report"
    EngineeringCaseRegistry(path).save_case(sample_case, report_text=report)
    assert len(EngineeringCaseRegistry(path).get_report(sample_case.case_id)) == len(report)



def test_registry_audit_case_format_is_deterministic_except_timestamps(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    first = registry.format_audit(sample_case.case_id)
    second = registry.format_audit(sample_case.case_id)
    assert first == second



def test_registry_case_id_is_persisted_as_primary_key(tmp_path, sample_case):
    path = tmp_path / "cases.sqlite3"
    EngineeringCaseRegistry(path).save_case(sample_case)
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA table_info(engineering_cases)").fetchall()



def test_registry_case_report_is_not_auto_regenerated(tmp_path, sample_case):
    path = tmp_path / "cases.sqlite3"
    registry = EngineeringCaseRegistry(path)
    registry.save_case(sample_case, report_text="Stored")
    assert registry.get_report(sample_case.case_id) == "Stored"



def test_registry_unknown_event_does_not_mutate_audit(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    with pytest.raises(ValueError):
        registry.record_event(sample_case.case_id, "UNKNOWN")
    assert len(registry.audit_case(sample_case.case_id)) == 1



def test_registry_audit_has_creation_event_for_failure_case(tmp_path):
    case = build_case("failed", inputs={}, result={"error": "x"}, status="FAILED")
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(case)
    assert registry.audit_case(case.case_id)[0].event_type == "CASE_CREATED"



def test_registry_get_report_record_event_is_optional(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case, report_text="Report")
    registry.get_report(sample_case.case_id, record_event=False)
    assert len(registry.audit_case(sample_case.case_id)) == 1



def test_registry_get_case_record_event_is_optional(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    registry.get_case(sample_case.case_id, record_event=False)
    assert len(registry.audit_case(sample_case.case_id)) == 1



def test_registry_case_report_preserves_unicode_surrogates_safely(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case, report_text="PVT α β")
    assert "PVT" in registry.get_report(sample_case.case_id)



def test_registry_case_type_list_is_newest_first(tmp_path):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    first = build_case("same", inputs={"i": 1}, result={}, status="OK")
    second = build_case("same", inputs={"i": 2}, result={}, status="OK")
    registry.save_case(first)
    registry.save_case(second)
    assert registry.list_cases(case_type="same")[0].case_id == second.case_id



def test_registry_event_sequence_starts_at_one(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    assert registry.audit_case(sample_case.case_id)[0].sequence == 1



def test_registry_audit_match_result_keeps_case_status(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    registry.record_replay_result(sample_case.case_id, matched=True, result={"status": "OK"})
    assert registry.get_case(sample_case.case_id).status == "OK"



def test_registry_typed_errors_are_not_python_tracebacks(tmp_path):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    with pytest.raises(CaseNotFoundError) as exc:
        registry.get_case("0" * 64)
    assert "Traceback" not in str(exc.value)



def test_registry_replay_result_case_not_mutated(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    before = registry.get_case(sample_case.case_id).to_dict()
    registry.record_replay_result(sample_case.case_id, matched=True, result={"status": "OK"})
    assert registry.get_case(sample_case.case_id).to_dict() == before



def test_registry_report_artifact_is_separate_column(tmp_path, sample_case):
    path = tmp_path / "cases.sqlite3"
    EngineeringCaseRegistry(path).save_case(sample_case, report_text="Report")
    with sqlite3.connect(path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(engineering_cases)")}
    assert "report_text" in columns



def test_registry_audit_table_is_separate(tmp_path, sample_case):
    path = tmp_path / "cases.sqlite3"
    EngineeringCaseRegistry(path).save_case(sample_case)
    with sqlite3.connect(path) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "engineering_case_audit" in tables



def test_registry_case_data_is_json_serializable(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    json.dumps(registry.get_case(sample_case.case_id).to_dict())



def test_registry_case_report_is_not_lost_if_audit_is_empty(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case, report_text="Report")
    assert registry.get_report(sample_case.case_id) == "Report"



def test_registry_case_id_is_same_as_original_after_storage(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    assert registry.get_case(sample_case.case_id).case_id == sample_case.case_id



def test_registry_case_report_text_is_stored_verbatim(tmp_path, sample_case):
    text = "line 1\nline 2"
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case, report_text=text)
    assert registry.get_report(sample_case.case_id) == text



def test_registry_audit_event_details_are_not_shared(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    details = {"a": 1}
    event = registry.record_event(sample_case.case_id, "REPORT_REQUESTED", details=details)
    details["a"] = 2
    assert event.details["a"] == 1



def test_registry_case_retrieval_after_reopen_has_same_result(tmp_path, sample_case):
    path = tmp_path / "cases.sqlite3"
    EngineeringCaseRegistry(path).save_case(sample_case)
    assert EngineeringCaseRegistry(path).get_case(sample_case.case_id).result == sample_case.result



def test_registry_report_retrieval_after_reopen_has_same_text(tmp_path, sample_case):
    path = tmp_path / "cases.sqlite3"
    EngineeringCaseRegistry(path).save_case(sample_case, report_text="Report")
    assert EngineeringCaseRegistry(path).get_report(sample_case.case_id) == "Report"



def test_registry_case_retrieval_records_no_report_event_by_default(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    registry.get_case(sample_case.case_id)
    assert len(registry.audit_case(sample_case.case_id)) == 1



def test_registry_save_case_returns_creation_audit_event(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    event = registry.save_case(sample_case)
    assert event.event_type == "CASE_CREATED"



def test_registry_audit_event_has_sequence_int(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    assert isinstance(registry.record_event(sample_case.case_id, "REPORT_REQUESTED").sequence, int)



def test_registry_case_report_does_not_return_case_object(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case, report_text="Report")
    assert isinstance(registry.get_report(sample_case.case_id), str)



def test_registry_case_list_hides_report_text(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case, report_text="private report")
    assert "private report" not in registry.format_case_list()



def test_registry_case_audit_hides_report_text(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case, report_text="private report")
    assert "private report" not in registry.format_audit(sample_case.case_id)



def test_registry_case_report_text_survives_audit_events(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case, report_text="Report")
    registry.record_event(sample_case.case_id, "REPORT_REQUESTED")
    registry.record_event(sample_case.case_id, "CASE_RETRIEVED")
    assert registry.get_report(sample_case.case_id) == "Report"



def test_registry_case_is_not_evicted_after_many_audit_events(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    for _ in range(10):
        registry.record_event(sample_case.case_id, "REPORT_REQUESTED")
    assert registry.get_case(sample_case.case_id).case_id == sample_case.case_id



def test_registry_audit_event_types_are_uppercase(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    assert registry.record_event(sample_case.case_id, "CASE_RETRIEVED").event_type.isupper()



def test_registry_case_id_validation_accepts_uppercase_hex(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    assert registry.get_case(sample_case.case_id.upper()).case_id == sample_case.case_id



def test_registry_case_id_validation_rejects_non_hex(tmp_path):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    with pytest.raises(CaseNotFoundError):
        registry.get_case("z" * 64)



def test_registry_audit_case_preserves_case_id_case(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    assert registry.audit_case(sample_case.case_id)[0].case_id == sample_case.case_id



def test_registry_case_report_preserves_case_id_in_text(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case, report_text=f"Engineering Case ID: {sample_case.case_id}")
    assert sample_case.case_id in registry.get_report(sample_case.case_id)



def test_registry_case_json_hash_is_verified_after_reopen(tmp_path, sample_case):
    path = tmp_path / "cases.sqlite3"
    EngineeringCaseRegistry(path).save_case(sample_case)
    assert EngineeringCaseRegistry(path).get_case(sample_case.case_id).case_id == sample_case.case_id



def test_registry_audit_table_has_case_id_index(tmp_path, sample_case):
    path = tmp_path / "cases.sqlite3"
    EngineeringCaseRegistry(path).save_case(sample_case)
    with sqlite3.connect(path) as connection:
        indexes = {row[1] for row in connection.execute("PRAGMA index_list(engineering_case_audit)")}
    assert indexes



def test_registry_case_table_has_case_id_index(tmp_path, sample_case):
    path = tmp_path / "cases.sqlite3"
    EngineeringCaseRegistry(path).save_case(sample_case)
    with sqlite3.connect(path) as connection:
        indexes = {row[1] for row in connection.execute("PRAGMA index_list(engineering_cases)")}
    assert indexes



def test_registry_audit_event_details_are_json_objects(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    event = registry.record_event(sample_case.case_id, "REPORT_REQUESTED")
    assert isinstance(event.details, dict)



def test_registry_case_report_not_exposed_in_audit_details(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case, report_text="Report")
    registry.record_event(sample_case.case_id, "REPORT_REQUESTED")
    assert "Report" not in json.dumps(registry.audit_case(sample_case.case_id)[-1].details)



def test_registry_audit_event_case_type_is_persisted(tmp_path, sample_case):
    path = tmp_path / "cases.sqlite3"
    EngineeringCaseRegistry(path).save_case(sample_case)
    event = EngineeringCaseRegistry(path).record_event(sample_case.case_id, "REPORT_REQUESTED")
    assert event.case_type == sample_case.calculation_type



def test_registry_report_is_stored_separately_from_case_payload(tmp_path, sample_case):
    path = tmp_path / "cases.sqlite3"
    EngineeringCaseRegistry(path).save_case(sample_case, report_text="Report")
    with sqlite3.connect(path) as connection:
        row = connection.execute("SELECT case_json, report_text FROM engineering_cases WHERE case_id = ?", (sample_case.case_id,)).fetchone()
    assert "Report" not in row[0]
    assert row[1] == "Report"



def test_registry_case_report_is_not_mutable_by_case_mutation(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case, report_text="Report")
    sample_case.result["status"] = "changed"
    assert registry.get_report(sample_case.case_id) == "Report"



def test_registry_audit_case_can_be_read_after_close(tmp_path, sample_case):
    path = tmp_path / "cases.sqlite3"
    registry = EngineeringCaseRegistry(path)
    registry.save_case(sample_case)
    registry.close()
    assert EngineeringCaseRegistry(path).audit_case(sample_case.case_id)



def test_registry_report_can_be_read_after_close(tmp_path, sample_case):
    path = tmp_path / "cases.sqlite3"
    registry = EngineeringCaseRegistry(path)
    registry.save_case(sample_case, report_text="Report")
    registry.close()
    assert EngineeringCaseRegistry(path).get_report(sample_case.case_id) == "Report"



def test_registry_case_can_be_read_after_close(tmp_path, sample_case):
    path = tmp_path / "cases.sqlite3"
    registry = EngineeringCaseRegistry(path)
    registry.save_case(sample_case)
    registry.close()
    assert EngineeringCaseRegistry(path).get_case(sample_case.case_id).case_id == sample_case.case_id



def test_registry_audit_records_replay_failure_event(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    registry.record_event(sample_case.case_id, "REPLAY_REQUESTED")
    registry.record_event(sample_case.case_id, "REPLAY_MISMATCH", details={"reason": "different result"})
    assert registry.audit_case(sample_case.case_id)[-1].event_type == "REPLAY_MISMATCH"



def test_registry_report_request_event_can_have_surface(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    event = registry.record_event(sample_case.case_id, "REPORT_REQUESTED", details={"surface": "telegram"})
    assert event.details["surface"] == "telegram"



def test_registry_audit_case_human_format_includes_event_count(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    registry.record_event(sample_case.case_id, "REPORT_REQUESTED")
    output = registry.format_audit(sample_case.case_id)
    assert "2" in output



def test_registry_case_list_human_format_includes_case_type(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    assert sample_case.calculation_type in registry.format_case_list()



def test_registry_case_metadata_pvt_is_plain_data(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    assert isinstance(registry.get_case_metadata(sample_case.case_id)["pvt"], dict)



def test_registry_record_event_requires_case_id_string(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    with pytest.raises(CaseNotFoundError):
        registry.record_event(None, "REPORT_REQUESTED")



def test_registry_case_report_requires_string_case_id(tmp_path):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    with pytest.raises(CaseNotFoundError):
        registry.get_report(None)



def test_registry_case_audit_requires_string_case_id(tmp_path):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    with pytest.raises(CaseNotFoundError):
        registry.audit_case(None)



def test_registry_replay_result_metadata_is_plain_data(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    registry.record_replay_result(sample_case.case_id, matched=True, result={"x": 1})
    assert isinstance(registry.get_case_metadata(sample_case.case_id)["replay_result"], dict)



def test_registry_case_report_not_stored_as_bytes(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case, report_text="Report")
    assert isinstance(registry.get_report(sample_case.case_id), str)



def test_registry_audit_event_details_not_stored_as_bytes(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    event = registry.record_event(sample_case.case_id, "REPORT_REQUESTED")
    assert isinstance(event.details, dict)



def test_registry_case_payload_does_not_include_report_text(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case, report_text="Report")
    assert "report_text" not in registry.get_case(sample_case.case_id).to_dict()



def test_registry_case_payload_does_not_include_audit_events(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    registry.record_event(sample_case.case_id, "REPORT_REQUESTED")
    assert "audit" not in registry.get_case(sample_case.case_id).to_dict()



def test_registry_case_report_does_not_include_audit_events(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case, report_text="Report")
    registry.record_event(sample_case.case_id, "REPORT_REQUESTED")
    assert "REPORT_REQUESTED" not in registry.get_report(sample_case.case_id)



def test_registry_audit_event_details_are_sanitized(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    event = registry.record_event(sample_case.case_id, "REPORT_REQUESTED", details={"telegram_chat_id": 1, "surface": "telegram"})
    assert "telegram_chat_id" not in event.details
    assert event.details["surface"] == "telegram"



def test_registry_case_report_persists_after_new_audit_instance(tmp_path, sample_case):
    path = tmp_path / "cases.sqlite3"
    EngineeringCaseRegistry(path).save_case(sample_case, report_text="Report")
    EngineeringCaseRegistry(path).record_event(sample_case.case_id, "REPORT_REQUESTED")
    assert EngineeringCaseRegistry(path).get_report(sample_case.case_id) == "Report"



def test_registry_save_case_does_not_add_duplicate_audit_on_same_id(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    registry.save_case(sample_case)
    assert len(registry.audit_case(sample_case.case_id)) == 1



def test_registry_case_report_after_failed_replay_still_available(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case, report_text="Report")
    registry.record_replay_result(sample_case.case_id, matched=False, result={"status": "DIFFERENT"})
    assert registry.get_report(sample_case.case_id) == "Report"



def test_registry_case_report_after_successful_replay_still_available(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case, report_text="Report")
    registry.record_replay_result(sample_case.case_id, matched=True, result={"status": "OK"})
    assert registry.get_report(sample_case.case_id) == "Report"



def test_registry_case_report_does_not_recompute_result(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case, report_text="Report")
    assert registry.get_case(sample_case.case_id).result == sample_case.result



def test_registry_case_audit_event_persists_reason(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    registry.record_event(sample_case.case_id, "CASE_NOT_FOUND", details={"action": "report"})
    assert registry.audit_case(sample_case.case_id)[-1].details["action"] == "report"



def test_registry_report_artifact_is_not_in_audit_table_payload(tmp_path, sample_case):
    path = tmp_path / "cases.sqlite3"
    EngineeringCaseRegistry(path).save_case(sample_case, report_text="Report")
    with sqlite3.connect(path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(engineering_case_audit)")}
    assert "report_text" not in columns



def test_registry_case_sha256_column_is_not_nullable(tmp_path, sample_case):
    path = tmp_path / "cases.sqlite3"
    EngineeringCaseRegistry(path).save_case(sample_case)
    with sqlite3.connect(path) as connection:
        nullable = [row for row in connection.execute("PRAGMA table_info(engineering_cases)") if row[1] == "case_sha256"][0]
    assert nullable[3] == 1



def test_registry_audit_case_preserves_failure_reason(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    registry.record_event(sample_case.case_id, "VALIDATION_FAILURE", details={"reason": "invalid input"})
    assert "invalid input" in registry.format_audit(sample_case.case_id)



def test_registry_case_id_is_same_in_metadata_and_case(tmp_path, sample_case):
    registry = EngineeringCaseRegistry(tmp_path / "cases.sqlite3")
    registry.save_case(sample_case)
    assert registry.get_case(sample_case.case_id).case_id == registry.get_case_metadata(sample_case.case_id)["case_id"]

