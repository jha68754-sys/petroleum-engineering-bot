# Regression test for the 7 engineering corrections (Aug 8, 2026)
import os, re, sys
import unittest

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "dummy")
os.environ.setdefault("GROQ_API_KEY", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.pvt_engine import run_exact_calculation, run_correlation


class TestEngineeringCorrections(unittest.TestCase):
    """Fixes: OGIP Bg unit, Vasquez-Beggs t_sep required, DAK hard-reject,
    PV vs NPV separation, mud-weight safety note, ENGINE-FIRST routing,
    specific validation messages."""

    def test_ogip_default_bg_ft3_scf(self):
        r = run_exact_calculation("ogip", {"area":1000,"h":50,"phi":0.2,"sw":0.3,"bg":0.003})
        res = float(re.search(r"RESULT: ([\d.eE+-]+)", r).group(1))
        self.assertAlmostEqual(res, 43560*1000*50*0.2*0.7/0.003, delta=1)

    def test_ogip_rb_scf_via_bg_rb(self):
        r = run_exact_calculation("ogip", {"area":1000,"h":50,"phi":0.2,"sw":0.3,"bg":0.003,"bg_rb":"1"})
        res = float(re.search(r"RESULT: ([\d.eE+-]+)", r).group(1))
        self.assertAlmostEqual(res, 7758*1000*50*0.2*0.7/0.003, delta=1)
        self.assertIn("7758", r)

    def test_vasquez_beggs_requires_t_sep(self):
        r = run_correlation("pb_vasquez_beggs", {"rs":650,"gas_sg":0.75,"tres":180,"api":35,"p_sep":150})
        self.assertIn("Missing", r)

    def test_vasquez_beggs_works_with_t_sep(self):
        r = run_correlation("pb_vasquez_beggs", {"rs":650,"gas_sg":0.75,"tres":180,"api":35,"p_sep":150,"t_sep":100})
        self.assertIn("ESTIMATED:", r)

    def test_dak_rejects_negative_ppr(self):
        r = run_correlation("z_standing_katz", {"tpr":1.5,"ppr":-1})
        self.assertTrue(r.startswith("REJECTED:"), r)

    def test_dak_rejects_nonpositive_tpr(self):
        r = run_correlation("z_standing_katz", {"tpr":0,"ppr":1})
        self.assertTrue(r.startswith("REJECTED:"), r)

    def test_dak_ppr_zero_is_ideal_gas(self):
        r = run_correlation("z_standing_katz", {"tpr":1.5,"ppr":0})
        self.assertTrue(r.startswith("REJECTED:"), r)
        self.assertIn("Ppr must be > 0", r)
        self.assertIn("Tpr must be > 0", r)

    def test_pv_vs_npv_separation(self):
        r_pv = run_exact_calculation("pv", {"cf":1000,"rate":0.1,"t":5})
        self.assertAlmostEqual(float(re.search(r"RESULT: ([\d.]+)", r_pv).group(1)), 1000/1.1**5, places=3)
        r_npv = run_exact_calculation("npv", {"cf":[-1000000.0,300000.0,350000.0,400000.0],"rate":0.1})
        exp = -1e6 + 300e3/1.1 + 350e3/1.1**2 + 400e3/1.1**3
        self.assertAlmostEqual(float(re.search(r"RESULT: ([\d.-]+)", r_npv).group(1)), exp, delta=1)
        r_bad = run_exact_calculation("npv", {"cf":"1000","rate":0.1})
        self.assertIn("Invalid", r_bad)

    def test_mud_weight_no_overbalance_prescription(self):
        r = run_exact_calculation("mud_weight_required", {"p_target":5000,"tvd":10000})
        self.assertIn("approved drilling program", r)
        self.assertNotIn("0.2", r.split("Note:")[1] if "Note:" in r else "")

    def test_specific_validation_messages(self):
        r = run_exact_calculation("ooip", {"area":100,"h":-5,"phi":0.2,"sw":0.3,"bo":1.3})
        self.assertIn("h = -5", r)
        r2 = run_exact_calculation("productivity_index", {"q":100,"pr":2000,"pwf":3000})
        self.assertIn("pr", r2)
        self.assertIn("pwf", r2)

    def test_engine_first_policy_in_context(self):
        from services.ai_service import AIService
        ctx = AIService._build_engineering_context()
        self.assertIn("ENGINE-FIRST", ctx)
        self.assertIn("/calc", ctx)
        self.assertIn("/estimate", ctx)


if __name__ == "__main__":
    unittest.main()
