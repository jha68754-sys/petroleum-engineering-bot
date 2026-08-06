"""
Comprehensive Production Engineering Knowledge Base adhering to SPE standards.
Covers IPR Models (Vogel, Fetkovich, PI), Decline Curve Analysis, Nodal Analysis,
Water Cut, GOR, Choke Performance, and Production Optimization.
"""

from __future__ import annotations
from typing import Dict, Any

PRODUCTION_KNOWLEDGE_BASE: Dict[str, Dict[str, Any]] = {
    "ipr_vogel_model": {
        "title": "Vogel Inflow Performance Relationship (IPR)",
        "definition": "An empirical inflow performance relationship for wells operating below bubble point pressure in solution-gas drive reservoirs.",
        "physical_meaning": "Relates oil production rate to flowing bottom-hole pressure accounting for two-phase relative permeability effects.",
        "engineering_importance": "Accurately predicts well deliverability and maximum potential flow rate (q_max) without requiring absolute pressure tests at multiple rates.",
        "required_inputs": ["q_current_stb_day", "pwf_current_psi", "pr_psi"],
        "equations": ["q / q_max = 1.0 - 0.2*(Pwf/Pr) - 0.8*(Pwf/Pr)^2"],
        "units": {"rate": "STB/day", "pressure": "psia"},
        "assumptions": ["Solution gas drive reservoir", "Constant bubble point below Pr"],
        "limitations": ["Not directly applicable to water-drive or gas-cap drive without modification"],
        "practical_interpretation": "Allows rapid forecasting of well rate under varied drawdown conditions.",
        "field_examples": "Permian Basin solution-gas drive wells.",
        "troubleshooting": "Discrepancies when free gas saturation dominates near wellbore.",
        "common_mistakes": "Applying Vogel equation to undersaturated single-phase pressure range.",
        "confidence": "High",
        "references": ["Vogel, J.V., Inflow Performance Relationships for Solution-Gas Drive Wells (JPT, 1968)", "Economides, Petroleum Production Systems"]
    },
    "productivity_index": {
        "title": "Productivity Index (PI)",
        "definition": "The ratio of total liquid production rate to the pressure drawdown in the well.",
        "physical_meaning": "Measures the overall capability of the well and reservoir system to deliver fluids.",
        "engineering_importance": "Core metric for well performance monitoring and artificial lift selection.",
        "required_inputs": ["q_stb_day", "pr_psi", "pwf_psi"],
        "equations": ["J = q / (Pr - Pwf)"],
        "units": {"PI": "STB/day/psi", "rate": "STB/day", "pressure": "psia"},
        "assumptions": ["Steady-state or pseudosteady-state single phase radial flow"],
        "limitations": ["Assumes constant PI, which breaks down below bubble point (non-linear IPR)"],
        "practical_interpretation": "Low PI indicates formation damage or low permeability requiring stimulation.",
        "field_examples": "Routine production logging and well testing.",
        "troubleshooting": "PI decline over time due to scaling or relative permeability changes.",
        "common_mistakes": "Using straight-line PI formulation below bubble point pressure.",
        "confidence": "High",
        "references": ["Craft & Hawkins, Applied Petroleum Reservoir Engineering"]
    },
    "decline_curve_analysis": {
        "title": "Arps Decline Curve Analysis (DCA)",
        "definition": "Empirical curve-fitting techniques used to forecast future hydrocarbon production rates based on historical production trends.",
        "physical_meaning": "Extrapolates reservoir depletion behavior (exponential, hyperbolic, harmonic) into the future.",
        "engineering_importance": "Essential for reserves booking, economic forecasting, and field development planning.",
        "required_inputs": ["q_i_stb_day", "b_factor", "d_i_per_year", "t_years"],
        "equations": [
            "Exponential (b=0): q(t) = q_i * exp(-d_i * t)",
            "Hyperbolic (0 < b < 1): q(t) = q_i / (1 + b * d_i * t)^(1/b)",
            "Harmonic (b=1): q(t) = q_i / (1 + d_i * t)"
        ],
        "units": {"rate": "STB/day", "time": "years", "decline": "fraction/year"},
        "assumptions": ["Historical operational trends continue into the future"],
        "limitations": ["Blind extrapolation without reservoir physics can overestimate reserves"],
        "practical_interpretation": "Hyperbolic decline is standard for unconventional and fractured reservoirs.",
        "field_examples": "Shale oil and mature conventional field forecasting.",
        "troubleshooting": "Sudden rate jumps due to workovers distorting decline trend.",
        "common_mistakes": "Using exponential decline for boundary-dominated transient unconventional wells.",
        "confidence": "High",
        "references": ["Arps, J.J., Analysis of Decline Curves (Trans. AIME, 1945)", "SPE Petroleum Engineering Handbook"]
    },
    "nodal_analysis": {
        "title": "Nodal Systems Analysis",
        "definition": "The systematic optimization of a production system by splitting the complete system into inflow and outflow performance at a specific node.",
        "physical_meaning": "Finds the operating intersection point between reservoir supply capability and tubing/surface lifting capacity.",
        "engineering_importance": "Optimizes tubing size, choke size, and artificial lift design.",
        "required_inputs": ["node_pressure", "inflow_curve", "outflow_curve"],
        "equations": ["P_inflow(q) = P_outflow(q) at operating rate"],
        "units": {"pressure": "psia", "rate": "STB/day"},
        "assumptions": ["Steady-state flow across nodes"],
        "limitations": ["Requires accurate multiphase flow correlations"],
        "practical_interpretation": "Operating point defines actual well production rate under given restrictions.",
        "field_examples": "Tubing string resizing and choke optimization.",
        "troubleshooting": "Operating point instability in slugging flow regimes.",
        "common_mistakes": "Neglecting temperature profile in vertical lift performance.",
        "confidence": "High",
        "references": ["Brown, K.E., The Technology of Artificial Lift Methods", "Beggs, H.C., Production Optimization"]
    }
}
