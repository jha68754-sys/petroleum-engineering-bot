"""
Validation tests for the Artificial Lift Engineering Module (Phase 1).
"""

import unittest
from services.artificial_lift_engine import ArtificialLiftEngine
from artificial_lift_kb import ARTIFICIAL_LIFT_KNOWLEDGE_BASE

class TestArtificialLiftModule(unittest.TestCase):

    def test_kb_completeness(self):
        """Verify all lift systems exist and have required fields."""
        expected_systems = ["esp", "gas_lift", "srp", "pcp", "hydraulic", "plunger_lift"]
        for sys_id in expected_systems:
            self.assertIn(sys_id, ARTIFICIAL_LIFT_KNOWLEDGE_BASE)
            details = ARTIFICIAL_LIFT_KNOWLEDGE_BASE[sys_id]
            self.assertTrue(details["theory_ar"])
            self.assertTrue(details["selection_criteria_ar"])
            self.assertTrue(details["key_equations_ar"])
            self.assertEqual(details["confidence"], "High")

    def test_screening_esp(self):
        """Test screening logic for high rate deep well -> ESP."""
        input_data = {
            "q_rate_stb_day": 3500,
            "depth_ft": 8500,
            "gor_scf_stb": 400,
            "water_cut_pct": 60,
            "viscosity_cp": 1.5,
            "sand_content": False,
            "temperature_f": 200,
            "offshore": False
        }
        res = ArtificialLiftEngine.screen_lift_system(input_data)
        self.assertEqual(res["recommended_system"], "esp")

    def test_screening_pcp(self):
        """Test screening logic for heavy oil / high viscosity -> PCP."""
        input_data = {
            "q_rate_stb_day": 400,
            "depth_ft": 3000,
            "gor_scf_stb": 50,
            "water_cut_pct": 20,
            "viscosity_cp": 250.0,
            "sand_content": True,
            "temperature_f": 120,
            "offshore": False
        }
        res = ArtificialLiftEngine.screen_lift_system(input_data)
        self.assertEqual(res["recommended_system"], "pcp")

    def test_esp_calculations(self):
        """Test ESP hydraulic calculations."""
        tdh = ArtificialLiftEngine.calculate_esp_tdh(8000, 200, 0.38)
        self.assertGreater(tdh, 3000)
        hhp = ArtificialLiftEngine.calculate_hydraulic_horsepower(2000, tdh, 0.85)
        self.assertGreater(hhp, 10.0)

if __name__ == "__main__":
    unittest.main()
