"""
Comprehensive unit and integration test suite for Operational Intelligence subsystem.
"""

import unittest
from petroleum_ai.operational_intelligence.digital_twin_manager import DigitalTwinManager
from petroleum_ai.operational_intelligence.field_surveillance_engine import FieldSurveillanceEngine
from petroleum_ai.operational_intelligence.engineering_monitoring_engine import EngineeringMonitoringEngine
from petroleum_ai.operational_intelligence.operational_decision_center import OperationalDecisionCenter
from petroleum_ai.operational_intelligence.optimization_center import OptimizationCenter
from petroleum_ai.operational_intelligence.economic_evaluation_engine import EconomicEvaluationEngine
from petroleum_ai.operational_intelligence.field_kpi_engine import FieldKPIEngine
from petroleum_ai.operational_intelligence.forecast_engine import ForecastEngine
from petroleum_ai.operational_intelligence.alert_engine import AlertEngine
from petroleum_ai.operational_intelligence.workflow_automation import EngineeringWorkflowAutomation
from petroleum_ai.operational_intelligence.unified_dashboard_generator import UnifiedDashboardGenerator
from petroleum_ai.operational_intelligence.executive_report_generator import ExecutiveReportGenerator
from petroleum_ai.operational_intelligence.plugin import OperationalIntelligencePlugin
from petroleum_ai.core.plugins.plugin_system import PluginManager

class TestOperationalIntelligence(unittest.TestCase):

    def test_digital_twin_creation(self):
        twin = DigitalTwinManager.create_well_digital_twin("WELL_001", "Ghawar", {"operational_status": "Active"})
        self.assertEqual(twin["well_id"], "WELL_001")
        self.assertEqual(twin["operational_status"], "Active")

    def test_field_surveillance(self):
        twin = {"production_history": [{"water_cut": 0.65, "gor": 1500}]}
        anomalies = FieldSurveillanceEngine.survey_well_status(twin)
        self.assertGreater(len(anomalies), 0)

    def test_monitoring_trends(self):
        res = EngineeringMonitoringEngine.detect_trends([{"oil_rate": 1000}, {"oil_rate": 850}])
        self.assertTrue(res["drift_detected"])

    def test_operational_decision(self):
        decision = OperationalDecisionCenter.evaluate_operational_decision({"operational_status": "Active"})
        self.assertIn("decision", decision)

    def test_optimization_center(self):
        scenarios = OptimizationCenter.optimize_scenarios({})
        self.assertGreaterEqual(len(scenarios), 3)

    def test_economic_evaluation(self):
        econ = EconomicEvaluationEngine.evaluate_economics(1000000, 50000, 400000)
        self.assertIn("npv", econ)

    def test_field_kpis(self):
        kpis = FieldKPIEngine.compute_field_kpis({})
        self.assertIn("field_health_index", kpis)

    def test_forecast_engine(self):
        forecasts = ForecastEngine.generate_forecasts(1000)
        self.assertIn("30_days", forecasts)

    def test_alert_engine(self):
        alerts = AlertEngine.generate_alerts([{"severity": "Critical", "anomaly": "High Pressure Drop"}])
        self.assertEqual(alerts[0]["severity"], "Critical")

    def test_workflow_automation(self):
        wf = EngineeringWorkflowAutomation.execute_operational_workflow("WELL_001", {})
        self.assertEqual(wf["status"], "Operational Workflow Successfully Automated")

    def test_dashboard_generator(self):
        dash = UnifiedDashboardGenerator.generate_dashboard_json({}, [])
        self.assertIn("dashboard_title", dash)

    def test_executive_report(self):
        report = ExecutiveReportGenerator.generate_executive_report({})
        self.assertIn("التقرير الهندسي التنفيذي", report)

    def test_plugin_registration(self):
        plugin = PluginManager.get_plugin("OperationalIntelligencePlugin")
        self.assertIsNotNone(plugin)
        self.assertEqual(plugin.discipline, "OperationalIntelligence")

if __name__ == "__main__":
    unittest.main()
