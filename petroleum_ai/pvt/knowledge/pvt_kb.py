"""
Advanced Petroleum Fluid Knowledge Base (PFIE) adhering to SPE and textbook standards.
Covers fluid classifications, phase behavior, PVT lab tests, and EOS fundamentals.
"""

from __future__ import annotations
from typing import Dict, Any

PVT_KNOWLEDGE_BASE: Dict[str, Dict[str, Any]] = {
    "black_oil": {
        "title": "Black Oil (Low-Shrinkage Crude Oil)",
        "definition": "A robust crude oil system characterized by relatively low gas-oil ratio (GOR < 2000 scf/STB), heavy stock-tank oil API gravity (< 45° API), and dark green to black color.",
        "physical_meaning": "Composed of heavy hydrocarbon molecules with moderate amounts of intermediate and light components.",
        "engineering_importance": "Represents the most common conventional reservoir fluid where surface conditions result in significant liquid recovery.",
        "required_inputs": ["api_gravity", "gas_gravity", "bubble_point_pressure", "temperature"],
        "equations": ["Standing / Vasquez-Beggs / Glaso correlations for Bo and Rs"],
        "units": {"api": "°API", "gor": "scf/STB", "pressure": "psia"},
        "assumptions": ["Two-component or multi-component black oil approximation"],
        "limitations": ["Inaccurate for volatile or near-critical systems near saturation pressure"],
        "practical_interpretation": "Standard black oil models are reliable for primary and secondary recovery evaluations.",
        "field_examples": "Ghawar Field, Prudhoe Bay conventional oil reservoirs.",
        "troubleshooting": "High GOR anomalies indicate transition to volatile oil or gas cap expansion.",
        "common_mistakes": "Applying black oil correlations to volatile or gas condensate reservoirs.",
        "confidence": "High",
        "references": ["Standing, M.B., Volumetric and Phase Behavior of Oil Field Hydrocarbon Systems", "Tarek Ahmed, Reservoir Engineering Handbook"]
    },
    "volatile_oil": {
        "title": "Volatile Oil (High-Shrinkage Crude Oil)",
        "definition": "A fluid system with GOR between 2000 and 3300 scf/STB, stock-tank oil gravity between 45° and 55° API, and high liquid shrinkage below bubble point.",
        "physical_meaning": "Contains a high percentage of intermediate hydrocarbons (C2 through C6).",
        "engineering_importance": "Exhibits rapid phase behavior changes near saturation pressure requiring compositional tracking.",
        "required_inputs": ["compositional_analysis", "separator_tests", "bubble_point_pressure"],
        "equations": ["EOS Peng-Robinson / Redlich-Kwong"],
        "units": {"gor": "scf/STB", "shrinkage": "fraction"},
        "assumptions": ["Multi-component fluid behavior"],
        "limitations": ["Standard empirical correlations have higher uncertainty for volatile oils"],
        "practical_interpretation": "Requires EOS tuning to capture retrograde vaporization effects near wellbore.",
        "field_examples": "Deepwater Gulf of Mexico volatile oil reservoirs.",
        "troubleshooting": "Severe wellbore productivity loss if flowing pressure drops below bubble point.",
        "common_mistakes": "Using standard black oil Bo correlations without compositional adjustment.",
        "confidence": "High",
        "references": ["Dake, L.P., Fundamentals of Reservoir Engineering", "SPE Monograph on Phase Behavior"]
    },
    "gas_condensate": {
        "title": "Gas Condensate Reservoir Fluid",
        "definition": "A single-phase gas phase in the reservoir that undergoes retrograde condensation as pressure declines below the dew point.",
        "physical_meaning": "Rich in intermediate and heavy hydrocarbon components dissolved in a methane/ethane gas matrix.",
        "engineering_importance": "Prone to liquid dropout in the reservoir, causing severe permeability impairment around the wellbore.",
        "required_inputs": ["dew_point_pressure", "gas_gravity", "condensate_gas_ratio"],
        "equations": ["Z-factor (Dranchuk-Abou-Kassem), Retrograde liquid saturation models"],
        "units": {"cgr": "STB/MMscf", "pressure": "psia"},
        "assumptions": ["Single phase initial state above dew point"],
        "limitations": ["Requires constant pressure depletion (CVD) lab data for accurate modeling"],
        "practical_interpretation": "Cycling (gas injection) or pressure maintenance is often required to prevent liquid blockage.",
        "field_examples": "North Field (Qatar), Arun Field (Indonesia).",
        "troubleshooting": "Productivity decline due to liquid accumulation near wellbore (condensate bank).",
        "common_mistakes": "Treating gas condensate as dry gas during depletion planning.",
        "confidence": "High",
        "references": ["Craft & Hawkins", "Whitson & Brule, Phase Behavior"]
    },
    "dry_gas": {
        "title": "Dry Gas Reservoir Fluid",
        "definition": "Hydrocarbon fluid that remains entirely in the gaseous phase in the reservoir and at surface conditions (no liquid dropout).",
        "physical_meaning": "Composed almost entirely of methane with very low heavier hydrocarbon fractions.",
        "engineering_importance": "Simplified phase behavior governed by real gas law and gas compressibility factor Z.",
        "required_inputs": ["gas_gravity", "temperature", "pressure"],
        "equations": ["Real Gas Law: p * V = z * n * R * T", "Standing-Katz Z-factor chart (Hall-Yarborough / Dranchuk-Abou-Kassem)"],
        "units": {"gravity": "dimensionless (air=1)", "z_factor": "dimensionless"},
        "assumptions": ["Single-phase gas throughout depletion"],
        "limitations": ["High-pressure deviation from ideal gas law requires accurate Z-factor"],
        "practical_interpretation": "Straightforward volumetric depletion calculations using material balance (p/z vs Gp).",
        "field_examples": "Hugoton Gas Field.",
        "troubleshooting": "Water production condensation requiring dehydration.",
        "common_mistakes": "Assuming ideal gas behavior at high reservoir pressures (> 3000 psia).",
        "confidence": "High",
        "references": ["Standing, M.B.", "Tarek Ahmed"]
    }
}
