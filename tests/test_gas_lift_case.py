"""Focused acceptance contract for Gas-Lift Engineering Case/Report/Replay V1.

The tests intentionally exercise only the orchestration boundary.  GasLiftEngine
remains the sole calculation source and is not modified by this feature.
"""

import pytest

from handlers import text_handlers as th
from services.black_oil_pvt import BlackOilPvtProvider
from services.engineering_case import (
    build_gas_lift_case,
    build_gas_lift_failure_case,
    replay_case,
    replay_matches,
)
from services.engineering_report import generate_report_v1
from services.gas_lift_engine import GasLiftEngine, GasLiftInput


GAS_LIFT_BASE = GasLiftInput(
    thp_psia=100.0,
    tvd_ft=8000.0,
    injection_pressure_psia=1200.0,
    gas_injection_rate_mscfd=1000.0,
    gas_specific_gravity=0.65,
    average_temperature_f=180.0,
    liquid_rate_stbd=3000.0,
    reservoir_pressure_psia=3000.0,
    productivity_index_stbd_psi=1.5,
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

LEGACY_COMMAND = (
    "/calc gas_lift case=1 thp=100 tvd=8000 p_inj=1200 q_gas=1000 "
    "gamma_g=0.65 t_avg=180 q_liquid=3000 pr=3000 j=1.5"
)

BLACK_OIL_COMMAND = (
    LEGACY_COMMAND + " pvt_mode=pressure_dependent pvt_model=black_oil_v1 "
    "pvt_pressure_psia=2000 pvt_temperature_f=180 pvt_oil_api=35 "
    "pvt_gas_specific_gravity=0.65 pvt_separator_pressure_psia=100 "
    "pvt_separator_temperature_f=60 pvt_bubble_point_psia=1800"
)


def _legacy_result():
    return GasLiftEngine().calculate(GAS_LIFT_BASE)


def _black_oil_result():
    return GasLiftEngine().calculate(
        GAS_LIFT_BASE,
        pvt_provider=BlackOilPvtProvider(),
        pvt_context=PVT_CONTEXT,
    )


def test_gas_lift_case_factory_is_deterministic_and_replayable():
    result = _legacy_result()
    first = build_gas_lift_case(
        GAS_LIFT_BASE,
        result,
        request={"calculation": "gas_lift"},
    )
    second = build_gas_lift_case(
        GasLiftInput(**dict(reversed(list(GAS_LIFT_BASE.__dict__.items())))),
        result,
        request={"calculation": "gas_lift"},
    )

    assert first.case_id == second.case_id
    assert len(first.case_id) == 64
    assert first.calculation_type == "gas_lift_v1"
    assert first.status == "OK"
    assert first.reproducibility["replayable"] is True
    assert first.result["bottomhole_pressure_with_lift_psia"] == pytest.approx(408.86, abs=0.01)
    assert first.result["predicted_oil_rate_stbd"] == pytest.approx(3886.71, abs=0.01)
    assert replay_matches(first, replay_case(first))


def test_gas_lift_case_report_preserves_model_units_and_honesty():
    case = build_gas_lift_case(
        GAS_LIFT_BASE,
        _legacy_result(),
        request={"calculation": "gas_lift"},
    )
    report = generate_report_v1(case)

    assert "# Engineering Case Report V1" in report
    assert "Continuous Gas-Lift Performance" in report
    assert "GasLiftEngine V1" in report
    assert "Bottomhole pressure with gas lift" in report
    assert "psia" in report
    assert "Engineering status: calculation completed successfully." in report
    assert "The calculation did not produce a valid engineering operating result." not in report
    assert "not measured field data" in report
    assert "Traceback" not in report


def test_gas_lift_black_oil_case_preserves_provider_context_and_replays():
    case = build_gas_lift_case(
        GAS_LIFT_BASE,
        _black_oil_result(),
        pvt_context=PVT_CONTEXT,
        pvt_mode="pressure_dependent",
        pvt_model="black_oil_v1",
        request={"calculation": "gas_lift"},
    )

    assert case.pvt["mode"] == "pressure_dependent"
    assert case.pvt["model"] == "black_oil_v1"
    assert case.pvt["context"] == PVT_CONTEXT
    assert case.pvt["provenance"]["provider"] == "BlackOilPvtProvider"
    report = generate_report_v1(case)
    assert "Pressure-dependent Black-Oil PVT" in report
    assert "BlackOilPvtProvider" not in report
    replayed = replay_case(case)
    assert replay_matches(case, replayed)
    assert replayed.pvt["mode"] == "pressure_dependent"
    assert replayed.pvt["model"] == "black_oil_v1"


def test_gas_lift_typed_failure_is_reported_without_traceback():
    failed = build_gas_lift_failure_case(
        GAS_LIFT_BASE,
        code="PHYSICALLY_INVALID_STATE",
        message="available injection pressure is below tubing pressure.",
        request={"calculation": "gas_lift"},
    )
    report = generate_report_v1(failed)

    assert failed.status == "PHYSICALLY_INVALID_STATE"
    assert "PHYSICALLY_INVALID_STATE" in report
    assert "available injection pressure" in report
    assert "did not produce a valid engineering operating result" in report
    assert "Traceback" not in report


def test_gas_lift_telegram_surface_supports_case_report_and_replay():
    text, png, error = th.handle_calc({"text": LEGACY_COMMAND}, None)

    assert png is None
    assert error is None
    assert "Gas-Lift Calculation Result" in text
    assert "Status: OK" in text
    assert "Engineering Case ID: " in text
    case_id = text.rsplit("Engineering Case ID: ", 1)[1].strip()

    report, _, report_error = th.handle_case_command(
        {"text": f"/case report {case_id}"}, None
    )
    replay, _, replay_error = th.handle_case_command(
        {"text": f"/case replay {case_id}"}, None
    )

    assert report_error is None
    assert replay_error is None
    assert "Continuous Gas-Lift Performance" in report
    assert replay.startswith("Replay comparison: MATCH")


def test_gas_lift_black_oil_telegram_case_preserves_selector_and_replay():
    text, png, error = th.handle_calc({"text": BLACK_OIL_COMMAND}, None)

    assert png is None
    assert error is None
    assert "Gas-Lift Calculation Result" in text
    assert "Engineering Case ID: " in text
    assert "PVT Provider: BlackOilPvtProvider" in text
    case_id = text.rsplit("Engineering Case ID: ", 1)[1].strip()

    report, _, report_error = th.handle_case_command(
        {"text": f"/case report {case_id}"}, None
    )
    replay, _, replay_error = th.handle_case_command(
        {"text": f"/case replay {case_id}"}, None
    )

    assert report_error is None
    assert replay_error is None
    assert "Pressure-dependent Black-Oil PVT" in report
    assert "evaluated pressure range" in report
    assert "BlackOilPvtProvider" not in report
    assert replay.startswith("Replay comparison: MATCH")


def test_gas_lift_case_flag_is_rejected_for_no_supported_mode():
    text, png, error = th.handle_calc(
        {"text": "/calc gas_lift case=1 thp=100 tvd=8000"}, None
    )
    assert png is None
    assert error is None
    assert text.startswith("Error: INSUFFICIENT_INPUT:")
    assert "Engineering Case ID:" not in text
