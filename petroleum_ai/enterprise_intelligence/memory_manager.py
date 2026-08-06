"""
Memory Manager: Manages Engineering Memory, Decision Memory, Case Memory, Calculation Memory, Workflow Memory, and Recommendation Memory.
"""

from __future__ import annotations
from typing import List, Dict, Any

class MemoryManager:
    def __init__(self):
        self.engineering_memory: List[Dict[str, Any]] = []
        self.decision_memory: List[Dict[str, Any]] = []
        self.case_memory: List[Dict[str, Any]] = []
        self.calculation_memory: List[Dict[str, Any]] = []
        self.workflow_memory: List[Dict[str, Any]] = []
        self.recommendation_memory: List[Dict[str, Any]] = []

    def remember(self, memory_type: str, data: Dict[str, Any]) -> None:
        if memory_type == "engineering":
            self.engineering_memory.append(data)
        elif memory_type == "decision":
            self.decision_memory.append(data)
        elif memory_type == "case":
            self.case_memory.append(data)
        elif memory_type == "calculation":
            self.calculation_memory.append(data)
        elif memory_type == "workflow":
            self.workflow_memory.append(data)
        elif memory_type == "recommendation":
            self.recommendation_memory.append(data)

    def recall(self, memory_type: str) -> List[Dict[str, Any]]:
        if memory_type == "engineering":
            return self.engineering_memory
        elif memory_type == "decision":
            return self.decision_memory
        elif memory_type == "case":
            return self.case_memory
        elif memory_type == "calculation":
            return self.calculation_memory
        elif memory_type == "workflow":
            return self.workflow_memory
        elif memory_type == "recommendation":
            return self.recommendation_memory
        return []
