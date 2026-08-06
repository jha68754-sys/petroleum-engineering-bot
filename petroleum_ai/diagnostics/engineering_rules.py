"""
Explainable Engineering Decision Rules for PEDI.
"""

from __future__ import annotations
from typing import Dict, Any

class EngineeringRules:
    """Rule engine for deterministic diagnostic decision-making."""

    @staticmethod
    def evaluate_rules(data: Dict[str, Any]) -> Dict[str, Any]:
        water_cut_increasing = data.get("water_cut_increasing", False)
        pressure_stable = data.get("reservoir_pressure_stable", True)
        gor_increasing = data.get("gor_increasing", False)

        diagnosis = "General Production Decline"
        explanation = "Standard production monitoring active."

        if water_cut_increasing and pressure_stable:
            diagnosis = "Water Breakthrough / Coning"
            explanation = "Water cut is increasing while reservoir pressure remains stable, indicating edge/bottom water encroachment rather than volumetric depletion."
        elif gor_increasing and pressure_stable:
            diagnosis = "Gas Breakthrough / Gas Cap Expansion"
            explanation = "Gas-Oil Ratio is rising under stable reservoir pressure, pointing to gas cap coning or free gas breakout."
        elif not pressure_stable and not water_cut_increasing:
            diagnosis = "Reservoir Pressure Depletion"
            explanation = "Pressure decline without water or gas breakthrough confirms volumetric depletion in a solution-gas drive reservoir."

        return {
            "diagnosis": diagnosis,
            "explanation": explanation,
            "confidence": "High"
        }
