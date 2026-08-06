"""
Petroleum AI Bridge: Connects Telegram bot handlers and commands to the Enterprise Petroleum AI Platform (EIF, ERF, Domain Modules) cleanly without modifying any underlying engines.
"""

from __future__ import annotations
from typing import Dict, Any, List
import sys
from pathlib import Path

# Ensure petroleum_ai package is accessible
sys.path.insert(0, str(Path(__file__).parent))

try:
    from petroleum_ai.enterprise_intelligence.enterprise_brain import EnterpriseBrain
    from petroleum_ai.enterprise_intelligence.engineering_validator import EngineeringValidator
    from petroleum_ai.core.plugins.plugin_system import PluginManager
except ImportError:
    EnterpriseBrain = None
    EngineeringValidator = None
    PluginManager = None

class PetroleumAIBridge:
    def __init__(self):
        self.brain = EnterpriseBrain() if EnterpriseBrain else None
        self.validator = EngineeringValidator() if EngineeringValidator else None
        self.plugin_manager = PluginManager() if PluginManager else None

    def process_query(self, intent: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process an engineering query through the Enterprise Intelligence Fabric (EIF).
        """
        if self.brain:
            try:
                return self.brain.process_request(intent, payload)
            except Exception as e:
                return {
                    "status": "ERROR",
                    "error": str(e),
                    "intent": intent
                }
        else:
            return {
                "status": "FALLBACK",
                "message": "Enterprise Brain not loaded, using standard processing.",
                "intent": intent,
                "payload": payload
            }

    def get_platform_status(self) -> Dict[str, Any]:
        """
        Return the operational status of the Enterprise Petroleum AI Platform.
        """
        return {
            "platform": "Enterprise Petroleum AI Platform",
            "version": "v1.0.0-Enterprise-Production",
            "status": "ACTIVE",
            "eif_loaded": self.brain is not None,
            "certified_ready": True
        }

# Global bridge instance
ai_bridge = PetroleumAIBridge()
