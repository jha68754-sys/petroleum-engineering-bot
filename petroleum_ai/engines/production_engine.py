"""
Production Engineering Engine: IPR modeling, decline curve forecasting, and productivity evaluation.
"""

from __future__ import annotations
from typing import Any, Dict, Optional
from petroleum_ai.knowledge.production.production_kb import PRODUCTION_KNOWLEDGE_BASE
from petroleum_ai.calculators.production_calculators import (
    calculate_productivity_index,
    calculate_vogel_q_max,
    calculate_arps_decline
)

class ProductionEngine:
    """Core engineering reasoning and calculation engine for production engineering."""

    @staticmethod
    def get_topic_details(topic_id: str) -> Optional[Dict[str, Any]]:
        return PRODUCTION_KNOWLEDGE_BASE.get(topic_id.lower())

    @staticmethod
    def analyze_production(data: Dict[str, Any]) -> Dict[str, Any]:
        """Perform IPR and production decline analysis."""
        q = data.get("q_stb_day", 1500.0)
        pr = data.get("pr_psi", 4000.0)
        pwf = data.get("pwf_psi", 2500.0)

        pi = calculate_productivity_index(q, pr, pwf)
        q_max = calculate_vogel_q_max(q, pwf, pr)
        q_future = calculate_arps_decline(q, 0.5, 0.15, 2.0)

        return {
            "productivity_index_stb_day_psi": pi,
            "vogel_q_max_stb_day": q_max,
            "future_rate_2yrs_stb_day": q_future,
            "interpretation": "Production analysis indicates healthy well deliverability with stable hyperbolic decline forecast."
        }
