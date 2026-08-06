"""
Comprehensive unit tests for the Enterprise-Grade Core Platform Layer.
"""

import unittest
from petroleum_ai.core.session.session_manager import SessionManager
from petroleum_ai.core.units.unit_manager import UnitManager
from petroleum_ai.core.calculators.calculator_manager import CalculatorManager
from petroleum_ai.core.workflows.workflow_manager import WorkflowManager
from petroleum_ai.core.plugins.plugin_system import PluginManager
from petroleum_ai.core.index.knowledge_index import KnowledgeIndex
from petroleum_ai.core.cache.performance_layer import PerformanceLayer
from petroleum_ai.core.api.api_gateway import APIGateway
from petroleum_ai.core.logging.engineering_logger import EngineeringLogger
from petroleum_ai.core.scalability.scalability_manager import ScalabilityManager

class TestCorePlatformLayer(unittest.TestCase):

    def test_session_manager(self):
        session = SessionManager.get_or_create_session("well_alpha_01")
        session.current_well = "Well-101"
        self.assertEqual(SessionManager.get_or_create_session("well_alpha_01").current_well, "Well-101")
        SessionManager.log_assumption("well_alpha_01", "Steady state radial flow")
        self.assertIn("Steady state radial flow", session.assumptions_history)

    def test_unit_manager(self):
        psi = 2000
        kPa = UnitManager.convert_pressure(psi, "field", "si")
        back_psi = UnitManager.convert_pressure(kPa, "si", "field")
        self.assertAlmostEqual(psi, back_psi, places=1)

    def test_calculator_manager(self):
        CalculatorManager.register_calculator("dummy_calc", lambda x: x * 2)
        res = CalculatorManager.run_calculation("dummy_calc", 21)
        self.assertEqual(res, 42)

    def test_workflow_manager(self):
        ctx = WorkflowManager.execute_workflow("Calculate OOIP for reservoir", {"area_acres": 640})
        self.assertEqual(ctx.discipline, "Reservoir")
        self.assertIn("net_pay_ft", ctx.missing_data)

    def test_knowledge_index(self):
        res = KnowledgeIndex.search_index("ooip")
        self.assertIn("equations", res)

    def test_performance_layer(self):
        val = PerformanceLayer.cached_calculation("test_key", lambda x: x + 10, 5)
        self.assertEqual(val, 15)

    def test_api_gateway(self):
        response = APIGateway.handle_request("telegram", {"query": "Design ESP for well", "data": {"q_rate_stb_day": 3000, "depth_ft": 8000}})
        self.assertEqual(response["status"], "success")
        self.assertIn("Artificial Lift", response["discipline"])

    def test_engineering_logger(self):
        audit = EngineeringLogger.log_calculation_audit("OOIP", {"A": 640}, ["OOIP formula"], ["SPE"], "High", "Standard volumetric sequence")
        self.assertEqual(audit["calculation_name"], "OOIP")

    def test_scalability_manager(self):
        ScalabilityManager.register_equation("SPE-EQ-001")
        stats = ScalabilityManager.get_stats()
        self.assertGreaterEqual(stats["total_registered_equations"], 1)

if __name__ == "__main__":
    unittest.main()
