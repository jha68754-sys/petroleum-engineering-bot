"""Focused acceptance contract for VLP Engineering Case/Report/Replay V1.

These tests define the orchestration contract before production wiring. The
released VLPEngine remains the only calculation source.
"""

import pytest

from handlers import text_handlers as th
from services.black_oil_pvt import BlackOilPvtProvider
from services.engineering_case import (
    build_vlp_case,
    replay_case,
    replay_matches,
)
from services.engineering_report import generate_report_v1
from services import vlp_engine


VLP_BASE = {
    "thp": 100.0,
    "tvd": 8000.0,
    "q": 3000.0,
    "q_w": 0.0,
    "gor": 1000.0,
    "bo": 1.4,
    "bw": 1.01,
    "z": 0.9,
    "gamma_g": 0.65,
    "gamma_w": 1.07,
    "mu_l": 1.0,
    "api": 35.0,
    "wc": 0.0,
    "id": 1.995,
    "rs": 600.0,
    "t_wh": 120.0,
    "geothermal": 1.5,
    "sigma": 30.0,
    "segments": 80,
    "vlp_model": "beggs_brill",
}

PVT_CONTEXT = {
    "pressure_psia": 1000.0,
    "temperature_f": 140.0,
    "oil_api": 35.0,
    "gas_specific_gravity": 0.75,
    "separator_pressure_psia": 100.0,
    "separator_temperature_f": 100.0,
    "bubble_point_psia": 2500.0,
    "solution_gor_scf_stb": 700.0,
}


def _legacy_result():
    return vlp_engine.traverse(
        VLP_BASE["thp"], VLP_BASE["tvd"], VLP_BASE["q"], VLP_BASE["q_w"],
        VLP_BASE["gor"], VLP_BASE["bo"], VLP_BASE["bw"], VLP_BASE["z"],
        VLP_BASE["gamma_g"], VLP_BASE["gamma_w"], VLP_BASE["mu_l"],
        VLP_BASE["api"], VLP_BASE["wc"], VLP_BASE["id"], VLP_BASE["rs"],
        VLP_BASE["t_wh"], VLP_BASE["geothermal"], sigma=VLP_BASE["sigma"],
        n_segments=VLP_BASE["segments"], vlp_model=VLP_BASE["vlp_model"],
    )


def _black_oil_result():
    return vlp_engine.traverse(
        VLP_BASE["thp"], VLP_BASE["tvd"], VLP_BASE["q"], VLP_BASE["q_w"],
        VLP_BASE["gor"], VLP_BASE["bo"], VLP_BASE["bw"], VLP_BASE["z"],
        VLP_BASE["gamma_g"], VLP_BASE["gamma_w"], VLP_BASE["mu_l"],
        VLP_BASE["api"], VLP_BASE["wc"], VLP_BASE["id"], VLP_BASE["rs"],
        VLP_BASE["t_wh"], VLP_BASE["geothermal"], sigma=VLP_BASE["sigma"],
        n_segments=VLP_BASE["segments"], vlp_model=VLP_BASE["vlp_model"],
        pvt_provider=BlackOilPvtProvider(), pvt_context=PVT_CONTEXT,
    )


def test_vlp_case_factory_is_deterministic_and_replayable():
    result = _legacy_result()
    first = build_vlp_case(
        VLP_BASE,
        result,
        request={"calculation": "vlp"},
    )
    second = build_vlp_case(
        dict(reversed(list(VLP_BASE.items()))),
        result,
        request={"calculation": "vlp"},
    )

    assert first.case_id == second.case_id
    assert len(first.case_id) == 64
    assert first.calculation_type == "vlp_v1"
    assert first.status == "CONVERGED"
    assert first.reproducibility["replayable"] is True
    assert first.result["pwf"] == pytest.approx(356.5, abs=2.0)
    assert replay_matches(first, replay_case(first))


def test_vlp_case_report_preserves_model_units_and_honesty():
    case = build_vlp_case(
        VLP_BASE,
        _legacy_result(),
        request={"calculation": "vlp"},
    )
    report = generate_report_v1(case)

    assert "# Engineering Case Report V1" in report
    assert "Vertical Lift Performance" in report
    assert "Outflow model" in report
    assert "Engineering status: calculation completed successfully." in report
    assert "The calculation did not produce a valid engineering operating result." not in report
    assert "Flowing bottomhole pressure" in report
    assert "psia" in report
    assert "psia" in report
    assert "not measured field data" in report
    assert "Traceback" not in report


def test_vlp_black_oil_case_preserves_provider_and_replays():
    case = build_vlp_case(
        VLP_BASE,
        _black_oil_result(),
        pvt_context=PVT_CONTEXT,
        pvt_mode="pressure_dependent",
        pvt_model="black_oil_v1",
        request={"calculation": "vlp"},
    )

    assert case.pvt["mode"] == "pressure_dependent"
    assert case.pvt["model"] == "black_oil_v1"
    assert case.pvt["provenance"]["provider"] == "BlackOilPvtProvider"
    report = generate_report_v1(case)
    assert "Pressure-dependent Black-Oil PVT" in report
    assert "BlackOilPvtProvider" not in report
    replayed = replay_case(case)
    assert replay_matches(case, replayed)
    assert replayed.pvt["mode"] == "pressure_dependent"
    assert replayed.pvt["model"] == "black_oil_v1"


def test_vlp_typed_failure_is_reported_without_traceback():
    failed = build_vlp_case(
        {"thp": -1.0, "tvd": 8000.0, "q": 3000.0},
        {"error": {"code": "PHYSICALLY_INVALID_STATE", "message": "thp must be positive."}},
        status="PHYSICALLY_INVALID_STATE",
        request={"calculation": "vlp"},
    )
    report = generate_report_v1(failed)

    assert failed.status == "PHYSICALLY_INVALID_STATE"
    assert "PHYSICALLY_INVALID_STATE" in report
    assert "thp must be positive." in report
    assert "did not produce a valid engineering operating result" in report
    assert "Traceback" not in report


def test_vlp_telegram_surface_is_opt_in_and_supports_case_report_replay():
    command = (
        "/calc vlp case=1 model=beggs_brill thp=100 tvd=8000 q=3000 "
        "id=1.995 gor=1000 api=35 gamma_g=0.65 mu_l=1 bo=1.4 rs=600 "
        "t_wh=120 geothermal=1.5"
    )
    text, png, error = th.handle_calc({"text": command}, None)

    assert png is None
    assert error is None
    assert "VLP Calculation Result" in text
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
    assert "Vertical Lift Performance" in report
    assert replay.startswith("Replay comparison: MATCH")


def test_vlp_hagedorn_brown_selector_is_preserved_in_case():
    inputs = dict(VLP_BASE, vlp_model="hagedorn_brown")
    result = vlp_engine.traverse(
        inputs["thp"], inputs["tvd"], inputs["q"], inputs["q_w"],
        inputs["gor"], inputs["bo"], inputs["bw"], inputs["z"],
        inputs["gamma_g"], inputs["gamma_w"], inputs["mu_l"], inputs["api"],
        inputs["wc"], inputs["id"], inputs["rs"], inputs["t_wh"],
        inputs["geothermal"], sigma=inputs["sigma"],
        n_segments=inputs["segments"], vlp_model="hagedorn_brown",
    )
    case = build_vlp_case(inputs, result, request={"calculation": "vlp"})

    assert case.selectors["vlp_model"] == "hagedorn_brown"
    assert case.model["engine"] == "Hagedorn-Brown (1965)"
    assert replay_matches(case, replay_case(case))
