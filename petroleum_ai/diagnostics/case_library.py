"""
Professional Engineering Case Library for PEDI.
"""

from __future__ import annotations
from typing import Dict, List, Any

CASE_LIBRARY: List[Dict[str, Any]] = [
    {
        "case_id": "CASE_001",
        "title": "Permian Basin Water Breakthrough",
        "symptom": "High Water Cut",
        "reservoir_type": "Sandstone",
        "diagnosis": "Water breakthrough through high-k thief zone",
        "recommended_action": "Run water shut-off polymer treatment or plug back bottom perforations."
    },
    {
        "case_id": "CASE_002",
        "title": "Middle East Carbonate Pressure Depletion",
        "symptom": "Production Decline",
        "reservoir_type": "Carbonate",
        "diagnosis": "Volumetric pressure depletion in solution-gas drive reservoir",
        "recommended_action": "Initiate water injection pressure maintenance or convert to artificial lift."
    }
]
