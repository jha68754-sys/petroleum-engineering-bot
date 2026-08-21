from dataclasses import replace

import pytest

from handlers import text_handlers as th
from services.black_oil_pvt import BlackOilPvtProvider
from services.engineering_case import (
    EngineeringCase,
    build_case,
    build_choke_case,
    build_system_case,
    build_case_id,
    replay_case,
    replay_matches,
)
from services.engineering_report import generate_report_v1
from services.choke_engine import ChokeEngine, ChokeInput
from services.system_engine import IntegratedSystemEngine, SystemInput


BASE = SystemInput(
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
    j=1.5,
    q_min=100.0,
    n_points=11,
)

PVT_CONTEXT = {
    "pressure_psia": 2000.0,
    "temperature_f": 180.0,
    "oil_api": 35.0,
    "gas_specific_gravity": 0.65,
    "separator_pressure_psia": 100.0,
    "separator_temperature_f": 60.0,
    "bubble_point_psia": 1800.0,
}


@pytest.fixture(scope="module")
def legacy_result():
    return IntegratedSystemEngine().calculate(BASE)


@pytest.fixture(scope="module")
def legacy_case(legacy_result):
    return build_system_case(BASE, legacy_result, request={"calculation": "system"})


def test_a_identity_same_engineering_state_has_same_case_id():
    one = build_case("demo", inputs={"p": 1000.0}, units={"p": "psia"}, result={"q": 5})
    two = build_case("demo", inputs={"p": 1000}, units={"p": "psia"}, result={"q": 5.0})
    assert one.case_id == two.case_id
    assert len(one.case_id) == 64


def test_b_mutation_of_effective_input_changes_case_id():
    one = build_case("demo", inputs={"p": 1000.0}, units={"p": "psia"})
    two = build_case("demo", inputs={"p": 1001.0}, units={"p": "psia"})
    assert one.case_id != two.case_id


def test_c_dictionary_order_does_not_change_identity():
    first = build_case(
        "demo", inputs={"pressure": 1000, "rate": 5},
        selectors={"model": "linear", "pvt": "legacy"},
    )
    second = build_case(
        "demo", inputs={"rate": 5.0, "pressure": 1000.0},
        selectors={"pvt": "legacy", "model": "linear"},
    )
    assert first.case_id == second.case_id
    assert build_case_id({"b": 2, "a": 1}) == build_case_id({"a": 1, "b": 2})


def test_d_serialization_round_trip_preserves_case_fields(legacy_case):
    restored = EngineeringCase.from_json(legacy_case.to_json())
    assert restored.to_dict() == legacy_case.to_dict()
    assert restored.case_id == legacy_case.case_id
    assert restored.units["pressure"] == "psia"
    assert restored.reproducibility["hash"] == "sha256"


def test_e_replay_uses_the_same_released_system_engine(legacy_case):
    replayed = replay_case(legacy_case)
    assert replay_matches(legacy_case, replayed)
    assert replayed.status == legacy_case.status == "OK"
    assert replayed.result["operating_rate_bpd"] == legacy_case.result["operating_rate_bpd"]


def test_f_typed_failure_is_preserved_in_case_and_report():
    failed = build_case(
        "integrated_system_v1",
        inputs={"pr": -1.0},
        units={"pressure": "psia"},
        result={"error": {"code": "PHYSICALLY_INVALID_STATE", "message": "pr must be positive."}},
        status="PHYSICALLY_INVALID_STATE",
    )
    report = generate_report_v1(failed)
    assert failed.status == "PHYSICALLY_INVALID_STATE"
    assert "PHYSICALLY_INVALID_STATE" in report
    assert "pr must be positive." in report
    assert "did not produce a valid engineering operating result" in report
    assert "Traceback" not in report


def test_g_legacy_increment12_numerical_result_is_unchanged(legacy_result, legacy_case):
    assert legacy_result.status == "OK"
    assert legacy_result.operating_rate_bpd == pytest.approx(711.23046875, abs=1e-6)
    assert legacy_case.result["operating_rate_bpd"] == pytest.approx(711.23046875, abs=1e-6)


def test_h_black_oil_selector_and_provenance_are_serialized():
    result = IntegratedSystemEngine().calculate(
        BASE, pvt_provider=BlackOilPvtProvider(), pvt_context=PVT_CONTEXT
    )
    case = build_system_case(
        BASE,
        result,
        pvt_context=PVT_CONTEXT,
        pvt_mode="pressure_dependent",
        pvt_model="black_oil_v1",
    )
    assert case.pvt["mode"] == "pressure_dependent"
    assert case.pvt["model"] == "black_oil_v1"
    assert case.pvt["context"]["pressure_psia"] == 2000.0
    assert case.pvt["provenance"]["provider"] == "BlackOilPvtProvider"
    report = generate_report_v1(case)
    assert "Pressure-dependent Black-Oil PVT" in report
    assert "BlackOilPvtProvider" not in report


def test_i_system_handler_case_surface_preserves_existing_result():
    command = (
        "/calc system case=1 model=linear pr=3000 j=1.5 tvd=8000 id=1.995 "
        "gor=1000 rs=600 api=35 gamma_g=0.65 mu_l=1 bo=1.4 "
        "t_wh=120 geothermal=1.5 choke=16 p_down=200"
    )
    text, png, error = th.handle_calc({"text": command}, None)
    assert png is None
    assert error is None
    assert "Status: OK" in text
    assert "q_op = 711.22" in text
    assert "Engineering Case ID: " in text
    case_id = text.rsplit("Engineering Case ID: ", 1)[1].strip()
    report, _, report_error = th.handle_case_command({"text": f"/case report {case_id}"}, None)
    assert report_error is None
    assert "# Engineering Case Report V1" in report
    assert case_id in report


def test_j_secret_safety_excludes_sensitive_keys_and_redacts_secret_values():
    case = build_case(
        "demo",
        inputs={
            "pressure": 1000,
            "credential": "do-not-serialize",
            "telegram_chat_id": 12345,
            "notes": "Bearer abc123 ghp_abcdef sk-testsecret",
        },
        units={"pressure": "psia"},
    )
    output = case.to_json() + generate_report_v1(case)
    assert "do-not-serialize" not in output
    assert "12345" not in output
    assert "abc123" not in output
    assert "ghp_abcdef" not in output
    assert "sk-testsecret" not in output
    assert "[REDACTED]" in output


def test_k_units_are_explicit_and_not_silently_dropped(legacy_case):
    expected = {
        "pressure": "psia",
        "rate": "STB/day",
        "tubing_id": "in",
        "depth": "ft",
    }
    for key, value in expected.items():
        assert legacy_case.units[key] == value
    report = generate_report_v1(legacy_case)
    assert "Reservoir pressure: 3,000 psia" in report
    assert "Operating liquid rate" in report
    assert "STB/day" in report


def test_l_report_is_deterministic(legacy_case):
    assert generate_report_v1(legacy_case) == generate_report_v1(legacy_case)


def test_m_black_oil_handler_case_report_and_replay_surface():
    command = (
        "/calc system case=1 model=linear pr=3000 j=1.5 tvd=8000 id=1.995 "
        "gor=1000 rs=600 api=35 gamma_g=0.65 mu_l=1 bo=1.4 "
        "t_wh=120 geothermal=1.5 choke=16 p_down=200 "
        "pvt_mode=pressure_dependent pvt_model=black_oil_v1 "
        "pvt_pressure_psia=2000 pvt_temperature_f=180 pvt_oil_api=35 "
        "pvt_gas_specific_gravity=0.65 pvt_separator_pressure_psia=100 "
        "pvt_separator_temperature_f=60 pvt_bubble_point_psia=1800"
    )
    text, _, error = th.handle_calc({"text": command}, None)
    assert error is None
    assert "Status: OK" in text
    assert "PVT Provider: BlackOilPvtProvider" in text
    case_id = text.rsplit("Engineering Case ID: ", 1)[1].strip()
    report, _, report_error = th.handle_case_command({"text": f"/case report {case_id}"}, None)
    assert report_error is None
    assert "Pressure-dependent Black-Oil PVT" in report
    assert "evaluated pressure range" in report
    replay, _, replay_error = th.handle_case_command({"text": f"/case replay {case_id}"}, None)
    assert replay_error is None
    assert replay.startswith("Replay comparison: MATCH")
    assert "The same engineering case was reproduced" in replay
    assert "BlackOilPvtProvider" not in replay


CHOKE_BASE = ChokeInput(
    upstream_pressure_psia=1000.0,
    downstream_pressure_psia=200.0,
    choke_size_64th_in=16.0,
    gor_scf_stb=1000.0,
    liquid_rate_bpd=1000.0,
    oil_api=35.0,
    gas_specific_gravity=0.65,
    choke_model="gilbert_1954",
)

CHOKE_COMMAND = "/calc choke case=1 p_up=1000 p_down=200 choke=16 gor=1000 q_liquid=1000"
CHOKE_PVT_ARGS = (
    "pvt_mode=pressure_dependent pvt_model=black_oil_v1 "
    "pvt_pressure_psia=2000 pvt_temperature_f=180 pvt_oil_api=35 "
    "pvt_gas_specific_gravity=0.65 pvt_separator_pressure_psia=100 "
    "pvt_separator_temperature_f=60 pvt_bubble_point_psia=1800"
)


def test_n_choke_legacy_case_report_and_replay_surface():
    text, png, error = th.handle_calc({"text": CHOKE_COMMAND}, None)
    assert png is None
    assert error is None
    assert "Status: OK" in text
    assert "Calculated Rate: 427.43 bbl/day" in text
    case_id = text.rsplit("Engineering Case ID: ", 1)[1].strip()

    report, _, report_error = th.handle_case_command(
        {"text": f"/case report {case_id}"}, None
    )
    assert report_error is None
    assert "# Engineering Case Report V1" in report
    assert "Choke Performance" in report
    assert "Gilbert" in report
    assert "Upstream pressure" in report
    assert "**Case ID:**" in report

    replay, _, replay_error = th.handle_case_command(
        {"text": f"/case replay {case_id}"}, None
    )
    assert replay_error is None
    assert replay.startswith("Replay comparison: MATCH")


def test_o_choke_black_oil_case_preserves_provenance_and_replays():
    command = CHOKE_COMMAND + " " + CHOKE_PVT_ARGS
    text, png, error = th.handle_calc({"text": command}, None)
    assert png is None
    assert error is None
    assert "Status: OK" in text
    assert "PVT Mode: pressure_dependent" in text
    assert "PVT Model: black_oil_v1" in text
    assert "PVT Provider: BlackOilPvtProvider" in text
    case_id = text.rsplit("Engineering Case ID: ", 1)[1].strip()

    report, _, report_error = th.handle_case_command(
        {"text": f"/case report {case_id}"}, None
    )
    assert report_error is None
    assert "Pressure-dependent Black-Oil PVT" in report
    assert "evaluated pressure range" in report
    assert "BlackOilPvtProvider" not in report

    replay, _, replay_error = th.handle_case_command(
        {"text": f"/case replay {case_id}"}, None
    )
    assert replay_error is None
    assert replay.startswith("Replay comparison: MATCH")
    assert "The same engineering case was reproduced" in replay
    assert "BlackOilPvtProvider" not in replay


def test_p_choke_typed_failure_is_preserved_by_case_report():
    failed = build_choke_case(
        CHOKE_BASE,
        {"error": {"code": "PHYSICALLY_INVALID_STATE", "message": "invalid choke state."}},
        status="PHYSICALLY_INVALID_STATE",
    )
    report = generate_report_v1(failed)
    assert failed.status == "PHYSICALLY_INVALID_STATE"
    assert "PHYSICALLY_INVALID_STATE" in report
    assert "invalid choke state." in report
    assert "did not produce a valid engineering operating result" in report
    assert "Traceback" not in report


def test_q_choke_case_identity_is_stable_for_same_inputs():
    result = ChokeEngine().calculate(CHOKE_BASE)
    first = build_choke_case(CHOKE_BASE, result, request={"calculation": "choke"})
    second = build_choke_case(CHOKE_BASE, result, request={"calculation": "choke"})
    assert first.case_id == second.case_id
    assert first.inputs["upstream_pressure_psia"] == 1000.0
    assert first.units["rate"] == "bbl/day"
    assert first.reproducibility["engine_version"] == "V1"
    assert replay_matches(first, replay_case(first))
