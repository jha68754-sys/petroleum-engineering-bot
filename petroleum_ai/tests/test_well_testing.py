"""
Comprehensive unit and integration tests for the Well Testing Engineering Module.
"""

import unittest
from petroleum_ai.knowledge.well_testing.well_testing_kb import WELL_TESTING_KNOWLEDGE_BASE
from petroleum_ai.calculators.well_testing_calculators import (
    calculate_skin_factor,
    calculate_radius_of_investigation,
    calculate_transmissibility
)
from petroleum_ai.engines.well_testing_engine import WellTestingEngine
from petroleum_ai.core.plugins.well_testing_plugin import WellTestingPlugin
from petroleum_ai.core.calculators.calculator_manager import CalculatorManager
from petroleum_ai.core.plugins.plugin_system import PluginManager
from petroleum_ai.core.workflows.workflow_manager import WorkflowManager

class TestWellTestingModule(unittest.TestCase):

    def test_knowledge_base(self):
        self.assertIn("pressure_drawdown", WELL_TESTING_KNOWLEDGE_BASE)
        self.assertIn("horner_buildup", WELL_TESTING_KNOWLEDGE_BASE)
        self.assertEqual(WELL_TESTING_KNOWLEDGE_BASE["skin_factor"]["confidence"], "High")

    def test_calculators(self):
        skin = calculate_skin_factor(15.0, 50.0)
        self.assertGreater(skin, 0)

        r_i = calculate_radius_of_investigation(72.0, 50.0, 0.18, 1.2, 1e-5)
        self.assertGreater(r_i, 0)

        trans = calculate_transmissibility(50.0, 40.0, 1.2)
        self.assertAlmostEqual(trans, 1666.67, places=1)

    def test_calculator_manager_integration(self):
        res = CalculatorManager.run_calculation("transmissibility", 100.0, 50.0, 2.0)
        self.assertEqual(res, 2500.0)

    def test_plugin_registration(self):
        plugin = PluginManager.get_plugin("WellTestingPlugin")
        self.assertIsNotNone(plugin)
        self.assertEqual(plugin.discipline, "Well Testing")

    def test_workflow_execution(self):
        ctx = WorkflowManager.execute_workflow("Perform Horner pressure build-up test analysis", {"flow_rate_stb_day": 1500, "initial_pressure_psi": 4000})
        self.assertEqual(ctx.discipline, "Well Testing")
        self.assertIsNotNone(ctx.confidence_level)

if __name__ == "__main__":
    unittest.main()
