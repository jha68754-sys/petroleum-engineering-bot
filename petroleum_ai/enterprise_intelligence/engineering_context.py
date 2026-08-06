"""
Engineering Context: Manages well, field, project, conversation, and historical context.
"""

from __future__ import annotations
from typing import Dict, Any

class EngineeringContext:
    def __init__(self):
        self.current_context: Dict[str, Any] = {}
        self.historical_context: Dict[str, Any] = {}
        self.well_context: Dict[str, Any] = {}
        self.field_context: Dict[str, Any] = {}
        self.project_context: Dict[str, Any] = {}

    def update_context(self, category: str, data: Dict[str, Any]) -> None:
        if category == "well":
            self.well_context.update(data)
        elif category == "field":
            self.field_context.update(data)
        elif category == "project":
            self.project_context.update(data)
        else:
            self.current_context.update(data)

    def get_full_context(self) -> Dict[str, Any]:
        return {
            "current": self.current_context,
            "historical": self.historical_context,
            "well": self.well_context,
            "field": self.field_context,
            "project": self.project_context
        }
