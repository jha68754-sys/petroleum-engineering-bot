"""
Comprehensive unit and integration tests for the Reservoir Engineering Module.
"""

import unittest
from petroleum_ai.knowledge.reservoir.reservoir_kb import RESERVOIR_KNOWLEDGE_BASE
from petroleum_ai.calculators.reservoir_calculators import (
    calculate_ooip,
    calculate_ogip,
    calculate_total_compressibility
)
from petroleum_ai.engines.reservoir_engine import ReservoirEngine
from petroleum_ai.core.plugins.reservoir_plugin import ReservoirPlugin
from petroleum_ai.core.calculators.calculator_manager import CalculatorManager
from petroleum_ai.core.plugins.plugin_system import PluginManager
from petroleum_ai.core.workflows.workflow_manager import WorkflowManager

class TestReservoirModule(unittest.TestCase):

    def test_knowledge_base(self):
        self.assertIn("reservoir_characterization", RESERVOIR_KNOWLEDGE_BASE)
        self.assertIn("volumetrics_ooip_ogip", RESERVOIR_KNOWLEDGE_BASE)
        self.assertEqual(RESERVOIR_KNOWLEDGE_BASE["material_balance"]["confidence"], "High")

    def test_calculators(self):
        ooip = calculate_ooip(640.0, 50.0, 0.20, 0.25, 1.25)
        self.assertGreater(ooip, 0)

        ogip = calculate_ogip(640.0, 50.0, 0.20, 0.25, 0.85)
        self.assertGreater(ogip, 0)

        ct = calculate_total_compressibility(3e-6, 12e-5, 3e-6, 0.25)
        self.assertGreater(ct, 0)

    def test_calculator_manager_integration(self):
        res = CalculatorManager.run_calculation("ooip", 640.0, 50.0, 0.20, 0.25, 1.25)
        self.assertGreater(res, 0)

    def test_plugin_registration(self):
        plugin = PluginManager.get_plugin("ReservoirPlugin")
        self.assertIsNotNone(plugin)
        self.assertEqual(plugin.discipline, "Reservoir")

    def test_workflow_execution(self):
        ctx = WorkflowManager.execute_workflow("Calculate OOIP for oil reservoir", {"area_acres": 640, "net_pay_ft": 50})
        self.assertEqual(ctx.discipline, "Reservoir")
        self.assertIsNotNone(ctx.confidence_level)

if __name__ == "__main__":
    unittest.main()
