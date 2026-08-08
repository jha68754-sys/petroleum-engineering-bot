"""
Domain constants for the Petroleum Engineering Bot.

Contains all PVT rules, knowledge base entries, fluid classification,
formulas, correlations, unit conversions, plot rules, ASCII sketches,
and simulation decisions. Extracted from the original monolithic bot.py
and organized into logically grouped constants.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional, Tuple

from models.pvt_models import (
    FluidClassification,
    FormulaSpec,
    KnowledgeEntry,
    PVTPlotRule,
)

# ═══════════════════════════════════════════════════════════════════════
#  SYSTEM PROMPT  (loaded from file at runtime — see prompts/system_prompt.txt)
# ═══════════════════════════════════════════════════════════════════════

SYSTEM_PROMPT_FILE = "prompts/system_prompt.txt"


# ═══════════════════════════════════════════════════════════════════════
#  KNOWLEDGE BASE
# ═══════════════════════════════════════════════════════════════════════

KNOWLEDGE_BASE: List[KnowledgeEntry] = [
    {
        "en": "Oil Formation Volume Factor (Bo)",
        "ar": "معامل حجم تكوين الزيت",
        "category": "PVT (Group B - Context Dependent)",
        "unit": "rb/STB",
        "def_ar": "نسبة حجم الزيت مع الغاز المذاب داخل المكمن الى حجمه في خزان التخزين السطحي. Bo = حجم الزيت في المكمن / حجم زيت خزان التخزين. مرجع: Tarek Ahmed, Reservoir Engineering Handbook; SPE PetroWiki. مستوى الثقة: High.",
        "trend": "rises to max at Pb (above Pb), decreases below Pb",
        "relationship_key": "bo_vs_p",
        "typical_range": "n/a (Context-dependent fluid property; varies with pressure, temperature, and composition)",
    },
    {
        "en": "Solution Gas-Oil Ratio (Rs)",
        "ar": "نسبة الغاز المذاب",
        "category": "PVT (Group B - Context Dependent)",
        "unit": "scf/STB",
        "def_ar": "حجم الغاز الذائب في برميل واحد من زيت خزان التخزين عند ضغط وحرارة المكمن. مرجع: Tarek Ahmed, Reservoir Engineering Handbook; Standing (1947). مستوى الثقة: High.",
        "trend": "constant = Rsi above Pb, decreases below Pb",
        "relationship_key": "rs_vs_p",
        "typical_range": "n/a (Context-dependent fluid property; depends on saturation pressure and separator flash)",
    },
    {
        "en": "Bubble Point Pressure (Pb)",
        "ar": "ضغط نقطة الفقاعة",
        "category": "PVT (Group B - Context Dependent)",
        "unit": "psia",
        "def_ar": "الضغط الذي يبدأ عنده انفصال أول فقاعة غاز عن الزيت. مرجع: Dake, Fundamentals of Reservoir Engineering; SPE PetroWiki. مستوى الثقة: High.",
        "trend": "pivot point",
        "relationship_key": "saturation_pressure_oil",
        "typical_range": "n/a (Context-dependent PVT property; unique to fluid composition and thermal state)",
    },
    {
        "en": "Gas Formation Volume Factor (Bg)",
        "ar": "معامل حجم تكوين الغاز",
        "category": "PVT (Group B - Context Dependent)",
        "unit": "rb/scf",
        "def_ar": "نسبة حجم الغاز عند ظروف المكمن الى حجمه عند الظروف القياسية. مرجع: Craft & Hawkins, Applied Petroleum Reservoir Engineering. مستوى الثقة: High.",
        "trend": "smooth hyperbolic decrease as pressure increases",
        "relationship_key": "bg_vs_p",
        "typical_range": "n/a (Context-dependent gas property; function of pressure, temperature, and Z-factor)",
    },
    {
        "en": "Gas Compressibility Factor (Z-factor)",
        "ar": "معامل الانضغاطية للغاز",
        "category": "PVT (Group B - Context Dependent)",
        "unit": "dimensionless",
        "def_ar": "معامل تصحيح في معادلة PV=ZnRT يعكس انحراف سلوك الغاز الحقيقي عن الغاز المثالي. مرجع: Standing & Katz (1942); Dranchuk-Abou-Kassem (1975). مستوى الثقة: High.",
        "trend": "U-shaped: decreases from 1, reaches minimum, increases again",
        "relationship_key": "z_vs_p",
        "typical_range": "n/a (Context-dependent real gas property; function of pseudo-reduced pressure and temperature)",
    },
    {
        "en": "Oil Viscosity",
        "ar": "لزوجة الزيت",
        "category": "PVT (Group B - Context Dependent)",
        "unit": "cP",
        "def_ar": "مقاومة الزيت للتدفق. تتأثر بكمية الغاز المذاب والضغط والحرارة. مرجع: Beggs & Robinson (1975); SPE PetroWiki. مستوى الثقة: High.",
        "trend": "decreases to min at Pb (above Pb), increases below Pb",
        "relationship_key": "oil_visc_vs_p",
        "typical_range": "n/a (Context-dependent fluid property; depends on pressure, temperature, and dissolved gas content)",
    },
    {
        "en": "Gas Viscosity",
        "ar": "لزوجة الغاز",
        "category": "PVT (Group B - Context Dependent)",
        "unit": "cP",
        "def_ar": "مقاومة الغاز للتدفق تحت ظروف المكمن. مرجع: Lee, Gonzalez, and Eakin (1966). مستوى الثقة: High.",
        "trend": "monotonically increases with pressure",
        "relationship_key": "gas_visc_vs_p",
        "typical_range": "n/a (Context-dependent gas property; function of pressure, temperature, and gas specific gravity)",
    },
    {
        "en": "Oil Density",
        "ar": "كثافة الزيت",
        "category": "PVT (Group B - Context Dependent)",
        "unit": "lb/ft3",
        "def_ar": "كتلة الزيت لكل وحدة حجم عند ظروف المكمن. مرجع: Tarek Ahmed, Reservoir Engineering Handbook. مستوى الثقة: High.",
        "trend": "decreases to min at Pb, increases below Pb",
        "relationship_key": "oil_density_vs_p",
        "typical_range": "n/a (Context-dependent fluid property; depends on API gravity, solution gas, and pressure)",
    },
    {
        "en": "Relative Volume (CCE)",
        "ar": "الحجم النسبي",
        "category": "PVT (Group B - Context Dependent)",
        "unit": "V/Vsat",
        "def_ar": "حجم العينة عند ضغط معين منسوباً الى حجمها عند ضغط التشبع في تجربة التمدد ذي الحجم الثابت. مرجع: Ahmed, Reservoir Engineering Handbook. مستوى الثقة: High.",
        "trend": "gentle slope above Pb, =1.0 at Pb, steep slope below Pb",
        "relationship_key": "vrel_vs_p_cce",
        "typical_range": "n/a",
    },
    {
        "en": "Liquid Dropout (CVD)",
        "ar": "نسبة تكثف السوائل",
        "category": "PVT (Group B - Context Dependent)",
        "unit": "% HC pore volume",
        "def_ar": "نسبة السائل المتكثف من الغاز داخل المكمن عند ضغوط أقل من ضغط نقطة الندى. مرجع: Ahmed, Petroleum Reservoir Engineering. مستوى الثقة: High.",
        "trend": "0% above Pd, rises to peak (retrograde), then decreases",
        "relationship_key": "liquid_dropout_vs_p",
        "typical_range": "n/a (Context-dependent retrograde condensate property; depends on retrograde gas composition and depletion path)",
    },
    {
        "en": "Condensate-Gas Ratio (CGR)",
        "ar": "نسبة المكثفات إلى الغاز",
        "category": "Production (Group B - Context Dependent)",
        "unit": "STB/MMscf",
        "def_ar": "حجم المكثفات السطحية المنتجة لكل وحدة حجم من الغاز المنتج. مرجع: Economides, Petroleum Production Systems. مستوى الثقة: High.",
        "trend": "roughly constant above Pd, decreases below Pd",
        "relationship_key": "cgr_vs_p",
        "typical_range": "n/a (Context-dependent production parameter; depends on initial fluid composition and separator conditions)",
    },
    {
        "en": "Porosity",
        "ar": "المسامية",
        "category": "Reservoir (Group A - Magnitude Ranked)",
        "unit": "fraction or %",
        "def_ar": "نسبة حجم الفراغات الى الحجم الكلي للصخرة. مرجع: Tiab & Donaldson, Petrophysics. مستوى الثقة: High.",
        "trend": "static property",
        "relationship_key": None,
        "typical_range": "0.05 - 0.35",
    },
    {
        "en": "Permeability",
        "ar": "النفاذية",
        "category": "Reservoir (Group A - Magnitude Ranked)",
        "unit": "mD",
        "def_ar": "قدرة الصخرة على نقل الموائع تحت فرق ضغط (قانون دارسي). مرجع: Tiab & Donaldson, Petrophysics; SPE PetroWiki. مستوى الثقة: High.",
        "trend": "static property",
        "relationship_key": None,
        "typical_range": "0.1 - 1000+ mD",
    },
    {
        "en": "Original Oil In Place (OOIP)",
        "ar": "النفط الأصلي في المكمن",
        "category": "Reservoir (Group A - Volumetric)",
        "unit": "STB",
        "def_ar": "OOIP = (7758 x A x h x phi x (1-Sw)) / Bo. مرجع: Craft & Hawkins, Applied Petroleum Reservoir Engineering. مستوى الثقة: High.",
        "trend": "static",
        "relationship_key": None,
        "typical_range": "varies widely",
    },
    {
        "en": "Original Gas In Place (OGIP)",
        "ar": "الغاز الأصلي في المكمن",
        "category": "Reservoir (Group A - Volumetric)",
        "unit": "scf",
        "def_ar": "OGIP = (43560 x A x h x phi x (1-Sw)) / Bg بوحدة ft3/scf، أو (7758 x A x h x phi x (1-Sw)) / Bg بوحدة rb/scf. مرجع: Craft & Hawkins, Applied Petroleum Reservoir Engineering. مستوى الثقة: High.",
        "trend": "static",
        "relationship_key": None,
        "typical_range": "varies widely",
    },
    {
        "en": "Recovery Factor",
        "ar": "عامل الاسترداد",
        "category": "Reservoir (Group A - Magnitude Ranked)",
        "unit": "% or fraction",
        "def_ar": "RF = Np / OOIP. نسبة النسبة المستخرجة إلى النفط الأصلي في المكمن. مرجع: Dake, Fundamentals of Reservoir Engineering. مستوى الثقة: High.",
        "trend": "static",
        "relationship_key": None,
        "typical_range": "20% - 50% (oil), 50% - 90% (gas)",
    },
    {
        "en": "Skin Factor",
        "ar": "عامل الجلد",
        "category": "Production (Group A - Magnitude Ranked)",
        "unit": "dimensionless",
        "def_ar": "مقياس تأثير الضرر أو التحفيز حول البئر (معادلة هورنر/دارسي المعدلة). مرجع: Earlougher, Advances in Well Test Analysis. مستوى الثقة: High.",
        "trend": "well condition indicator",
        "relationship_key": None,
        "typical_range": "-5 to +20",
    },
    {
        "en": "Productivity Index (PI)",
        "ar": "مؤشر الإنتاجية",
        "category": "Production (Group A - Magnitude Ranked)",
        "unit": "STB/day/psi",
        "def_ar": "PI = q / (Pr - Pwf). معدل الإنتاج لكل وحدة هبوط ضغط. مرجع: Economides, Petroleum Production Systems. مستوى الثقة: High.",
        "trend": "well performance indicator",
        "relationship_key": None,
        "typical_range": "0.5 - 50 STB/day/psi",
    },
    {
        "en": "Water Cut (WC)",
        "ar": "نسبة الماء المنتج",
        "category": "Production (Group A - Magnitude Ranked)",
        "unit": "%",
        "def_ar": "WC = qw / (qo + qw) x 100. نسبة حجم الماء المنتج إلى إجمالي السوائل المنتجة. مرجع: Dake, Fundamentals of Reservoir Engineering. مستوى الثقة: High.",
        "trend": "increases over field life",
        "relationship_key": None,
        "typical_range": "0 - 98%",
    },
    {
        "en": "Hydrostatic Pressure",
        "ar": "الضغط الهيدروستاتيكي",
        "category": "Drilling (Group B - Operational)",
        "unit": "psi",
        "def_ar": "P = 0.052 x MW x TVD. ضغط عمود الطين في البئر. مرجع: Bourgoyne et al., Applied Drilling Engineering. مستوى الثقة: High.",
        "trend": "calculated from mud column",
        "relationship_key": None,
        "typical_range": "n/a (Operational parameter calculated from mud weight and true vertical depth)",
    },
    {
        "en": "Net Present Value (NPV)",
        "ar": "صافي القيمة الحالية",
        "category": "Economics (Group B - Economic Metric)",
        "unit": "$",
        "def_ar": "NPV = Sum[CFt/(1+r)^t] - C0. مقياس ربحية المشروع المالي. مرجع: SPE Petroleum Engineering Handbook, Economics and Evaluation. مستوى الثقة: Medium.",
        "trend": "n/a",
        "relationship_key": None,
        "typical_range": "n/a (Economic evaluation metric; depends on Capex, Opex, hydrocarbon pricing, and discount rate)",
    },
]


# ═══════════════════════════════════════════════════════════════════════
#  FLUID CLASSIFICATION TABLE
# ═══════════════════════════════════════════════════════════════════════

FLUID_CLASSIFICATION_TABLE: List[Dict[str, Any]] = [
    {
        "type_en": "Black Oil",
        "type_ar": "الزيت الأسود التقليدي",
        "gor_min": 0, "gor_max": 2000,
        "api_min": 0, "api_max": 40,
        "behavior": "سلوك Bo/Rs قياسي، لا يوجد تكثف رجعي.",
    },
    {
        "type_en": "Volatile Oil",
        "type_ar": "الزيت المتطاير",
        "gor_min": 2000, "gor_max": 8000,
        "api_min": 40, "api_max": 50,
        "behavior": "تغير حاد في Bo و Rs قرب ضغط نقطة الفقاعة.",
    },
    {
        "type_en": "Gas Condensate",
        "type_ar": "الغاز المكثف",
        "gor_min": 8000, "gor_max": 100000,
        "api_min": 50, "api_max": 70,
        "behavior": "تكثف رجعي (Retrograde) أسفل ضغط نقطة الندى.",
    },
    {
        "type_en": "Wet Gas",
        "type_ar": "الغاز الرطب",
        "gor_min": 100000, "gor_max": 1e9,
        "api_min": 60, "api_max": 200,
        "behavior": "لا يوجد تكثف داخل المكمن، فقط على السطح.",
    },
    {
        "type_en": "Dry Gas",
        "type_ar": "الغاز الجاف",
        "gor_min": 0, "gor_max": 0,
        "api_min": 0, "api_max": 0,
        "behavior": "لا يوجد تكثف على الإطلاق (شبه ميثان صافي).",
        "note": (
            "Dry gas produces effectively no stock-tank liquid, so GOR is "
            "undefined/very high and API gravity is not a meaningful property "
            "of this fluid -- it cannot be reached via numeric GOR/API bounds "
            "alone. classify_fluid() must be called with no_liquid=True for "
            "this class (see services/pvt_engine.py)."
        ),
    },
]


# ═══════════════════════════════════════════════════════════════════════
#  PVT PLOT RULES
# ═══════════════════════════════════════════════════════════════════════

PVT_PLOT_RULES: Dict[str, PVTPlotRule] = {
    "bo_vs_p": {
        "title_en": "Bo vs Pressure",
        "title_ar": "معامل حجم تكوين الزيت مقابل الضغط",
        "definition": "Bo = Reservoir Oil Volume / Stock Tank Oil Volume",
        "x_axis": "Pressure (psia)",
        "y_axis": "Bo (rb/STB)",
        "above_saturation": "increases gently as P decreases toward Pb",
        "at_saturation": "MAXIMUM value (Bob)",
        "below_saturation": "decreases as P decreases (steeper than rise above Pb)",
        "shape": "rises gently to a peak at Pb, then declines more steeply",
        "pivot": "Pb (peak)",
        "common_ai_mistakes": [
            "Bo increases continuously as pressure decreases",
            "Bo increases below Pb",
            "Bo = Stock Tank Volume / Reservoir Volume (inverted)",
            "higher Bo -> higher OOIP (Bo is in denominator: higher Bo = LOWER OOIP)",
        ],
        "plot_color": "#1A5276",
        "y_label": "Bo (rb/STB)",
    },
    "rs_vs_p": {
        "title_en": "Rs vs Pressure",
        "title_ar": "نسبة الغاز المذاب مقابل الضغط",
        "definition": "Rs = Solution Gas-Oil Ratio (scf/STB)",
        "x_axis": "Pressure (psia)",
        "y_axis": "Rs (scf/STB)",
        "above_saturation": "CONSTANT at Rsi (no free gas exists)",
        "at_saturation": "Rs = Rsi (maximum, start of decline)",
        "below_saturation": "decreases toward 0 as P decreases",
        "shape": "flat line above Pb, then declines below Pb",
        "pivot": "Pb (elbow)",
        "common_ai_mistakes": [
            "Rs increasing as pressure decreases",
            "Rs varying above Pb (must be constant = Rsi)",
        ],
        "plot_color": "#E67E22",
        "y_label": "Rs (scf/STB)",
    },
    "bg_vs_p": {
        "title_en": "Bg vs Pressure",
        "title_ar": "معامل حجم تكوين الغاز مقابل الضغط",
        "definition": "Bg = Reservoir Gas Volume / Standard Gas Volume",
        "x_axis": "Pressure (psia)",
        "y_axis": "Bg (rb/scf)",
        "above_saturation": "n/a",
        "at_saturation": "n/a",
        "below_saturation": "n/a",
        "shape": "smooth hyperbolic decrease as pressure increases",
        "pivot": "none",
        "common_ai_mistakes": ["Bg increasing with pressure"],
        "plot_color": "#1E8449",
        "y_label": "Bg (rb/scf)",
    },
    "z_vs_p": {
        "title_en": "Z-factor vs Pressure",
        "title_ar": "معامل الانضغاطية للغاز مقابل الضغط",
        "definition": "Z = Gas Compressibility Factor (dimensionless)",
        "x_axis": "Pressure (psia)",
        "y_axis": "Z-factor (dimensionless)",
        "above_saturation": "n/a",
        "at_saturation": "n/a",
        "below_saturation": "n/a",
        "shape": "U-shaped: starts near 1, decreases to minimum, then increases",
        "pivot": "minimum Z at intermediate P",
        "common_ai_mistakes": ["Z decreasing monotonically", "Z=1 always"],
        "plot_color": "#7D3C98",
        "y_label": "Z-factor",
    },
    "oil_visc_vs_p": {
        "title_en": "Oil Viscosity vs Pressure",
        "title_ar": "لزوجة الزيت مقابل الضغط",
        "definition": "Oil Viscosity (cP)",
        "x_axis": "Pressure (psia)",
        "y_axis": "Oil Viscosity (cP)",
        "above_saturation": "decreases gently as P decreases toward Pb",
        "at_saturation": "MINIMUM value (mu_ob)",
        "below_saturation": "increases as P decreases",
        "shape": "mirror image of Bo -- trough at Pb",
        "pivot": "Pb (minimum)",
        "common_ai_mistakes": [
            "monotonic increase as pressure decreases everywhere",
            "constant viscosity below Pb",
        ],
        "plot_color": "#C0392B",
        "y_label": "Oil Viscosity (cP)",
    },
    "gas_visc_vs_p": {
        "title_en": "Gas Viscosity vs Pressure",
        "title_ar": "لزوجة الغاز مقابل الضغط",
        "definition": "Gas Viscosity (cP) - monotonically increases with pressure",
        "x_axis": "Pressure (psia)",
        "y_axis": "Gas Viscosity (cP)",
        "above_saturation": "n/a",
        "at_saturation": "n/a",
        "below_saturation": "n/a",
        "shape": "monotonically increases with pressure",
        "pivot": "none",
        "common_ai_mistakes": ["Gas viscosity decreasing with pressure"],
        "plot_color": "#884EA0",
        "y_label": "Gas Viscosity (cP)",
    },
    "liquid_dropout_vs_p": {
        "title_en": "Liquid Dropout vs Pressure (CVD)",
        "title_ar": "نسبة تكثف السوائل مقابل الضغط",
        "definition": "Liquid Dropout = % of HC pore volume condensed below Pd",
        "x_axis": "Pressure (psia)",
        "y_axis": "Liquid Dropout (% HC PV)",
        "above_saturation": "0%",
        "at_saturation": "0% by definition",
        "below_saturation": "RISES sharply (retrograde), peaks, then DECREASES (re-vaporization)",
        "shape": "rises from 0 at Pd, peaks, then declines",
        "pivot": "Pd (start); peak at lower P",
        "common_ai_mistakes": [
            "monotonically increasing dropout with no peak",
            "dropout starting above Pd",
        ],
        "plot_color": "#2E86C1",
        "y_label": "Liquid Dropout (% HC PV)",
    },
    "cgr_vs_p": {
        "title_en": "CGR vs Pressure",
        "title_ar": "نسبة المكثفات إلى الغاز مقابل الضغط",
        "definition": "CGR = Condensate-Gas Ratio (STB/MMscf)",
        "x_axis": "Pressure (psia)",
        "y_axis": "CGR (STB/MMscf)",
        "above_saturation": "roughly constant",
        "at_saturation": "constant",
        "below_saturation": "DECREASES",
        "shape": "flat then declining below Pd",
        "pivot": "Pd (where decline begins)",
        "common_ai_mistakes": ["CGR increasing as pressure depletes"],
        "plot_color": "#117A65",
        "y_label": "CGR (STB/MMscf)",
    },
    "pt_diagram": {
        "title_en": "Phase Envelope (P-T Diagram)",
        "title_ar": "المغلف الطوري (مخطط الضغط - درجة الحرارة)",
        "definition": "Bubble-point and dew-point lines meeting at Critical Point",
        "x_axis": "Temperature (F)",
        "y_axis": "Pressure (psia)",
        "above_saturation": "n/a",
        "at_saturation": "n/a",
        "below_saturation": "n/a",
        "shape": "two-phase envelope bounded by Cricondenbar (max P) and Cricondentherm (max T)",
        "pivot": "Critical Point",
        "common_ai_mistakes": [
            "single curve with no critical point",
            "critical point at cricondenbar",
        ],
        "plot_color": "#1A5276",
        "y_label": "Pressure (psia)",
    },
    "oil_density_vs_p": {
        "title_en": "Oil Density vs Pressure",
        "title_ar": "كثافة الزيت مقابل الضغط",
        "definition": "Oil Density at reservoir conditions",
        "x_axis": "Pressure (psia)",
        "y_axis": "Oil Density (lb/ft3)",
        "above_saturation": "decreases gently toward Pb",
        "at_saturation": "MINIMUM value",
        "below_saturation": "increases as P decreases",
        "shape": "mirror image of Bo -- minimum at Pb",
        "pivot": "Pb (minimum)",
        "common_ai_mistakes": ["monotonic increase ignoring Pb minimum"],
        "plot_color": "#6E2F8C",
        "y_label": "Oil Density (lb/ft3)",
    },
    "vrel_vs_p_cce": {
        "title_en": "Relative Volume vs Pressure (CCE)",
        "title_ar": "الحجم النسبي مقابل الضغط",
        "definition": "Vrel = V(P)/V(Pb), CCE test output for Pb identification",
        "x_axis": "Pressure (psia)",
        "y_axis": "Relative Volume (V/Vsat)",
        "above_saturation": "gentle upward slope as P decreases",
        "at_saturation": "Vrel = 1.0 (SLOPE BREAK)",
        "below_saturation": "steep upward slope",
        "shape": "two segments with a kink at Pb",
        "pivot": "Pb (slope discontinuity)",
        "common_ai_mistakes": ["single straight line through whole curve"],
        "plot_color": "#1ABC9C",
        "y_label": "Relative Volume (V/Vsat)",
    },
    "gor_vs_p": {
        "title_en": "GOR vs Pressure",
        "title_ar": "نسبة الغاز إلى الزيت مقابل الضغط",
        "definition": "GOR = Gas-Oil Ratio (scf/STB)",
        "x_axis": "Pressure (psia)",
        "y_axis": "GOR (scf/STB)",
        "plot_color": "#E67E22",
        "y_label": "GOR (scf/STB)",
    },
    "wor_vs_p": {
        "title_en": "WOR vs Pressure",
        "title_ar": "نسبة الماء إلى الزيت مقابل الضغط",
        "definition": "WOR = Water-Oil Ratio (bbl/bbl)",
        "x_axis": "Pressure (psia)",
        "y_axis": "WOR (bbl/bbl)",
        "plot_color": "#2E86C1",
        "y_label": "WOR (bbl/bbl)",
    },
    "wc_vs_p": {
        "title_en": "Water Cut vs Pressure",
        "title_ar": "نسبة الماء المنتج مقابل الضغط",
        "definition": "Water Cut (%)",
        "x_axis": "Pressure (psia)",
        "y_axis": "Water Cut (%)",
        "plot_color": "#2E86C1",
        "y_label": "Water Cut (%)",
    },
    "p_vs_t": {
        "title_en": "Pressure vs Time",
        "title_ar": "الضغط مقابل الزمن",
        "definition": "Pressure evolution over time",
        "x_axis": "Time (days)",
        "y_axis": "Pressure (psia)",
        "plot_color": "#C0392B",
        "y_label": "Pressure (psia)",
    },
    "q_vs_t": {
        "title_en": "Production vs Time",
        "title_ar": "الإنتاج مقابل الزمن",
        "definition": "Production rate over time",
        "x_axis": "Time (days)",
        "y_axis": "Rate (STB/day)",
        "plot_color": "#1E8449",
        "y_label": "Production Rate (STB/day)",
    },
    "kr_vs_sw": {
        "title_en": "Relative Permeability vs Sw",
        "title_ar": "النفاذية النسبية مقابل تشبع الماء",
        "definition": "Kro and Krw relative permeability",
        "x_axis": "Water Saturation (Sw)",
        "y_axis": "Relative Permeability",
        "plot_color": "#1A5276",
        "y_label": "Kr",
    },
    "ipr_plot": {
        "title_en": "Inflow Performance Relationship (IPR)",
        "title_ar": "علاقة أداء التدفق الداخل (IPR)",
        "definition": "IPR = Rate vs Bottomhole Pressure",
        "x_axis": "Production Rate (STB/day)",
        "y_axis": "BHP (psia)",
        "plot_color": "#1E8449",
        "y_label": "Pressure (psia)",
    },
    "vlp_plot": {
        "title_en": "Vertical Lift Performance (VLP)",
        "title_ar": "أداء الرفع العمودي (VLP)",
        "definition": "VLP = Rate vs Required BHP",
        "x_axis": "Production Rate (STB/day)",
        "y_axis": "BHP (psia)",
        "plot_color": "#C0392B",
        "y_label": "Pressure (psia)",
    },
    "nodal_plot": {
        "title_en": "Nodal Analysis (IPR vs VLP)",
        "title_ar": "التحليل العقدي (IPR مقابل VLP)",
        "definition": "Intersection of IPR and VLP curves",
        "x_axis": "Production Rate (STB/day)",
        "y_axis": "BHP (psia)",
        "plot_color": "#2E86C1",
        "y_label": "Pressure (psia)",
    },
}


# ═══════════════════════════════════════════════════════════════════════
#  ASCII SKETCHES
# ═══════════════════════════════════════════════════════════════════════

ASCII_SKETCHES: Dict[str, str] = {
    "bo_vs_p": (
        "Bo (rb/STB)\n"
        "  ^\n"
        "  |                    Bob (max)\n"
        "  |                  ,-*\n"
        "  |               ,-'    \\\n"
        "  |            ,-'         \\\n"
        "  |         ,-'               \\\n"
        "  |      ,-'                     \\\n"
        "  |   ,-'                            \\___\n"
        "  |,-'\n"
        "  +------------------------------------------------> Pressure\n"
        "  (low P)              Pb                  (high P, Pi)\n"
    ),
    "rs_vs_p": (
        "Rs (scf/STB)\n"
        "  ^\n"
        "  |  ______________________ Rsi (constant above Pb)\n"
        "  | /\n"
        "  |/\n"
        "  |\\\n"
        "  | \\\n"
        "  |  \\\n"
        "  |   \\___\n"
        "  |       \\____\n"
        "  |            \\________\n"
        "  +------------------------------------------------> Pressure\n"
        "  (low P)              Pb                  (high P, Pi)\n"
    ),
    "bg_vs_p": (
        "Bg (rb/scf)\n"
        "  ^\n"
        "  |\\\n"
        "  | \\\n"
        "  |  \\___\n"
        "  |      \\____\n"
        "  |           \\_______\n"
        "  |                    \\____________\n"
        "  +------------------------------------------------> Pressure\n"
        "  (low P)                                  (high P)\n"
    ),
    "z_vs_p": (
        "Z-factor\n"
        "  ^\n"
        "1.0|\\____                                    ____\n"
        "   |     \\                                 /\n"
        "   |      \\___                      ______/\n"
        "   |          \\___________\n"
        "   |          (minimum Z, near Ppr ~ 1-2)\n"
        "   +------------------------------------------------> Pressure\n"
    ),
    "oil_visc_vs_p": (
        "Oil Viscosity (cP)\n"
        "  ^\n"
        "  |\\                                          /\n"
        "  | \\                                       /\n"
        "  |  \\                                    /\n"
        "  |   \\___                          ____/\n"
        "  |       \\__ mu_ob (min at Pb) ___/\n"
        "  +------------------------------------------------> Pressure\n"
        "  (low P)              Pb                  (high P, Pi)\n"
    ),
    "gas_visc_vs_p": (
        "Gas Viscosity (cP)\n"
        "  ^\n"
        "  |                                          ____\n"
        "  |                                    ____/\n"
        "  |                              ____/\n"
        "  |                        ____/\n"
        "  |                  ____/\n"
        "  |____/\n"
        "  +------------------------------------------------> Pressure\n"
        "  (low P)                                  (high P)\n"
    ),
    "liquid_dropout_vs_p": (
        "Liquid Dropout (% HC pore volume)\n"
        "  ^\n"
        "  |              ___---___\n"
        "  |           ,-'           '-.\n"
        "  |         ,'                  '-.\n"
        "  |        /                        '--.\n"
        "  |       /                              '----___\n"
        "  | 0% __/\n"
        "  +------------------------------------------------> Pressure\n"
        "  (low P)              Pd (dropout=0)       (high P)\n"
    ),
    "cgr_vs_p": (
        "CGR (STB/MMscf)\n"
        "  ^\n"
        "  |______________\n"
        "  |               \\\n"
        "  |                \\___\n"
        "  |                    \\____\n"
        "  |                         \\________\n"
        "  +------------------------------------------------> Pressure\n"
        "  (low P, late life)   Pd            (high P, Pi)\n"
    ),
    "pt_diagram": (
        "Pressure\n"
        "  ^\n"
        "  |        Cricondenbar\n"
        "  |            *\n"
        "  |         .'   '.\n"
        "  |       .'  TWO   '.\n"
        "  |     .'   PHASE     '.\n"
        "  |   .'    REGION        '.\n"
        "  |C <- Critical Pt           '.\n"
        "  | '.                             '.\n"
        "  +-------------------------------------> Temperature\n"
    ),
    "oil_density_vs_p": (
        "Oil Density (lb/ft3)\n"
        "  ^\n"
        "  |\\                                        /\n"
        "  | \\                                     /\n"
        "  |  \\___                          ____/\n"
        "  |      \\__ (min at Pb) _________/\n"
        "  +------------------------------------------------> Pressure\n"
    ),
    "vrel_vs_p_cce": (
        "Relative Volume (Vrel)\n"
        "  ^\n"
        "  |                                      /\n"
        "  |                                    /  <- steep (below Pb)\n"
        "  |                    ___,-'  1.0 at Pb (slope break)\n"
        "  |    ______,-,-'\n"
        "  |__,-'  <- gentle (above Pb)\n"
        "  +------------------------------------------------> Pressure\n"
    ),
}


# ═══════════════════════════════════════════════════════════════════════
#  PLOT ALIASES
# ═══════════════════════════════════════════════════════════════════════

PLOT_ALIASES: Dict[str, str] = {
    "bo": "bo_vs_p", "fvf": "bo_vs_p", "oil fvf": "bo_vs_p",
    "rs": "rs_vs_p", "solution gor": "rs_vs_p",
    "bg": "bg_vs_p", "gas fvf": "bg_vs_p",
    "z": "z_vs_p", "z-factor": "z_vs_p", "zfactor": "z_vs_p",
    "oil viscosity": "oil_visc_vs_p", "viscosity": "oil_visc_vs_p",
    "mu_o": "oil_visc_vs_p", "oilvisc": "oil_visc_vs_p",
    "gas viscosity": "gas_visc_vs_p", "mu_g": "gas_visc_vs_p",
    "gasvisc": "gas_visc_vs_p",
    "liquid dropout": "liquid_dropout_vs_p", "dropout": "liquid_dropout_vs_p",
    "cvd": "liquid_dropout_vs_p",
    "cgr": "cgr_vs_p",
    "phase envelope": "pt_diagram", "pt diagram": "pt_diagram",
    "p-t": "pt_diagram", "envelope": "pt_diagram",
    "oil density": "oil_density_vs_p", "density": "oil_density_vs_p",
    "relative volume": "vrel_vs_p_cce", "vrel": "vrel_vs_p_cce",
    "cce": "vrel_vs_p_cce", "cme": "vrel_vs_p_cce",
    "gor": "gor_vs_p", "wor": "wor_vs_p",
    "watercut": "wc_vs_p", "wc": "wc_vs_p",
    "pressure": "p_vs_t", "production": "q_vs_t",
    "kr": "kr_vs_sw", "kro": "kr_vs_sw", "krw": "kr_vs_sw",
    "ipr": "ipr_plot", "vlp": "vlp_plot", "nodal": "nodal_plot",
}


# ═══════════════════════════════════════════════════════════════════════
#  EXACT FORMULAS
# ═══════════════════════════════════════════════════════════════════════

EXACT_FORMULAS: Dict[str, FormulaSpec] = {
    "api": {
        "name_en": "API Gravity",
        "name_ar": "درجة API",
        "inputs": ["sg"],
        "units": {"sg": "dimensionless (SG, water=1.0)"},
        "formula_str": "API = (141.5 / SG) - 131.5",
        "func": lambda sg: (141.5 / sg) - 131.5,
        "output_unit": "deg API",
        "validation": lambda sg: 0.5 < sg < 1.2,
        "classify": lambda api: (
            "نفط خفيف / Light Oil" if api > 35 else
            "نفط متوسط / Medium Oil" if api > 22 else
            "نفط ثقيل / Heavy Oil"
        ),
    },
    "ooip": {
        "name_en": "Original Oil In Place (Volumetric)",
        "name_ar": "النفط الأصلي في المكمن",
        "inputs": ["area", "h", "phi", "sw", "bo"],
        "units": {"area": "acres", "h": "ft", "phi": "fraction",
                  "sw": "fraction", "bo": "rb/STB"},
        "formula_str": "OOIP = (7758 x A x h x phi x (1-Sw)) / Bo",
        "func": lambda area, h, phi, sw, bo: (7758 * area * h * phi * (1 - sw)) / bo,
        "output_unit": "STB",
        "validation": lambda area, h, phi, sw, bo: (
            0 < phi < 1 and 0 <= sw < 1 and bo > 0
        ),
        "note": "Bo في المقام: زيادة Bo تقلل OOIP المحسوب.",
    },
    "ogip": {
        "name_en": "Original Gas In Place (Volumetric)",
        "name_ar": "الغاز الأصلي في المكمن",
        "inputs": ["area", "h", "phi", "sw", "bg"],
        "units": {"area": "acres", "h": "ft", "phi": "fraction",
                  "sw": "fraction", "bg": "ft3/scf (default)"},
        "formula_str": "OGIP = (43560 x A x h x phi x (1-Sw)) / Bg  [Bg in ft3/scf] "
                       "OR (7758 x A x h x phi x (1-Sw)) / Bg  [Bg in rb/scf]",
        "func": lambda area, h, phi, sw, bg, bg_rb=0.0: (
            (7758.0 if bg_rb else 43560.0) * area * h * phi * (1.0 - sw) / bg
        ),
        "output_unit": "scf",
        "validation": lambda area, h, phi, sw, bg, bg_rb=0.0: (
            0 < phi < 1 and 0 <= sw < 1 and bg > 0
        ),
        "note": (
            "Bg unit is explicit: default is ft3/scf with constant 43560 "
            "(1 acre-ft = 43,560 ft3). Provide bg_rb=1 to declare Bg in rb/scf, "
            "which uses constant 7758 (1 acre-ft = 7,758 bbl). "
            "Reference: Craft & Hawkins, Applied Petroleum Reservoir Engineering."
        ),
    },
    "darcy": {
        "name_en": "Darcy Linear Flow Rate",
        "name_ar": "معدل التدفق الخطي",
        "inputs": ["k", "area", "dp", "mu", "length"],
        "units": {"k": "mD", "area": "ft2", "dp": "psi", "mu": "cP", "length": "ft"},
        "formula_str": "q = 0.001127 x k x A x dP / (mu x L)",
        "func": lambda k, area, dp, mu, length: (
            0.001127 * k * area * dp
        ) / (mu * length),
        "output_unit": "bbl/day",
        "validation": lambda k, area, dp, mu, length: (
            all(v > 0 for v in [k, area, dp, mu, length])
        ),
    },
    "recovery_factor": {
        "name_en": "Recovery Factor",
        "name_ar": "عامل الاسترداد",
        "inputs": ["np", "ooip"],
        "units": {"np": "STB", "ooip": "STB"},
        "formula_str": "RF = NP / OOIP x 100",
        "func": lambda np, ooip: (np / ooip) * 100,
        "output_unit": "%",
        "validation": lambda np, ooip: 0 <= np <= ooip,
    },
    "productivity_index": {
        "name_en": "Productivity Index",
        "name_ar": "مؤشر الإنتاجية",
        "inputs": ["q", "pr", "pwf"],
        "units": {"q": "STB/day", "pr": "psi", "pwf": "psi"},
        "formula_str": "PI = q / (Pr - Pwf)",
        "func": lambda q, pr, pwf: q / (pr - pwf),
        "output_unit": "STB/day/psi",
        "validation": lambda q, pr, pwf: pr > pwf and q > 0,
    },
    "hydrostatic": {
        "name_en": "Hydrostatic Pressure",
        "name_ar": "الضغط الهيدروستاتيكي",
        "inputs": ["mw", "tvd"],
        "units": {"mw": "ppg", "tvd": "ft"},
        "formula_str": "P (psi) = 0.052 x MW x TVD",
        "func": lambda mw, tvd: 0.052 * mw * tvd,
        "output_unit": "psi",
        "validation": lambda mw, tvd: 6 < mw < 25 and tvd > 0,
    },
    "mud_weight_required": {
        "name_en": "Required Mud Weight",
        "name_ar": "وزن الطين المطلوب",
        "inputs": ["p_target", "tvd"],
        "units": {"p_target": "psi", "tvd": "ft"},
        "formula_str": "MW (ppg) = P_target / (0.052 x TVD)",
        "func": lambda p_target, tvd: p_target / (0.052 * tvd),
        "output_unit": "ppg",
        "validation": lambda p_target, tvd: p_target > 0 and tvd > 0,
        "note": (
            "Any overbalance margin must be selected per the approved drilling program and the "
            "pore-pressure / fracture-gradient window, considering ECD, well-control requirements, and "
            "applicable operating procedures. No margin is prescribed without an approved design basis."
        ),
    },
    "ecd": {
        "name_en": "Equivalent Circulating Density (ECD)",
        "name_ar": "الكثافة المكافئة للدوران",
        "inputs": ["mw", "app", "tvd"],
        "units": {"mw": "ppg", "app": "psi (annular pressure loss)", "tvd": "ft"},
        "formula_str": "ECD (ppg) = MW + (APL / (0.052 x TVD))",
        "func": lambda mw, app, tvd: mw + (app / (0.052 * tvd)),
        "output_unit": "ppg",
        "validation": lambda mw, app, tvd: mw > 0 and tvd > 0 and app >= 0,
    },
    "water_cut": {
        "name_en": "Water Cut",
        "name_ar": "نسبة الماء المنتج",
        "inputs": ["qw", "qo"],
        "units": {"qw": "bbl/day", "qo": "bbl/day"},
        "formula_str": "WC = qw / (qo + qw) x 100",
        "func": lambda qw, qo: (qw / (qo + qw)) * 100,
        "output_unit": "%",
        "validation": lambda qw, qo: qw >= 0 and qo >= 0 and (qw + qo) > 0,
    },
    "wor": {
        "name_en": "Water-Oil Ratio (WOR)",
        "name_ar": "نسبة الماء إلى الزيت",
        "inputs": ["qw", "qo"],
        "units": {"qw": "bbl/day", "qo": "bbl/day"},
        "formula_str": "WOR = qw / qo",
        "func": lambda qw, qo: qw / qo,
        "output_unit": "bbl/bbl",
        "validation": lambda qw, qo: qw >= 0 and qo > 0,
    },
    "gor_produced": {
        "name_en": "Produced GOR",
        "name_ar": "نسبة الغاز إلى الزيت المنتجة",
        "inputs": ["qg", "qo"],
        "units": {"qg": "scf/day", "qo": "STB/day"},
        "formula_str": "GOR = qg / qo",
        "func": lambda qg, qo: qg / qo,
        "output_unit": "scf/STB",
        "validation": lambda qg, qo: qg >= 0 and qo > 0,
    },
    "pv": {
        "name_en": "Present Value (single cash flow)",
        "name_ar": "القيمة الحالية (دفقة نقدية واحدة)",
        "inputs": ["cf", "rate", "t"],
        "units": {"cf": "$", "rate": "fraction", "t": "years"},
        "formula_str": "PV = CF / (1+r)^t",
        "func": lambda cf, rate, t: cf / (1 + rate) ** t,
        "output_unit": "$",
        "validation": lambda cf, rate, t: rate > -1 and t >= 0,
        "note": "Single-cash-flow present value. NOT a project NPV -- see /calc npv for multiple cash flows.",
    },
    "npv": {
        "name_en": "Net Present Value (multi cash flow)",
        "name_ar": "صافي القيمة الحالية (تعدد الدفعات)",
        "inputs": ["cf", "rate"],
        "units": {"cf": "$ (comma-separated: cf0,cf1,...,cfN for t=0..N)",
                  "rate": "fraction"},
        "formula_str": "NPV = sum(CF_t / (1+r)^t) for t = 0..N",
        "func": lambda cf, rate: sum(
            c / (1 + rate) ** t
            for t, c in enumerate(float(v) for v in str(cf).split(","))
        ),
        "output_unit": "$",
        "validation": lambda cf, rate: rate > -1 and "," in str(cf),
        "note": (
            "True multi-cash-flow NPV: provide cf as a comma-separated list starting at t=0, "
            "e.g. cf=-1000000,300000,350000,400000. Only supplied values are discounted -- no "
            "cash flows are invented. For a single cash flow use /calc pv instead."
        ),
    },
}


# ═══════════════════════════════════════════════════════════════════════
#  CORRELATIONS (Expanded)
# ═══════════════════════════════════════════════════════════════════════

CORRELATIONS: Dict[str, CorrelationSpec] = {
    "pb_standing": {
        "name_en": "Bubble Point Pressure (Standing, 1947)",
        "name_ar": "ضغط نقطة الفقاعة (معادلة ستاندينغ)",
        "inputs": ["rs", "gas_sg", "tres", "api"],
        "units": {"rs": "scf/STB", "gas_sg": "dimensionless",
                  "tres": "deg F", "api": "deg API"},
        "formula_str": "Pb = 18.2 * [(Rs/gamma_g)^0.83 * 10^(0.00091*T - 0.0125*API) - 1.4]",
        "func": lambda rs, gas_sg, tres, api: 18.2 * (
            (rs / gas_sg) ** 0.83 * 10 ** (0.00091 * tres - 0.0125 * api) - 1.4
        ),
        "output_unit": "psia",
        "applicability": {"rs": (20, 1425), "api": (16.5, 63.8), "tres": (100, 258)},
    },
    "rs_standing": {
        "name_en": "Solution GOR (Standing, 1947)",
        "name_ar": "نسبة الغاز المذاب (معادلة ستاندينغ)",
        "inputs": ["p", "gas_sg", "tres", "api"],
        "units": {"p": "psia", "gas_sg": "dimensionless",
                  "tres": "deg F", "api": "deg API"},
        "formula_str": "Rs = gamma_g * [(P/18.2 + 1.4) * 10^(0.0125*API - 0.00091*T)]^1.2048",
        "func": lambda p, gas_sg, tres, api: gas_sg * (
            (p / 18.2 + 1.4) * 10 ** (0.0125 * api - 0.00091 * tres)
        ) ** 1.2048,
        "output_unit": "scf/STB",
        "applicability": {"p": (130, 7000), "api": (16.5, 63.8), "tres": (100, 258)},
    },
    # --- Vasquez-Beggs (1980) ---
    # Reference: Vasquez, M.E. and Beggs, H.D., "Correlations for Fluid Physical
    # Property Prediction," JPT, June 1980, pp. 968-970.
    # Uses API-gravity-dependent coefficients (two branches) and gas gravity
    # normalized to a reference separator pressure of 100 psig via p_sep/t_sep.
    "pb_vasquez_beggs": {
        "name_en": "Bubble Point Pressure (Vasquez-Beggs, 1980)",
        "name_ar": "ضغط نقطة الفقاعة (فاسكيز-بيغز)",
        "inputs": ["rs", "gas_sg", "tres", "api", "p_sep", "t_sep"],
        "units": {"rs": "scf/STB", "gas_sg": "dimensionless",
                  "tres": "deg F", "api": "deg API", "p_sep": "psia",
                  "t_sep": "deg F (REQUIRED -- separator temperature)"},
        "formula_str": (
            "Pb = [Rs / (C1 * gamma_gs * exp(C3*API/(T+460)))]^(1/C2), "
            "gamma_gs = gamma_g*[1 + 5.912e-5*API*Tsep*log10(Psep/114.7)], "
            "(C1,C2,C3) = (0.0362,1.0937,25.724) if API<=30 else (0.0178,1.1870,23.931)"
        ),
        "func": lambda rs, gas_sg, tres, api, p_sep, t_sep: _vasquez_beggs_pb(rs, gas_sg, tres, api, p_sep, t_sep),
        "output_unit": "psia",
        "applicability": {"rs": (20, 2070), "api": (15.2, 60), "tres": (70, 300)},
    },
    "rs_vasquez_beggs": {
        "name_en": "Solution GOR (Vasquez-Beggs, 1980)",
        "name_ar": "نسبة الغاز المذاب (فاسكيز-بيغز)",
        "inputs": ["p", "gas_sg", "tres", "api", "p_sep", "t_sep"],
        "units": {"p": "psia", "gas_sg": "dimensionless",
                  "tres": "deg F", "api": "deg API", "p_sep": "psia",
                  "t_sep": "deg F (REQUIRED -- separator temperature)"},
        "formula_str": (
            "Rs = C1 * gamma_gs * P^C2 * exp(C3*API/(T+460)), "
            "gamma_gs = gamma_g*[1 + 5.912e-5*API*Tsep*log10(Psep/114.7)], "
            "(C1,C2,C3) = (0.0362,1.0937,25.724) if API<=30 else (0.0178,1.1870,23.931)"
        ),
        "func": lambda p, gas_sg, tres, api, p_sep, t_sep: _vasquez_beggs_rs(p, gas_sg, tres, api, p_sep, t_sep),
        "output_unit": "scf/STB",
        "applicability": {"p": (100, 7000), "api": (15.2, 60), "tres": (70, 300)},
    },
    # --- Standing Bo ---
    "bo_standing": {
        "name_en": "Oil FVF (Standing, 1947)",
        "name_ar": "معامل حجم تكوين الزيت (ستاندينغ)",
        "inputs": ["rs", "gas_sg", "tres", "api"],
        "units": {"rs": "scf/STB", "gas_sg": "dimensionless",
                  "tres": "deg F", "api": "deg API"},
        "formula_str": "Bob = 0.9759 + 0.000120 * (Rs*sqrt(gamma_g/gamma_o) + 1.25*T)^1.2",
        "func": lambda rs, gas_sg, tres, api: (
            0.9759 + 0.000120 * (
                rs * (gas_sg / (141.5 / (api + 131.5))) ** 0.5
                + 1.25 * tres
            ) ** 1.2
        ),
        "output_unit": "rb/STB",
        "applicability": {"rs": (0, 1425), "api": (16.5, 63.8), "tres": (100, 258)},
    },
    # --- Z-factor (Standing-Katz approximation) ---
    "z_standing_katz": {
        "name_en": "Z-factor (Standing-Katz, 1942)",
        "name_ar": "معامل الانضغاطية (ستاندينغ-كاتز)",
        "inputs": ["tpr", "ppr"],
        "units": {"tpr": "dimensionless (T/Tpc)", "ppr": "dimensionless (P/Ppc)"},
        "formula_str": "Dranchuk-Abou-Kassem (1975) -- numerical fit to Standing-Katz chart, solved iteratively",
        "func": lambda tpr, ppr: _standing_katz_approx(tpr, ppr),
        "output_unit": "dimensionless",
        "applicability": {"tpr": (1.0, 3.0), "ppr": (0.0, 15.0)},
    },
}


def _vb_coefficients(api: float) -> Tuple[float, float, float]:
    """Vasquez-Beggs (1980) coefficients, branched by oil API gravity."""
    if api <= 30:
        return 0.0362, 1.0937, 25.724
    return 0.0178, 1.1870, 23.931


def _vb_gas_gravity_at_ref_sep(
    gas_sg: float, api: float, p_sep: float, t_sep: float
) -> float:
    """
    Correct gas specific gravity to the Vasquez-Beggs reference separator
    condition (100 psig), per the original 1980 correlation.

    Args:
        gas_sg: Gas specific gravity at actual separator conditions.
        api: Stock-tank oil API gravity.
        p_sep: Actual separator pressure (psia).
        t_sep: Separator temperature in deg F. REQUIRED explicit input of
            the correlation -- no default is ever assumed.

    Returns:
        Gas gravity normalized to the 100 psig reference separator pressure.
    """
    import math
    p_sep_safe = max(p_sep, 1e-6)
    return gas_sg * (
        1 + 5.912e-5 * api * t_sep * math.log10(p_sep_safe / 114.7)
    )


def _vasquez_beggs_rs(p: float, gas_sg: float, tres: float, api: float, p_sep: float, t_sep: float) -> float:
    """Vasquez-Beggs (1980) solution GOR (Rs) at pressure P < Pb.

    t_sep (separator temperature, deg F) is a REQUIRED input of the
    correlation (Vasquez & Beggs, JPT 1980, pp. 968-970). It must be
    supplied explicitly; no default value is ever assumed.
    """
    import math
    c1, c2, c3 = _vb_coefficients(api)
    gamma_gs = _vb_gas_gravity_at_ref_sep(gas_sg, api, p_sep, t_sep)
    return c1 * gamma_gs * (p ** c2) * math.exp(c3 * api / (tres + 460))


def _vasquez_beggs_pb(rs: float, gas_sg: float, tres: float, api: float, p_sep: float, t_sep: float) -> float:
    """Vasquez-Beggs (1980) bubble point pressure, by inverting the Rs equation at Rs=Rsb.

    t_sep (separator temperature, deg F) is a REQUIRED input of the
    correlation (Vasquez & Beggs, JPT 1980, pp. 968-970). It must be
    supplied explicitly; no default value is ever assumed.
    """
    import math
    c1, c2, c3 = _vb_coefficients(api)
    gamma_gs = _vb_gas_gravity_at_ref_sep(gas_sg, api, p_sep, t_sep)
    denom = c1 * gamma_gs * math.exp(c3 * api / (tres + 460))
    return (rs / denom) ** (1 / c2)


def _standing_katz_approx(tpr: float, ppr: float) -> float:
    """
    Gas Z-factor via the Dranchuk-Abou-Kassem (1975) correlation -- the
    standard numerical fit to the original Standing-Katz (1942) chart.

    Solved iteratively (fixed-point) since Z appears on both sides of the
    equation through the reduced gas density rho_r = 0.27*Ppr/(Z*Tpr).

    Valid range (per the original paper): 1.0 <= Tpr <= 3.0, 0.2 <= Ppr <= 30.

    Args:
        tpr: Pseudo-reduced temperature (T / Tpc)
        ppr: Pseudo-reduced pressure (P / Ppc)

    Returns:
        Estimated Z-factor (dimensionless)
    """
    import math
    if tpr <= 0 or ppr < 0:
        raise ValueError(
            f"Physically invalid input: tpr={tpr}, ppr={ppr}. "
            "Tpr must be > 0 and Ppr must be >= 0; the DAK iteration is not "
            "defined for non-positive reduced conditions."
        )
    if ppr == 0:
        return 1.0

    a1, a2, a3, a4, a5 = 0.3265, -1.0700, -0.5339, 0.01569, -0.05165
    a6, a7, a8, a9, a10, a11 = 0.5475, -0.7361, 0.1844, 0.1056, 0.6134, 0.7210

    z = 1.0
    for _ in range(100):
        rho_r = 0.27 * ppr / (z * tpr)
        term1 = (a1 + a2 / tpr + a3 / tpr ** 3 + a4 / tpr ** 4 + a5 / tpr ** 5) * rho_r
        term2 = (a6 + a7 / tpr + a8 / tpr ** 2) * rho_r ** 2
        term3 = -a9 * (a7 / tpr + a8 / tpr ** 2) * rho_r ** 5
        term4 = (
            a10 * (1 + a11 * rho_r ** 2) * (rho_r ** 2 / tpr ** 3)
            * math.exp(-a11 * rho_r ** 2)
        )
        z_new = 1 + term1 + term2 + term3 + term4
        if abs(z_new - z) < 1e-8:
            return z_new
        z = z_new
    return z


# ═══════════════════════════════════════════════════════════════════════
#  UNIT CONVERSIONS
# ═══════════════════════════════════════════════════════════════════════

UNIT_CONVERSIONS: Dict[Tuple[str, str], Callable[[float], float]] = {
    ("psi", "bar"):      lambda v: v * 0.0689476,
    ("bar", "psi"):      lambda v: v / 0.0689476,
    ("psi", "kpa"):      lambda v: v * 6.89476,
    ("kpa", "psi"):      lambda v: v / 6.89476,
    ("ppg", "lb/ft3"):   lambda v: v * 7.4805,
    ("lb/ft3", "ppg"):   lambda v: v / 7.4805,
    ("ppg", "sg"):       lambda v: v / 8.345,
    ("sg", "ppg"):       lambda v: v * 8.345,
    ("scf/stb", "m3/m3"): lambda v: v * 0.1781,
    ("m3/m3", "scf/stb"): lambda v: v / 0.1781,
    ("bbl", "m3"):       lambda v: v * 0.158987,
    ("m3", "bbl"):       lambda v: v / 0.158987,
    ("ft", "m"):         lambda v: v * 0.3048,
    ("m", "ft"):         lambda v: v / 0.3048,
    ("cp", "pa.s"):      lambda v: v * 0.001,
    ("pa.s", "cp"):      lambda v: v / 0.001,
    ("degf", "degc"):    lambda v: (v - 32) * 5 / 9,
    ("degc", "degf"):    lambda v: v * 9 / 5 + 32,
    ("acre", "m2"):      lambda v: v * 4046.86,
    ("m2", "acre"):      lambda v: v / 4046.86,
}


# ═══════════════════════════════════════════════════════════════════════
#  PVTO / PVDO / PVTG / PVDG SKELETONS
# ═══════════════════════════════════════════════════════════════════════

PVTO_SKELETON = (
    "PVTO Table (Live Oil -- Eclipse Black Oil)\n\n"
    "When to use: Black Oil or Volatile Oil with Rs > 0\n"
    "If Rs ~ 0 (dead/heavy oil): use PVDO instead\n\n"
    "Eclipse format:\n"
    "  PVTO\n"
    "  -- Rs(scf/STB)  Pb(psia)  Bo(rb/STB)  Viscosity(cP)  -- saturated\n"
    "                  P>Pb      Bo<Bob       Visc>Visc_ob   -- undersaturated\n"
    "  /\n\n"
    "Rule: For each Rs (0 to Rsi):\n"
    "  Saturated row: Rs, Pb(Rs), Bo_sat, mu_o_sat\n"
    "  Undersaturated rows (same Rs, P>Pb): Bo decreases, mu_o increases\n\n"
    "DATA REQUIRED:\n"
    "  From DV Test (below Pb):\n"
    "    Rs(P)   [scf/STB]\n"
    "    Bo(P)   [rb/STB]\n"
    "    mu_o(P) [cP]\n"
    "  From CCE (above Pb):\n"
    "    Co (oil compressibility) [1/psi]\n"
    "    d(mu_o)/dP above Pb\n\n"
    "Important Eclipse rule:\n"
    "  Bo in PVTO must be from DV Test, NOT from CCE.\n"
    "  Apply Separator Test correction:\n"
    "  Bo_field = Bo_DV x (Bo_sep / Bo_DV_at_Pb)"
)

PVDO_SKELETON = (
    "PVDO Table (Dead Oil -- Eclipse Black Oil)\n\n"
    "When to use: Heavy/Dead Oil with Rs ~ 0\n\n"
    "Eclipse format:\n"
    "  PVDO\n"
    "  -- P(psia)  Bo(rb/STB)  Viscosity(cP)\n"
    "  /\n\n"
    "DATA REQUIRED:\n"
    "  P(P)    [psia]\n"
    "  Bo(P)   [rb/STB]  -- decreases with increasing P\n"
    "  mu_o(P) [cP]      -- increases with increasing P"
)

PVTG_SKELETON = (
    "PVTG Table (Live/Wet Gas -- Eclipse Black Oil)\n\n"
    "When to use: Gas Condensate or Wet Gas with Rv > 0\n"
    "If Rv ~ 0 (dry gas): use PVDG instead\n\n"
    "Eclipse format:\n"
    "  PVTG\n"
    "  -- P(psia)  Rv(STB/scf)  Bg(rb/scf)  Gas_Visc(cP)\n"
    "  /\n\n"
    "DATA REQUIRED:\n"
    "  From CVD:\n"
    "    Bg(P)   [rb/scf]\n"
    "    mu_g(P) [cP]\n"
    "  From Compositional Analysis:\n"
    "    Rv(P)   [STB/scf]  (= CGR x Bg_initial, or from EOS)\n\n"
    "Note: For rich/near-critical Gas Condensate, use Compositional\n"
    "  simulation (Eclipse E300 / CMG GEM + EOS) for best accuracy."
)

PVDG_SKELETON = (
    "PVDG Table (Dry Gas -- Eclipse Black Oil)\n\n"
    "When to use: Dry Gas or Wet Gas with Rv ~ 0\n\n"
    "Eclipse format:\n"
    "  PVDG\n"
    "  -- P(psia)  Bg(rb/scf)  Gas_Visc(cP)\n"
    "  /\n\n"
    "DATA REQUIRED:\n"
    "  P(P)    [psia]\n"
    "  Bg(P)   [rb/scf]  -- decreases with increasing P\n"
    "  mu_g(P) [cP]      -- increases with increasing P\n\n"
    "Calculate Bg:\n"
    "  Bg (rb/scf) = 0.005615 x (Z x T_R) / P\n"
    "  T_R = T(F) + 459.67 [Rankine]"
)


# ═══════════════════════════════════════════════════════════════════════
#  SIMULATION EXPORT DECISIONS
# ═══════════════════════════════════════════════════════════════════════

EXPORT_SIM_DECISIONS: Dict[str, Dict[str, Optional[str]]] = {
    "black_oil": {
        "table": "PVTO (if Rs > 0) or PVDO (if Rs ~ 0)",
        "simulator": "Eclipse Black Oil (E100) or CMG IMEX",
        "reason": "Black-Oil model sufficient. Phase composition changes slowly.",
        "warning": None,
    },
    "volatile_oil": {
        "table": "PVTO with dense data near Pb",
        "simulator": "Eclipse E100 or CMG IMEX -- with caution",
        "reason": "Volatile Oil can use Black-Oil but sharp Bo/Rs changes near Pb require dense data.",
        "warning": "If near-critical: switch to Compositional (Eclipse E300 / CMG GEM + EOS).",
    },
    "gas_condensate": {
        "table": "PVTG with Rv from compositional analysis",
        "simulator": "Eclipse E100 with PVTG or CMG IMEX",
        "reason": "Lean Gas Condensate: Black-Oil with PVTG acceptable.",
        "warning": "Rich/near-critical Gas Condensate: Compositional (E300/CMG GEM + EOS) preferred.",
    },
    "wet_gas": {
        "table": "PVTG with approximately constant Rv",
        "simulator": "Eclipse E100 or CMG IMEX",
        "reason": "No reservoir condensation. PVTG sufficient.",
        "warning": None,
    },
    "dry_gas": {
        "table": "PVDG (no Rv)",
        "simulator": "Eclipse E100 or CMG IMEX",
        "reason": "Simplest case. No condensate. PVDG with Bg and gas viscosity only.",
        "warning": None,
    },
}

EXPORT_SIM_ALIASES: Dict[str, str] = {
    "black oil": "black_oil", "black_oil": "black_oil",
    "زيت أسود": "black_oil", "زيت تقليدي": "black_oil",
    "volatile oil": "volatile_oil", "volatile_oil": "volatile_oil",
    "زيت متطاير": "volatile_oil",
    "gas condensate": "gas_condensate", "condensate": "gas_condensate",
    "gas_condensate": "gas_condensate", "غاز مكثف": "gas_condensate",
    "wet gas": "wet_gas", "wet_gas": "wet_gas", "غاز رطب": "wet_gas",
    "dry gas": "dry_gas", "dry_gas": "dry_gas", "غاز جاف": "dry_gas",
}


# ═══════════════════════════════════════════════════════════════════════
#  PDF SECTION HEADERS
# ═══════════════════════════════════════════════════════════════════════

PVT_SECTION_HEADERS: List[str] = [
    "Differential Liberation", "Differential Vaporization",
    "Constant Composition Expansion", "CCE",
    "Constant Volume Depletion", "CVD",
    "Separator Test", "Compositional Analysis",
    "Viscosity", "Recombination", "Reservoir Fluid Properties",
    "Sample Information", "PVT Summary", "Well Test", "Fluid Analysis",
]


# ═══════════════════════════════════════════════════════════════════════
#  TEXT CLEANER DICTIONARY
# ═══════════════════════════════════════════════════════════════════════

TEXT_FIXES: Dict[str, str] = {
    "**": "", "###": "", "##": "",
    "Pressuring Volume and Temperature": "Pressure-Volume-Temperature",
    "الضغط البيني": "معامل حجم التكوين",
    "المعامل البيني": "معامل حجم التكوين",
    "الترشيح": "نسبة الغاز المذاب",
    "النسبة المئوية للغاز": "نسبة الغاز إلى الزيت",
    "الويسكوزية": "اللزوجة",
    "الليزج": "اللزوجة",
    "الحفرة": "المكمن",
}


# ═══════════════════════════════════════════════════════════════════════
#  STATIC RESPONSES
# ═══════════════════════════════════════════════════════════════════════

START_MESSAGE = (
    "Enterprise Petroleum AI Platform (v1.0.0-Enterprise)\n"
    "Powered by Enterprise Intelligence Fabric (EIF) & Senior Petroleum Expert System\n\n"
    "Covers:\n"
    "• Reservoir Engineering & Volumetrics (OOIP/OGIP)\n"
    "• Production Engineering & IPR (Vogel/Fetkovich)\n"
    "• Well Testing & Pressure Transient Analysis\n"
    "• Artificial Lift Selection & Optimization\n"
    "• PVT & Fluid Properties Analysis (PFIE)\n"
    "• Diagnostics & Operational Intelligence (PEDI)\n"
    "• 30+ Years Senior Expert Emulation System\n\n"
    "Ask any engineering question or use /help for the complete command list."
)

HELP_MESSAGE = (
    "Enterprise Petroleum AI Platform -- Command Reference\n\n"
    "=== ENTERPRISE COGNITIVE & ENGINEERING COMMANDS ===\n\n"
    "/classify gor=<val> api=<val>\n"
    "  Classify fluid type using PFIE & EIF reasoning.\n\n"
    "/calc <type> key=value ...\n"
    "  Enterprise calculators (OOIP, OGIP, Darcy, Vogel, Nodal, etc.).\n"
    "  Example: /calc ooip area=500 h=50 phi=0.2 sw=0.3 bo=1.3\n\n"
    "/estimate <type> key=value ...\n"
    "  Advanced petroleum correlations and expert system estimations.\n\n"
    "/analyze\n"
    "  Run Enterprise Intelligence Fabric (EIF) multi-module reasoning workflow.\n\n"
    "/report\n"
    "  Generate professional enterprise engineering reports with ERF and EIF.\n\n"
    "/plot <type> [p=x1,x2 v=y1,y2] [pb=val]\n"
    "  Direct-data plotting tool. Supports multi-series (v1=, v2=).\n"
    "  Example: /plot bo p=500,1000 v=1.1,1.2 pb=1500\n\n"
    "/convert <value> <from> to <to>\n"
    "  Universal petroleum unit conversion.\n\n"
    "/reset     -- Clear active session context.\n\n"
    "Supported Disciplines:\n"
    "• Reservoir | Production | Well Testing | Artificial Lift | PVT | Diagnostics | Expert System\n\n"
    "Upload reports, datasets, or type any complex engineering question."
)

SURFACE_SEPARATOR_ANSWER = (
    "Engineering Analysis -- Surface Separator Oil + Gas Samples\n\n"
    "Sample Type\n"
    "These are surface samples, NOT direct reservoir fluid.\n"
    "Oil and gas separated at surface separator conditions.\n"
    "RECOMBINATION is required first before any PVT test or property (Bo, Rs, Pb).\n\n"
    "Data Required Before Proceeding\n"
    "- Separator Pressure and Temperature\n"
    "- Oil Rate [STB/day] and Gas Rate [scf/day]\n"
    "- Producing GOR [scf/STB]\n"
    "- Gas Composition and Stock Tank Oil Composition\n"
    "- API Gravity and Gas Specific Gravity\n"
    "- Water Cut and H2S/CO2 content\n\n"
    "Correct Lab Workflow\n"
    "1. Sample QC\n"
    "2. Recombination -- reconstruct reservoir fluid\n"
    "3. Validation of recombined sample\n"
    "4. Compositional Analysis (C1 to C12+)\n"
    "5. CCE/CME -- determine saturation pressure\n"
    "6. DV (oil) or CVD (gas condensate)\n"
    "7. Separator Test -- convert DV data to field data\n"
    "8. Viscosity Test\n"
    "9. EOS Tuning if compositional simulation planned\n\n"
    "Use /classify after getting GOR and API to identify fluid type.\n"
    "Use /pvto or /pvtg for simulation table requirements."
)
