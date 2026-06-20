"""
Petroleum Engineering AI Bot — Production Architecture v3 (FIXED)
==================================================================
Fixes applied:
  1. CRITICAL: /check block indentation error (SyntaxError)
  2. /check body.split()[0] crash when body is empty
  3. offset management logic corrected
  4. send_message chunk splitting improved (split on newlines)
  5. PDF extraction: try pypdf first, fallback to PyPDF2
  6. Added full matplotlib PVT Plot generator with PNG → Telegram
  7. Added proper logging throughout
  8. Added try/except around every command handler
  9. /plot now supports BOTH ASCII mode and PNG plot mode
 10. Added CSV data input support for /plot
 11. Fixed glossary HTML caching
 12. Added /help alias for /start
"""

import os
import re
import io
import csv
import time
import math
import json as _json
import base64
import logging
import tempfile
import mimetypes
import requests
import matplotlib
matplotlib.use("Agg")                   # non-interactive backend — must be before pyplot
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D

# PDF extraction — try modern pypdf first, fall back to legacy PyPDF2
try:
    from pypdf import PdfReader
except ImportError:
    try:
        from PyPDF2 import PdfReader
    except ImportError:
        PdfReader = None

try:
    from docx import Document as DocxDocument
except ImportError:
    DocxDocument = None


# ─────────────────────────────────────────────
#  LOGGING SETUP
# ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(funcName)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


# ─────────────────────────────────────────────
#  ENVIRONMENT
# ─────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY       = os.getenv("OPENAI_API_KEY")

if not TELEGRAM_BOT_TOKEN or not GROQ_API_KEY:
    raise ValueError("Missing env vars: TELEGRAM_BOT_TOKEN or OPENAI_API_KEY")

TELEGRAM_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
GROQ_URL     = "https://api.groq.com/openai/v1/chat/completions"

TEXT_MODEL   = os.getenv("GROQ_TEXT_MODEL",   "llama-3.3-70b-versatile")
VISION_MODEL = os.getenv("GROQ_VISION_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")

# FIX #8: offset starts at 0 and is updated to max seen update_id
offset        = 0
FILE_CONTEXT  = {}    # chat_id -> segmented document text
IMAGE_CONTEXT = {}    # chat_id -> local image path
_GLOSSARY_CACHE = {}  # FIX #11: cache glossary HTML


# ─────────────────────────────────────────────
#  SYSTEM PROMPT  (unchanged from original)
# ─────────────────────────────────────────────
SYSTEM_PROMPT = """
You are a senior Petroleum Engineering Consultant covering the FULL discipline:
PVT Laboratory Analysis, Reservoir Engineering, Reservoir Simulation
(Eclipse / CMG), Drilling Engineering, Production Engineering, and
Petroleum Economics.

You think and answer like a real senior engineer reviewing data and
reports -- never like a generic chatbot.

CRITICAL ARCHITECTURE RULE: For any question about a PVT property's
behavior vs pressure (Bo, Rs, Bg, Z-factor, oil viscosity, liquid dropout,
CGR, phase envelope), DETERMINISTIC PYTHON LOGIC (BLOCK 5, /plot, /check)
is the SOURCE OF TRUTH and OVERRIDES your own reasoning. If your own
"intuition" about a PVT trend conflicts with BLOCK 5, BLOCK 5 IS CORRECT.
Never contradict BLOCK 5. For general (non-PVT-trend) petroleum
engineering questions -- reservoir, drilling, production, economics,
simulation workflow -- you may reason normally, always grounded in the
formulas and rules given below.

===============================================
BLOCK 1 -- LANGUAGE RULES
===============================================
- Arabic input -> respond in professional Arabic, using the approved
  terminology dictionary (BLOCK 3). Keep core technical abbreviations (Bo,
  Rs, Bg, GOR, WOR, API, PVT, CCE, CVD, PVTO, PVTG, OOIP, OGIP, PI, NPV,
  etc.) in English even inside Arabic sentences.
- English input -> respond in professional petroleum engineering English.
- Mixed input -> mirror the user's mix naturally.
- Never use machine-translated or non-standard Arabic petroleum terms.
  See BLOCK 3 for the canonical dictionary and BLOCK 4 for banned terms.

===============================================
BLOCK 2 -- RESPONSE STRUCTURE
===============================================
1. Classify the question type.
2. If PVT-vs-pressure relationship: use BLOCK 5 EXACTLY.
3. If user data provided: identify sample type, classify fluid per BLOCK 6.
4. If calculation: use BLOCK 8 rules, state formula and correlation name.
5. If document/graph: follow BLOCK 9 or BLOCK 10.
6. If simulation export: follow BLOCK 11.
7. ALWAYS end with engineering interpretation AND missing data note.

===============================================
BLOCK 3 -- APPROVED TERMINOLOGY DICTIONARY
===============================================
Bo = معامل حجم تكوين الزيت (Oil Formation Volume Factor, rb/STB)
     DEFINITION: Bo = Reservoir Oil Volume / Stock Tank Oil Volume
Rs = نسبة الغاز المذاب (Solution Gas-Oil Ratio, scf/STB)
Bg = معامل حجم تكوين الغاز (Gas Formation Volume Factor, rb/scf)
Pb = ضغط نقطة الفقاعة (Bubble Point Pressure)
Pd = ضغط نقطة الندى (Dew Point Pressure)
GOR = نسبة الغاز إلى الزيت (Gas-Oil Ratio)
WOR = نسبة الماء إلى الزيت (Water-Oil Ratio)
CGR = نسبة المكثفات إلى الغاز (Condensate-Gas Ratio)
Z-factor = معامل الانضغاطية للغاز (Gas Compressibility Factor)
CCE/CME = اختبار التمدد عند كتلة ثابتة
DV = اختبار التحرر التفاضلي (Differential Liberation)
CVD = اختبار الاستنزاف عند حجم ثابت
OOIP = النفط الأصلي في المكمن
OGIP = الغاز الأصلي في المكمن
PVTO = جدول PVTO لمحاكي Eclipse (Live Oil)
PVDO = جدول PVDO لمحاكي Eclipse (Dead Oil)
PVTG = جدول PVTG لمحاكي Eclipse (Live/Wet Gas)
PVDG = جدول PVDG لمحاكي Eclipse (Dry Gas)

===============================================
BLOCK 4 -- BANNED TERMS
===============================================
"الويسكوزية" -> use: "اللزوجة"
"الحفرة" -> use: "المكمن"
"Bo = Stock Tank Volume / Reservoir Volume" -> ALWAYS REJECT (inverted)
Any invented numeric lab value not provided by the user.

===============================================
BLOCK 5 -- PVT PHYSICAL RELATIONSHIPS (DETERMINISTIC GROUND TRUTH)
===============================================
--- Bo vs Pressure ---
Above Pb: Bo increases gently as P decreases toward Pb (max = Bob at Pb).
At Pb: Bo = MAXIMUM (Bob).
Below Pb: Bo DECREASES as P decreases (steeper than rise above Pb).
REJECT: "Bo increases continuously as P decreases" or "Bo increases below Pb".
REJECT: "Bo = Stock Tank / Reservoir" (inverted).
REJECT: "higher Bo -> higher OOIP" (Bo is denominator, higher Bo = LOWER OOIP).

--- Rs vs Pressure ---
Above Pb: Rs = CONSTANT = Rsi (no free gas).
At Pb: Rs = Rsi (maximum, start of decline).
Below Pb: Rs DECREASES toward 0.
REJECT: "Rs increases above Pb" or "Rs increases as P decreases".

--- Bg vs Pressure ---
Smooth HYPERBOLIC DECREASE as pressure increases (Bg ~ Z*T/P).
No saturation pivot for Bg itself.
REJECT: "Bg increases with pressure".

--- Z-factor vs Pressure ---
U-SHAPED: starts ~1 at low P, decreases to MINIMUM (near Ppr~1-2), then increases.
REJECT: "Z decreases monotonically" or "Z=1 always".

--- Oil Viscosity vs Pressure ---
Above Pb: decreases gently toward Pb (MINIMUM = mu_ob at Pb).
Below Pb: INCREASES as P decreases.
REJECT: "viscosity increases monotonically everywhere".

--- Liquid Dropout vs Pressure (Gas Condensate CVD) ---
Above Pd: 0%. At Pd: 0% (first drop). Below Pd: RISES (retrograde), peaks, then DECREASES.
REJECT: "monotonically increasing dropout".

--- CGR vs Pressure ---
Above Pd: roughly constant. Below Pd: DECREASES.
REJECT: "CGR increases as pressure depletes".

===============================================
BLOCK 6 -- FLUID CLASSIFICATION
===============================================
Black Oil:      GOR < 2,000,    API < 40
Volatile Oil:   GOR 2,000-8,000, API 40-50
Gas Condensate: GOR 8,000-100,000, API 50-70
Wet Gas:        GOR > 100,000,  API > 60
Dry Gas:        ~no liquid

===============================================
BLOCK 7 -- LAB WORKFLOW
===============================================
1. Sample QC -> 2. Recombination (if surface samples) ->
3. CCE/CME -> 4. DV (oil) or CVD (gas condensate) ->
5. Separator Test -> 6. Viscosity -> 7. EOS Tuning

===============================================
BLOCK 8 -- CALCULATION RULES
===============================================
Always state formula name, applicability range, and units.
Label results as: Lab-measured / Correlation estimate / User assumption.

===============================================
BLOCK 9 -- PDF/DOCX ANALYSIS RULES
===============================================
Use section labels. Flag PVT trend violations vs BLOCK 5 as
POSSIBLE DATA QUALITY ISSUE rather than silently accepting.

===============================================
BLOCK 10 -- GRAPH INTERPRETATION RULES
===============================================
Identify axes, match to BLOCK 5 reference, confirm or flag discrepancy.

===============================================
BLOCK 11 -- PVTO/PVDO/PVTG/PVDG GENERATION RULES
===============================================
Black Oil Rs>0 -> PVTO. Dead Oil Rs~0 -> PVDO.
Gas Condensate/Wet Gas -> PVTG. Dry Gas -> PVDG.
Near-critical -> recommend Compositional EOS simulation.

===============================================
BLOCK 12 -- ANTI-HALLUCINATION RULES
===============================================
1. No numeric results without data.
2. BLOCK 5 always overrides AI reasoning for PVT trends.
3. Label each value: Lab-measured / Correlation / User-provided / Engineering judgment.
4. Never invent well names, field names, or company names.
5. Ask for GOR/API if fluid type is ambiguous.

===============================================
BLOCK 13 -- FORMATTING RULES
===============================================
No markdown ** or ### in chat responses.
No vertical-line tables (ASCII sketches exempt).
Concise, direct, professional.
"""


# ─────────────────────────────────────────────
#  KNOWLEDGE BASE
# ─────────────────────────────────────────────
KNOWLEDGE_BASE = [
    {"en": "Oil Formation Volume Factor (Bo)", "ar": "معامل حجم تكوين الزيت",
     "category": "PVT", "unit": "rb/STB",
     "def_ar": "نسبة حجم الزيت مع الغاز المذاب داخل المكمن الى حجمه في خزان التخزين السطحي. Bo = حجم الزيت في المكمن / حجم زيت خزان التخزين.",
     "trend": "rises to max at Pb (above Pb), decreases below Pb",
     "relationship_key": "bo_vs_p", "typical_range": "1.0 - 2.0 rb/STB"},
    {"en": "Solution Gas-Oil Ratio (Rs)", "ar": "نسبة الغاز المذاب",
     "category": "PVT", "unit": "scf/STB",
     "def_ar": "حجم الغاز الذائب في برميل واحد من زيت خزان التخزين عند ضغط وحرارة المكمن.",
     "trend": "constant = Rsi above Pb, decreases below Pb",
     "relationship_key": "rs_vs_p", "typical_range": "100 - 2000+ scf/STB"},
    {"en": "Bubble Point Pressure (Pb)", "ar": "ضغط نقطة الفقاعة",
     "category": "PVT", "unit": "psia",
     "def_ar": "الضغط الذي يبدأ عنده انفصال أول فقاعة غاز عن الزيت.",
     "trend": "pivot point", "relationship_key": "saturation_pressure_oil",
     "typical_range": "100 - 5000+ psia"},
    {"en": "Gas Formation Volume Factor (Bg)", "ar": "معامل حجم تكوين الغاز",
     "category": "PVT", "unit": "rb/scf",
     "def_ar": "نسبة حجم الغاز عند ظروف المكمن الى حجمه عند الظروف القياسية.",
     "trend": "smooth hyperbolic decrease as pressure increases",
     "relationship_key": "bg_vs_p", "typical_range": "0.0005 - 0.02 rb/scf"},
    {"en": "Gas Compressibility Factor (Z-factor)", "ar": "معامل الانضغاطية للغاز",
     "category": "PVT", "unit": "dimensionless",
     "def_ar": "معامل تصحيح في معادلة PV=ZnRT يعكس انحراف سلوك الغاز الحقيقي عن الغاز المثالي.",
     "trend": "U-shaped: decreases from 1, reaches minimum, increases again",
     "relationship_key": "z_vs_p", "typical_range": "0.6 - 1.2"},
    {"en": "Oil Viscosity", "ar": "لزوجة الزيت",
     "category": "PVT", "unit": "cP",
     "def_ar": "مقاومة الزيت للتدفق. تتأثر بكمية الغاز المذاب.",
     "trend": "decreases to min at Pb (above Pb), increases below Pb",
     "relationship_key": "oil_visc_vs_p", "typical_range": "0.2 - 50+ cP"},
    {"en": "Gas Viscosity", "ar": "لزوجة الغاز",
     "category": "PVT", "unit": "cP",
     "def_ar": "مقاومة الغاز للتدفق.",
     "trend": "monotonically increases with pressure",
     "relationship_key": "gas_visc_vs_p", "typical_range": "0.01 - 0.05 cP"},
    {"en": "Oil Density", "ar": "كثافة الزيت",
     "category": "PVT", "unit": "lb/ft3",
     "def_ar": "كتلة الزيت لكل وحدة حجم عند ظروف المكمن.",
     "trend": "decreases to min at Pb, increases below Pb",
     "relationship_key": "oil_density_vs_p", "typical_range": "40 - 60 lb/ft3"},
    {"en": "Relative Volume (CCE)", "ar": "الحجم النسبي",
     "category": "PVT", "unit": "V/Vsat",
     "def_ar": "حجم العينة عند ضغط معين منسوباً الى حجمها عند ضغط التشبع.",
     "trend": "gentle slope above Pb, =1.0 at Pb, steep slope below Pb",
     "relationship_key": "vrel_vs_p_cce", "typical_range": "n/a"},
    {"en": "Liquid Dropout (CVD)", "ar": "نسبة تكثف السوائل",
     "category": "PVT - Gas Condensate", "unit": "% HC pore volume",
     "def_ar": "نسبة السائل المتكثف من الغاز داخل المكمن عند الضغوط الاقل من ضغط الندى.",
     "trend": "0% above Pd, rises to peak (retrograde), then decreases",
     "relationship_key": "liquid_dropout_vs_p", "typical_range": "0 - 30%+"},
    {"en": "Condensate-Gas Ratio (CGR)", "ar": "نسبة المكثفات إلى الغاز",
     "category": "Production - Gas Condensate", "unit": "STB/MMscf",
     "def_ar": "حجم المكثفات السطحية المنتجة لكل وحدة حجم من الغاز المنتج.",
     "trend": "roughly constant above Pd, decreases below Pd",
     "relationship_key": "cgr_vs_p", "typical_range": "10 - 300 STB/MMscf"},
    {"en": "Porosity", "ar": "المسامية", "category": "Reservoir", "unit": "fraction or %",
     "def_ar": "نسبة حجم الفراغات الى الحجم الكلي للصخرة.",
     "trend": "static property", "relationship_key": None, "typical_range": "0.05 - 0.35"},
    {"en": "Permeability", "ar": "النفاذية", "category": "Reservoir", "unit": "mD",
     "def_ar": "قدرة الصخرة على نقل الموائع تحت فرق ضغط.",
     "trend": "static property", "relationship_key": None, "typical_range": "0.1 - 1000+ mD"},
    {"en": "Original Oil In Place (OOIP)", "ar": "النفط الأصلي في المكمن",
     "category": "Reservoir", "unit": "STB",
     "def_ar": "OOIP = (7758 x A x h x phi x (1-Sw)) / Bo. ملاحظة: Bo في المقام.",
     "trend": "static", "relationship_key": None, "typical_range": "varies widely"},
    {"en": "Original Gas In Place (OGIP)", "ar": "الغاز الأصلي في المكمن",
     "category": "Reservoir", "unit": "scf",
     "def_ar": "OGIP = (43560 x A x h x phi x (1-Sw)) / Bgi.",
     "trend": "static", "relationship_key": None, "typical_range": "varies widely"},
    {"en": "Recovery Factor", "ar": "عامل الاسترداد",
     "category": "Reservoir", "unit": "% or fraction",
     "def_ar": "RF = Np / OOIP.",
     "trend": "static", "relationship_key": None, "typical_range": "20% - 50% (oil), 50% - 90% (gas)"},
    {"en": "Skin Factor", "ar": "عامل الجلد",
     "category": "Production", "unit": "dimensionless",
     "def_ar": "مقياس تأثير الضرر أو التحفيز حول البئر.",
     "trend": "well condition indicator", "relationship_key": None, "typical_range": "-5 to +20"},
    {"en": "Productivity Index (PI)", "ar": "مؤشر الإنتاجية",
     "category": "Production", "unit": "STB/day/psi",
     "def_ar": "PI = q / (Pr - Pwf).",
     "trend": "well performance indicator", "relationship_key": None,
     "typical_range": "0.5 - 50 STB/day/psi"},
    {"en": "Water Cut (WC)", "ar": "نسبة الماء المنتج",
     "category": "Production", "unit": "%",
     "def_ar": "WC = qw / (qo + qw) x 100.",
     "trend": "increases over field life", "relationship_key": None, "typical_range": "0 - 98%"},
    {"en": "Hydrostatic Pressure", "ar": "الضغط الهيدروستاتيكي",
     "category": "Drilling", "unit": "psi",
     "def_ar": "P = 0.052 x MW x TVD.",
     "trend": "calculated from mud column", "relationship_key": None, "typical_range": "depends on MW, TVD"},
    {"en": "Net Present Value (NPV)", "ar": "صافي القيمة الحالية",
     "category": "Economics", "unit": "$",
     "def_ar": "NPV = Sum[CFt/(1+r)^t] - C0.",
     "trend": "n/a", "relationship_key": None, "typical_range": "n/a"},
]


# ─────────────────────────────────────────────
#  FLUID CLASSIFICATION TABLE
# ─────────────────────────────────────────────
FLUID_CLASSIFICATION_TABLE = [
    {"type_en": "Black Oil", "type_ar": "الزيت الأسود التقليدي",
     "gor_min": 0, "gor_max": 2000, "api_min": 0, "api_max": 40,
     "behavior": "سلوك Bo/Rs قياسي، لا يوجد تكثف رجعي."},
    {"type_en": "Volatile Oil", "type_ar": "الزيت المتطاير",
     "gor_min": 2000, "gor_max": 8000, "api_min": 40, "api_max": 50,
     "behavior": "تغير حاد في Bo و Rs قرب ضغط نقطة الفقاعة."},
    {"type_en": "Gas Condensate", "type_ar": "الغاز المكثف",
     "gor_min": 8000, "gor_max": 100000, "api_min": 50, "api_max": 70,
     "behavior": "تكثف رجعي (Retrograde) أسفل ضغط نقطة الندى."},
    {"type_en": "Wet Gas", "type_ar": "الغاز الرطب",
     "gor_min": 100000, "gor_max": 1e9, "api_min": 60, "api_max": 200,
     "behavior": "لا يوجد تكثف داخل المكمن، فقط على السطح."},
    {"type_en": "Dry Gas", "type_ar": "الغاز الجاف",
     "gor_min": 0, "gor_max": 0, "api_min": 0, "api_max": 0,
     "behavior": "لا يوجد تكثف على الإطلاق (شبه ميثان صافي)."},
]


def classify_fluid(gor: float, api: float) -> str:
    for row in FLUID_CLASSIFICATION_TABLE[:-1]:
        if row["gor_min"] <= gor < row["gor_max"] and row["api_min"] <= api <= row["api_max"]:
            return (
                f"{row['type_en']} ({row['type_ar']})\n\n"
                f"GOR = {gor:,.0f} scf/STB (Range: {row['gor_min']:,}-{row['gor_max']:,})\n"
                f"API = {api} (Range: {row['api_min']}-{row['api_max']})\n\n"
                f"Expected behavior: {row['behavior']}"
            )
    return (
        f"GOR = {gor:,.0f} scf/STB and API = {api} do not fit cleanly into one category.\n"
        "This may indicate a Near-Critical fluid. Consider Compositional (EOS) simulation.\n"
        "Use /classify gor=<value> api=<value> with confirmed lab data."
    )


# ─────────────────────────────────────────────
#  PVT PLOT RULES + ASCII SKETCHES
# ─────────────────────────────────────────────
PVT_PLOT_RULES = {
    "bo_vs_p": {
        "title_en": "Bo vs Pressure", "title_ar": "معامل حجم تكوين الزيت مقابل الضغط",
        "definition": "Bo = Reservoir Oil Volume / Stock Tank Oil Volume",
        "x_axis": "Pressure (psia)", "y_axis": "Bo (rb/STB)",
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
        "title_en": "Rs vs Pressure", "title_ar": "نسبة الغاز المذاب مقابل الضغط",
        "definition": "Rs = Solution Gas-Oil Ratio (scf/STB)",
        "x_axis": "Pressure (psia)", "y_axis": "Rs (scf/STB)",
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
        "title_en": "Bg vs Pressure", "title_ar": "معامل حجم تكوين الغاز مقابل الضغط",
        "definition": "Bg = Reservoir Gas Volume / Standard Gas Volume",
        "x_axis": "Pressure (psia)", "y_axis": "Bg (rb/scf)",
        "above_saturation": "n/a", "at_saturation": "n/a", "below_saturation": "n/a",
        "shape": "smooth hyperbolic decrease as pressure increases",
        "pivot": "none",
        "common_ai_mistakes": ["Bg increasing with pressure"],
        "plot_color": "#1E8449",
        "y_label": "Bg (rb/scf)",
    },
    "z_vs_p": {
        "title_en": "Z-factor vs Pressure", "title_ar": "معامل الانضغاطية للغاز مقابل الضغط",
        "definition": "Z = Gas Compressibility Factor (dimensionless)",
        "x_axis": "Pressure (psia)", "y_axis": "Z-factor (dimensionless)",
        "above_saturation": "n/a", "at_saturation": "n/a", "below_saturation": "n/a",
        "shape": "U-shaped: starts near 1, decreases to minimum, then increases",
        "pivot": "minimum Z at intermediate P",
        "common_ai_mistakes": ["Z decreasing monotonically", "Z=1 always"],
        "plot_color": "#7D3C98",
        "y_label": "Z-factor",
    },
    "oil_visc_vs_p": {
        "title_en": "Oil Viscosity vs Pressure", "title_ar": "لزوجة الزيت مقابل الضغط",
        "definition": "Oil Viscosity (cP)",
        "x_axis": "Pressure (psia)", "y_axis": "Oil Viscosity (cP)",
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
        "title_en": "Gas Viscosity vs Pressure", "title_ar": "لزوجة الغاز مقابل الضغط",
        "definition": "Gas Viscosity (cP) - monotonically increases with pressure",
        "x_axis": "Pressure (psia)", "y_axis": "Gas Viscosity (cP)",
        "above_saturation": "n/a", "at_saturation": "n/a", "below_saturation": "n/a",
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
        "x_axis": "Pressure (psia)", "y_axis": "Liquid Dropout (% HC PV)",
        "above_saturation": "0%", "at_saturation": "0% by definition",
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
        "title_en": "CGR vs Pressure", "title_ar": "نسبة المكثفات إلى الغاز مقابل الضغط",
        "definition": "CGR = Condensate-Gas Ratio (STB/MMscf)",
        "x_axis": "Pressure (psia)", "y_axis": "CGR (STB/MMscf)",
        "above_saturation": "roughly constant", "at_saturation": "constant",
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
        "x_axis": "Temperature (F)", "y_axis": "Pressure (psia)",
        "above_saturation": "n/a", "at_saturation": "n/a", "below_saturation": "n/a",
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
        "title_en": "Oil Density vs Pressure", "title_ar": "كثافة الزيت مقابل الضغط",
        "definition": "Oil Density at reservoir conditions",
        "x_axis": "Pressure (psia)", "y_axis": "Oil Density (lb/ft3)",
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
        "x_axis": "Pressure (psia)", "y_axis": "Relative Volume (V/Vsat)",
        "above_saturation": "gentle upward slope as P decreases",
        "at_saturation": "Vrel = 1.0 (SLOPE BREAK)",
        "below_saturation": "steep upward slope",
        "shape": "two segments with a kink at Pb",
        "pivot": "Pb (slope discontinuity)",
        "common_ai_mistakes": ["single straight line through whole curve"],
        "plot_color": "#1ABC9C",
        "y_label": "Relative Volume (V/Vsat)",
    },
}

ASCII_SKETCHES = {
    "bo_vs_p": r"""
Bo (rb/STB)
  ^
  |                    Bob (max)
  |                  ,-*
  |               ,-'    \
  |            ,-'         \
  |         ,-'               \
  |      ,-'                     \
  |   ,-'                            \___
  |,-'
  +------------------------------------------------> Pressure
  (low P)              Pb                  (high P, Pi)
""",
    "rs_vs_p": r"""
Rs (scf/STB)
  ^
  |  ______________________ Rsi (constant above Pb)
  | /
  |/
  |\
  | \
  |  \
  |   \___
  |       \____
  |            \________
  +------------------------------------------------> Pressure
  (low P)              Pb                  (high P, Pi)
""",
    "bg_vs_p": r"""
Bg (rb/scf)
  ^
  |\
  | \
  |  \___
  |      \____
  |           \_______
  |                    \____________
  +------------------------------------------------> Pressure
  (low P)                                  (high P)
""",
    "z_vs_p": r"""
Z-factor
  ^
1.0|\____                                    ____
   |     \                                 /
   |      \___                      ______/
   |          \___________________/
   |          (minimum Z, near Ppr ~ 1-2)
   +------------------------------------------------> Pressure
""",
    "oil_visc_vs_p": r"""
Oil Viscosity (cP)
  ^
  |\                                          /
  | \                                       /
  |  \                                    /
  |   \___                          ____/
  |       \__ mu_ob (min at Pb) ___/
  +------------------------------------------------> Pressure
  (low P)              Pb                  (high P, Pi)
""",
    "gas_visc_vs_p": r"""
Gas Viscosity (cP)
  ^
  |                                          ____
  |                                    ____/
  |                              ____/
  |                        ____/
  |                  ____/
  |____/
  +------------------------------------------------> Pressure
  (low P)                                  (high P)
""",
    "liquid_dropout_vs_p": r"""
Liquid Dropout (% HC pore volume)
  ^
  |              ___---___
  |           ,-'           '-.
  |         ,'                  '-.
  |        /                        '--.
  |       /                              '----___
  | 0% __/
  +------------------------------------------------> Pressure
  (low P)              Pd (dropout=0)       (high P)
""",
    "cgr_vs_p": r"""
CGR (STB/MMscf)
  ^
  |______________
  |               \
  |                \___
  |                    \____
  |                         \________
  +------------------------------------------------> Pressure
  (low P, late life)   Pd            (high P, Pi)
""",
    "pt_diagram": r"""
Pressure
  ^
  |        Cricondenbar
  |            *
  |         .'   '.
  |       .'  TWO   '.
  |     .'   PHASE     '.
  |   .'    REGION        '.
  |C <- Critical Pt           '.
  | '.                             '.
  +-------------------------------------> Temperature
""",
    "oil_density_vs_p": r"""
Oil Density (lb/ft3)
  ^
  |\                                        /
  | \                                     /
  |  \___                          ____/
  |      \__ (min at Pb) _________/
  +------------------------------------------------> Pressure
""",
    "vrel_vs_p_cce": r"""
Relative Volume (Vrel)
  ^
  |                                      /
  |                                    /  <- steep (below Pb)
  |                    ___,-'  1.0 at Pb (slope break)
  |    ______,-,-'
  |__,-'  <- gentle (above Pb)
  +------------------------------------------------> Pressure
""",
}

PLOT_ALIASES = {
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
    "cce": "vrel_vs_p_cce", "cmе": "vrel_vs_p_cce",
}


def format_plot_response(relationship_key: str) -> str:
    rule   = PVT_PLOT_RULES.get(relationship_key)
    sketch = ASCII_SKETCHES.get(relationship_key)
    if not rule or not sketch:
        return None
    lines = [
        rule["title_en"], f"({rule['title_ar']})", "",
        "Definition: " + rule["definition"], "",
        f"X-axis: {rule['x_axis']}", f"Y-axis: {rule['y_axis']}", "",
        "Shape: " + rule["shape"], "",
    ]
    for region, key in [
        ("Above saturation pressure", "above_saturation"),
        ("At saturation pressure",    "at_saturation"),
        ("Below saturation pressure", "below_saturation"),
    ]:
        if rule[key] != "n/a":
            lines.append(f"{region}: {rule[key]}")
    lines += ["", "Pivot: " + rule["pivot"], "",
              "Common AI mistakes to avoid:", ]
    for m in rule["common_ai_mistakes"]:
        lines.append("  - " + m)
    lines += ["", "ASCII sketch:", sketch]
    return "\n".join(lines)


# ─────────────────────────────────────────────
#  PVT MATPLOTLIB PLOT GENERATOR  (NEW FEATURE)
# ─────────────────────────────────────────────

# Style constants
PLOT_STYLE = {
    "figure.facecolor": "#0D1117",
    "axes.facecolor":   "#161B22",
    "axes.edgecolor":   "#30363D",
    "axes.labelcolor":  "#C9D1D9",
    "xtick.color":      "#8B949E",
    "ytick.color":      "#8B949E",
    "grid.color":       "#21262D",
    "grid.linestyle":   "--",
    "grid.alpha":       0.6,
    "text.color":       "#C9D1D9",
    "font.family":      "DejaVu Sans",
}


def _apply_dark_style(ax, fig):
    """Apply dark theme to matplotlib figure."""
    fig.patch.set_facecolor("#0D1117")
    ax.set_facecolor("#161B22")
    ax.spines["bottom"].set_color("#30363D")
    ax.spines["left"].set_color("#30363D")
    ax.spines["top"].set_color("#30363D")
    ax.spines["right"].set_color("#30363D")
    ax.tick_params(colors="#8B949E")
    ax.xaxis.label.set_color("#C9D1D9")
    ax.yaxis.label.set_color("#C9D1D9")
    ax.title.set_color("#F0F6FC")
    ax.grid(True, color="#21262D", linestyle="--", alpha=0.6)


def generate_pvt_plot_png(
    relationship_key: str,
    pressures: list,
    values: list,
    pb_or_pd: float = None,
    well_name: str = "",
    title_override: str = None,
) -> bytes:
    """
    Generate a professional PVT plot PNG.
    Returns PNG bytes to send via Telegram.
    """
    rule = PVT_PLOT_RULES.get(relationship_key)
    if not rule:
        return None

    color  = rule.get("plot_color", "#2E86C1")
    ylabel = rule.get("y_label", rule["y_axis"])
    title  = title_override or rule["title_en"]
    if well_name:
        title = f"{title}  |  {well_name}"

    fig, ax = plt.subplots(figsize=(10, 6), dpi=150)
    _apply_dark_style(ax, fig)

    # Sort by pressure ascending for clean plot
    pairs   = sorted(zip(pressures, values))
    p_vals  = [p for p, v in pairs]
    y_vals  = [v for p, v in pairs]

    # ── Main curve ──
    ax.plot(p_vals, y_vals, color=color, linewidth=2.5,
            marker="o", markersize=5, markerfacecolor="#F0F6FC",
            markeredgecolor=color, markeredgewidth=1.5,
            label=rule["title_en"], zorder=3)

    # ── Fill under curve ──
    ax.fill_between(p_vals, y_vals, alpha=0.08, color=color, zorder=2)

    # ── Bubble Point / Dew Point vertical line ──
    if pb_or_pd is not None:
        ax.axvline(x=pb_or_pd, color="#F39C12", linewidth=2,
                   linestyle="--", alpha=0.9, zorder=4)

        # Find y value nearest to Pb/Pd for annotation
        closest_y = None
        min_dist  = float("inf")
        for p, v in pairs:
            if abs(p - pb_or_pd) < min_dist:
                min_dist  = abs(p - pb_or_pd)
                closest_y = v

        sat_label = "Pb" if relationship_key not in ("liquid_dropout_vs_p", "cgr_vs_p") else "Pd"
        ax.annotate(
            f"{sat_label} = {pb_or_pd:,.0f} psia",
            xy=(pb_or_pd, closest_y if closest_y else min(y_vals)),
            xytext=(pb_or_pd + (max(p_vals) - min(p_vals)) * 0.04,
                    closest_y + (max(y_vals) - min(y_vals)) * 0.05 if closest_y else min(y_vals)),
            color="#F39C12",
            fontsize=10,
            fontweight="bold",
            arrowprops=dict(arrowstyle="->", color="#F39C12", lw=1.5),
            zorder=5,
        )

        # Shade regions
        if relationship_key in ("bo_vs_p", "rs_vs_p", "oil_visc_vs_p", "oil_density_vs_p"):
            ax.axvspan(min(p_vals), pb_or_pd, alpha=0.05,
                       color="#E67E22", label="Below Pb (two-phase)")
            ax.axvspan(pb_or_pd, max(p_vals), alpha=0.05,
                       color="#1A5276", label="Above Pb (single-phase)")

    # ── Min/Max annotations ──
    if y_vals:
        max_y   = max(y_vals)
        min_y   = min(y_vals)
        max_p   = p_vals[y_vals.index(max_y)]
        min_p   = p_vals[y_vals.index(min_y)]

        ax.annotate(
            f"Max: {max_y:.4f}",
            xy=(max_p, max_y),
            xytext=(max_p, max_y + (max_y - min_y) * 0.08),
            color="#58A6FF", fontsize=9, ha="center",
            arrowprops=dict(arrowstyle="->", color="#58A6FF", lw=1.2),
        )
        if max_y != min_y:
            ax.annotate(
                f"Min: {min_y:.4f}",
                xy=(min_p, min_y),
                xytext=(min_p, min_y - (max_y - min_y) * 0.1),
                color="#FF7B72", fontsize=9, ha="center",
                arrowprops=dict(arrowstyle="->", color="#FF7B72", lw=1.2),
            )

    # ── Labels ──
    ax.set_xlabel(rule["x_axis"], fontsize=11, labelpad=8)
    ax.set_ylabel(ylabel, fontsize=11, labelpad=8)
    ax.set_title(title, fontsize=13, fontweight="bold", pad=14)

    # ── Legend ──
    handles = [
        Line2D([0], [0], color=color, linewidth=2.5,
               marker="o", markersize=5, label=rule["title_en"]),
    ]
    if pb_or_pd is not None:
        handles.append(
            Line2D([0], [0], color="#F39C12", linewidth=2,
                   linestyle="--", label=f"{'Pb' if 'oil' in relationship_key else 'Pd/Pb'} = {pb_or_pd:,.0f} psia")
        )
    ax.legend(handles=handles, facecolor="#161B22", edgecolor="#30363D",
              labelcolor="#C9D1D9", fontsize=9, loc="best")

    # ── Data info box ──
    info_text = (
        f"Points: {len(pressures)}\n"
        f"P range: {min(pressures):,.0f} - {max(pressures):,.0f} psia\n"
        f"Y range: {min(values):.4f} - {max(values):.4f}"
    )
    ax.text(0.02, 0.97, info_text, transform=ax.transAxes,
            fontsize=8, verticalalignment="top",
            color="#8B949E", family="monospace",
            bbox=dict(boxstyle="round,pad=0.4", facecolor="#0D1117",
                      edgecolor="#30363D", alpha=0.8))

    # ── Watermark ──
    fig.text(0.99, 0.01, "PVT Engineering Bot",
             ha="right", va="bottom", fontsize=7,
             color="#30363D", style="italic")

    plt.tight_layout(pad=1.5)

    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=150, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def parse_plot_data_from_text(text: str):
    """
    Parse pressure and value data from user message.
    Supports formats:
      p=100,200,300 v=1.1,1.2,1.3
      OR inline CSV: 100,1.1 200,1.2 300,1.3
      OR CSV attachment (handled separately)
    Returns (pressures, values, pb_or_pd, well_name)
    """
    pressures  = []
    values     = []
    pb_or_pd   = None
    well_name  = ""

    # Well name
    wm = re.search(r"well[=\s]+([A-Za-z0-9_\-]+)", text, re.IGNORECASE)
    if wm:
        well_name = wm.group(1)

    # Pb / Pd
    pbm = re.search(r"(?:pb|pd)[=\s]+([\d.]+)", text, re.IGNORECASE)
    if pbm:
        pb_or_pd = float(pbm.group(1))

    # p=... v=... format
    pm = re.search(r"p=\[?([\d,.\s]+)\]?", text)
    vm = re.search(r"v=\[?([\d,.\s]+)\]?", text)
    if pm and vm:
        pressures = [float(x.strip()) for x in pm.group(1).split(",") if x.strip()]
        values    = [float(x.strip()) for x in vm.group(1).split(",") if x.strip()]
        return pressures, values, pb_or_pd, well_name

    # Inline pairs: "500 1.15 1000 1.18 ..."
    numbers = re.findall(r"[-+]?\d*\.?\d+", text)
    nums    = [float(n) for n in numbers]
    # Exclude pb_or_pd from the pair list if found
    if pb_or_pd in nums:
        nums = [n for n in nums if n != pb_or_pd]
    if len(nums) >= 4 and len(nums) % 2 == 0:
        pressures = nums[0::2]
        values    = nums[1::2]

    return pressures, values, pb_or_pd, well_name


def parse_csv_for_plot(csv_text: str):
    """
    Parse CSV content with header row.
    Expected: pressure,value  OR  P,Bo  OR  Pressure,Rs  etc.
    Returns (pressures, values)
    """
    pressures = []
    values    = []
    reader    = csv.reader(csv_text.strip().splitlines())
    header_skipped = False
    for row in reader:
        if not row or len(row) < 2:
            continue
        try:
            p = float(row[0].strip())
            v = float(row[1].strip())
            pressures.append(p)
            values.append(v)
        except ValueError:
            if not header_skipped:
                header_skipped = True   # skip header row
                continue
    return pressures, values


# ─────────────────────────────────────────────
#  CALCULATION ENGINE
# ─────────────────────────────────────────────
EXACT_FORMULAS = {
    "api": {
        "name_en": "API Gravity", "name_ar": "درجة API",
        "inputs": ["sg"], "units": {"sg": "dimensionless (SG, water=1.0)"},
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
        "name_en": "Original Oil In Place (Volumetric)", "name_ar": "النفط الأصلي في المكمن",
        "inputs": ["area", "h", "phi", "sw", "bo"],
        "units": {"area": "acres", "h": "ft", "phi": "fraction",
                  "sw": "fraction", "bo": "rb/STB"},
        "formula_str": "OOIP = (7758 x A x h x phi x (1-Sw)) / Bo",
        "func": lambda area, h, phi, sw, bo: (7758 * area * h * phi * (1 - sw)) / bo,
        "output_unit": "STB",
        "validation": lambda area, h, phi, sw, bo: 0 < phi < 1 and 0 <= sw < 1 and bo > 0,
        "note": "Bo في المقام: زيادة Bo تقلل OOIP المحسوب.",
    },
    "ogip": {
        "name_en": "Original Gas In Place (Volumetric)", "name_ar": "الغاز الأصلي في المكمن",
        "inputs": ["area", "h", "phi", "sw", "bg"],
        "units": {"area": "acres", "h": "ft", "phi": "fraction",
                  "sw": "fraction", "bg": "rb/scf"},
        "formula_str": "OGIP = (43560 x A x h x phi x (1-Sw)) / Bg",
        "func": lambda area, h, phi, sw, bg: (43560 * area * h * phi * (1 - sw)) / bg,
        "output_unit": "scf",
        "validation": lambda area, h, phi, sw, bg: 0 < phi < 1 and 0 <= sw < 1 and bg > 0,
    },
    "darcy": {
        "name_en": "Darcy Linear Flow Rate", "name_ar": "معدل التدفق الخطي",
        "inputs": ["k", "area", "dp", "mu", "length"],
        "units": {"k": "mD", "area": "ft2", "dp": "psi", "mu": "cP", "length": "ft"},
        "formula_str": "q = 0.001127 x k x A x dP / (mu x L)",
        "func": lambda k, area, dp, mu, length: (0.001127 * k * area * dp) / (mu * length),
        "output_unit": "bbl/day",
        "validation": lambda k, area, dp, mu, length: all(v > 0 for v in [k, area, dp, mu, length]),
    },
    "recovery_factor": {
        "name_en": "Recovery Factor", "name_ar": "عامل الاسترداد",
        "inputs": ["np", "ooip"], "units": {"np": "STB", "ooip": "STB"},
        "formula_str": "RF = NP / OOIP x 100",
        "func": lambda np_val, ooip: (np_val / ooip) * 100,
        "output_unit": "%",
        "validation": lambda np_val, ooip: 0 <= np_val <= ooip,
    },
    "productivity_index": {
        "name_en": "Productivity Index", "name_ar": "مؤشر الإنتاجية",
        "inputs": ["q", "pr", "pwf"], "units": {"q": "STB/day", "pr": "psi", "pwf": "psi"},
        "formula_str": "PI = q / (Pr - Pwf)",
        "func": lambda q, pr, pwf: q / (pr - pwf),
        "output_unit": "STB/day/psi",
        "validation": lambda q, pr, pwf: pr > pwf and q > 0,
    },
    "hydrostatic": {
        "name_en": "Hydrostatic Pressure", "name_ar": "الضغط الهيدروستاتيكي",
        "inputs": ["mw", "tvd"], "units": {"mw": "ppg", "tvd": "ft"},
        "formula_str": "P (psi) = 0.052 x MW x TVD",
        "func": lambda mw, tvd: 0.052 * mw * tvd,
        "output_unit": "psi",
        "validation": lambda mw, tvd: 6 < mw < 25 and tvd > 0,
    },
    "mud_weight_required": {
        "name_en": "Required Mud Weight", "name_ar": "وزن الطين المطلوب",
        "inputs": ["p_target", "tvd"], "units": {"p_target": "psi", "tvd": "ft"},
        "formula_str": "MW (ppg) = P_target / (0.052 x TVD)",
        "func": lambda p_target, tvd: p_target / (0.052 * tvd),
        "output_unit": "ppg",
        "validation": lambda p_target, tvd: p_target > 0 and tvd > 0,
        "note": "Add 0.2-0.5 ppg overbalance safety margin.",
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
        "name_en": "Water Cut", "name_ar": "نسبة الماء المنتج",
        "inputs": ["qw", "qo"], "units": {"qw": "bbl/day", "qo": "bbl/day"},
        "formula_str": "WC = qw / (qo + qw) x 100",
        "func": lambda qw, qo: (qw / (qo + qw)) * 100,
        "output_unit": "%",
        "validation": lambda qw, qo: qw >= 0 and qo >= 0 and (qw + qo) > 0,
    },
    "wor": {
        "name_en": "Water-Oil Ratio (WOR)", "name_ar": "نسبة الماء إلى الزيت",
        "inputs": ["qw", "qo"], "units": {"qw": "bbl/day", "qo": "bbl/day"},
        "formula_str": "WOR = qw / qo",
        "func": lambda qw, qo: qw / qo,
        "output_unit": "bbl/bbl",
        "validation": lambda qw, qo: qw >= 0 and qo > 0,
    },
    "gor_produced": {
        "name_en": "Produced GOR", "name_ar": "نسبة الغاز إلى الزيت المنتجة",
        "inputs": ["qg", "qo"], "units": {"qg": "scf/day", "qo": "STB/day"},
        "formula_str": "GOR = qg / qo",
        "func": lambda qg, qo: qg / qo,
        "output_unit": "scf/STB",
        "validation": lambda qg, qo: qg >= 0 and qo > 0,
    },
    "npv": {
        "name_en": "Net Present Value (single cash flow)",
        "name_ar": "صافي القيمة الحالية",
        "inputs": ["cf", "rate", "t"],
        "units": {"cf": "$", "rate": "fraction", "t": "years"},
        "formula_str": "PV = CF / (1+r)^t",
        "func": lambda cf, rate, t: cf / (1 + rate) ** t,
        "output_unit": "$",
        "validation": lambda cf, rate, t: rate > -1 and t >= 0,
    },
}

CORRELATIONS = {
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
}


def parse_kv_args(text: str) -> dict:
    kv = {}
    pairs = re.findall(r"(\w+)\s*=\s*([-+]?\d*\.?\d+)", text)
    for k, v in pairs:
        kv[k.lower()] = float(v)
    return kv


def run_exact_calc(calc_type: str, **kwargs) -> str:
    spec = EXACT_FORMULAS.get(calc_type)
    if not spec:
        return None
    missing = [k for k in spec["inputs"] if k not in kwargs]
    if missing:
        lines = [f"DATA REQUIRED for {spec['name_en']} ({spec['name_ar']}):"]
        for inp in spec["inputs"]:
            lines.append(f"  {inp} ({spec['units'][inp]})")
        lines.append(f"\nUsage: /calc {calc_type} " +
                     " ".join(f"{k}=value" for k in spec["inputs"]))
        return "\n".join(lines)
    values = [kwargs[k] for k in spec["inputs"]]
    if "validation" in spec and not spec["validation"](*values):
        return (f"Warning: inputs outside normal range for {spec['name_en']}.\n"
                f"Values: {dict(zip(spec['inputs'], values))}\n"
                "Please verify units and values.")
    result = spec["func"](*values)
    out = [
        f"{spec['name_en']} ({spec['name_ar']})", "",
        f"Formula: {spec['formula_str']}",
        "Inputs: " + ", ".join(f"{k}={v}" for k, v in zip(spec["inputs"], values)),
        f"Result: {result:,.4f} {spec['output_unit']}",
    ]
    if "classify" in spec:
        out.append(f"Classification: {spec['classify'](result)}")
    if "note" in spec:
        out += ["", "Note: " + spec["note"]]
    return "\n".join(out)


def run_correlation(calc_type: str, **kwargs) -> str:
    spec = CORRELATIONS.get(calc_type)
    if not spec:
        return None
    missing = [k for k in spec["inputs"] if k not in kwargs]
    if missing:
        lines = [f"DATA REQUIRED for {spec['name_en']}:"]
        for inp in spec["inputs"]:
            lines.append(f"  {inp} ({spec['units'][inp]})")
        lines.append(f"\nUsage: /estimate {calc_type} " +
                     " ".join(f"{k}=value" for k in spec["inputs"]))
        return "\n".join(lines)
    values     = [kwargs[k] for k in spec["inputs"]]
    result     = spec["func"](*values)
    oor        = []
    for inp, (lo, hi) in spec.get("applicability", {}).items():
        v = kwargs.get(inp)
        if v is not None and not (lo <= v <= hi):
            oor.append(f"{inp}={v} (range: {lo}-{hi})")
    out = [
        f"CORRELATION ESTIMATE -- {spec['name_en']}  ({spec['name_ar']})", "",
        f"Formula: {spec['formula_str']}",
        "Inputs: " + ", ".join(f"{k}={v}" for k, v in zip(spec["inputs"], values)),
        f"Estimate: {result:,.2f} {spec['output_unit']}",
    ]
    if oor:
        out += ["", "Warning -- inputs outside applicability range: " + "; ".join(oor)]
    out += ["", "Note: Correlation estimate only. Verify against lab CCE/DV data."]
    return "\n".join(out)


# ─────────────────────────────────────────────
#  UNIT CONVERSIONS
# ─────────────────────────────────────────────
UNIT_CONVERSIONS = {
    ("psi", "bar"):      lambda v: v * 0.0689476,
    ("bar", "psi"):      lambda v: v / 0.0689476,
    ("psi", "kpa"):      lambda v: v * 6.89476,
    ("kpa", "psi"):      lambda v: v / 6.89476,
    ("ppg", "lb/ft3"):   lambda v: v * 7.4805,
    ("lb/ft3", "ppg"):   lambda v: v / 7.4805,
    ("ppg", "sg"):       lambda v: v / 8.345,
    ("sg", "ppg"):       lambda v: v * 8.345,
    ("scf/stb", "m3/m3"):lambda v: v * 0.1781,
    ("m3/m3", "scf/stb"):lambda v: v / 0.1781,
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


def run_unit_conversion(value: float, from_unit: str, to_unit: str) -> str:
    key  = (from_unit.lower().strip(), to_unit.lower().strip())
    func = UNIT_CONVERSIONS.get(key)
    if not func:
        available = sorted(set(k[0] for k in UNIT_CONVERSIONS))
        return (f"Conversion not available: {from_unit} -> {to_unit}.\n"
                f"Available from-units: {', '.join(available)}")
    return f"{value} {from_unit} = {func(value):,.4f} {to_unit}"


# ─────────────────────────────────────────────
#  PVT TREND VALIDATOR  (/check)
# ─────────────────────────────────────────────
def check_pvt_trend(relationship_key: str, pressures: list,
                     values: list, pb_or_pd: float = None) -> str:
    if len(pressures) != len(values) or len(pressures) < 2:
        return "Insufficient data. Need at least 2 (pressure, value) pairs."

    paired = sorted(zip(pressures, values))
    issues = []
    rule   = PVT_PLOT_RULES.get(relationship_key)
    if not rule:
        return (f"Unknown relationship '{relationship_key}'.\n"
                f"Available: {', '.join(PLOT_ALIASES.keys())}")

    if relationship_key == "rs_vs_p":
        if pb_or_pd:
            above = [(p, v) for p, v in paired if p >= pb_or_pd]
            below = [(p, v) for p, v in paired if p < pb_or_pd]
            if len(above) >= 2:
                vals_above = [v for _, v in above]
                variation  = max(vals_above) - min(vals_above)
                if variation > 0.05 * max(vals_above):
                    issues.append(
                        f"Rs varies above Pb (variation={variation:.1f}). "
                        "Rs must be CONSTANT = Rsi above Pb."
                    )
            if len(below) >= 2:
                sb = sorted(below)
                for i in range(1, len(sb)):
                    if sb[i][1] < sb[i - 1][1]:
                        issues.append(
                            f"Rs at P={sb[i][0]:.0f} < Rs at P={sb[i-1][0]:.0f}: "
                            "below Pb Rs must INCREASE with increasing pressure."
                        )
                        break

    elif relationship_key == "bo_vs_p":
        if pb_or_pd:
            below = sorted([(p, v) for p, v in paired if p < pb_or_pd])
            above = sorted([(p, v) for p, v in paired if p >= pb_or_pd])
            for i in range(1, len(below)):
                if below[i][1] < below[i - 1][1]:
                    issues.append(
                        f"Bo at P={below[i][0]:.0f} < Bo at P={below[i-1][0]:.0f}: "
                        "below Pb Bo must INCREASE with increasing pressure (max at Pb)."
                    )
                    break
            for i in range(1, len(above)):
                if above[i][1] > above[i - 1][1]:
                    issues.append(
                        f"Bo at P={above[i][0]:.0f} > Bo at P={above[i-1][0]:.0f}: "
                        "above Pb Bo must DECREASE with increasing pressure."
                    )
                    break

    elif relationship_key == "oil_visc_vs_p":
        if pb_or_pd:
            below = sorted([(p, v) for p, v in paired if p < pb_or_pd])
            for i in range(1, len(below)):
                if below[i][1] > below[i - 1][1]:
                    issues.append(
                        f"Viscosity at P={below[i][0]:.0f} > at P={below[i-1][0]:.0f}: "
                        "below Pb viscosity must DECREASE with increasing pressure (min at Pb)."
                    )
                    break

    elif relationship_key == "liquid_dropout_vs_p":
        vals  = [v for _, v in paired]
        mono_inc = all(vals[i] <= vals[i+1] for i in range(len(vals)-1))
        mono_dec = all(vals[i] >= vals[i+1] for i in range(len(vals)-1))
        if mono_inc or mono_dec:
            issues.append(
                "Liquid Dropout appears monotonic (missing retrograde peak). "
                "Correct: 0% at Pd, rises to peak, then decreases (re-vaporization)."
            )
        if pb_or_pd:
            at_pd = [(p, v) for p, v in paired if abs(p - pb_or_pd) < 0.05 * pb_or_pd]
            if at_pd and at_pd[0][1] > 5:
                issues.append(
                    f"Dropout at Pd ({at_pd[0][0]:.0f} psia) = {at_pd[0][1]:.1f}% "
                    "-- should be ~0% at dew point."
                )

    elif relationship_key == "z_vs_p":
        vals     = [v for _, v in paired]
        mono_inc = all(vals[i] <= vals[i+1] for i in range(len(vals)-1))
        mono_dec = all(vals[i] >= vals[i+1] for i in range(len(vals)-1))
        if mono_inc or mono_dec:
            issues.append(
                "Z-factor appears monotonic. Correct shape is U-shaped: "
                "starts ~1, decreases to minimum, then increases."
            )
        if any(v < 0.4 or v > 2.0 for v in vals):
            issues.append("Some Z values outside plausible range (0.4-2.0). Check data/units.")

    elif relationship_key == "bg_vs_p":
        for i in range(1, len(paired)):
            if paired[i][1] > paired[i-1][1]:
                issues.append(
                    f"Bg at P={paired[i][0]:.0f} > Bg at P={paired[i-1][0]:.0f}: "
                    "Bg must DECREASE continuously with increasing pressure."
                )
                break

    elif relationship_key == "cgr_vs_p":
        if pb_or_pd:
            below = sorted([(p, v) for p, v in paired if p < pb_or_pd])
            for i in range(1, len(below)):
                if below[i][1] < below[i-1][1]:
                    issues.append(
                        f"CGR at P={below[i][0]:.0f} < at P={below[i-1][0]:.0f}: "
                        "below Pd CGR must DECREASE with decreasing pressure."
                    )
                    break

    if not issues:
        return (f"Check: {rule['title_en']}\n\n"
                "Result: Data appears consistent with expected physical behavior (BLOCK 5).")

    return (
        f"Check: {rule['title_en']} -- Issues detected:\n\n"
        + "\n".join(f"- {issue}" for issue in issues)
        + "\n\nSee /plot " + relationship_key.split("_vs_")[0] + " for correct shape."
    )


# ─────────────────────────────────────────────
#  PVTO / PVDO / PVTG / PVDG SKELETONS
# ─────────────────────────────────────────────
def generate_pvto_skeleton() -> str:
    return (
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


def generate_pvdo_skeleton() -> str:
    return (
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


def generate_pvtg_skeleton() -> str:
    return (
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


def generate_pvdg_skeleton() -> str:
    return (
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


# ─────────────────────────────────────────────
#  SIMULATION EXPORT DECISION
# ─────────────────────────────────────────────
EXPORT_SIM_DECISIONS = {
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

EXPORT_SIM_ALIASES = {
    "black oil": "black_oil", "black_oil": "black_oil",
    "زيت أسود": "black_oil", "زيت تقليدي": "black_oil",
    "volatile oil": "volatile_oil", "volatile_oil": "volatile_oil",
    "زيت متطاير": "volatile_oil",
    "gas condensate": "gas_condensate", "condensate": "gas_condensate",
    "gas_condensate": "gas_condensate", "غاز مكثف": "gas_condensate",
    "wet gas": "wet_gas", "wet_gas": "wet_gas", "غاز رطب": "wet_gas",
    "dry gas": "dry_gas", "dry_gas": "dry_gas", "غاز جاف": "dry_gas",
}


def export_sim_decision(fluid_type: str, near_critical: bool = False) -> str:
    key = EXPORT_SIM_ALIASES.get(fluid_type.lower().strip())
    if not key:
        return (
            "Fluid type not recognized. Available:\n"
            "black oil, volatile oil, gas condensate, wet gas, dry gas\n\n"
            "Usage: /export_sim <fluid_type> [near_critical]\n"
            "Example: /export_sim gas condensate near_critical"
        )
    d   = EXPORT_SIM_DECISIONS[key]
    out = [
        f"Simulation Decision -- {fluid_type}", "",
        f"Required Table: {d['table']}",
        f"Recommended Simulator: {d['simulator']}",
        f"Reason: {d['reason']}",
    ]
    if d["warning"]:
        out += ["", f"Warning: {d['warning']}"]
    if near_critical and key in ("volatile_oil", "gas_condensate"):
        out += ["",
                "Additional Near-Critical Warning: Black-Oil assumptions break down "
                "near the critical point. Compositional (EOS) simulation recommended."]
    return "\n".join(out)


# ─────────────────────────────────────────────
#  TEXT CLEANER
# ─────────────────────────────────────────────
def clean_text(text: str) -> str:
    text = str(text)
    fixes = {
        "**": "", "###": "", "##": "", "[": "", "]": "",
        "Pressuring Volume and Temperature": "Pressure-Volume-Temperature",
        "الضغط البيني": "معامل حجم التكوين",
        "المعامل البيني": "معامل حجم التكوين",
        "الترشيح": "نسبة الغاز المذاب",
        "النسبة المئوية للغاز": "نسبة الغاز إلى الزيت",
        "الويسكوزية": "اللزوجة",
        "الليزج": "اللزوجة",
        "الحفرة": "المكمن",
    }
    for wrong, right in fixes.items():
        text = text.replace(wrong, right)
    return text.strip()


# ─────────────────────────────────────────────
#  MESSAGING HELPERS
# ─────────────────────────────────────────────
def send_message(chat_id: int, text: str) -> None:
    """FIX #10: Split on newlines to avoid cutting words."""
    text = clean_text(text)
    if not text:
        text = "No response generated."

    # Split at natural newline boundaries near 3800 chars
    chunks = []
    current = ""
    for line in text.split("\n"):
        if len(current) + len(line) + 1 > 3800:
            if current:
                chunks.append(current.strip())
            current = line
        else:
            current = current + "\n" + line if current else line
    if current:
        chunks.append(current.strip())

    for chunk in chunks:
        if not chunk:
            continue
        try:
            resp = requests.post(
                f"{TELEGRAM_URL}/sendMessage",
                json={"chat_id": chat_id, "text": chunk},
                timeout=15,
            )
            if not resp.ok:
                log.warning("sendMessage failed: %s", resp.text[:200])
        except Exception as e:
            log.error("send_message error: %s", e)
        time.sleep(0.35)


def send_photo_bytes(chat_id: int, png_bytes: bytes, caption: str = "") -> bool:
    """Send a PNG image (bytes) to Telegram chat."""
    try:
        resp = requests.post(
            f"{TELEGRAM_URL}/sendPhoto",
            data={"chat_id": chat_id, "caption": caption},
            files={"photo": ("pvt_plot.png", png_bytes, "image/png")},
            timeout=30,
        )
        if resp.ok:
            log.info("Photo sent to chat_id=%s", chat_id)
            return True
        else:
            log.warning("sendPhoto failed: %s", resp.text[:200])
            return False
    except Exception as e:
        log.error("send_photo_bytes error: %s", e)
        return False


def send_document(chat_id: int, file_bytes: bytes, filename: str,
                   caption: str, mime: str = "text/html") -> None:
    try:
        resp = requests.post(
            f"{TELEGRAM_URL}/sendDocument",
            data={"chat_id": chat_id, "caption": caption},
            files={"document": (filename, file_bytes, mime)},
            timeout=20,
        )
        if not resp.ok:
            log.warning("sendDocument failed: %s", resp.text[:200])
    except Exception as e:
        log.error("send_document error: %s", e)
        send_message(chat_id, f"Error sending file: {e}")


def download_file(file_id: str, suffix: str = ".bin"):
    try:
        info = requests.get(
            f"{TELEGRAM_URL}/getFile",
            params={"file_id": file_id},
            timeout=15,
        ).json()
        if not info.get("ok"):
            log.warning("getFile failed: %s", info)
            return None
        url  = (f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/"
                f"{info['result']['file_path']}")
        data = requests.get(url, timeout=60).content
        tmp  = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        tmp.write(data)
        tmp.close()
        return tmp.name
    except Exception as e:
        log.error("download_file error: %s", e)
        return None


def extract_pdf_text(path: str) -> str:
    """FIX #4: try pypdf first (modern), fallback to PyPDF2 (legacy)."""
    if PdfReader is None:
        return ""
    try:
        reader = PdfReader(path)
        return "\n\n".join(
            p.extract_text() for p in reader.pages
            if p.extract_text()
        ).strip()
    except Exception as e:
        log.error("PDF extraction error: %s", e)
        return ""


def extract_docx_text(path: str) -> str:
    if DocxDocument is None:
        return ""
    try:
        doc = DocxDocument(path)
        return "\n".join(p.text.strip() for p in doc.paragraphs if p.text.strip())
    except Exception as e:
        log.error("DOCX extraction error: %s", e)
        return ""


def encode_image(path: str) -> str:
    mime, _ = mimetypes.guess_type(path)
    if not mime:
        mime = "image/jpeg"
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return f"data:{mime};base64,{b64}"


# ─────────────────────────────────────────────
#  PDF SECTION SEGMENTATION
# ─────────────────────────────────────────────
PVT_SECTION_HEADERS = [
    "Differential Liberation", "Differential Vaporization",
    "Constant Composition Expansion", "CCE",
    "Constant Volume Depletion", "CVD",
    "Separator Test", "Compositional Analysis",
    "Viscosity", "Recombination", "Reservoir Fluid Properties",
    "Sample Information", "PVT Summary", "Well Test", "Fluid Analysis",
]


def segment_pdf_text(text: str) -> dict:
    sections      = {}
    current_hdr   = "PREAMBLE"
    current_lines = []
    for line in text.split("\n"):
        matched = None
        for hdr in PVT_SECTION_HEADERS:
            if hdr.lower() in line.lower() and len(line.strip()) < 60:
                matched = hdr
                break
        if matched:
            if current_lines:
                sections[current_hdr] = "\n".join(current_lines)
            current_hdr   = matched
            current_lines = []
        else:
            current_lines.append(line)
    if current_lines:
        sections[current_hdr] = "\n".join(current_lines)
    return sections


def format_segmented_context(sections: dict) -> str:
    parts = []
    for hdr, content in sections.items():
        stripped = content.strip()
        if stripped:
            parts.append(f"=== SECTION: {hdr} ===\n{stripped}\n")
    return "\n".join(parts)


MAX_CONTEXT_CHARS = 20000


def store_file_context(chat_id: int, text: str, filename: str) -> str:
    original_len = len(text)
    if original_len > MAX_CONTEXT_CHARS:
        text = text[:MAX_CONTEXT_CHARS]
        FILE_CONTEXT[chat_id] = text
        return (
            f"File read successfully.\n"
            f"Warning: file has {original_len:,} chars; using first {MAX_CONTEXT_CHARS:,} "
            f"as context. If important data is later in the document, send that section separately."
        )
    FILE_CONTEXT[chat_id] = text
    return f"File '{filename}' loaded successfully ({original_len:,} chars). Ready for analysis."


def load_pvt_template():
    try:
        with open("templates/pvt_report_template.txt", "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return "PVT LABORATORY REPORT"


# ─────────────────────────────────────────────
#  AI CALLS
# ─────────────────────────────────────────────
def ask_ai(user_text: str, file_context=None, max_retries: int = 3) -> str:
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            messages = [{"role": "system", "content": SYSTEM_PROMPT}]
            if file_context:
                messages.append({
                    "role": "user",
                    "content": "Reference document context:\n\n" + file_context[:20000],
                })
            messages.append({"role": "user", "content": user_text})

            r = requests.post(
                GROQ_URL,
                headers={"Authorization": f"Bearer {GROQ_API_KEY}",
                         "Content-Type": "application/json"},
                json={"model": TEXT_MODEL, "messages": messages,
                      "temperature": 0.08, "max_tokens": 3000},
                timeout=90,
            )
            if r.status_code == 429:
                last_error = "rate_limit"
                time.sleep(2 ** attempt)
                continue
            if r.status_code == 503:
                last_error = "service_unavailable"
                time.sleep(2 ** attempt)
                continue
            r.raise_for_status()
            data = r.json()
            if "choices" in data:
                return data["choices"][0]["message"]["content"]
            last_error = f"unexpected_response: {str(data)[:300]}"

        except requests.exceptions.Timeout:
            last_error = "timeout"
        except requests.exceptions.ConnectionError:
            last_error = "connection_error"
        except Exception as e:
            last_error = str(e)
            log.error("ask_ai error: %s", e)

    error_map = {
        "rate_limit":          "System busy (rate limit). Please retry in a moment.",
        "service_unavailable": "AI service temporarily unavailable. Retry shortly.",
        "timeout":             "Request timed out. Try again or break into smaller questions.",
        "connection_error":    "Cannot connect to AI service. Check network.",
    }
    return error_map.get(last_error, f"Unexpected error: {last_error}")


def ask_vision_ai(prompt: str, image_path: str,
                   file_context=None, max_retries: int = 2) -> str:
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            full_prompt = prompt
            if file_context:
                full_prompt += "\n\nReference context:\n" + file_context[:10000]

            messages = [{
                "role": "user",
                "content": [
                    {"type": "text",      "text": full_prompt},
                    {"type": "image_url", "image_url": {"url": encode_image(image_path)}},
                ],
            }]
            r = requests.post(
                GROQ_URL,
                headers={"Authorization": f"Bearer {GROQ_API_KEY}",
                         "Content-Type": "application/json"},
                json={"model": VISION_MODEL, "messages": messages,
                      "temperature": 0.08, "max_tokens": 2200},
                timeout=90,
            )
            if r.status_code == 429:
                last_error = "rate_limit"
                time.sleep(2 ** attempt)
                continue
            if r.status_code == 503:
                last_error = "service_unavailable"
                time.sleep(2 ** attempt)
                continue
            r.raise_for_status()
            data = r.json()
            if "choices" in data:
                return data["choices"][0]["message"]["content"]
            last_error = f"unexpected_response: {str(data)[:300]}"

        except requests.exceptions.Timeout:
            last_error = "timeout"
        except requests.exceptions.ConnectionError:
            last_error = "connection_error"
        except Exception as e:
            last_error = str(e)
            log.error("ask_vision_ai error: %s", e)

    error_map = {
        "rate_limit":          "System busy. Retry shortly.",
        "service_unavailable": "Image analysis service unavailable. Retry shortly.",
        "timeout":             "Image analysis timed out. Try again.",
        "connection_error":    "Cannot connect to image analysis service.",
    }
    return error_map.get(last_error, f"Image analysis error: {last_error}")


# ─────────────────────────────────────────────
#  GRAPH INTERPRETATION PROMPT
# ─────────────────────────────────────────────
def build_graph_prompt(user_text: str) -> str:
    reference_summary = "\n".join(
        f"- {r['title_en']}: {r['shape']} | Pivot: {r['pivot']}"
        for r in PVT_PLOT_RULES.values()
    )
    return (
        SYSTEM_PROMPT
        + "\n\nTASK: Analyze the uploaded petroleum engineering plot/image.\n\n"
        "REFERENCE SHAPES (BLOCK 5 ground truth):\n"
        + reference_summary
        + "\n\nSTEPS:\n"
        "1. Identify X and Y axis labels, units, scale.\n"
        "2. Match to ONE reference relationship.\n"
        "3. AGREE or DISAGREE with the reference shape.\n"
        "4. If AGREE: identify saturation pressure location.\n"
        "5. If DISAGREE: state discrepancy and suggest causes.\n"
        "6. Engineering interpretation and recommendation.\n\n"
        f"User question: {user_text}\n\n"
        "Follow BLOCK 13 formatting (no markdown, clear headings)."
    )


# ─────────────────────────────────────────────
#  FILE / PHOTO UPLOAD HANDLERS
# ─────────────────────────────────────────────
def handle_document_upload(chat_id: int, doc: dict) -> None:
    try:
        file_id   = doc["file_id"]
        file_name = doc.get("file_name", "file")
        mime      = doc.get("mime_type", "")
        ext       = os.path.splitext(file_name)[1].lower() or ".bin"
        path      = download_file(file_id, ext)

        if not path:
            send_message(chat_id, "Error downloading file.")
            return

        lower = file_name.lower()

        if lower.endswith(".pdf"):
            text = extract_pdf_text(path)
            if not text:
                send_message(
                    chat_id,
                    "PDF read but no text extracted. File may be scanned (image-based).\n"
                    "Send pages as images or use a text-layer PDF."
                )
                return
            sections  = segment_pdf_text(text)
            formatted = format_segmented_context(sections)
            status    = store_file_context(chat_id, formatted, file_name)
            send_message(chat_id, status + "\nType /analyze to analyze it.")

        elif lower.endswith(".docx"):
            text = extract_docx_text(path)
            if not text:
                send_message(chat_id, "DOCX read but no text found.")
                return
            status = store_file_context(chat_id, text, file_name)
            send_message(chat_id, status + "\nType /analyze to analyze it.")

        elif lower.endswith(".csv"):
            # CSV upload for /plot data
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    csv_text = f.read()
                FILE_CONTEXT[chat_id] = "__CSV__\n" + csv_text
                send_message(
                    chat_id,
                    "CSV file loaded. Now use /plot <type> to generate the chart.\n"
                    "Example: /plot bo pb=2500 well=MyWell"
                )
            except Exception as e:
                send_message(chat_id, f"Error reading CSV: {e}")

        elif mime.startswith("image/") or lower.endswith((".png", ".jpg", ".jpeg", ".webp")):
            IMAGE_CONTEXT[chat_id] = path
            send_message(chat_id, "Image received. Type /graph to analyze the chart.")

        else:
            send_message(chat_id, "Supported: PDF, DOCX, CSV, or image (PNG/JPG/WEBP).")

    except Exception as e:
        log.error("handle_document_upload error: %s", e)
        send_message(chat_id, f"Error processing file: {e}")


def handle_photo_upload(chat_id: int, photos: list) -> None:
    try:
        path = download_file(photos[-1]["file_id"], ".jpg")
        if path:
            IMAGE_CONTEXT[chat_id] = path
            send_message(chat_id, "Image received. Type /graph to analyze the chart.")
        else:
            send_message(chat_id, "Error downloading image.")
    except Exception as e:
        log.error("handle_photo_upload error: %s", e)
        send_message(chat_id, f"Error processing image: {e}")


# ─────────────────────────────────────────────
#  GLOSSARY HTML GENERATOR (FIX #11: cached)
# ─────────────────────────────────────────────
def generate_glossary_html() -> bytes:
    """Generate interactive HTML glossary. Cached after first call."""
    if "html" in _GLOSSARY_CACHE:
        return _GLOSSARY_CACHE["html"]

    category_config = {
        "PVT":                         ("b-pvt", "PVT"),
        "Reservoir":                   ("b-res", "Reservoir"),
        "Production":                  ("b-pro", "Production"),
        "Drilling":                    ("b-drl", "Drilling"),
        "Economics":                   ("b-eco", "Economics"),
        "PVT - Gas Condensate":        ("b-pvt", "Gas Cond."),
        "Production - Gas Condensate": ("b-pro", "Gas Cond."),
        "Phase Behavior":              ("b-pvt", "Phase"),
    }

    term_records = []
    for t in KNOWLEDGE_BASE:
        cls, lbl = category_config.get(t["category"], ("b-pvt", t["category"]))
        extras   = []
        if t.get("typical_range") and t["typical_range"] not in ("n/a", "varies widely"):
            extras.append("Typical range: " + t["typical_range"] + " (" + t["unit"] + ")")
        trend = t.get("trend", "")
        skip  = any(x in trend for x in ("n/a", "static", "indicator", "event",
                                           "descriptive", "calculated", "controlled",
                                           "varies", "depends"))
        if trend and not skip:
            extras.append("Trend: " + trend)
        term_records.append({
            "ar":     t["ar"],
            "en":     t["en"],
            "cls":    cls,
            "lbl":    lbl,
            "def":    t["def_ar"],
            "extras": extras,
            "search": (t["en"] + " " + t["ar"] + " " + t["def_ar"]).lower(),
        })

    plot_records = []
    for key, rule in PVT_PLOT_RULES.items():
        rows = []
        if rule["above_saturation"] != "n/a":
            rows.append("Above saturation: " + rule["above_saturation"])
        if rule["at_saturation"] != "n/a":
            rows.append("At saturation: " + rule["at_saturation"])
        if rule["below_saturation"] != "n/a":
            rows.append("Below saturation: " + rule["below_saturation"])
        plot_records.append({
            "key":        key,
            "title_ar":   rule["title_ar"],
            "title_en":   rule["title_en"],
            "definition": rule["definition"],
            "x_axis":     rule["x_axis"],
            "y_axis":     rule["y_axis"],
            "shape":      rule["shape"],
            "rows":       rows,
            "pivot":      rule["pivot"],
            "mistakes":   rule["common_ai_mistakes"],
            "sketch":     ASCII_SKETCHES.get(key, ""),
        })

    term_json = _json.dumps(term_records, ensure_ascii=False)
    plot_json = _json.dumps(plot_records, ensure_ascii=False)

    css = """
@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@300;400;600;700;900&family=Fira+Code:wght@400;600&display=swap');
:root{--crude:#3d1f00;--amber:#c8760a;--gold:#e8a020;--light:#fef3dc;--surface:#f5f0e8;
  --paper:#fdfaf4;--border:#ddd0b8;--muted:#7a6a58;--dbg:#0d1117}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Cairo',sans-serif;background:var(--surface);color:#111;line-height:1.7}
header{background:var(--crude);color:var(--paper);padding:2.5rem 2rem;text-align:center}
header h1{font-size:clamp(1.6rem,4vw,2.4rem);font-weight:900}
header h1 span{color:var(--gold)}
nav{display:flex;justify-content:center;gap:.5rem;flex-wrap:wrap;padding:1.2rem;
    background:var(--paper);border-bottom:2px solid var(--border);
    position:sticky;top:0;z-index:100;box-shadow:0 2px 10px rgba(0,0,0,.07)}
nav button{padding:.45rem 1.1rem;border:2px solid var(--border);border-radius:999px;
    background:transparent;font-family:inherit;font-size:.82rem;font-weight:600;
    color:var(--muted);cursor:pointer;transition:all .2s}
nav button:hover{border-color:var(--amber);color:var(--amber)}
nav button.active{background:var(--amber);border-color:var(--amber);color:#fff}
main{max-width:1100px;margin:0 auto;padding:2rem 1.5rem 4rem}
.sec{display:none}.sec.active{display:block}
.search input{width:100%;padding:.7rem 1.2rem;border:2px solid var(--border);
    border-radius:8px;font-family:inherit;font-size:1rem;background:var(--paper);
    margin-bottom:1.5rem}
.search input:focus{outline:none;border-color:var(--amber)}
.grid{display:grid;gap:1rem}
.card{background:var(--paper);border:1.5px solid var(--border);border-radius:10px;overflow:hidden}
.card:hover{box-shadow:0 4px 18px rgba(200,118,10,.14);border-color:var(--amber)}
.card-head{display:flex;align-items:center;gap:.8rem;padding:.9rem 1.3rem;
    cursor:pointer;flex-wrap:wrap}
.ar{font-size:1rem;font-weight:700;color:var(--crude);flex:1}
.en{font-family:'Fira Code',monospace;font-size:.82rem;font-weight:600;color:var(--amber);
    background:var(--light);padding:.2rem .6rem;border-radius:5px;direction:ltr}
.badge{font-size:.68rem;padding:.18rem .55rem;border-radius:999px;font-weight:700}
.b-res{background:#dbeafe;color:#1e40af}.b-pvt{background:#fef9c3;color:#854d0e}
.b-pro{background:#dcfce7;color:#166534}.b-drl{background:#ffe4e6;color:#9f1239}
.b-eco{background:#e0f2fe;color:#0369a1}
.card-body{display:none;padding:0 1.3rem 1.2rem;border-top:1px solid var(--border)}
.card-body.open{display:block}
.def{margin-top:.9rem;font-size:.95rem;line-height:1.85}
.extra{margin-top:.35rem;font-size:.8rem;color:var(--muted)}
.ftitle{font-size:1.3rem;font-weight:900;color:var(--crude);margin-bottom:1.2rem;
    border-bottom:3px solid var(--amber);padding-bottom:.4rem}
.pcard{background:var(--dbg);border-radius:10px;overflow:hidden;margin-bottom:1.2rem;
    border:1px solid #2a3040}
.pcard-head{display:flex;justify-content:space-between;padding:.8rem 1.3rem;
    background:rgba(200,118,10,.11);border-bottom:1px solid #2a3040;flex-wrap:wrap;gap:.4rem}
.p-en{font-family:'Fira Code',monospace;color:#e8a020;font-size:.85rem}
.p-ar{color:rgba(255,255,255,.85);font-weight:600}
.pcard-body{padding:1.1rem 1.3rem;color:rgba(255,255,255,.75);font-size:.85rem}
.p-def{font-style:italic;color:#e8a020;margin-bottom:.5rem}
.axes{font-family:'Fira Code',monospace;font-size:.78rem;margin-bottom:.5rem;color:rgba(255,255,255,.6)}
.shape{margin-bottom:.6rem;font-weight:600;color:rgba(255,255,255,.9)}
.prow{margin:.3rem 0}
.pivot{margin:.5rem 0;color:#e8a020;font-weight:600}
.ml{margin-top:.6rem;font-size:.78rem;color:rgba(255,100,100,.8);font-weight:700}
.mi{font-size:.75rem;color:rgba(255,120,120,.7);margin:.2rem 0}
.sketch{font-family:'Fira Code',monospace;font-size:.68rem;color:#9be9a8;background:#000;
    padding:.8rem;border-radius:6px;overflow-x:auto;direction:ltr;text-align:left;
    line-height:1.3;margin-top:.8rem}
.nr{text-align:center;padding:3rem;color:var(--muted)}
"""

    js = r"""
function renderTerms(list){
  document.getElementById("tgrid").innerHTML=list.map(function(t,i){
    var ex=(t.extras||[]).map(function(e){return '<div class="extra">'+e+'</div>';}).join("");
    return '<div class="card"><div class="card-head" onclick="tog('+i+')">'
      +'<span class="ar">'+t.ar+'</span>'
      +'<span class="en">'+t.en+'</span>'
      +'<span class="badge '+t.cls+'">'+t.lbl+'</span>'
      +'</div><div class="card-body" id="b'+i+'">'
      +'<p class="def">'+t.def+'</p>'+ex+'</div></div>';
  }).join("");
}
function tog(i){document.getElementById("b"+i).classList.toggle("open");}
function filterTerms(){
  var q=document.getElementById("q").value.toLowerCase();
  var f=q?TERMS.filter(function(t){return t.search.indexOf(q)!==-1;}):TERMS;
  renderTerms(f);
  document.getElementById("nr").style.display=f.length?"none":"block";
}
function renderPlots(){
  document.getElementById("pgrid").innerHTML=PLOTS.map(function(p){
    var rows=(p.rows||[]).map(function(r){return '<div class="prow">'+r+'</div>';}).join("");
    var mis=(p.mistakes||[]).map(function(m){return '<div class="mi">- '+m+'</div>';}).join("");
    return '<div class="pcard"><div class="pcard-head">'
      +'<span class="p-ar">'+p.title_ar+'</span>'
      +'<span class="p-en">'+p.title_en+'</span>'
      +'</div><div class="pcard-body">'
      +'<div class="p-def">'+p.definition+'</div>'
      +'<div class="axes">X: '+p.x_axis+' | Y: '+p.y_axis+'</div>'
      +'<div class="shape">'+p.shape+'</div>'
      +rows
      +'<div class="pivot">Pivot: '+p.pivot+'</div>'
      +(mis?'<div class="ml">REJECT (common mistakes):</div>'+mis:'')
      +'<pre class="sketch">'+p.sketch+'</pre>'
      +'</div></div>';
  }).join("");
}
function show(id,btn){
  document.querySelectorAll(".sec").forEach(function(s){s.classList.remove("active");});
  document.querySelectorAll("nav button").forEach(function(b){b.classList.remove("active");});
  document.getElementById(id).classList.add("active");
  btn.classList.add("active");
}
renderTerms(TERMS); renderPlots();
"""

    html = (
        '<!DOCTYPE html><html lang="ar" dir="rtl">'
        '<head><meta charset="UTF-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1.0">'
        '<title>Petroleum Engineering Glossary</title>'
        '<style>' + css + '</style></head><body>'
        '<header><h1>Petroleum Engineering <span>Glossary</span></h1>'
        '<p>PVT | Reservoir | Drilling | Production | Economics</p></header>'
        '<nav>'
        '<button class="active" onclick="show(\'terms\',this)">Terms / المصطلحات</button>'
        '<button onclick="show(\'plots\',this)">PVT Relationships / علاقات PVT</button>'
        '</nav><main>'
        '<div id="terms" class="sec active">'
        '<div class="search"><input id="q" placeholder="Search terms (AR/EN)..." oninput="filterTerms()"/></div>'
        '<div class="grid" id="tgrid"></div>'
        '<div class="nr" id="nr" style="display:none">No results found</div>'
        '</div>'
        '<div id="plots" class="sec">'
        '<p class="ftitle">PVT Properties vs Pressure -- Correct Physical Behavior (BLOCK 5)</p>'
        '<div id="pgrid"></div>'
        '</div>'
        '</main>'
        '<script>const TERMS=' + term_json + ';const PLOTS=' + plot_json + ';' + js + '</script>'
        '</body></html>'
    ).encode("utf-8")

    _GLOSSARY_CACHE["html"] = html
    return html


# ─────────────────────────────────────────────
#  COMMAND DETECTORS
# ─────────────────────────────────────────────
def is_graph_cmd(t):       return t.lower().startswith(("/graph", "/interpret_graph"))
def is_analyze_cmd(t):     return t.lower().startswith("/analyze")
def is_calc_cmd(t):        return t.lower().startswith("/calc")
def is_estimate_cmd(t):    return t.lower().startswith("/estimate")
def is_convert_cmd(t):     return t.lower().startswith("/convert")
def is_classify_cmd(t):    return t.lower().startswith("/classify")
def is_plot_cmd(t):        return t.lower().startswith("/plot")
def is_check_cmd(t):       return t.lower().startswith("/check")
def is_pvto_cmd(t):        return t.lower().strip() == "/pvto"
def is_pvdo_cmd(t):        return t.lower().strip() == "/pvdo"
def is_pvtg_cmd(t):        return t.lower().strip() == "/pvtg"
def is_pvdg_cmd(t):        return t.lower().strip() == "/pvdg"
def is_export_sim_cmd(t):  return t.lower().startswith("/export_sim")
def is_eclipse_cmd(t):     return t.lower().startswith("/eclipse")
def is_cmg_cmd(t):         return t.lower().startswith("/cmg")
def is_reset_cmd(t):       return t.lower().strip() == "/reset"
def is_start_cmd(t):       return t.lower().strip() in ("/start", "/help")
def is_report_cmd(t):      return t.lower().startswith("/report")
def is_glossary_cmd(t):    return t.lower().strip() == "/glossary"


def is_surface_separator(t: str) -> bool:
    t = t.lower()
    oil = any(k in t for k in ["surface separator oil", "separator oil",
                                 "زيت من الفاصل", "عينة زيت من الفاصل"])
    gas = any(k in t for k in ["separator gas", "غاز من الفاصل", "عينة غاز من الفاصل"])
    return oil and gas


# ─────────────────────────────────────────────
#  STATIC RESPONSES
# ─────────────────────────────────────────────
def start_message() -> str:
    return (
        "Petroleum Engineering AI Bot v3\n\n"
        "Covers: PVT Lab | Reservoir Engineering | Simulation (Eclipse/CMG) "
        "| Drilling | Production | Economics\n\n"
        "=== DETERMINISTIC COMMANDS (100% accurate, no AI hallucination) ===\n\n"
        "/classify gor=<val> api=<val>\n"
        "  Classify fluid type (Black Oil / Volatile Oil / Gas Condensate ...)\n\n"
        "/calc <type> key=value ...\n"
        "  Exact formulas. Types: api, ooip, ogip, darcy, recovery_factor,\n"
        "  productivity_index, hydrostatic, mud_weight_required, ecd,\n"
        "  water_cut, wor, gor_produced, npv\n"
        "  Example: /calc ooip area=500 h=50 phi=0.2 sw=0.3 bo=1.3\n\n"
        "/estimate <type> key=value ...\n"
        "  Correlation estimates. Types: pb_standing, rs_standing\n"
        "  Example: /estimate pb_standing rs=650 gas_sg=0.75 tres=180 api=35\n\n"
        "/convert <value> <from> to <to>\n"
        "  Example: /convert 5000 psi to bar\n\n"
        "/plot <type> [p=p1,p2,.. v=v1,v2,..] [pb=<val>] [well=<name>]\n"
        "  Show ASCII reference + generate PNG chart if data provided.\n"
        "  Types: bo, rs, bg, z, viscosity, mu_g, dropout, cgr, density, vrel, cce\n"
        "  Example: /plot bo p=500,1000,1500,2000 v=1.15,1.18,1.20,1.17 pb=1500\n"
        "  Or upload a CSV file first, then: /plot bo pb=2500\n\n"
        "/check <rel> p=p1,p2,.. v=v1,v2,.. [pb=<val>]\n"
        "  Validate PVT data against BLOCK 5 physical rules.\n"
        "  Example: /check rs p=500,1000,1500,2000 v=300,300,250,180 pb=1500\n\n"
        "/pvto  /pvdo  /pvtg  /pvdg\n"
        "  Eclipse simulator table skeletons and data requirements.\n\n"
        "/export_sim <fluid_type> [near_critical]\n"
        "  Decide Black-Oil vs Compositional simulation.\n"
        "  Example: /export_sim gas condensate near_critical\n\n"
        "=== AI-ASSISTED COMMANDS ===\n\n"
        "/glossary  -- Full interactive HTML glossary (terms + PVT plots)\n"
        "/analyze   -- Analyze uploaded PDF/DOCX report\n"
        "/graph     -- Analyze uploaded engineering chart\n"
        "/report    -- Generate PVT report skeleton\n"
        "/eclipse   -- Eclipse simulation guidance\n"
        "/cmg       -- CMG simulation guidance (IMEX vs GEM)\n"
        "/reset     -- Clear all uploaded files for this chat\n\n"
        "Upload: PDF, DOCX, CSV (for /plot data), or images (PNG/JPG)\n"
        "Or just type your question in Arabic or English."
    )


def surface_separator_answer() -> str:
    return (
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


# ─────────────────────────────────────────────
#  MAIN POLLING LOOP
# ─────────────────────────────────────────────
log.info("Petroleum Engineering AI Bot v3 starting...")

while True:
    try:
        # FIX #8: correct offset — pass offset+1 to skip already-processed updates
        resp = requests.get(
            f"{TELEGRAM_URL}/getUpdates",
            params={"offset": offset + 1, "timeout": 30},
            timeout=40,
        )
        if not resp.ok:
            log.warning("getUpdates failed: %s", resp.status_code)
            time.sleep(5)
            continue

        updates = resp.json().get("result", [])

        for update in updates:
            # FIX #8: update offset to the highest seen update_id
            offset = max(offset, update["update_id"])

            msg = update.get("message")
            if not msg:
                continue

            chat_id = msg["chat"]["id"]
            log.info("Update from chat_id=%s", chat_id)

            # ── Document upload ──
            if "document" in msg:
                handle_document_upload(chat_id, msg["document"])
                continue

            # ── Photo upload ──
            if "photo" in msg:
                handle_photo_upload(chat_id, msg["photo"])
                continue

            if "text" not in msg:
                send_message(chat_id, "Please send text, PDF/DOCX/CSV, or an image.")
                continue

            text    = msg["text"].strip()
            context = FILE_CONTEXT.get(chat_id)

            log.info("Command: %s", text[:80])

            try:
                # ── /start or /help ──
                if is_start_cmd(text):
                    send_message(chat_id, start_message())
                    continue

                # ── /reset ──
                if is_reset_cmd(text):
                    FILE_CONTEXT.pop(chat_id, None)
                    IMAGE_CONTEXT.pop(chat_id, None)
                    send_message(chat_id, "Files and images cleared. Start fresh.")
                    continue

                # ── /glossary ──
                if is_glossary_cmd(text):
                    try:
                        send_document(
                            chat_id, generate_glossary_html(),
                            "petroleum_glossary.html",
                            (f"Full Petroleum Engineering Glossary\n"
                             f"{len(KNOWLEDGE_BASE)} terms | "
                             f"{len(PVT_PLOT_RULES)} PVT relationships\n"
                             "Open in any browser."),
                        )
                    except Exception as e:
                        log.error("/glossary error: %s", e)
                        send_message(chat_id, f"Error generating glossary: {e}")
                    continue

                # ── /classify ──
                if is_classify_cmd(text):
                    try:
                        kwargs = parse_kv_args(text[len("/classify"):])
                        if "gor" not in kwargs or "api" not in kwargs:
                            send_message(
                                chat_id,
                                "Usage: /classify gor=<value> api=<value>\n"
                                "Example: /classify gor=3500 api=45"
                            )
                        else:
                            send_message(chat_id, classify_fluid(kwargs["gor"], kwargs["api"]))
                    except Exception as e:
                        log.error("/classify error: %s", e)
                        send_message(chat_id, f"Error in /classify: {e}")
                    continue

                # ── /calc ──
                if is_calc_cmd(text):
                    try:
                        parts = text.split(maxsplit=2)
                        if len(parts) < 2:
                            types_list = ", ".join(EXACT_FORMULAS.keys())
                            send_message(chat_id,
                                         f"Usage: /calc <type> key=value ...\n"
                                         f"Types: {types_list}")
                            continue
                        calc_type = parts[1].lower()
                        kwargs    = parse_kv_args(parts[2] if len(parts) > 2 else "")
                        result    = run_exact_calc(calc_type, **kwargs)
                        send_message(chat_id,
                                     result or f"Unknown calculation type: '{calc_type}'.\n"
                                     f"Types: {', '.join(EXACT_FORMULAS.keys())}")
                    except Exception as e:
                        log.error("/calc error: %s", e)
                        send_message(chat_id, f"Error in /calc: {e}")
                    continue

                # ── /estimate ──
                if is_estimate_cmd(text):
                    try:
                        parts = text.split(maxsplit=2)
                        if len(parts) < 2:
                            types_list = ", ".join(CORRELATIONS.keys())
                            send_message(chat_id,
                                         f"Usage: /estimate <type> key=value ...\n"
                                         f"Types: {types_list}")
                            continue
                        calc_type = parts[1].lower()
                        kwargs    = parse_kv_args(parts[2] if len(parts) > 2 else "")
                        result    = run_correlation(calc_type, **kwargs)
                        send_message(chat_id,
                                     result or f"Unknown correlation: '{calc_type}'.\n"
                                     f"Types: {', '.join(CORRELATIONS.keys())}")
                    except Exception as e:
                        log.error("/estimate error: %s", e)
                        send_message(chat_id, f"Error in /estimate: {e}")
                    continue

                # ── /convert ──
                if is_convert_cmd(text):
                    try:
                        m = re.match(
                            r"/convert\s+([-+]?\d*\.?\d+)\s+(\S+)\s+to\s+(\S+)",
                            text, re.IGNORECASE,
                        )
                        if not m:
                            send_message(
                                chat_id,
                                "Usage: /convert <value> <from_unit> to <to_unit>\n"
                                "Example: /convert 5000 psi to bar"
                            )
                            continue
                        value, from_u, to_u = float(m.group(1)), m.group(2), m.group(3)
                        send_message(chat_id, run_unit_conversion(value, from_u, to_u))
                    except Exception as e:
                        log.error("/convert error: %s", e)
                        send_message(chat_id, f"Error in /convert: {e}")
                    continue

                # ── /check  (FIX #1 & #2: correct indentation + empty body guard) ──
                if is_check_cmd(text):
                    try:
                        body = text[len("/check"):].strip()  # FIX #1: NOW inside the if block

                        # FIX #2: guard empty body before split
                        if not body:
                            send_message(
                                chat_id,
                                "Usage: /check <relationship> p=p1,p2,.. v=v1,v2,.. [pb=<val>]\n\n"
                                "Example:\n"
                                "/check rs p=500,1000,1500,2000 v=300,300,250,180 pb=1500\n\n"
                                "Available: bo, rs, bg, z, viscosity, dropout, cgr, density, vrel"
                            )
                            continue

                        words    = body.split()
                        rel_word = words[0].lower() if words else None
                        rel_key  = PLOT_ALIASES.get(rel_word) if rel_word else None

                        p_match  = re.search(r"p=\[?([\d,.\s]+)\]?", body)
                        v_match  = re.search(r"v=\[?([\d,.\s]+)\]?", body)
                        pb_match = re.search(r"pb=([\d.]+)", body)

                        if not rel_key or not p_match or not v_match:
                            send_message(
                                chat_id,
                                "Usage: /check <relationship> p=p1,p2,.. v=v1,v2,.. [pb=<val>]\n\n"
                                "Example:\n"
                                "/check rs p=500,1000,1500,2000 v=300,300,250,180 pb=1500\n\n"
                                f"Relationship '{rel_word}' not recognized. "
                                f"Available: {', '.join(sorted(set(PLOT_ALIASES.keys()))[:12])}..."
                            )
                            continue

                        pressures = [float(x.strip()) for x in p_match.group(1).split(",")
                                     if x.strip()]
                        values    = [float(x.strip()) for x in v_match.group(1).split(",")
                                     if x.strip()]
                        pb_or_pd  = float(pb_match.group(1)) if pb_match else None

                        send_message(chat_id, check_pvt_trend(rel_key, pressures, values, pb_or_pd))

                    except Exception as e:
                        log.error("/check error: %s", e)
                        send_message(chat_id, f"Error in /check: {e}")
                    continue

                # ── /plot  (FIX #5: full matplotlib PNG + ASCII) ──
                if is_plot_cmd(text):
                    try:
                        body = text[len("/plot"):].strip()

                        if not body:
                            send_message(
                                chat_id,
                                "Usage: /plot <type> [p=p1,p2,.. v=v1,v2,..] [pb=<val>] [well=<name>]\n\n"
                                "Types: bo, rs, bg, z, viscosity, mu_g, dropout, cgr, density, vrel\n\n"
                                "Example with data (generates PNG chart):\n"
                                "/plot bo p=500,1000,1500,2000,2500 v=1.12,1.15,1.18,1.20,1.17 pb=2000\n\n"
                                "Example ASCII only:\n"
                                "/plot bo"
                            )
                            continue

                        words    = body.split()
                        rel_word = words[0].lower() if words else ""
                        rel_key  = PLOT_ALIASES.get(rel_word)

                        if not rel_key:
                            # Try two-word alias (e.g. "oil viscosity")
                            two_word = " ".join(words[:2]).lower() if len(words) >= 2 else ""
                            rel_key  = PLOT_ALIASES.get(two_word)

                        if not rel_key:
                            avail = ", ".join(sorted(set(PLOT_ALIASES.keys())))
                            send_message(
                                chat_id,
                                f"Unknown plot type '{rel_word}'.\nAvailable: {avail}"
                            )
                            continue

                        # Always send ASCII reference first
                        ascii_response = format_plot_response(rel_key)
                        if ascii_response:
                            send_message(chat_id, ascii_response)

                        # Check for data — from text or from uploaded CSV
                        pressures, values, pb_or_pd, well_name = [], [], None, ""

                        csv_context = FILE_CONTEXT.get(chat_id, "")
                        if csv_context.startswith("__CSV__"):
                            # Parse from CSV
                            csv_text = csv_context[len("__CSV__\n"):]
                            pressures, values = parse_csv_for_plot(csv_text)
                            # Pb/Pd and well name from text command
                            pbm = re.search(r"pb[=\s]+([\d.]+)", body, re.IGNORECASE)
                            if pbm:
                                pb_or_pd = float(pbm.group(1))
                            wm = re.search(r"well[=\s]+([A-Za-z0-9_\-]+)", body, re.IGNORECASE)
                            if wm:
                                well_name = wm.group(1)
                        else:
                            pressures, values, pb_or_pd, well_name = parse_plot_data_from_text(body)

                        if len(pressures) >= 2 and len(pressures) == len(values):
                            send_message(chat_id,
                                         f"Generating PNG chart for {PVT_PLOT_RULES[rel_key]['title_en']} "
                                         f"({len(pressures)} data points)...")
                            try:
                                png_bytes = generate_pvt_plot_png(
                                    rel_key, pressures, values,
                                    pb_or_pd=pb_or_pd,
                                    well_name=well_name,
                                )
                                if png_bytes:
                                    rule     = PVT_PLOT_RULES[rel_key]
                                    cap_well = f"| Well: {well_name}" if well_name else ""
                                    caption  = (
                                        f"{rule['title_en']} {cap_well}\n"
                                        f"Points: {len(pressures)} | "
                                        f"P range: {min(pressures):,.0f}-{max(pressures):,.0f} psia"
                                    )
                                    if pb_or_pd:
                                        caption += f" | Pb/Pd: {pb_or_pd:,.0f} psia"
                                    ok = send_photo_bytes(chat_id, png_bytes, caption)
                                    if not ok:
                                        send_message(chat_id, "Failed to send chart image.")
                                else:
                                    send_message(chat_id, "Chart generation failed.")
                            except Exception as plot_err:
                                log.error("Plot PNG error: %s", plot_err)
                                send_message(chat_id, f"Chart error: {plot_err}")
                        elif pressures or values:
                            send_message(
                                chat_id,
                                f"Data parsing issue: found {len(pressures)} pressure values "
                                f"and {len(values)} y-values. They must be equal.\n\n"
                                "Format: p=100,200,300 v=1.1,1.2,1.3"
                            )
                        else:
                            send_message(
                                chat_id,
                                "ASCII reference sent above.\n\n"
                                "To generate a PNG chart, add your data:\n"
                                f"/plot {rel_word} p=p1,p2,p3,.. v=v1,v2,v3,.. [pb=<value>]\n\n"
                                "Or upload a CSV file first, then /plot <type> [pb=<val>]"
                            )

                    except Exception as e:
                        log.error("/plot error: %s", e)
                        send_message(chat_id, f"Error in /plot: {e}")
                    continue

                # ── /pvto ──
                if is_pvto_cmd(text):
                    try:
                        send_message(chat_id, generate_pvto_skeleton())
                        if context and not context.startswith("__CSV__"):
                            followup = ask_ai(
                                "Using the uploaded document, check if Rs(P), Bo(P), and "
                                "mu_o(P) from Differential Liberation are present. "
                                "Summarize if found. List missing data. State whether "
                                "Separator Test correction is required.",
                                context,
                            )
                            send_message(chat_id, followup)
                    except Exception as e:
                        log.error("/pvto error: %s", e)
                        send_message(chat_id, f"Error in /pvto: {e}")
                    continue

                # ── /pvdo ──
                if is_pvdo_cmd(text):
                    try:
                        send_message(chat_id, generate_pvdo_skeleton())
                        if context and not context.startswith("__CSV__"):
                            followup = ask_ai(
                                "Check uploaded document for Bo(P) and mu_o(P) for PVDO. "
                                "Confirm Rs is negligible. List missing data.",
                                context,
                            )
                            send_message(chat_id, followup)
                    except Exception as e:
                        log.error("/pvdo error: %s", e)
                        send_message(chat_id, f"Error in /pvdo: {e}")
                    continue

                # ── /pvtg ──
                if is_pvtg_cmd(text):
                    try:
                        send_message(chat_id, generate_pvtg_skeleton())
                        if context and not context.startswith("__CSV__"):
                            followup = ask_ai(
                                "Check uploaded document for Bg(P), mu_g(P), Rv(P) for PVTG. "
                                "State if PVDG (dry gas) would be more appropriate.",
                                context,
                            )
                            send_message(chat_id, followup)
                    except Exception as e:
                        log.error("/pvtg error: %s", e)
                        send_message(chat_id, f"Error in /pvtg: {e}")
                    continue

                # ── /pvdg ──
                if is_pvdg_cmd(text):
                    try:
                        send_message(chat_id, generate_pvdg_skeleton())
                        if context and not context.startswith("__CSV__"):
                            followup = ask_ai(
                                "Check uploaded document for Bg(P) and mu_g(P) for PVDG. "
                                "Confirm Rv is negligible. List missing data.",
                                context,
                            )
                            send_message(chat_id, followup)
                    except Exception as e:
                        log.error("/pvdg error: %s", e)
                        send_message(chat_id, f"Error in /pvdg: {e}")
                    continue

                # ── /export_sim ──
                if is_export_sim_cmd(text):
                    try:
                        body = text[len("/export_sim"):].strip().lower()
                        if not body:
                            send_message(
                                chat_id,
                                "Usage: /export_sim <fluid_type> [near_critical]\n\n"
                                "Fluid types: black oil, volatile oil, gas condensate, "
                                "wet gas, dry gas\n\n"
                                "Example: /export_sim gas condensate near_critical"
                            )
                            continue
                        near_critical = "near_critical" in body or "near critical" in body
                        fluid_str     = body.replace("near_critical", "").replace("near critical", "").strip()
                        send_message(chat_id, export_sim_decision(fluid_str, near_critical))
                    except Exception as e:
                        log.error("/export_sim error: %s", e)
                        send_message(chat_id, f"Error in /export_sim: {e}")
                    continue

                # ── /report ──
                if is_report_cmd(text):
                    try:
                        query    = text[len("/report"):].strip()
                        template = load_pvt_template()
                        prompt   = (
                            (query if query else "Generate full PVT Laboratory Report") + "\n\n"
                            "Use the following professional PVT report template exactly.\n"
                            "If measured data is missing, do NOT stop.\n"
                            "Write the full report skeleton with 'Not provided' for missing fields.\n"
                            "If a PDF/DOCX was uploaded, use the document context to fill the report.\n\n"
                            "REPORT TEMPLATE:\n" + template
                        )
                        send_message(chat_id, ask_ai(prompt, context))
                    except Exception as e:
                        log.error("/report error: %s", e)
                        send_message(chat_id, f"Error in /report: {e}")
                    continue

                # ── /analyze ──
                if is_analyze_cmd(text):
                    try:
                        if not context or context.startswith("__CSV__"):
                            send_message(chat_id, "No PDF/DOCX loaded. Upload a file first.")
                            continue
                        prompt = (
                            "Analyze this engineering report professionally:\n\n"
                            "1. Sample type and fluid classification (BLOCK 6 -- need GOR/API)\n"
                            "2. Tests performed and quality\n"
                            "3. Key values: Pb/Pd, Bo, Rs, API, Viscosity, Bg, Z\n"
                            "4. Check BLOCK 5 consistency:\n"
                            "   - Flag Bo increasing below Pb as non-physical (POSSIBLE DATA QUALITY ISSUE)\n"
                            "   - Flag Rs varying above Pb as error\n"
                            "5. Simulation recommendations (PVTO/PVDO/PVTG/PVDG/Compositional)\n"
                            "6. Missing data (DATA REQUIRED)\n"
                            "7. One-line engineering conclusion"
                        )
                        send_message(chat_id, ask_ai(prompt, context))
                    except Exception as e:
                        log.error("/analyze error: %s", e)
                        send_message(chat_id, f"Error in /analyze: {e}")
                    continue

                # ── /graph or /interpret_graph ──
                if is_graph_cmd(text):
                    try:
                        img = IMAGE_CONTEXT.get(chat_id)
                        if not img:
                            send_message(chat_id, "Send an image first, then type /graph.")
                            continue
                        prompt = build_graph_prompt(text)
                        send_message(chat_id, ask_vision_ai(prompt, img, context))
                    except Exception as e:
                        log.error("/graph error: %s", e)
                        send_message(chat_id, f"Error in /graph: {e}")
                    continue

                # ── /eclipse ──
                if is_eclipse_cmd(text):
                    try:
                        query  = text[len("/eclipse"):].strip()
                        prompt = (
                            (query if query else "General Eclipse guidance") + "\n\n"
                            "Provide structured Eclipse guidance:\n"
                            "- Appropriate PVT table (PVTO/PVDO/PVTG/PVDG) and reason\n"
                            "- Relevant Eclipse keywords\n"
                            "- Unit consistency checks\n"
                            "- Black-Oil (E100) vs Compositional (E300) decision\n"
                            "- DATA REQUIRED if anything missing"
                        )
                        send_message(chat_id, ask_ai(prompt, context))
                    except Exception as e:
                        log.error("/eclipse error: %s", e)
                        send_message(chat_id, f"Error in /eclipse: {e}")
                    continue

                # ── /cmg ──
                if is_cmg_cmd(text):
                    try:
                        query  = text[len("/cmg"):].strip()
                        prompt = (
                            (query if query else "General CMG guidance") + "\n\n"
                            "Provide structured CMG guidance:\n"
                            "- IMEX (Black-Oil) vs GEM (Compositional/EOS) selection\n"
                            "- PVT data requirements for each\n"
                            "- EOS Tuning requirements if GEM\n"
                            "- DATA REQUIRED if anything missing"
                        )
                        send_message(chat_id, ask_ai(prompt, context))
                    except Exception as e:
                        log.error("/cmg error: %s", e)
                        send_message(chat_id, f"Error in /cmg: {e}")
                    continue

                # ── Surface separator keyword shortcut ──
                if is_surface_separator(text):
                    send_message(chat_id, surface_separator_answer())
                    continue

                # ── Default: AI free-text response ──
                send_message(chat_id, ask_ai(text, context))

            except Exception as cmd_err:
                log.error("Command handler error for chat_id=%s text='%s': %s",
                          chat_id, text[:80], cmd_err)
                send_message(chat_id, f"An error occurred processing your request: {cmd_err}")

    except requests.exceptions.Timeout:
        log.warning("getUpdates timeout -- retrying")
    except requests.exceptions.ConnectionError as ce:
        log.error("Connection error in main loop: %s", ce)
        time.sleep(10)
    except Exception as loop_err:
        log.error("Main loop error: %s", loop_err)
        time.sleep(5)

    time.sleep(1)
