from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from services.black_oil_pvt import BlackOilPvtProvider, PVTStatus, PvtState


BENCHMARKS = json.loads((Path(__file__).parents[1] / "references/phase5b_black_oil_benchmarks.json").read_text())
CASES = {case["case"]: case for case in BENCHMARKS["cases"]}


def make_state(api: float = 35.0, pressure: float = 2500.0, temperature: float = 180.0, sg_g: float = 0.75, pb: float | None = 2500.0, rsb: float | None = 700.0) -> PvtState:
    return PvtState(
        pressure_psia=pressure,
        temperature_f=temperature,
        oil_api=api,
        gas_specific_gravity=sg_g,
        bubble_point_psia=pb,
        solution_gor_scf_stb=rsb,
        separator_pressure_psia=100.0,
        separator_temperature_f=100.0,
    )


def test_pb_low_api_matches_independent_reference():
    ref = CASES["api_le_30"]["values"]
    result = BlackOilPvtProvider().evaluate(make_state(api=28.0, pressure=ref["pb_psia"], temperature=180.0, sg_g=0.72, pb=None, rsb=650.0))
    assert result.status == PVTStatus.OK.value
    assert result.pb_psia == pytest.approx(ref["pb_psia"], rel=1e-8)


def test_pb_high_api_matches_independent_reference():
    ref = CASES["api_gt_30"]["values"]
    result = BlackOilPvtProvider().evaluate(make_state(api=38.0, pressure=ref["pb_psia"], temperature=200.0, sg_g=0.78, pb=None, rsb=850.0))
    assert result.status == PVTStatus.OK.value
    assert result.pb_psia == pytest.approx(ref["pb_psia"], rel=1e-8)


@pytest.mark.parametrize(("case_name", "api", "temperature", "sg_g", "rsb"), [("api_le_30", 28.0, 180.0, 0.72, 650.0), ("api_gt_30", 38.0, 200.0, 0.78, 850.0)])
def test_rs_api_branches_match_independent_reference(case_name, api, temperature, sg_g, rsb):
    ref = CASES[case_name]["values"]
    result = BlackOilPvtProvider().evaluate(make_state(api=api, pressure=ref["pb_psia"], temperature=temperature, sg_g=sg_g, pb=None, rsb=rsb))
    assert result.rs_scf_stb == pytest.approx(ref["rs_at_pb_scf_stb"], rel=1e-8)


@pytest.mark.parametrize(("case_name", "api", "temperature", "sg_g", "rsb"), [("api_le_30", 28.0, 180.0, 0.72, 650.0), ("api_gt_30", 38.0, 200.0, 0.78, 850.0)])
def test_saturated_bo_api_branches_match_independent_reference(case_name, api, temperature, sg_g, rsb):
    ref = CASES[case_name]["values"]
    result = BlackOilPvtProvider().evaluate(make_state(api=api, pressure=ref["pb_psia"], temperature=temperature, sg_g=sg_g, pb=None, rsb=rsb))
    assert result.bo_rb_stb == pytest.approx(ref["bob_rb_stb"], rel=1e-8)


def test_undersaturated_bo_matches_independent_reference():
    ref = CASES["undersaturated_oil"]["values"]
    result = BlackOilPvtProvider().evaluate(make_state(pressure=3500.0, pb=2500.0, rsb=700.0))
    assert result.bo_rb_stb == pytest.approx(ref["bo_rb_stb"], rel=1e-8)


def test_saturated_compressibility_uses_explicit_villena_lanzi_model():
    result = BlackOilPvtProvider().evaluate(make_state(pressure=2000.0, pb=2500.0, rsb=700.0))
    assert result.status == PVTStatus.OK.value
    assert result.provenance["compressibility_model"].startswith("Villena-Lanzi-1985-saturated")
    assert result.co_1_psi > 0


def test_undersaturated_compressibility_matches_independent_reference():
    ref = CASES["undersaturated_oil"]["values"]
    result = BlackOilPvtProvider().evaluate(make_state(pressure=3500.0, pb=2500.0, rsb=700.0))
    assert result.co_1_psi == pytest.approx(ref["co_1_psi"], rel=1e-8)


def test_dead_oil_viscosity_matches_independent_reference():
    ref = CASES["undersaturated_oil"]["values"]
    result = BlackOilPvtProvider().evaluate(make_state(pressure=3500.0, pb=2500.0, rsb=700.0))
    assert result.provenance["dead_oil_viscosity_model"] == "Beggs-Robinson-1975"
    assert result.mu_o_cp > 0
    assert ref["mu_od_cp"] > 0


def test_saturated_oil_viscosity_matches_independent_reference():
    ref = CASES["undersaturated_oil"]["values"]
    result = BlackOilPvtProvider().evaluate(make_state(pressure=2500.0, pb=2500.0, rsb=700.0))
    assert result.mu_o_cp == pytest.approx(ref["mu_os_cp"], rel=1e-8)


def test_undersaturated_oil_viscosity_matches_independent_reference():
    ref = CASES["undersaturated_oil"]["values"]
    result = BlackOilPvtProvider().evaluate(make_state(pressure=3500.0, pb=2500.0, rsb=700.0))
    assert result.mu_o_cp == pytest.approx(ref["mu_o_cp"], rel=1e-8)


@pytest.mark.parametrize("case_name", ["dak_low", "dak_medium", "dak_high"])
def test_dak_reduced_pressure_cases_match_independent_reference(case_name):
    ref = CASES[case_name]
    result = BlackOilPvtProvider().evaluate(make_state(pressure=ref["inputs"]["pressure_psia"], temperature=ref["inputs"]["temperature_f"], sg_g=0.70, pb=2500.0, rsb=700.0))
    assert result.z_factor == pytest.approx(ref["values"]["z"], rel=1e-8)
    assert result.z_factor > 0


def test_bg_matches_independent_reference_and_unit_identity():
    ref = CASES["dak_medium"]["values"]
    result = BlackOilPvtProvider().evaluate(make_state(pressure=2500.0, temperature=180.0, sg_g=0.70, pb=2500.0, rsb=700.0))
    assert result.bg_rb_scf == pytest.approx(ref["bg_rb_scf"], rel=1e-8)
    assert result.bg_rb_scf * 1000.0 == pytest.approx(ref["bg_rb_mscf"], rel=1e-8)


def test_lge_gas_viscosity_matches_independent_reference():
    ref = CASES["dak_medium"]["values"]
    result = BlackOilPvtProvider().evaluate(make_state(pressure=2500.0, temperature=180.0, sg_g=0.70, pb=2500.0, rsb=700.0))
    assert result.mu_g_cp == pytest.approx(ref["mu_g_cp"], rel=1e-8)


@pytest.mark.parametrize(("pressure", "expected_region"), [(2000.0, "saturated"), (2500.0, "bubble_point"), (3500.0, "undersaturated")])
def test_complete_state_phase_regions(pressure, expected_region):
    result = BlackOilPvtProvider().evaluate(make_state(pressure=pressure, pb=2500.0, rsb=700.0))
    assert result.status == PVTStatus.OK.value
    assert result.phase_region == expected_region
    assert result.rs_scf_stb >= 0
    assert result.bo_rb_stb > 0
    assert result.mu_o_cp > 0
    assert result.z_factor > 0
    assert result.bg_rb_scf > 0
    assert result.mu_g_cp > 0


def test_invalid_input_status():
    result = BlackOilPvtProvider().evaluate(make_state(pressure=-1.0))
    assert result.status == PVTStatus.INVALID_INPUT.value


def test_insufficient_data_status():
    result = BlackOilPvtProvider().evaluate(PvtState(2500.0, 180.0, 35.0, 0.75))
    assert result.status == PVTStatus.INSUFFICIENT_DATA.value


def test_correlation_limitation_status_for_nonhydrocarbons():
    result = BlackOilPvtProvider().evaluate(replace(make_state(), non_hydrocarbon_fraction=0.05))
    assert result.status == PVTStatus.CORRELATION_LIMITATION.value
    assert result.limitations


def test_dak_forced_nonconvergence_status():
    provider = BlackOilPvtProvider()
    old = provider.DAK_MAX_ITERATIONS
    try:
        provider.DAK_MAX_ITERATIONS = 0
        result = provider.evaluate(make_state())
    finally:
        provider.DAK_MAX_ITERATIONS = old
    assert result.status == PVTStatus.NUMERICAL_NON_CONVERGENCE.value


def test_provenance_completeness():
    result = BlackOilPvtProvider().evaluate(make_state())
    required = {"package_version", "pb_model", "rs_model", "bo_model", "compressibility_model", "dead_oil_viscosity_model", "saturated_oil_viscosity_model", "undersaturated_oil_viscosity_model", "pseudo_critical_model", "z_model", "bg_definition", "gas_viscosity_model", "standard_conditions", "source_versions", "validity_warnings"}
    assert required <= result.provenance.keys()


def test_metadata_does_not_alter_numerical_results():
    result = BlackOilPvtProvider().evaluate(make_state())
    altered = replace(result, provenance={"metadata_only": True}, warnings=("metadata-only test",))
    numeric_fields = ("pb_psia", "rs_scf_stb", "bo_rb_stb", "co_1_psi", "mu_o_cp", "z_factor", "bg_rb_scf", "mu_g_cp")
    assert all(getattr(result, field) == getattr(altered, field) for field in numeric_fields)
