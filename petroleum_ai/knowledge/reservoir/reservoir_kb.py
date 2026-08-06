"""
Comprehensive Reservoir Engineering Knowledge Base adhering to SPE standards.
Covers Reservoir Characterization, Porosity, Permeability, Net Pay, Water Saturation,
Volumetrics (OOIP/OGIP), Material Balance, Drive Mechanisms, Compressibility, and Flow Units.
"""

from __future__ import annotations
from typing import Dict, Any

RESERVOIR_KNOWLEDGE_BASE: Dict[str, Dict[str, Any]] = {
    "reservoir_characterization": {
        "title": "Reservoir Characterization & Petrophysics",
        "definition": "The comprehensive process of estimating reservoir properties (porosity, permeability, saturation) using core, log, and seismic data.",
        "physical_meaning": "Defines storage capacity and fluid flow pathways within porous geological formations.",
        "engineering_importance": "Fundamental for reserves estimation, flow modeling, and field development planning.",
        "required_inputs": ["bulk_volume", "pore_volume", "net_pay_ft", "porosity", "water_saturation"],
        "equations": ["phi = V_pore / V_bulk", "S_w = V_water / V_pore", "h_net = sum(h_i where phi >= phi_cutoff)"],
        "units": {"porosity": "fraction", "saturation": "fraction", "length": "feet"},
        "assumptions": ["Representative core/log sampling", "Clean formation matrix"],
        "limitations": ["Heterogeneity scale-up uncertainty"],
        "practical_interpretation": "High porosity and low water saturation indicate high hydrocarbon storage potential.",
        "field_examples": "Sandstone and carbonate reservoir evaluation.",
        "troubleshooting": "Clay bound water interference in resistivity logs.",
        "common_mistakes": "Conflating total porosity with effective porosity.",
        "confidence": "High",
        "references": ["Tiab & Donaldson, Petrophysics", "SPE Petroleum Engineering Handbook"]
    },
    "volumetrics_ooip_ogip": {
        "title": "Volumetric Reserves Estimation (OOIP & OGIP)",
        "definition": "Calculating initial oil and gas in place based on volumetric reservoir geometry and rock/fluid properties.",
        "physical_meaning": "Total volume of hydrocarbons residing in the reservoir at initial conditions.",
        "engineering_importance": "Establishes baseline reserves before production initiation.",
        "required_inputs": ["area_acres", "net_pay_ft", "porosity", "water_saturation", "boi_or_bgi"],
        "equations": [
            "OOIP (STB) = (7758 * A * h * phi * (1 - Sw)) / Boi",
            "OGIP (scf) = (43560 * A * h * phi * (1 - Sw)) / Bgi"
        ],
        "units": {"area": "acres", "thickness": "ft", "OOIP": "STB", "OGIP": "scf"},
        "assumptions": ["Uniform rock and fluid properties across area A", "Hydrostatic equilibrium"],
        "limitations": ["Uncertainty in areal extent and net pay cutoffs"],
        "practical_interpretation": "Primary input for reserve classification (1P, 2P, 3P).",
        "field_examples": "Giant Middle Eastern carbonate reservoirs.",
        "troubleshooting": "Inaccurate OWC / GWC depth mapping.",
        "common_mistakes": "Unit conversion errors between acres-feet and barrels.",
        "confidence": "High",
        "references": ["Craft & Hawkins, Applied Petroleum Reservoir Engineering"]
    },
    "material_balance": {
        "title": "Reservoir Material Balance Equation (MBE)",
        "definition": "A conservation of mass principle applied to hydrocarbon reservoirs equating cumulative production to expansion and influx.",
        "physical_meaning": "Tracks pressure drop against cumulative fluid withdrawal to determine original reserves and drive mechanisms.",
        "engineering_importance": "Dynamic method to calculate OOIP/OGIP independent of volumetric mapping.",
        "required_inputs": ["p_i", "p_bar", "np", "rp", "bo", "boi", "bg", "bgi"],
        "equations": ["N * (E_o + m * E_g + E_fw) = N_p * (B_o + (R_p - R_s) * B_g) + W_p * B_w - W_e"],
        "units": {"pressure": "psia", "production": "STB or scf"},
        "assumptions": ["Volumetric or water-drive system", "Uniform pressure depletion"],
        "limitations": ["Sensitive to pressure measurement errors and PVT data"],
        "practical_interpretation": "Havlena-Odeh straight line plots identify drive mechanisms and actual OOIP.",
        "field_examples": "Depletion drive and water injection tracking.",
        "troubleshooting": "Scatter in Havlena-Odeh plot due to multi-layer pressure averaging.",
        "common_mistakes": "Ignoring aquifer influx (We) in water-driven systems.",
        "confidence": "High",
        "references": ["Dake, L.P., Fundamentals of Reservoir Engineering"]
    },
    "compressibility_and_drive": {
        "title": "Rock/Fluid Compressibility & Drive Mechanisms",
        "definition": "Study of how pore volume and fluid volumes change with pressure, dictating natural reservoir drive energy.",
        "physical_meaning": "Energy source driving hydrocarbons to the wellbore.",
        "engineering_importance": "Determines primary recovery factor and pressure maintenance timing.",
        "required_inputs": ["c_f", "c_o", "c_g", "c_w", "sw"],
        "equations": ["c_t = c_f + c_o * S_o + c_w * S_w + c_g * S_g"],
        "units": {"compressibility": "psi^-1"},
        "assumptions": ["Isothermal compressibility"],
        "limitations": ["Stress-dependent permeability and porosity at high depletion"],
        "practical_interpretation": "Gas cap and water drive provide superior recovery compared to solution gas drive.",
        "field_examples": "Under-saturated vs. saturated reservoirs.",
        "troubleshooting": "Abnormal pore compressibility in unconsolidated sands.",
        "common_mistakes": "Neglecting formation compressibility (cf) in high pressure overpressured reservoirs.",
        "confidence": "High",
        "references": ["Ahmed, T., Reservoir Engineering Handbook"]
    }
}
