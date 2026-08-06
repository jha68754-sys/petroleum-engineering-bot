"""
Comprehensive unit and integration test suite for the Expert System subsystem.
"""

import unittest
from petroleum_ai.expert_system.expert_engine import ExpertEngine
from petroleum_ai.expert_system.case_reasoning import CaseReasoningEngine
from petroleum_ai.expert_system.scenario_engine import ScenarioEngine
from petroleum_ai.expert_system.optimization_engine import OptimizationEngine
from petroleum_ai.expert_system.engineering_explainer import EngineeringExplainer
from petroleum_ai.expert_system.expert_reports import ExpertReportGenerator
from petroleum_ai.expert_system.plugin import ExpertSystemPlugin
from petroleum_ai.core.plugins.plugin_system import PluginManager

class TestExpertSystem(unittest.TestCase):

    def test_expert_engine_analysis(self):
        data = {"water_cut": 0.70, "water_cut_increasing": True}
        res = ExpertEngine.analyze_expert_situation("High water cut and decline", data)
        self.assertEqual(res["expert_confidence"], "High")
        self.assertIn("decision", res)

    def test_case_reasoning(self):
        res = CaseReasoningEngine.reason_by_case("Water breakthrough")
        self.assertIsNotNone(res["adapted_solution"])

    def test_scenario_generation(self):
        scenarios = ScenarioEngine.generate_scenarios({})
        self.assertGreaterEqual(len(scenarios), 3)

    def test_optimization_recommendations(self):
        opts = OptimizationEngine.optimize_production({})
        self.assertGreaterEqual(len(opts), 2)

    def test_engineering_explanation(self):
        exp = EngineeringExplainer.explain_recommendation("Zonal isolation")
        self.assertIn("engineering_justification", exp)
        self.assertGreater(len(exp["supporting_references"]), 0)

    def test_expert_report_generation(self):
        res = ExpertEngine.analyze_expert_situation("Test", {})
        report = ExpertReportGenerator.generate_expert_report(res)
        self.assertIn("تقرير الخبير الهندسي الاحترافي", report)

    def test_plugin_registration(self):
        plugin = PluginManager.get_plugin("ExpertSystemPlugin")
        self.assertIsNotNone(plugin)
        self.assertEqual(plugin.discipline, "ExpertSystem")

if __name__ == "__main__":
    unittest.main()
