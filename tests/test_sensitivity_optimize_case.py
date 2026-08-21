"""Focused orchestration contracts for Sensitivity/Optimize Case V1.

The tests intentionally cover only case identity, serialization, report/replay,
PVT provenance, and Telegram routing.  ProductionOptimizer and all petroleum
engines remain the sole calculation sources.
"""

from handlers import text_handlers as th


BASE_VLP = (
    "model=linear pr=3000 j=1.5 thp=100 tvd=8000 id=1.995 gor=1000 rs=600 "
    "api=35 gamma_g=0.65 mu_l=1 bo=1.4 t_wh=120 geothermal=1.5"
)

PVT_ARGS = (
    "pvt_mode=pressure_dependent pvt_model=black_oil_v1 "
    "pvt_pressure_psia=2000 pvt_temperature_f=180 pvt_oil_api=35 "
    "pvt_gas_specific_gravity=0.65 pvt_separator_pressure_psia=100 "
    "pvt_separator_temperature_f=60 pvt_bubble_point_psia=1800"
)

SENS_LEGACY = (
    "/calc sensitivity case=1 report=1 type=thp thp=100,200,300 "
    + BASE_VLP
)
SENS_BLACK_OIL = SENS_LEGACY + " " + PVT_ARGS

OPT_LEGACY = (
    "/calc optimize case=1 report=1 type=thp thp=100,200,300 "
    "objective=max_oil_rate min_pwf=500 " + BASE_VLP
)
OPT_BLACK_OIL = OPT_LEGACY + " " + PVT_ARGS


def _case_id(text: str) -> str:
    marker = "Engineering Case ID: "
    assert marker in text
    return text.rsplit(marker, 1)[1].strip()


def _run_case(command: str):
    text, png, error = th.handle_calc({"text": command}, None)
    assert png is None
    assert error is None
    return text, _case_id(text)


def test_sensitivity_case_report_and_replay_are_deterministic():
    first_text, first_id = _run_case(SENS_LEGACY)
    second_text, second_id = _run_case(SENS_LEGACY)

    assert first_id == second_id
    assert "Sensitivity Analysis" in first_text
    assert "Engineering Case ID: " in first_text

    report, _, report_error = th.handle_case_command(
        {"text": f"/case report {first_id}"}, None
    )
    replay, _, replay_error = th.handle_case_command(
        {"text": f"/case replay {first_id}"}, None
    )

    assert report_error is None
    assert replay_error is None
    assert "Sensitivity Analysis" in report
    assert "Evaluated variable" in report
    assert "not measured field data" in report
    assert replay.startswith("Replay comparison: MATCH")


def test_sensitivity_black_oil_case_preserves_provider_and_replay():
    text, case_id = _run_case(SENS_BLACK_OIL)
    assert "Sensitivity Analysis" in text

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


def test_optimize_case_report_and_replay_are_deterministic():
    first_text, first_id = _run_case(OPT_LEGACY)
    second_text, second_id = _run_case(OPT_LEGACY)

    assert first_id == second_id
    assert "Production Optimization" in first_text
    assert "Optimization target" in first_text

    report, _, report_error = th.handle_case_command(
        {"text": f"/case report {first_id}"}, None
    )
    replay, _, replay_error = th.handle_case_command(
        {"text": f"/case replay {first_id}"}, None
    )

    assert report_error is None
    assert replay_error is None
    assert "Production Optimization" in report
    assert "Optimization target" in report
    assert replay.startswith("Replay comparison: MATCH")


def test_optimize_report_does_not_contradict_candidate_feasibility():
    text, case_id = _run_case(OPT_LEGACY)
    report, _, report_error = th.handle_case_command(
        {"text": f"/case report {case_id}"}, None
    )

    assert report_error is None
    candidate_block = report.split("Candidate evaluation", 1)[1].split(
        "Best feasible candidate", 1
    )[0]
    first_candidate = candidate_block.split("THP: 200", 1)[0]
    assert "Engineering classification: INFEASIBLE" in first_candidate
    assert "Engineering classification: FEASIBLE" not in first_candidate
    assert "Constraint note: Min pwf" in first_candidate


def test_optimize_black_oil_case_preserves_provider_and_replay():
    text, case_id = _run_case(OPT_BLACK_OIL)
    assert "Production Optimization" in text

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


def test_sensitivity_invalid_pressure_dependent_context_has_typed_case_failure():
    bad = (
        "/calc sensitivity case=1 type=thp thp=100,200 " + BASE_VLP +
        " pvt_mode=pressure_dependent pvt_model=black_oil_v1"
    )
    text, png, error = th.handle_calc({"text": bad}, None)

    assert png is None
    assert error is None
    assert "PHYSICALLY_INVALID_STATE" in text
    assert "Engineering Case ID: " in text
    case_id = _case_id(text)
    report, _, report_error = th.handle_case_command(
        {"text": f"/case report {case_id}"}, None
    )
    assert report_error is None
    assert "PHYSICALLY_INVALID_STATE" in report
    assert "Traceback" not in report


def test_optimize_invalid_pressure_dependent_context_has_typed_case_failure():
    bad = (
        "/calc optimize case=1 type=thp thp=100,200 "
        "objective=max_oil_rate " + BASE_VLP +
        " pvt_mode=pressure_dependent pvt_model=black_oil_v1"
    )
    text, png, error = th.handle_calc({"text": bad}, None)

    assert png is None
    assert error is None
    assert "PHYSICALLY_INVALID_STATE" in text
    assert "Engineering Case ID: " in text
    case_id = _case_id(text)
    replay, _, replay_error = th.handle_case_command(
        {"text": f"/case replay {case_id}"}, None
    )
    assert replay_error is None
    assert replay.startswith("Replay comparison: MATCH")
