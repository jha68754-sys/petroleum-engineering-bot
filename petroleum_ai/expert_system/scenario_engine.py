"""
Scenario Engine: Generates multiple engineering scenarios with risk and economic impact.
"""

from __future__ import annotations
from typing import Dict, List, Any

class ScenarioEngine:
    """Generates optimistic, base, and pessimistic engineering scenarios."""

    @staticmethod
    def generate_scenarios(data: Dict[str, Any]) -> List[Dict[str, Any]]:
        return [
            {
                "scenario": "Optimistic Scenario (Stimulation & Pressure Maintenance)",
                "action": "Execute matrix acidizing and initiate water injection.",
                "production_gain": 1200,
                "economic_impact": "High Net Present Value (NPV), ROI = 3.5",
                "risk": "Low"
            },
            {
                "scenario": "Base Scenario (Targeted Workover)",
                "action": "Isolate water-producing interval and re-optimize gas lift.",
                "production_gain": 600,
                "economic_impact": "Moderate NPV, ROI = 2.2",
                "risk": "Moderate"
            },
            {
                "scenario": "Pessimistic Scenario (Do Nothing / Natural Decline)",
                "action": "Maintain current operating parameters without intervention.",
                "production_gain": 0,
                "economic_impact": "Declining cash flow and premature abandonment",
                "risk": "High"
            }
        ]
