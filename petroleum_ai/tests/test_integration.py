"""
Comprehensive System Integration Tests verifying multi-discipline workflow orchestration,
Core Platform, ERF, Reservoir, Production, Well Testing, and Artificial Lift modules.
"""

import unittest
from petroleum_ai.core.orchestrator.engineering_orchestrator import EngineeringOrchestrator
from petroleum_ai.core.calculators.calculator_manager import CalculatorManager
from petroleum_ai.core.plugins.plugin_system import PluginManager

class TestSystemIntegration(unittest.TestCase):

    def test_orchestrator_full_workflow(self):
        payload = {
            "query": "Perform complete reservoir, production, and artificial lift analysis for well",
            "data": {
                "area_acres": 640.0,
                "net_pay_ft": 50.0,
                "porosity": 0.20,
                "water_saturation": 0.25,
                "boi": 1.25,
                "q_stb_day": 1500.0,
                "pr_psi": 4000.0,
                "pwf_psi": 2500.0,
                "depth_ft": 8000.0,
                "gor_scf_stb": 500.0,
                "water_cut": 0.2,
                "k_md": 50.0,
                "h_ft": 40.0,
                "mu_cp": 1.2
            }
        }

        result = EngineeringOrchestrator.execute_complete_workflow(payload["query"], payload["data"])
        self.assertEqual(result["status"], "success")
        self.assertIn("reservoir_results", result)
        self.assertIn("production_results", result)
        self.assertIn("well_testing_results", result)
        self.assertIn("lift_results", result)
        self.assertIn("unified_report", result)
        self.assertEqual(result["confidence_level"], "High")

    def test_universal_calculator_manager_cross_module(self):
        # Test calculators registered across different module plugins
        ooip_res = CalculatorManager.run_calculation("ooip", 640.0, 50.0, 0.20, 0.25, 1.25)
        self.assertGreater(ooip_res, 0)

        pi_res = CalculatorManager.run_calculation("productivity_index", 1500.0, 4000.0, 2500.0)
        self.assertEqual(pi_res, 1.0)

        trans_res = CalculatorManager.run_calculation("transmissibility", 50.0, 40.0, 1.2)
        self.assertAlmostEqual(trans_res, 1666.67, places=1)

    def test_plugin_system_all_registered(self):
        plugins = PluginManager.list_plugins()
        self.assertIn("WellTestingPlugin", plugins)
        self.assertIn("ReservoirPlugin", plugins)
        self.assertIn("ProductionPlugin", plugins)

if __name__ == "__main__":
    unittest.main()
