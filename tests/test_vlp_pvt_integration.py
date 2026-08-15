import pytest

from services import vlp_engine
from services.black_oil_pvt import BlackOilPvtProvider, PvtResult, PvtState


WELL = dict(
    thp=100.0,
    tvd=8000.0,
    q_o=3000.0,
    q_w=0.0,
    gor=1000.0,
    bo=1.4,
    bw=1.01,
    z_factor=0.9,
    gamma_g=0.65,
    gamma_w=1.07,
    mu_l=1.0,
    api=35.0,
    wc=0.0,
    tubing_id_in=1.995,
    rs=600.0,
    t_wh=120.0,
    geothermal=1.5,
    sigma=30.0,
)


PVT_CONTEXT = dict(
    pressure_psia=1000.0,
    temperature_f=140.0,
    oil_api=35.0,
    gas_specific_gravity=0.75,
    separator_pressure_psia=100.0,
    separator_temperature_f=100.0,
    bubble_point_psia=2500.0,
    solution_gor_scf_stb=700.0,
)


def run_traverse(model=None, **kwargs):
    args = dict(WELL)
    args.update(kwargs)
    model_kwargs = {} if model is None else {"vlp_model": model}
    return vlp_engine.traverse(
        args.pop("thp"), args.pop("tvd"), args.pop("q_o"), args.pop("q_w"),
        args.pop("gor"), args.pop("bo"), args.pop("bw"),
        args.pop("z_factor"), args.pop("gamma_g"), args.pop("gamma_w"),
        args.pop("mu_l"), args.pop("api"), args.pop("wc"),
        args.pop("tubing_id_in"), args.pop("rs"), args.pop("t_wh"),
        args.pop("geothermal"), sigma=args.pop("sigma"),
        n_segments=args.pop("n_segments", 80), **model_kwargs, **args)


class TrackingProvider(BlackOilPvtProvider):
    def __init__(self):
        super().__init__()
        self.states = []
        self.results = []

    def evaluate(self, state):
        self.states.append(state)
        result = super().evaluate(state)
        self.results.append(result)
        return result


def assert_dynamic_metadata(result):
    metadata = result.pvt_metadata
    assert metadata["enabled"] is True
    assert metadata["mode"] == "pressure_dependent_segment"
    assert metadata["provider"] == "TrackingProvider"
    assert metadata["pvt_evaluations"] > 1
    assert metadata["unique_pressure_states"] > 1
    assert metadata["pressure_range_psia"][0] < metadata["pressure_range_psia"][1]
    assert metadata["provenance"]["package_version"] == "black_oil_v1"
    assert metadata["phase_regions"]
    assert metadata["pressure_psia"] == pytest.approx(metadata["pressure_range_psia"][0])


def test_default_beggs_brill_path_preserves_phase5a_contract():
    result = run_traverse()
    assert result.status == "CONVERGED"
    assert result.pwf == pytest.approx(356.5, abs=2.0)
    assert result.pvt_metadata == {}


def test_default_hagedorn_brown_path_preserves_frozen_control():
    result = vlp_engine.traverse(
        300.0, 4000.0, 800.0, 0.0, 1200.0, 1.3, 1.01, 1.0, 0.65,
        1.07, 2.0, 35.0, 0.0, 1.35, 500.0, 120.0, 1.5,
        vlp_model="hagedorn_brown")
    assert result.status == "CONVERGED"
    assert result.pwf == pytest.approx(332.664, abs=0.01)
    assert result.pvt_metadata == {}


@pytest.mark.parametrize("model", ["beggs_brill", "hagedorn_brown"])
def test_provider_evaluates_multiple_local_pressures_and_reports_metadata(model):
    provider = TrackingProvider()
    result = run_traverse(
        model=model,
        pvt_provider=provider,
        pvt_context=PVT_CONTEXT,
        n_segments=12,
    )
    assert result.status == "CONVERGED"
    assert result.pwf > WELL["thp"]
    assert_dynamic_metadata(result)
    assert len(provider.states) == result.pvt_metadata["pvt_evaluations"]
    assert len({state.pressure_psia for state in provider.states}) > 1
    assert min(state.pressure_psia for state in provider.states) < max(
        state.pressure_psia for state in provider.states)
    assert result.z_factor_provenance == "BlackOilPvtProvider"


def test_pressure_resolved_properties_are_carried_from_provider():
    provider = TrackingProvider()
    result = run_traverse(
        pvt_provider=provider,
        pvt_context=PVT_CONTEXT,
        n_segments=12,
    )
    assert result.status == "CONVERGED"
    for field_name in ("rs_scf_stb", "bo_rb_stb", "mu_o_cp", "z_factor",
                       "bg_rb_scf", "mu_g_cp"):
        values = [getattr(item, field_name) for item in provider.results]
        assert all(value is not None for value in values)
        assert all(value > 0.0 for value in values)
        assert len({round(value, 10) for value in values}) > 1


def test_saturated_rs_changes_across_local_pressure_traverse():
    provider = TrackingProvider()
    result = run_traverse(
        pvt_provider=provider,
        pvt_context=dict(PVT_CONTEXT, bubble_point_psia=10000.0),
        n_segments=12,
    )
    assert result.status == "CONVERGED"
    saturated = [
        item for state, item in zip(provider.states, provider.results)
        if state.pressure_psia < 10000.0
    ]
    assert len(saturated) > 1
    assert {item.phase_region for item in saturated} == {"saturated"}
    assert len({round(item.rs_scf_stb, 10) for item in saturated}) > 1


def test_pressure_entirely_above_pb_uses_undersaturated_branch():
    provider = TrackingProvider()
    result = run_traverse(
        pvt_provider=provider,
        pvt_context=dict(PVT_CONTEXT, bubble_point_psia=50.0),
        n_segments=8,
    )
    assert result.status == "CONVERGED"
    assert result.pvt_metadata["pressure_range_psia"][0] > 50.0
    assert {item.phase_region for item in provider.results} == {"undersaturated"}
    assert result.pvt_metadata["pb_crossed"] is False


def test_pressure_entirely_below_pb_uses_saturated_branch():
    provider = TrackingProvider()
    result = run_traverse(
        pvt_provider=provider,
        pvt_context=dict(PVT_CONTEXT, bubble_point_psia=10000.0),
        n_segments=8,
    )
    assert result.status == "CONVERGED"
    assert result.pvt_metadata["pressure_range_psia"][1] < 10000.0
    assert {item.phase_region for item in provider.results} == {"saturated"}
    assert result.pvt_metadata["pb_crossed"] is False


def test_traverse_crossing_pb_records_both_phase_regions():
    provider = TrackingProvider()
    result = run_traverse(
        pvt_provider=provider,
        pvt_context=dict(PVT_CONTEXT, bubble_point_psia=250.0),
        n_segments=12,
    )
    assert result.status == "CONVERGED"
    pressure_min, pressure_max = result.pvt_metadata["pressure_range_psia"]
    assert pressure_min < 250.0 < pressure_max
    assert {item.phase_region for item in provider.results} >= {
        "saturated", "undersaturated"
    }
    assert result.pvt_metadata["pb_crossed"] is True


def test_exact_pb_evaluation_is_deterministic_bubble_point_state():
    context = dict(PVT_CONTEXT)
    context["pressure_psia"] = context["bubble_point_psia"]
    result = BlackOilPvtProvider().evaluate(PvtState(**context))
    assert result.status == "OK"
    assert result.phase_region == "bubble_point"
    assert result.pressure_psia == pytest.approx(context["bubble_point_psia"])
    assert result.rs_scf_stb == pytest.approx(context["solution_gor_scf_stb"])


def test_zero_rate_static_column_remains_frictionless():
    result = vlp_engine.static_gradient(
        WELL["thp"], WELL["tvd"], WELL["t_wh"], WELL["geothermal"],
        WELL["gamma_g"], WELL["gamma_w"], WELL["z_factor"])
    assert result.status == "CONVERGED"
    assert result.rate == 0.0
    assert result.components["friction"] == 0.0
    assert result.components["acceleration"] == 0.0


def test_provider_passes_dynamic_states_through_vlp_curve():
    provider = TrackingProvider()
    rates, pressures = vlp_engine.vlp_curve(
        WELL["thp"], WELL["tvd"], WELL["gor"], WELL["bo"], WELL["bw"],
        WELL["z_factor"], WELL["gamma_g"], WELL["gamma_w"], WELL["mu_l"],
        WELL["api"], WELL["wc"], WELL["tubing_id_in"], WELL["rs"],
        WELL["t_wh"], WELL["geothermal"], 500.0, 1500.0, 3,
        n_segments=8, pvt_provider=provider, pvt_context=PVT_CONTEXT,
    )
    assert rates == [500.0, 1000.0, 1500.0]
    assert all(value > WELL["thp"] for value in pressures)
    assert len({state.pressure_psia for state in provider.states}) > 1


def test_provider_failure_during_intermediate_segment_propagates():
    class FailingProvider(BlackOilPvtProvider):
        def evaluate(self, state):
            if state.pressure_psia > 150.0:
                return PvtResult(
                    pressure_psia=state.pressure_psia,
                    temperature_f=state.temperature_f,
                    pb_psia=None, rs_scf_stb=None, bo_rb_stb=None,
                    co_1_psi=None, mu_o_cp=None, z_factor=None,
                    bg_rb_scf=None, mu_g_cp=None, phase_region=None,
                    status="NUMERICAL_NON_CONVERGENCE",
                    provenance={"package_version": "test"},
                    warnings=("forced intermediate failure",),
                )
            return super().evaluate(state)

    with pytest.raises(ValueError, match="NUMERICAL_NON_CONVERGENCE"):
        run_traverse(
            pvt_provider=FailingProvider(),
            pvt_context=PVT_CONTEXT,
            n_segments=8,
        )


def test_provider_requires_context():
    with pytest.raises(ValueError, match="INSUFFICIENT_DATA"):
        run_traverse(pvt_provider=BlackOilPvtProvider(), pvt_context={})


def test_provider_requires_explicit_pressure_and_temperature():
    context = dict(PVT_CONTEXT)
    context.pop("pressure_psia")
    with pytest.raises(ValueError, match="PHYSICALLY_INVALID"):
        run_traverse(pvt_provider=BlackOilPvtProvider(), pvt_context=context)


def test_invalid_provider_context_propagates_as_physical_input_error():
    context = dict(PVT_CONTEXT)
    context["pressure_psia"] = "1000"
    with pytest.raises(ValueError, match="PHYSICALLY_INVALID"):
        run_traverse(pvt_provider=BlackOilPvtProvider(), pvt_context=context)


def test_provider_nonconvergence_propagates_for_both_models():
    for model in ("beggs_brill", "hagedorn_brown"):
        provider = BlackOilPvtProvider()
        provider.DAK_MAX_ITERATIONS = 0
        with pytest.raises(ValueError, match="NUMERICAL_NON_CONVERGENCE"):
            run_traverse(
                model=model, pvt_provider=provider, pvt_context=PVT_CONTEXT)


def test_increment_5_routing_is_limited_to_vlp_and_nodal_handlers():
    from pathlib import Path

    handler_text = Path("handlers/text_handlers.py").read_text()
    assert "def handle_calc_vlp(" in handler_text
    assert "def handle_calc_nodal(" in handler_text
    assert "def handle_calc_vlp_compare(" in handler_text


TELEGRAM_PVT_ARGS = (
    "pvt_mode=pressure_dependent pvt_model=black_oil_v1 "
    "pvt_pressure_psia=1000 pvt_temperature_f=140 pvt_oil_api=35 "
    "pvt_gas_specific_gravity=0.75 pvt_separator_pressure_psia=100 "
    "pvt_separator_temperature_f=100 pvt_bubble_point_psia=2500 "
    "pvt_solution_gor_scf_stb=700"
)


def _telegram_message(command: str):
    return {"text": command, "chat": {"id": 1001}}


def _text_handler_module():
    import os

    os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
    from handlers import text_handlers

    return text_handlers


def test_telegram_vlp_default_path_preserves_legacy_response():
    handlers = _text_handler_module()
    response, png, error = handlers.handle_calc_vlp(
        _telegram_message(
            "/calc vlp thp=100 tvd=8000 id=1.995 q=3000 gor=1000 "
            "api=35 gamma_g=0.65 mu_l=1 bo=1.4 rs=600 t_wh=120 "
            "geothermal=1.5"
        ),
        None,
    )
    assert error is None
    assert png is None
    assert response.startswith("VLP Calculation Result")
    assert "Pressure-Dependent PVT Provenance:" not in response


def test_telegram_vlp_pressure_dependent_provider_returns_provenance():
    handlers = _text_handler_module()
    response, png, error = handlers.handle_calc_vlp(
        _telegram_message(
            "/calc vlp thp=100 tvd=8000 id=1.995 q=3000 gor=1000 "
            "api=35 gamma_g=0.65 mu_l=1 bo=1.4 rs=600 t_wh=120 "
            "geothermal=1.5 " + TELEGRAM_PVT_ARGS
        ),
        None,
    )
    assert error is None
    assert png is None
    assert "Pressure-Dependent PVT Provenance:" in response
    assert "PVT Mode: pressure_dependent" in response
    assert "PVT Model: black_oil_v1" in response
    assert "PVT Provider: BlackOilPvtProvider" in response
    assert "Pressure Range Evaluated:" in response
    assert "Phase Region(s):" in response
    assert "PVT Status:" in response
    assert "Traceback" not in response


def test_telegram_vlp_curve_routes_provider_and_reports_provenance():
    handlers = _text_handler_module()
    response, png, error = handlers.handle_calc_vlp(
        _telegram_message(
            "/calc vlp thp=100 tvd=8000 id=1.995 gor=1000 api=35 "
            "gamma_g=0.65 mu_l=1 bo=1.4 rs=600 t_wh=120 geothermal=1.5 "
            "q_min=500 q_max=1500 n_points=3 " + TELEGRAM_PVT_ARGS
        ),
        None,
    )
    assert error is None
    assert png is None
    assert "Calculated VLP Curve" in response
    assert "Pressure-Dependent PVT Provenance:" in response
    assert "PVT Status:" in response


def test_telegram_nodal_pressure_dependent_provider_returns_provenance():
    handlers = _text_handler_module()
    response, png, error = handlers.handle_calc_nodal(
        _telegram_message(
            "/calc nodal model=linear pr=3000 j=1.5 thp=100 tvd=8000 "
            "id=1.995 gor=1000 rs=600 api=35 gamma_g=0.65 mu_l=1 "
            "bo=1.4 t_wh=120 geothermal=1.5 " + TELEGRAM_PVT_ARGS
        ),
        None,
    )
    assert error is None
    assert png is None
    assert "Nodal Analysis Result" in response
    assert "Pressure-Dependent PVT Provenance:" in response
    assert "PVT Mode: pressure_dependent" in response
    assert "PVT Provider: BlackOilPvtProvider" in response
    assert "PVT Status:" in response
    assert "Traceback" not in response


def test_telegram_pvt_missing_context_is_actionable_and_deterministic():
    handlers = _text_handler_module()
    incomplete = TELEGRAM_PVT_ARGS.replace("pvt_separator_temperature_f=100 ", "")
    response, png, error = handlers.handle_calc_vlp(
        _telegram_message(
            "/calc vlp thp=100 tvd=8000 id=1.995 q=3000 gor=1000 "
            "api=35 gamma_g=0.65 mu_l=1 bo=1.4 rs=600 t_wh=120 "
            "geothermal=1.5 " + incomplete
        ),
        None,
    )
    assert png is None
    assert error is None
    assert "Engineering Data Requirement" in response
    assert "pvt_separator_temperature_f" in response


def test_telegram_pvt_provider_failure_has_no_traceback_or_fallback():
    handlers = _text_handler_module()
    response, png, error = handlers.handle_calc_vlp(
        _telegram_message(
            "/calc vlp thp=100 tvd=8000 id=1.995 q=3000 gor=1000 "
            "api=35 gamma_g=0.65 mu_l=1 bo=1.4 rs=600 t_wh=120 "
            "geothermal=1.5 pvt_mode=pressure_dependent "
            "pvt_model=black_oil_v1 pvt_pressure_psia=-1 "
            "pvt_temperature_f=140 pvt_oil_api=35 "
            "pvt_gas_specific_gravity=0.75 pvt_separator_pressure_psia=100 "
            "pvt_separator_temperature_f=100 pvt_bubble_point_psia=2500 "
            "pvt_solution_gor_scf_stb=700"
        ),
        None,
    )
    assert png is None
    assert error is None
    assert "physically invalid Black-Oil PVT input" in response
    assert "Traceback" not in response
    assert "VLP calculation error" not in response


def test_telegram_pvt_option_is_not_enabled_for_vlp_compare():
    handlers = _text_handler_module()
    response, png, error = handlers.handle_calc_vlp_compare(
        _telegram_message(
            "/calc vlp_compare thp=100 tvd=8000 id=1.995 q_min=500 "
            "q_max=1000 gor=1000 api=35 gamma_g=0.65 mu_l=1 bo=1.4 "
            "rs=600 t_wh=120 geothermal=1.5 " + TELEGRAM_PVT_ARGS
        ),
        None,
    )
    assert png is None
    assert error is None
    assert "supported only for /calc vlp and /calc nodal" in response.lower()
    assert "Pressure-Dependent PVT Provenance:" not in response


# A legacy import seam remains intentionally free of Telegram integration;
# only /calc vlp and /calc nodal receive the explicit provider binding.

def test_increment_5_does_not_add_provider_to_plot_or_unrelated_handlers():
    from pathlib import Path

    handler_text = Path("handlers/text_handlers.py").read_text()
    assert "def handle_plot(" in handler_text or "def handle_calc_plot(" in handler_text
    assert "pvt_provider=pvt_provider" in handler_text
    assert "handle_calc_vlp_compare" in handler_text
    assert "pvt_mode" not in handler_text.split("def handle_calc_vlp_compare", 1)[1].split("def ", 1)[0]


def test_telegram_pvt_selector_values_are_normalized():
    handlers = _text_handler_module()
    response, png, error = handlers.handle_calc_vlp(
        _telegram_message(
            "/calc vlp thp=100 tvd=8000 id=1.995 q=3000 gor=1000 "
            "api=35 gamma_g=0.65 mu_l=1 bo=1.4 rs=600 t_wh=120 "
            "geothermal=1.5 pvt_mode=PRESSURE_DEPENDENT "
            "pvt_model=BLACK_OIL_V1 " + TELEGRAM_PVT_ARGS.split("pvt_mode=pressure_dependent pvt_model=black_oil_v1 ", 1)[1]
        ),
        None,
    )
    assert error is None
    assert png is None
    assert "PVT Mode: pressure_dependent" in response
    assert "PVT Model: black_oil_v1" in response


def test_telegram_unsupported_pvt_model_is_rejected_without_fallback():
    handlers = _text_handler_module()
    response, png, error = handlers.handle_calc_vlp(
        _telegram_message(
            "/calc vlp thp=100 tvd=8000 id=1.995 q=3000 gor=1000 "
            "api=35 gamma_g=0.65 mu_l=1 bo=1.4 rs=600 t_wh=120 "
            "geothermal=1.5 pvt_mode=pressure_dependent "
            "pvt_model=unsupported_model"
        ),
        None,
    )
    assert png is None
    assert error is None
    assert "unsupported pvt_model" in response
    assert "VLP calculation error" not in response


def test_telegram_provider_nonconvergence_is_typed_and_no_traceback(monkeypatch):
    handlers = _text_handler_module()

    class FailingProvider(handlers.BlackOilPvtProvider):
        DAK_MAX_ITERATIONS = 0

    monkeypatch.setattr(handlers, "BlackOilPvtProvider", FailingProvider)
    response, png, error = handlers.handle_calc_vlp(
        _telegram_message(
            "/calc vlp thp=100 tvd=8000 id=1.995 q=3000 gor=1000 "
            "api=35 gamma_g=0.65 mu_l=1 bo=1.4 rs=600 t_wh=120 "
            "geothermal=1.5 " + TELEGRAM_PVT_ARGS
        ),
        None,
    )
    assert png is None
    assert error is None
    assert "Black-Oil PVT numerical non-convergence" in response
    assert "Traceback" not in response
    assert "VLP calculation error" not in response
