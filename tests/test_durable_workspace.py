import json
import sqlite3
from pathlib import Path

import pytest

from handlers import text_handlers as th
from services.choke_engine import ChokeInput
from services.engineering_case_registry import CaseIntegrityError, EngineeringCaseRegistry
from services.scenario_comparison import (
    ScenarioSpec,
    comparison_replay_matches,
    evaluate_comparison,
    generate_comparison_report_v1,
    replay_comparison,
)


def choke_spec(label: str, choke_size: float, **request):
    inputs = ChokeInput(
        upstream_pressure_psia=1000.0,
        downstream_pressure_psia=200.0,
        choke_size_64th_in=float(choke_size),
        gor_scf_stb=1000.0,
        liquid_rate_bpd=1000.0,
    )
    return ScenarioSpec(
        label=label,
        calculation_type="choke",
        inputs=inputs,
        request={"calculation": "choke", "scenario": label, **request},
    )


def build_comparison(**request):
    return evaluate_comparison(
        [choke_spec("small", 16, **request), choke_spec("large", 32, **request)],
        request={"calculation": "choke", "scenarios": ["small", "large"], **request},
    )


def test_comparison_workspace_survives_close_reload_report_replay_and_match(tmp_path):
    path = tmp_path / "workspace.sqlite3"
    comparison = build_comparison()
    report = generate_comparison_report_v1(comparison)

    first = EngineeringCaseRegistry(path)
    first.save_comparison(comparison, report_text=report)
    comparison_id = comparison.comparison_id
    first.close()

    reloaded = EngineeringCaseRegistry(path)
    restored = reloaded.get_comparison(comparison_id)
    assert restored.to_json() == comparison.to_json()
    assert reloaded.get_comparison_report(comparison_id) == report

    replayed = replay_comparison(restored)
    assert replayed.comparison_id == comparison_id
    assert comparison_replay_matches(restored, replayed)
    reloaded.record_comparison_replay_result(
        comparison_id,
        matched=True,
        result={"comparison_id": replayed.comparison_id},
    )
    metadata = reloaded.get_comparison_metadata(comparison_id)
    assert metadata["persistent"] is True
    assert metadata["replay_match"] is True
    assert metadata["replay_count"] == 1
    assert metadata["schema_version"] == "scenario_comparison_v1"
    assert [event.event_type for event in reloaded.audit_comparison(comparison_id)] == [
        "COMPARISON_CREATED",
        "COMPARISON_REPLAY_MATCH",
    ]


def test_comparison_workspace_rejects_tampered_payload(tmp_path):
    path = tmp_path / "workspace.sqlite3"
    comparison = build_comparison()
    registry = EngineeringCaseRegistry(path)
    registry.save_comparison(comparison)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE engineering_comparisons SET comparison_json = ? WHERE comparison_id = ?",
            (json.dumps({"comparison_id": comparison.comparison_id}), comparison.comparison_id),
        )
        connection.commit()
    with pytest.raises(CaseIntegrityError, match="COMPARISON_INTEGRITY_FAILURE"):
        EngineeringCaseRegistry(path).get_comparison(comparison.comparison_id)


def test_comparison_workspace_redacts_secrets_and_telegram_metadata(tmp_path):
    path = tmp_path / "workspace.sqlite3"
    comparison = build_comparison(
        api_key="sk-live-secret",
        notes="Bearer ghp_comparison_secret",
        telegram_chat_id=123456,
    )
    registry = EngineeringCaseRegistry(path)
    registry.save_comparison(comparison, report_text=generate_comparison_report_v1(comparison))
    raw = path.read_bytes()
    assert b"sk-live-secret" not in raw
    assert b"ghp_comparison_secret" not in raw
    assert b"telegram_chat_id" not in raw
    restored = registry.get_comparison(comparison.comparison_id)
    assert "api_key" not in json.loads(restored.to_json()).get("request", {})


def test_registry_uses_railway_volume_mount_path_when_explicit_path_is_absent(tmp_path, monkeypatch):
    volume_path = tmp_path / "mounted-volume"
    monkeypatch.delenv("ENGINEERING_CASE_DB_PATH", raising=False)
    monkeypatch.setenv("RAILWAY_VOLUME_MOUNT_PATH", str(volume_path))
    registry = EngineeringCaseRegistry.from_environment()
    try:
        assert Path(registry.db_path) == volume_path / "engineering_cases.sqlite3"
    finally:
        registry.close()


def test_comparison_commands_reload_from_workspace_after_memory_is_cleared(tmp_path, monkeypatch):
    path = tmp_path / "workspace.sqlite3"
    persistent = EngineeringCaseRegistry(path)
    monkeypatch.setattr(th, "_CASE_REGISTRY", persistent)
    th._COMPARISONS.clear()

    text, png, error = th.handle_calc(
        {
            "text": (
                "/calc compare type=choke "
                "scenario=small:choke=16 scenario=large:choke=32 "
                "p_up=1000 p_down=200 gor=1000 q_liquid=1000"
            )
        },
        None,
    )
    assert png is None
    assert error is None
    comparison_id = text.split("Comparison ID: ", 1)[1].splitlines()[0].strip()

    th._COMPARISONS.clear()
    persistent.close()
    monkeypatch.setattr(th, "_CASE_REGISTRY", EngineeringCaseRegistry(path))

    report, _, report_error = th.handle_comparison_command(
        {"text": f"/comparison report {comparison_id}"}, None
    )
    replay, _, replay_error = th.handle_comparison_command(
        {"text": f"/comparison replay {comparison_id}"}, None
    )
    assert report_error is None
    assert replay_error is None
    assert "# Scenario Comparison Report V1" in report
    assert replay.startswith("Replay comparison: MATCH")
    metadata = th._CASE_REGISTRY.get_comparison_metadata(comparison_id)
    assert metadata["replay_match"] is True
    assert metadata["replay_result"]["comparison_id"] == comparison_id
    assert len(metadata["replay_result"]["scenarios"]) == 2
