"""
Comprehensive unit and integration test suite for Petroleum Engineering Diagnostic Intelligence (PEDI).
"""

import unittest
from petroleum_ai.diagnostics.workflow_engine import WorkflowEngine
from petroleum_ai.diagnostics.evidence_engine import EvidenceEngine
from petroleum_ai.diagnostics.root_cause_engine import RootCauseEngine
from petroleum_ai.diagnostics.diagnostic_reports import DiagnosticReportGenerator
from petroleum_ai.diagnostics.plugin import PEDIPlugin
from petroleum_ai.core.plugins.plugin_system import PluginManager

class TestPEDISystem(unittest.TestCase):

    def test_workflow_execution(self):
        data = {
            "water_cut_increasing": True,
            "reservoir_pressure_stable": True,
            "water_cut": 0.65,
            "gor": 800
        }
        res = WorkflowEngine.execute_workflow("Production decline and water cut surge", data)
        self.assertEqual(res["diagnosis"]["diagnosis"], "Water Breakthrough / Coning")
        self.assertGreater(len(res["root_causes"]), 0)

    def test_evidence_collection(self):
        missing = EvidenceEngine.identify_missing_evidence({"reservoir_pressure": 3500})
        self.assertIn("bottom_hole_pressure", missing)

    def test_root_cause_analysis(self):
        causes = RootCauseEngine.analyze_root_causes("production_decline", {})
        self.assertGreater(len(causes), 0)

    def test_plugin_registration(self):
        plugin = PluginManager.get_plugin("PEDIPlugin")
        self.assertIsNotNone(plugin)
        self.assertEqual(plugin.discipline, "Diagnostics")

    def test_report_generation(self):
        res = WorkflowEngine.execute_workflow("Test Problem", {})
        report = DiagnosticReportGenerator.generate_report(res)
        self.assertIn("PEDI Enterprise Diagnostic Report", report)

if __name__ == "__main__":
    unittest.main()
