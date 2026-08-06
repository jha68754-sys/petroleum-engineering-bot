"""
Comprehensive Well Testing Engineering Knowledge Base adhering to SPE standards.
Covers Pressure Drawdown, Build-up, Horner Plot, Skin Factor, Wellbore Storage,
Radius of Investigation, Transmissibility, Flow Efficiency, and Type Curve Matching.
"""

from __future__ import annotations
from typing import Dict, Any

WELL_TESTING_KNOWLEDGE_BASE: Dict[str, Dict[str, Any]] = {
    "pressure_drawdown": {
        "title": "Pressure Drawdown Testing",
        "definition": "A test conducted at a constant flow rate while recording bottomhole pressure as a function of time.",
        "physical_meaning": "Measures reservoir transmissibility, average reservoir pressure, and skin factor under transient flow.",
        "engineering_importance": "Evaluates initial well deliverability and reservoir flow capacity.",
        "required_inputs": ["q_rate_stb_day", "flowing_pressure_psi", "initial_pressure_psi", "mu_cp", "bo", "h_ft", "k_md"],
        "equations": ["p_wf = p_i - (162.6 * q * B * mu / (k * h)) * (log(t) + log(k / (phi * mu * c_t * r_w^2)) - 3.23 + 0.868s)"],
        "units": {"q": "STB/day", "pressure": "psia", "time": "hours", "permeability": "mD"},
        "assumptions": ["Single phase flow", "Homogeneous infinite acting reservoir", "Constant flow rate"],
        "limitations": ["Difficult to maintain strictly constant rate in field operations"],
        "practical_interpretation": "Semi-log straight line slope yields permeability; intercept yields skin factor.",
        "field_examples": "Offshore exploration well testing.",
        "troubleshooting": "Rate fluctuations during test.",
        "common_mistakes": "Reading pressure before stabilization.",
        "confidence": "High",
        "references": ["Earlougher, R.C., Advances in Well Test Analysis (SPE Monograph)", "SPE Petroleum Engineering Handbook"]
    },
    "horner_buildup": {
        "title": "Horner Pressure Build-up Testing",
        "definition": "Shutting in a well after a period of production and recording pressure recovery as a function of shut-in time.",
        "physical_meaning": "Removes rate transients during production and establishes static reservoir pressure (p*).",
        "engineering_importance": "Most reliable method for determining undisturbed reservoir pressure and skin factor.",
        "required_inputs": ["p_ws_psi", "t_p_hrs", "delta_t_hrs", "q_rate_stb_day", "mu_cp", "bo", "h_ft", "k_md"],
        "equations": ["p_ws = p_i - (162.6 * q * B * mu / (k * h)) * log((t_p + delta_t) / delta_t)"],
        "units": {"pressure": "psia", "time": "hours"},
        "assumptions": ["Constant production rate before shut-in (tp)", "Superposition principle applies"],
        "limitations": ["Requires accurate cumulative production time (tp)"],
        "practical_interpretation": "Horner time ratio (tp + delta_t) / delta_t plotted against p_ws on semi-log scale.",
        "field_examples": "Production well routine annual testing.",
        "troubleshooting": "Afterflow distortion at early shut-in times.",
        "common_mistakes": "Incorrect producing time tp estimation.",
        "confidence": "High",
        "references": ["Horner, D.R., Pressure Build-Up in Wells (Proceedings Third World Petroleum Congress)"]
    },
    "skin_factor": {
        "title": "Skin Factor & Wellbore Damage",
        "definition": "A dimensionless quantity (s) representing a localized pressure drop near the wellbore due to formation damage or stimulation.",
        "physical_meaning": "Quantifies formation impairment (s > 0) or hydraulic enhancement (s < 0).",
        "engineering_importance": "Determines if well stimulation (acidizing/fracturing) is required.",
        "required_inputs": ["delta_p_skin_psi", "flow_rate", "permeability"],
        "equations": ["delta_p_skin = 0.869 * m * s"],
        "units": {"skin": "dimensionless", "pressure": "psi"},
        "assumptions": ["Radial steady or unsteady flow near wellbore"],
        "limitations": ["Assumes skin is infinitesimally thin unless extended skin model is used"],
        "practical_interpretation": "s > +5 indicates severe wellbore damage.",
        "field_examples": "Drilling mud filtrate invasion.",
        "troubleshooting": "High skin despite good permeability.",
        "common_mistakes": "Conflating wellbore storage pressure drop with skin.",
        "confidence": "High",
        "references": ["Hawkins, M.F., A Note on the Skin Effect (JPT, 1956)"]
    },
    "radius_of_investigation": {
        "title": "Radius of Investigation (r_i)",
        "definition": "The maximum distance into the reservoir from which pressure transient signals have reached the wellbore.",
        "physical_meaning": "Indicates the depth of reservoir explored during a transient test.",
        "engineering_importance": "Ensures test duration is sufficient to reach boundaries or drainage limits.",
        "required_inputs": ["t_hrs", "k_md", "phi", "mu_cp", "c_t_psi_1"],
        "equations": ["r_i = 0.029 * sqrt((k * t) / (phi * mu * c_t))"],
        "units": {"radius": "feet", "time": "hours", "permeability": "mD"},
        "assumptions": ["Radial diffusivity equation applies"],
        "limitations": ["Approximation valid for infinite-acting radial flow"],
        "practical_interpretation": "Larger shut-in time increases investigation radius.",
        "field_examples": "Detecting outer fault barriers.",
        "troubleshooting": "Stopping test before reaching target reservoir sector.",
        "common_mistakes": "Ignoring compressibility variations.",
        "confidence": "High",
        "references": ["Lee, J., Well Testing (SPE Textbook Series)"]
    }
}
