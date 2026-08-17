import math

import pytest

from handlers import text_handlers as th
from services.choke_engine import ChokeEngine, ChokeError, ChokeInput


# Independent arithmetic only. This helper intentionally does not import or call
# ChokeEngine so benchmark expected values remain independent of production code.
ATM_PSIA = 14.7
COEFFICIENT = 435.0
GLR_EXPONENT = 0.546
CHOKE_EXPONENT = 1.89


def independent_rate(p_up_psia, gor_scf_stb, choke_64th_in):
    p_up_psig = p_up_psia - ATM_PSIA
    glr_mscf_per_bbl = gor_scf_stb / 1000.0
    return (
        p_up_psig * choke_64th_in ** CHOKE_EXPONENT
        / (COEFFICIENT * glr_mscf_per_bbl ** GLR_EXPONENT)
    )


def independent_pressure(q_bpd, gor_scf_stb, choke_64th_in):
    glr_mscf_per_bbl = gor_scf_stb / 1000.0
    return (
        ATM_PSIA
        + COEFFICIENT
        * glr_mscf_per_bbl ** GLR_EXPONENT
        * q_bpd
        / choke_64th_in ** CHOKE_EXPONENT
    )


def valid_input(**overrides):
    values = dict(
        upstream_pressure_psia=1000.0,
        downstream_pressure_psia=200.0,
        choke_size_64th_in=16.0,
        gor_scf_stb=1000.0,
        liquid_rate_bpd=None,
        oil_api=None,
        gas_specific_gravity=None,
        choke_model="gilbert_1954",
    )
    values.update(overrides)
    return ChokeInput(**values)


def test_a_nominal_valid_case_matches_independent_equation():
    result = ChokeEngine().calculate(valid_input())
    assert result.status == "OK"
    assert result.flow_regime == "CRITICAL"
    assert result.calculated_rate_bpd == pytest.approx(
        independent_rate(1000.0, 1000.0, 16.0), rel=1e-12, abs=1e-9
    )
    assert result.pressure_ratio == pytest.approx(0.2, abs=1e-12)


def test_b_repeatability_is_exact():
    engine = ChokeEngine()
    first = engine.calculate(valid_input(liquid_rate_bpd=1000.0))
    second = engine.calculate(valid_input(liquid_rate_bpd=1000.0))
    assert first == second


def test_c_larger_choke_increases_calculated_rate():
    engine = ChokeEngine()
    small = engine.calculate(valid_input(choke_size_64th_in=16.0))
    large = engine.calculate(valid_input(choke_size_64th_in=32.0))
    assert large.calculated_rate_bpd > small.calculated_rate_bpd


def test_d_larger_upstream_pressure_increases_calculated_rate():
    engine = ChokeEngine()
    low = engine.calculate(valid_input(upstream_pressure_psia=1000.0))
    high = engine.calculate(valid_input(upstream_pressure_psia=1500.0))
    assert high.calculated_rate_bpd > low.calculated_rate_bpd


def test_e_higher_downstream_pressure_can_classify_subcritical_without_extrapolation():
    result = ChokeEngine().calculate(valid_input(downstream_pressure_psia=800.0))
    assert result.status == "CORRELATION_LIMITATION"
    assert result.flow_regime == "SUBCRITICAL / NON-CRITICAL"
    assert result.calculated_rate_bpd is None
    assert result.limitations


def test_f_critical_and_subcritical_classification_boundary():
    critical = ChokeEngine().calculate(valid_input(downstream_pressure_psia=699.0))
    subcritical = ChokeEngine().calculate(valid_input(downstream_pressure_psia=700.0))
    assert critical.flow_regime == "CRITICAL"
    assert subcritical.flow_regime == "SUBCRITICAL / NON-CRITICAL"


@pytest.mark.parametrize(
    "field,value,code",
    [
        ("upstream_pressure_psia", -1.0, "PHYSICALLY_INVALID_STATE"),
        ("downstream_pressure_psia", -1.0, "PHYSICALLY_INVALID_STATE"),
        ("choke_size_64th_in", 0.0, "PHYSICALLY_INVALID_STATE"),
        ("choke_size_64th_in", -4.0, "PHYSICALLY_INVALID_STATE"),
        ("gor_scf_stb", -1.0, "PHYSICALLY_INVALID_STATE"),
        ("gor_scf_stb", 0.0, "CORRELATION_LIMITATION"),
        ("liquid_rate_bpd", -1.0, "PHYSICALLY_INVALID_STATE"),
        ("oil_api", 120.0, "PHYSICALLY_INVALID_STATE"),
        ("gas_specific_gravity", 0.0, "PHYSICALLY_INVALID_STATE"),
    ],
)
def test_g_i_j_invalid_inputs_are_typed(field, value, code):
    with pytest.raises(ChokeError) as exc_info:
        ChokeEngine().calculate(valid_input(**{field: value}))
    assert exc_info.value.code == code


def test_h_upstream_must_exceed_downstream():
    with pytest.raises(ChokeError, match="upstream_pressure_psia must be greater"):
        ChokeEngine().calculate(valid_input(upstream_pressure_psia=200.0, downstream_pressure_psia=200.0))


def test_k_unsupported_model_is_rejected_without_fallback():
    with pytest.raises(ChokeError, match="unsupported choke_model"):
        ChokeEngine().calculate(valid_input(choke_model="gilbert_legacy"))


def test_l_outside_screened_range_is_visible_as_warning():
    result = ChokeEngine().calculate(valid_input(gor_scf_stb=100.0, choke_size_64th_in=4.0))
    assert result.status == "OK"
    assert result.warnings
    assert any("outside" in warning for warning in result.warnings)


def test_m_psia_to_psig_unit_interpretation_is_explicit():
    result = ChokeEngine().calculate(valid_input())
    expected = independent_rate(1000.0, 1000.0, 16.0)
    assert result.calculated_rate_bpd == pytest.approx(expected, rel=1e-12)
    assert "psia input / psig in Gilbert equation" in result.units


def test_n_independent_benchmark_case_two():
    result = ChokeEngine().calculate(
        valid_input(
            upstream_pressure_psia=1500.0,
            downstream_pressure_psia=1000.0,
            gor_scf_stb=2000.0,
            choke_size_64th_in=32.0,
        )
    )
    assert result.calculated_rate_bpd == pytest.approx(1635.6711945757165, rel=1e-12)
    assert result.pressure_ratio == pytest.approx(2.0 / 3.0, abs=1e-12)


def test_o_independent_benchmark_case_three_inverse_pressure():
    result = ChokeEngine().calculate(
        valid_input(
            upstream_pressure_psia=1000.0,
            downstream_pressure_psia=100.0,
            gor_scf_stb=1000.0,
            choke_size_64th_in=16.0,
            liquid_rate_bpd=1000.0,
        )
    )
    assert result.correlation_pressure_psia == pytest.approx(
        independent_pressure(1000.0, 1000.0, 16.0), rel=1e-12
    )
    assert result.correlation_pressure_psia == pytest.approx(2319.867509530224, rel=1e-12)


def test_p_black_oil_is_not_required_or_called():
    result = ChokeEngine().calculate(valid_input())
    assert any("Black-Oil PVT: Not required" in item for item in result.limitations)
    assert "BlackOilPvtProvider" not in result.provenance


def test_q_telegram_parsing_and_successful_formatting():
    text, png, error = th.handle_calc(
        {
            "text": "/calc choke choke_model=gilbert_1954 p_up=1000 p_down=200 choke=16 gor=1000 q_liquid=1000"
        },
        None,
    )
    assert png is None
    assert error is None
    assert "Choke Performance" in text
    assert "Status: OK" in text
    assert "Model: gilbert_1954" in text
    assert "Flow Regime: CRITICAL" in text
    assert "Choke Model: Gilbert (1954) critical-flow empirical choke correlation" in text
    assert "Source:" in text
    assert "Traceback" not in text


def test_r_telegram_missing_data_is_engineering_requirement():
    text, png, error = th.handle_calc({"text": "/calc choke p_up=1000"}, None)
    assert png is None
    assert error is None
    assert "Engineering Data Requirement" in text
    assert "p_down" in text
    assert "Traceback" not in text


def test_s_telegram_typed_failure_has_no_traceback():
    text, png, error = th.handle_calc(
        {"text": "/calc choke p_up=-1 p_down=0 choke=16 gor=1000"}, None
    )
    assert png is None
    assert error is None
    assert "PHYSICALLY_INVALID_STATE" in text
    assert "Traceback" not in text
    assert "Choke Performance" not in text


def test_t_existing_gas_lift_route_remains_registered_and_unchanged():
    text, png, error = th.handle_calc(
        {"text": "/calc gas_lift thp=100 tvd=8000 p_inj=1200 q_gas=1000 gamma_g=0.65 t_avg=180 q_liquid=3600"},
        None,
    )
    assert png is None
    assert error is None
    assert "Gas-Lift Calculation Result" in text
    assert "Status: OK" in text
    assert "Choke Performance" not in text


def test_u_other_frozen_routes_remain_registered():
    assert "handle_calc_vlp" in th.handle_calc.__code__.co_names
    assert "handle_calc_nodal" in th.handle_calc.__code__.co_names
    assert "handle_calc_sensitivity" in th.handle_calc.__code__.co_names
    assert "handle_calc_optimize" in th.handle_calc.__code__.co_names
