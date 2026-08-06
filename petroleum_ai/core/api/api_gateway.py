"""
8. API Layer: Gateway supporting Telegram Bot, Web Dashboard, REST API, and Mobile App integration.
"""

from __future__ import annotations
from typing import Any, Dict
from petroleum_ai.core.workflows.workflow_manager import WorkflowManager
from petroleum_ai.reasoning.framework import EngineeringReasoningFramework

class APIGateway:
    """Unified API entry point for Telegram, Web, REST, and Mobile interfaces."""

    @staticmethod
    def handle_request(client_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Process requests from any client interface (telegram, web, rest, mobile)."""
        query = payload.get("query", "")
        provided_data = payload.get("data", {})
        
        context = WorkflowManager.execute_workflow(query, provided_data)
        report = EngineeringReasoningFramework.generate_report(context)

        return {
            "status": "success",
            "client_type": client_type,
            "discipline": context.discipline,
            "confidence": context.confidence_level,
            "report_markdown": report,
            "raw_context": {
                "missing_data": context.missing_data,
                "recommendations": context.recommendations
            }
        }
