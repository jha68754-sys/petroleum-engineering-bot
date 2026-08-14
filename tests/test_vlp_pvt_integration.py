import os

import pytest

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")

from services.black_oil_pvt import BlackOilPvtProvider
from services import vlp_engine
from handlers import text_handlers


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


def test_provider_changes_pressure_dependent_beggs_brill_result_and_reports_metadata():
    baseline = run_traverse()
    result = run_traverse(
        pvt_provider=BlackOilPvtProvider(), pvt_context=PVT_CONTEXT)

    assert result.status == "CONVERGED"
    assert result.pwf != pytest.approx(baseline.pwf, abs=1.0e-8)
    assert result.pvt_metadata["enabled"] is True
    assert result.pvt_metadata["mode"] == "pressure_dependent"
    assert result.pvt_metadata["provider"] == "BlackOilPvtProvider"
    assert result.pvt_metadata["pressure_range_psia"][0] < result.pvt_metadata["pressure_range_psia"][1]
    assert "black_oil_v1" == result.pvt_metadata["provenance"]["package_version"]
    assert set(result.pvt_metadata["statuses"]) <= {"OK", "CORRELATION_LIMITATION"}
    assert "OK" in result.pvt_metadata["statuses"]
    assert result.pvt_metadata["phase_regions"]
    assert result.z_factor_provenance == "BlackOilPvtProvider"


@pytest.mark.parametrize("model", ["beggs_brill", "hagedorn_brown"])
def test_provider_path_converges_for_both_vlp_models(model):
    result = run_traverse(
        model=model, pvt_provider=BlackOilPvtProvider(),
        pvt_context=PVT_CONTEXT)

    assert result.status == "CONVERGED"
    assert result.pvt_metadata["enabled"] is True
    assert set(result.pvt_metadata["statuses"]) <= {"OK", "CORRELATION_LIMITATION"}
    assert "OK" in result.pvt_metadata["statuses"]
    assert result.pvt_metadata["pressure_range_psia"]
    assert result.z_factor_provenance == "BlackOilPvtProvider"
    assert result.pwf > WELL["thp"]


def test_provider_is_passed_through_vlp_curve():
    provider = BlackOilPvtProvider()
    baseline_q, baseline_p = vlp_engine.vlp_curve(
        WELL["thp"], WELL["tvd"], WELL["gor"], WELL["bo"], WELL["bw"],
        WELL["z_factor"], WELL["gamma_g"], WELL["gamma_w"], WELL["mu_l"],
        WELL["api"], WELL["wc"], WELL["tubing_id_in"], WELL["rs"],
        WELL["t_wh"], WELL["geothermal"], 500.0, 1500.0, 3,
        n_segments=8)
    provider_q, provider_p = vlp_engine.vlp_curve(
        WELL["thp"], WELL["tvd"], WELL["gor"], WELL["bo"], WELL["bw"],
        WELL["z_factor"], WELL["gamma_g"], WELL["gamma_w"], WELL["mu_l"],
        WELL["api"], WELL["wc"], WELL["tubing_id_in"], WELL["rs"],
        WELL["t_wh"], WELL["geothermal"], 500.0, 1500.0, 3,
        n_segments=8, pvt_provider=provider, pvt_context=PVT_CONTEXT)

    assert provider_q == baseline_q
    assert provider_q == [500.0, 1000.0, 1500.0]
    assert any(abs(a - b) > 1.0e-8 for a, b in zip(baseline_p, provider_p))


@pytest.mark.parametrize("model", ["beggs_brill", "hagedorn_brown"])
def test_missing_provider_context_propagates_as_insufficient_data(model):
    with pytest.raises(ValueError, match="INSUFFICIENT_DATA"):
        run_traverse(
            model=model, pvt_provider=BlackOilPvtProvider(), pvt_context={})


def test_invalid_provider_context_propagates_as_physical_input_error():
    with pytest.raises(ValueError, match="PHYSICALLY_INVALID"):
        run_traverse(
            pvt_provider=BlackOilPvtProvider(),
            pvt_context={"oil_api": 35.0})


@pytest.mark.parametrize("model", ["beggs_brill", "hagedorn_brown"])
def test_provider_nonconvergence_propagates(model):
    provider = BlackOilPvtProvider()
    provider.DAK_MAX_ITERATIONS = 0

    with pytest.raises(ValueError, match="NUMERICAL_NON_CONVERGENCE"):
        run_traverse(model=model, pvt_provider=provider, pvt_context=PVT_CONTEXT)


def _handler_vlp_text(**extra):
    args = {
        "thp": 100, "tvd": 8000, "id": 1.995, "q": 3000,
        "gor": 1000, "rs": 600, "api": 35, "gamma_g": 0.65,
        "mu_l": 1, "bo": 1.4, "t_wh": 120, "geothermal": 1.5,
        "segments": 8,
    }
    args.update(extra)
    return "/calc vlp " + " ".join(f"{key}={value}" for key, value in args.items())


def test_telegram_vlp_default_path_has_no_provider_annotation():
    text, png, caption = text_handlers.handle_calc_vlp(
        {"text": _handler_vlp_text()}, None)
    assert png is None
    assert caption is None
    assert "VLP Calculation Result" in text
    assert "PVT model:" not in text
    assert "Gas Z-factor = 1.00 (default" in text


def test_telegram_vlp_black_oil_model_routes_and_reports_metadata():
    text, png, caption = text_handlers.handle_calc_vlp(
        {"text": _handler_vlp_text(
            pvt_model="black_oil", pvt_sep_p=100, pvt_sep_t=100,
            pvt_pb=2500, pvt_rsb=700)}, None)
    assert png is None
    assert caption is None
    assert "PVT model: Black-Oil V1 (pressure-dependent)" in text
    assert "PVT pressure range:" in text
    assert "Black-Oil provider" in text


def test_telegram_vlp_black_oil_requires_context():
    text, png, caption = text_handlers.handle_calc_vlp(
        {"text": _handler_vlp_text(pvt_model="black_oil")}, None)
    assert png is None
    assert caption is None
    assert "pvt_model=black_oil requires" in text
    assert "pvt_sep_p" in text


def test_telegram_vlp_rejects_unknown_pvt_model():
    text, png, caption = text_handlers.handle_calc_vlp(
        {"text": _handler_vlp_text(pvt_model="eos")}, None)
    assert png is None
    assert caption is None
    assert text.startswith("Error: unknown pvt_model")
