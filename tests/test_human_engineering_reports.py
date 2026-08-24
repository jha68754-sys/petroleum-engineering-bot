"""User-facing engineering reports must be readable and free of raw JSON.

These tests deliberately assert presentation contracts only.  They do not
change or re-implement any petroleum calculation.
"""

from handlers import text_handlers as th
from services.engineering_report import generate_report_arabic_v1


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


def _case_id(text: str) -> str:
    marker = "Engineering Case ID: "
    assert marker in text
    return text.rsplit(marker, 1)[1].strip()


def _run(command: str):
    text, photo, error = th.handle_calc({"text": command}, None)
    assert photo is None
    assert error is None
    return text, _case_id(text)


def _assert_no_raw_json_or_internal_schema(report: str) -> None:
    forbidden = (
        "```json",
        '"variable"',
        '"objective"',
        '"pvt_context"',
        '"canonical_json"',
        '"engine_version"',
        '"schema"',
        "phase5c_increment13_case_report_v1",
    )
    for token in forbidden:
        assert token not in report
    assert "{" not in report
    assert "}" not in report


def test_sensitivity_report_is_plain_petroleum_engineering_prose():
    _, case_id = _run(
        "/calc sensitivity case=1 report=1 type=thp thp=100,200,300 "
        + BASE_VLP
    )
    report, _, error = th.handle_case_command(
        {"text": f"/case report {case_id}"}, None
    )

    assert error is None
    assert "Sensitivity Analysis" in report
    assert "THP" in report
    assert "Operating point" in report
    assert "Production rate" in report
    assert "calculated model result" in report
    _assert_no_raw_json_or_internal_schema(report)


def test_black_oil_report_uses_engineering_language_not_provider_internals():
    _, case_id = _run(
        "/calc sensitivity case=1 report=1 type=thp thp=100,200,300 "
        + BASE_VLP + " " + PVT_ARGS
    )
    report, _, error = th.handle_case_command(
        {"text": f"/case report {case_id}"}, None
    )

    assert error is None
    assert "Pressure-dependent Black-Oil PVT" in report
    assert "evaluated pressure range" in report
    assert "BlackOilPvtProvider" not in report
    _assert_no_raw_json_or_internal_schema(report)


def test_replay_response_contains_only_readable_report_after_match():
    _, case_id = _run(
        "/calc optimize case=1 report=1 type=thp thp=100,200,300 "
        "objective=max_oil_rate min_pwf=500 " + BASE_VLP
    )
    replay, _, error = th.handle_case_command(
        {"text": f"/case replay {case_id}"}, None
    )

    assert error is None
    assert replay.startswith("Replay comparison: MATCH")
    assert "The same engineering case was reproduced" in replay
    _assert_no_raw_json_or_internal_schema(replay)


def test_json_export_is_not_available_as_a_user_facing_case_command():
    _, case_id = _run(
        "/calc sensitivity case=1 type=thp thp=100,200 " + BASE_VLP
    )
    response, _, error = th.handle_case_command(
        {"text": f"/case json {case_id}"}, None
    )

    assert error is None
    assert "raw JSON" not in response
    assert "Use /case report" in response
    assert "{" not in response
    assert "}" not in response


def test_report_uses_engineering_labels_for_temperature_and_geothermal_aliases():
    _, case_id = _run(
        "/calc sensitivity case=1 report=1 type=thp thp=100,200 " + BASE_VLP
    )
    report, _, error = th.handle_case_command(
        {"text": f"/case report {case_id}"}, None
    )

    assert error is None
    assert "Wellhead temperature: 120 degF" in report
    assert "Geothermal gradient: 1.5 degF/100ft" in report
    assert "T wh f" not in report
    assert "Geothermal f 100ft" not in report


def test_arabic_case_report_uses_verified_petroleum_labels_and_units():
    _, case_id = _run(
        "/calc sensitivity case=1 report=1 type=thp thp=100,200 " + BASE_VLP
    )
    case = th._CASE_REGISTRY.get_case(case_id)
    report = generate_report_arabic_v1(case)

    assert "تقرير الحالة الهندسية V1" in report
    assert "درجة حرارة رأس البئر: 120 degF" in report
    assert "التدرج الحراري الأرضي: 1.5 degF/100ft" in report
    assert "المتبقي الضغطي للحل" in report or "المتبقي الضغطي" in report
    assert "T wh f" not in report
    assert "Geothermal f 100ft" not in report
    assert "{\"" not in report
