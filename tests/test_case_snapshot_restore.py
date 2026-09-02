import main

from handlers import text_handlers as th
from services.case_snapshot import (
    CaseSnapshotError,
    build_case_snapshot,
    parse_case_snapshot,
)
from services.engineering_case import build_system_case
from services.system_engine import IntegratedSystemEngine, SystemInput



def _system_case():
    inputs = SystemInput(
        pr=3000.0,
        thp=100.0,
        tvd=8000.0,
        tubing_id_in=1.995,
        gor_scf_stb=1000.0,
        rs_scf_stb=600.0,
        api=35.0,
        gamma_g=0.65,
        mu_l_cp=1.0,
        bo_rb_stb=1.4,
        t_wh_f=120.0,
        geothermal_f_100ft=1.5,
        choke_size_64th_in=16.0,
        downstream_pressure_psia=200.0,
        ipr_model="linear",
        vlp_model="beggs_brill",
        j=1.5,
    )
    result = IntegratedSystemEngine().calculate(inputs)
    return build_system_case(
        inputs,
        result,
        request={"calculation": "system", "arguments": {"pr": "3000", "thp": "100"}},
    )



def test_snapshot_round_trip_restores_full_case_envelope():
    case = _system_case()
    snapshot = build_case_snapshot(case).decode("utf-8")

    restored = parse_case_snapshot(snapshot)

    assert restored.to_dict() == case.to_dict()
    assert "ENGINEERING_CASE_RESTORE_PAYLOAD_V1_BEGIN" in snapshot
    assert "bot1234567890" not in snapshot
    assert "telegram_chat_id" not in snapshot



def test_snapshot_tampering_fails_closed():
    case = _system_case()
    snapshot = build_case_snapshot(case).decode("utf-8")
    tampered = snapshot.replace(f"Case ID: `{case.case_id}`", "Case ID: `" + ("0" * 64) + "`", 1)

    try:
        parse_case_snapshot(tampered)
    except CaseSnapshotError as exc:
        assert exc.code == "SNAPSHOT_INTEGRITY_FAILURE"
    else:
        raise AssertionError("tampered Snapshot must be rejected")



def test_case_resume_restores_into_existing_registry_and_replays():
    case = _system_case()
    chat_id = 982001
    main.FILE_CONTEXT[chat_id] = build_case_snapshot(case).decode("utf-8")

    text, content, filename = th.handle_case_command(
        {"chat": {"id": chat_id}, "text": "/case resume"},
        None,
    )

    assert content is None
    assert filename is None
    assert "MATCH" in text
    assert th.load_engineering_session(chat_id).current_case_id == case.case_id



def test_natural_snapshot_resume_supports_explicit_thp_override():
    case = _system_case()
    chat_id = 982002
    main.FILE_CONTEXT[chat_id] = build_case_snapshot(case).decode("utf-8")

    answer = th.handle_snapshot_resume_message(
        {"chat": {"id": chat_id}, "text": "أكمل الحساب عند THP=200 psia"}
    )

    assert answer is not None
    assert "معرّف الحالة:" in answer
    assert th.load_engineering_session(chat_id).current_case_id != case.case_id



def test_legacy_snapshot_can_still_be_used_when_case_is_in_registry():
    case = _system_case()
    snapshot = build_case_snapshot(case).decode("utf-8")
    legacy = snapshot.split("<!-- ENGINEERING_CASE_RESTORE_PAYLOAD_V1_BEGIN", 1)[0]
    th._CASE_REGISTRY.save_case(case)
    chat_id = 982003
    main.FILE_CONTEXT[chat_id] = legacy

    text, content, filename = th.handle_case_command(
        {"chat": {"id": chat_id}, "text": "/case restore"},
        None,
    )

    assert "تمت استعادة الحالة" in text
    assert content is None
    assert filename is None
