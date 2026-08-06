"""
Comprehensive unit and integration test suite for Enterprise Application Layer.
"""

import unittest
from petroleum_ai.apps.engineering_assistant import EngineeringAssistant
from petroleum_ai.apps.well_workspace import WellWorkspace
from petroleum_ai.apps.field_workspace import FieldWorkspace
from petroleum_ai.apps.scenario_studio import ScenarioStudio
from petroleum_ai.apps.report_center import ReportCenter
from petroleum_ai.apps.knowledge_center import KnowledgeCenter
from petroleum_ai.apps.calculator_center import CalculatorCenter
from petroleum_ai.apps.decision_center import DecisionCenter
from petroleum_ai.apps.digital_twin_viewer import DigitalTwinViewer
from petroleum_ai.apps.executive_dashboard import ExecutiveDashboard
from petroleum_ai.apps.project_manager import ProjectManager
from petroleum_ai.apps.user_management import UserManagement
from petroleum_ai.apps.audit_center import AuditCenter
from petroleum_ai.apps.api_gateway_app import ApiGatewayApp
from petroleum_ai.apps.application_launcher import ApplicationLauncher
from petroleum_ai.apps.plugin import EnterpriseAppsPlugin
from petroleum_ai.core.plugins.plugin_system import PluginManager

class TestEnterpriseApps(unittest.TestCase):

    def test_engineering_assistant(self):
        assistant = EngineeringAssistant()
        res = assistant.chat("sess_01", "Hello")
        self.assertEqual(res["session_id"], "sess_01")
        self.assertEqual(res["status"], "Success")

    def test_well_workspace(self):
        ws = WellWorkspace.get_well_workspace("WELL_001")
        self.assertEqual(ws["well_id"], "WELL_001")

    def test_field_workspace(self):
        fw = FieldWorkspace.get_field_overview("Ghawar")
        self.assertEqual(fw["field_name"], "Ghawar")

    def test_scenario_studio(self):
        scen = ScenarioStudio.compare_scenarios([{"name": "A"}])
        self.assertEqual(scen["compared_count"], 1)

    def test_report_center(self):
        rep = ReportCenter.generate_report("Test", "pdf", {})
        self.assertEqual(rep["format"], "pdf")

    def test_knowledge_center(self):
        res = KnowledgeCenter.search_knowledge("Darcy")
        self.assertGreater(len(res), 0)

    def test_calculator_center(self):
        calcs = CalculatorCenter.list_calculators()
        self.assertIn("Reservoir", calcs)

    def test_decision_center(self):
        dec = DecisionCenter.evaluate_decision_options(["Option 1", "Option 2"])
        self.assertEqual(dec["recommended_option"], "Option 1")

    def test_digital_twin_viewer(self):
        dt = DigitalTwinViewer.get_digital_twin_view("WELL_001")
        self.assertEqual(dt["well_id"], "WELL_001")

    def test_executive_dashboard(self):
        dash = ExecutiveDashboard.get_executive_summary()
        self.assertIn("total_field_production_bopd", dash)

    def test_project_manager(self):
        proj = ProjectManager.get_project_status("PROJ_01")
        self.assertEqual(proj["project_id"], "PROJ_01")

    def test_user_management(self):
        auth = UserManagement.authorize_user("engineer_ali", "Field Engineer")
        self.assertTrue(auth["authorized"])

    def test_audit_center(self):
        log = AuditCenter.log_action("ali", "Calculate OOIP", "Volumetrics", "Craft & Hawkins", "High")
        self.assertEqual(log["user"], "ali")

    def test_api_gateway(self):
        resp = ApiGatewayApp.handle_api_request("/v1/well", {}, "token")
        self.assertEqual(resp["code"], 200)

    def test_application_launcher(self):
        apps = ApplicationLauncher.get_available_applications()
        self.assertEqual(len(apps), 15)

    def test_plugin_registration(self):
        plugin = PluginManager.get_plugin("EnterpriseAppsPlugin")
        self.assertIsNotNone(plugin)
        self.assertEqual(plugin.discipline, "EnterpriseApplicationLayer")

if __name__ == "__main__":
    unittest.main()
