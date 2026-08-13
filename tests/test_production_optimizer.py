"""Tests for the deterministic Phase-4 sensitivity & optimization layer.

`services.production_optimizer.ProductionOptimizer` contains NO equations:
all IPR/VLP/nodal mathematics is delegated to the verified Phase 1-3 engines.
This suite verifies the orchestration layer (base case, sweeps, deltas,
feasibility classification, constraints) plus the Telegram handler's
validation and duplicate-key parsing.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('TELEGRAM_BOT_TOKEN', 'dummy')
os.environ.setdefault('OPENAI_API_KEY', 'dummy')
os.environ.setdefault('GROQ_API_KEY', 'dummy')

from services import production_optimizer as po
from services import nodal_engine
from handlers import text_handlers as th


BASE_IPR = {"ipr_model": "linear", "pr": 3000.0, "pb": None, "j": 1.5,
            "j_star": None, "qmax": None, "q_test": None, "pwf_test": None}
BASE_VLP = {"thp": 100.0, "tvd": 8000.0, "tubing_id_in": 1.995,
            "gor": 1000.0, "rs": 600.0, "api": 35.0, "gamma_g": 0.65,
            "mu_l": 1.0, "bo": 1.4, "t_wh": 120.0, "geothermal": 1.5}

# Phase-3 benchmark operating point for the same inputs, re-verified
# after the Phase-5A root-acceptance tightening (bracketed bisection now
# refines to pressure_tol/10, so the endpoint residual is tighter and the
# operating point reports q = 3944.20 STB/D, pwf = 370.53 psia).
BENCH_Q, BENCH_PWF = 3944.20, 370.53


class TestOptimizerBaseCase(unittest.TestCase):
    """The base case must reproduce the standalone nodal solver exactly."""

    def setUp(self):
        self.opt = po.ProductionOptimizer()

    def test_base_case_reproduces_nodal_benchmark(self):
        r = self.opt.sensitivity("thp", explicit_values=[100.0],
                                 base_kwargs=BASE_VLP, ipr_kwargs=BASE_IPR)
        bp = r.base_point
        self.assertEqual(bp.nodal.status,
                         "UNIQUE_OPERATING_POINT")
        self.assertAlmostEqual(bp.q_op, BENCH_Q, places=0)
        self.assertAlmostEqual(bp.pwf_op, BENCH_PWF, places=0)

    def test_classification_feasible_for_unique_root(self):
        r = self.opt.sensitivity("thp", explicit_values=[100.0],
                                 base_kwargs=BASE_VLP, ipr_kwargs=BASE_IPR)
        self.assertEqual(r.base_point.classification, po.FEASIBLE)

    def test_base_value_selection_first_candidate(self):
        r = self.opt.sensitivity("thp", explicit_values=[100.0, 200.0, 300.0],
                                 base_kwargs=BASE_VLP, ipr_kwargs=BASE_IPR)
        self.assertAlmostEqual(r.base_point.pwf_op, BENCH_PWF, places=0)

    def test_explicit_base_value_override(self):
        r = self.opt.sensitivity("thp", explicit_values=[200.0, 300.0],
                                 base_value=100.0, base_kwargs=BASE_VLP,
                                 ipr_kwargs=BASE_IPR)
        self.assertAlmostEqual(r.base_point.q_op, BENCH_Q, places=0)


class TestOptimizerSensitivity(unittest.TestCase):
    def setUp(self):
        self.opt = po.ProductionOptimizer()

    def test_thp_monotonicity(self):
        """Lower THP must release backpressure -> higher operating rate."""
        r = self.opt.sensitivity("thp",
                                 explicit_values=[100.0, 200.0, 300.0],
                                 base_kwargs=BASE_VLP, ipr_kwargs=BASE_IPR)
        qs = [p.q_op for p in r.points]
        self.assertEqual(len(qs), 3)
        self.assertTrue(qs[0] > qs[1] > qs[2] > 0)

    def test_tubing_id_monotonicity(self):
        r = self.opt.sensitivity("tubing_id",
                                 explicit_values=[1.995, 2.5, 3.0],
                                 base_kwargs=BASE_VLP, ipr_kwargs=BASE_IPR)
        qs = [p.q_op for p in r.points]
        self.assertTrue(qs[0] < qs[1] < qs[2])

    def test_water_cut_degrades_rate(self):
        r = self.opt.sensitivity("water_cut",
                                 explicit_values=[0.0, 0.5, 1.0],
                                 base_kwargs=BASE_VLP, ipr_kwargs=BASE_IPR)
        qs = [p.q_op for p in r.points]
        self.assertTrue(qs[0] >= qs[1] >= qs[2])

    def test_deltas_versus_base(self):
        r = self.opt.sensitivity("thp",
                                 explicit_values=[100.0, 200.0],
                                 base_kwargs=BASE_VLP, ipr_kwargs=BASE_IPR)
        b, d = r.base_point, r.deltas[1]
        self.assertAlmostEqual(d.dq, r.points[1].q_op - b.q_op, places=6)
        self.assertAlmostEqual(d.dq_pct, 100.0 * d.dq / b.q_op, places=4)
        self.assertAlmostEqual(d.dpwf, r.points[1].pwf_op - b.pwf_op, places=6)

    def test_range_sweep(self):
        r = self.opt.sensitivity("thp", lo=100.0, hi=300.0, n_points=3,
                                 base_kwargs=BASE_VLP, ipr_kwargs=BASE_IPR)
        self.assertEqual(len(r.points), 3)
        self.assertAlmostEqual(r.points[0].pwf_op, BENCH_PWF, places=0)

    def test_range_degenerate_raises(self):
        with self.assertRaises(po.OptimizationError):
            self.opt.sensitivity("thp", lo=300.0, hi=100.0,
                                 base_kwargs=BASE_VLP, ipr_kwargs=BASE_IPR)


class TestOptimizerConstraints(unittest.TestCase):
    def setUp(self):
        self.opt = po.ProductionOptimizer()

    def _run(self, **kw):
        constraints = kw.pop("constraints", None)
        return self.opt.optimize("tubing_id",
                                 values=[1.995, 2.5, 3.0],
                                 base_kwargs=BASE_VLP, ipr_kwargs=BASE_IPR,
                                 constraints=constraints, **kw)

    def test_best_feasible_is_largest_tubing(self):
        r = self._run(objective="max_oil_rate")
        self.assertEqual(r.best.parameter_value, 3.0)

    def test_constraint_eliminates_best(self):
        r = self._run(objective="max_oil_rate",
                      constraints={"max_liquid_rate": 4000.0})
        self.assertEqual(r.best.parameter_value, 2.5)

    def test_all_infeasible(self):
        r = self._run(objective="max_oil_rate",
                      constraints={"min_pwf": 10000.0})
        self.assertIsNone(r.best)
        self.assertTrue(r.all_infeasible)

    def test_infeasible_candidate_still_reported(self):
        r = self._run(objective="max_oil_rate",
                      constraints={"min_pwf": 1000.0})
        statuses = [c.classification for c in r.candidates]
        self.assertIn(po.INFEASIBLE, statuses)

    def test_single_candidate_rejected(self):
        with self.assertRaises(po.OptimizationError):
            self.opt.optimize("tubing_id",
                              values=[2.5],
                              base_kwargs=BASE_VLP, ipr_kwargs=BASE_IPR,
                              objective="max_oil_rate")

    def test_unknown_objective_rejected(self):
        with self.assertRaises(po.OptimizationError):
            self._run(objective="min_cost")

    def test_drawdown_constraint_feasibility(self):
        r = self._run(objective="max_oil_rate",
                      constraints={"max_drawdown": 0.10})
        for c in r.candidates:
            if c.classification == po.FEASIBLE:
                dd = (BASE_IPR["pr"] - c.point.pwf_op) / BASE_IPR["pr"]
                self.assertLessEqual(dd, 0.10 + 1e-9)


class TestOptimizerGuardrails(unittest.TestCase):
    def setUp(self):
        self.opt = po.ProductionOptimizer()

    def test_negative_thp_rejected(self):
        with self.assertRaises(po.OptimizationError) as cm:
            self.opt.sensitivity("thp", explicit_values=[-10.0],
                                 base_kwargs=BASE_VLP, ipr_kwargs=BASE_IPR)
        self.assertEqual(cm.exception.kind, "PHYSICALLY_INVALID")

    def test_water_cut_out_of_range_rejected(self):
        with self.assertRaises(po.OptimizationError) as cm:
            self.opt.sensitivity("water_cut", explicit_values=[-0.1],
                                 base_kwargs=BASE_VLP, ipr_kwargs=BASE_IPR)
        self.assertEqual(cm.exception.kind, "PHYSICALLY_INVALID")

    def test_unknown_variable_rejected(self):
        with self.assertRaises(po.OptimizationError):
            self.opt.sensitivity("choke_size",
                                 explicit_values=[1.0],
                                 base_kwargs=BASE_VLP, ipr_kwargs=BASE_IPR)


class TestHandlerValidation(unittest.TestCase):
    BASE = ("model=linear pr=3000 j=1.5 thp=100 tvd=8000 id=1.995 gor=1000 "
            "rs=600 api=35 gamma_g=0.65 mu_l=1 bo=1.4 t_wh=120 "
            "geothermal=1.5")

    def _s(self, text):
        return th.handle_calc_sensitivity({"text": text}, None)

    def _o(self, text):
        return th.handle_calc_optimize({"text": text}, None)

    def test_sensitivity_full_flow(self):
        t, png, _ = self._s(f"/calc sensitivity type=thp thp=100,200 "
                            f"{self.BASE}")
        self.assertIn("THP Sensitivity Result", t)
        self.assertIn("3944.20", t)
        self.assertIsNone(png)

    def test_missing_type(self):
        t, _, _ = self._s(f"/calc sensitivity thp=100,200 {self.BASE}")
        self.assertTrue(t.startswith("Error:"))

    def test_missing_vlp_key(self):
        t, _, _ = self._s("/calc sensitivity type=thp thp=100,200 "
                          "model=linear pr=3000 j=1.5 tvd=8000 "
                          "gor=1000 rs=600 api=35 gamma_g=0.65 mu_l=1 "
                          "bo=1.4 t_wh=120 geothermal=1.5")
        self.assertIn("missing data", t)

    def test_optimize_full_flow(self):
        t, png, _ = self._o(f"/calc optimize type=id id=1.995,2.5,3.0 plot=1 "
                            f"objective=max_oil_rate {self.BASE}")
        self.assertIn("BEST FEASIBLE CANDIDATE", t)
        self.assertIsNotNone(png)

    def test_optimize_missing_objective(self):
        t, _, _ = self._o(f"/calc optimize type=id id=1.995,2.5 "
                          f"{self.BASE}")
        self.assertIn("objective=", t)

    def test_optimize_single_candidate(self):
        t, _, _ = self._o(f"/calc optimize type=id id=1.995 "
                          f"objective=max_oil_rate {self.BASE}")
        self.assertIn("at least two values", t)

    def test_duplicate_key_list_wins(self):
        """type=id with both an id list and a plain id token: list wins."""
        t, _, _ = self._o(f"/calc optimize type=id id=1.995,2.5,3.0 plot=1 "
                          f"objective=max_oil_rate {self.BASE} id=1.995")
        self.assertIn("BEST FEASIBLE CANDIDATE", t)

    def test_invalid_value_guardrail(self):
        t, _, _ = self._s(f"/calc sensitivity type=wc wc=-0.1,0.5 "
                          f"{self.BASE}")
        self.assertIn("rejected as physically invalid", t)

    def test_calc_dispatch(self):
        """The /calc dispatcher must route sensitivity correctly."""
        t, _, _ = th.handle_calc(
            {"text": f"/calc sensitivity type=thp thp=100,200 {self.BASE}"},
            None)
        self.assertIn("THP Sensitivity Result", t)


class TestHagedornBrownModelSelection(unittest.TestCase):
    """Phase 5A: sensitivity and optimization must honor vlp_model and
    route every calculation through the independent H-B correlation while
    preserving the frozen Beggs-Brill defaults.

    The H-B outflow is materially different (lower liquid holdup and
    friction), so the operating points must NOT match the BB baseline.
    """

    def setUp(self):
        self.base = ("pr=3000 j=5 qmax=5000 thp=100 tvd=8000 id=1.995 "
                     "gor=1000 rs=600 api=35 gamma_g=0.65 mu_l=1 bo=1.4 "
                     "t_wh=120 geothermal=1.5 wc=0.2")

    def test_sensitivity_uses_hb(self):
        t, _, _ = th.handle_calc_sensitivity(
            {"text": f"/calc sensitivity type=thp thp=100,200 "
                     f"model=auto {self.base} vlp_model=hagedorn_brown"},
            None)
        self.assertIn("Sensitivity Result", t)
        self.assertIn("hagedorn_brown", t)

    def test_sensitivity_hb_differs_from_bb(self):
        t_bb, _, _ = th.handle_calc_sensitivity(
            {"text": f"/calc sensitivity type=thp thp=100,200 "
                     f"model=auto {self.base} vlp_model=beggs_brill"},
            None)
        t_hb, _, _ = th.handle_calc_sensitivity(
            {"text": f"/calc sensitivity type=thp thp=100,200 "
                     f"model=auto {self.base} vlp_model=hagedorn_brown"},
            None)
        # The base case operating point must differ between correlations.
        bb = [l for l in t_bb.splitlines() if "q_op = " in l][0]
        hb = [l for l in t_hb.splitlines() if "q_op = " in l][0]
        self.assertNotEqual(bb, hb)

    def test_optimize_uses_hb(self):
        t, png, _ = th.handle_calc_optimize(
            {"text": f"/calc optimize type=thp thp=100,200,300 "
                     f"objective=max_oil_rate model=auto "
                     f"{self.base} vlp_model=hagedorn_brown plot=1"},
            None)
        self.assertIn("hagedorn_brown", t)
        self.assertIsNotNone(png)

    def test_vlp_model_invalid_rejected(self):
        t, _, _ = th.handle_calc_sensitivity(
            {"text": f"/calc sensitivity type=thp thp=100,200 "
                     f"model=auto {self.base} vlp_model=gray"},
            None)
        self.assertTrue(t.startswith("Error:"))


class TestParameterUnitFormatting(unittest.TestCase):
    """Parameter labels must use explicit per-parameter unit metadata:
    tubing ID in "in", water cut dimensionless/percent, THP in psia.
    Never formatted with a generic pressure unit."""

    def test_tubing_id_renders_in_not_psia(self):
        text, _, _ = th.handle_calc_sensitivity(
            {"text": f"/calc sensitivity type=id id=1.995,2.5,3.0 "
                     f"model=linear {self.base}"}, None)
        self.assertIn("id = 1.995 in", text)
        # :g formatting drops trailing zeros (2.5 in, 3 in)
        self.assertIn("in", text)
        self.assertNotIn("id = 1.995 psia", text)
        for line in text.splitlines():
            if line.strip().startswith("id ="):
                self.assertNotIn("psia", line)

    def test_water_cut_renders_dimensionless_percent(self):
        text, _, _ = th.handle_calc_sensitivity(
            {"text": f"/calc sensitivity type=wc wc=0,0.5,1 "
                     f"model=linear {self.base}"}, None)
        # BASE CASE line uses the 'wc =' prefix; scenario lines use the
        # plain dimensionless label. Both must stay free of psia.
        self.assertIn("wc = 0.00 (0%)", text)
        self.assertIn("  0.50 (50%):", text)
        self.assertIn("  1.00 (100%):", text)
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("wc ="):
                # BASE CASE label: 'wc = 0.00 (0%)' ends with ')'
                self.assertRegex(stripped, r"^wc = .* \([0-9]+%\)$")
            elif stripped.startswith(("0.00 (", "0.50 (", "1.00 (")):
                # Scenario label ends with ')' before the ': q = ...'
                self.assertTrue(stripped.startswith("0.00 (0%):")
                                or stripped.startswith("0.50 (50%):")
                                or stripped.startswith("1.00 (100%):"))

    def test_thp_renders_psia(self):
        text, _, _ = th.handle_calc_sensitivity(
            {"text": f"/calc sensitivity type=thp thp=100,200,300 "
                     f"model=linear {self.base}"}, None)
        # BASE CASE line uses the 'thp =' prefix
        self.assertIn("thp = 100 psia", text)
        self.assertIn("q = 3944.20", text)
        self.assertIn("q = 3745.70", text)
        self.assertIn("q = 3534.30", text)

    def test_verified_thp_sensitivity_values(self):
        """Live-verified deterministic THP sweep benchmarks
        (Telegram verification 2026-08-13)."""
        text, _, _ = th.handle_calc_sensitivity(
            {"text": f"/calc sensitivity type=thp thp=100,200,300 "
                     f"model=linear {self.base}"}, None)
        self.assertIn("q = 3944.20", text)   # THP 100 psia
        self.assertIn("q = 3745.70", text)   # THP 200 psia
        self.assertIn("q = 3534.30", text)   # THP 300 psia

    def test_all_infeasible_never_yields_best(self):
        text, _, _ = th.handle_calc_optimize(
            {"text": f"/calc optimize type=id id=1.995,2.5,3.0 "
                     f"objective=max_oil_rate min_pwf=10000 "
                     f"model=linear {self.base}"}, None)
        self.assertIn("ALL CANDIDATES INFEASIBLE", text)
        self.assertNotIn("BEST FEASIBLE CANDIDATE", text)

    def setUp(self):
        self.base = ("pr=3000 j=1.5 thp=100 tvd=8000 id=1.995 gor=1000 "
                     "rs=600 api=35 gamma_g=0.65 mu_l=1 bo=1.4 t_wh=120 "
                     "geothermal=1.5")
