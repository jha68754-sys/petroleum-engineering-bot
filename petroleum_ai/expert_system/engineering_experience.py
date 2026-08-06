"""
Engineering Experience: Encodes 30+ years of senior field engineering wisdom and heuristics.
"""

from __future__:: annotations
from typing import Dict, Any

class EngineeringExperience:
    """Encapsulates expert engineering rules of thumb and field heuristics."""

    @staticmethod
    def get_expert_wisdom(discipline: str) -> Dict[str, Any]:
        wisdoms = {
            "reservoir": "Never rely solely on volumetric calculations without material balance and pressure transient calibration.",
            "production": "Always check flowing bottom-hole pressure relative to bubble point before blaming mechanical failure.",
            "artificial_lift": "Match ESP or Gas Lift design to the maximum expected PI to avoid pump-off or instability."
        }
        return {"wisdom": wisdoms.get(discipline.lower(), "Always verify field measurements with independent pressure surveys.")}
