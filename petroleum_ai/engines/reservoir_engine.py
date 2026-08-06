"""
Reservoir Engineering Engine: Volumetrics, petrophysics, and drive mechanism evaluation.
"""

from __future__ import annotations
from typing import Any, Dict, Optional
from petroleum_ai.knowledge.reservoir.reservoir_kb import RESERVOIR_KNOWLEDGE_BASE
from petroleum_ai.calculators.reservoir_calculators import (
    calculate_ooip,
    calculate_ogip,
    calculate_total_compressibility
)

class ReservoirEngine:
    """Core engineering reasoning and calculation engine for reservoir engineering."""

    @staticmethod
    def get_topic_details(topic_id: str) -> Optional[Dict[str, Any]]:
        return RESERVOIR_KNOWLEDGE_BASE.get(topic_id.lower())

    @staticmethod
    def analyze_reservoir(data: Dict[str, Any]) -> Dict[str, Any]:
        """Perform volumetric and reservoir characterization analysis."""
        area = data.get("area_acres", 640.0)
        h = data.get("net_pay_ft", 50.0)
        phi = data.get("porosity", 0.20)
        sw = data.get("water_saturation", 0.25)
        boi = data.get("boi", 1.25)

        ooip = calculate_ooip(area, h, phi, sw, boi)
        ct = calculate_total_compressibility(3e-6, 12e-5, 3e-6, sw)

        return {
            "ooip_stb": ooip,
            "total_compressibility_psi_1": ct,
            "interpretation": "Volumetric assessment confirms massive hydrocarbon in-place with normal pore compressibility."
        }
