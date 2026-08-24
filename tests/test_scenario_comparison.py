import json

import pytest

from handlers import text_handlers as th
from services.black_oil_pvt import BlackOilPvtProvider
from services.choke_engine import ChokeInput
from services.scenario_comparison import (
    ComparisonError,
    ScenarioSpec,
    build_system_input,
    comparison_replay_matches,
    evaluate_comparison,
    replay_comparison,
    format_comparison_arabic,
)


PVT_CONTEXT = {
    "pressure_psia": 1000.0,
    "temperature_f": 180.0,
    "oil_api": 35.0,
    "gas_specific_gravity": 0.65,
    "separator_pressure_psia": 100.0,
    "separator_temperature_f": 60.0,
    "bubble_point_psia": 1800.0,
}


def choke_spec(label, choke_size, **kwargs):
    inputs = ChokeInput(
        upstream_pressure_psia=1000.0,
        downstream_pressure_psia=200.0,
        choke_size_64th_in=float(choke_size),
        gor_scf_stb=1000.0,
        liquid_rate_bpd=1000.0,
        **kwargs,
    )
    return ScenarioSpec(
        label=label,
        calculation_type="choke",
        inputs=inputs,
        request={"calculation": "choke", "scenario": label},
    )


def test_comparison_identity_is_deterministic_and_preserves_order():
    first = evaluate_comparison([
        choke_spec("small", 16),
        choke_spec("large", 32),
    ])
    second = evaluate_comparison([
        choke_spec("small", 16),
        choke_spec("large", 32),
    ])

    assert first.comparison_id == second.comparison_id
    assert [item.label for item in first.scenarios] == ["small", "large"]
    assert first.scenarios[0].case.result["calculated_rate_bpd"] == pytest.approx(427.43097667587574)
    assert first.scenarios[1].case.result["calculated_rate_bpd"] == pytest.approx(1584.2097610800322)
    assert len(first.comparison_id) == 64


def test_comparison_replay_is_deterministic_for_legacy_choke_scenarios():
    comparison = evaluate_comparison([
        choke_spec("small", 16),
        choke_spec("large", 32),
    ])
    replayed = replay_comparison(comparison)

    assert comparison_replay_matches(comparison, replayed)
    assert replayed.comparison_id == comparison.comparison_id
    assert all(item.case.reproducibility["replayable"] for item in replayed.scenarios)


def test_one_invalid_scenario_is_typed_without_hiding_valid_scenarios():
    comparison = evaluate_comparison([
        choke_spec("valid", 16),
        choke_spec("invalid", -1),
    ])

    assert comparison.scenarios[0].case.status == "OK"
    assert comparison.scenarios[1].case.status == "PHYSICALLY_INVALID_STATE"
    assert comparison.scenarios[1].case.result["error"]["code"] == "PHYSICALLY_INVALID_STATE"
    assert "Traceback" not in comparison.to_json()


def test_comparison_rejects_duplicate_labels_and_too_few_scenarios():
    with pytest.raises(ComparisonError, match="at least two"):
        evaluate_comparison([choke_spec("only", 16)])
    with pytest.raises(ComparisonError, match="unique"):
        evaluate_comparison([choke_spec("same", 16), choke_spec("same", 32)])


def test_black_oil_provenance_is_preserved_without_serializing_provider_objects():
    first = ScenarioSpec(
        label="black_oil",
        calculation_type="choke",
        inputs=choke_spec("unused", 16).inputs,
        request={"calculation": "choke", "scenario": "black_oil"},
        pvt_provider=BlackOilPvtProvider(),
        pvt_context=PVT_CONTEXT,
        pvt_mode="pressure_dependent",
        pvt_model="black_oil_v1",
    )
    comparison = evaluate_comparison([first, choke_spec("legacy", 16)])

    payload = json.loads(comparison.to_json())
    pvt = payload["scenarios"][0]["case"]["pvt"]
    assert pvt["mode"] == "pressure_dependent"
    assert pvt["model"] == "black_oil_v1"
    assert "BlackOilPvtProvider" in json.dumps(pvt)
    assert "OPENAI_API_KEY" not in comparison.to_json()


def test_telegram_compare_surface_supports_repeated_labeled_scenarios():
    text, png, caption = th.handle_calc({
        "text": (
            "/calc compare type=choke "
            "scenario=small:choke=16 scenario=large:choke=32 "
            "p_up=1000 p_down=200 gor=1000 q_liquid=1000"
        )
    }, None)

    assert png is None
    assert caption is None
    assert "Scenario Comparison" in text
    assert "small" in text and "large" in text
    assert "427.43" in text
    assert "Comparison ID:" in text


def test_arabic_comparison_renderer_uses_petroleum_terms_without_raw_json():
    comparison = evaluate_comparison([
        choke_spec("الصغير", 16),
        choke_spec("الكبير", 32),
    ])
    text = format_comparison_arabic(comparison)

    assert "مقارنة السيناريوهات V1" in text
    assert "معدل السائل المحسوب" in text
    assert "معرّف الحالة" in text
    assert "الأمانة الهندسية" in text
    assert "{" not in text and "}" not in text


def test_telegram_compare_rejects_unknown_override_as_typed_input_error():
    text, _, _ = th.handle_calc({
        "text": "/calc compare type=choke scenario=bad:made_up=1 scenario=ok:choke=16 p_up=1000 p_down=200 gor=1000"
    }, None)
    assert "INVALID_INPUT" in text or "unsupported" in text.lower()


SYSTEM_COMMON = {
    "pr": "3000",
    "tvd": "8000",
    "id": "1.995",
    "gor": "1000",
    "rs": "600",
    "api": "35",
    "gamma_g": "0.65",
    "mu_l": "1",
    "bo": "1.4",
    "t_wh": "120",
    "geothermal": "1.5",
    "choke": "16",
    "p_down": "200",
    "model": "linear",
    "j": "1.5",
    "q_min": "100",
    "n_points": "11",
}


def test_system_comparison_uses_released_integrated_engine():
    low = dict(SYSTEM_COMMON, thp="100", choke="16")
    high = dict(SYSTEM_COMMON, thp="100", choke="32")
    comparison = evaluate_comparison([
        ScenarioSpec("small_choke", "system", build_system_input(low), request={"scenario": "small_choke"}),
        ScenarioSpec("large_choke", "system", build_system_input(high), request={"scenario": "large_choke"}),
    ])

    assert [item.label for item in comparison.scenarios] == ["small_choke", "large_choke"]
    assert all(item.case.calculation_type == "integrated_system_v1" for item in comparison.scenarios)
    assert all(item.case.status == "OK" for item in comparison.scenarios)
    assert comparison.scenarios[0].case.result["operating_rate_bpd"] != comparison.scenarios[1].case.result["operating_rate_bpd"]
    assert comparison_replay_matches(comparison, replay_comparison(comparison))


def test_comparison_report_and_replay_commands_use_in_process_registry():
    text, _, _ = th.handle_calc({
        "text": (
            "/calc compare type=choke "
            "scenario=small:choke=16 scenario=large:choke=32 "
            "p_up=1000 p_down=200 gor=1000 q_liquid=1000"
        )
    }, None)
    comparison_id = text.split("Comparison ID: ", 1)[1].splitlines()[0].strip()

    report, _, _ = th.handle_comparison_command({"text": f"/comparison report {comparison_id}"}, None)
    replay, _, _ = th.handle_comparison_command({"text": f"/comparison replay {comparison_id}"}, None)
    payload, _, _ = th.handle_comparison_command({"text": f"/comparison json {comparison_id}"}, None)

    assert "# Scenario Comparison Report V1" in report
    assert "small" in report and "large" in report
    assert "Replay comparison: MATCH" in replay
    assert payload.startswith("{") and comparison_id in payload
