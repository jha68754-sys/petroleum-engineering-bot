from __future__ import annotations

from dataclasses import replace

import pytest

from handlers import text_handlers as th
from services.black_oil_pvt import BlackOilPvtProvider
from services.gas_lift_engine import GasLiftEngine, GasLiftError, GasLiftInput


BASE = GasLiftInput(
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

PVT_ARGS = (
    "pvt_mode=pressure_dependent pvt_model=black_oil_v1 "
    "pvt_pressure_psia=2000 pvt_temperature_f=180 pvt_oil_api=35 "
    "pvt_gas_specific_gravity=0.65 pvt_separator_pressure_psia=100 "
    "pvt_separator_temperature_f=60 pvt_bubble_point_psia=1800"
)

VALID_COMMAND = (
    "/calc gas_lift thp=100 tvd=8000 p_inj=1200 q_gas=1000 "
    "gamma_g=0.65 t_avg=180 q_liquid=3000 pr=3000 j=1.5 "
    + PVT_ARGS
)


def _result_with_shift(result, z_factor=None, bo_rb_stb=None):
    return replace(
        result,
        z_factor=result.z_factor if z_factor is None else result.z_factor * z_factor,
        bo_rb_stb=result.bo_rb_stb if bo_rb_stb is None else result.bo_rb_stb * bo_rb_stb,
    )


class RecordingProvider(BlackOilPvtProvider):
    def __init__(self, z_multiplier=1.0, bo_multiplier=1.0):
        super().__init__()
        self.states = []
        self.z_multiplier = z_multiplier
        self.bo_multiplier = bo_multiplier

    def evaluate(self, state):
        self.states.append(state)
        result = super().evaluate(state)
        return _result_with_shift(
            result,
            z_factor=self.z_multiplier,
            bo_rb_stb=self.bo_multiplier,
        )


def test_a_n_legacy_reference_case_is_unchanged_and_repeatable():
    engine = GasLiftEngine()
    first = engine.calculate(BASE)
    second = engine.calculate(BASE)

    assert first == second
    assert first.pvt_metadata == {}
    assert first.injection_depth_ft == pytest.approx(8000.0, abs=1e-6)
    assert first.representative_pressure_psia == pytest.approx(280.0, abs=1e-6)
    assert first.injected_gas_in_situ_bpd == pytest.approx(704.19, abs=0.01)
    assert first.gas_fraction == pytest.approx(0.1636, abs=0.0001)
    assert first.bottomhole_pressure_with_lift_psia == pytest.approx(408.86, abs=0.01)
    assert first.predicted_oil_rate_stbd == pytest.approx(3886.71, abs=0.01)
    assert any("reserved for Increment 9" in item for item in first.limitations)


def test_b_explicit_selector_binds_the_existing_black_oil_provider():
    text, png, error = th.handle_calc({"text": VALID_COMMAND}, None)
    assert png is None
    assert error is None
    assert "PVT Mode: pressure_dependent" in text
    assert "PVT Model: black_oil_v1" in text
    assert "PVT Provider: BlackOilPvtProvider" in text
    assert "Gas-Lift Calculation Result" in text
    assert "Traceback" not in text


def test_c_black_oil_properties_are_consumed_by_the_engine():
    provider = RecordingProvider()
    result = GasLiftEngine().calculate(BASE, pvt_provider=provider, pvt_context=PVT_CONTEXT)

    assert result.pvt_metadata["enabled"] is True
    assert result.pvt_metadata["properties_consumed"] == ["z_factor", "bo_rb_stb"]
    assert {point["name"] for point in result.pvt_metadata["evaluation_points"]} == {
        "representative_tubing",
        "injection_point",
    }
    assert len(provider.states) == 2
    assert result.liquid_in_situ_bpd != pytest.approx(
        BASE.liquid_rate_stbd * BASE.oil_fvf_rb_stb,
        abs=1e-6,
    )
    assert result.injected_gas_in_situ_bpd != pytest.approx(
        BASE.gas_injection_rate_mscfd * 1000.0 * BASE.z_factor
        * (BASE.average_temperature_f + 459.67)
        / (result.representative_pressure_psia * 520.0) / 5.615,
        abs=1e-6,
    )


def test_d_relevant_pressure_changes_pressure_dependent_evaluation():
    first_provider = RecordingProvider()
    second_provider = RecordingProvider()
    first = GasLiftEngine().calculate(BASE, pvt_provider=first_provider, pvt_context=PVT_CONTEXT)
    second = GasLiftEngine().calculate(
        replace(BASE, thp_psia=200.0),
        pvt_provider=second_provider,
        pvt_context=PVT_CONTEXT,
    )

    assert {state.pressure_psia for state in first_provider.states} != {
        state.pressure_psia for state in second_provider.states
    }
    assert first.representative_pressure_psia != second.representative_pressure_psia
    assert first.injected_gas_in_situ_bpd != second.injected_gas_in_situ_bpd


def test_e_required_black_oil_context_is_validated():
    with pytest.raises(GasLiftError, match="INSUFFICIENT_DATA"):
        GasLiftEngine().calculate(BASE, pvt_provider=BlackOilPvtProvider(), pvt_context=None)

    invalid = dict(PVT_CONTEXT)
    invalid["pressure_psia"] = -1.0
    with pytest.raises(GasLiftError, match="PHYSICALLY_INVALID_STATE"):
        GasLiftEngine().calculate(BASE, pvt_provider=BlackOilPvtProvider(), pvt_context=invalid)


def test_f_unsupported_pvt_mode_fails_without_legacy_fallback():
    text, png, error = th.handle_calc(
        {"text": "/calc gas_lift thp=100 tvd=8000 p_inj=1200 q_gas=1000 gamma_g=0.65 t_avg=180 q_liquid=3000 pvt_mode=legacy pvt_model=black_oil_v1"},
        None,
    )
    assert png is None
    assert error is None
    assert "unsupported pvt_mode" in text
    assert "Gas-Lift Calculation Result" not in text


def test_g_unsupported_pvt_model_fails_without_legacy_fallback():
    text, png, error = th.handle_calc(
        {"text": VALID_COMMAND.replace("pvt_model=black_oil_v1", "pvt_model=black_oil_v2")},
        None,
    )
    assert png is None
    assert error is None
    assert "unsupported pvt_model" in text
    assert "Gas-Lift Calculation Result" not in text


def test_h_explicit_black_oil_mode_cannot_fall_back_to_increment_8_values():
    legacy = GasLiftEngine().calculate(BASE)
    shifted_provider = RecordingProvider(z_multiplier=1.15, bo_multiplier=1.10)
    pressure_dependent = GasLiftEngine().calculate(
        BASE,
        pvt_provider=shifted_provider,
        pvt_context=PVT_CONTEXT,
    )

    assert pressure_dependent.pvt_metadata["enabled"] is True
    assert shifted_provider.states
    assert pressure_dependent != legacy
    assert pressure_dependent.injected_gas_in_situ_bpd != pytest.approx(
        legacy.injected_gas_in_situ_bpd,
        abs=1e-6,
    )


def test_i_invalid_black_oil_state_is_typed_and_not_fabricated():
    invalid = dict(PVT_CONTEXT)
    invalid["temperature_f"] = -500.0
    with pytest.raises(GasLiftError, match="PHYSICALLY_INVALID_STATE"):
        GasLiftEngine().calculate(BASE, pvt_provider=BlackOilPvtProvider(), pvt_context=invalid)

    text, png, error = th.handle_calc({"text": VALID_COMMAND.replace("pvt_pressure_psia=2000", "pvt_pressure_psia=-1")}, None)
    assert png is None
    assert error is None
    assert "PHYSICALLY_INVALID_STATE" in text
    assert "Gas-Lift Calculation Result" not in text
    assert "Traceback" not in text


def test_j_correlation_limitations_remain_visible():
    limited = dict(PVT_CONTEXT)
    limited["non_hydrocarbon_fraction"] = 0.05
    result = GasLiftEngine().calculate(
        BASE,
        pvt_provider=BlackOilPvtProvider(),
        pvt_context=limited,
    )

    assert result.pvt_metadata["statuses"] == ["CORRELATION_LIMITATION"]
    assert result.pvt_metadata["limitations"]
    assert any("sour-gas" in item for item in result.limitations)


def test_k_provider_failure_is_typed_and_never_replaced_by_legacy_result():
    provider = BlackOilPvtProvider()
    provider.DAK_MAX_ITERATIONS = 0
    with pytest.raises(GasLiftError, match="NUMERICAL_NON_CONVERGENCE"):
        GasLiftEngine().calculate(BASE, pvt_provider=provider, pvt_context=PVT_CONTEXT)


def test_l_injection_pressure_balance_and_m_trend_are_preserved_with_provider():
    provider = BlackOilPvtProvider()
    shallow = GasLiftEngine().calculate(
        replace(BASE, injection_pressure_psia=300.0),
        pvt_provider=provider,
        pvt_context=PVT_CONTEXT,
    )
    deep = GasLiftEngine().calculate(
        BASE,
        pvt_provider=BlackOilPvtProvider(),
        pvt_context=PVT_CONTEXT,
    )

    assert shallow.injection_depth_ft < deep.injection_depth_ft
    assert abs(shallow.pressure_margin_at_injection_psi) <= 0.01
    assert shallow.required_surface_injection_pressure_psia <= 300.0 + 0.01
    assert deep.required_surface_injection_pressure_psia <= BASE.injection_pressure_psia


def test_handler_missing_state_is_typed_without_fabricating_a_result():
    text, png, error = th.handle_calc(
        {"text": "/calc gas_lift thp=100 tvd=8000 p_inj=1200 q_gas=1000 gamma_g=0.65 t_avg=180 q_liquid=3000 pvt_mode=pressure_dependent pvt_model=black_oil_v1 pvt_pressure_psia=2000"},
        None,
    )
    assert png is None
    assert error is None
    assert "pressure-dependent Black-Oil PVT is missing" in text
    assert "Gas-Lift Calculation Result" not in text
    assert "Traceback" not in text


def test_handler_unknown_pvt_option_is_rejected_without_fallback():
    text, png, error = th.handle_calc({"text": VALID_COMMAND + " pvt_unknown=1"}, None)
    assert png is None
    assert error is None
    assert "unsupported PVT option" in text
    assert "Gas-Lift Calculation Result" not in text


def test_provider_provenance_is_deterministic_and_concise():
    provider = RecordingProvider()
    first = GasLiftEngine().calculate(BASE, pvt_provider=provider, pvt_context=PVT_CONTEXT)
    second = GasLiftEngine().calculate(BASE, pvt_provider=BlackOilPvtProvider(), pvt_context=PVT_CONTEXT)

    assert first.pvt_metadata["provider"] == "RecordingProvider"
    assert first.pvt_metadata["pressure_range_psia"][0] < first.pvt_metadata["pressure_range_psia"][1]
    assert first.pvt_metadata["pvt_evaluations"] == 2
    assert first.pvt_metadata["phase_regions"]
    assert first.pvt_metadata["provenance"]["package_version"] == "black_oil_v1"
    assert second.pvt_metadata["provider"] == "BlackOilPvtProvider"


def test_legacy_handler_has_no_black_oil_provenance():
    command = "/calc gas_lift thp=100 tvd=8000 p_inj=1200 q_gas=1000 gamma_g=0.65 t_avg=180 q_liquid=3000 pr=3000 j=1.5"
    text, png, error = th.handle_calc({"text": command}, None)
    assert png is None
    assert error is None
    assert "Status: OK" in text
    assert "PVT Provider: BlackOilPvtProvider" not in text
    assert "Pressure-Dependent PVT Provenance" not in text
