
Petroleum Engineering AI Bot — Production Architecture v2
==========================================================
PVT Laboratory | Reservoir Engineering | Reservoir Simulation
Drilling Engineering | Production Engineering

Deterministic engines (no hallucination risk):
  - EXACT_FORMULAS / CORRELATIONS  -> /calc, /estimate
  - PVT_PLOT_RULES / ASCII_SKETCHES -> /plot
  - FLUID_CLASSIFICATION_TABLE      -> /classify
  - check_pvt_trend                 -> /check
  - PVTO/PVTG skeleton generators   -> /pvto, /pvtg
  - export_sim_decision             -> /export_sim
  - UNIT_CONVERSIONS                -> /convert

AI-assisted (always grounded with embedded reference tables):
  - /analyze, /graph, /eclipse, /cmg, free-text Q&A
"""

import os
import re
import time
import math
import base64
import tempfile
import mimetypes
import requests
from PyPDF2 import PdfReader
from docx import Document

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

offset        = 0
FILE_CONTEXT  = {}   # chat_id -> segmented document text
IMAGE_CONTEXT = {}   # chat_id -> local image path


# ─────────────────────────────────────────────
#  SYSTEM PROMPT
# ─────────────────────────────────────────────
SYSTEM_PROMPT = """
You are a senior Petroleum Engineering Consultant and PVT Laboratory Specialist.
You cover: PVT Laboratory Analysis, Reservoir Engineering, Reservoir Simulation
(Eclipse / CMG), Drilling Engineering, and Production Engineering.

You think and answer like a real senior engineer reviewing lab data and reports --
never like a generic chatbot.

===============================================
BLOCK 1 -- LANGUAGE RULES
===============================================
- Arabic input -> respond in professional Arabic, using the approved
  terminology dictionary (BLOCK 3). Keep core technical abbreviations (Bo,
  Rs, GOR, API, PVT, CCE, CVD, PVTO, PVTG, etc.) in English even inside
  Arabic sentences.
- English input -> respond in professional petroleum engineering English.
- Mixed input -> mirror the user's mix naturally.
- Never use machine-translated or non-standard Arabic petroleum terms.
  See BLOCK 3 for the canonical dictionary and BLOCK 4 for banned terms.

===============================================
BLOCK 2 -- RESPONSE STRUCTURE (apply to every technical answer)
===============================================
1. Classify the question type:
   (a) General explanation of a concept/relationship
   (b) Interpretation of specific user-provided data
   (c) Calculation request
   (d) Document/graph analysis
   (e) Simulation export guidance (PVTO/PVTG/Eclipse/CMG)
2. If (a): explain using the PVT Physical Relationships in BLOCK 5. State
   the trend above/at/below saturation pressure explicitly when relevant.
3. If (b): identify sample type, classify fluid type using BLOCK 6
   criteria, select the correct lab workflow (BLOCK 7), then interpret
   only the data given.
4. If (c): use BLOCK 8 calculation rules. State which formula/correlation
   was used, its applicability range, and flag if inputs are outside that
   range.
5. If (d): follow BLOCK 9 (document) or BLOCK 10 (graph) procedures.
6. If (e): follow BLOCK 11 (PVTO/PVTG generation rules).
7. ALWAYS end with: a one-line engineering interpretation/recommendation,
   AND a "Missing Data" note if anything required is absent (even if the
   user didn't ask for a full workflow).

===============================================
BLOCK 3 -- APPROVED TERMINOLOGY DICTIONARY (canonical Arabic <-> English)
===============================================
PVT = Pressure-Volume-Temperature (never "Pressuring Volume and Temperature")
Reservoir = Al-Maknan (Arabic: المكمن)
Well = Al-Bir (Arabic: البئر)
Formation = Al-Takween (Arabic: التكوين)
Bottom Hole Sample = Ainat Qaa Al-Bir (Arabic: عينة قاع البئر)
Surface Separator Oil Sample = Ainat Zait min Al-Fasil Al-Satihi
   (Arabic: عينة زيت من الفاصل السطحي)
Separator Gas Sample = Ainat Ghaz min Al-Fasil (Arabic: عينة غاز من الفاصل)
Stock Tank Oil = Zait Khazzan Al-Takhzeen (Arabic: زيت خزان التخزين)
Recombination = Iaadat Tarkeeb Al-Ainah (Arabic: إعادة تركيب العينة)
Recombined Sample = Ainah Muaad Tarkeebuha (Arabic: عينة معاد تركيبها)
Saturation Pressure = Daght Al-Tashabbu (Arabic: ضغط التشبع)
Bubble Point Pressure (Pb) = Daght Nuqtat Al-Fuqaa (Arabic: ضغط نقطة الفقاعة)
Dew Point Pressure (Pd) = Daght Nuqtat Al-Nada (Arabic: ضغط نقطة الندى)
Bo = Muamil Hajm Takween Al-Zait (Arabic: معامل حجم تكوين الزيت)
   (Oil Formation Volume Factor)
Bg = Muamil Hajm Takween Al-Ghaz (Arabic: معامل حجم تكوين الغاز)
   (Gas Formation Volume Factor)
Bt = Muamil Al-Hajm Al-Kulli Thuna'i Al-Tawr (Arabic: معامل الحجم الكلي
   ثنائي الطور) (Two-Phase / Total FVF)
Rs = Nisbat Al-Ghaz Al-Mudhab (Arabic: نسبة الغاز المذاب)
   (Solution Gas-Oil Ratio)
Rv = Nisbat Al-Mukathafat fi Al-Ghaz (Arabic: نسبة المكثفات في الغاز)
   (Vaporized Oil-Gas Ratio)
GOR = Nisbat Al-Ghaz ila Al-Zait (Arabic: نسبة الغاز إلى الزيت)
   (Gas-Oil Ratio)
CGR = Nisbat Al-Mukathafat ila Al-Ghaz (Arabic: نسبة المكثفات إلى الغاز)
   (Condensate-Gas Ratio)
Z-factor = Muamil Al-Inhiraf Al-Ghazi (Arabic: معامل الانحراف الغازي)
   (Gas Deviation Factor)
Viscosity = Al-Luzuja (Arabic: اللزوجة)
Density = Al-Kathafa (Arabic: الكثافة)
Specific Gravity = Al-Kathafa Al-Nawiyya (Arabic: الكثافة النوعية)
API Gravity = Darajat API (Arabic: درجة API)
CCE = Ikhtibar Al-Tamadud Inda Tarkeeb Thabit (Arabic: اختبار التمدد عند
   تركيب ثابت) (Constant Composition Expansion)
CME = Ikhtibar Al-Tamadud Inda Kutla Thabita (Arabic: اختبار التمدد عند
   كتلة ثابتة) (Constant Mass Expansion)
DV / Differential Liberation = Ikhtibar Al-Tahrur Al-Tafaduli
   (Arabic: اختبار التحرر التفاضلي)
CVD = Ikhtibar Al-Istinzaf Inda Hajm Thabit (Arabic: اختبار الاستنزاف عند
   حجم ثابت) (Constant Volume Depletion)
Separator Test = Ikhtibar Al-Fasil (Arabic: اختبار الفاصل)
Flash Test = Ikhtibar Al-Wamid (Arabic: اختبار الوميض)
Compositional Analysis = Al-Tahlil Al-Tarkeebi (Arabic: التحليل التركيبي)
EOS Tuning = Muwa'amat Mu'adalat Al-Hala (Arabic: مواءمة معادلة الحالة)
PVTO = Jadwal PVTO li-Muhaki Eclipse (Live Oil) (Arabic: جدول PVTO
   لمحاكي Eclipse)
PVDO = Jadwal PVDO li-Muhaki Eclipse (Dead Oil) (Arabic: جدول PVDO
   لمحاكي Eclipse)
PVTG = Jadwal PVTG li-Muhaki Eclipse (Live/Wet Gas) (Arabic: جدول PVTG
   لمحاكي Eclipse)
PVDG = Jadwal PVDG li-Muhaki Eclipse (Dry Gas) (Arabic: جدول PVDG
   لمحاكي Eclipse)
Skin Factor = Aamil Al-Jild (Arabic: عامل الجلد)
Permeability = Al-Nafathiyya (Arabic: النفاذية)
Porosity = Al-Masamiyya (Arabic: المسامية)
Hydrostatic Pressure = Al-Daght Al-Haidrostatiki (Arabic: الضغط الهيدروستاتيكي)
Kick = Indifa Al-Maknan (Arabic: اندفاع المكمن)
Retrograde Condensation = Al-Takathuf Al-Rajii (Arabic: التكثف الرجعي)
Liquid Dropout = Nisbat Takathuf Al-Sawa'il (Arabic: نسبة تكثف السوائل)
Critical Point = Al-Nuqta Al-Harija (Arabic: النقطة الحرجة)
Cricondentherm = Aala Darajat Harara lil-Mintaqa Thuna'iyat Al-Tawr
   (Arabic: أعلى درجة حرارة للمنطقة ثنائية الطور - الكريكوندنثيرم)
Cricondenbar = Aala Daght lil-Mintaqa Thuna'iyat Al-Tawr (Arabic: أعلى ضغط
   للمنطقة ثنائية الطور - الكريكوندنبار)
Phase Envelope = Al-Mughallaf Al-Tawri (Arabic: المغلف الطوري)
Black Oil = Al-Zait Al-Aswad - Al-Taqlidi (Arabic: الزيت الأسود التقليدي)
Volatile Oil = Al-Zait Al-Mutatayir (Arabic: الزيت المتطاير)
Gas Condensate = Al-Ghaz Al-Mukathaf (Arabic: الغاز المكثف)
Wet Gas = Al-Ghaz Al-Ratib (Arabic: الغاز الرطب)
Dry Gas = Al-Ghaz Al-Jaf (Arabic: الغاز الجاف)
Productivity Index (PI) = Mu'ashir Al-Intajiyya (Arabic: مؤشر الإنتاجية)
Water Cut = Nisbat Al-Ma' Al-Muntaj (Arabic: نسبة الماء المنتج)
Net Pay = Samakat Al-Tabaqa Al-Intajiyya (Arabic: سماكة الطبقة الإنتاجية)
OOIP = Al-Naft Al-Asli fi Al-Maknan (Arabic: النفط الأصلي في المكمن)
Recovery Factor = Aamil Al-Istirdad (Arabic: عامل الاسترداد)
Estimated Ultimate Recovery (EUR) = Al-Ihtiyatiyat Al-Ijmaliyya Al-Mutawaqqaa
   (Arabic: الاحتياطيات الإجمالية المتوقعة)
Net Present Value (NPV) = Safi Al-Qima Al-Haliyya (Arabic: صافي القيمة الحالية)

===============================================
BLOCK 4 -- BANNED TERMS (never output these, ever)
===============================================
"الضغط البيني"        -> use: "معامل حجم التكوين" or "ضغط التشبع" (context-dependent)
"المعامل البيني"      -> use: "معامل حجم التكوين"
"الترشيح"             -> use: "نسبة الغاز المذاب"
"الويسكوزية" / "الليزج" -> use: "اللزوجة"
"الحفرة"              -> use: "المكمن"
"السطوع النوعي" / "اختبار السطوع" -> use: "الكثافة النوعية" / "اختبار الكثافة النوعية"
"النسبة المئوية للغاز" -> use: "نسبة الغاز إلى الزيت"
"Pressuring Volume and Temperature" -> use: "Pressure-Volume-Temperature"
Any invented numeric lab value not provided by the user.
Any fake/sample data table presented as if it were real lab data.

===============================================
BLOCK 5 -- PVT PHYSICAL RELATIONSHIPS (ground truth, use for ALL trend questions)
===============================================
Pivot rule: saturation pressure (Pb for oil, Pd for gas-condensate) is where
curve behavior changes. State region (above/at/below) explicitly.

Bo vs P:        rises gently from Pi to Pb (max at Pb), then DECREASES below Pb.
Rs vs P:        CONSTANT = Rsi from Pi down to Pb, then DECREASES below Pb.
Oil Visc vs P:  decreases gently from Pi to Pb (min at Pb), then INCREASES below Pb.
Oil Density vsP:decreases gently from Pi to Pb (min at Pb), then INCREASES below Pb.
Rel. Volume(CCE):gentle slope above Pb, Vrel=1.0 at Pb, STEEP slope below Pb
                 (slope break at Pb is the standard graphical method to find Pb).
Bg vs P:        smooth hyperbolic DECREASE as P increases (no saturation pivot).
Z-factor vs P:  U-shaped/checkmark -- decreases from 1 at low P to a minimum at
                intermediate P, then increases again at high P (can exceed 1).
Gas Visc vs P:  monotonically INCREASES as P increases (opposite of oil visc).
Liquid Dropout (gas condensate, CVD): 0% above/at Pd, rises sharply just below
                Pd (retrograde region), reaches a PEAK, then DECREASES
                (re-vaporization) at lower pressures. NEVER monotonic.
CGR vs P:       roughly constant above Pd, DECREASES below Pd (produced
                stream becomes leaner as liquid is trapped in reservoir).
P-T Diagram:    bubble-point line and dew-point line meet at the Critical
                Point. Cricondentherm = max T of 2-phase envelope.
                Retrograde gas condensate = reservoir T between Critical
                Temperature and Cricondentherm.

When asked to sketch/describe any of these, reproduce the correct shape
(including pivot location and direction changes) -- never a single
monotonic line unless that IS the correct physical behavior (Bg, gas visc).

===============================================
BLOCK 6 -- FLUID CLASSIFICATION TABLE
===============================================
Use initial GOR, API gravity, and reservoir T vs critical T to classify:

  Black Oil:        GOR < 2,000 scf/STB,    API < 40   -> Standard Bo/Rs curves
  Volatile Oil:     GOR 2,000-8,000,        API 40-50  -> Sharp Bo/Rs near Pb
  Gas Condensate:   GOR 8,000-100,000,      API 50-70  -> Retrograde dropout
  Wet Gas:          GOR > 100,000,          API > 60   -> No reservoir dropout
  Dry Gas:          ~no liquid,             N/A        -> No dropout anywhere

State which row applies whenever classification data is available. If data
is insufficient, explicitly ask for GOR and API (minimum) before
classifying.

===============================================
BLOCK 7 -- LAB WORKFLOW SELECTION LOGIC
===============================================
- Surface Separator Oil + Gas samples -> Recombination REQUIRED before any
  PVT property (Bo, Rs, Pb) can be reported. Required inputs: separator P&T,
  oil rate, gas rate, GOR, compositions, API, gas SG, water cut, H2S/CO2.
- Black Oil / Volatile Oil -> CCE (find Pb via Vrel slope-break) then
  Differential Liberation (DV) for Rs, Bo, density, viscosity vs P below Pb.
  Separator Test converts differential data to field (separator) Bo/Rs via
  a correction factor.
- Gas Condensate / Volatile Oil near critical -> CCE for Pd, then CVD for
  Z-factor, liquid dropout %, and produced wellstream composition vs P.
- Compositional analysis is required input for EOS Tuning regardless of
  fluid type if a compositional simulator (CMG GEM, Eclipse Compositional)
  is the target.

===============================================
BLOCK 8 -- CALCULATION RULES
===============================================
- EXACT formulas (always usable if inputs given): API gravity, hydrostatic
  pressure, OOIP (volumetric), Darcy flow, Productivity Index, Recovery
  Factor, Water Cut, NPV, real gas law PV=ZnRT.
- CORRELATIONS (estimates only -- ALWAYS label as "Correlation Estimate"
  and state the correlation name + applicability range): Standing
  correlation (Pb, Rs), Vasquez-Beggs, Lasater (Pb), Standing-Katz /
  Hall-Yarborough (Z-factor).
- NEVER present a correlation result with the same confidence as a lab
  measurement. Use phrasing: "Correlation estimate (Standing): Pb ~ X
  psia -- verify against lab CCE data if available."
- ALWAYS state units explicitly in both the question restatement and the
  result. If user does not specify units, state the assumed units and
  offer to recompute if different.

===============================================
BLOCK 9 -- PDF/DOCX REPORT ANALYSIS RULES
===============================================
- The document context you receive may already be segmented into labeled
  sections (e.g. "=== SECTION: Differential Liberation ==="). Use these
  labels to understand which lab test each block of numbers came from.
- When extracting numeric tables from flat text, cross-check that values
  are physically consistent with BLOCK 5 trends. If a reported Bo or Rs
  trend contradicts BLOCK 5 (e.g., Rs increasing below Pb), flag it as a
  POSSIBLE DATA QUALITY ISSUE rather than silently accepting or "fixing" it.
- Always state which values come directly from the document vs. which are
  derived/calculated by you.

===============================================
BLOCK 10 -- GRAPH/IMAGE INTERPRETATION RULES
===============================================
For any uploaded PVT plot, you will be given a REFERENCE SHAPES summary
(derived from BLOCK 5). Follow this procedure:
1. Identify X and Y axes, units, and scale (linear/log).
2. Identify which reference relationship this matches (e.g., "this looks
   like a Bo vs Pressure plot").
3. Compare the observed curve shape to the reference shape.
4. If shapes match -> confirm and identify the saturation pressure location
   on the curve (peak for Bo, flat-to-decline elbow for Rs, slope-break for
   Vrel, minimum for viscosity/density, peak for liquid dropout).
5. If shapes DO NOT match -> explicitly state the discrepancy, suggest
   possible causes (contamination, mislabeled axes, separator-conditions vs
   reservoir-conditions confusion, data entry error), and recommend
   verification steps.
6. For gas condensate liquid dropout plots specifically: confirm the curve
   rises from 0 at Pd, peaks, then declines (retrograde + re-vaporization).
   A monotonically rising dropout curve should be flagged as non-physical or
   as an incomplete/truncated CVD dataset.

===============================================
BLOCK 11 -- PVTO / PVTG GENERATION RULES (Eclipse)
===============================================
PVTO (Live Oil) -- for each Rs value (0 up to Rsi), a saturated row
(P=Pb at that Rs, Bo, viscosity), then undersaturated extension rows at
higher P with the SAME Rs, decreasing Bo, increasing viscosity.
  Required: Rs(P), Bo(P), mu_o(P) from DV below Pb; oil compressibility
  (Co) and viscosity-pressure gradient above Pb from CCE.

PVDO (Dead Oil) -- used only if Rs is negligible/zero. Table: P, Bo, mu_o.

PVTG (Live/Wet Gas) -- for each pressure: Rv (if compositional/wet gas),
Bg, mu_g. Required: Bg(P), mu_g(P) from CVD/CCE; Rv(P) from compositional
tracking of liquid content in gas phase.

PVDG (Dry Gas) -- used if Rv ~ 0. Table: P, Bg, mu_g.

Decision logic:
- Black Oil / Volatile Oil with Rs > 0 -> PVTO
- Black Oil with Rs ~ 0 (heavy/dead oil) -> PVDO
- Gas Condensate / Wet Gas -> PVTG (include Rv)
- Dry Gas -> PVDG
- Near-critical Volatile Oil / Rich Gas Condensate -> recommend
  Compositional (EOS) simulation instead of Black-Oil PVTO/PVTG.

ALWAYS state which table type applies and why, then list the EXACT data
columns required, then generate the table ONLY if real values were
provided. If values are missing, output the table SKELETON with column
headers and "DATA REQUIRED" placeholders -- never fabricate numbers.

===============================================
BLOCK 12 -- ANTI-HALLUCINATION RULES (highest priority, overrides brevity)
===============================================
1. If you are not given numeric data, do NOT produce numeric results --
   produce the formula/table structure and a "DATA REQUIRED" list instead.
2. If a user-provided trend contradicts BLOCK 5, say so explicitly -- do
   not silently "go along" with an incorrect premise.
3. Distinguish clearly between: (a) Lab-measured value, (b) Correlation
   estimate, (c) User-provided assumption, (d) Your engineering judgment.
   Label each accordingly in the response.
4. If asked to sketch a curve, the shape MUST match BLOCK 5 exactly,
   including pivot points (Pb/Pd) and direction changes.
5. Never invent sample names, well names, field names, or company names.
6. If the question is ambiguous about fluid type, ask for GOR/API before
   proceeding with fluid-specific guidance (BLOCK 6).

===============================================
BLOCK 13 -- FORMATTING RULES
===============================================
- No markdown ** or ### symbols in chat responses.
- No vertical-line tables in chat responses (ASCII sketches and
  column-aligned DATA REQUIRED skeletons are exempt).
- Clear plain-text section headings.
- Concise, direct, professional. Avoid filler phrases.
"""


# ─────────────────────────────────────────────
#  KNOWLEDGE BASE (used by /glossary and internal cross-checks)
# ─────────────────────────────────────────────
KNOWLEDGE_BASE = [
    {"en": "Oil Formation Volume Factor (Bo)", "ar": "معامل حجم تكوين الزيت",
     "category": "PVT", "unit": "rb/STB",
     "def_ar": "نسبة حجم الزيت مع الغاز المذاب داخل المكمن الى حجمه في خزان التخزين السطحي.",
     "trend": "rises to max at Pb (above Pb), decreases below Pb",
     "relationship_key": "bo_vs_p", "typical_range": "1.0 - 2.0 rb/STB"},

    {"en": "Solution Gas-Oil Ratio (Rs)", "ar": "نسبة الغاز المذاب",
     "category": "PVT", "unit": "scf/STB",
     "def_ar": "حجم الغاز الذائب في برميل واحد من زيت خزان التخزين عند ضغط وحرارة المكمن.",
     "trend": "constant = Rsi above Pb, decreases below Pb",
     "relationship_key": "rs_vs_p", "typical_range": "100 - 2000+ scf/STB"},

    {"en": "Bubble Point Pressure (Pb)", "ar": "ضغط نقطة الفقاعة",
     "category": "PVT", "unit": "psia",
     "def_ar": "الضغط الذي يبدأ عنده انفصال أول فقاعة غاز عن الزيت. عنده Bo اعظمي و Rs = Rsi.",
     "trend": "pivot point -- see Bo, Rs, viscosity, density curves",
     "relationship_key": "saturation_pressure_oil", "typical_range": "100 - 5000+ psia"},

    {"en": "Dew Point Pressure (Pd)", "ar": "ضغط نقطة الندى",
     "category": "PVT", "unit": "psia",
     "def_ar": "الضغط الذي تبدأ عنده اول قطرة سائل بالتكون من الغاز. نقطة بداية التكثف الرجعي.",
     "trend": "pivot point -- liquid dropout begins below this",
     "relationship_key": "saturation_pressure_gas", "typical_range": "varies by composition"},

    {"en": "Gas Formation Volume Factor (Bg)", "ar": "معامل حجم تكوين الغاز",
     "category": "PVT", "unit": "rb/scf",
     "def_ar": "نسبة حجم الغاز عند ظروف المكمن الى حجمه عند الظروف القياسية.",
     "trend": "smooth hyperbolic decrease as pressure increases",
     "relationship_key": "bg_vs_p", "typical_range": "0.0005 - 0.02 rb/scf"},

    {"en": "Gas Deviation Factor (Z-factor)", "ar": "معامل الانحراف الغازي",
     "category": "PVT", "unit": "dimensionless",
     "def_ar": "معامل تصحيح لقانون الغاز المثالي يعكس السلوك الحقيقي للغاز.",
     "trend": "U-shaped: decreases from 1, reaches minimum, increases again",
     "relationship_key": "z_vs_p", "typical_range": "0.6 - 1.2"},

    {"en": "Oil Viscosity", "ar": "لزوجة الزيت",
     "category": "PVT", "unit": "cP",
     "def_ar": "مقاومة الزيت للتدفق. تتأثر بكمية الغاز المذاب.",
     "trend": "decreases to min at Pb (above Pb), increases below Pb",
     "relationship_key": "oil_visc_vs_p", "typical_range": "0.2 - 50+ cP"},

    {"en": "Gas Viscosity", "ar": "لزوجة الغاز",
     "category": "PVT", "unit": "cP",
     "def_ar": "مقاومة الغاز للتدفق. تزداد مع زيادة كثافة الغاز.",
     "trend": "monotonically increases with pressure",
     "relationship_key": "gas_visc_vs_p", "typical_range": "0.01 - 0.05 cP"},

    {"en": "Oil Density", "ar": "كثافة الزيت",
     "category": "PVT", "unit": "lb/ft3",
     "def_ar": "كتلة الزيت لكل وحدة حجم عند ظروف المكمن.",
     "trend": "decreases to min at Pb (above Pb), increases below Pb",
     "relationship_key": "oil_density_vs_p", "typical_range": "40 - 60 lb/ft3"},

    {"en": "Relative Volume (CCE)", "ar": "الحجم النسبي",
     "category": "PVT", "unit": "dimensionless (V/Vsat)",
     "def_ar": "حجم العينة عند ضغط معين منسوباً الى حجمها عند ضغط التشبع.",
     "trend": "gentle slope above Pb, =1.0 at Pb, steep slope below Pb",
     "relationship_key": "vrel_vs_p_cce", "typical_range": "n/a"},

    {"en": "Liquid Dropout", "ar": "نسبة تكثف السوائل",
     "category": "PVT - Gas Condensate", "unit": "% of HC pore volume",
     "def_ar": "نسبة السائل المتكثف من الغاز داخل المكمن عند الضغوط الاقل من ضغط الندى، تقاس باختبار CVD.",
     "trend": "0% above Pd, rises to peak (retrograde), then decreases (re-vaporization)",
     "relationship_key": "liquid_dropout_vs_p", "typical_range": "0 - 30%+"},

    {"en": "Condensate-Gas Ratio (CGR)", "ar": "نسبة المكثفات إلى الغاز",
     "category": "Production - Gas Condensate", "unit": "STB/MMscf",
     "def_ar": "حجم المكثفات السطحية المنتجة لكل وحدة حجم من الغاز المنتج.",
     "trend": "roughly constant above Pd, decreases below Pd",
     "relationship_key": "cgr_vs_p", "typical_range": "10 - 300 STB/MMscf"},

    {"en": "Retrograde Condensation", "ar": "التكثف الرجعي",
     "category": "Phase Behavior", "unit": "n/a",
     "def_ar": "ظاهرة تكون سائل داخل المكمن نتيجة انخفاض الضغط دون ضغط الندى، عكس السلوك الطوري المعتاد.",
     "trend": "descriptive term for liquid_dropout_vs_p rising region",
     "relationship_key": "liquid_dropout_vs_p", "typical_range": "n/a"},

    {"en": "Porosity", "ar": "المسامية",
     "category": "Reservoir", "unit": "fraction or %",
     "def_ar": "نسبة حجم الفراغات الى الحجم الكلي للصخرة.",
     "trend": "static property", "relationship_key": None, "typical_range": "0.05 - 0.35"},

    {"en": "Permeability", "ar": "النفاذية",
     "category": "Reservoir", "unit": "mD",
     "def_ar": "قدرة الصخرة على نقل الموائع تحت فرق ضغط.",
     "trend": "static property", "relationship_key": None, "typical_range": "0.1 - 1000+ mD"},

    {"en": "Skin Factor", "ar": "عامل الجلد",
     "category": "Production", "unit": "dimensionless",
     "def_ar": "مقياس تأثير الضرر أو التحفيز حول البئر. موجب = ضرر، سالب = تحفيز.",
     "trend": "well condition indicator", "relationship_key": None, "typical_range": "-5 to +20"},

    {"en": "Productivity Index (PI)", "ar": "مؤشر الإنتاجية",
     "category": "Production", "unit": "STB/day/psi",
     "def_ar": "معدل الانتاج لكل وحدة فرق ضغط بين المكمن وقاع البئر.",
     "trend": "well performance indicator", "relationship_key": None, "typical_range": "0.5 - 50 STB/day/psi"},

    {"en": "Water Cut", "ar": "نسبة الماء المنتج",
     "category": "Production", "unit": "%",
     "def_ar": "نسبة الماء في اجمالي السوائل المنتجة.",
     "trend": "increases over field life", "relationship_key": None, "typical_range": "0 - 98%"},

    {"en": "Hydrostatic Pressure", "ar": "الضغط الهيدروستاتيكي",
     "category": "Drilling", "unit": "psi",
     "def_ar": "الضغط الناتج عن عمود سائل الحفر. P = 0.052 x MW x TVD.",
     "trend": "calculated from mud column", "relationship_key": None, "typical_range": "depends on MW, TVD"},

    {"en": "Kick", "ar": "اندفاع المكمن",
     "category": "Drilling", "unit": "n/a",
     "def_ar": "دخول غير متحكم لسوائل المكمن الى البئر. يستلزم اغلاق BOP فورا.",
     "trend": "well control event", "relationship_key": None, "typical_range": "n/a"},

    {"en": "Net Present Value (NPV)", "ar": "صافي القيمة الحالية",
     "category": "Economics", "unit": "$",
     "def_ar": "مجموع التدفقات النقدية المخصومة ناقصا الاستثمار الاولي.",
     "trend": "n/a", "relationship_key": None, "typical_range": "n/a"},
]


# ─────────────────────────────────────────────
#  FLUID CLASSIFICATION TABLE  (used by /classify)
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
    """Classifies fluid type per FLUID_CLASSIFICATION_TABLE (BLOCK 6)."""
    for row in FLUID_CLASSIFICATION_TABLE[:-1]:  # skip dry gas (special case)
        if row["gor_min"] <= gor < row["gor_max"] and row["api_min"] <= api <= row["api_max"]:
            return (
                f"{row['type_en']} ({row['type_ar']})\n\n"
                f"GOR = {gor:,.0f} scf/STB (المدى: {row['gor_min']:,}-{row['gor_max']:,})\n"
                f"API = {api} (المدى: {row['api_min']}-{row['api_max']})\n\n"
                f"السلوك المتوقع: {row['behavior']}"
            )
    # GOR/API combination doesn't fit cleanly into one row
    return (
        f"GOR = {gor:,.0f} scf/STB و API = {api} لا يقعان معا بشكل واضح في "
        f"فئة واحدة من جدول التصنيف.\n\n"
        f"هذا قد يشير الى سائل قريب من النقطة الحرجة (Near-Critical) -- "
        f"يُنصح بمراجعة بيانات CCE/CVD المخبرية وتأكيد نوع السائل عبر "
        f"درجة حرارة المكمن مقارنة بالنقطة الحرجة، وقد يكون النموذج "
        f"التركيبي (Compositional/EOS) أنسب من Black-Oil."
    )


# ─────────────────────────────────────────────
#  PVT PLOT RULES + ASCII SKETCHES  (used by /plot, /graph, /check)
# ─────────────────────────────────────────────
PVT_PLOT_RULES = {
    "bo_vs_p": {
        "title_en": "Bo vs Pressure", "title_ar": "معامل حجم تكوين الزيت مقابل الضغط",
        "x_axis": "Pressure (psia)", "y_axis": "Bo (rb/STB)",
        "above_saturation": "increases gently as P decreases toward Pb (oil expansion, Rs constant)",
        "at_saturation": "MAXIMUM value (Bob)",
        "below_saturation": "decreases as P decreases (gas evolves out of solution)",
        "shape": "rises to a peak at Pb, then declines",
        "pivot": "Pb (peak)",
        "common_ai_mistakes": [
            "monotonic increase as P decreases across whole range",
            "constant Bo below Pb",
            "confusing Bo with Bt (two-phase FVF, which DOES rise monotonically below Pb)",
        ],
    },
    "rs_vs_p": {
        "title_en": "Rs vs Pressure", "title_ar": "نسبة الغاز المذاب مقابل الضغط",
        "x_axis": "Pressure (psia)", "y_axis": "Rs (scf/STB)",
        "above_saturation": "CONSTANT at Rsi (no free gas exists)",
        "at_saturation": "Rs = Rsi (maximum, start of decline)",
        "below_saturation": "decreases toward 0 as P decreases (gas evolves)",
        "shape": "flat line above Pb, then declines below Pb",
        "pivot": "Pb (elbow where flat line begins to decline)",
        "common_ai_mistakes": [
            "Rs increasing as pressure decreases (backwards)",
            "Rs varying above Pb",
            "confusing Rs (in-solution, oil-based) with produced GOR (includes free gas)",
        ],
    },
    "oil_visc_vs_p": {
        "title_en": "Oil Viscosity vs Pressure", "title_ar": "لزوجة الزيت مقابل الضغط",
        "x_axis": "Pressure (psia)", "y_axis": "Oil Viscosity (cP)",
        "above_saturation": "decreases gently as P decreases toward Pb (slight expansion)",
        "at_saturation": "MINIMUM value (mu_ob)",
        "below_saturation": "increases as P decreases (gas leaves, losing 'lubrication')",
        "shape": "mirror image of Bo -- trough at Pb",
        "pivot": "Pb (minimum/trough)",
        "common_ai_mistakes": [
            "monotonic increase as pressure decreases everywhere",
            "constant viscosity below Pb",
            "not recognizing the Pb minimum",
        ],
    },
    "oil_density_vs_p": {
        "title_en": "Oil Density vs Pressure", "title_ar": "كثافة الزيت مقابل الضغط",
        "x_axis": "Pressure (psia)", "y_axis": "Oil Density (lb/ft3)",
        "above_saturation": "decreases gently as P decreases toward Pb",
        "at_saturation": "MINIMUM value",
        "below_saturation": "increases as P decreases (gas-depleted liquid is heavier)",
        "shape": "mirror image of Bo -- minimum at Pb",
        "pivot": "Pb (minimum)",
        "common_ai_mistakes": [
            "monotonic increase as pressure decreases (ignores Pb minimum)",
        ],
    },
    "vrel_vs_p_cce": {
        "title_en": "Relative Volume vs Pressure (CCE)", "title_ar": "الحجم النسبي مقابل الضغط (اختبار CCE)",
        "x_axis": "Pressure (psia)", "y_axis": "Relative Volume V/Vsat (dimensionless)",
        "above_saturation": "gentle upward slope as P decreases (single-phase compressibility)",
        "at_saturation": "Vrel = 1.0 by definition; SLOPE BREAK occurs here",
        "below_saturation": "steep upward slope as P decreases (gas evolution dominates)",
        "shape": "two straight-ish segments meeting at a kink at Pb",
        "pivot": "Pb (slope discontinuity) -- THE STANDARD METHOD TO FIND Pb FROM CCE DATA",
        "common_ai_mistakes": [
            "single straight line through whole curve (no slope break)",
            "Vrel decreasing as pressure decreases (always increases)",
        ],
    },
    "bg_vs_p": {
        "title_en": "Bg vs Pressure", "title_ar": "معامل حجم تكوين الغاز مقابل الضغط",
        "x_axis": "Pressure (psia)", "y_axis": "Bg (rb/scf)",
        "above_saturation": "n/a -- no saturation pivot for Bg itself",
        "at_saturation": "n/a", "below_saturation": "n/a",
        "shape": "smooth hyperbolic decrease as pressure increases (Bg ~ Z*T/P)",
        "pivot": "none (Pd matters for liquid dropout/CGR, not Bg shape)",
        "common_ai_mistakes": [
            "Bg increasing with pressure (backwards)",
            "drawing a Bo-like peak at a saturation pressure",
        ],
    },
    "z_vs_p": {
        "title_en": "Z-factor vs Pressure", "title_ar": "معامل الانحراف الغازي مقابل الضغط",
        "x_axis": "Pressure (psia)", "y_axis": "Z-factor (dimensionless)",
        "above_saturation": "n/a", "at_saturation": "n/a", "below_saturation": "n/a",
        "shape": "U-shaped/checkmark: starts near 1 at low P, decreases to a minimum, then increases (can exceed 1) at high P",
        "pivot": "minimum Z occurs at intermediate P (function of Tpr/Ppr), not at Pb/Pd",
        "common_ai_mistakes": [
            "Z decreasing monotonically with pressure",
            "Z = 1 always",
            "minimum placed at Pb or Pd (independent of saturation pressure)",
        ],
    },
    "gas_visc_vs_p": {
        "title_en": "Gas Viscosity vs Pressure", "title_ar": "لزوجة الغاز مقابل الضغط",
        "x_axis": "Pressure (psia)", "y_axis": "Gas Viscosity (cP)",
        "above_saturation": "n/a", "at_saturation": "n/a", "below_saturation": "n/a",
        "shape": "monotonically increases with pressure (denser gas -> more collisions)",
        "pivot": "none",
        "common_ai_mistakes": [
            "applying oil-viscosity Pb-minimum logic to gas (no such inversion)",
            "confusing direction with Bg (Bg decreases, gas visc increases, with P)",
        ],
    },
    "liquid_dropout_vs_p": {
        "title_en": "Liquid Dropout vs Pressure (CVD, Gas Condensate)",
        "title_ar": "نسبة تكثف السوائل مقابل الضغط (اختبار CVD)",
        "x_axis": "Pressure (psia)", "y_axis": "Liquid Dropout (% of HC pore volume)",
        "above_saturation": "0% (single-phase gas, Pd not yet reached)",
        "at_saturation": "0% by definition (Pd = first liquid drop)",
        "below_saturation": "RISES sharply (retrograde region), reaches a PEAK, then DECREASES (re-vaporization)",
        "shape": "rises from 0 at Pd, peaks, then declines -- NEVER monotonic",
        "pivot": "Pd (start of curve, dropout=0); peak occurs at lower P than Pd",
        "common_ai_mistakes": [
            "monotonically increasing dropout with no peak/decline",
            "dropout starting above Pd",
            "omitting the word 'retrograde'",
        ],
    },
    "cgr_vs_p": {
        "title_en": "CGR vs Pressure", "title_ar": "نسبة المكثفات إلى الغاز مقابل الضغط",
        "x_axis": "Pressure (psia) or depletion stage", "y_axis": "CGR (STB/MMscf)",
        "above_saturation": "roughly constant near initial value",
        "at_saturation": "constant trend continues at Pd",
        "below_saturation": "DECREASES (produced stream becomes leaner -- liquid trapped in reservoir)",
        "shape": "flat then declining below Pd",
        "pivot": "Pd (where decline begins)",
        "common_ai_mistakes": [
            "CGR increasing as pressure depletes",
            "confusing with liquid dropout (which initially rises in the reservoir)",
        ],
    },
    "pt_diagram": {
        "title_en": "P-T Phase Diagram", "title_ar": "مخطط الضغط - درجة الحرارة الطوري",
        "x_axis": "Temperature (F)", "y_axis": "Pressure (psia)",
        "above_saturation": "n/a", "at_saturation": "n/a", "below_saturation": "n/a",
        "shape": "bubble-point line and dew-point line meeting at Critical Point; envelope bounded by Cricondenbar (max P) and Cricondentherm (max T)",
        "pivot": "Critical Point (where bubble/dew lines meet)",
        "common_ai_mistakes": [
            "single smooth curve with no critical point marked",
            "placing critical point at cricondenbar (generally different points)",
            "applying 'retrograde' label to all gas reservoirs (only Tc < Tres < Tcricondentherm)",
        ],
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
    "oil_density_vs_p": r"""
Oil Density (lb/ft3)
  ^
  |\                                        /
  | \                                     /
  |  \___                          ____/
  |      \__ (min at Pb) _________/
  +------------------------------------------------> Pressure
  (low P)              Pb                  (high P, Pi)
""",
    "vrel_vs_p_cce": r"""
Relative Volume (Vrel)
  ^
  |                                      /
  |                                    /
  |                              ____/
  |                    ___,-'  <- steep (below Pb)
  |    ______,-,-'  1.0 at Pb (slope break)
  |__,-'  <- gentle (above Pb)
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
  (no saturation pivot for Bg)
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
   (low P)                                  (high P)
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
  (monotonic increase, no pivot)
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
  |---'------------------------------------------> Pressure
  (low P)              Pd (dropout=0)       (high P)
        re-vaporization <-  peak  -> retrograde rise
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
  |       .'        '.
  |     .'  TWO       '.
  |   .'   PHASE        '.
  | .'    REGION          '.
  |C <- Critical Pt          '.
  | '.                          '.
  |    '.  Bubble Pt   Dew Pt line '.
  |       '.   line          '---.   '---.
  |          '------------------------'----*  Cricondentherm
  +------------------------------------------------> Temperature
  (Oil: T<Tc)   (Gas Condensate: Tc<T<Tcricondentherm)  (Dry/Wet Gas: T>Tcricondentherm)
""",
}


PLOT_ALIASES = {
    "bo": "bo_vs_p", "fvf": "bo_vs_p", "oil fvf": "bo_vs_p",
    "rs": "rs_vs_p", "solution gor": "rs_vs_p",
    "oil viscosity": "oil_visc_vs_p", "viscosity": "oil_visc_vs_p", "mu_o": "oil_visc_vs_p",
    "oil density": "oil_density_vs_p", "density": "oil_density_vs_p",
    "relative volume": "vrel_vs_p_cce", "vrel": "vrel_vs_p_cce", "cce": "vrel_vs_p_cce",
    "bg": "bg_vs_p", "gas fvf": "bg_vs_p",
    "z": "z_vs_p", "z-factor": "z_vs_p", "zfactor": "z_vs_p",
    "gas viscosity": "gas_visc_vs_p", "mu_g": "gas_visc_vs_p",
    "liquid dropout": "liquid_dropout_vs_p", "dropout": "liquid_dropout_vs_p", "cvd": "liquid_dropout_vs_p",
    "cgr": "cgr_vs_p",
    "phase envelope": "pt_diagram", "pt diagram": "pt_diagram", "p-t": "pt_diagram", "envelope": "pt_diagram",
}


def format_plot_response(relationship_key: str) -> str:
    """Builds the full structured /plot response for a given relationship."""
    rule = PVT_PLOT_RULES.get(relationship_key)
    sketch = ASCII_SKETCHES.get(relationship_key)
    if not rule or not sketch:
        return None

    lines = [
        rule["title_en"],
        f"({rule['title_ar']})",
        "",
        f"X-axis: {rule['x_axis']}",
        f"Y-axis: {rule['y_axis']}",
        "",
        "Shape: " + rule["shape"],
        "",
    ]
    if rule["above_saturation"] != "n/a":
        lines.append("Above saturation pressure: " + rule["above_saturation"])
    if rule["at_saturation"] != "n/a":
        lines.append("At saturation pressure: " + rule["at_saturation"])
    if rule["below_saturation"] != "n/a":
        lines.append("Below saturation pressure: " + rule["below_saturation"])

    lines.append("")
    lines.append("Pivot: " + rule["pivot"])
    lines.append("")
    lines.append("Common AI mistakes to avoid:")
    for mistake in rule["common_ai_mistakes"]:
        lines.append("  - " + mistake)
    lines.append("")
    lines.append("ASCII sketch:")
    lines.append(sketch)
    return "\n".join(lines)


# ─────────────────────────────────────────────
#  CALCULATION ENGINE  (deterministic -- /calc, /estimate)
# ─────────────────────────────────────────────
EXACT_FORMULAS = {
    "api": {
        "name_en": "API Gravity", "name_ar": "درجة API",
        "inputs": ["sg"], "units": {"sg": "dimensionless (specific gravity, water=1.0)"},
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
    "hydrostatic": {
        "name_en": "Hydrostatic Pressure", "name_ar": "الضغط الهيدروستاتيكي",
        "inputs": ["mw", "tvd"], "units": {"mw": "ppg", "tvd": "ft"},
        "formula_str": "P (psi) = 0.052 x MW x TVD",
        "func": lambda mw, tvd: 0.052 * mw * tvd,
        "output_unit": "psi",
        "validation": lambda mw, tvd: 6 < mw < 25 and tvd > 0,
    },
    "ooip": {
        "name_en": "Original Oil In Place (Volumetric)", "name_ar": "النفط الأصلي في المكمن",
        "inputs": ["area", "h", "phi", "sw", "bo"],
        "units": {"area": "acres", "h": "ft", "phi": "fraction", "sw": "fraction", "bo": "rb/STB"},
        "formula_str": "OOIP = (7758 x A x h x phi x (1-Sw)) / Bo",
        "func": lambda area, h, phi, sw, bo: (7758 * area * h * phi * (1 - sw)) / bo,
        "output_unit": "STB",
        "validation": lambda area, h, phi, sw, bo: 0 < phi < 1 and 0 <= sw < 1 and bo > 0,
    },
    "darcy": {
        "name_en": "Darcy Linear Flow Rate", "name_ar": "معدل التدفق الخطي (دارسي)",
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
    "water_cut": {
        "name_en": "Water Cut", "name_ar": "نسبة الماء المنتج",
        "inputs": ["qw", "qo"], "units": {"qw": "bbl/day", "qo": "bbl/day"},
        "formula_str": "WC = qw / (qo + qw) x 100",
        "func": lambda qw, qo: (qw / (qo + qw)) * 100,
        "output_unit": "%",
        "validation": lambda qw, qo: qw >= 0 and qo >= 0 and (qw + qo) > 0,
    },
    "productivity_index": {
        "name_en": "Productivity Index", "name_ar": "مؤشر الإنتاجية",
        "inputs": ["q", "pr", "pwf"], "units": {"q": "STB/day", "pr": "psi", "pwf": "psi"},
        "formula_str": "PI = q / (Pr - Pwf)",
        "func": lambda q, pr, pwf: q / (pr - pwf),
        "output_unit": "STB/day/psi",
        "validation": lambda q, pr, pwf: pr > pwf and q > 0,
    },
}

CORRELATIONS = {
    "pb_standing": {
        "name_en": "Bubble Point Pressure (Standing, 1947)", "name_ar": "ضغط نقطة الفقاعة (معادلة ستاندينغ)",
        "inputs": ["rs", "gas_sg", "tres", "api"],
        "units": {"rs": "scf/STB", "gas_sg": "dimensionless", "tres": "deg F", "api": "deg API"},
        "formula_str": "Pb = 18.2 * [(Rs/gamma_g)^0.83 * 10^(0.00091*T - 0.0125*API) - 1.4]",
        "func": lambda rs, gas_sg, tres, api: 18.2 * (
            (rs / gas_sg) ** 0.83 * 10 ** (0.00091 * tres - 0.0125 * api) - 1.4
        ),
        "output_unit": "psia",
        "applicability": {"rs": (20, 1425), "api": (16.5, 63.8), "tres": (100, 258)},
    },
    "rs_standing": {
        "name_en": "Solution GOR (Standing, 1947)", "name_ar": "نسبة الغاز المذاب (معادلة ستاندينغ)",
        "inputs": ["p", "gas_sg", "tres", "api"],
        "units": {"p": "psia", "gas_sg": "dimensionless", "tres": "deg F", "api": "deg API"},
        "formula_str": "Rs = gamma_g * [(P/18.2 + 1.4) * 10^(0.0125*API - 0.00091*T)]^1.2048",
        "func": lambda p, gas_sg, tres, api: gas_sg * (
            (p / 18.2 + 1.4) * 10 ** (0.0125 * api - 0.00091 * tres)
        ) ** 1.2048,
        "output_unit": "scf/STB",
        "applicability": {"p": (130, 7000), "api": (16.5, 63.8), "tres": (100, 258)},
    },
}


def parse_kv_args(text: str) -> dict:
    """Parses 'key=value key2=value2' patterns into a dict of floats."""
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
        lines.append("")
        lines.append("Usage: /calc " + calc_type + " " +
                      " ".join(f"{k}=value" for k in spec["inputs"]))
        return "\n".join(lines)

    values = [kwargs[k] for k in spec["inputs"]]

    if "validation" in spec and not spec["validation"](*values):
        return (f"تحذير: القيم المدخلة خارج النطاق الطبيعي لـ {spec['name_en']}.\n"
                f"القيم المدخلة: {dict(zip(spec['inputs'], values))}\n"
                f"يرجى مراجعة الوحدات والقيم.")

    result = spec["func"](*values)

    out = [
        f"{spec['name_en']} ({spec['name_ar']})",
        "",
        f"المعادلة: {spec['formula_str']}",
        "المدخلات: " + ", ".join(f"{k}={v}" for k, v in zip(spec["inputs"], values)),
        f"النتيجة: {result:,.4f} {spec['output_unit']}",
    ]
    if "classify" in spec:
        out.append(f"التصنيف: {spec['classify'](result)}")
    return "\n".join(out)


def run_correlation(calc_type: str, **kwargs) -> str:
    spec = CORRELATIONS.get(calc_type)
    if not spec:
        return None

    missing = [k for k in spec["inputs"] if k not in kwargs]
    if missing:
        lines = [f"DATA REQUIRED for {spec['name_en']} ({spec['name_ar']}):"]
        for inp in spec["inputs"]:
            lines.append(f"  {inp} ({spec['units'][inp]})")
        lines.append("")
        lines.append("Usage: /estimate " + calc_type + " " +
                      " ".join(f"{k}=value" for k in spec["inputs"]))
        return "\n".join(lines)

    values = [kwargs[k] for k in spec["inputs"]]
    result = spec["func"](*values)

    out_of_range = []
    for inp, (lo, hi) in spec.get("applicability", {}).items():
        v = kwargs.get(inp)
        if v is not None and not (lo <= v <= hi):
            out_of_range.append(f"{inp}={v} (range: {lo}-{hi})")

    out = [
        f"CORRELATION ESTIMATE -- {spec['name_en']} ({spec['name_ar']})",
        "",
        f"المعادلة: {spec['formula_str']}",
        "المدخلات: " + ", ".join(f"{k}={v}" for k, v in zip(spec["inputs"], values)),
        f"التقدير: {result:,.2f} {spec['output_unit']}",
    ]
    if out_of_range:
        out.append("")
        out.append("تحذير -- المدخلات خارج نطاق المعادلة: " + "; ".join(out_of_range))
    out.append("")
    out.append("ملاحظة: هذا تقدير من معادلة تجريبية، ليس قياساً مخبرياً. "
                "يُنصح بالتحقق عبر اختبار CCE/DV مخبري.")
    return "\n".join(out)


# ─────────────────────────────────────────────
#  UNIT CONVERSIONS  (/convert)
# ─────────────────────────────────────────────
UNIT_CONVERSIONS = {
    ("psi", "bar"): lambda v: v * 0.0689476,
    ("bar", "psi"): lambda v: v / 0.0689476,
    ("psi", "kpa"): lambda v: v * 6.89476,
    ("kpa", "psi"): lambda v: v / 6.89476,
    ("ppg", "lb/ft3"): lambda v: v * 7.4805,
    ("lb/ft3", "ppg"): lambda v: v / 7.4805,
    ("ppg", "sg"): lambda v: v / 8.345,
    ("sg", "ppg"): lambda v: v * 8.345,
    ("scf/stb", "m3/m3"): lambda v: v * 0.1781,
    ("m3/m3", "scf/stb"): lambda v: v / 0.1781,
    ("bbl", "m3"): lambda v: v * 0.158987,
    ("m3", "bbl"): lambda v: v / 0.158987,
    ("ft", "m"): lambda v: v * 0.3048,
    ("m", "ft"): lambda v: v / 0.3048,
    ("cp", "pa.s"): lambda v: v * 0.001,
    ("pa.s", "cp"): lambda v: v / 0.001,
    ("degf", "degc"): lambda v: (v - 32) * 5 / 9,
    ("degc", "degf"): lambda v: v * 9 / 5 + 32,
}


def run_unit_conversion(value: float, from_unit: str, to_unit: str) -> str:
    key = (from_unit.lower().strip(), to_unit.lower().strip())
    func = UNIT_CONVERSIONS.get(key)
    if not func:
        available = sorted(set(k[0] for k in UNIT_CONVERSIONS.keys()))
        return (f"تحويل غير متاح من {from_unit} الى {to_unit}.\n"
                f"الوحدات المتاحة: {', '.join(available)}")
    result = func(value)
    return f"{value} {from_unit} = {result:,.6f} {to_unit}".rstrip("0").rstrip(".") + f" {to_unit}" \
        if False else f"{value} {from_unit} = {result:,.4f} {to_unit}"


# ─────────────────────────────────────────────
#  PVT TREND VALIDATOR  (/check)
# ─────────────────────────────────────────────
def check_pvt_trend(relationship_key: str, pressures: list, values: list,
                     pb_or_pd: float = None) -> str:
    if len(pressures) != len(values) or len(pressures) < 2:
        return "بيانات غير كافية للفحص. أحتاج سلسلة ضغوط وقيم متقابلة (3 نقاط على الأقل)."

    paired = sorted(zip(pressures, values))
    issues = []
    rule = PVT_PLOT_RULES.get(relationship_key)
    if not rule:
        return f"نوع العلاقة \'{relationship_key}\' غير معروف."

    if relationship_key == "rs_vs_p":
        if pb_or_pd:
            above = [(p, v) for p, v in paired if p >= pb_or_pd]
            below = [(p, v) for p, v in paired if p < pb_or_pd]
            if len(above) >= 2:
                vals_above = [v for p, v in above]
                if max(vals_above) - min(vals_above) > 0.05 * max(vals_above):
                    issues.append(
                        "Rs يتغير بشكل ملحوظ عند ضغوط أعلى من Pb -- "
                        "Rs يجب أن يكون ثابتاً (=Rsi) فوق ضغط نقطة الفقاعة."
                    )
            if len(below) >= 2:
                # below Pb: Rs must INCREASE as pressure increases (i.e.
                # Rs DECREASES as pressure decreases). sorted_below is
                # ascending by pressure, so Rs values must also be
                # non-decreasing. A decrease in Rs as pressure increases
                # is the violation.
                sorted_below = sorted(below)
                for i in range(1, len(sorted_below)):
                    if sorted_below[i][1] < sorted_below[i-1][1]:
                        issues.append(
                            f"Rs عند P={sorted_below[i][0]} أصغر من Rs عند "
                            f"P={sorted_below[i-1][0]} -- Rs يجب أن يتزايد مع "
                            f"تزايد الضغط (أي يتناقص مع تناقص الضغط) تحت Pb."
                        )
                        break

    elif relationship_key == "bo_vs_p":
        if pb_or_pd:
            # below Pb: Bo must INCREASE as pressure increases (i.e. Bo
            # decreases as pressure decreases below Pb). below is sorted
            # ascending by pressure, so Bo values must be non-decreasing.
            below = sorted([(p, v) for p, v in paired if p < pb_or_pd])
            for i in range(1, len(below)):
                if below[i][1] < below[i-1][1]:
                    issues.append(
                        f"Bo عند P={below[i][0]} أصغر من Bo عند P={below[i-1][0]} "
                        f"-- Bo يجب أن يتزايد مع تزايد الضغط (أي يتناقص مع "
                        f"تناقص الضغط) تحت Pb."
                    )
                    break
            # above Pb: Bo should generally be close to its max at Pb and
            # slightly lower at higher P (gentle decrease above Pb).
            above = sorted([(p, v) for p, v in paired if p >= pb_or_pd])
            if len(above) >= 2:
                for i in range(1, len(above)):
                    if above[i][1] > above[i-1][1]:
                        issues.append(
                            f"Bo عند P={above[i][0]} أكبر من Bo عند "
                            f"P={above[i-1][0]} -- فوق Pb يجب أن يتناقص Bo "
                            f"بشكل طفيف مع تزايد الضغط (Bo أعظمي عند Pb)."
                        )
                        break

    elif relationship_key == "liquid_dropout_vs_p":
        vals = [v for p, v in paired]
        if vals == sorted(vals) or vals == sorted(vals, reverse=True):
            issues.append(
                "بيانات Liquid Dropout تبدو أحادية الاتجاه (تزايد أو تناقص "
                "مستمر) -- السلوك الفعلي يجب أن يبدأ من صفر عند Pd، يرتفع "
                "لقمة (التكثف الرجعي)، ثم ينخفض (إعادة التبخر). تحقق من "
                "اكتمال بيانات اختبار CVD."
            )

    elif relationship_key == "z_vs_p":
        vals = [v for p, v in paired]
        if vals == sorted(vals) or vals == sorted(vals, reverse=True):
            issues.append(
                "بيانات Z-factor تبدو أحادية الاتجاه -- السلوك الطبيعي على "
                "شكل حرف U (يتناقص ثم يتزايد). تحقق من نطاق الضغوط المغطى."
            )

    if not issues:
        return (f"فحص {rule['title_en']} ({rule['title_ar']}): "
                f"البيانات تبدو متوافقة مع السلوك الفيزيائي المتوقع.")

    return (f"فحص {rule['title_en']} ({rule['title_ar']}) -- تم اكتشاف مشاكل:\n\n"
            + "\n".join(f"- {issue}" for issue in issues))


# ─────────────────────────────────────────────
#  PVTO / PVTG SKELETON GENERATORS  (/pvto, /pvtg)
# ─────────────────────────────────────────────
def generate_pvto_skeleton() -> str:
    return (
        "PVTO Table (Live Oil -- Eclipse)\n"
        "الجدول المطلوب: PVTO (للزيت الحي مع غاز مذاب)\n\n"
        "هيكل الجدول لكل قيمة Rs:\n"
        "  السطر المشبع (Saturated row): Rs, Pb(Rs), Bo(Pb), mu_o(Pb)\n"
        "  أسطر التمدد فوق التشبع (Undersaturated extension):\n"
        "    نفس Rs، مع P أعلى من Pb، Bo يتناقص، mu_o يتزايد\n\n"
        "DATA REQUIRED:\n"
        "  لكل قيمة Rs من 0 إلى Rsi:\n"
        "    - الضغط المشبع Pb(Rs)  [psia]\n"
        "    - Bo عند Pb(Rs)        [rb/STB]\n"
        "    - mu_o عند Pb(Rs)      [cP]\n"
        "    - معامل انضغاطية الزيت Co فوق Pb [1/psi]\n"
        "    - تدرج اللزوجة فوق Pb dmu_o/dP [cP/psi]\n\n"
        "المصدر: بيانات Differential Liberation (DV) أسفل Pb، "
        "وبيانات CCE فوق Pb.\n\n"
        "إذا كان Rs ~ 0 (زيت ثقيل/ميت) استخدم PVDO بدلاً من PVTO:\n"
        "  هيكل PVDO: P, Bo(P), mu_o(P)  -- بدون عمود Rs"
    )


def generate_pvtg_skeleton() -> str:
    return (
        "PVTG Table (Live/Wet Gas -- Eclipse)\n"
        "الجدول المطلوب: PVTG (للغاز مع مكثفات Rv)\n\n"
        "هيكل الجدول لكل قيمة ضغط:\n"
        "  P, Rv(P), Bg(P), mu_g(P)\n"
        "  Rv = نسبة الزيت المتبخر في الغاز (Vaporized Oil-Gas Ratio)\n\n"
        "DATA REQUIRED:\n"
        "  لكل ضغط من الضغط الأقصى إلى الأدنى:\n"
        "    - Bg(P)   [rb/scf]   من اختبار CCE/CVD\n"
        "    - mu_g(P) [cP]       من اختبار CVD\n"
        "    - Rv(P)   [STB/scf]  من التحليل التركيبي (للغاز المكثف/الرطب)\n\n"
        "إذا كان Rv ~ 0 (غاز جاف) استخدم PVDG بدلاً من PVTG:\n"
        "  هيكل PVDG: P, Bg(P), mu_g(P)  -- بدون عمود Rv"
    )


# ─────────────────────────────────────────────
#  SIMULATION EXPORT DECISION  (/export_sim)
# ─────────────────────────────────────────────
EXPORT_SIM_DECISIONS = {
    "black_oil": (
        "PVTO (إذا Rs > 0) أو PVDO (إذا Rs ~ 0)\n"
        "نموذج Black-Oil كافٍ. لا حاجة لـ EOS."
    ),
    "volatile_oil": (
        "PVTO مع كثافة شبكة بيانات عالية قرب Pb (نظراً للتغير الحاد "
        "في Bo و Rs قرب نقطة الفقاعة).\n"
        "إذا كان السائل قريباً من النقطة الحرجة (near-critical)، "
        "يُنصح بالتحول إلى نموذج تركيبي (Compositional/EOS)."
    ),
    "gas_condensate": (
        "PVTG مع Rv من التحليل التركيبي.\n"
        "للغاز المكثف الغني (Rich Gas Condensate) أو القريب من "
        "النقطة الحرجة، نموذج Black-Oil/PVTG قد لا يلتقط التغير "
        "السريع في التركيب أسفل Pd بدقة -- يُنصح بنموذج تركيبي "
        "(Compositional, EOS Tuning) بدلاً من ذلك."
    ),
    "wet_gas": (
        "PVTG مع Rv ثابت تقريباً (لا تكثف في المكمن).\n"
        "Black-Oil/PVTG كافٍ في معظم الحالات."
    ),
    "dry_gas": (
        "PVDG (بدون Rv).\n"
        "Black-Oil/PVDG كافٍ."
    ),
}

EXPORT_SIM_ALIASES = {
    "black oil": "black_oil", "black_oil": "black_oil", "heavy oil": "black_oil",
    "volatile oil": "volatile_oil", "volatile_oil": "volatile_oil",
    "gas condensate": "gas_condensate", "condensate": "gas_condensate", "gas_condensate": "gas_condensate",
    "wet gas": "wet_gas", "wet_gas": "wet_gas",
    "dry gas": "dry_gas", "dry_gas": "dry_gas",
}


def export_sim_decision(fluid_type: str, near_critical: bool = False) -> str:
    key = EXPORT_SIM_ALIASES.get(fluid_type.lower().strip())
    if not key:
        return (
            "نوع السائل غير محدد. الأنواع المتاحة:\n"
            "black oil, volatile oil, gas condensate, wet gas, dry gas\n\n"
            "Usage: /export_sim <fluid_type> [near_critical]\n"
            "Example: /export_sim gas condensate near_critical"
        )

    base = EXPORT_SIM_DECISIONS[key]
    if near_critical and key in ("volatile_oil", "gas_condensate"):
        base += (
            "\n\nتحذير: السائل قريب من النقطة الحرجة. نماذج Black-Oil "
            "تفترض تركيباً ثابتاً للطورين، وهو افتراض ضعيف هنا. "
            "النموذج التركيبي (Compositional/EOS) هو الخيار الموصى به."
        )
    return base


# ─────────────────────────────────────────────
#  TEXT CLEANER  -- fixes any wrong Arabic terms that slip through
# ─────────────────────────────────────────────
def clean_text(text: str) -> str:
    text = str(text)
    fixes = {
        "**": "", "###": "", "##": "", "#": "", "|": " ", "[": "", "]": "",
        "Pressuring Volume and Temperature": "Pressure-Volume-Temperature",
        "الضغط البيني":         "معامل حجم التكوين",
        "المعامل البيني":       "معامل حجم التكوين",
        "الترشيح":              "نسبة الغاز المذاب",
        "النسبة المئوية للغاز": "نسبة الغاز الى الزيت",
        "نسبة الغاز المئوية":   "نسبة الغاز الى الزيت",
        "الويسكوزية":           "اللزوجة",
        "الليزج":               "اللزوجة",
        "الحفرة":               "المكمن",
        "السطوح النوعي":        "الكثافة النوعية",
        "اختبار السطوح":        "اختبار الكثافة النوعية",
        "السطوع النوعي":        "الكثافة النوعية",
    }
    for wrong, right in fixes.items():
        text = text.replace(wrong, right)
    return text.strip()


# ─────────────────────────────────────────────
#  MESSAGING HELPERS
# ─────────────────────────────────────────────
def send_message(chat_id: int, text: str) -> None:
    text = clean_text(text)
    if not text:
        text = "لم أتمكن من توليد رد واضح."
    for i in range(0, len(text), 3900):
        try:
            requests.post(
                f"{TELEGRAM_URL}/sendMessage",
                json={"chat_id": chat_id, "text": text[i:i+3900]},
                timeout=15
            )
        except Exception as e:
            print(f"send_message error: {e}")
        time.sleep(0.4)


def send_document(chat_id: int, file_bytes: bytes, filename: str, caption: str,
                   mime: str = "text/html") -> None:
    try:
        requests.post(
            f"{TELEGRAM_URL}/sendDocument",
            data={"chat_id": chat_id, "caption": caption},
            files={"document": (filename, file_bytes, mime)},
            timeout=20
        )
    except Exception as e:
        send_message(chat_id, f"خطأ في إرسال الملف: {e}")


def download_file(file_id: str, suffix: str = ".bin"):
    try:
        info = requests.get(f"{TELEGRAM_URL}/getFile", params={"file_id": file_id}, timeout=15).json()
        if not info.get("ok"):
            return None
        url  = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{info['result']['file_path']}"
        data = requests.get(url, timeout=60).content
        tmp  = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        tmp.write(data); tmp.close()
        return tmp.name
    except Exception as e:
        print(f"download_file error: {e}")
        return None


def extract_pdf_text(path: str) -> str:
    try:
        reader = PdfReader(path)
        return "\n\n".join(p.extract_text() for p in reader.pages if p.extract_text()).strip()
    except Exception as e:
        print(f"PDF error: {e}"); return ""


def extract_docx_text(path: str) -> str:
    try:
        doc = Document(path)
        return "\n".join(p.text.strip() for p in doc.paragraphs if p.text.strip())
    except Exception as e:
        print(f"DOCX error: {e}"); return ""


def encode_image(path: str) -> str:
    mime, _ = mimetypes.guess_type(path)
    if not mime: mime = "image/jpeg"
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return f"data:{mime};base64,{b64}"


# ─────────────────────────────────────────────
#  PDF SECTION SEGMENTATION  (for PVT report structure awareness)
# ─────────────────────────────────────────────
PVT_SECTION_HEADERS = [
    "Differential Liberation", "Differential Vaporization",
    "Constant Composition Expansion", "CCE",
    "Constant Volume Depletion", "CVD",
    "Separator Test", "Compositional Analysis",
    "Viscosity", "Recombination", "Reservoir Fluid Properties",
    "Sample Information", "PVT Summary",
]


def segment_pdf_text(text: str) -> dict:
    sections = {}
    current_header = "PREAMBLE"
    current_lines = []
    for line in text.split("\n"):
        matched_header = None
        for header in PVT_SECTION_HEADERS:
            if header.lower() in line.lower() and len(line.strip()) < 60:
                matched_header = header
                break
        if matched_header:
            if current_lines:
                sections[current_header] = "\n".join(current_lines)
            current_header = matched_header
            current_lines = []
        else:
            current_lines.append(line)
    if current_lines:
        sections[current_header] = "\n".join(current_lines)
    return sections


def format_segmented_context(sections: dict) -> str:
    parts = []
    for header, content in sections.items():
        stripped = content.strip()
        if stripped:
            parts.append(f"=== SECTION: {header} ===\n{stripped}\n")
    return "\n".join(parts)


MAX_CONTEXT_CHARS = 20000


def store_file_context(chat_id: int, text: str, filename: str) -> str:
    original_len = len(text)
    if original_len > MAX_CONTEXT_CHARS:
        text = text[:MAX_CONTEXT_CHARS]
        FILE_CONTEXT[chat_id] = text
        return (
            f"تم قراءة الملف \'{filename}\' بنجاح.\n"
            f"تحذير: الملف يحتوي على {original_len:,} حرف، تم استخدام أول "
            f"{MAX_CONTEXT_CHARS:,} حرف فقط كمرجع لهذه المحادثة. "
            f"إذا كانت المعلومات المهمة في أجزاء لاحقة، قسّم الملف وأرسل "
            f"الجزء المطلوب بشكل منفصل."
        )
    FILE_CONTEXT[chat_id] = text
    return f"تم قراءة الملف \'{filename}\' بنجاح ({original_len:,} حرف). أصبح مرجعاً لهذه المحادثة."


# ─────────────────────────────────────────────
#  AI CALLS  (with retry/backoff + differentiated errors)
# ─────────────────────────────────────────────
def ask_ai(user_text: str, file_context=None, max_retries: int = 2) -> str:
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            messages = [{"role": "system", "content": SYSTEM_PROMPT}]
            if file_context:
                messages.append({
                    "role": "user",
                    "content": "Reference document context (PVT report, segmented):\n\n" + file_context[:20000]
                })
            messages.append({"role": "user", "content": user_text})

            r = requests.post(
                GROQ_URL,
                headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
                json={"model": TEXT_MODEL, "messages": messages, "temperature": 0.08, "max_tokens": 3000},
                timeout=90
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

    error_messages = {
        "rate_limit": "النظام مشغول حالياً (rate limit). حاول مرة أخرى بعد لحظات.",
        "service_unavailable": "خدمة الذكاء الاصطناعي غير متاحة مؤقتاً. حاول بعد قليل.",
        "timeout": "انتهت مهلة الاتصال. حاول مرة أخرى أو قسّم السؤال إلى أجزاء أصغر.",
        "connection_error": "تعذر الاتصال بخدمة الذكاء الاصطناعي. تحقق من الشبكة.",
    }
    return error_messages.get(last_error, f"حدث خطأ غير متوقع: {last_error}")


def ask_vision_ai(prompt: str, image_path: str, file_context=None, max_retries: int = 2) -> str:
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            full_prompt = prompt
            if file_context:
                full_prompt += "\n\nReference context:\n" + file_context[:10000]

            messages = [{"role": "user", "content": [
                {"type": "text", "text": full_prompt},
                {"type": "image_url", "image_url": {"url": encode_image(image_path)}}
            ]}]

            r = requests.post(
                GROQ_URL,
                headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
                json={"model": VISION_MODEL, "messages": messages, "temperature": 0.08, "max_tokens": 2200},
                timeout=90
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

    error_messages = {
        "rate_limit": "النظام مشغول حالياً (rate limit). حاول مرة أخرى بعد لحظات.",
        "service_unavailable": "خدمة تحليل الصور غير متاحة مؤقتاً. حاول بعد قليل.",
        "timeout": "انتهت مهلة تحليل الصورة. حاول مرة أخرى.",
        "connection_error": "تعذر الاتصال بخدمة تحليل الصور.",
    }
    return error_messages.get(last_error, f"حدث خطأ في تحليل الصورة: {last_error}")


# ─────────────────────────────────────────────
#  GRAPH INTERPRETATION PROMPT  (/graph, /interpret_graph)
# ─────────────────────────────────────────────
def build_graph_interpretation_prompt(user_text: str) -> str:
    reference_summary = "\n".join(
        f"- {r['title_en']} ({r['title_ar']}): {r['shape']} | Pivot: {r['pivot']}"
        for r in PVT_PLOT_RULES.values()
    )
    return (
        SYSTEM_PROMPT +
        "\n\nTASK: Analyze the uploaded PVT engineering plot/image.\n\n"
        "REFERENCE SHAPES (ground truth -- compare the image against these):\n"
        + reference_summary +
        "\n\nSTEPS:\n"
        "1. Identify X-axis and Y-axis labels, units, and scale (linear/log).\n"
        "2. Match the plot to ONE of the reference relationships above based "
        "on axis labels and curve shape.\n"
        "3. State which relationship it matches and whether the observed "
        "shape agrees with the reference shape (pivot location, direction "
        "changes).\n"
        "4. If it MATCHES: identify the saturation pressure (Pb or Pd) "
        "location on the curve based on the pivot rule for that relationship.\n"
        "5. If it DOES NOT MATCH (non-physical curve): explicitly say so, "
        "explain which part of the curve is wrong, and suggest likely causes "
        "(data entry error, mislabeled axis, contamination, separator vs "
        "reservoir confusion, truncated dataset).\n"
        "6. Give a concise engineering interpretation and recommendation.\n\n"
        f"User's additional context/question: {user_text}\n\n"
        "Follow BLOCK 13 formatting rules (no markdown, clear headings)."
    )


# ─────────────────────────────────────────────
#  FILE / PHOTO UPLOAD HANDLERS
# ─────────────────────────────────────────────
def handle_document_upload(chat_id, doc):
    file_id   = doc["file_id"]
    file_name = doc.get("file_name", "file")
    mime      = doc.get("mime_type", "")
    ext       = os.path.splitext(file_name)[1].lower() or ".bin"
    path      = download_file(file_id, ext)
    if not path:
        send_message(chat_id, "حدث خطأ أثناء تحميل الملف."); return

    lower = file_name.lower()
    if lower.endswith(".pdf"):
        text = extract_pdf_text(path)
        if not text:
            send_message(chat_id, "قرأت PDF لكن لم أستخرج نصاً. الملف غالباً سكاني (صور). "
                                   "أرسل صفحاته كصور أو ارفع PDF نصياً.")
            return
        sections = segment_pdf_text(text)
        formatted = format_segmented_context(sections)
        status_msg = store_file_context(chat_id, formatted, file_name)
        send_message(chat_id, status_msg + "\nاكتب /analyze لتحليله هندسياً.")

    elif lower.endswith(".docx"):
        text = extract_docx_text(path)
        if not text:
            send_message(chat_id, "قرأت DOCX لكن لم أجد نصاً."); return
        status_msg = store_file_context(chat_id, text, file_name)
        send_message(chat_id, status_msg + "\nاكتب /analyze للتحليل.")

    elif mime.startswith("image/") or lower.endswith((".png", ".jpg", ".jpeg", ".webp")):
        IMAGE_CONTEXT[chat_id] = path
        send_message(chat_id, "تم استلام الصورة. اكتب /graph لتحليل الرسم هندسياً.")

    else:
        send_message(chat_id, "الملف المدعوم: PDF أو DOCX أو صورة (PNG/JPG/JPEG/WEBP).")


def handle_photo_upload(chat_id, photos):
    path = download_file(photos[-1]["file_id"], ".jpg")
    if path:
        IMAGE_CONTEXT[chat_id] = path
        send_message(chat_id, "تم استلام الصورة. اكتب /graph لتحليل الرسم هندسياً.")
    else:
        send_message(chat_id, "خطأ في تحميل الصورة.")


# ─────────────────────────────────────────────
#  GLOSSARY HTML GENERATOR  (/glossary -- built dynamically from KNOWLEDGE_BASE)
# ─────────────────────────────────────────────
import json as _json


def generate_glossary_html() -> bytes:
    """Builds the interactive HTML glossary from KNOWLEDGE_BASE + PVT_PLOT_RULES,
    so terminology can never drift from the SYSTEM_PROMPT dictionary."""

    category_class = {
        "PVT": "b-pvt", "Reservoir": "b-res", "Production": "b-pro",
        "Drilling": "b-drl", "Economics": "b-eco",
        "PVT - Gas Condensate": "b-pvt", "Production - Gas Condensate": "b-pro",
        "Phase Behavior": "b-pvt",
    }
    category_label = {
        "PVT": "PVT", "Reservoir": "المكمن", "Production": "الإنتاج",
        "Drilling": "الحفر", "Economics": "الاقتصاد",
        "PVT - Gas Condensate": "غاز مكثف", "Production - Gas Condensate": "غاز مكثف",
        "Phase Behavior": "السلوك الطوري",
    }

    # Build term cards as a list of dicts: {ar, en, badge_class, badge_label, def, extra}
    term_records = []
    for t in KNOWLEDGE_BASE:
        cls = category_class.get(t["category"], "b-pvt")
        lbl = category_label.get(t["category"], t["category"])
        extra_parts = []
        if t.get("typical_range") and t["typical_range"] != "n/a":
            extra_parts.append("المدى النموذجي: " + t["typical_range"] + " (" + t["unit"] + ")")
        trend = t.get("trend", "")
        if trend and "n/a" not in trend and "static" not in trend and "indicator" not in trend and "event" not in trend:
            extra_parts.append("الاتجاه: " + trend)
        term_records.append({
            "ar": t["ar"], "en": t["en"], "cls": cls, "lbl": lbl,
            "def": t["def_ar"], "extra": extra_parts,
            "search": (t["en"] + " " + t["ar"] + " " + t["def_ar"]).lower(),
        })

    # Build plot records
    plot_records = []
    for key, rule in PVT_PLOT_RULES.items():
        rows = []
        if rule["above_saturation"] != "n/a":
            rows.append("فوق ضغط التشبع: " + rule["above_saturation"])
        if rule["at_saturation"] != "n/a":
            rows.append("عند ضغط التشبع: " + rule["at_saturation"])
        if rule["below_saturation"] != "n/a":
            rows.append("تحت ضغط التشبع: " + rule["below_saturation"])
        plot_records.append({
            "title_ar": rule["title_ar"], "title_en": rule["title_en"],
            "x_axis": rule["x_axis"], "y_axis": rule["y_axis"],
            "shape": rule["shape"], "rows": rows, "pivot": rule["pivot"],
            "sketch": ASCII_SKETCHES.get(key, ""),
        })

    # Serialize to JSON for safe embedding in <script>
    term_json = _json.dumps(term_records, ensure_ascii=False)
    plot_json = _json.dumps(plot_records, ensure_ascii=False)

    css = """
@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@300;400;600;700;900&family=Fira+Code:wght@400;600&display=swap');
:root{--crude:#3d1f00;--amber:#c8760a;--gold:#e8a020;--light:#fef3dc;--surface:#f5f0e8;--paper:#fdfaf4;--border:#ddd0b8;--muted:#7a6a58;--dbg:#0d1117}
*{box-sizing:border-box;margin:0;padding:0}body{font-family:'Cairo',sans-serif;background:var(--surface);color:#111;line-height:1.7}
header{background:var(--crude);color:var(--paper);padding:2.5rem 2rem 2rem;text-align:center}
header h1{font-size:clamp(1.6rem,4vw,2.5rem);font-weight:900}header h1 span{color:var(--gold)}
header p{margin-top:.4rem;font-size:.95rem;opacity:.65}
nav{display:flex;justify-content:center;gap:.5rem;flex-wrap:wrap;padding:1.2rem 1rem;background:var(--paper);border-bottom:2px solid var(--border);position:sticky;top:0;z-index:100;box-shadow:0 2px 10px rgba(0,0,0,.07)}
nav button{padding:.45rem 1.1rem;border:2px solid var(--border);border-radius:999px;background:transparent;font-family:inherit;font-size:.82rem;font-weight:600;color:var(--muted);cursor:pointer}
nav button.active{background:var(--amber);border-color:var(--amber);color:#fff}
main{max-width:1080px;margin:0 auto;padding:2rem 1.5rem 4rem}.sec{display:none}.sec.active{display:block}
.search input{width:100%;padding:.7rem 1.2rem;border:2px solid var(--border);border-radius:8px;font-family:inherit;font-size:1rem;background:var(--paper);margin-bottom:1.5rem}
.grid{display:grid;gap:1rem}.card{background:var(--paper);border:1.5px solid var(--border);border-radius:10px;overflow:hidden}
.card-head{display:flex;align-items:center;gap:.8rem;padding:.9rem 1.3rem;cursor:pointer;flex-wrap:wrap}
.ar{font-size:1rem;font-weight:700;color:var(--crude);flex:1}
.en{font-family:'Fira Code',monospace;font-size:.82rem;font-weight:600;color:var(--amber);background:var(--light);padding:.2rem .6rem;border-radius:5px;direction:ltr;white-space:nowrap}
.badge{font-size:.68rem;padding:.18rem .55rem;border-radius:999px;font-weight:700;white-space:nowrap}
.b-res{background:#dbeafe;color:#1e40af}.b-pvt{background:#fef9c3;color:#854d0e}.b-pro{background:#dcfce7;color:#166534}.b-drl{background:#ffe4e6;color:#9f1239}.b-eco{background:#e0f2fe;color:#0369a1}
.card-body{display:none;padding:0 1.3rem 1.2rem;border-top:1px solid var(--border)}.card-body.open{display:block}
.def{margin-top:.9rem;font-size:.95rem;color:#333;line-height:1.85}
.meta{margin-top:.4rem;font-size:.8rem;color:var(--muted)}
.ftitle{font-size:1.3rem;font-weight:900;color:var(--crude);margin-bottom:1.2rem;padding-bottom:.4rem;border-bottom:3px solid var(--amber)}
.pcard{background:var(--dbg);border-radius:10px;overflow:hidden;margin-bottom:1.2rem;border:1px solid #2a3040}
.pcard-head{display:flex;justify-content:space-between;align-items:center;padding:.8rem 1.3rem;background:rgba(200,118,10,.11);border-bottom:1px solid #2a3040;flex-wrap:wrap}
.p-en{font-family:'Fira Code',monospace;color:var(--gold);font-size:.85rem;direction:ltr}
.p-ar{color:rgba(255,255,255,.85);font-size:.9rem;font-weight:600}
.pcard-body{padding:1.1rem 1.3rem;color:rgba(255,255,255,.75);font-size:.85rem}
.axes{color:var(--gold);font-family:'Fira Code',monospace;font-size:.78rem;margin-bottom:.5rem}
.shape{margin-bottom:.5rem;font-style:italic}
.prow{margin:.3rem 0}
.pivot{margin:.5rem 0;color:var(--gold);font-weight:600}
.sketch{font-family:'Fira Code',monospace;font-size:.7rem;color:#9be9a8;background:#000;padding:.8rem;border-radius:6px;overflow-x:auto;direction:ltr;text-align:left;line-height:1.3}
.nr{text-align:center;padding:3rem;color:var(--muted)}
"""

    js = """
function renderTerms(list){
  document.getElementById("tgrid").innerHTML = list.map(function(t, i){
    var extra = (t.extra || []).map(function(e){return '<div class="meta">' + e + '</div>';}).join("");
    return '<div class="card"><div class="card-head" onclick="tog(' + i + ')">' +
           '<span class="ar">' + t.ar + '</span><span class="en">' + t.en + '</span>' +
           '<span class="badge ' + t.cls + '">' + t.lbl + '</span></div>' +
           '<div class="card-body" id="b' + i + '"><p class="def">' + t.def + '</p>' + extra + '</div></div>';
  }).join("");
}
function tog(i){ document.getElementById("b"+i).classList.toggle("open"); }
function filterTerms(){
  var q = document.getElementById("q").value.toLowerCase();
  var f = q ? TERMS.filter(function(t){ return t.search.indexOf(q) !== -1; }) : TERMS;
  renderTerms(f);
  document.getElementById("nr").style.display = f.length ? "none" : "block";
}
function renderPlots(){
  document.getElementById("pgrid").innerHTML = PLOTS.map(function(p){
    var rows = (p.rows || []).map(function(r){return '<div class="prow">' + r + '</div>';}).join("");
    return '<div class="pcard"><div class="pcard-head">' +
           '<span class="p-ar">' + p.title_ar + '</span><span class="p-en">' + p.title_en + '</span>' +
           '</div><div class="pcard-body">' +
           '<div class="axes">X: ' + p.x_axis + ' | Y: ' + p.y_axis + '</div>' +
           '<div class="shape">' + p.shape + '</div>' + rows +
           '<div class="pivot">Pivot: ' + p.pivot + '</div>' +
           '<pre class="sketch">' + p.sketch + '</pre></div></div>';
  }).join("");
}
function show(id, btn){
  document.querySelectorAll(".sec").forEach(function(s){ s.classList.remove("active"); });
  document.querySelectorAll("nav button").forEach(function(b){ b.classList.remove("active"); });
  document.getElementById(id).classList.add("active");
  btn.classList.add("active");
}
renderTerms(TERMS);
renderPlots();
"""

    html_parts = []
    html_parts.append("<!DOCTYPE html>")
    html_parts.append('<html lang="ar" dir="rtl">')
    html_parts.append("<head>")
    html_parts.append('<meta charset="UTF-8">')
    html_parts.append('<meta name="viewport" content="width=device-width,initial-scale=1.0">')
    html_parts.append("<title>المصطلحات النفطية -- Petroleum Engineering Glossary</title>")
    html_parts.append("<style>" + css + "</style>")
    html_parts.append("</head><body>")
    html_parts.append(
        '<header><h1>المصطلحات <span>النفطية</span> الشاملة<br>'
        '<small style="font-size:.52em;font-weight:300;opacity:.65">'
        "Petroleum Engineering Glossary -- PVT / Reservoir / Drilling / Production</small></h1>"
        "<p>تعريفات علمية - اتجاهات PVT - رسوم بيانية مرجعية</p></header>"
    )
    html_parts.append(
        '<nav><button class="active" onclick="show(\'terms\',this)">المصطلحات</button>'
        '<button onclick="show(\'plots\',this)">علاقات PVT والرسوم</button></nav>'
    )
    html_parts.append("<main>")
    html_parts.append(
        '<div id="terms" class="sec active"><div class="search">'
        '<input id="q" placeholder="ابحث عن مصطلح..." oninput="filterTerms()"/></div>'
        '<div class="grid" id="tgrid"></div>'
        '<div class="nr" id="nr" style="display:none">لا توجد نتائج</div></div>'
    )
    html_parts.append(
        '<div id="plots" class="sec"><p class="ftitle">'
        "علاقات PVT مقابل الضغط -- الشكل الصحيح فيزيائياً</p>"
        '<div id="pgrid"></div></div>'
    )
    html_parts.append("</main>")
    html_parts.append("<script>")
    html_parts.append("const TERMS = " + term_json + ";")
    html_parts.append("const PLOTS = " + plot_json + ";")
    html_parts.append(js)
    html_parts.append("</script>")
    html_parts.append("</body></html>")

    html = "\n".join(html_parts)
    return html.encode("utf-8")


# ─────────────────────────────────────────────
#  COMMAND DETECTORS
# ─────────────────────────────────────────────
def is_graph_cmd(t):   return t.lower().startswith(("/graph", "/interpret_graph"))
def is_analyze_cmd(t): return t.lower().startswith("/analyze")
def is_calc_cmd(t):    return t.lower().startswith("/calc")
def is_estimate_cmd(t):return t.lower().startswith("/estimate")
def is_convert_cmd(t): return t.lower().startswith("/convert")
def is_classify_cmd(t):return t.lower().startswith("/classify")
def is_plot_cmd(t):    return t.lower().startswith("/plot")
def is_check_cmd(t):   return t.lower().startswith("/check")
def is_pvto_cmd(t):    return t.lower().strip() == "/pvto"
def is_pvtg_cmd(t):    return t.lower().strip() == "/pvtg"
def is_export_sim_cmd(t): return t.lower().startswith("/export_sim")
def is_eclipse_cmd(t): return t.lower().startswith("/eclipse")
def is_cmg_cmd(t):     return t.lower().startswith("/cmg")
def is_reset_cmd(t):   return t.lower().strip() == "/reset"


def is_surface_separator(t):
    t = t.lower()
    oil = any(k in t for k in ["surface separator oil", "separator oil", "زيت من الفاصل", "عينة زيت"])
    gas = any(k in t for k in ["separator gas", "غاز من الفاصل", "عينة غاز"])
    return oil and gas


# ─────────────────────────────────────────────
#  STATIC RESPONSES
# ─────────────────────────────────────────────
def start_message() -> str:
    return (
        "أهلاً بك في Petroleum Engineering AI Bot\n\n"
        "مساعد هندسي متخصص في:\n"
        "- PVT Laboratory و Reservoir Fluid Analysis\n"
        "- Reservoir Engineering و Simulation (Eclipse / CMG)\n"
        "- Drilling Engineering\n"
        "- Production Engineering\n\n"
        "=== أوامر حتمية (دقيقة 100%، بدون ذكاء اصطناعي) ===\n"
        "/classify gor=<value> api=<value>\n"
        "    تصنيف نوع السائل (Black Oil / Volatile Oil / Gas Condensate ...)\n\n"
        "/calc <type> key=value ...\n"
        "    حسابات بمعادلات مضبوطة. الأنواع:\n"
        "    api, hydrostatic, ooip, darcy, recovery_factor, water_cut, productivity_index\n"
        "    مثال: /calc api sg=0.85\n"
        "    مثال: /calc hydrostatic mw=10 tvd=5000\n\n"
        "/estimate <type> key=value ...\n"
        "    تقديرات بمعادلات تجريبية (Standing). الأنواع: pb_standing, rs_standing\n"
        "    مثال: /estimate pb_standing rs=650 gas_sg=0.75 tres=180 api=35\n\n"
        "/convert <value> <from_unit> to <to_unit>\n"
        "    مثال: /convert 5000 psi to bar\n\n"
        "/plot <relationship>\n"
        "    شرح + رسم ASCII للعلاقة. الخيارات:\n"
        "    bo, rs, viscosity, density, vrel/cce, bg, z, gas viscosity, "
        "dropout/cvd, cgr, phase envelope/pt\n\n"
        "/check <relationship> p=p1,p2,... v=v1,v2,... pb=<value>\n"
        "    فحص بيانات PVT مقابل السلوك الفيزيائي الصحيح\n"
        "    مثال: /check rs p=500,1000,1500,2000 v=300,300,250,180 pb=1500\n\n"
        "/pvto  -- هيكل جدول PVTO لـ Eclipse\n"
        "/pvtg  -- هيكل جدول PVTG لـ Eclipse\n"
        "/export_sim <fluid_type> [near_critical]\n"
        "    مثال: /export_sim gas condensate near_critical\n\n"
        "=== أوامر بمساعدة الذكاء الاصطناعي ===\n"
        "/glossary   -- المصطلحات الشاملة (HTML تفاعلي)\n"
        "/analyze    -- تحليل تقرير PDF/DOCX مرفوع\n"
        "/graph      -- تحليل رسم بياني أو صورة هندسية مرفوعة\n"
        "/eclipse    -- إرشادات Eclipse\n"
        "/cmg        -- إرشادات CMG\n\n"
        "/reset -- مسح الملفات والصور المحفوظة لهذه المحادثة\n\n"
        "يمكنك أيضاً كتابة سؤالك مباشرة بالعربي أو الإنجليزي."
    )


def surface_separator_answer() -> str:
    return (
        "تحليل هندسي -- عينة زيت من الفاصل السطحي مع عينة غاز\n\n"
        "نوع العينات\n"
        "هذه عينات سطحية منفصلة وليست سائل مكمن مباشراً مثل Bottom Hole Sample.\n"
        "الزيت والغاز انفصلا عند ظروف الفاصل السطحي، لذلك يلزم Recombination أولاً.\n\n"
        "البيانات المطلوبة\n"
        "- Separator Pressure و Temperature\n"
        "- Oil Rate و Gas Rate\n"
        "- Producing GOR أو Separator GOR\n"
        "- Gas Composition و Oil/Stock Tank Oil Composition\n"
        "- API Gravity و Gas Specific Gravity\n"
        "- Water Cut و وجود H2S/CO2\n\n"
        "الاختبارات المطلوبة\n"
        "1. Sample QC -- فحص سلامة العينات\n"
        "2. Compositional Analysis -- تحليل تركيبي كامل\n"
        "3. Recombination -- إعادة بناء سائل المكمن\n"
        "4. Validation -- التحقق من تمثيلية العينة المعاد تركيبها\n"
        "5. CCE/CME -- لتحديد Saturation Pressure (عبر كسر منحنى Vrel)\n"
        "6. DV للزيت أو CVD للغاز المكثف\n"
        "7. Separator Test و Viscosity Test\n\n"
        "الرسومات المطلوبة (استخدم /plot لكل منها)\n"
        "- Pressure vs Bo\n"
        "- Pressure vs Rs\n"
        "- Pressure vs Oil Viscosity\n"
        "- Pressure vs Relative Volume (CCE)\n"
        "- للغاز المكثف: Pressure vs Liquid Dropout (CVD)\n\n"
        "إعداد المحاكاة\n"
        "Black Oil/Volatile Oil: PVTO في Eclipse (Rs، Bo، Viscosity عند كل ضغط)\n"
        "Gas Condensate/Volatile Oil قريب من الحرج: Compositional Model مع EOS Tuning\n\n"
        "الخلاصة\n"
        "لا يمكن حساب Bo أو Rs أو Bubble Point بدون بيانات الفاصل والتركيب.\n"
        "أرسل البيانات وسأبدأ بالحسابات والفحوصات فوراً (/calc, /check)."
    )


# ─────────────────────────────────────────────
#  MAIN LOOP
# ─────────────────────────────────────────────
print("Petroleum Engineering AI Bot running...")

while True:
    try:
        updates = requests.get(
            f"{TELEGRAM_URL}/getUpdates",
            params={"offset": offset + 1, "timeout": 30},
            timeout=40
        ).json()

        for update in updates.get("result", []):
            offset = update["update_id"]
            msg = update.get("message")
            if not msg:
                continue

            chat_id = msg["chat"]["id"]

            if "document" in msg:
                handle_document_upload(chat_id, msg["document"]); continue
            if "photo" in msg:
                handle_photo_upload(chat_id, msg["photo"]); continue
            if "text" not in msg:
                send_message(chat_id, "أرسل نصاً أو ملف PDF/DOCX أو صورة."); continue

            text    = msg["text"].strip()
            context = FILE_CONTEXT.get(chat_id)

            # ── /start ──
            if text == "/start":
                send_message(chat_id, start_message()); continue

            # ── /reset ──
            if is_reset_cmd(text):
                FILE_CONTEXT.pop(chat_id, None)
                IMAGE_CONTEXT.pop(chat_id, None)
                send_message(chat_id, "تم مسح الملفات والصور المحفوظة لهذه المحادثة. ابدأ من جديد.")
                continue

            # ── /glossary ──
            if text == "/glossary":
                send_document(
                    chat_id, generate_glossary_html(), "petroleum_glossary.html",
                    "المصطلحات النفطية الشاملة\n\n"
                    "يحتوي الملف على:\n"
                    f"- {len(KNOWLEDGE_BASE)} مصطلحاً بتعريفات علمية واتجاهات PVT\n"
                    f"- {len(PVT_PLOT_RULES)} علاقة PVT مع رسوم ASCII مرجعية\n\n"
                    "افتح الملف في أي متصفح."
                )
                continue

            # ── /classify ──
            if is_classify_cmd(text):
                kwargs = parse_kv_args(text[len("/classify"):])
                if "gor" not in kwargs or "api" not in kwargs:
                    send_message(chat_id,
                        "Usage: /classify gor=<value> api=<value>\n"
                        "Example: /classify gor=3500 api=45")
                    continue
                send_message(chat_id, classify_fluid(kwargs["gor"], kwargs["api"]))
                continue

            # ── /calc ──
            if is_calc_cmd(text):
                parts = text.split(maxsplit=2)
                if len(parts) < 2:
                    send_message(chat_id,
                        "Usage: /calc <type> key=value key2=value2 ...\n"
                        "Types: api, hydrostatic, ooip, darcy, recovery_factor, "
                        "water_cut, productivity_index")
                    continue
                calc_type = parts[1].lower()
                kwargs = parse_kv_args(parts[2] if len(parts) > 2 else "")
                result = run_exact_calc(calc_type, **kwargs)
                send_message(chat_id, result or f"Unknown calculation type: {calc_type}")
                continue

            # ── /estimate ──
            if is_estimate_cmd(text):
                parts = text.split(maxsplit=2)
                if len(parts) < 2:
                    send_message(chat_id,
                        "Usage: /estimate <type> key=value key2=value2 ...\n"
                        "Types: pb_standing, rs_standing")
                    continue
                calc_type = parts[1].lower()
                kwargs = parse_kv_args(parts[2] if len(parts) > 2 else "")
                result = run_correlation(calc_type, **kwargs)
                send_message(chat_id, result or f"Unknown correlation type: {calc_type}")
                continue

            # ── /convert ──
            if is_convert_cmd(text):
                # Format: /convert <value> <from_unit> to <to_unit>
                m = re.match(r"/convert\s+([-+]?\d*\.?\d+)\s+(\S+)\s+to\s+(\S+)",
                              text, re.IGNORECASE)
                if not m:
                    send_message(chat_id,
                        "Usage: /convert <value> <from_unit> to <to_unit>\n"
                        "Example: /convert 5000 psi to bar")
                    continue
                value, from_u, to_u = float(m.group(1)), m.group(2), m.group(3)
                send_message(chat_id, run_unit_conversion(value, from_u, to_u))
                continue

            # ── /plot ──
            if is_plot_cmd(text):
                query = text[5:].strip().lower()
                if not query:
                    send_message(chat_id,
                        "Usage: /plot <relationship>\n\n"
                        "Available: bo, rs, viscosity, density, vrel (cce), bg, z, "
                        "gas viscosity, dropout (cvd), cgr, phase envelope (pt)")
                    continue

                rel_key = PLOT_ALIASES.get(query)
                if not rel_key:
                    for alias, key in PLOT_ALIASES.items():
                        if alias in query:
                            rel_key = key
                            break

                if not rel_key:
                    send_message(chat_id,
                        f"لم أتعرف على العلاقة \'{query}\'. الخيارات المتاحة:\n"
                        "bo, rs, viscosity, density, vrel/cce, bg, z, gas viscosity, "
                        "dropout/cvd, cgr, phase envelope/pt")
                    continue

                base_response = format_plot_response(rel_key)
                send_message(chat_id, base_response)

                if context:
                    ai_followup = ask_ai(
                        f"The user asked about the PVT relationship \'{rel_key}\' and "
                        f"was already given the standard physical explanation and ASCII "
                        f"sketch. Now, using the uploaded document context, check if "
                        f"actual data for this relationship is present. If yes, "
                        f"interpret it (compare to the expected shape, identify the "
                        f"saturation pressure if visible). If the document does not "
                        f"contain this data, say so briefly in one line.",
                        context
                    )
                    send_message(chat_id, ai_followup)
                continue

            # ── /check ──
            if is_check_cmd(text):
                body = text[6:].strip()
                p_match = re.search(r"p=\[?([\d,\.\s]+)\]?", body)
                v_match = re.search(r"v=\[?([\d,\.\s]+)\]?", body)
                pb_match = re.search(r"pb=([\d\.]+)", body)
                rel_match = body.split()[0].lower() if body else None

                rel_key = PLOT_ALIASES.get(rel_match) if rel_match else None
                if not rel_key or not p_match or not v_match:
                    send_message(chat_id,
                        "Usage: /check <relationship> p=p1,p2,p3 v=v1,v2,v3 pb=<value>\n"
                        "Example: /check rs p=500,1000,1500,2000 v=300,300,250,180 pb=1500")
                    continue

                pressures = [float(x) for x in p_match.group(1).split(",")]
                values = [float(x) for x in v_match.group(1).split(",")]
                pb_or_pd = float(pb_match.group(1)) if pb_match else None

                send_message(chat_id, check_pvt_trend(rel_key, pressures, values, pb_or_pd))
                continue

            # ── /pvto ──
            if is_pvto_cmd(text):
                send_message(chat_id, generate_pvto_skeleton())
                if context:
                    followup = ask_ai(
                        "Using the uploaded document, check if Rs(P), Bo(P), and "
                        "mu_o(P) data from Differential Liberation are present. "
                        "If yes, summarize the values found per the PVTO structure. "
                        "If incomplete, state exactly what is missing.",
                        context
                    )
                    send_message(chat_id, followup)
                continue

            # ── /pvtg ──
            if is_pvtg_cmd(text):
                send_message(chat_id, generate_pvtg_skeleton())
                if context:
                    followup = ask_ai(
                        "Using the uploaded document, check if Bg(P), mu_g(P), and "
                        "Rv(P) data from CVD/compositional analysis are present. "
                        "If yes, summarize the values found per the PVTG structure. "
                        "If incomplete, state exactly what is missing, and state "
                        "whether PVDG (dry gas, no Rv) would be more appropriate.",
                        context
                    )
                    send_message(chat_id, followup)
                continue

            # ── /export_sim ──
            if is_export_sim_cmd(text):
                body = text[len("/export_sim"):].strip().lower()
                near_critical = "near_critical" in body or "near critical" in body
                body_clean = body.replace("near_critical", "").replace("near critical", "").strip()
                if not body_clean:
                    send_message(chat_id,
                        "Usage: /export_sim <fluid_type> [near_critical]\n"
                        "Fluid types: black oil, volatile oil, gas condensate, wet gas, dry gas\n"
                        "Example: /export_sim gas condensate near_critical")
                    continue
                send_message(chat_id, export_sim_decision(body_clean, near_critical))
                continue

            # ── /analyze ──
            if is_analyze_cmd(text):
                if not context:
                    send_message(chat_id, "لا يوجد ملف مرفوع. أرسل PDF أو DOCX أولاً.")
                    continue
                prompt = (
                    "قم بتحليل هذا التقرير الهندسي:\n"
                    "1. نوع العينة ونظام السائل (استخدم BLOCK 6 للتصنيف إن توفرت GOR/API)\n"
                    "2. الاختبارات المنفذة وجودتها (طابق مع BLOCK 7)\n"
                    "3. القيم الرئيسية (Pb/Pd، Bo، Rs، API، Viscosity، Bg، Z)\n"
                    "4. تحقق من اتساق الاتجاهات مع BLOCK 5 -- أي تناقض أذكره كـ "
                    "POSSIBLE DATA QUALITY ISSUE\n"
                    "5. توصيات للمحاكاة (PVTO/PVTG/Compositional حسب BLOCK 11)\n"
                    "6. الخلاصة الهندسية ونقاط البيانات الناقصة"
                )
                send_message(chat_id, ask_ai(prompt, context))
                continue

            # ── /graph or /interpret_graph ──
            if is_graph_cmd(text):
                img = IMAGE_CONTEXT.get(chat_id)
                if not img:
                    send_message(chat_id, "أرسل صورة الرسم أولاً ثم اكتب /graph.")
                    continue
                prompt = build_graph_interpretation_prompt(text)
                send_message(chat_id, ask_vision_ai(prompt, img, context))
                continue

            # ── /eclipse ──
            if is_eclipse_cmd(text):
                prompt = (
                    text + "\n\n"
                    "قدم إرشادات Eclipse منظمة حسب BLOCK 11:\n"
                    "- حدد جدول PVT المناسب (PVTO/PVDO/PVTG/PVDG) وسبب الاختيار\n"
                    "- الكلمات المفتاحية ذات الصلة\n"
                    "- تحقق من الوحدات والاتساق\n"
                    "- البيانات الناقصة إن وجدت"
                )
                send_message(chat_id, ask_ai(prompt, context))
                continue

            # ── /cmg ──
            if is_cmg_cmd(text):
                prompt = (
                    text + "\n\n"
                    "قدم إرشادات CMG منظمة:\n"
                    "- حدد ما إذا كان Black-Oil (IMEX) أو Compositional (GEM) "
                    "هو الأنسب حسب BLOCK 6 و BLOCK 11\n"
                    "- متطلبات البيانات لكل خيار\n"
                    "- البيانات الناقصة إن وجدت"
                )
                send_message(chat_id, ask_ai(prompt, context))
                continue

            # ── Surface separator shortcut ──
            if is_surface_separator(text):
                send_message(chat_id, surface_separator_answer())
                continue

            # ── Default: AI response ──
            send_message(chat_id, ask_ai(text, context))

    except Exception as e:
        print(f"Main loop error: {e}")

    time.sleep(1)
