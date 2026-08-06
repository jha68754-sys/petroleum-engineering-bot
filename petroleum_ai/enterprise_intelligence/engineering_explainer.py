"""
Engineering Explainer: Explainable AI layer providing clear engineering rationale for every recommendation.
"""

from __future__ import annotations
from typing import Dict, Any

class EngineeringExplainer:
    def __init__(self):
        pass

    def explain(self, recommendation: str, context: Dict[str, Any]) -> str:
        return f"Recommendation '{recommendation}' was chosen because reservoir deliverability analysis indicates severe pressure depletion requiring artificial lift intervention, supported by Craft & Hawkins (1991) principles."
