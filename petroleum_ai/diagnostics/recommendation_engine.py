"""
Recommendation Engine for PEDI.
"""

from __future__ import annotations
from typing import Dict, List, Any

class RecommendationEngine:
    """Prioritizes and explains engineering recommendations."""

    @staticmethod
    def generate_recommendations(diagnosis: str, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        return [
            {
                "priority": 1,
                "category": "Immediate Action",
                "recommendation": "Perform pressure transient testing (pressure buildup) to quantify skin factor and reservoir permeability.",
                "why": "Provides definitive diagnostic parameters to separate mechanical skin from reservoir boundary effects."
            },
            {
                "priority": 2,
                "category": "Production Optimization",
                "recommendation": "Conduct Nodal Analysis to optimize tubing size and artificial lift operating parameters.",
                "why": "Ensures operating flow rate matches maximum well deliverability without inducing excessive drawdown or coning."
            }
        ]
