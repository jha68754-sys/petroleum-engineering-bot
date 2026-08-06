"""
Artificial Lift Engineering Engine: Screening, Decision Support, Calculations, and Troubleshooting.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from artificial_lift_kb import ARTIFICIAL_LIFT_KNOWLEDGE_BASE
from models.artificial_lift_models import LiftScreeningInput, LiftScreeningResult, LiftSystemDetails

class ArtificialLiftEngine:
    """Advanced engineering reasoning and screening engine for artificial lift selection."""

    @staticmethod
    def get_system_details(system_id: str) -> Optional[LiftSystemDetails]:
        return ARTIFICIAL_LIFT_KNOWLEDGE_BASE.get(system_id.lower())

    @staticmethod
    def screen_lift_system(data: LiftScreeningInput) -> LiftScreeningResult:
        """
        Screen and recommend the optimal artificial lift system based on SPE criteria:
        - Q rate
        - Depth
        - GOR
        - Water cut
        - Viscosity
        - Sand content
        """
        q = data.get("q_rate_stb_day", 100)
        depth = data.get("depth_ft", 5000)
        gor = data.get("gor_scf_stb", 500)
        wc = data.get("water_cut_pct", 50)
        visc = data.get("viscosity_cp", 1.0)
        sand = data.get("sand_content", False)

        recommended = "esp"
        score = 85.0
        reasoning = "معدل الإنتاج والعمق مناسبان جداً للمضخات الغاطسة الكهربائية (ESP)."
        alternatives = ["gas_lift", "srp"]

        # High viscosity or sand -> PCP
        if visc > 50 or (sand and q < 3000):
            recommended = "pcp"
            score = 90.0
            reasoning = "وجود لزوجة عالية أو رمال بمعدلات متوسطة يرجح استخدام المضخات ذات التجويف التقدمي (PCP)."
            alternatives = ["esp", "srp"]

        # Low rate and high GOR in gas/oil wells -> Plunger Lift
        elif q < 200 and gor > 2000 and depth > 4000:
            recommended = "plunger_lift"
            score = 92.0
            reasoning = "معدل الإنتاج المنخفض مع GOR مرتفع يجعله مثالياً للرفع المكبسي (Plunger Lift)."
            alternatives = ["gas_lift", "srp"]

        # High GOR and gas availability -> Gas Lift
        elif gor > 1500 and depth > 6000:
            recommended = "gas_lift"
            score = 88.0
            reasoning = "نسبة الغاز للزيت (GOR) المرتفعة والعمق الكبير يدعمان اختيار الرفع بالغاز (Gas Lift)."
            alternatives = ["esp"]

        # Low to moderate rate, shallow/medium depth -> SRP
        elif q < 1000 and depth < 8000 and not sand:
            recommended = "srp"
            score = 89.0
            reasoning = "معدلات الإنتاج المعتدلة والعمق المتوسط تجعل مضخات الماصات الميكانيكية (SRP) الخيار الاقتصادي الأفضل."
            alternatives = ["pcp", "esp"]

        # High rate, deep/medium depth -> ESP
        elif q >= 500:
            recommended = "esp"
            score = 95.0
            reasoning = "معدلات الإنتاج العالية تتطلب قدرة سحب قوية وموثوقة عبر المضخات الغاطسة (ESP)."
            alternatives = ["gas_lift"]

        res: LiftScreeningResult = {
            "recommended_system": recommended,
            "suitability_score": score,
            "reasoning_ar": reasoning,
            "alternative_systems": alternatives
        }
        return res

    @staticmethod
    def calculate_esp_tdh(vertical_lift_ft: float, tubing_head_pressure_psi: float, effective_fluid_gradient_psi_ft: float) -> float:
        """Calculate Total Dynamic Head (TDH) in psi or equivalent feet."""
        hydrostatic_head = vertical_lift_ft * effective_fluid_gradient_psi_ft
        tdh_psi = hydrostatic_head + tubing_head_pressure_psi
        return tdh_psi

    @staticmethod
    def calculate_hydraulic_horsepower(q_stb_day: float, tdh_psi: float, specific_gravity: float) -> float:
        """Calculate Hydraulic HP for pump design."""
        q_gpm = (q_stb_day * 42.0) / 1440.0
        hhp = (q_gpm * tdh_psi) / 1714.0
        return round(hhp, 2)
