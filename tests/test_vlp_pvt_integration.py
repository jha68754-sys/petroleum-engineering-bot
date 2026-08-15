import pytest

from services import vlp_engine
from services.black_oil_pvt import BlackOilPvtProvider


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


def test_default_path_preserves_phase5a_contract_and_metadata_is_empty():
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
def test_explicit_provider_state_converges_and_reports_provenance(model):
    result = run_traverse(
        model=model,
        pvt_provider=BlackOilPvtProvider(),
        pvt_context=PVT_CONTEXT,
    )

    assert result.status == "CONVERGED"
    assert result.pwf > WELL["thp"]
    assert result.pvt_metadata["enabled"] is True
    assert result.pvt_metadata["mode"] == "explicit_state"
    assert result.pvt_metadata["provider"] == "BlackOilPvtProvider"
    assert result.pvt_metadata["pressure_psia"] == pytest.approx(1000.0)
    assert result.pvt_metadata["pressure_range_psia"] == [1000.0, 1000.0]
    assert set(result.pvt_metadata["statuses"]) <= {"OK", "CORRELATION_LIMITATION"}
    assert "OK" in result.pvt_metadata["statuses"]
    assert result.pvt_metadata["phase_regions"]
    assert result.pvt_metadata["provenance"]["package_version"] == "black_oil_v1"
    assert result.z_factor_provenance == "BlackOilPvtProvider"


def test_explicit_provider_state_is_evaluated_once_per_traverse():
    class CountingProvider(BlackOilPvtProvider):
        def __init__(self):
            super().__init__()
            self.calls = 0

        def evaluate(self, state):
            self.calls += 1
            return super().evaluate(state)

    provider = CountingProvider()
    result = run_traverse(
        pvt_provider=provider,
        pvt_context=PVT_CONTEXT,
        n_segments=12,
    )

    assert result.status == "CONVERGED"
    assert provider.calls == 1
    assert result.pvt_metadata["pressure_range_psia"] == [1000.0, 1000.0]


def test_explicit_provider_is_passed_through_vlp_curve():
    provider = BlackOilPvtProvider()
    baseline_q, baseline_p = vlp_engine.vlp_curve(
        WELL["thp"], WELL["tvd"], WELL["gor"], WELL["bo"], WELL["bw"],
        WELL["z_factor"], WELL["gamma_g"], WELL["gamma_w"], WELL["mu_l"],
        WELL["api"], WELL["wc"], WELL["tubing_id_in"], WELL["rs"],
        WELL["t_wh"], WELL["geothermal"], 500.0, 1500.0, 3,
        n_segments=8,
    )
    provider_q, provider_p = vlp_engine.vlp_curve(
        WELL["thp"], WELL["tvd"], WELL["gor"], WELL["bo"], WELL["bw"],
        WELL["z_factor"], WELL["gamma_g"], WELL["gamma_w"], WELL["mu_l"],
        WELL["api"], WELL["wc"], WELL["tubing_id_in"], WELL["rs"],
        WELL["t_wh"], WELL["geothermal"], 500.0, 1500.0, 3,
        n_segments=8, pvt_provider=provider, pvt_context=PVT_CONTEXT,
    )

    assert provider_q == baseline_q == [500.0, 1000.0, 1500.0]
    assert all(value > WELL["thp"] for value in provider_p)
    assert any(abs(a - b) > 1.0e-8 for a, b in zip(baseline_p, provider_p))


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


@pytest.mark.parametrize("model", ["beggs_brill", "hagedorn_brown"])
def test_provider_nonconvergence_propagates(model):
    provider = BlackOilPvtProvider()
    provider.DAK_MAX_ITERATIONS = 0

    with pytest.raises(ValueError, match="NUMERICAL_NON_CONVERGENCE"):
        run_traverse(
            model=model, pvt_provider=provider, pvt_context=PVT_CONTEXT)
