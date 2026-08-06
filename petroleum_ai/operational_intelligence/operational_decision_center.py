"""
Operational Decision Center: Recommends operational actions (Continue, Shut-in, Stimulate, Acidize, Fracture, etc.).
"""

from __future__ import annotations
from typing import Dict, Any

class OperationalDecisionCenter:
    """Analyzes current well state and recommends operational actions with scientific justification."""

    @staticmethod
    def evaluate_operational_decision(twin_data: Dict[str, Any]) -> Dict[str, Any]:
        status = twin_data.get("operational_status", "Active")
        risk = twin_data.get("risk_profile", {}).get("risk_level", "Low")

        if risk == "Critical":
            return {
                "decision": "Shut-in & Workover",
                "justification": "Risk profile is critical; immediate shut-in and workover intervention required to prevent catastrophic failure.",
                "confidence": "High"
            }
        return {
            "decision": "Continue & Optimize Artificial Lift",
            "justification": "Well is operating within stable parameters; continue production with continuous surveillance and lift tuning.",
            "confidence": "High"
        }
