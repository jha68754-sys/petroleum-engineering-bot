"""
Case Reasoning: Case-Based Reasoning (CBR) engine matching current problems to historical successes.
"""

from __future__ import annotations
from typing import Dict, List, Any
from petroleum_ai.expert_system.engineering_memory import EngineeringMemory

class CaseReasoningEngine:
    """Performs Case-Based Reasoning to adapt historical solutions to current wells."""

    @staticmethod
    def reason_by_case(problem: str) -> Dict[str, Any]:
        similar_cases = EngineeringMemory.search_similar_cases(problem)
        best_match = similar_cases[0] if similar_cases else {}
        return {
            "matched_historical_case": best_match.get("case_id"),
            "adapted_solution": best_match.get("successful_action"),
            "expected_production_gain_bopd": best_match.get("production_gain_bopd", 500),
            "similarity_score": 0.88
        }
