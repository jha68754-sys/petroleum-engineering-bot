"""
Evidence Collection Engine for PEDI: Identifies missing engineering information and generates follow-up queries.
"""

from __future__ import annotations
from typing import Dict, List, Any

class EvidenceEngine:
    """Collects and audits engineering evidence."""

    REQUIRED_PARAMETERS = [
        "reservoir_pressure", "bottom_hole_pressure", "tubing_pressure",
        "flowing_pressure", "water_cut", "gor", "api_gravity", "bubble_point",
        "temperature", "permeability", "porosity", "skin", "completion_type"
    ]

    @staticmethod
    def identify_missing_evidence(provided_data: Dict[str, Any]) -> List[str]:
        missing = []
        for param in EvidenceEngine.REQUIRED_PARAMETERS:
            if param not in provided_data:
                missing.append(param)
        return missing
