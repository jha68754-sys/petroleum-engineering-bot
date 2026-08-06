"""
Unit tests for the Unified Engineering Reasoning Framework (ERF).
"""

import unittest
from petroleum_ai.reasoning.framework import EngineeringReasoningFramework, EngineeringContext

class TestEngineeringReasoningFramework(unittest.TestCase):

    def test_intent_detection(self):
        self.assertEqual(EngineeringReasoningFramework.detect_intent("How to calculate OOIP?"), "Reservoir")
        self.assertEqual(EngineeringReasoningFramework.detect_intent("Design an ESP for this well"), "Artificial Lift")
        self.assertEqual(EngineeringReasoningFramework.detect_intent("Vogel IPR performance curve"), "Production")
        self.assertEqual(EngineeringReasoningFramework.detect_intent("Calculate Z-factor and Bo"), "PVT")

    def test_missing_data(self):
        missing = EngineeringReasoningFramework.collect_missing_data("Reservoir", {"area_acres": 640})
        self.assertIn("net_pay_ft", missing)
        self.assertNotIn("area_acres", missing)

    def test_reasoning_and_recommendations(self):
        reasoning = EngineeringReasoningFramework.perform_reasoning("Artificial Lift", {})
        self.assertTrue(reasoning["assumptions"])
        self.assertTrue(reasoning["equations"])

        recs = EngineeringReasoningFramework.generate_recommendations("Artificial Lift", {})
        self.assertGreater(len(recs), 0)

    def test_confidence_engine(self):
        level, reason = EngineeringReasoningFramework.evaluate_confidence("Reservoir", {"area_acres": 640, "net_pay_ft": 50, "porosity": 0.2, "water_saturation": 0.25, "boi": 1.25}, [])
        self.assertEqual(level, "High")

        level_med, _ = EngineeringReasoningFramework.evaluate_confidence("Reservoir", {"area_acres": 640}, ["net_pay_ft"])
        self.assertEqual(level_med, "Medium")

    def test_report_generation(self):
        ctx = EngineeringContext(
            query="Recommend artificial lift for high rate well",
            discipline="Artificial Lift",
            provided_data={"q_rate_stb_day": 3000, "depth_ft": 8000},
            missing_data=[],
            assumptions=["Steady state flow"],
            constraints=["Pressure limits"],
            selected_equations=["TDH = ..."],
            calculation_sequence=["1. Calculate TDH", "2. Select pump"],
            uncertainty="Medium uncertainty",
            recommendations=[{"rank": "1", "recommendation": "ESP", "why_selected": "High rate", "why_rejected": "Gas lock"}],
            confidence_level="High",
            confidence_reason="All data provided",
            references=["SPE Handbook"]
        )
        report = EngineeringReasoningFramework.generate_report(ctx)
        self.assertIn("تقرير الهندسة البترولية الاحترافي", report)
        self.assertIn("Artificial Lift", report)
        self.assertIn("ESP", report)

if __name__ == "__main__":
    unittest.main()
