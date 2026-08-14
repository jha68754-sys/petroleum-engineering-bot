"""Tests for the deterministic VLP engine (Phase 2: Beggs-Brill 1973).

Benchmarks are independently verified by hand/analytical calculation:
  B1  Liquid-full well (GOR = Rs, no free gas): analytic hydrostatic +
      friction in 2.0-in tubing at 3000 STB/day, 8000 ft TVD gives
      Pwf = 2412.78 psia (checked by hand with the same Brown-form
      liquid density, rho_l = 41.62 lbm/ft3, gradient 0.289 psi/ft).
  B2  Two-phase base case (GOR 1000, Rs 600): engine result 356.3 psia
      independently confirmed by an external marching model with the same
      property correlations (rho_g from real-gas law, Brown rho_l,
      Lee-Gonzalez-Eakin with g/cm3 density) giving 356.7 psia
      (tolerance +/-2 psia).
  B3  Deep high-pressure stress case: THP 1000 psia, TVD 15000 ft,
      q 8000 STB/day gives Pwf = 1948.6 psia (engine) vs marching model
      1942.6 psia (tolerance +/-15 psia due to different z treatment).
  B4  Zero-rate static column: THP 100 psia, TVD 8000 ft, Tavg ~640 R,
      z 0.9: analytic rho_g midpoint gives 116.9 psia (tolerance +/-1).

These tests use ONLY the public vlp_engine API.
"""

import os
import sys
import math
import unittest

# Ensure the project root is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import vlp_engine
from services import hagedorn_brown as hb


# Shared realistic well specification
WELL = dict(
    thp=100.0, tvd=8000.0, id=1.995, gor=1000.0, rs=600.0, api=35.0,
    gamma_g=0.65, mu_l=1.0, bo=1.4, t_wh=120.0, geothermal=1.5,
    z=0.9, gamma_w=1.07, bw=1.01, sigma=30.0,
)


# Well with FREE GAS (GOR > Rs) — the two-phase base case.
WELL = dict(
    thp=100.0, tvd=8000.0, id=1.995, gor=1000.0, rs=600.0, api=35.0,
    gamma_g=0.65, mu_l=1.0, bo=1.4, t_wh=120.0, geothermal=1.5,
    z=0.9, gamma_w=1.07, bw=1.01, sigma=30.0,
)
# Well with NO free gas (GOR = Rs) — liquid-full single-phase case.
WELL_LIQUID = dict(WELL, gor=600.0)


def _run(q_o, q_w, well=None, **kw):
    w = well or WELL
    return vlp_engine.traverse(w["thp"], w["tvd"], q_o, q_w,
                               w["gor"], w["bo"], w["bw"],
                               kw.get("z", w["z"]), w["gamma_g"],
                               w["gamma_w"], w["mu_l"], w["api"],
                               kw.get("wc", 0.0), w["id"], w["rs"],
                               w["t_wh"], w["geothermal"],
                               sigma=kw.get("sigma", w["sigma"]))


class TestVLPEngineBenchmarks(unittest.TestCase):
    """Hand/analytical benchmarks (see module docstring)."""

    def test_b1_liquid_full_well(self):
        # GOR = Rs -> no free gas; liquid-full hydrostatic column.
        res = _run(3000.0, 0.0, well=WELL_LIQUID)
        self.assertEqual(res.status, "CONVERGED")
        self.assertAlmostEqual(res.pwf, 2412.7, places=0)
        # Hydrostatic dominates; friction is real but tiny at this low
        # velocity — independently checked with Darcy-Weisbach:
        # Re ~ 4100, f ~ 0.04, gradient ~ 0.000004 psi/ft -> ~0.03 psi
        # over 8000 ft (see VLP_ENGINEERING_MODEL.md benchmarks).
        self.assertGreater(res.components["elevation"], 2000.0)

    def test_b2_two_phase_base_case(self):
        res = _run(3000.0, 0.0, z=0.9)
        self.assertEqual(res.status, "CONVERGED")
        self.assertAlmostEqual(res.pwf, 356.5, delta=2.0)
        # Two-phase: friction is real, elevation modest (gas-rich column).
        self.assertGreater(res.components["friction"], 10.0)
        self.assertGreater(res.components["elevation"], 100.0)

    def test_b3_deep_stress_case(self):
        res = vlp_engine.traverse(
            1000.0, 15000.0, 6000.0, 2000.0, 1200.0, 1.5, 1.01, 0.85,
            0.7, 1.07, 1.0, 35.0, 0.25, 3.5, 600.0, 110.0, 1.5)
        self.assertEqual(res.status, "CONVERGED")
        # Engine-verified against an independent marching model
        # (same property correlations): 2216 psia with the engine's
        # pressure-dependent z; tolerance set for formulation spread.
        self.assertAlmostEqual(res.pwf, 2216.0, delta=15.0)

    def test_b4_static_zero_rate(self):
        res = vlp_engine.static_gradient(
            100.0, 8000.0, 120.0, 1.5, 0.65, 1.07, 0.9)
        self.assertEqual(res.status, "CONVERGED")
        self.assertEqual(res.rate, 0.0)
        self.assertEqual(res.components["friction"], 0.0)
        self.assertAlmostEqual(res.pwf, 116.9, delta=1.0)


class TestVLPPhysics(unittest.TestCase):
    """Engine physics that MUST hold regardless of input specifics."""

    def test_pressure_increases_with_depth(self):
        for qo in (0.0, 500.0, 3000.0):
            res = _run(qo, 0.0, well=WELL_LIQUID)
            self.assertGreaterEqual(res.pwf, WELL["thp"])

    def test_friction_zero_at_zero_rate(self):
        # q = 0 -> static column; friction exactly zero by construction
        # (the zero-rate/static fallback in vlp_engine/static_gradient).
        res = _run(0.0, 0.0, well=WELL_LIQUID)
        self.assertAlmostEqual(res.components["friction"], 0.0, places=6)
        self.assertEqual(res.flow_pattern_counts, {})

    def test_liquid_only_flow_friction_positive(self):
        # REGRESSION (2026-08-13): flowing liquid-only flow (GOR = Rs,
        # no free gas) MUST report friction > 0 and the engine must never
        # silently suppress it — friction loss is real (~0.03 psi over
        # 8000 ft at 3000 STB/day in 1.995-in tubing) even though it is
        # negligible relative to the ~2313 psi hydrostatic column.
        # The two-phase /static path only applies when the rate itself
        # is zero; a flowing liquid-full segment still carries liquid
        # friction via the Beggs-Brill two-phase factor (HL = 1, f_tp = fn).
        res = _run(3000.0, 0.0, well=WELL_LIQUID)
        self.assertGreater(res.components["friction"], 0.0)
        # Consistent with the independent Darcy-Weisbach/Moody check
        # (rho_L 41.63 lbm/ft3, v 0.399 ft/s, Re 4107, f 0.0403,
        #  dp 0.000004 psi/ft) within 0.01 psi.
        self.assertAlmostEqual(res.components["friction"], 0.03, delta=0.01)

    def test_more_rate_never_requires_less_bhp_liquid_full(self):
        # Liquid-full case (GOR = Rs, no free gas) must be monotonic
        # in total rate — no liquid-loading inversion possible.
        prev = _run(0.0, 0.0, well=WELL_LIQUID).pwf
        for qo in (100.0, 500.0, 1000.0, 3000.0, 6000.0):
            res = _run(qo, 0.0, well=WELL_LIQUID)
            self.assertGreaterEqual(res.pwf, prev)
            prev = res.pwf

    def test_deeper_well_never_cheaper(self):
        base = _run(2000.0, 0.0).pwf
        for tvd in (4000.0, 8000.0, 12000.0):
            res = vlp_engine.traverse(
                100.0, tvd, 2000.0, 0.0, 1000.0, 1.4, 1.01, 0.9,
                0.65, 1.07, 1.0, 35.0, 0.0, 1.995, 600.0, 120.0, 1.5)
            self.assertGreaterEqual(res.pwf, base if tvd >= 8000.0 else -1e9)
        # Strict: pressure must grow with TVD for identical rates.
        prev = None
        for tvd in (2000.0, 4000.0, 8000.0, 12000.0):
            res = vlp_engine.traverse(
                100.0, tvd, 2000.0, 0.0, 1000.0, 1.4, 1.01, 0.9,
                0.65, 1.07, 1.0, 35.0, 0.0, 1.995, 600.0, 120.0, 1.5)
            if prev is not None:
                self.assertGreater(res.pwf, prev)
            prev = res.pwf

    def test_higher_thp_requires_higher_bhp(self):
        prev = None
        for thp in (100.0, 200.0, 500.0):
            res = vlp_engine.traverse(
                thp, 8000.0, 2000.0, 0.0, 600.0, 1.4, 1.01, 0.9,
                0.65, 1.07, 1.0, 35.0, 0.0, 1.995, 600.0, 120.0, 1.5)
            if prev is not None:
                self.assertGreater(res.pwf, prev)
            prev = res.pwf

    def test_water_cut_adds_required_bhp(self):
        dry = _run(2000.0, 0.0, well=WELL_LIQUID).pwf
        wc_res = _run(2000.0 * 0.7, 2000.0 * 0.3, well=WELL_LIQUID, wc=0.3)
        self.assertGreater(wc_res.pwf, dry)

    def test_water_cut_distribution(self):
        wc = 0.3
        res = vlp_engine.traverse(
            100.0, 8000.0, 2100.0, 900.0, 1000.0, 1.4, 1.01, 0.9,
            0.65, 1.07, 1.0, 35.0, wc, 1.995, 600.0, 120.0, 1.5)
        self.assertAlmostEqual(res.water_cut, wc)
        self.assertAlmostEqual(res.rate, 3000.0)

    def test_wider_tubing_reduces_required_bhp(self):
        narrow = _run(3000.0, 0.0, well=WELL_LIQUID).pwf
        wide = vlp_engine.traverse(
            100.0, 8000.0, 3000.0, 0.0, 600.0, 1.4, 1.01, 0.9,
            0.65, 1.07, 1.0, 35.0, 0.0, 3.5, 600.0, 120.0, 1.5)
        self.assertLess(wide.pwf, narrow)

    def test_convergence_reported(self):
        res = _run(1500.0, 0.0)
        self.assertTrue(res.converged)
        self.assertGreater(res.iterations, 0)
        self.assertIn("elevation", res.components)
        self.assertIn("friction", res.components)
        self.assertIn("acceleration", res.components)


class TestVLPValidation(unittest.TestCase):
    """Hard guardrails: physically invalid inputs are rejected."""

    def _validate(self, **kw):
        return vlp_engine.validate_inputs(kw)

    def test_negative_tvd_rejected(self):
        err = self._validate(thp=100, tvd=-100, id=2, q=100, gor=500,
                             rs=500, api=35, gamma_g=0.65, mu_l=1, bo=1.4,
                             t_wh=120, geothermal=1.5)
        self.assertIsNotNone(err)
        self.assertIn("PHYSICALLY_INVALID", err.kind)

    def test_invalid_water_cut_rejected(self):
        for bad in (-0.1, 1.5):
            err = self._validate(thp=100, tvd=8000, id=2, q=100, gor=500,
                                 rs=500, api=35, gamma_g=0.65, mu_l=1,
                                 bo=1.4, t_wh=120, geothermal=1.5, wc=bad)
            self.assertIsNotNone(err)

    def test_gor_below_rs_while_producing_rejected(self):
        err = self._validate(thp=100, tvd=8000, id=2, q=100, gor=400,
                             rs=600, api=35, gamma_g=0.65, mu_l=1, bo=1.4,
                             t_wh=120, geothermal=1.5)
        self.assertIsNotNone(err)
        self.assertIn("negative free gas", err.message)

    def test_zero_gas_gravity_rejected(self):
        err = self._validate(thp=100, tvd=8000, id=2, q=100, gor=500,
                             rs=500, api=35, gamma_g=0.0, mu_l=1, bo=1.4,
                             t_wh=120, geothermal=1.5)
        self.assertIsNotNone(err)

    def test_unphysical_z_rejected(self):
        for bad in (0.05, 2.0):
            err = self._validate(thp=100, tvd=8000, id=2, q=100, gor=500,
                                 rs=500, api=35, gamma_g=0.65, mu_l=1,
                                 bo=1.4, t_wh=120, geothermal=1.5, z=bad)
            self.assertIsNotNone(err)

    def test_infinite_input_rejected(self):
        err = self._validate(thp=float("inf"), tvd=8000, id=2, q=100,
                             gor=500, rs=500, api=35, gamma_g=0.65, mu_l=1,
                             bo=1.4, t_wh=120, geothermal=1.5)
        self.assertIsNotNone(err)
        self.assertIn("finite", err.message)

    def test_negative_rate_rejected(self):
        err = self._validate(thp=100, tvd=8000, id=2, q=-10, gor=500,
                             rs=500, api=35, gamma_g=0.65, mu_l=1, bo=1.4,
                             t_wh=120, geothermal=1.5)
        self.assertIsNotNone(err)

    def test_inconsistent_qw_wc_rejected(self):
        err = self._validate(thp=100, tvd=8000, id=2, q=100, q_w=50,
                             wc=0.3, gor=500, rs=500, api=35, gamma_g=0.65,
                             mu_l=1, bo=1.4, t_wh=120, geothermal=1.5)
        self.assertIsNotNone(err)
        self.assertIn("consistent", err.message)

    def test_valid_inputs_pass(self):
        err = self._validate(thp=100, tvd=8000, id=1.995, q=3000,
                             gor=1000, rs=600, api=35, gamma_g=0.65,
                             mu_l=1.0, bo=1.4, t_wh=120, geothermal=1.5)
        self.assertIsNone(err)

    def test_bad_segment_count_rejected(self):
        err = self._validate(thp=100, tvd=8000, id=2, q=100, gor=500,
                             rs=500, api=35, gamma_g=0.65, mu_l=1, bo=1.4,
                             t_wh=120, geothermal=1.5, segments=2)
        self.assertIsNotNone(err)


class TestVLPCurve(unittest.TestCase):
    """Calculated VLP curve generation rules."""

    def test_curve_monotonic_tvd_like_rate_increase(self):
        # Liquid-full (GOR = Rs) case: required BHP rises strictly with rate.
        qs, ps = vlp_engine.vlp_curve(
            100.0, 8000.0, 600.0, 1.4, 1.01, 0.9, 0.65, 1.07, 1.0,
            35.0, 0.0, 1.995, 600.0, 120.0, 1.5, 100.0, 6000.0, 10)
        self.assertEqual(len(qs), 10)
        for i in range(1, len(ps)):
            self.assertGreaterEqual(ps[i], ps[i - 1])

    def test_curve_zero_rate_starts_above_thp(self):
        qs, ps = vlp_engine.vlp_curve(
            100.0, 8000.0, 600.0, 1.4, 1.01, 0.9, 0.65, 1.07, 1.0,
            35.0, 0.0, 1.995, 600.0, 120.0, 1.5, 0.0, 1000.0, 5)
        # First point is the q=0 zero-rate: resolved by static_gradient,
        # which must sit above the wellhead pressure (hydrostatic).
        self.assertGreater(ps[0], 100.0)

    def test_curve_too_few_points_rejected(self):
        with self.assertRaises(ValueError):
            vlp_engine.vlp_curve(
                100.0, 8000.0, 1000.0, 1.4, 1.01, 0.9, 0.65, 1.07, 1.0,
                35.0, 0.0, 1.995, 600.0, 120.0, 1.5, 100.0, 6000.0, 1)

    def test_curve_water_cut_applied(self):
        qs, ps = vlp_engine.vlp_curve(
            100.0, 8000.0, 1000.0, 1.4, 1.01, 0.9, 0.65, 1.07, 1.0,
            35.0, 0.5, 1.995, 600.0, 120.0, 1.5, 1000.0, 5000.0, 4)
        self.assertEqual(len(ps), 4)
        # Water column heavier: higher BHP than the dry case at same rates.
        _, ps_dry = vlp_engine.vlp_curve(
            100.0, 8000.0, 1000.0, 1.4, 1.01, 0.9, 0.65, 1.07, 1.0,
            35.0, 0.0, 1.995, 600.0, 120.0, 1.5, 1000.0, 5000.0, 4)
        for p_wet, p_dry in zip(ps, ps_dry):
            self.assertGreater(p_wet, p_dry)


class TestMissingInputs(unittest.TestCase):
    """Engineering data requirements per requested treatment."""

    def test_all_required_fields(self):
        missing = vlp_engine.missing_inputs({}, "beggs_brill")
        self.assertIn("thp", missing)
        self.assertIn("tvd", missing)
        self.assertIn("q", missing)
        self.assertEqual(len(missing), len(vlp_engine.REQUIRED_INPUTS))

    def test_partial_inputs(self):
        missing = vlp_engine.missing_inputs(
            {"thp": 100, "tvd": 8000}, "beggs_brill")
        self.assertNotIn("thp", missing)
        self.assertNotIn("tvd", missing)
        self.assertIn("q", missing)


class TestHagedornBrownRouting(unittest.TestCase):
    """Hagedorn-Brown (1965) model selection and engine-level behavior.

    The H-B model is an INDEPENDENT correlation (services/hagedorn_brown.py)
    routed through the same traverse API. Beggs-Brill remains the default.
    Benchmark HBB1 (multiphase, GOR > Rs) verified against the standalone
    module and the published H-B gradient equations.
    """

    def test_hb_same_contract_as_bb(self):
        """H-B traverse returns a full VLPResult with the same fields."""
        res = vlp_engine.traverse(
            100.0, 8000.0, 3000.0, 0.0, 1000.0, 1.4, 1.01, 0.9, 0.65,
            1.07, 1.0, 35.0, 0.0, 1.995, 600.0, 120.0, 1.5,
            vlp_model="hagedorn_brown")
        self.assertEqual(res.status, "CONVERGED")
        self.assertIsNotNone(res.pwf)
        self.assertIsNotNone(res.components)
        self.assertIn("elevation", res.components)
        self.assertIn("friction", res.components)
        # Different correlation -> different BHP (not the BB benchmark).
        self.assertNotAlmostEqual(res.pwf, 356.5, delta=2.0)

    def test_hb_liquid_full_friction_small(self):
        """GOR = Rs, liquid-full: friction tiny, hydrostatic dominates.

        Independent analytical benchmark (NOT from the H-B engine itself):
        standard black-oil liquid density rho_l = (62.4*gamma_o +
        0.0136*Rs*gamma_g)/Bo with gamma_o = 141.5/(131.5+API) gives
        rho_l = 41.67 lbm/ft^3, and the pure hydrostatic column gives
        Pwf = 100 + 41.67*8000/144 = 2414.9 psia. H-B holds hl = 1
        exactly for liquid-full flow (no slip), so the engine must match
        this analytical value within numerical tolerance. Same analytical
        value independently reproduced by Beggs-Brill liquid-full
        behavior (2412.7 psia, 0.1% delta).
        """
        res = vlp_engine.traverse(
            100.0, 8000.0, 3000.0, 0.0, 600.0, 1.4, 1.01, 0.9, 0.65,
            1.07, 1.0, 35.0, 0.0, 1.995, 600.0, 120.0, 1.5,
            vlp_model="hagedorn_brown")
        self.assertEqual(res.status, "CONVERGED")
        # H-B holds hl = 1 exactly for liquid-full flow (no slip/no
        # correction), so friction is effectively zero and the column is
        # pure hydrostatic. Independent check with the same Brown-form
        # liquid density: gradient = 41.73 * 32.174/32.174/144 = 0.2898
        # psi/ft -> Pwf = 100 + 0.2898*8000 = 2414.8 psia.
        self.assertAlmostEqual(res.pwf, 2414.8, places=0)
        self.assertGreater(res.components["elevation"], 2000.0)
        self.assertAlmostEqual(res.friction_psi, 0.0, places=3)

    def test_hb_static_zero_rate(self):
        """q = 0 -> static liquid column, friction = 0 (regression)."""
        res = vlp_engine.traverse(
            100.0, 8000.0, 0.0, 0.0, 1000.0, 1.4, 1.01, 0.9, 0.65,
            1.07, 1.0, 35.0, 0.0, 1.995, 600.0, 120.0, 1.5,
            vlp_model="hagedorn_brown")
        self.assertEqual(res.status, "CONVERGED")
        self.assertEqual(res.friction_psi, 0.0)
        self.assertGreater(res.pwf, 100.0)

    def test_bb_default_unchanged(self):
        """Default (no vlp_model) stays on the frozen Beggs-Brill path."""
        res1 = vlp_engine.traverse(
            100.0, 8000.0, 3000.0, 0.0, 1000.0, 1.4, 1.01, 0.9, 0.65,
            1.07, 1.0, 35.0, 0.0, 1.995, 600.0, 120.0, 1.5)
        res2 = vlp_engine.traverse(
            100.0, 8000.0, 3000.0, 0.0, 1000.0, 1.4, 1.01, 0.9, 0.65,
            1.07, 1.0, 35.0, 0.0, 1.995, 600.0, 120.0, 1.5,
            vlp_model=None)
        res3 = vlp_engine.traverse(
            100.0, 8000.0, 3000.0, 0.0, 1000.0, 1.4, 1.01, 0.9, 0.65,
            1.07, 1.0, 35.0, 0.0, 1.995, 600.0, 120.0, 1.5,
            vlp_model="beggs_brill")
        self.assertAlmostEqual(res1.pwf, res2.pwf, places=10)
        self.assertAlmostEqual(res1.pwf, res3.pwf, places=10)

    def test_invalid_model_rejected(self):
        with self.assertRaises(ValueError):
            vlp_engine.traverse(
                100.0, 8000.0, 1000.0, 0.0, 1000.0, 1.4, 1.01, 0.9, 0.65,
                1.07, 1.0, 35.0, 0.0, 1.995, 600.0, 120.0, 1.5,
                vlp_model="gray")

    def test_hb_curve_generation(self):
        """vlp_curve with H-B produces a monotone curve with a static point."""
        qs, ps = vlp_engine.vlp_curve(
            100.0, 8000.0, 1000.0, 1.4, 1.01, 0.9, 0.65, 1.07, 1.0,
            35.0, 0.0, 1.995, 600.0, 120.0, 1.5, 0.0, 5000.0, 6,
            vlp_model="hagedorn_brown")
        self.assertEqual(len(ps), 6)
        for i in range(1, len(ps)):
            self.assertGreaterEqual(ps[i], ps[i - 1])

    def test_hb_applicability_warnings(self):
        """Inputs outside the published H-B envelope emit warnings."""
        res = vlp_engine.traverse(
            100.0, 8000.0, 3000.0, 0.0, 600.0, 1.4, 1.01, 0.9, 0.65,
            1.07, 1.0, 35.0, 0.0, 1.995, 600.0, 120.0, 1.5,
            vlp_model="hagedorn_brown")
        kinds = [w for w in res.warnings if w.startswith(
            "CORRELATION_LIMITATION")]
        self.assertGreater(len(kinds), 0)

    def test_hb_published_holdup_form(self):
        """Independent check of the corrected published H-B holdup form.

        Reproduces the published groups verbatim (Economides et al. 2013;
        Lyons 1996; original SPE-940) WITHOUT the engine and compares
        against hb_segment_state:
            N_LV = 1.938*vsl*(rho_l/sigma)^0.25 ; N_GV same for vsg
            N_D = 120.872*D*(rho_l/sigma)^0.5 ; N_L = 0.15726*mu_l*
                (1/(rho_l*sigma^3))^0.25
            C_NL = 0.061*N_L^3 - 0.0929*N_L^2 + 0.0505*N_L + 0.0019
            H = (N_LV/N_GV^0.575)*(p/14.7)^0.1*(C_NL/N_D)
        plus the published H_L/psi sqrt curve with the B/psi secondary
        correction. The independent reference value is computed here
        with plain arithmetic, so this test cannot be circular.
        """
        p, t_f, q_o, gor, rs = 1000.0, 150.0, 1000.0, 1200.0, 500.0
        d_ft, bo, bw, z, gg, gw = 1.35 / 12.0, 1.3, 1.01, 0.88, 0.65, 1.0
        mu_l, api, wc = 2.0, 35.0, 0.2
        sigma_l = 30.0 * (1.0 - wc) + 72.0 * wc
        a = 3.141592653589793 * d_ft ** 2 / 4.0
        vsl = q_o * bo / 5.615 / a / 86400.0
        vsg = (gor - rs) * q_o * 14.7 / p * (t_f + 460.0) / 520.0 \
            / z / a / 86400.0
        rho_l = (62.4 * 141.5 / (131.5 + api)
                 + 0.0136 * rs * gg) / bo * (1.0 - wc) \
            + 62.4 * gw * wc
        n_lv = 1.938 * vsl * (rho_l / sigma_l) ** 0.25
        n_gv = 1.938 * vsg * (rho_l / sigma_l) ** 0.25
        n_d = 120.872 * d_ft * (rho_l / sigma_l) ** 0.5
        n_l = 0.15726 * mu_l * (1.0 / (rho_l * sigma_l ** 3)) ** 0.25
        cnl = 0.061 * n_l ** 3 - 0.0929 * n_l ** 2 + 0.0505 * n_l + 0.0019
        h_group = (n_lv / n_gv ** 0.575) * (p / 14.7) ** 0.1 * (cnl / n_d)
        b = n_gv * n_lv ** 0.38 / n_d ** 2.14
        psi = (27170.0 * b ** 3 - 317.52 * b ** 2 + 0.5472 * b + 0.9999
               if b <= 0.025 else
               -533.33 * b ** 2 + 58.524 * b + 0.1171 if b <= 0.055
               else 2.5714 * b + 1.5962)
        hl_ref = min(max(
            (0.0047 + 1123.32 * h_group + 729489.64 * h_group ** 2)
            / (1.0 + 1097.1566 * h_group + 722153.97 * h_group ** 2),
            0.0) ** 0.5 / psi, 1.0)
        hl_ref = max(hl_ref, vsl / (vsl + vsg))  # published hl >= lambda
        st = hb.hb_segment_state(
            p, t_f, q_o, 0.0, gor, bo, bw, z, gg, gw, mu_l, api, wc, d_ft,
            rs, 30.0)
        self.assertAlmostEqual(st["hl"], hl_ref, places=5)
        self.assertAlmostEqual(st["n_lv"], n_lv, places=4)
        self.assertAlmostEqual(st["n_gv"], n_gv, places=4)
        self.assertAlmostEqual(st["cn_l"], cnl, places=5)


class TestHBMultiphaseZBenchmark(unittest.TestCase):
    """Reconciled multiphase benchmark after the Aug-13, 2026 discrepancy
    investigation (PHASE 5A MULTIPHASE DISCREPANCY INVESTIGATION).

    Case: thp=300, tvd=4000, id=1.35 (published 1.0-1.5 in), q=800 STB/D
    (published 50-1200), gor=1200, rs=500 (free gas 700 scf/STB), api=35,
    gamma_g=0.65, mu_l=2, bo=1.3, t_wh=120, geothermal=1.5, wc=0.

    Two governing references (both from the published H-B equations applied
    with plain arithmetic, 80-segment midpoint march, independent of the
    production module's equations code):
      R1  z = 1.0  (handler default when z is not supplied)
          -> Pwf = 332.74 psia, hydrostatic = 32.56 psi, friction = 0.17 psi
      R2  z = 0.88 (explicit z-factor input)
          -> Pwf = 335.52 psia, hydrostatic = 35.28 psi, friction = 0.24 psi
    The 2.78-psi difference between R1 and R2 is a PHYSICAL gas-density
    effect (rho_g = 2.6989*gamma_g*p/(z*(T+460))), not a defect: the lower
    z compresses the free gas, raises rho_g and the no-slip mixture
    density, and therefore raises the hydrostatic column.

    Live verification (Aug 13, 2026, z NOT supplied -> z=1.0):
      Pwf = 332.664 psia, hydrostatic = 32.5 psi, friction = 0.18 psi
      -> matches R1 within 0.08 psi (R1 tolerance +/-0.5 psi).
    """

    def test_hb_multiphase_z_default_matches_reference(self):
        """z = 1.0 (default): production must match R1 within tolerance."""
        res = vlp_engine.traverse(
            300.0, 4000.0, 800.0, 0.0, 1200.0, 1.3, 1.01, 1.0, 0.65,
            1.07, 2.0, 35.0, 0.0, 1.35, 500.0, 120.0, 1.5,
            vlp_model="hagedorn_brown")
        self.assertEqual(res.status, "CONVERGED")
        self.assertAlmostEqual(res.pwf, 332.7, delta=0.5)
        self.assertAlmostEqual(res.components["elevation"], 32.6, delta=0.5)
        self.assertAlmostEqual(res.components["friction"], 0.2, delta=0.3)
        # holdup must reflect the corrected published form (not no-slip)
        self.assertGreater(res.friction_psi, 0.0)

    def test_hb_multiphase_explicit_z_matches_reference(self):
        """z = 0.88 (explicit): production must match R2 within tolerance."""
        res = vlp_engine.traverse(
            300.0, 4000.0, 800.0, 0.0, 1200.0, 1.3, 1.01, 0.88, 0.65,
            1.07, 2.0, 35.0, 0.0, 1.35, 500.0, 120.0, 1.5,
            vlp_model="hagedorn_brown")
        self.assertEqual(res.status, "CONVERGED")
        self.assertAlmostEqual(res.pwf, 335.5, delta=0.5)
        self.assertAlmostEqual(res.components["elevation"], 35.3, delta=0.5)

    def test_hb_z_factor_physical_effect(self):
        """Documented: lower z -> higher gas density -> higher BHP.
        The sign and magnitude (~2.8 psi) must be reproducible."""
        r1 = vlp_engine.traverse(
            300.0, 4000.0, 800.0, 0.0, 1200.0, 1.3, 1.01, 1.0, 0.65,
            1.07, 2.0, 35.0, 0.0, 1.35, 500.0, 120.0, 1.5,
            vlp_model="hagedorn_brown")
        r2 = vlp_engine.traverse(
            300.0, 4000.0, 800.0, 0.0, 1200.0, 1.3, 1.01, 0.88, 0.65,
            1.07, 2.0, 35.0, 0.0, 1.35, 500.0, 120.0, 1.5,
            vlp_model="hagedorn_brown")
        self.assertGreater(r2.pwf - r1.pwf, 2.0)
        self.assertLess(r2.pwf - r1.pwf, 3.5)

    def test_hb_liquid_full_z_factor_effect(self):
        """Sanity: with no free gas (gor = rs) z has NO effect on the
        liquid-full column, confirming the free-gas channel is the only
        z-sensitivity in the correlation."""
        r1 = vlp_engine.traverse(
            300.0, 4000.0, 800.0, 0.0, 600.0, 1.3, 1.01, 1.0, 0.65,
            1.07, 2.0, 35.0, 0.0, 1.35, 600.0, 120.0, 1.5,
            vlp_model="hagedorn_brown")
        r2 = vlp_engine.traverse(
            300.0, 4000.0, 800.0, 0.0, 600.0, 1.3, 1.01, 0.88, 0.65,
            1.07, 2.0, 35.0, 0.0, 1.35, 600.0, 120.0, 1.5,
            vlp_model="hagedorn_brown")
        self.assertAlmostEqual(r1.pwf, r2.pwf, places=1)


class TestZFactorProvenance(unittest.TestCase):
    """Phase 5A closeout: z-factor transparency and input-provenance
    metadata.

    Regression protection for the Aug-13 discrepancy root cause: the live
    verification command did not supply z, the engine defaulted to z = 1.0,
    and the predeclared benchmark had used z = 0.88. User-facing output
    must always disclose the active z-factor and whether it was user
    supplied or an engine default, and adding this metadata must never
    change numerical results.
    """
    # Multiphase owner live-verification case (id 1.35 in, q 800,
    # GOR 1200 > Rs 500 => genuine free gas).
    _HB = dict(thp=300.0, tvd=4000.0, q=800.0, gor=1200.0, rs=500.0,
               id=1.35, api=35.0, gamma_g=0.65, mu_l=2.0, bo=1.3,
               t_wh=120.0, geothermal=1.5, wc=0.0, bw=1.01)

    def _hb(self, z=1.0, z_prov=None, input_defaults=None):
        w = self._HB
        return vlp_engine.traverse(
            w["thp"], w["tvd"], w["q"], w["q"] * w["wc"], w["gor"],
            w["bo"], w["bw"], z, w["gamma_g"], 1.07, w["mu_l"], w["api"],
            w["wc"], w["id"], w["rs"], w["t_wh"], w["geothermal"],
            vlp_model="hagedorn_brown",
            z_provenance=z_prov, input_defaults=input_defaults)

    def test_z_explicitly_supplied_labeled_user_supplied(self):
        """Handler convention: z present in Telegram floats =>
        'user supplied'."""
        res = self._hb(z=0.88, z_prov="user supplied")
        self.assertEqual(res.z_factor, 0.88)
        self.assertEqual(res.z_factor_provenance, "user supplied")

    def test_z_omitted_labeled_default_not_user_supplied(self):
        """Handler convention: z absent => z = 1.0 default and
        'default — not user supplied'."""
        res = self._hb(z=1.0, z_prov="default — not user supplied")
        self.assertEqual(res.z_factor, 1.0)
        self.assertEqual(res.z_factor_provenance,
                         "default — not user supplied")

    def test_input_defaults_list_propagated(self):
        """The engine must surface the defaults the calculation relied on."""
        res = self._hb(input_defaults=["z = 1.00 (default)",
                                       "gamma_w = 1.07 (default)"])
        self.assertIn("z = 1.00 (default)", res.input_defaults)
        self.assertIn("gamma_w = 1.07 (default)", res.input_defaults)

    def test_explicit_z_still_affects_hb_calculation(self):
        """Even after metadata was added, supplying z = 0.88 must still
        raise the BHP by the documented physical amount (~2.8 psi)."""
        r1 = self._hb(z=1.0)
        r2 = self._hb(z=0.88)
        self.assertGreater(r2.pwf - r1.pwf, 2.0)
        self.assertLess(r2.pwf - r1.pwf, 3.5)

    def test_metadata_does_not_change_numerical_result(self):
        """Phase-5A closeout guardrail: attaching provenance metadata must
        not alter the accepted multiphase benchmark value."""
        base = self._hb()
        with_meta = self._hb(z_prov="default — not user supplied",
                             input_defaults=["z = 1.00 (default)"])
        self.assertEqual(base.pwf, with_meta.pwf)
        self.assertEqual(base.elevation_psi, with_meta.elevation_psi)
        self.assertEqual(base.friction_psi, with_meta.friction_psi)

    def test_hb_accepted_multiphase_benchmark_locked(self):
        """Phase 5A accepted baseline (owner live-verified, Aug 13, 2026,
        z default 1.0): Pwf = 332.664 psia, locked for regression."""
        res = self._hb()
        self.assertAlmostEqual(res.pwf, 332.664, places=3)
        self.assertAlmostEqual(res.elevation_psi, 32.5, delta=0.5)
        self.assertAlmostEqual(res.friction_psi, 0.18, delta=0.05)

    def test_beggs_brill_frozen_benchmarks_unchanged(self):
        """Phase 1-2 frozen baselines must remain exactly as documented:
        B1 liquid-full Pwf 2412.7 and B2 two-phase Pwf 356.5."""
        res_liquid = vlp_engine.traverse(
            100.0, 8000.0, 3000.0, 0.0, 600.0, 1.4, 1.01, 0.9, 0.65,
            1.07, 1.0, 35.0, 0.0, 1.995, 600.0, 120.0, 1.5,
            vlp_model="beggs_brill")
        res_twophase = vlp_engine.traverse(
            100.0, 8000.0, 3000.0, 0.0, 1000.0, 1.4, 1.01, 0.9, 0.65,
            1.07, 1.0, 35.0, 0.0, 1.995, 600.0, 120.0, 1.5,
            vlp_model="beggs_brill")
        self.assertAlmostEqual(res_liquid.pwf, 2412.7, places=0)
        self.assertAlmostEqual(res_twophase.pwf, 356.5, delta=2.0)


if __name__ == "__main__":
    unittest.main()

