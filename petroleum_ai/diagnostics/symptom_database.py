"""
Symptom and Root Cause Database for Petroleum Engineering Diagnostic Intelligence (PEDI).
Covers production decline, water breakthrough, scaling, sand production, and artificial lift failure.
"""

from __future__ import annotations
from typing import Dict, Any

SYMPTOM_DATABASE: Dict[str, Dict[str, Any]] = {
    "production_decline": {
        "symptom": "Production Decline",
        "description": "Sudden or progressive decrease in oil and gas production rate from historical trend.",
        "potential_causes": [
            "Reservoir Pressure Depletion",
            "Skin Damage / Formation Damage",
            "Water Breakthrough / Coning",
            "Scale Deposition in Tubing",
            "ESP Degradation or Pump-off"
        ],
        "required_evidence": ["Reservoir Pressure Pr", "Flowing Bottom-Hole Pressure Pwf", "Water Cut", "GOR"],
        "confidence": "High",
        "references": ["Economides, Petroleum Production Systems", "Craft & Hawkins"]
    },
    "high_water_cut": {
        "title": "High Water Cut Increase",
        "definition": "Rapid or steady rise in produced water ratio relative to total liquid production.",
        "physical_meaning": "Water encroaching from aquifer or injected water breakthrough through high-permeability streaks.",
        "engineering_importance": "Reduces effective oil relative permeability and increases hydrostatic backpressure on formation.",
        "required_inputs": ["water_cut", "reservoir_pressure", "offset_injector_rates"],
        "equations": ["Fractional Flow Equation (Buckley-Leverett)"],
        "confidence": "High",
        "references": ["Dake, Fundamentals of Reservoir Engineering"]
    }
}
