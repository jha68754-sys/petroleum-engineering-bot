"""
Data models and TypedDict structures for the Artificial Lift Engineering Module.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from typing_extensions import TypedDict

class LiftSystemDetails(TypedDict):
    system_id: str
    name_en: str
    name_ar: str
    theory_ar: str
    selection_criteria_ar: List[str]
    advantages_ar: List[str]
    limitations_ar: List[str]
    design_parameters_ar: List[str]
    key_equations_ar: List[str]
    field_applications_ar: List[str]
    troubleshooting_ar: List[str]
    failure_analysis_ar: List[str]
    reference: str
    confidence: str

class LiftScreeningInput(TypedDict):
    q_rate_stb_day: float
    depth_ft: float
    gor_scf_stb: float
    water_cut_pct: float
    viscosity_cp: float
    sand_content: bool
    temperature_f: float
    offshore: bool

class LiftScreeningResult(TypedDict):
    recommended_system: str
    suitability_score: float
    reasoning_ar: str
    alternative_systems: List[str]
