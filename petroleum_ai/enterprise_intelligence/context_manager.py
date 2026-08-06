"""
Context Manager: Manages Current, Historical, Conversation, Engineering, Well, Field, and Project context.
"""

from __future__ import annotations
from typing import Dict, Any
from petroleum_ai.enterprise_intelligence.engineering_context import EngineeringContext

class ContextManager:
    def __init__(self):
        self.engineering_context = EngineeringContext()
        self.conversation_context: Dict[str, Any] = {}

    def update_engineering_context(self, category: str, data: Dict[str, Any]) -> None:
        self.engineering_context.update_context(category, data)

    def update_conversation_context(self, data: Dict[str, Any]) -> None:
        self.conversation_context.update(data)

    def get_context(self) -> Dict[str, Any]:
        full = self.engineering_context.get_full_context()
        full["conversation"] = self.conversation_context
        return full
