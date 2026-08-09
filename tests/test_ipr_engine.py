"""
Deterministic IPR engine tests — Production Engineering Phase 1.

Benchmarks are hand-calculated independently of the implementation:
- Vogel (1968) factor: q/qmax = 1 - 0.2*(Pwf/Pr) - 0.8*(Pwf/Pr)^2
- Composite IPR: Brown, The Technology of Artificial Lift Methods, Vol. 1,
  Ch. 5; Beggs, Production Optimization Using Nodal Analysis, Ch. 3.
"""

from __future__ import annotations

import sys
import unittest

sys.path.insert(0, ".")

from services.production_engine import IPREngine, MODEL_DISPLAY  # noqa: E402

_TOL = 0.2  # engine rounds to 0.1 STB/day


class VogelIPRTests(unittest.TestCase):
    """Vogel IPR (1968) — saturated-oil inflow."""

    def setUp(self):
        self.engine = IPREngine()

    def test_known_factor_half_pr(self):
        # Pwf = Pr/2 -> factor = 1 - 0.1 - 0.2 = 0.7 exactly
        self.assertAlmostEqual(self.engine.vogel_q(3000, 1000, 1500), 700.0, places=1)

    def test_zero_rate_at_pr(self):
        self.assertEqual(self.engine.vogel_q(3000, 1500, 3000), 0.0)

    def test_aof_at_zero_pwf(self):
        self.assertAlmostEqual(self.engine.vogel_q(3000, 1500, 0), 1500.0, places=1)

    def test_benchmark_1200_psia(self):
        # factor = 1 - 0.2*(0.4) - 0.8*(0.16) = 0.792
        self.assertAlmostEqual(self.engine.vogel_q(3000, 1500, 1200), 1188.0, places=1)

    def test_qmax_inversion_from_test_point(self):
        # q_test = 600 STB/day @ Pwf_test = 1500 psia, Pr = 3000 psia
        # factor = 0.7 -> qmax = 600/0.7 = 857.1428...
        qmax = self.engine.vogel_qmax_from_test(3000, 1500, 600)
        self.assertAlmostEqual(qmax, 857.1, places=1)
        # round-trip: rebuilding the curve through the test point
        self.assertAlmostEqual(self.engine.vogel_q(3000, qmax, 1500), 600.0, places=1)

    def test_qmax_inversion_second_point(self):
        # q_test = 720 @ Pwf_test = 1800, Pr = 3000: factor = 1 - 0.12 - 0.288 = 0.592
        qmax = self.engine.vogel_qmax_from_test(3000, 1800, 720)
        self.assertAlmostEqual(qmax, 1216.2, places=1)

    def test_monotonicity(self):
        ps = [3000 - 300 * i for i in range(11)]
        qs = [self.engine.vogel_q(3000, 1500, p) for p in ps]
        self.assertTrue(all(qs[i] <= qs[i + 1] + 1e-9 for i in range(len(qs) - 1)))


class LinearIPRTests(unittest.TestCase):
    """Linear PI / Darcy inflow — undersaturated regime."""

    def setUp(self):
        self.engine = IPREngine()

    def test_known_productivity_index(self):
        self.assertAlmostEqual(self.engine.linear_q(3000, 1.5, 2000), 1500.0, places=1)

    def test_j_from_test_point_roundtrip(self):
        j = self.engine.linear_j(900, 3000, 2400)
        self.assertAlmostEqual(j, 1.5, places=3)
        self.assertAlmostEqual(self.engine.linear_q(3000, j, 1500), 2250.0, places=1)

    def test_zero_rate_at_pr(self):
        self.assertEqual(self.engine.linear_q(3000, 2.0, 3000), 0.0)


class CompositeIPRTests(unittest.TestCase):
    """Composite IPR: linear above Pb, Vogel below Pb, C1-continuous at Pb."""

    def setUp(self):
        self.engine = IPREngine()

    def test_segments_benchmark(self):
        # j* = 900/(3000-2400) = 1.5; qb = 1.5*800 = 1200;
        # qo_max = 1200 + 1200*2200/(1.8*800) = 3033.3
        qb, qo_max = self.engine.composite_segments(3000, 2200, 1.5)
        self.assertAlmostEqual(qb, 1200.0, places=1)
        self.assertAlmostEqual(qo_max, 3033.3, places=1)

    def test_c1_continuity_at_pb(self):
        qb, qo_max = self.engine.composite_segments(3000, 2200, 1.5)
        # linear side at Pb
        q_above = 1.5 * (3000 - 2200)
        # Vogel side at Pb: qb + (qo_max-qb)*[1-0.2-0.8] = qb + 0
        q_below = qb + (qo_max - qb) * (1 - 0.2 * 1.0 - 0.8 * 1.0)
        self.assertAlmostEqual(q_above, q_below, places=6)

    def test_slope_continuity_at_pb(self):
        qb, qo_max = self.engine.composite_segments(3000, 2200, 1.5)
        # Vogel segment slope at Pb: dq/dPwf = -(qo_max-qb)*(0.2+1.6)/Pb
        # With qo_max = qb + qb*Pb/(1.8*(Pr-Pb)) this reduces to -qb/(Pr-Pb) = -J*.
        slope_below = -(qo_max - qb) * 1.8 / 2200
        self.assertAlmostEqual(slope_below, -1.5, places=2)  # equals -J* (places=2 allows rounding of qb/qo_max to 0.1)

    def test_composite_q_benchmark(self):
        # j* = 1.5 from test point; Pwf = 1200 below Pb = 2200
        j_star = self.engine.linear_j(900, 3000, 2400)
        q = self.engine.composite_q(3000, 2200, j_star, 1200)
        self.assertAlmostEqual(q, 2396.9, places=1)

    def test_composite_second_benchmark(self):
        # j* = 0.5 -> qb = 400, qo_max = 1011.1; Pwf = 1200
        q = self.engine.composite_q(3000, 2200, 0.5, 1200)
        self.assertAlmostEqual(q, 799.0, places=1)

    def test_linear_segment_above_pb(self):
        j_star = self.engine.linear_j(900, 3000, 2400)
        q = self.engine.composite_q(3000, 2200, j_star, 2800)
        self.assertAlmostEqual(q, 300.0, places=1)

    def test_zero_rate_at_pr(self):
        q = self.engine.composite_q(3000, 2200, 1.5, 3000)
        self.assertEqual(q, 0.0)

    def test_monotonicity(self):
        j_star = self.engine.linear_j(900, 3000, 2400)
        ps = sorted([3000 - 300 * i for i in range(11)] + [2200], reverse=True)
        qs = [self.engine.composite_q(3000, 2200, j_star, p) for p in ps]
        self.assertTrue(all(qs[i] <= qs[i + 1] + 1e-9 for i in range(len(qs) - 1)))


class ModelSelectionTests(unittest.TestCase):
    """Deterministic CASE A/B/C model selection."""

    def setUp(self):
        self.engine = IPREngine()

    def test_case_a_saturated(self):
        model, _ = self.engine.select_model(1800, 2000, 1200)
        self.assertEqual(model, "vogel")

    def test_case_b_undersaturated_above_pb(self):
        model, _ = self.engine.select_model(3000, 2200, 2500)
        self.assertEqual(model, "linear")

    def test_case_c_crosses_pb(self):
        model, _ = self.engine.select_model(3000, 2200, 1200)
        self.assertEqual(model, "composite")

    def test_curve_mode_no_pb_vogel(self):
        model, _ = self.engine.select_model(3000, None, None)
        self.assertEqual(model, "vogel")

    def test_curve_mode_with_pb_composite(self):
        model, _ = self.engine.select_model(3000, 2200, None)
        self.assertEqual(model, "composite")

    def test_no_pb_point_below_pr_linear(self):
        model, _ = self.engine.select_model(3000, None, 2000)
        self.assertEqual(model, "linear")


class GuardrailTests(unittest.TestCase):
    """Hard-reject rules: PHYSICALLY_INVALID / OUTSIDE_ASSUMPTIONS."""

    def setUp(self):
        self.engine = IPREngine()

    def _expect_invalid(self, fn):
        with self.assertRaises(ValueError) as ctx:
            fn()
        self.assertIn("PHYSICALLY_INVALID", str(ctx.exception))

    def test_negative_pr(self):
        self._expect_invalid(lambda: self.engine.vogel_q(-100, 100, 50))

    def test_pwf_above_pr(self):
        self._expect_invalid(lambda: self.engine.vogel_q(3000, 1500, 4000))

    def test_zero_qmax(self):
        self._expect_invalid(lambda: self.engine.vogel_q(3000, 0, 1200))

    def test_negative_qtest(self):
        self._expect_invalid(lambda: self.engine.vogel_qmax_from_test(3000, 1500, -5))

    def test_test_point_at_pr(self):
        self._expect_invalid(lambda: self.engine.vogel_qmax_from_test(3000, 3000, 5))

    def test_zero_j(self):
        self._expect_invalid(lambda: self.engine.linear_q(3000, 0, 2000))

    def test_negative_pwf(self):
        self._expect_invalid(lambda: self.engine.linear_q(3000, 1.5, -10))

    def test_composite_pb_ge_pr(self):
        with self.assertRaises(ValueError) as ctx:
            self.engine.composite_segments(2000, 2200, 1.0)
        self.assertIn("OUTSIDE_ASSUMPTIONS", str(ctx.exception))

    def test_composite_requires_pb(self):
        with self.assertRaises(ValueError) as ctx:
            self.engine.composite_segments(3000, None, 1.0)
        self.assertIn("INSUFFICIENT_DATA", str(ctx.exception))


class CurveGenerationTests(unittest.TestCase):
    """Engine-built curve points are deterministic and monotonic."""

    def setUp(self):
        self.engine = IPREngine()

    def test_vogel_curve(self):
        qs = self.engine.build_curve("vogel", 3000, qmax=1500)
        self.assertEqual(len(qs), 10)
        self.assertEqual(qs[0], 0.0)
        self.assertTrue(self.engine.monotonicity_check(
            [3000 - 3000 * i / 9 for i in range(10)], qs))

    def test_composite_curve_includes_pb(self):
        ps = self.engine._curve_pressures(3000, include_pb=True, pb=2200)
        self.assertTrue(any(abs(p - 2200) < 0.5 for p in ps))

    def test_unknown_model_raises(self):
        with self.assertRaises(ValueError):
            self.engine.build_curve("fetkovich", 3000, qmax=1500)

    def test_model_display_names_present(self):
        for key in ("vogel", "linear", "composite"):
            self.assertIn(key, MODEL_DISPLAY)


if __name__ == "__main__":
    unittest.main()
