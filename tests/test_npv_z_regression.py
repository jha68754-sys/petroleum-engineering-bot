# Regression test: NPV comma-separated parsing + Z-factor validation consistency
# (Aug 8, 2026 — reproduction of exact production Telegram commands)
import os
import re
import sys
import unittest

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "dummy")
os.environ.setdefault("GROQ_API_KEY", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.calculation_engine import parse_kv_args
from services.pvt_engine import run_exact_calculation, run_correlation


def get_result(output: str) -> float:
    return float(re.search(r"RESULT: ([\d.-]+)", output).group(1))


class TestNpvZRegression(unittest.TestCase):

    def test_npv_telegram_command_parses_cf_list(self):
        kw = parse_kv_args("cf=-1000000,300000,350000,400000 rate=0.1")
        self.assertEqual(
            kw,
            {"cf": [-1000000.0, 300000.0, 350000.0, 400000.0], "rate": 0.1},
        )

    def test_npv_true_multi_period_value(self):
        kw = parse_kv_args("cf=-1000000,300000,350000,400000 rate=0.1")
        r = run_exact_calculation("npv", kw)
        res = get_result(r)
        expected = sum(c / 1.1 ** t for t, c in enumerate(
            [-1000000.0, 300000.0, 350000.0, 400000.0]))
        self.assertAlmostEqual(res, expected, places=3)

    def test_npv_negative_and_positive_cf_accepted(self):
        r = run_exact_calculation("npv", parse_kv_args(
            "cf=-500,-200,100,400,800 rate=0.1"))
        self.assertIn("RESULT:", r)

    def test_npv_malformed_trailing_comma_reports_missing(self):
        r = run_exact_calculation("npv", parse_kv_args("cf=1000, rate=0.1"))
        self.assertIn("Missing", r)

    def test_npv_malformed_non_numeric_reports_missing(self):
        r = run_exact_calculation("npv", parse_kv_args("cf=abc,def rate=0.1"))
        self.assertIn("Missing", r)

    def test_npv_single_value_uses_pv(self):
        r = run_exact_calculation("npv", parse_kv_args("cf=1000 rate=0.1"))
        self.assertIn("Invalid", r)

    def test_z_valid_regression(self):
        r = run_correlation("z_standing_katz", parse_kv_args("ppr=2 tpr=1.5"))
        z = float(re.search(r"ESTIMATED: ([\d.]+)", r).group(1))
        self.assertAlmostEqual(z, 0.8215, places=3)

    def test_z_rejects_ppr_le_zero(self):
        for args in ("ppr=-1 tpr=1.5", "ppr=0 tpr=1.5", "ppr=0 tpr=0"):
            r = run_correlation("z_standing_katz", parse_kv_args(args))
            self.assertTrue(r.startswith("REJECTED:"), args)
            self.assertIn("Ppr must be > 0", r)
            self.assertIn("Tpr must be > 0", r)

    def test_z_rejects_tpr_le_zero(self):
        r = run_correlation("z_standing_katz", parse_kv_args("ppr=2 tpr=0"))
        self.assertTrue(r.startswith("REJECTED:"))
        self.assertIn("Tpr must be > 0", r)

    def test_z_uses_strictly_positive_conditions(self):
        """Message consistency: both conditions must state '> 0'."""
        r = run_correlation("z_standing_katz", parse_kv_args("ppr=-1 tpr=1.5"))
        self.assertIn("Ppr must be > 0", r)
        self.assertNotIn("Ppr must be >= 0", r)


if __name__ == "__main__":
    unittest.main()
