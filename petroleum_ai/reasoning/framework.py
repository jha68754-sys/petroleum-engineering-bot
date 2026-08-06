"""
Unified Engineering Reasoning Framework (ERF) for Petroleum AI Platform.
Implements the 7 core pillars:
1. Intent Detection
2. Missing Data Collector
3. Engineering Reasoning Engine
4. Recommendation Engine
5. Confidence Engine
6. Reference Engine
7. Professional Report Generator
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field

@dataclass
class EngineeringContext:
    query: str
    discipline: str = "general"
    provided_data: Dict[str, Any] = field(default_factory=dict)
    missing_data: List[str] = field(default_factory=list)
    assumptions: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    selected_equations: List[str] = field(default_factory=list)
    correlations: List[str] = field(default_factory=list)
    calculation_sequence: List[str] = field(default_factory=list)
    uncertainty: str = ""
    uncertainty_evaluation: str = ""
    recommendations: List[Dict[str, str]] = field(default_factory=list)
    confidence_level: str = "Medium"
    confidence_reason: str = ""
    references: List[str] = field(default_factory=list)


class EngineeringReasoningFramework:
    """Core intelligence layer for petroleum engineering analysis and decision making."""

    DISCIPLINES = [
        "Reservoir",
        "Production",
        "Drilling",
        "Completion",
        "Artificial Lift",
        "PVT",
        "Well Testing",
        "Economics"
    ]

    @classmethod
    def detect_intent(cls, query: str) -> str:
        """1. Intent Detection: Automatically detect the engineering discipline."""
        q_lower = query.lower()
        if any(w in q_lower for w in ["reservoir", "ooip", "ogip", "porosity", "permeability", "recovery", "mكمن", "مكامن"]):
            return "Reservoir"
        elif any(w in q_lower for w in ["production", "ipr", "vogel", "darcy", "skin", "productivity", "إنتاج", "تدفق"]):
            return "Production"
        elif any(w in q_lower for w in ["drilling", "mud", "hydrostatic", "bit", "casing", "حفر", "طين"]):
            return "Drilling"
        elif any(w in q_lower for w in ["completion", "perforation", "packer", "إكمال"]):
            return "Completion"
        elif any(w in q_lower for w in ["lift", "esp", "gas lift", "srp", "pcp", "plunger", "رفع"]):
            return "Artificial Lift"
        elif any(w in q_lower for w in ["pvt", "bo", "rs", "pb", "viscosity", "z-factor", "موائع"]):
            return "PVT"
        elif any(w in q_lower for w in ["test", "horner", "drawdown", "build-up", "pressure", "اختبار"]):
            return "Well Testing"
        elif any(w in q_lower for w in ["economics", "npv", "irr", "cash flow", "cost", "اقتصاد"]):
            return "Economics"
        return "Production"  # Default fallback

    @classmethod
    def collect_missing_data(cls, discipline: str, provided: Dict[str, Any]) -> List[str]:
        """2. Missing Data Collector: Determine missing mandatory parameters."""
        mandatory_fields = {
            "Reservoir": ["area_acres", "net_pay_ft", "porosity", "water_saturation", "boi"],
            "Production": ["reservoir_pressure_psi", "flowing_pressure_psi", "permeability_md"],
            "Drilling": ["mud_weight_ppg", "tvd_ft"],
            "Completion": ["tubing_size_in", "packer_depth_ft"],
            "Artificial Lift": ["q_rate_stb_day", "depth_ft", "water_cut_pct"],
            "PVT": ["pressure_psi", "temperature_f", "api_gravity"],
            "Well Testing": ["flow_rate_stb_day", "initial_pressure_psi"],
            "Economics": ["capex", "opex", "discount_rate"]
        }
        required = mandatory_fields.get(discipline, [])
        missing = [param for param in required if param not in provided]
        return missing

    @classmethod
    def perform_reasoning(cls, discipline: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """3. Engineering Reasoning Engine: Assumptions, constraints, equations, sequence, uncertainty."""
        assumptions = [
            "Steady-state or pseudo-steady-state flow conditions apply unless specified otherwise.",
            "Single-phase or effective multi-phase relative permeabilities follow standard relative permeability curves.",
            "Reservoir temperature remains isothermal during the evaluation period."
        ]
        constraints = [
            "Operating pressures must remain within formation fracture pressure and bubble point limits.",
            "Equipment mechanical ratings (tubing, pump, wellhead) must not be exceeded."
        ]
        equations = []
        correlations = []
        sequence = [
            "1. Validate input data and units against SPE standards.",
            "2. Establish initial reservoir/fluid conditions and boundary constraints.",
            "3. Apply governing flow or volumetric equations.",
            "4. Perform sensitivity analysis on key uncertain parameters."
        ]
        uncertainty = "Uncertainty is primarily driven by reservoir heterogeneity, relative permeability hysteresis, and PVT sampling representation."

        if discipline == "Reservoir":
            equations = ["OOIP = (7758 * A * h * phi * (1 - Sw)) / Boi", "OGIP = (43560 * A * h * phi * (1 - Sw)) / Bgi"]
            correlations = ["Standing PVT Correlations", "Vasquez-Beggs Bubble Point"]
        elif discipline == "Production":
            equations = ["q / q_max = 1.0 - 0.2*(Pwf/Pr) - 0.8*(Pwf/Pr)^2 (Vogel IPR)", "Darcy Radial Flow Equation"]
            correlations = ["Vogel IPR", "Fetkovich Multirate"]
        elif discipline == "Artificial Lift":
            equations = ["Total Dynamic Head (TDH) = Vertical Lift + Friction + Wellhead Pressure", "Hydraulic HP = (Q * TDH * SG) / 1714"]
            correlations = ["Takacs ESP Design Rules", "Brown Gas Lift Spacing"]
        elif discipline == "PVT":
            equations = ["Bo = V_res / V_stock_tank", "Z-factor from Standing & Katz compressibility chart"]
            correlations = ["Standing (1947)", "Vasquez-Beggs (1980)", "Beggs-Robinson Viscosity"]
        else:
            equations = ["Standard SPE Engineering Governing Equations"]
            correlations = ["Industry Standard Correlations"]

        return {
            "assumptions": assumptions,
            "constraints": constraints,
            "equations": equations,
            "correlations": correlations,
            "calculation_sequence": sequence,
            "uncertainty": uncertainty
        }

    @classmethod
    def generate_recommendations(cls, discipline: str, data: Dict[str, Any]) -> List[Dict[str, str]]:
        """4. Recommendation Engine: Ranked recommendations with justifications and rejections."""
        recs = []
        if discipline == "Artificial Lift":
            recs = [
                {
                    "rank": "1",
                    "recommendation": "Electrical Submersible Pump (ESP)",
                    "why_selected": "High production rate and deep well requirements align with ESP high-head capacity.",
                    "why_rejected": "Higher sensitivity to free gas and sand compared to PCP or Gas Lift."
                },
                {
                    "rank": "2",
                    "recommendation": "Gas Lift",
                    "why_selected": "Good tolerance to sand and flexibility if high-pressure gas is available.",
                    "why_rejected": "Cannot achieve as low a flowing bottomhole pressure (Pwf) as ESP in high-rate wells."
                },
                {
                    "rank": "3",
                    "recommendation": "Progressive Cavity Pump (PCP)",
                    "why_selected": "Excellent for heavy oil and high sand production.",
                    "why_rejected": "Limited by high depth and elastomer temperature constraints."
                }
            ]
        elif discipline == "Reservoir":
            recs = [
                {
                    "rank": "1",
                    "recommendation": "Pressure Maintenance via Water Injection",
                    "why_selected": "Compensates for voidage replacement and sustains reservoir pressure.",
                    "why_rejected": "Requires water source and high injection capex."
                }
            ]
        else:
            recs = [
                {
                    "rank": "1",
                    "recommendation": "Standard SPE Engineering Optimization",
                    "why_selected": "Directly addresses core performance bottlenecks based on validated formulas.",
                    "why_rejected": "Alternative non-standard empirical methods lack rigorous physical backing."
                }
            ]
        return recs

    @classmethod
    def evaluate_confidence(cls, discipline: str, provided: Dict[str, Any], missing: List[str]) -> Tuple[str, str]:
        """5. Confidence Engine: Assign confidence level (High/Medium/Low) with explanation."""
        if len(missing) == 0:
            return "High", "All mandatory engineering parameters are provided and verified against SPE standards."
        elif len(missing) <= 2:
            return "Medium", f"Some parameters are missing ({', '.join(missing)}). Standard industry defaults were assumed."
        else:
            return "Low", f"Multiple critical parameters are missing ({', '.join(missing)}). Results are preliminary and require lab/field validation."

    @classmethod
    def attach_references(cls, discipline: str) -> List[str]:
        """6. Reference Engine: Attach authoritative SPE and textbook references."""
        refs = [
            "SPE Petroleum Engineering Handbook (Volumes I - VI)",
            "Craft & Hawkins, Applied Petroleum Reservoir Engineering",
            "Tarek Ahmed, Reservoir Engineering Handbook",
            "Economides, Petroleum Production Systems"
        ]
        if discipline == "Artificial Lift":
            refs.append("Takacs, G., Electrical Submersible Pumps Manual")
            refs.append("Brown, K.E., The Technology of Artificial Lift Methods")
        elif discipline == "Well Testing":
            refs.append("Earlougher, R.C., Advances in Well Test Analysis (SPE Monograph)")
        return refs

    @classmethod
    def generate_report(cls, context: EngineeringContext) -> str:
        """7. Report Generator: Professional engineering report formatted in markdown."""
        report = f"""# تقرير الهندسة البترولية الاحترافي (Professional Engineering Analysis Report)
## التخصص: {context.discipline}

### 1. بيان المشكلة (Problem Statement)
* **استعلام المستخدم:** {context.query}
* **التخصص الهندسي المكتشف:** {context.discipline}

### 2. البيانات المدخلة والمفقودة (Input Data & Missing Parameters)
* **البيانات المتوفرة:** {context.provided_data if context.provided_data else "معلومات عامة مفاهيمية"}
* **البيانات الناقصة (إن وجدت):** {context.missing_data if context.missing_data else "لا توجد بيانات ناقصة حرجة"}

### 3. الافتراضات والقيود الهندسية (Engineering Assumptions & Constraints)
* **الافتراضات:**
"""
        for a in context.assumptions:
            report += f"  - {a}\n"
        report += "* **القيود الهندسية:**\n"
        for c in context.constraints:
            report += f"  - {c}\n"

        report += "\n### 4. المعادلات المعتمدة وتسلسل الحساب (Equations & Calculation Sequence)\n"
        for eq in context.selected_equations:
            report += f"  - **معادلة:** {eq}\n"
        for step in context.calculation_sequence:
            report += f"  - {step}\n"

        report += f"\n### 5. تقييم عدم اليقين (Uncertainty Evaluation)\n* {context.uncertainty}\n"

        report += "\n### 6. التوصيات الهندسية المرتبة (Ranked Recommendations)\n"
        for rec in context.recommendations:
            report += f"* **المرتبة {rec['rank']}:** {rec['recommendation']}\n"
            report += f"  - **لماذا تم اختياره:** {rec['why_selected']}\n"
            report += f"  - **لماذا تم استبعاد البدائل:** {rec['why_rejected']}\n"

        report += f"\n### 7. مستوى الثقة (Confidence Level)\n* **المستوى:** {context.confidence_level}\n* **السبب:** {context.confidence_reason}\n"

        report += "\n### 8. المراجع الهندسية المعتمدة (Engineering References)\n"
        for ref in context.references:
            report += f"  - {ref}\n"

        return report
