"""
Engineering Memory: Historical case repository and similarity search engine for Expert System.
"""

from __future__ import annotations
from typing import Dict, List, Any

class EngineeringMemory:
    """Stores and retrieves historical petroleum engineering field cases."""

    HISTORICAL_CASES = [
        {
            "case_id": "EXP_HIST_001",
            "field": "Permian Basin Wolfcamp",
            "problem": "Rapid production decline and high water cut surge",
            "root_cause": "Active edge water encroachment and thief zone channeling",
            "successful_action": "Zonal isolation and polymer gel water shut-off treatment",
            "production_gain_bopd": 850,
            "economic_roi": 3.2
        },
        {
            "case_id": "EXP_HIST_002",
            "field": "Ghawar Arab-D",
            "problem": "Pressure depletion and solution gas breakout",
            "root_cause": "Volumetric depletion without pressure maintenance",
            "successful_action": "Inverted nine-spot water injection pattern and ESP installation",
            "production_gain_bopd": 2500,
            "economic_roi": 4.5
        }
    ]

    @staticmethod
    def search_similar_cases(symptom: str) -> List[Dict[str, Any]]:
        matches = []
        for case in EngineeringMemory.HISTORICAL_CASES:
            if symptom.lower() in case["problem"].lower() or symptom.lower() in case["root_cause"].lower():
                matches.append(case)
        return matches if matches else EngineeringMemory.HISTORICAL_CASES
