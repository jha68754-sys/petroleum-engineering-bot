"""Focused acceptance contract for Nodal Engineering Case/Report/Replay V1.

These tests intentionally define the new public contract before production code
is changed. The NodalEngine remains the single source of calculation truth.
"""

import pytest

from handlers import text_handlers as th
from services.black_oil_pvt import BlackOilPvtProvider
from services.engineering_case import (
    build_nodal_case,
    replay_case,
    replay_matches,
)
from services.engineering_report import generate_report_v1
from services.nodal_engine import NodalEngine


NODAL_BASE = {
    "ipr_model": "linear",
    "pr": 3000.0,
    "pb": None,
    "j": 1.5,
    "j_star": None,
    "qmax": None,
    "q_test": None,
    "pwf_test": None,
    "thp": 100.0,
    "tvd": 8000.0,
    "tubing_id_in": 1.995,
    "gor": 1000.0,
    "rs": 600.0,
    "api": 35.0,
    "gamma_g": 0.65,
    "mu_l": 1.0,
    "bo": 1.4,
    "t_wh": 120.0,
    "geothermal": 1.5,
    "wc": 0.0,
    "gamma_w": 1.07,
    "bw": 1.01,
    "z_factor": 0.9,
    "sigma": 30.0,
    "n_segments": 80,
    "vlp_model": "beggs_brill",
    "q_min": 0.0,
    "q_max": None,
    "n_points": 201,
}

PVT_CONTEXT = {
    "pressure_psia": 2000.0,
    "temperature_f": 180.0,
    "oil_api": 35.0,
    "gas_specific_gravity": 0.65,
    "separator_pressure_psia": 100.0,
    "separator_temperature_f": 60.0,
    "bubble_point_psia": 1800.0,
}


def _legacy_result():
    return NodalEngine().solve(**NODAL_BASE)


def _black_oil_result():
    return NodalEngine().solve(
        **NODAL_BASE,
        pvt_provider=BlackOilPvtProvider(),
        pvt_context=PVT_CONTEXT,
    )


def test_nodal_case_factory_is_deterministic_and_replayable():
    result = _legacy_result()
    first = build_nodal_case(
        NODAL_BASE,
        result,
        request={"calculation": "nodal"},
    )
    second = build_nodal_case(
        dict(reversed(list(NODAL_BASE.items()))),
        result,
        request={"calculation": "nodal"},
    )

    assert first.case_id == second.case_id
    assert len(first.case_id) == 64
    assert first.calculation_type == "nodal_v1"
    assert first.status == "UNIQUE_OPERATING_POINT"
    assert first.reproducibility["replayable"] is True
    # Legacy Nodal control is 3944.198913574 STB/day; the 3867.70
    # control belongs to the explicit pressure-dependent Black-Oil path.
    assert first.result["roots"][0]["q"] == pytest.approx(3944.198913574, abs=1.0e-6)
    assert replay_matches(first, replay_case(first))


def test_nodal_case_report_preserves_solver_contract_and_honesty():
    case = build_nodal_case(
        NODAL_BASE,
        _legacy_result(),
        request={"calculation": "nodal"},
    )
    report = generate_report_v1(case)

    assert "# Engineering Case Report V1" in report
    assert "nodal_v1" in report
    assert "beggs_brill" in report
    assert "UNIQUE_OPERATING_POINT" in report
    assert "not measured field data" in report
    assert "Traceback" not in report


def test_nodal_black_oil_case_preserves_explicit_provider_and_replays():
    result = _black_oil_result()
    case = build_nodal_case(
        NODAL_BASE,
        result,
        pvt_context=PVT_CONTEXT,
        pvt_mode="pressure_dependent",
        pvt_model="black_oil_v1",
        request={"calculation": "nodal"},
    )

    assert case.pvt["mode"] == "pressure_dependent"
    assert case.pvt["model"] == "black_oil_v1"
    assert case.pvt["provenance"]["provider"] == "BlackOilPvtProvider"
    assert "BlackOilPvtProvider" in generate_report_v1(case)
    replayed = replay_case(case)
    assert replay_matches(case, replayed)
    assert replayed.pvt["mode"] == "pressure_dependent"
    assert replayed.pvt["model"] == "black_oil_v1"


def test_nodal_typed_failure_is_reported_without_traceback():
    failed = build_nodal_case(
        {"ipr_model": "linear", "pr": -1.0},
        {"error": {"code": "PHYSICALLY_INVALID_STATE", "message": "pr must be positive."}},
        status="PHYSICALLY_INVALID_STATE",
        request={"calculation": "nodal"},
    )
    report = generate_report_v1(failed)

    assert failed.status == "PHYSICALLY_INVALID_STATE"
    assert "PHYSICALLY_INVALID_STATE" in report
    assert "pr must be positive." in report
    assert "did not produce a valid engineering operating result" in report
    assert "Traceback" not in report


def test_nodal_case_telegram_surface_is_opt_in_and_reports_case_id():
    command = (
        "/calc nodal case=1 model=linear pr=3000 j=1.5 "
        "thp=100 tvd=8000 id=1.995 gor=1000 rs=600 api=35 "
        "gamma_g=0.65 mu_l=1 bo=1.4 t_wh=120 geothermal=1.5"
    )
    text, png, error = th.handle_calc({"text": command}, None)

    assert png is None
    assert error is None
    assert "Status: UNIQUE_OPERATING_POINT" in text
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
    assert "nodal_v1" in report
    assert replay.startswith("Replay comparison: MATCH")
