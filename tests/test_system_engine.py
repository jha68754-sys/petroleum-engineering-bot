from dataclasses import replace

import pytest
from types import SimpleNamespace

from handlers import text_handlers as th
from services.black_oil_pvt import BlackOilPvtProvider
from services.choke_engine import ChokeEngine, ChokeInput, ChokeResult
from services.system_engine import IntegratedSystemEngine, SystemError, SystemInput


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

PVT_ARGS = (
    "pvt_mode=pressure_dependent pvt_model=black_oil_v1 "
    "pvt_pressure_psia=2000 pvt_temperature_f=180 pvt_oil_api=35 "
    "pvt_gas_specific_gravity=0.65 pvt_separator_pressure_psia=100 "
    "pvt_separator_temperature_f=60 pvt_bubble_point_psia=1800"
)

SYSTEM_COMMAND = (
    "/calc system model=linear pr=3000 j=1.5 tvd=8000 id=1.995 "
    "gor=1000 rs=600 api=35 gamma_g=0.65 mu_l=1 bo=1.4 "
    "t_wh=120 geothermal=1.5 choke=16 p_down=200"
)



def test_a_frozen_legacy_choke_remains_unchanged():
    result = ChokeEngine().calculate(ChokeInput(
        upstream_pressure_psia=1000.0,
        downstream_pressure_psia=200.0,
        choke_size_64th_in=16.0,
        gor_scf_stb=1000.0,
        liquid_rate_bpd=1000.0,
        choke_model="gilbert_1954",
    ))
    assert result.calculated_rate_bpd == pytest.approx(427.43, abs=0.01)



def test_b_integrated_legacy_case_converges_and_reuses_choke_engine():
    result = IntegratedSystemEngine().calculate(BASE)
    assert result.status == "OK"
    assert result.operating_rate_bpd == pytest.approx(711.23046875, abs=1e-6)
    assert result.choke_flow_regime == "CRITICAL"
    assert result.choke_result is not None
    assert result.choke_result.calculated_rate_bpd == pytest.approx(result.operating_rate_bpd, abs=1e-9)



def test_c_operating_point_satisfies_well_and_choke_pressure_relationships():
    result = IntegratedSystemEngine().calculate(BASE)
    assert result.upstream_pressure_psia > result.downstream_pressure_psia
    assert result.choke_result is not None
    assert result.upstream_pressure_psia == pytest.approx(
        result.choke_result.upstream_pressure_psia, abs=0.1
    )
    assert result.solver_residual_psi <= BASE.pressure_tol
    assert result.convergence == "converged"



def test_d_integrated_result_is_deterministic_for_identical_inputs():
    first = IntegratedSystemEngine().calculate(BASE)
    second = IntegratedSystemEngine().calculate(BASE)
    assert first.status == second.status
    assert first.operating_rate_bpd == second.operating_rate_bpd
    assert first.pwf_psia == second.pwf_psia
    assert first.upstream_pressure_psia == second.upstream_pressure_psia
    assert first.solver_residual_psi == second.solver_residual_psi
    assert first.choke_flow_regime == second.choke_flow_regime



def test_e_increasing_downstream_pressure_reaches_typed_surface_limit():
    result = IntegratedSystemEngine().calculate(
        replace(BASE, downstream_pressure_psia=1000.0)
    )
    assert result.status == "NO_OPERATING_POINT"
    assert result.operating_rate_bpd is None
    assert result.reason
    assert any(token in result.reason.lower() for token in ("critical-flow", "no rate", "domain"))



def test_f_reducing_choke_opening_reduces_operating_rate():
    wide = IntegratedSystemEngine().calculate(BASE)
    restricted = IntegratedSystemEngine().calculate(
        replace(BASE, choke_size_64th_in=8.0)
    )
    assert wide.status == restricted.status == "OK"
    assert restricted.operating_rate_bpd < wide.operating_rate_bpd



def test_g_invalid_choke_input_remains_typed():
    with pytest.raises(SystemError, match="PHYSICALLY_INVALID_STATE"):
        IntegratedSystemEngine().calculate(replace(BASE, choke_size_64th_in=0.0))



def test_h_explicit_black_oil_binds_existing_provider_without_fallback():
    result = IntegratedSystemEngine().calculate(
        BASE, pvt_provider=BlackOilPvtProvider(), pvt_context=PVT_CONTEXT
    )
    assert result.status == "OK"
    assert result.pvt_metadata["enabled"] is True
    assert result.pvt_metadata["provider"] == "BlackOilPvtProvider"
    assert result.pvt_metadata["evaluation_strategy"] == (
        "dynamic_well_pressure_and_upstream_choke_pressure"
    )
    assert result.pvt_metadata["pressure_range_psia"]



def test_i_black_oil_limitations_remain_visible():
    limited = dict(PVT_CONTEXT)
    limited["non_hydrocarbon_fraction"] = 0.05
    result = IntegratedSystemEngine().calculate(
        BASE, pvt_provider=BlackOilPvtProvider(), pvt_context=limited
    )
    assert result.status == "OK"
    assert result.pvt_metadata["limitations"]



def test_j_explicit_black_oil_invalid_state_does_not_fallback():
    invalid = dict(PVT_CONTEXT)
    invalid["pressure_psia"] = -1.0
    with pytest.raises(SystemError, match="PHYSICALLY_INVALID_STATE"):
        IntegratedSystemEngine().calculate(
            BASE, pvt_provider=BlackOilPvtProvider(), pvt_context=invalid
        )



def test_k_system_handler_renders_legacy_result_without_pvt_provenance():
    text, png, error = th.handle_calc({"text": SYSTEM_COMMAND}, None)
    assert png is None
    assert error is None
    assert "Status: OK" in text
    assert "q_op =" in text
    assert "PVT Provider: BlackOilPvtProvider" not in text
    assert "Traceback" not in text



def test_l_system_handler_renders_black_oil_provenance():
    text, png, error = th.handle_calc(
        {"text": SYSTEM_COMMAND + " " + PVT_ARGS}, None
    )
    assert png is None
    assert error is None
    assert "Status: OK" in text
    assert "PVT Mode: pressure_dependent" in text
    assert "PVT Model: black_oil_v1" in text
    assert "PVT Provider: BlackOilPvtProvider" in text
    assert "NOTE: Results are CALCULATED" in text
    assert "Traceback" not in text



def test_m_system_handler_rejects_unsupported_pvt_model_without_fallback():
    command = SYSTEM_COMMAND + " " + PVT_ARGS.replace(
        "pvt_model=black_oil_v1", "pvt_model=black_oil_v2"
    )
    text, png, error = th.handle_calc({"text": command}, None)
    assert png is None
    assert error is None
    assert "unsupported pvt_model" in text
    assert "Operating Rate" not in text
    assert "Traceback" not in text



def test_n_no_operating_point_is_safe_and_deterministic():
    first = IntegratedSystemEngine().calculate(
        replace(BASE, downstream_pressure_psia=1000.0)
    )
    second = IntegratedSystemEngine().calculate(
        replace(BASE, downstream_pressure_psia=1000.0)
    )
    assert first.status == second.status == "NO_OPERATING_POINT"
    assert first.operating_rate_bpd is None
    assert first.reason == second.reason



def test_o_solver_non_convergence_is_typed_and_has_no_guessed_result():
    class NonConvergingChoke:
        def calculate(self, inputs, *, pvt_provider=None, pvt_context=None):
            q = float(inputs.liquid_rate_bpd)
            pressure = 1000.0 + 0.4 * q
            return ChokeResult(
                status="OK", choke_model="gilbert_1954",
                upstream_pressure_psia=float(inputs.upstream_pressure_psia),
                downstream_pressure_psia=float(inputs.downstream_pressure_psia),
                choke_size_64th_in=float(inputs.choke_size_64th_in),
                gor_scf_stb=float(inputs.gor_scf_stb), calculated_rate_bpd=q,
                supplied_rate_bpd=q, correlation_pressure_psia=pressure,
                pressure_ratio=0.2, flow_regime="CRITICAL",
                provenance="test double", source="test", units="field",
            )

    class NonConvergingSystem(IntegratedSystemEngine):
        def _well_required_thp(self, inputs, model, params, q, pvt_provider,
                               pvt_context, pvt_tracker):
            well_thp = 2200.0 - 0.5 * float(q)
            return well_thp, 1000.0, SimpleNamespace(
                pvt_metadata={}, warnings=[], limitations=[]
            ), 1

    with pytest.raises(SystemError, match="NUMERICAL_NON_CONVERGENCE"):
        NonConvergingSystem(choke_engine=NonConvergingChoke()).calculate(
            replace(BASE, max_refine_iter=1, n_points=11)
        )
