"""
Enterprise Brain: The top-level cognitive hub managing thinking, reasoning, memory, and coordination.
"""

from __future__ import annotations
from typing import Dict, Any
from petroleum_ai.enterprise_intelligence.context_manager import ContextManager
from petroleum_ai.enterprise_intelligence.memory_manager import MemoryManager
from petroleum_ai.enterprise_intelligence.workflow_manager import WorkflowManager
from petroleum_ai.enterprise_intelligence.orchestration_center import OrchestrationCenter
from petroleum_ai.enterprise_intelligence.engineering_reasoner import EngineeringReasoner

class EnterpriseBrain:
    def __init__(self):
        self.context_manager = ContextManager()
        self.memory_manager = MemoryManager()
        self.workflow_manager = WorkflowManager()
        self.orchestration_center = OrchestrationCenter()
        self.engineering_reasoner = EngineeringReasoner()

    def process_request(self, intent: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        self.context_manager.update_engineering_context("current", payload)
        reasoning = self.engineering_reasoner.reason(intent, payload)
        orchestration = self.orchestration_center.orchestrate(intent, payload)
        
        self.memory_manager.remember("engineering", {"intent": intent, "reasoning": reasoning})
        
        return {
            "intent": intent,
            "reasoning": reasoning,
            "orchestration": orchestration,
            "status": "ENTERPRISE_INTELLIGENCE_PROCESSED"
        }
