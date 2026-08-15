from pathlib import Path

import pytest

from services.black_oil_pvt import BlackOilPvtProvider
from services.nodal_engine import NodalEngine, NodalError


WELL = dict(
    thp=100.0,
    tvd=8000.0,
    tubing_id_in=1.995,
    gor=1000.0,
    rs=600.0,
    api=35.0,
    gamma_g=0.65,
    mu_l=1.0,
    bo=1.4,
    t_wh=120.0,
    geothermal=1.5,
    bw=1.01,
    z_factor=0.9,
    gamma_w=1.07,
    wc=0.0,
    sigma=30.0,
    n_segments=12,
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


def solve_nodal(**overrides):
    args = dict(WELL)
    args.update(overrides)
    return NodalEngine().solve(
        ipr_model=args.pop("ipr_model", "linear"),
        pr=args.pop("pr", 3000.0),
        pb=args.pop("pb", None),
        j=args.pop("j", 1.5),
        j_star=args.pop("j_star", None),
        qmax=args.pop("qmax", None),
        q_test=args.pop("q_test", None),
        pwf_test=args.pop("pwf_test", None),
        q_min=args.pop("q_min", None),
        q_max=args.pop("q_max", None),
        n_points=args.pop("n_points", 41),
        vlp_model=args.pop("vlp_model", "beggs_brill"),
        pvt_provider=args.pop("pvt_provider", None),
        pvt_context=args.pop("pvt_context", None),
        **args,
    )


def test_legacy_nodal_path_reproduces_frozen_linear_control():
    result = solve_nodal(n_points=201, n_segments=80)
    assert result.status == "UNIQUE_OPERATING_POINT"
    assert result.roots[0].q == pytest.approx(3944.198913574, abs=1.0e-6)
    assert result.roots[0].pwf == pytest.approx(370.533655486, abs=1.0e-6)
    assert result.pvt_metadata == {}


@pytest.mark.parametrize("vlp_model", ["beggs_brill", "hagedorn_brown"])
def test_nodal_explicit_black_oil_provider_converges(vlp_model):
    result = solve_nodal(
        vlp_model=vlp_model,
        pvt_provider=BlackOilPvtProvider(),
        pvt_context=PVT_CONTEXT,
    )

    assert result.status == "UNIQUE_OPERATING_POINT"
    assert len(result.roots) == 1
    assert result.roots[0].q > 0.0
    assert result.pvt_metadata["enabled"] is True
    assert result.pvt_metadata["mode"] == "explicit_state"
    assert result.pvt_metadata["provider"] == "BlackOilPvtProvider"
    assert result.pvt_metadata["pressure_psia"] == pytest.approx(1000.0)
    assert result.pvt_metadata["pressure_range_psia"] == [1000.0, 1000.0]
    assert result.pvt_metadata["provenance"]["package_version"] == "black_oil_v1"
    assert result.vlp_kwargs["pvt_context"] == PVT_CONTEXT


def test_provider_context_is_propagated_through_nodal_into_vlp():
    class SpyProvider(BlackOilPvtProvider):
        def __init__(self):
            super().__init__()
            self.states = []

        def evaluate(self, state):
            self.states.append(state)
            return super().evaluate(state)

    provider = SpyProvider()
    result = solve_nodal(
        pvt_provider=provider,
        pvt_context=PVT_CONTEXT,
        n_points=21,
    )

    assert result.status == "UNIQUE_OPERATING_POINT"
    assert provider.states
    assert all(state.pressure_psia == pytest.approx(1000.0)
               for state in provider.states)
    assert all(state.temperature_f == pytest.approx(140.0)
               for state in provider.states)
    assert result.pvt_metadata["pressure_range_psia"] == [1000.0, 1000.0]


@pytest.mark.parametrize("vlp_model", ["beggs_brill", "hagedorn_brown"])
def test_missing_provider_context_fails_deterministically(vlp_model):
    with pytest.raises(NodalError, match="INSUFFICIENT_DATA"):
        solve_nodal(
            vlp_model=vlp_model,
            pvt_provider=BlackOilPvtProvider(),
            pvt_context=None,
        )


def test_invalid_physical_provider_context_fails_deterministically():
    context = dict(PVT_CONTEXT)
    context["pressure_psia"] = -1.0
    with pytest.raises(NodalError) as exc:
        solve_nodal(
            pvt_provider=BlackOilPvtProvider(),
            pvt_context=context,
        )
    assert exc.value.kind == "PHYSICALLY_INVALID"


@pytest.mark.parametrize("vlp_model", ["beggs_brill", "hagedorn_brown"])
def test_provider_nonconvergence_is_not_replaced_by_legacy_values(vlp_model):
    provider = BlackOilPvtProvider()
    provider.DAK_MAX_ITERATIONS = 0

    with pytest.raises(NodalError, match="NUMERICAL_NON_CONVERGENCE"):
        solve_nodal(
            vlp_model=vlp_model,
            pvt_provider=provider,
            pvt_context=PVT_CONTEXT,
        )


def test_increment_3_does_not_add_telegram_routing():
    handler_text = Path("handlers/text_handlers.py").read_text()
    assert "pvt_model" not in handler_text
    assert "BlackOilPvtProvider" not in handler_text
