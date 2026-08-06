"""
Field Rules: Practical thumb rules used by senior field operations engineers.
"""

from __future__ import annotations
from typing import Dict, Any

class FieldRules:
    """Operational rules of thumb for quick field diagnostics."""

    @staticmethod
    def evaluate_field_rule(data: Dict[str, Any]) -> str:
        gor = data.get("gor", 1000)
        if gor > 5000:
            return "High GOR advisory: Check for gas cap coning or second-stage separation pressure."
        return "GOR within normal operational envelope."
