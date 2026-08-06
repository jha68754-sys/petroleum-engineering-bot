"""
Comprehensive unit and integration tests for the Production Engineering Module.
"""

import unittest
from petroleum_ai.knowledge.production.production_kb import PRODUCTION_KNOWLEDGE_BASE
from petroleum_ai.calculators.production_calculators import (
    calculate_productivity_index,
    calculate_vogel_q_max,
    calculate_arps_decline
)
from petroleum_ai.engines.production_engine import ProductionEngine
from petroleum_ai.core.plugins.production_plugin import ProductionPlugin
from petroleum_ai.core.calculators.calculator_manager import CalculatorManager
from petroleum_ai.core.plugins.plugin_system import PluginManager
from petroleum_ai.core.workflows.workflow_manager import WorkflowManager

class TestProductionModule(unittest.TestCase):

    def test_knowledge_base(self):
        self.assertIn("ipr_vogel_model", PRODUCTION_KNOWLEDGE_BASE)
        self.assertIn("decline_curve_analysis", PRODUCTION_KNOWLEDGE_BASE)
        self.assertEqual(PRODUCTION_KNOWLEDGE_BASE["productivity_index"]["confidence"], "High")

    def test_calculators(self):
        pi = calculate_productivity_index(1500.0, 4000.0, 2500.0)
        self.assertEqual(pi, 1.0)

        q_max = calculate_vogel_q_max(1500.0, 2500.0, 4000.0)
        self.assertGreater(q_max, 1500.0)

        q_future = calculate_arps_decline(1500.0, 0.5, 0.15, 2.0)
        self.assertGreater(q_future, 0)

    def test_calculator_manager_integration(self):
        res = CalculatorManager.run_calculation("productivity_index", 2000.0, 4500.0, 3000.0)
        self.assertEqual(res, 1.333)

    def test_plugin_registration(self):
        plugin = PluginManager.get_plugin("ProductionPlugin")
        self.assertIsNotNone(plugin)
        self.assertEqual(plugin.discipline, "Production")

    def test_workflow_execution(self):
        ctx = WorkflowManager.execute_workflow("Analyze Vogel IPR and productivity index", {"q_stb_day": 1500, "pr_psi": 4000})
        self.assertEqual(ctx.discipline, "Production")
        self.assertIsNotNone(ctx.confidence_level)

if __name__ == "__main__":
    unittest.main()
