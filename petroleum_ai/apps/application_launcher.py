"""
Application Launcher: Central launcher coordinating and initializing all enterprise applications.
"""

from __future__ import annotations
from typing import Dict, List, Any
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

class ApplicationLauncher:
    """Launches and coordinates all 15 enterprise applications from a single point."""

    @staticmethod
    def get_available_applications() -> List[str]:
        return [
            "Engineering Assistant",
            "Well Workspace",
            "Field Workspace",
            "Scenario Studio",
            "Report Center",
            "Knowledge Center",
            "Engineering Calculator Center",
            "Decision Center",
            "Digital Twin Viewer",
            "Executive Dashboard",
            "Project Manager",
            "User Management",
            "Audit Center",
            "API Gateway",
            "Application Launcher"
        ]
