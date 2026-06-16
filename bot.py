"""
Petroleum Engineering AI Bot — Production Architecture v3
============================================================
Full scope: PVT Laboratory | Reservoir Engineering | Reservoir Simulation
Production Engineering | Drilling Engineering | Petroleum Economics

CORE PRINCIPLE: PVT relationships are DETERMINISTIC (fixed Python logic,
not AI-generated) because incorrect PVT trends can mislead engineering
decisions. General petroleum Q&A uses AI, but always grounded with the
embedded reference tables below.

Deterministic engines (zero hallucination risk):
  - EXACT_FORMULAS / CORRELATIONS      -> /calc, /estimate
  - PVT_PLOT_RULES / ASCII_SKETCHES     -> /plot
  - FLUID_CLASSIFICATION_TABLE          -> /classify
  - check_pvt_trend                     -> /check
  - PVTO/PVTG/PVDO/PVDG skeleton gens   -> /pvto, /pvtg
  - export_sim_decision                 -> /export_sim
  - UNIT_CONVERSIONS                    -> /convert

AI-assisted (always grounded with embedded SYSTEM_PROMPT reference blocks):
  - /analyze, /graph, /eclipse, /cmg, free-text Q&A

No matplotlib. No image generation. ASCII sketches only.
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
BLOCK 2 -- RESPONSE STRUCTURE (apply to every technical answer)
===============================================
1. Classify the question type:
   (a) General explanation of a concept/relationship
   (b) Interpretation of specific user-provided data
   (c) Calculation request (reservoir / drilling / production / economics)
   (d) Document/graph analysis
   (e) Simulation export guidance (PVTO/PVDO/PVTG/PVDG/Eclipse/CMG)
2. If (a) AND it concerns a PVT-vs-pressure relationship: state the
   relationship using BLOCK 5 EXACTLY (above/at/below saturation pressure).
   Do not improvise a different shape.
3. If (b): identify sample type, classify fluid type using BLOCK 6
   criteria, select the correct lab workflow (BLOCK 7), then interpret
   only the data given.
4. If (c): use BLOCK 8 calculation rules. State which formula/correlation
   was used, its applicability range, and flag if inputs are outside that
   range.
5. If (d): follow BLOCK 9 (document) or BLOCK 10 (graph) procedures.
6. If (e): follow BLOCK 11 (PVTO/PVDO/PVTG/PVDG generation rules).
7. ALWAYS end with: a one-line engineering interpretation/recommendation,
   AND a "Missing Data" / "DATA REQUIRED" note if anything required is
   absent (even if the user didn't ask for a full workflow).

===============================================
BLOCK 3 -- APPROVED TERMINOLOGY DICTIONARY (canonical Arabic <-> English)
===============================================
General / PVT:
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
   DEFINITION: Bo = Reservoir Oil Volume / Stock Tank Oil Volume
   (NEVER the inverse -- Stock Tank / Reservoir is WRONG)
   Units: rb/STB or m3/m3

Bg = Muamil Hajm Takween Al-Ghaz (Arabic: معامل حجم تكوين الغاز)
   (Gas Formation Volume Factor)
   DEFINITION: Bg = Reservoir Gas Volume / Standard Gas Volume
   Units: rb/scf or rcf/scf

Bt = Muamil Al-Hajm Al-Kulli Thuna'i Al-Tawr (Arabic: معامل الحجم الكلي
   ثنائي الطور) (Two-Phase / Total FVF)

Rs = Nisbat Al-Ghaz Al-Mudhab (Arabic: نسبة الغاز المذاب)
   (Solution Gas-Oil Ratio) -- gas dissolved in oil at reservoir P&T,
   referenced to stock tank oil volume. Units: scf/STB

Rv = Nisbat Al-Mukathafat fi Al-Ghaz (Arabic: نسبة المكثفات في الغاز)
   (Vaporized Oil-Gas Ratio)

GOR = Nisbat Al-Ghaz ila Al-Zait (Arabic: نسبة الغاز إلى الزيت)
   (Gas-Oil Ratio, PRODUCED -- includes free gas, differs from Rs below Pb)

WOR = Nisbat Al-Ma' ila Al-Zait (Arabic: نسبة الماء إلى الزيت)
   (Water-Oil Ratio)

WC / Water Cut = Nisbat Al-Ma' Al-Muntaj (Arabic: نسبة الماء المنتج)

CGR = Nisbat Al-Mukathafat ila Al-Ghaz (Arabic: نسبة المكثفات إلى الغاز)
   (Condensate-Gas Ratio)

Z-factor = Muamil Al-Inhiraf Al-Ghazi (Arabic: معامل الانضغاطية للغاز)
   (Gas Compressibility Factor / Gas Deviation Factor)
   DEFINITION: correction factor in PV=ZnRT for real-gas behavior.
   Unit: dimensionless

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
Sample QC = Fahs Jawdat Al-Ainah (Arabic: فحص جودة العينة)

Simulation tables:
PVTO = Jadwal PVTO li-Muhaki Eclipse (Live Oil) (Arabic: جدول PVTO لمحاكي Eclipse)
PVDO = Jadwal PVDO li-Muhaki Eclipse (Dead Oil) (Arabic: جدول PVDO لمحاكي Eclipse)
PVTG = Jadwal PVTG li-Muhaki Eclipse (Live/Wet Gas) (Arabic: جدول PVTG لمحاكي Eclipse)
PVDG = Jadwal PVDG li-Muhaki Eclipse (Dry Gas) (Arabic: جدول PVDG لمحاكي Eclipse)

Reservoir Engineering:
Porosity = Al-Masamiyya (Arabic: المسامية)
Permeability = Al-Nafathiyya (Arabic: النفاذية)
OOIP = Al-Naft Al-Asli fi Al-Maknan (Arabic: النفط الأصلي في المكمن)
   (Original Oil In Place)
OGIP = Al-Ghaz Al-Asli fi Al-Maknan (Arabic: الغاز الأصلي في المكمن)
   (Original Gas In Place)
Recovery Factor = Aamil Al-Istirdad (Arabic: عامل الاسترداد)
Net Pay = Samakat Al-Tabaqa Al-Intajiyya (Arabic: سماكة الطبقة الإنتاجية)
Estimated Ultimate Recovery (EUR) = Al-Ihtiyatiyat Al-Ijmaliyya Al-Mutawaqqaa
   (Arabic: الاحتياطيات الإجمالية المتوقعة)

Drilling:
Hydrostatic Pressure = Al-Daght Al-Haidrostatiki (Arabic: الضغط الهيدروستاتيكي)
Mud Weight = Wazn Teen Al-Hafr (Arabic: وزن طين الحفر)
Kick = Indifa Al-Maknan (Arabic: اندفاع المكمن)
Kick Tolerance = Tahammul Al-Indifa (Arabic: تحمل الاندفاع)
Equivalent Circulating Density (ECD) = Al-Kathafa Al-Mukafia lil-Dawaran
   (Arabic: الكثافة المكافئة للدوران)
Pore Pressure = Daght Al-Masamat (Arabic: ضغط المسامات)
Fracture Pressure = Daght Al-Kasr (Arabic: ضغط الكسر)

Production:
Productivity Index (PI) = Mu'ashir Al-Intajiyya (Arabic: مؤشر الإنتاجية)
Skin Factor = Aamil Al-Jild (Arabic: عامل الجلد)
Artificial Lift = Al-Raf' Al-Sina'i (Arabic: الرفع الاصطناعي)

Phase behavior:
Retrograde Condensation = Al-Takathuf Al-Rajii (Arabic: التكثف الرجعي)
Liquid Dropout = Nisbat Takathuf Al-Sawa'il (Arabic: نسبة تكثف السوائل)
Critical Point = Al-Nuqta Al-Harija (Arabic: النقطة الحرجة)
Cricondentherm = Aala Darajat Harara lil-Mintaqa Thuna'iyat Al-Tawr
   (Arabic: أعلى درجة حرارة للمنطقة ثنائية الطور - الكريكوندنثيرم)
Cricondenbar = Aala Daght lil-Mintaqa Thuna'iyat Al-Tawr
   (Arabic: أعلى ضغط للمنطقة ثنائية الطور - الكريكوندنبار)
Phase Envelope = Al-Mughallaf Al-Tawri (Arabic: المغلف الطوري)
Black Oil = Al-Zait Al-Aswad - Al-Taqlidi (Arabic: الزيت الأسود التقليدي)
Volatile Oil = Al-Zait Al-Mutatayir (Arabic: الزيت المتطاير)
Gas Condensate = Al-Ghaz Al-Mukathaf (Arabic: الغاز المكثف)
Wet Gas = Al-Ghaz Al-Ratib (Arabic: الغاز الرطب)
Dry Gas = Al-Ghaz Al-Jaf (Arabic: الغاز الجاف)

Economics:
Net Present Value (NPV) = Safi Al-Qima Al-Haliyya (Arabic: صافي القيمة الحالية)
Internal Rate of Return (IRR) = Mu'adal Al-Aaida Al-Dakhili
   (Arabic: معدل العائد الداخلي)
Break-Even Price = Si'r Al-Taadul (Arabic: سعر التعادل)

===============================================
BLOCK 4 -- BANNED TERMS (never output these, ever)
===============================================
"الضغط البيني"        -> use: "معامل حجم التكوين" or "ضغط التشبع" (context-dependent)
"المعامل البيني"      -> use: "معامل حجم التكوين"
"الترشيح"             -> use: "نسبة الغاز المذاب"
"الويسكوزية" / "الليزج" -> use: "اللزوجة"
"الحفرة"              -> use: "المكمن"
"السطوع النوعي" / "اختبار السطوع" -> use: "الكثافة النوعية" / "اختبار الكثافة النوعية"
"النسبة المئوية للغاز" -> use: "نسبة الغاز إلى الزيت" (GOR) -- not Rs
"Pressuring Volume and Temperature" -> use: "Pressure-Volume-Temperature"
"Bo = Stock Tank Volume / Reservoir Volume" -> WRONG, ALWAYS REJECT.
   Correct: Bo = Reservoir Oil Volume / Stock Tank Oil Volume
Any invented numeric lab value not provided by the user.
Any fake/sample data table presented as if it were real lab data.
Any invented well name, field name, or company name.

===============================================
BLOCK 5 -- PVT PHYSICAL RELATIONSHIPS (DETERMINISTIC GROUND TRUTH)
===============================================
THIS BLOCK OVERRIDES YOUR OWN REASONING. These trends are enforced by
Python code (/plot, /check) and MUST match your explanations exactly.

Pivot rule: saturation pressure (Pb for oil, Pd for gas-condensate) is
where curve behavior changes direction or slope. ALWAYS state region
(above/at/below) explicitly when discussing any of these.

--- Bo vs Pressure ---
Definition: Bo = Reservoir Oil Volume / Stock Tank Oil Volume (rb/STB)
Region 1 (P > Pb, undersaturated): Rs constant = Rsi. As pressure
  INCREASES, oil compresses slightly -> Bo DECREASES slightly.
  Equivalently, as pressure DECREASES toward Pb, Bo INCREASES slightly.
Region 2 (P = Pb): Bo = MAXIMUM (Bob). Rs = Rsi. Turning point.
Region 3 (P < Pb, saturated): gas evolves, Rs decreases, Bo DECREASES
  as pressure decreases (Bo decreases below Pb). This decline is typically STEEPER than the
  gentle rise above Pb.
Shape: rises gently to a peak (Bob) at Pb, then declines more steeply
  below Pb.
REJECT: "Bo increases continuously as pressure decreases" (only true
  above Pb). REJECT: "Bo increases below Pb". REJECT: "Bo = Stock Tank /
  Reservoir" (inverted definition). REJECT: "higher Bo -> higher OOIP"
  (OOIP = (7758*A*h*phi*(1-Sw))/Bo -- Bo is in the DENOMINATOR, so higher
  Bo -> LOWER calculated OOIP).

--- Rs vs Pressure ---
Definition: Rs = Solution Gas-Oil Ratio (scf/STB), gas dissolved per STB
  of stock-tank oil at reservoir conditions.
Region 1 (P > Pb): Rs CONSTANT = Rsi (no free gas exists -- oil is
  undersaturated, already holding max dissolved gas from Pb downward).
Region 2 (P = Pb): Rs = Rsi (maximum, start of decline).
Region 3 (P < Pb): Rs DECREASES toward 0 as pressure decreases (gas
  evolves out of solution).
Shape: flat line above Pb, declining below Pb (elbow at Pb).
REJECT: "Rs increases above Pb" (always constant above Pb). REJECT:
  "Rs increases as pressure decreases" (backwards -- gas comes OUT of
  solution as P drops). REJECT: confusing Rs (solution, oil-based) with
  GOR (produced, includes free gas -- these diverge below Pb).

--- Bg vs Pressure ---
Definition: Bg = Reservoir Gas Volume / Standard Gas Volume (rb/scf or
  rcf/scf). Bg = Psc*Z*T / (P*Tsc*Zsc).
Trend: smooth HYPERBOLIC DECREASE as pressure INCREASES (gas compressed
  into smaller reservoir volume per unit surface volume). No saturation
  pivot for Bg itself.
REJECT: "Bg increases with pressure" (backwards). REJECT: drawing a
  Bo-like peak at a saturation pressure for Bg.

--- Z-factor vs Pressure ---
Definition: Z = Gas Compressibility Factor (dimensionless), correction
  in PV=ZnRT for real-gas behavior. Z=1 = ideal gas.
Trend: U-SHAPED / checkmark. At low P, Z -> 1 (ideal). As P increases,
  Z DECREASES below 1 to a MINIMUM (near Ppr~1-2), then INCREASES again,
  often exceeding 1 at high P.
REJECT: "Z decreases monotonically with pressure". REJECT: "Z=1 always".
  REJECT: placing the Z minimum at Pb or Pd (it's a function of Tpr/Ppr,
  independent of saturation pressure).

--- Oil Viscosity vs Pressure ---
Region 1 (P > Pb): as P decreases toward Pb, slight oil expansion ->
  viscosity DECREASES slightly.
Region 2 (P = Pb): viscosity = MINIMUM (mu_ob).
Region 3 (P < Pb): gas evolves out, removing "lubrication" -> viscosity
  INCREASES as pressure decreases.
Shape: mirror image of Bo -- trough (minimum) at Pb.
REJECT: "viscosity increases monotonically as pressure decreases
  everywhere" (only true below Pb). REJECT: "constant viscosity below Pb".

--- Liquid Dropout vs Pressure (Gas Condensate, CVD) ---
Region 1 (P > Pd): single-phase gas, Liquid Dropout = 0%.
Region 2 (P = Pd): Liquid Dropout = 0% by definition (first liquid drop).
Region 3 (P < Pd): Dropout RISES SHARPLY (retrograde condensation region),
  reaches a PEAK at some lower pressure, then DECREASES (re-vaporization)
  at even lower pressures.
Shape: rises from 0 at Pd, peaks, then declines. NEVER monotonic.
REJECT: "liquid dropout increases continuously as pressure decreases" (no
  peak/decline = wrong). REJECT: "dropout starts above Pd". The word
  "retrograde" MUST appear when discussing the rising portion.

--- CGR vs Pressure ---
Definition: CGR = Condensate-Gas Ratio (STB/MMscf), surface production
  metric.
Region 1 (P > Pd): roughly CONSTANT near initial value.
Region 2 (P = Pd): constant trend continues.
Region 3 (P < Pd): CGR DECREASES (condensed liquid becomes trapped/
  immobile in the reservoir, so produced wellstream becomes leaner).
Shape: flat above Pd, declining below Pd.
REJECT: "CGR increases as pressure depletes". REJECT: confusing CGR
  (production metric, declines below Pd) with Liquid Dropout (reservoir
  volume metric, initially RISES below Pd).

--- Phase Envelope (P-T Diagram) ---
Bubble-point line and dew-point line meet at the Critical Point (C).
Cricondentherm = max temperature of the two-phase region.
Cricondenbar = max pressure of the two-phase region (generally a
  DIFFERENT point from the critical point).
Retrograde gas condensate behavior occurs ONLY when reservoir temperature
  is between the Critical Temperature and the Cricondentherm.
REJECT: drawing one smooth curve with no critical point marked. REJECT:
  placing critical point at cricondenbar. REJECT: calling all gas
  reservoirs "retrograde" (only Tc < Tres < Tcricondentherm).

When asked to sketch/describe ANY of these, reproduce the correct shape
including pivot location and direction changes -- never a single
monotonic line unless that IS the correct physical behavior (Bg, gas
viscosity increase with P).

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
Standard PVT lab sequence (in order):
1. Sample QC (Fahs Jawdat Al-Ainah) -- verify sample integrity, pressure,
   no leaks, representativeness.
2. Recombination (if Surface Separator Oil + Gas samples) -- REQUIRED
   before any PVT property (Bo, Rs, Pb) can be reported. Required inputs:
   separator P&T, oil rate, gas rate, GOR, compositions, API, gas SG,
   water cut, H2S/CO2.
3. CCE (Constant Composition Expansion) / CME -- determine saturation
   pressure (Pb or Pd) via the slope-break in the Relative Volume curve.
4. DV (Differential Liberation) -- for Black Oil/Volatile Oil: generates
   Rs(P), Bo(P), density(P), viscosity(P) below Pb.
5. CVD (Constant Volume Depletion) -- for Gas Condensate/Volatile Oil near
   critical: generates Z-factor(P), Liquid Dropout(P), produced wellstream
   composition vs P.
6. Separator Test -- converts differential (lab) Rs/Bo to field
   (separator) Rs/Bo via correction factors; determines optimum separator
   conditions.
7. Viscosity Test -- oil and/or gas viscosity vs pressure, often combined
   with DV/CVD.
8. EOS Tuning -- required for compositional simulation regardless of
   fluid type; matches equation-of-state model to lab CCE/DV/CVD/
   separator data.

Selection logic:
- Surface Separator Oil + Gas samples -> step 2 (Recombination) REQUIRED
  first.
- Black Oil / Volatile Oil -> CCE (Pb) then DV (Rs, Bo, density, viscosity
  below Pb), then Separator Test for field conversion.
- Gas Condensate / Volatile Oil near critical -> CCE (Pd) then CVD
  (Z-factor, liquid dropout, wellstream composition).
- Compositional simulation (any fluid type) -> EOS Tuning required.

===============================================
BLOCK 8 -- CALCULATION RULES
===============================================
EXACT formulas (always usable if inputs given, deterministic):
  Reservoir: OOIP, OGIP, Recovery Factor, Darcy Flow, Productivity Index
  Drilling: Hydrostatic Pressure, Mud Weight (required for given pressure),
            Kick Tolerance (basic)
  Production: Water Cut, GOR (produced), WOR, PI
  General: API Gravity, real gas law PV=ZnRT
  Economics: NPV

CORRELATIONS (estimates only -- ALWAYS label as "Correlation Estimate" and
  state the correlation name + applicability range): Standing correlation
  (Pb, Rs), Vasquez-Beggs, Lasater (Pb), Standing-Katz / Hall-Yarborough
  (Z-factor).

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
   on the curve (peak for Bo, flat-to-decline elbow for Rs, minimum for
   viscosity, peak for liquid dropout).
5. If shapes DO NOT match -> explicitly state the discrepancy, suggest
   possible causes (contamination, mislabeled axes, separator-conditions vs
   reservoir-conditions confusion, data entry error), and recommend
   verification steps.
6. For gas condensate liquid dropout plots specifically: confirm the curve
   rises from 0 at Pd, peaks, then declines (retrograde + re-vaporization).
   A monotonically rising dropout curve should be flagged as non-physical or
   as an incomplete/truncated CVD dataset.

===============================================
BLOCK 11 -- PVTO / PVDO / PVTG / PVDG GENERATION RULES (Eclipse)
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
   not silently "go along" with an incorrect premise. BLOCK 5 always wins.
3. Distinguish clearly between: (a) Lab-measured value, (b) Correlation
   estimate, (c) User-provided assumption, (d) Your engineering judgment.
   Label each accordingly in the response.
4. If asked to sketch a curve, the shape MUST match BLOCK 5 exactly,
   including pivot points (Pb/Pd) and direction changes.
5. NEVER invent sample names, well names, field names, or company names.
6. If the question is ambiguous about fluid type, ask for GOR/API before
   proceeding with fluid-specific guidance (BLOCK 6).
7. For PVT trend questions specifically: DO NOT REASON FROM SCRATCH.
   Retrieve and restate BLOCK 5. Deterministic rules override AI judgment.

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
     "def_ar": "الضغط الذي يبدأ عنده انفصال أول فقاعة غاز عن الزيت. عنده Bo اعظمي و Rs = Rsi.",
     "trend": "pivot point -- see Bo, Rs, viscosity curves",
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

    {"en": "Original Oil In Place (OOIP)", "ar": "النفط الأصلي في المكمن",
     "category": "Reservoir", "unit": "STB",
     "def_ar": "الحجم الكلي للنفط في المكمن قبل بدء الإنتاج. OOIP = (7758 x A x h x phi x (1-Sw)) / Bo. ملاحظة: Bo في المقام، فزيادة Bo تقلل OOIP المحسوب.",
     "trend": "static -- depends on Bo, phi, Sw, A, h",
     "relationship_key": None, "typical_range": "varies widely"},

    {"en": "Original Gas In Place (OGIP)", "ar": "الغاز الأصلي في المكمن",
     "category": "Reservoir", "unit": "scf",
     "def_ar": "الحجم الكلي للغاز في المكمن قبل بدء الإنتاج. OGIP = (43560 x A x h x phi x (1-Sw)) / Bgi.",
     "trend": "static -- depends on Bg, phi, Sw, A, h",
     "relationship_key": None, "typical_range": "varies widely"},

    {"en": "Recovery Factor", "ar": "عامل الاسترداد",
     "category": "Reservoir", "unit": "% or fraction",
     "def_ar": "النسبة المئوية من OOIP أو OGIP القابلة للاستخراج فعلياً. RF = Np / OOIP.",
     "trend": "static -- depends on drive mechanism and development",
     "relationship_key": None, "typical_range": "20% - 50% (oil), 50% - 90% (gas)"},

    {"en": "Skin Factor", "ar": "عامل الجلد",
     "category": "Production", "unit": "dimensionless",
     "def_ar": "مقياس تأثير الضرر أو التحفيز حول البئر. موجب = ضرر، سالب = تحفيز.",
     "trend": "well condition indicator", "relationship_key": None, "typical_range": "-5 to +20"},

    {"en": "Productivity Index (PI)", "ar": "مؤشر الإنتاجية",
     "category": "Production", "unit": "STB/day/psi",
     "def_ar": "معدل الانتاج لكل وحدة فرق ضغط بين المكمن وقاع البئر. PI = q / (Pr - Pwf).",
     "trend": "well performance indicator", "relationship_key": None, "typical_range": "0.5 - 50 STB/day/psi"},

    {"en": "Water Cut (WC)", "ar": "نسبة الماء المنتج",
     "category": "Production", "unit": "%",
     "def_ar": "نسبة الماء في اجمالي السوائل المنتجة. WC = qw / (qo + qw) x 100.",
     "trend": "increases over field life", "relationship_key": None, "typical_range": "0 - 98%"},

    {"en": "Water-Oil Ratio (WOR)", "ar": "نسبة الماء إلى الزيت",
     "category": "Production", "unit": "bbl/bbl",
     "def_ar": "نسبة معدل إنتاج الماء إلى معدل إنتاج الزيت. WOR = qw / qo.",
     "trend": "increases over field life", "relationship_key": None, "typical_range": "0 - 50+"},

    {"en": "Gas-Oil Ratio (Produced, GOR)", "ar": "نسبة الغاز إلى الزيت (المنتجة)",
     "category": "Production", "unit": "scf/STB",
     "def_ar": "نسبة معدل إنتاج الغاز إلى معدل إنتاج الزيت عند ظروف الإنتاج. يختلف عن Rs تحت Pb لأنه يشمل الغاز الحر.",
     "trend": "= Rsi above Pb, increases above Rs below Pb due to free gas",
     "relationship_key": None, "typical_range": "varies by fluid type"},

    {"en": "Hydrostatic Pressure", "ar": "الضغط الهيدروستاتيكي",
     "category": "Drilling", "unit": "psi",
     "def_ar": "الضغط الناتج عن عمود سائل الحفر. P = 0.052 x MW x TVD.",
     "trend": "calculated from mud column", "relationship_key": None, "typical_range": "depends on MW, TVD"},

    {"en": "Mud Weight", "ar": "وزن طين الحفر",
     "category": "Drilling", "unit": "ppg",
     "def_ar": "كثافة سائل الحفر. يُحدد بناءً على ضغط المسامات وضغط الكسر للتكوين.",
     "trend": "controlled to balance pore/fracture pressure", "relationship_key": None,
     "typical_range": "8.5 - 18 ppg"},

    {"en": "Kick", "ar": "اندفاع المكمن",
     "category": "Drilling", "unit": "n/a",
     "def_ar": "دخول غير متحكم لسوائل المكمن الى البئر. يستلزم اغلاق BOP فورا.",
     "trend": "well control event", "relationship_key": None, "typical_range": "n/a"},

    {"en": "Net Present Value (NPV)", "ar": "صافي القيمة الحالية",
     "category": "Economics", "unit": "$",
     "def_ar": "مجموع التدفقات النقدية المخصومة ناقصا الاستثمار الاولي. NPV = Sum[CFt/(1+r)^t] - C0.",
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
#  These are the DETERMINISTIC GROUND TRUTH referenced by BLOCK 5.
# ─────────────────────────────────────────────
PVT_PLOT_RULES = {
    "bo_vs_p": {
        "title_en": "Bo vs Pressure", "title_ar": "معامل حجم تكوين الزيت مقابل الضغط",
        "definition": "Bo = Reservoir Oil Volume / Stock Tank Oil Volume",
        "x_axis": "Pressure (psia)", "y_axis": "Bo (rb/STB)",
        "above_saturation": "increases gently as P decreases toward Pb (oil expansion, Rs constant)",
        "at_saturation": "MAXIMUM value (Bob)",
        "below_saturation": "decreases as P decreases (gas evolves out of solution); decline steeper than rise above Pb",
        "shape": "rises gently to a peak at Pb, then declines more steeply",
        "pivot": "Pb (peak)",
        "common_ai_mistakes": [
            "Bo increases continuously as pressure decreases (only true above Pb)",
            "Bo increases below Pb (it decreases)",
            "Rs increases above Pb (Rs is constant above Pb)",
            "Bo = Stock Tank Volume / Reservoir Volume (inverted -- WRONG)",
            "higher Bo -> higher OOIP (Bo is in the denominator: higher Bo -> LOWER OOIP)",
        ],
    },
    "rs_vs_p": {
        "title_en": "Rs vs Pressure", "title_ar": "نسبة الغاز المذاب مقابل الضغط",
        "definition": "Rs = Solution Gas-Oil Ratio (scf/STB)",
        "x_axis": "Pressure (psia)", "y_axis": "Rs (scf/STB)",
        "above_saturation": "CONSTANT at Rsi (no free gas exists)",
        "at_saturation": "Rs = Rsi (maximum, start of decline)",
        "below_saturation": "decreases toward 0 as P decreases (gas evolves)",
        "shape": "flat line above Pb, then declines below Pb",
        "pivot": "Pb (elbow where flat line begins to decline)",
        "common_ai_mistakes": [
            "Rs increasing as pressure decreases (backwards)",
            "Rs varying above Pb (must be constant = Rsi)",
            "confusing Rs (in-solution, oil-based) with produced GOR (includes free gas)",
        ],
    },
    "bg_vs_p": {
        "title_en": "Bg vs Pressure", "title_ar": "معامل حجم تكوين الغاز مقابل الضغط",
        "definition": "Bg = Reservoir Gas Volume / Standard Gas Volume",
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
        "title_en": "Z-factor vs Pressure", "title_ar": "معامل الانضغاطية للغاز مقابل الضغط",
        "definition": "Z = Gas Compressibility Factor, correction in PV=ZnRT (dimensionless)",
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
    "oil_visc_vs_p": {
        "title_en": "Oil Viscosity vs Pressure", "title_ar": "لزوجة الزيت مقابل الضغط",
        "definition": "Oil Viscosity = resistance to flow (cP)",
        "x_axis": "Pressure (psia)", "y_axis": "Oil Viscosity (cP)",
        "above_saturation": "decreases gently as P decreases toward Pb (slight expansion)",
        "at_saturation": "MINIMUM value (mu_ob)",
        "below_saturation": "increases as P decreases (gas leaves, losing 'lubrication')",
        "shape": "mirror image of Bo -- trough at Pb",
        "pivot": "Pb (minimum/trough)",
        "common_ai_mistakes": [
            "monotonic increase as pressure decreases everywhere (only true below Pb)",
            "constant viscosity below Pb",
            "not recognizing the Pb minimum",
        ],
    },
    "liquid_dropout_vs_p": {
        "title_en": "Liquid Dropout vs Pressure (CVD, Gas Condensate)",
        "title_ar": "نسبة تكثف السوائل مقابل الضغط (اختبار CVD)",
        "definition": "Liquid Dropout = % of HC pore volume condensed to liquid below Pd",
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
        "definition": "CGR = Condensate-Gas Ratio (STB/MMscf), production surveillance metric",
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
        "title_en": "Phase Envelope (P-T Diagram)", "title_ar": "المغلف الطوري (مخطط الضغط - درجة الحرارة)",
        "definition": "Bubble-point and dew-point lines meeting at the Critical Point",
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
    # Extra relationships kept for completeness (not in the mandatory-8 but useful)
    "oil_density_vs_p": {
        "title_en": "Oil Density vs Pressure", "title_ar": "كثافة الزيت مقابل الضغط",
        "definition": "Oil Density = mass per unit volume at reservoir conditions",
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
        "definition": "Vrel = V(P) / V(Pb), direct CCE test output, used to determine Pb graphically",
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
    "gas_visc_vs_p": {
        "title_en": "Gas Viscosity vs Pressure", "title_ar": "لزوجة الغاز مقابل الضغط",
        "definition": "Gas Viscosity = resistance to flow, governed by collision frequency",
        "x_axis": "Pressure (psia)", "y_axis": "Gas Viscosity (cP)",
        "above_saturation": "n/a", "at_saturation": "n/a", "below_saturation": "n/a",
        "shape": "monotonically increases with pressure (denser gas -> more collisions)",
        "pivot": "none",
        "common_ai_mistakes": [
            "applying oil-viscosity Pb-minimum logic to gas (no such inversion)",
            "confusing direction with Bg (Bg decreases, gas visc increases, with P)",
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
}


PLOT_ALIASES = {
    "bo": "bo_vs_p", "fvf": "bo_vs_p", "oil fvf": "bo_vs_p",
    "rs": "rs_vs_p", "solution gor": "rs_vs_p",
    "bg": "bg_vs_p", "gas fvf": "bg_vs_p",
    "z": "z_vs_p", "z-factor": "z_vs_p", "zfactor": "z_vs_p",
    "oil viscosity": "oil_visc_vs_p", "viscosity": "oil_visc_vs_p", "mu_o": "oil_visc_vs_p",
    "liquid dropout": "liquid_dropout_vs_p", "dropout": "liquid_dropout_vs_p", "cvd": "liquid_dropout_vs_p",
    "cgr": "cgr_vs_p",
    "phase envelope": "pt_diagram", "pt diagram": "pt_diagram", "p-t": "pt_diagram", "envelope": "pt_diagram",
    "oil density": "oil_density_vs_p", "density": "oil_density_vs_p",
    "relative volume": "vrel_vs_p_cce", "vrel": "vrel_vs_p_cce", "cce": "vrel_vs_p_cce",
    "gas viscosity": "gas_visc_vs_p", "mu_g": "gas_visc_vs_p",
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
        "Definition: " + rule["definition"],
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
    lines.append("Common AI mistakes to avoid (REJECTED statements):")
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
    # ── General / PVT ──
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

    # ── Reservoir Engineering ──
    "ooip": {
        "name_en": "Original Oil In Place (Volumetric)", "name_ar": "النفط الأصلي في المكمن",
        "inputs": ["area", "h", "phi", "sw", "bo"],
        "units": {"area": "acres", "h": "ft", "phi": "fraction", "sw": "fraction", "bo": "rb/STB"},
        "formula_str": "OOIP = (7758 x A x h x phi x (1-Sw)) / Bo",
        "func": lambda area, h, phi, sw, bo: (7758 * area * h * phi * (1 - sw)) / bo,
        "output_unit": "STB",
        "validation": lambda area, h, phi, sw, bo: 0 < phi < 1 and 0 <= sw < 1 and bo > 0,
        "note": "Bo في المقام: زيادة Bo تقلل OOIP المحسوب، وانخفاض Bo يزيد OOIP المحسوب.",
    },
    "ogip": {
        "name_en": "Original Gas In Place (Volumetric)", "name_ar": "الغاز الأصلي في المكمن",
        "inputs": ["area", "h", "phi", "sw", "bg"],
        "units": {"area": "acres", "h": "ft", "phi": "fraction", "sw": "fraction", "bg": "rb/scf"},
        "formula_str": "OGIP = (43560 x A x h x phi x (1-Sw)) / Bg",
        "func": lambda area, h, phi, sw, bg: (43560 * area * h * phi * (1 - sw)) / bg,
        "output_unit": "scf",
        "validation": lambda area, h, phi, sw, bg: 0 < phi < 1 and 0 <= sw < 1 and bg > 0,
        "note": "Bg في المقام، ووحدته rb/scf. تأكد من تطابق وحدات Bg مع المعادلة (43560 = تحويل أكر-قدم الى قدم مكعب).",
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
    "productivity_index": {
        "name_en": "Productivity Index", "name_ar": "مؤشر الإنتاجية",
        "inputs": ["q", "pr", "pwf"], "units": {"q": "STB/day", "pr": "psi", "pwf": "psi"},
        "formula_str": "PI = q / (Pr - Pwf)",
        "func": lambda q, pr, pwf: q / (pr - pwf),
        "output_unit": "STB/day/psi",
        "validation": lambda q, pr, pwf: pr > pwf and q > 0,
    },

    # ── Drilling ──
    "hydrostatic": {
        "name_en": "Hydrostatic Pressure", "name_ar": "الضغط الهيدروستاتيكي",
        "inputs": ["mw", "tvd"], "units": {"mw": "ppg", "tvd": "ft"},
        "formula_str": "P (psi) = 0.052 x MW x TVD",
        "func": lambda mw, tvd: 0.052 * mw * tvd,
        "output_unit": "psi",
        "validation": lambda mw, tvd: 6 < mw < 25 and tvd > 0,
    },
    "mud_weight_required": {
        "name_en": "Required Mud Weight (to balance a target pressure)",
        "name_ar": "وزن الطين المطلوب (لموازنة ضغط معين)",
        "inputs": ["p_target", "tvd"], "units": {"p_target": "psi", "tvd": "ft"},
        "formula_str": "MW (ppg) = P_target / (0.052 x TVD)",
        "func": lambda p_target, tvd: p_target / (0.052 * tvd),
        "output_unit": "ppg",
        "validation": lambda p_target, tvd: p_target > 0 and tvd > 0,
        "note": "هذا وزن الطين الأدنى لموازنة الضغط المستهدف (مثل ضغط المسامات). "
                "يُضاف هامش أمان (Trip Margin/Overbalance) عادة 0.2-0.5 ppg إضافية.",
    },
    "ecd": {
        "name_en": "Equivalent Circulating Density (ECD)", "name_ar": "الكثافة المكافئة للدوران",
        "inputs": ["mw", "app", "tvd"],
        "units": {"mw": "ppg", "app": "psi (annular pressure loss)", "tvd": "ft"},
        "formula_str": "ECD (ppg) = MW + (APL / (0.052 x TVD))",
        "func": lambda mw, app, tvd: mw + (app / (0.052 * tvd)),
        "output_unit": "ppg",
        "validation": lambda mw, app, tvd: mw > 0 and tvd > 0 and app >= 0,
        "note": "ECD يجب أن يبقى بين ضغط المسامات (Pore Pressure) وضغط الكسر (Fracture Pressure) "
                "أثناء الدوران، وإلا قد يحدث Kick أو Lost Circulation.",
    },

    # ── Production ──
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
        "name_en": "Produced Gas-Oil Ratio (GOR)", "name_ar": "نسبة الغاز إلى الزيت المنتجة",
        "inputs": ["qg", "qo"], "units": {"qg": "scf/day", "qo": "STB/day"},
        "formula_str": "GOR = qg / qo",
        "func": lambda qg, qo: qg / qo,
        "output_unit": "scf/STB",
        "validation": lambda qg, qo: qg >= 0 and qo > 0,
        "note": "هذا GOR المنتج (من معدلات السطح)، يختلف عن Rs (نسبة الغاز المذاب من اختبار DV) "
                "تحت ضغط نقطة الفقاعة لأن GOR المنتج يشمل الغاز الحر المتدفق مع الزيت.",
    },

    # ── Economics ──
    "npv": {
        "name_en": "Net Present Value (single cash flow)", "name_ar": "صافي القيمة الحالية (تدفق واحد)",
        "inputs": ["cf", "rate", "t"],
        "units": {"cf": "$ (cash flow in year t)", "rate": "fraction (discount rate)", "t": "years"},
        "formula_str": "PV = CF / (1+r)^t",
        "func": lambda cf, rate, t: cf / (1 + rate) ** t,
        "output_unit": "$",
        "validation": lambda cf, rate, t: rate > -1 and t >= 0,
        "note": "هذه القيمة الحالية لتدفق نقدي واحد في السنة t. لـ NPV الكلي، "
                "اجمع PV لكل سنة واطرح الاستثمار الأولي C0.",
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
    if "note" in spec:
        out.append("")
        out.append("ملاحظة: " + spec["note"])
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
    ("acre", "m2"): lambda v: v * 4046.86,
    ("m2", "acre"): lambda v: v / 4046.86,
}


def run_unit_conversion(value: float, from_unit: str, to_unit: str) -> str:
    key = (from_unit.lower().strip(), to_unit.lower().strip())
    func = UNIT_CONVERSIONS.get(key)
    if not func:
        available = sorted(set(k[0] for k in UNIT_CONVERSIONS.keys()))
        return (f"تحويل غير متاح من {from_unit} الى {to_unit}.\n"
                f"الوحدات المتاحة: {', '.join(available)}")
    result = func(value)
    return f"{value} {from_unit} = {result:,.4f} {to_unit}"


# ─────────────────────────────────────────────
#  PVT TREND VALIDATOR  (/check)
#  Compares user-supplied data series against BLOCK 5 physical rules.
# ─────────────────────────────────────────────
def check_pvt_trend(relationship_key: str, pressures: list, values: list,
                     pb_or_pd: float = None) -> str:
    if len(pressures) != len(values) or len(pressures) < 2:
        return "بيانات غير كافية للفحص. أحتاج سلسلة ضغوط وقيم متقابلة (نقطتان على الأقل)."

    # Sort by pressure ascending
    paired = sorted(zip(pressures, values))
    issues = []
    rule = PVT_PLOT_RULES.get(relationship_key)
    if not rule:
        available = ", ".join(PLOT_ALIASES.keys())
        return (f"نوع العلاقة '{relationship_key}' غير معروف.\n"
                f"الخيارات المتاحة: {available}")

    if relationship_key == "rs_vs_p":
        if pb_or_pd:
            above = [(p, v) for p, v in paired if p >= pb_or_pd]
            below = [(p, v) for p, v in paired if p < pb_or_pd]
            # Above Pb: Rs must be constant (= Rsi)
            if len(above) >= 2:
                vals_above = [v for p, v in above]
                variation = max(vals_above) - min(vals_above)
                if variation > 0.05 * max(vals_above):
                    issues.append(
                        f"Rs يتغير بشكل ملحوظ عند ضغوط أعلى من Pb (التغير = {variation:.1f}) "
                        f"-- Rs يجب أن يكون ثابتاً (=Rsi) فوق ضغط نقطة الفقاعة."
                    )
            # Below Pb: Rs must decrease as P decreases
            # (sorted ascending by P, so Rs must be non-decreasing as P increases)
            if len(below) >= 2:
                sorted_below = sorted(below)
                for i in range(1, len(sorted_below)):
                    if sorted_below[i][1] < sorted_below[i - 1][1]:
                        issues.append(
                            f"Rs عند P={sorted_below[i][0]:.0f} أصغر من Rs عند "
                            f"P={sorted_below[i-1][0]:.0f} -- تحت Pb يجب أن يتزايد "
                            f"Rs مع تزايد الضغط (أي يتناقص مع تناقص الضغط)."
                        )
                        break

    elif relationship_key == "bo_vs_p":
        if pb_or_pd:
            below = sorted([(p, v) for p, v in paired if p < pb_or_pd])
            above = sorted([(p, v) for p, v in paired if p >= pb_or_pd])
            # Below Pb: Bo must decrease as P decreases
            # (sorted ascending by P, so Bo must be non-decreasing as P increases)
            for i in range(1, len(below)):
                if below[i][1] < below[i - 1][1]:
                    issues.append(
                        f"Bo عند P={below[i][0]:.0f} أصغر من Bo عند P={below[i-1][0]:.0f} "
                        f"-- تحت Pb يجب أن يتزايد Bo مع تزايد الضغط (أي يتناقص مع "
                        f"تناقص الضغط). Bo أعظمي عند Pb."
                    )
                    break
            # Above Pb: Bo must decrease as P increases
            # (sorted ascending by P, so Bo must be non-increasing as P increases)
            for i in range(1, len(above)):
                if above[i][1] > above[i - 1][1]:
                    issues.append(
                        f"Bo عند P={above[i][0]:.0f} أكبر من Bo عند P={above[i-1][0]:.0f} "
                        f"-- فوق Pb يجب أن يتناقص Bo مع تزايد الضغط (Bo أعظمي عند Pb)."
                    )
                    break

    elif relationship_key == "oil_visc_vs_p":
        if pb_or_pd:
            below = sorted([(p, v) for p, v in paired if p < pb_or_pd])
            # Below Pb: viscosity must increase as P decreases
            # (sorted ascending by P, so visc must be non-increasing as P increases)
            for i in range(1, len(below)):
                if below[i][1] > below[i - 1][1]:
                    issues.append(
                        f"لزوجة الزيت عند P={below[i][0]:.0f} أكبر من عند P={below[i-1][0]:.0f} "
                        f"-- تحت Pb يجب أن تتناقص اللزوجة مع تزايد الضغط "
                        f"(اللزوجة أدنى ما يكون عند Pb، ثم تزداد مع نقصان الضغط)."
                    )
                    break

    elif relationship_key == "liquid_dropout_vs_p":
        vals = [v for p, v in paired]
        is_monotone_increasing = all(vals[i] <= vals[i + 1] for i in range(len(vals) - 1))
        is_monotone_decreasing = all(vals[i] >= vals[i + 1] for i in range(len(vals) - 1))
        if is_monotone_increasing or is_monotone_decreasing:
            issues.append(
                "بيانات Liquid Dropout تبدو أحادية الاتجاه (تزايد أو تناقص مستمر -- retrograde behavior مفقود). "
                "السلوك الفيزيائي الصحيح: يبدأ من صفر عند Pd، يرتفع لقمة "
                "(التكثف الرجعي / Retrograde Condensation)، ثم ينخفض (إعادة التبخر / "
                "Re-vaporization). تحقق من اكتمال بيانات اختبار CVD."
            )
        # Check that first point near Pd should be close to 0
        if pb_or_pd:
            at_pd = [(p, v) for p, v in paired if abs(p - pb_or_pd) < 0.05 * pb_or_pd]
            if at_pd and at_pd[0][1] > 5:
                issues.append(
                    f"Liquid Dropout عند Pd ({at_pd[0][0]:.0f} psia) = {at_pd[0][1]:.1f}% "
                    f"-- يجب أن يكون صفراً أو قريباً من الصفر عند ضغط نقطة الندى."
                )

    elif relationship_key == "z_vs_p":
        vals = [v for p, v in paired]
        is_monotone_increasing = all(vals[i] <= vals[i + 1] for i in range(len(vals) - 1))
        is_monotone_decreasing = all(vals[i] >= vals[i + 1] for i in range(len(vals) - 1))
        if is_monotone_increasing or is_monotone_decreasing:
            issues.append(
                "بيانات Z-factor تبدو أحادية الاتجاه. السلوك الطبيعي لـ Z على شكل "
                "حرف U: يتناقص من حوالي 1 عند الضغوط المنخفضة الى الحد الأدنى "
                "عند ضغط متوسط، ثم يتزايد مجدداً (قد يتجاوز 1 عند الضغوط العالية). "
                "تحقق من نطاق الضغوط المغطى في البيانات."
            )
        # Check Z values are in plausible range
        if any(v < 0.4 or v > 2.0 for v in vals):
            issues.append(
                "بعض قيم Z خارج النطاق المعقول (0.4 - 2.0). تحقق من الوحدات والبيانات."
            )

    elif relationship_key == "cgr_vs_p":
        if pb_or_pd:
            below = sorted([(p, v) for p, v in paired if p < pb_or_pd])
            # Below Pd: CGR must decrease as P decreases
            # (sorted ascending by P, so CGR must be non-decreasing as P increases)
            for i in range(1, len(below)):
                if below[i][1] < below[i - 1][1]:
                    issues.append(
                        f"CGR عند P={below[i][0]:.0f} أصغر من عند P={below[i-1][0]:.0f} "
                        f"-- تحت Pd يجب أن يتزايد CGR مع تزايد الضغط "
                        f"(أي يتناقص مع تناقص ضغط المكمن)."
                    )
                    break

    elif relationship_key == "bg_vs_p":
        # Bg must always decrease as pressure increases
        for i in range(1, len(paired)):
            if paired[i][1] > paired[i - 1][1]:
                issues.append(
                    f"Bg عند P={paired[i][0]:.0f} أكبر من Bg عند P={paired[i-1][0]:.0f} "
                    f"-- Bg يجب أن يتناقص باستمرار مع تزايد الضغط (Bg لا يملك نقطة محورية)."
                )
                break

    if not issues:
        return (
            f"فحص {rule['title_en']} ({rule['title_ar']})\n\n"
            f"النتيجة: البيانات تبدو متوافقة مع السلوك الفيزيائي المتوقع حسب BLOCK 5."
        )

    result = (
        f"فحص {rule['title_en']} ({rule['title_ar']}) -- تم اكتشاف مشاكل:\n\n"
        + "\n".join(f"- {issue}" for issue in issues)
        + "\n\nملاحظة: راجع BLOCK 5 في SYSTEM_PROMPT أو استخدم /plot "
          + relationship_key.split("_vs_")[0] + " للاطلاع على الشكل الصحيح."
    )
    return result


# ─────────────────────────────────────────────
#  PVTO / PVDO / PVTG / PVDG SKELETON GENERATORS  (/pvto, /pvtg)
# ─────────────────────────────────────────────
def generate_pvto_skeleton() -> str:
    return (
        "PVTO Table (Live Oil -- Eclipse Black Oil Simulator)\n"
        "الجدول المطلوب: PVTO (للزيت الحي مع غاز مذاب)\n\n"
        "متى تستخدم PVTO؟\n"
        "  - Black Oil أو Volatile Oil مع Rs > 0\n"
        "  - إذا كان Rs ~ 0 (زيت ميت/ثقيل) استخدم PVDO\n\n"
        "هيكل الجدول Eclipse:\n"
        "  PVTO\n"
        "  -- Rs (scf/STB)  Pb (psia)  Bo (rb/STB)  Viscosity (cP)  -- saturated row\n"
        "                   P > Pb      Bo < Bob     Visc > Visc_ob  -- undersaturated rows\n"
        "  /\n\n"
        "القاعدة: لكل قيمة Rs (من 0 الى Rsi):\n"
        "  السطر المشبع: Rs, Pb(Rs), Bo_sat, mu_o_sat\n"
        "  أسطر التمدد فوق Pb (نفس Rs، P > Pb): Bo يتناقص، mu_o يتزايد\n\n"
        "DATA REQUIRED:\n"
        "  من اختبار DV (أسفل Pb):\n"
        "    - Rs(P)    [scf/STB]  -- نسبة الغاز المذاب عند كل ضغط\n"
        "    - Bo(P)    [rb/STB]   -- معامل حجم التكوين عند كل ضغط\n"
        "    - mu_o(P)  [cP]       -- لزوجة الزيت عند كل ضغط\n"
        "  من اختبار CCE (فوق Pb):\n"
        "    - Co (oil compressibility) [1/psi] -- لحساب Bo فوق Pb\n"
        "    - d(mu_o)/dP فوق Pb [cP/psi]       -- لحساب لزوجة الزيت فوق Pb\n\n"
        "المصدر: بيانات اختبار التحرر التفاضلي (DV) أسفل Pb، "
        "وبيانات CCE فوق Pb.\n\n"
        "قاعدة Eclipse المهمة:\n"
        "  Bo في PVTO يجب أن يكون من DV (Differential Liberation)، ليس من CCE.\n"
        "  البيانات المباشرة من DV تحتاج تصحيح باستخدام Separator Test\n"
        "  لتحويلها من بيانات مختبرية (تفاضلية) الى بيانات ميدانية (فاصل).\n"
        "  تصحيح Standing: Bo_field = Bo_DV * (Bo_sep / Bo_DV_at_Pb)"
    )


def generate_pvdo_skeleton() -> str:
    return (
        "PVDO Table (Dead Oil -- Eclipse Black Oil Simulator)\n"
        "الجدول المطلوب: PVDO (للزيت الميت بدون غاز مذاب)\n\n"
        "متى تستخدم PVDO؟\n"
        "  - Black Oil ثقيل/زيت ميت (Heavy Oil / Dead Oil) مع Rs ~ 0\n"
        "  - زيت GOR منخفض جداً حيث يمكن إهمال الغاز المذاب\n\n"
        "هيكل الجدول Eclipse:\n"
        "  PVDO\n"
        "  -- P (psia)  Bo (rb/STB)  Viscosity (cP)\n"
        "  /\n\n"
        "DATA REQUIRED:\n"
        "  - P(P)     [psia]    -- الضغط\n"
        "  - Bo(P)    [rb/STB]  -- معامل حجم التكوين (يتناقص مع تزايد الضغط)\n"
        "  - mu_o(P)  [cP]      -- لزوجة الزيت (تتزايد مع تزايد الضغط)\n\n"
        "ملاحظة: في PVDO لا يوجد عمود Rs. Bo أبسط: يتناقص فقط مع تزايد الضغط."
    )


def generate_pvtg_skeleton() -> str:
    return (
        "PVTG Table (Live/Wet Gas -- Eclipse Black Oil Simulator)\n"
        "الجدول المطلوب: PVTG (للغاز مع مكثفات -- Gas Condensate / Wet Gas)\n\n"
        "متى تستخدم PVTG؟\n"
        "  - Gas Condensate أو Wet Gas مع Rv > 0\n"
        "  - إذا كان Rv ~ 0 (غاز جاف) استخدم PVDG\n\n"
        "هيكل الجدول Eclipse:\n"
        "  PVTG\n"
        "  -- P (psia)  Rv (STB/scf)  Bg (rb/scf)  Gas Viscosity (cP)\n"
        "  /\n\n"
        "القاعدة: لكل ضغط (من الأعلى الى الأدنى):\n"
        "  السطر المشبع: P, Rv_sat(P), Bg_sat(P), mu_g_sat(P)\n"
        "  أسطر التمدد (اختياري للغاز المكثف الغني): نفس P مع Rv > Rv_sat\n\n"
        "DATA REQUIRED:\n"
        "  من اختبار CVD:\n"
        "    - Bg(P)      [rb/scf]    -- معامل حجم تكوين الغاز\n"
        "    - mu_g(P)    [cP]        -- لزوجة الغاز\n"
        "  من التحليل التركيبي:\n"
        "    - Rv(P)      [STB/scf]   -- نسبة المكثفات في الغاز\n"
        "      (Rv = CGR * Bg_initial, أو من حسابات EOS)\n\n"
        "ملاحظة: للغاز المكثف الغني أو القريب من النقطة الحرجة،\n"
        "  النموذج التركيبي (Compositional / CMG GEM / Eclipse Compositional)\n"
        "  أكثر دقة من PVTG لأن PVTG يفترض تركيباً ثابتاً للطورين."
    )


def generate_pvdg_skeleton() -> str:
    return (
        "PVDG Table (Dry Gas -- Eclipse Black Oil Simulator)\n"
        "الجدول المطلوب: PVDG (للغاز الجاف بدون مكثفات)\n\n"
        "متى تستخدم PVDG؟\n"
        "  - Dry Gas أو Wet Gas عندما يكون Rv ~ 0\n"
        "  - أبسط أنواع جداول الغاز\n\n"
        "هيكل الجدول Eclipse:\n"
        "  PVDG\n"
        "  -- P (psia)  Bg (rb/scf)  Gas Viscosity (cP)\n"
        "  /\n\n"
        "DATA REQUIRED:\n"
        "  - P(P)      [psia]     -- الضغط\n"
        "  - Bg(P)     [rb/scf]   -- معامل حجم تكوين الغاز (يتناقص مع تزايد الضغط)\n"
        "  - mu_g(P)   [cP]       -- لزوجة الغاز (تتزايد مع تزايد الضغط)\n\n"
        "حساب Bg:\n"
        "  Bg (rb/scf) = 0.005615 * (Z * T) / (P)\n"
        "  حيث T بوحدة Rankine (T(°R) = T(°F) + 459.67) و P بوحدة psia."
    )


# ─────────────────────────────────────────────
#  SIMULATION EXPORT DECISION  (/export_sim)
# ─────────────────────────────────────────────
EXPORT_SIM_DECISIONS = {
    "black_oil": {
        "table": "PVTO (إذا Rs > 0) أو PVDO (إذا Rs ~ 0)",
        "simulator": "Eclipse Black Oil (E100) أو CMG IMEX",
        "reason": "نموذج Black-Oil كافٍ لأن تغيرات التركيب بين الطورين بطيئة ويمكن تبسيطها.",
        "warning": None,
    },
    "volatile_oil": {
        "table": "PVTO مع كثافة بيانات عالية قرب Pb",
        "simulator": "Eclipse Black Oil (E100) أو CMG IMEX -- مع تحفظ",
        "reason": "Volatile Oil يمكن معالجته بـ Black-Oil لكن التغير الحاد في Bo و Rs قرب Pb "
                  "يتطلب شبكة بيانات كثيفة جداً.",
        "warning": "إذا كان السائل قريباً من النقطة الحرجة (Near-Critical Volatile Oil): "
                   "يُنصح بالتحول الى النموذج التركيبي (Compositional / Eclipse E300 / CMG GEM) "
                   "لأن افتراضات Black-Oil تنهار قرب النقطة الحرجة.",
    },
    "gas_condensate": {
        "table": "PVTG مع Rv من التحليل التركيبي",
        "simulator": "Eclipse Black Oil (E100) مع PVTG -- أو CMG IMEX مع PVTG",
        "reason": "Black-Oil مع PVTG مناسب للغاز المكثف الخفيف (Lean Gas Condensate).",
        "warning": "للغاز المكثف الغني (Rich Gas Condensate) أو القريب من النقطة الحرجة: "
                   "النموذج التركيبي (Eclipse E300 / CMG GEM + EOS) أكثر دقة لأن PVTG "
                   "لا يلتقط تغير التركيب بدقة أسفل ضغط الندى.",
    },
    "wet_gas": {
        "table": "PVTG مع Rv ثابت تقريباً (لا تكثف في المكمن)",
        "simulator": "Eclipse Black Oil (E100) أو CMG IMEX",
        "reason": "Wet Gas لا يوجد فيه تكثف في المكمن، فقط على السطح، لذا PVTG كافٍ.",
        "warning": None,
    },
    "dry_gas": {
        "table": "PVDG (بدون Rv)",
        "simulator": "Eclipse Black Oil (E100) أو CMG IMEX",
        "reason": "Dry Gas أبسط حالة -- لا مكثفات. PVDG يحوي فقط Bg و لزوجة الغاز.",
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
            "نوع السائل غير محدد. الأنواع المتاحة:\n"
            "black oil, volatile oil, gas condensate, wet gas, dry gas\n"
            "الترادفات العربية: زيت أسود، زيت متطاير، غاز مكثف، غاز رطب، غاز جاف\n\n"
            "Usage: /export_sim <fluid_type> [near_critical]\n"
            "Example: /export_sim gas condensate near_critical"
        )

    d = EXPORT_SIM_DECISIONS[key]
    out = [
        f"قرار المحاكاة -- {fluid_type}",
        "",
        f"الجدول المطلوب: {d['table']}",
        f"المحاكي الموصى به: {d['simulator']}",
        f"السبب: {d['reason']}",
    ]
    if d["warning"]:
        out.append("")
        out.append(f"تحذير: {d['warning']}")
    if near_critical and key in ("volatile_oil", "gas_condensate"):
        out.append("")
        out.append(
            "تحذير إضافي (Near-Critical): السائل قريب من النقطة الحرجة. نماذج Black-Oil "
            "تفترض تركيباً ثابتاً للطورين، وهو افتراض ضعيف جداً هنا. "
            "النموذج التركيبي (Compositional / EOS) هو الخيار الموصى به."
        )
    return "\n".join(out)


# ─────────────────────────────────────────────
#  TEXT CLEANER  -- fixes wrong Arabic terms that slip through
# ─────────────────────────────────────────────
def clean_text(text: str) -> str:
    text = str(text)
    fixes = {
        "**": "", "###": "", "##": "", "#": "", "[": "", "]": "",
        "Pressuring Volume and Temperature": "Pressure-Volume-Temperature",
        "الضغط البيني":          "معامل حجم التكوين",
        "المعامل البيني":        "معامل حجم التكوين",
        "الترشيح":               "نسبة الغاز المذاب",
        "النسبة المئوية للغاز":  "نسبة الغاز إلى الزيت",
        "نسبة الغاز المئوية":    "نسبة الغاز إلى الزيت",
        "الويسكوزية":            "اللزوجة",
        "الليزج":                "اللزوجة",
        "الحفرة":                "المكمن",
        "السطوح النوعي":         "الكثافة النوعية",
        "اختبار السطوح":         "اختبار الكثافة النوعية",
        "السطوع النوعي":         "الكثافة النوعية",
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
                json={"chat_id": chat_id, "text": text[i:i + 3900]},
                timeout=15
            )
        except Exception as e:
            print(f"send_message error: {e}")
        time.sleep(0.4)


def send_document(chat_id: int, file_bytes: bytes, filename: str,
                   caption: str, mime: str = "text/html") -> None:
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
        info = requests.get(
            f"{TELEGRAM_URL}/getFile",
            params={"file_id": file_id},
            timeout=15
        ).json()
        if not info.get("ok"):
            return None
        url  = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{info['result']['file_path']}"
        data = requests.get(url, timeout=60).content
        tmp  = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        tmp.write(data)
        tmp.close()
        return tmp.name
    except Exception as e:
        print(f"download_file error: {e}")
        return None


def extract_pdf_text(path: str) -> str:
    try:
        reader = PdfReader(path)
        return "\n\n".join(
            p.extract_text() for p in reader.pages if p.extract_text()
        ).strip()
    except Exception as e:
        print(f"PDF error: {e}")
        return ""


def extract_docx_text(path: str) -> str:
    try:
        doc = Document(path)
        return "\n".join(
            p.text.strip() for p in doc.paragraphs if p.text.strip()
        )
    except Exception as e:
        print(f"DOCX error: {e}")
        return ""


def encode_image(path: str) -> str:
    mime, _ = mimetypes.guess_type(path)
    if not mime:
        mime = "image/jpeg"
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return f"data:{mime};base64,{b64}"


# ─────────────────────────────────────────────
#  PDF SECTION SEGMENTATION (PVT report structure awareness)
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
    """Splits extracted PDF text into labeled sections based on PVT report headers."""
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
    """Formats segmented sections with clear labels for the AI prompt."""
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
            f"تم قراءة الملف بنجاح.\n"
            f"تحذير: الملف يحتوي على {original_len:,} حرف، تم استخدام أول "
            f"{MAX_CONTEXT_CHARS:,} حرف كمرجع لهذه المحادثة. "
            f"إذا كانت المعلومات المهمة في أجزاء لاحقة، قسّم الملف "
            f"وأرسل الجزء المطلوب بشكل منفصل."
        )
    FILE_CONTEXT[chat_id] = text
    return f"تم قراءة الملف '{filename}' بنجاح ({original_len:,} حرف). أصبح مرجعاً لهذه المحادثة."


# ─────────────────────────────────────────────
#  AI CALLS  (with retry/backoff + differentiated error messages)
# ─────────────────────────────────────────────
def ask_ai(user_text: str, file_context=None, max_retries: int = 2) -> str:
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            messages = [{"role": "system", "content": SYSTEM_PROMPT}]
            if file_context:
                messages.append({
                    "role": "user",
                    "content": "Reference document context (PVT / engineering report, segmented):\n\n"
                               + file_context[:20000]
                })
            messages.append({"role": "user", "content": user_text})

            r = requests.post(
                GROQ_URL,
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": TEXT_MODEL,
                    "messages": messages,
                    "temperature": 0.08,
                    "max_tokens": 3000
                },
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
        "rate_limit":          "النظام مشغول حالياً (rate limit). حاول مرة أخرى بعد لحظات.",
        "service_unavailable": "خدمة الذكاء الاصطناعي غير متاحة مؤقتاً. حاول بعد قليل.",
        "timeout":             "انتهت مهلة الاتصال. حاول مرة أخرى أو قسّم السؤال إلى أجزاء أصغر.",
        "connection_error":    "تعذر الاتصال بخدمة الذكاء الاصطناعي. تحقق من الشبكة.",
    }
    return error_messages.get(last_error, f"حدث خطأ غير متوقع: {last_error}")


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
                    {"type": "text", "text": full_prompt},
                    {"type": "image_url", "image_url": {"url": encode_image(image_path)}}
                ]
            }]

            r = requests.post(
                GROQ_URL,
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": VISION_MODEL,
                    "messages": messages,
                    "temperature": 0.08,
                    "max_tokens": 2200
                },
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
        "rate_limit":          "النظام مشغول حالياً. حاول مرة أخرى بعد لحظات.",
        "service_unavailable": "خدمة تحليل الصور غير متاحة مؤقتاً. حاول بعد قليل.",
        "timeout":             "انتهت مهلة تحليل الصورة. حاول مرة أخرى.",
        "connection_error":    "تعذر الاتصال بخدمة تحليل الصور.",
    }
    return error_messages.get(last_error, f"حدث خطأ في تحليل الصورة: {last_error}")


# ─────────────────────────────────────────────
#  GRAPH INTERPRETATION PROMPT  (/graph, /interpret_graph)
#  Embeds PVT_PLOT_RULES as inline reference so the vision model
#  compares the image against known-correct shapes.
# ─────────────────────────────────────────────
def build_graph_prompt(user_text: str) -> str:
    reference_summary = "\n".join(
        f"- {r['title_en']} ({r['title_ar']}): {r['shape']} | Pivot: {r['pivot']}"
        for r in PVT_PLOT_RULES.values()
    )
    return (
        SYSTEM_PROMPT
        + "\n\nTASK: Analyze the uploaded petroleum engineering plot/image.\n\n"
        "REFERENCE SHAPES (BLOCK 5 ground truth -- compare the image against these):\n"
        + reference_summary
        + "\n\nSTEPS:\n"
        "1. Identify X-axis and Y-axis labels, units, and scale (linear/log).\n"
        "2. Match the plot to ONE of the reference relationships above.\n"
        "3. State whether the observed shape AGREES or DISAGREES with the reference shape "
        "(pivot location, direction changes, monotonicity).\n"
        "4. If AGREES: identify the saturation pressure (Pb or Pd) location on the curve.\n"
        "5. If DISAGREES: state the discrepancy, suggest likely causes "
        "(contamination, mislabeled axes, separator vs reservoir confusion, "
        "data entry error, truncated dataset), and recommend verification steps.\n"
        "6. Give a concise engineering interpretation and recommendation.\n\n"
        "SPECIAL RULE: If the plot shows Bo INCREASING below Pb, flag it immediately "
        "as non-physical and reject it per BLOCK 5 (Bo = Reservoir/StockTank, "
        "decreases below Pb).\n\n"
        f"User's additional context/question: {user_text}\n\n"
        "Follow BLOCK 13 formatting rules (no markdown, clear headings)."
    )


# ─────────────────────────────────────────────
#  FILE / PHOTO UPLOAD HANDLERS
# ─────────────────────────────────────────────
def handle_document_upload(chat_id: int, doc: dict) -> None:
    file_id   = doc["file_id"]
    file_name = doc.get("file_name", "file")
    mime      = doc.get("mime_type", "")
    ext       = os.path.splitext(file_name)[1].lower() or ".bin"
    path      = download_file(file_id, ext)

    if not path:
        send_message(chat_id, "حدث خطأ أثناء تحميل الملف.")
        return

    lower = file_name.lower()
    if lower.endswith(".pdf"):
        text = extract_pdf_text(path)
        if not text:
            send_message(
                chat_id,
                "قرأت PDF لكن لم أستخرج نصاً. الملف غالباً سكاني (صور مُسحوحة).\n"
                "أرسل صفحاته كصور أو ارفع PDF نصياً."
            )
            return
        sections = segment_pdf_text(text)
        formatted = format_segmented_context(sections)
        status_msg = store_file_context(chat_id, formatted, file_name)
        send_message(chat_id, status_msg + "\nاكتب /analyze لتحليله هندسياً.")

    elif lower.endswith(".docx"):
        text = extract_docx_text(path)
        if not text:
            send_message(chat_id, "قرأت DOCX لكن لم أجد نصاً.")
            return
        status_msg = store_file_context(chat_id, text, file_name)
        send_message(chat_id, status_msg + "\nاكتب /analyze للتحليل.")

    elif mime.startswith("image/") or lower.endswith((".png", ".jpg", ".jpeg", ".webp")):
        IMAGE_CONTEXT[chat_id] = path
        send_message(chat_id, "تم استلام الصورة. اكتب /graph لتحليل الرسم هندسياً.")

    else:
        send_message(chat_id, "الملف المدعوم: PDF أو DOCX أو صورة (PNG/JPG/JPEG/WEBP).")


def handle_photo_upload(chat_id: int, photos: list) -> None:
    path = download_file(photos[-1]["file_id"], ".jpg")
    if path:
        IMAGE_CONTEXT[chat_id] = path
        send_message(chat_id, "تم استلام الصورة. اكتب /graph لتحليل الرسم هندسياً.")
    else:
        send_message(chat_id, "خطأ في تحميل الصورة.")


# ─────────────────────────────────────────────
#  GLOSSARY HTML GENERATOR  (/glossary)
#  Built dynamically from KNOWLEDGE_BASE + PVT_PLOT_RULES + ASCII_SKETCHES.
#  Uses JSON serialization to avoid all nested-quote escaping issues.
# ─────────────────────────────────────────────
import json as _json


def generate_glossary_html() -> bytes:
    """
    Generates a complete interactive HTML glossary file.
    Content is pulled from KNOWLEDGE_BASE and PVT_PLOT_RULES so the
    HTML can never drift from the SYSTEM_PROMPT definitions.
    """

    category_config = {
        "PVT":                      ("b-pvt",  "PVT"),
        "Reservoir":                ("b-res",  "المكمن"),
        "Production":               ("b-pro",  "الإنتاج"),
        "Drilling":                 ("b-drl",  "الحفر"),
        "Economics":                ("b-eco",  "الاقتصاد"),
        "PVT - Gas Condensate":     ("b-pvt",  "غاز مكثف"),
        "Production - Gas Condensate": ("b-pro", "غاز مكثف"),
        "Phase Behavior":           ("b-pvt",  "السلوك الطوري"),
    }

    # ── Term records for JS ──────────────────────────────────
    term_records = []
    for t in KNOWLEDGE_BASE:
        cls, lbl = category_config.get(t["category"], ("b-pvt", t["category"]))
        extras = []
        if t.get("typical_range") and t["typical_range"] not in ("n/a", "varies widely"):
            extras.append("المدى النموذجي: " + t["typical_range"] + " (" + t["unit"] + ")")
        trend = t.get("trend", "")
        skip_trend = any(x in trend for x in ("n/a", "static", "indicator", "event",
                                                "descriptive", "calculated", "controlled",
                                                "varies", "depends"))
        if trend and not skip_trend:
            extras.append("الاتجاه: " + trend)
        term_records.append({
            "ar": t["ar"],
            "en": t["en"],
            "cls": cls,
            "lbl": lbl,
            "def": t["def_ar"],
            "extras": extras,
            "search": (t["en"] + " " + t["ar"] + " " + t["def_ar"]).lower(),
        })

    # ── Plot records for JS ──────────────────────────────────
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
            "key":       key,
            "title_ar":  rule["title_ar"],
            "title_en":  rule["title_en"],
            "definition": rule["definition"],
            "x_axis":    rule["x_axis"],
            "y_axis":    rule["y_axis"],
            "shape":     rule["shape"],
            "rows":      rows,
            "pivot":     rule["pivot"],
            "mistakes":  rule["common_ai_mistakes"],
            "sketch":    ASCII_SKETCHES.get(key, ""),
        })

    term_json = _json.dumps(term_records, ensure_ascii=False)
    plot_json = _json.dumps(plot_records, ensure_ascii=False)

    css = """
@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@300;400;600;700;900&family=Fira+Code:wght@400;600&display=swap');
:root{--crude:#3d1f00;--amber:#c8760a;--gold:#e8a020;--light:#fef3dc;--surface:#f5f0e8;--paper:#fdfaf4;--border:#ddd0b8;--muted:#7a6a58;--dbg:#0d1117}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Cairo',sans-serif;background:var(--surface);color:#111;line-height:1.7}
header{background:var(--crude);color:var(--paper);padding:2.5rem 2rem 2rem;text-align:center}
header h1{font-size:clamp(1.6rem,4vw,2.5rem);font-weight:900}
header h1 span{color:var(--gold)}
header p{margin-top:.4rem;font-size:.95rem;opacity:.65}
nav{display:flex;justify-content:center;gap:.5rem;flex-wrap:wrap;padding:1.2rem 1rem;
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
    margin-bottom:1.5rem;transition:border .2s}
.search input:focus{outline:none;border-color:var(--amber)}
.grid{display:grid;gap:1rem}
.card{background:var(--paper);border:1.5px solid var(--border);border-radius:10px;
    overflow:hidden;transition:box-shadow .2s,border-color .2s}
.card:hover{box-shadow:0 4px 18px rgba(200,118,10,.14);border-color:var(--amber)}
.card-head{display:flex;align-items:center;gap:.8rem;padding:.9rem 1.3rem;
    cursor:pointer;flex-wrap:wrap}
.ar{font-size:1rem;font-weight:700;color:var(--crude);flex:1}
.en{font-family:'Fira Code',monospace;font-size:.82rem;font-weight:600;color:var(--amber);
    background:var(--light);padding:.2rem .6rem;border-radius:5px;direction:ltr;white-space:nowrap}
.badge{font-size:.68rem;padding:.18rem .55rem;border-radius:999px;font-weight:700;white-space:nowrap}
.b-res{background:#dbeafe;color:#1e40af}.b-pvt{background:#fef9c3;color:#854d0e}
.b-pro{background:#dcfce7;color:#166534}.b-drl{background:#ffe4e6;color:#9f1239}
.b-eco{background:#e0f2fe;color:#0369a1}
.card-body{display:none;padding:0 1.3rem 1.2rem;border-top:1px solid var(--border)}
.card-body.open{display:block}
.def{margin-top:.9rem;font-size:.95rem;color:#333;line-height:1.85}
.extra{margin-top:.35rem;font-size:.8rem;color:var(--muted)}
.ftitle{font-size:1.3rem;font-weight:900;color:var(--crude);margin-bottom:1.2rem;
    padding-bottom:.4rem;border-bottom:3px solid var(--amber)}
.pcard{background:var(--dbg);border-radius:10px;overflow:hidden;margin-bottom:1.2rem;
    border:1px solid #2a3040}
.pcard-head{display:flex;justify-content:space-between;align-items:center;
    padding:.8rem 1.3rem;background:rgba(200,118,10,.11);border-bottom:1px solid #2a3040;
    flex-wrap:wrap;gap:.4rem}
.p-en{font-family:'Fira Code',monospace;color:var(--gold);font-size:.85rem;direction:ltr}
.p-ar{color:rgba(255,255,255,.85);font-size:.9rem;font-weight:600}
.pcard-body{padding:1.1rem 1.3rem;color:rgba(255,255,255,.75);font-size:.85rem}
.p-def{font-style:italic;color:var(--gold);margin-bottom:.5rem;font-size:.82rem}
.axes{font-family:'Fira Code',monospace;font-size:.78rem;margin-bottom:.5rem;
    color:rgba(255,255,255,.6)}
.shape{margin-bottom:.6rem;font-weight:600;color:rgba(255,255,255,.9)}
.prow{margin:.3rem 0}
.pivot{margin:.5rem 0;color:var(--gold);font-weight:600}
.mistakes-label{margin-top:.6rem;font-size:.78rem;color:rgba(255,100,100,.8);font-weight:700}
.mistake{font-size:.75rem;color:rgba(255,120,120,.7);margin:.2rem 0}
.sketch{font-family:'Fira Code',monospace;font-size:.68rem;color:#9be9a8;background:#000;
    padding:.8rem;border-radius:6px;overflow-x:auto;direction:ltr;text-align:left;
    line-height:1.3;margin-top:.8rem}
.nr{text-align:center;padding:3rem;color:var(--muted)}
"""

    js = r"""
function renderTerms(list){
  document.getElementById("tgrid").innerHTML = list.map(function(t,i){
    var ex = (t.extras||[]).map(function(e){
      return '<div class="extra">' + e + '</div>';
    }).join("");
    return '<div class="card">'
      + '<div class="card-head" onclick="tog('+i+')">'
      + '<span class="ar">'+t.ar+'</span>'
      + '<span class="en">'+t.en+'</span>'
      + '<span class="badge '+t.cls+'">'+t.lbl+'</span>'
      + '</div>'
      + '<div class="card-body" id="b'+i+'">'
      + '<p class="def">'+t.def+'</p>'+ex
      + '</div></div>';
  }).join("");
}
function tog(i){ document.getElementById("b"+i).classList.toggle("open"); }
function filterTerms(){
  var q = document.getElementById("q").value.toLowerCase();
  var f = q ? TERMS.filter(function(t){ return t.search.indexOf(q)!==-1; }) : TERMS;
  renderTerms(f);
  document.getElementById("nr").style.display = f.length ? "none" : "block";
}
function renderPlots(){
  document.getElementById("pgrid").innerHTML = PLOTS.map(function(p){
    var rows = (p.rows||[]).map(function(r){
      return '<div class="prow">' + r + '</div>';
    }).join("");
    var mistakes = (p.mistakes||[]).map(function(m){
      return '<div class="mistake">- ' + m + '</div>';
    }).join("");
    return '<div class="pcard">'
      + '<div class="pcard-head">'
      + '<span class="p-ar">'+p.title_ar+'</span>'
      + '<span class="p-en">'+p.title_en+'</span>'
      + '</div>'
      + '<div class="pcard-body">'
      + '<div class="p-def">'+p.definition+'</div>'
      + '<div class="axes">X: '+p.x_axis+' | Y: '+p.y_axis+'</div>'
      + '<div class="shape">'+p.shape+'</div>'
      + rows
      + '<div class="pivot">Pivot: '+p.pivot+'</div>'
      + (mistakes ? '<div class="mistakes-label">محظورات (REJECT):</div>'+mistakes : '')
      + '<pre class="sketch">'+p.sketch+'</pre>'
      + '</div></div>';
  }).join("");
}
function show(id,btn){
  document.querySelectorAll(".sec").forEach(function(s){s.classList.remove("active");});
  document.querySelectorAll("nav button").forEach(function(b){b.classList.remove("active");});
  document.getElementById(id).classList.add("active");
  btn.classList.add("active");
}
renderTerms(TERMS);
renderPlots();
"""

    parts = [
        '<!DOCTYPE html>',
        '<html lang="ar" dir="rtl">',
        '<head>',
        '<meta charset="UTF-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1.0">',
        '<title>Petroleum Engineering Glossary - المصطلحات الهندسية النفطية</title>',
        '<style>' + css + '</style>',
        '</head><body>',
        (
            '<header>'
            '<h1>المصطلحات <span>الهندسية النفطية</span><br>'
            '<small style="font-size:.52em;font-weight:300;opacity:.65">'
            'Full Petroleum Engineering Glossary -- PVT / Reservoir / Drilling / Production / Economics'
            '</small></h1>'
            '<p>تعريفات علمية مضبوطة - اتجاهات PVT الصحيحة - رسوم ASCII مرجعية</p>'
            '</header>'
        ),
        (
            '<nav>'
            '<button class="active" onclick="show(\'terms\',this)">المصطلحات</button>'
            '<button onclick="show(\'plots\',this)">علاقات PVT والرسوم</button>'
            '</nav>'
        ),
        '<main>',
        (
            '<div id="terms" class="sec active">'
            '<div class="search"><input id="q" placeholder="ابحث عن مصطلح بالعربي أو الإنجليزي..." oninput="filterTerms()"/></div>'
            '<div class="grid" id="tgrid"></div>'
            '<div class="nr" id="nr" style="display:none">لا توجد نتائج مطابقة</div>'
            '</div>'
        ),
        (
            '<div id="plots" class="sec">'
            '<p class="ftitle">علاقات PVT مقابل الضغط -- الشكل الصحيح فيزيائياً (BLOCK 5)</p>'
            '<div id="pgrid"></div>'
            '</div>'
        ),
        '</main>',
        '<script>',
        'const TERMS = ' + term_json + ';',
        'const PLOTS = ' + plot_json + ';',
        js,
        '</script>',
        '</body></html>',
    ]

    return "\n".join(parts).encode("utf-8")


# ─────────────────────────────────────────────
#  COMMAND DETECTORS
# ─────────────────────────────────────────────
def is_graph_cmd(t):      return t.lower().startswith(("/graph", "/interpret_graph"))
def is_analyze_cmd(t):    return t.lower().startswith("/analyze")
def is_calc_cmd(t):       return t.lower().startswith("/calc")
def is_estimate_cmd(t):   return t.lower().startswith("/estimate")
def is_convert_cmd(t):    return t.lower().startswith("/convert")
def is_classify_cmd(t):   return t.lower().startswith("/classify")
def is_plot_cmd(t):       return t.lower().startswith("/plot")
def is_check_cmd(t):      return t.lower().startswith("/check")
def is_pvto_cmd(t):       return t.lower().strip() == "/pvto"
def is_pvdo_cmd(t):       return t.lower().strip() == "/pvdo"
def is_pvtg_cmd(t):       return t.lower().strip() == "/pvtg"
def is_pvdg_cmd(t):       return t.lower().strip() == "/pvdg"
def is_export_sim_cmd(t): return t.lower().startswith("/export_sim")
def is_eclipse_cmd(t):    return t.lower().startswith("/eclipse")
def is_cmg_cmd(t):        return t.lower().startswith("/cmg")
def is_reset_cmd(t):      return t.lower().strip() == "/reset"


def is_surface_separator(t: str) -> bool:
    t = t.lower()
    oil = any(k in t for k in [
        "surface separator oil", "separator oil",
        "زيت من الفاصل", "عينة زيت من الفاصل"
    ])
    gas = any(k in t for k in [
        "separator gas", "غاز من الفاصل", "عينة غاز من الفاصل"
    ])
    return oil and gas


# ─────────────────────────────────────────────
#  STATIC RESPONSES
# ─────────────────────────────────────────────
def start_message() -> str:
    return (
        "أهلاً بك في Petroleum Engineering AI Bot\n\n"
        "مساعد هندسي متخصص في:\n"
        "- PVT Laboratory و Reservoir Fluid Analysis\n"
        "- Reservoir Engineering و Reservoir Simulation (Eclipse / CMG)\n"
        "- Drilling Engineering\n"
        "- Production Engineering\n"
        "- Petroleum Economics\n\n"
        "=== أوامر حتمية (دقيقة 100% -- بدون توليد AI) ===\n\n"
        "/classify gor=<val> api=<val>\n"
        "    تصنيف نوع السائل (Black Oil / Volatile Oil / Gas Condensate ...)\n\n"
        "/calc <type> key=value ...\n"
        "    حسابات بمعادلات مضبوطة. الأنواع المتاحة:\n"
        "    api, ooip, ogip, darcy, recovery_factor, productivity_index\n"
        "    hydrostatic, mud_weight_required, ecd\n"
        "    water_cut, wor, gor_produced, npv\n"
        "    أمثلة:\n"
        "      /calc api sg=0.85\n"
        "      /calc hydrostatic mw=10 tvd=5000\n"
        "      /calc ooip area=500 h=50 phi=0.2 sw=0.3 bo=1.3\n"
        "      /calc water_cut qw=800 qo=200\n\n"
        "/estimate <type> key=value ...\n"
        "    تقديرات بمعادلات تجريبية. الأنواع: pb_standing, rs_standing\n"
        "    مثال: /estimate pb_standing rs=650 gas_sg=0.75 tres=180 api=35\n\n"
        "/convert <value> <from_unit> to <to_unit>\n"
        "    مثال: /convert 5000 psi to bar\n\n"
        "/plot <relationship>\n"
        "    شرح + رسم ASCII صحيح فيزيائياً. الخيارات:\n"
        "    bo, rs, bg, z, viscosity, dropout/cvd, cgr, phase envelope/pt\n"
        "    + oil density, vrel/cce, gas viscosity\n\n"
        "/check <rel> p=p1,p2,.. v=v1,v2,.. pb=<val>\n"
        "    فحص بيانات PVT مقابل السلوك الفيزيائي الصحيح\n"
        "    مثال: /check rs p=500,1000,1500,2000 v=300,300,250,180 pb=1500\n\n"
        "/pvto  -- هيكل + شرح جدول PVTO لـ Eclipse\n"
        "/pvdo  -- هيكل + شرح جدول PVDO لـ Eclipse\n"
        "/pvtg  -- هيكل + شرح جدول PVTG لـ Eclipse\n"
        "/pvdg  -- هيكل + شرح جدول PVDG لـ Eclipse\n\n"
        "/export_sim <fluid_type> [near_critical]\n"
        "    قرار Black-Oil vs Compositional\n"
        "    مثال: /export_sim gas condensate near_critical\n\n"
        "=== أوامر بمساعدة الذكاء الاصطناعي ===\n\n"
        "/glossary  -- الغلوساري الشامل (HTML تفاعلي: مصطلحات + علاقات PVT)\n"
        "/analyze   -- تحليل تقرير PDF/DOCX مرفوع\n"
        "/graph     -- تحليل رسم بياني أو صورة هندسية مرفوعة\n"
        "/eclipse   -- إرشادات Eclipse (كلمات مفتاحية، جداول PVT، تحقق من الوحدات)\n"
        "/cmg       -- إرشادات CMG (IMEX vs GEM، مدخلات البيانات)\n"
        "/reset     -- مسح الملفات والصور المحفوظة لهذه المحادثة\n\n"
        "يمكنك أيضاً كتابة سؤالك مباشرة بالعربي أو الإنجليزي."
    )


def surface_separator_answer() -> str:
    return (
        "تحليل هندسي -- عينة زيت من الفاصل السطحي مع عينة غاز\n\n"
        "نوع العينات\n"
        "هذه عينات سطحية منفصلة وليست سائل مكمن مباشراً مثل Bottom Hole Sample.\n"
        "الزيت والغاز انفصلا عند ظروف الفاصل السطحي، لذلك يلزم Recombination أولاً "
        "قبل إجراء أي اختبار PVT أو الإبلاغ عن أي خاصية (Bo, Rs, Pb).\n\n"
        "البيانات المطلوبة قبل المتابعة\n"
        "- Separator Pressure و Separator Temperature\n"
        "- Oil Rate [STB/day] و Gas Rate [scf/day]\n"
        "- Producing GOR أو Separator GOR [scf/STB]\n"
        "- Gas Composition و Oil/Stock Tank Oil Composition\n"
        "- API Gravity و Gas Specific Gravity\n"
        "- Water Cut و وجود H2S/CO2\n\n"
        "تسلسل العمل المخبري الصحيح\n"
        "1. Sample QC -- فحص جودة وسلامة العينات\n"
        "2. Recombination -- إعادة بناء سائل المكمن\n"
        "3. Validation -- التحقق من تمثيلية العينة المعاد تركيبها\n"
        "4. Compositional Analysis -- تحليل تركيبي كامل (C1 to C12+)\n"
        "5. CCE/CME -- لتحديد Saturation Pressure عبر كسر منحنى Vrel\n"
        "6. DV للزيت (Black Oil / Volatile Oil) أو CVD للغاز المكثف\n"
        "7. Separator Test -- تحويل البيانات التفاضلية الى بيانات ميدانية\n"
        "8. Viscosity Test\n"
        "9. EOS Tuning إذا كان الهدف محاكاة تركيبية\n\n"
        "الرسومات المطلوبة (استخدم /plot لكل منها)\n"
        "- /plot bo       -- Bo vs Pressure\n"
        "- /plot rs       -- Rs vs Pressure\n"
        "- /plot vrel     -- Relative Volume vs Pressure (CCE)\n"
        "- /plot viscosity -- Oil Viscosity vs Pressure\n"
        "- للغاز المكثف: /plot dropout -- Liquid Dropout vs Pressure (CVD)\n\n"
        "قرار المحاكاة\n"
        "Black Oil / Volatile Oil: PVTO في Eclipse (استخدم /pvto للتفاصيل)\n"
        "Gas Condensate / Volatile Oil قرب النقطة الحرجة: Compositional Model مع EOS Tuning\n"
        "استخدم /classify بعد معرفة GOR و API لتحديد نوع السائل.\n\n"
        "الخلاصة\n"
        "لا يمكن حساب Bo أو Rs أو Pb بدون بيانات الفاصل والتركيب.\n"
        "أرسل البيانات وسأبدأ بالحسابات والفحوصات فوراً (/calc, /check, /classify)."
    )


# ─────────────────────────────────────────────
#  MAIN LOOP
# ─────────────────────────────────────────────
print("Petroleum Engineering AI Bot v3 running...")

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

            # ── Document upload ──
            if "document" in msg:
                handle_document_upload(chat_id, msg["document"])
                continue

            # ── Photo upload ──
            if "photo" in msg:
                handle_photo_upload(chat_id, msg["photo"])
                continue

            # ── Must be text ──
            if "text" not in msg:
                send_message(chat_id, "أرسل نصاً أو ملف PDF/DOCX أو صورة.")
                continue

            text    = msg["text"].strip()
            context = FILE_CONTEXT.get(chat_id)

            # ── /start ──
            if text == "/start":
                send_message(chat_id, start_message())
                continue

            # ── /reset ──
            if is_reset_cmd(text):
                FILE_CONTEXT.pop(chat_id, None)
                IMAGE_CONTEXT.pop(chat_id, None)
                send_message(chat_id, "تم مسح الملفات والصور المحفوظة. ابدأ من جديد.")
                continue

            # ── /glossary ──
            if text == "/glossary":
                send_document(
                    chat_id,
                    generate_glossary_html(),
                    "petroleum_engineering_glossary.html",
                    (
                        "الغلوساري الهندسي النفطي الشامل\n\n"
                        f"يحتوي على:\n"
                        f"- {len(KNOWLEDGE_BASE)} مصطلحاً هندسياً بتعريفات علمية مضبوطة\n"
                        f"- {len(PVT_PLOT_RULES)} علاقة PVT مع الشكل الفيزيائي الصحيح\n"
                        f"- رسوم ASCII مرجعية لكل علاقة\n\n"
                        "افتح الملف في أي متصفح."
                    )
                )
                continue

            # ── /classify ──
            if is_classify_cmd(text):
                kwargs = parse_kv_args(text[len("/classify"):])
                if "gor" not in kwargs or "api" not in kwargs:
                    send_message(
                        chat_id,
                        "Usage: /classify gor=<value> api=<value>\n"
                        "Example: /classify gor=3500 api=45"
                    )
                    continue
                send_message(chat_id, classify_fluid(kwargs["gor"], kwargs["api"]))
                continue

            # ── /calc ──
            if is_calc_cmd(text):
                parts = text.split(maxsplit=2)
                if len(parts) < 2:
                    types_list = ", ".join(EXACT_FORMULAS.keys())
                    send_message(
                        chat_id,
                        f"Usage: /calc <type> key=value key2=value2 ...\n"
                        f"Available types: {types_list}"
                    )
                    continue
                calc_type = parts[1].lower()
                kwargs = parse_kv_args(parts[2] if len(parts) > 2 else "")
                result = run_exact_calc(calc_type, **kwargs)
                send_message(chat_id, result or f"Unknown calculation type: '{calc_type}'")
                continue

            # ── /estimate ──
            if is_estimate_cmd(text):
                parts = text.split(maxsplit=2)
                if len(parts) < 2:
                    types_list = ", ".join(CORRELATIONS.keys())
                    send_message(
                        chat_id,
                        f"Usage: /estimate <type> key=value key2=value2 ...\n"
                        f"Available types: {types_list}"
                    )
                    continue
                calc_type = parts[1].lower()
                kwargs = parse_kv_args(parts[2] if len(parts) > 2 else "")
                result = run_correlation(calc_type, **kwargs)
                send_message(chat_id, result or f"Unknown correlation type: '{calc_type}'")
                continue

            # ── /convert ──
            if is_convert_cmd(text):
                m = re.match(
                    r"/convert\s+([-+]?\d*\.?\d+)\s+(\S+)\s+to\s+(\S+)",
                    text, re.IGNORECASE
                )
                if not m:
                    send_message(
                        chat_id,
                        "Usage: /convert <value> <from_unit> to <to_unit>\n"
                        "Example: /convert 5000 psi to bar\n"
                        "Example: /convert 10 ppg to sg"
                    )
                    continue
                value, from_u, to_u = float(m.group(1)), m.group(2), m.group(3)
                send_message(chat_id, run_unit_conversion(value, from_u, to_u))
                continue

            # ── /plot ──
            if is_plot_cmd(text):
                query = text[5:].strip().lower()
                if not query:
                    send_message(
                        chat_id,
                        "Usage: /plot <relationship>\n\n"
                        "Available:\n"
                        "bo, rs, bg, z/z-factor, viscosity/oil viscosity,\n"
                        "dropout/cvd (liquid dropout), cgr,\n"
                        "phase envelope/pt (P-T diagram),\n"
                        "oil density, vrel/cce, gas viscosity"
                    )
                    continue

                rel_key = PLOT_ALIASES.get(query)
                if not rel_key:
                    for alias, key in PLOT_ALIASES.items():
                        if alias in query:
                            rel_key = key
                            break

                if not rel_key:
                    send_message(
                        chat_id,
                        f"لم أتعرف على العلاقة '{query}'.\n\n"
                        "الخيارات المتاحة:\n"
                        "bo, rs, bg, z, viscosity, dropout, cgr, phase envelope,\n"
                        "oil density, vrel, gas viscosity"
                    )
                    continue

                base_response = format_plot_response(rel_key)
                send_message(chat_id, base_response)

                # Optional AI follow-up if a document is in context
                if context:
                    followup = ask_ai(
                        f"The user was given the deterministic /plot description for "
                        f"'{rel_key}' (physical shape per BLOCK 5). Now check the "
                        f"uploaded document: does it contain actual measured data for "
                        f"this relationship? If yes, summarize the values and compare "
                        f"to the expected shape. If no, say so in one line.",
                        context
                    )
                    send_message(chat_id, followup)
                continue

            # ── /check ──
            if is_check_cmd(text):
                body = text[6:].strip()
                p_match  = re.search(r"p=\[?([\d,\.\s]+)\]?", body)
                v_match  = re.search(r"v=\[?([\d,\.\s]+)\]?", body)
                pb_match = re.search(r"pb=([\d\.]+)", body)
                rel_word = body.split()[0].lower() if body else None

                rel_key  = PLOT_ALIASES.get(rel_word) if rel_word else None

                if not rel_key or not p_match or not v_match:
                    send_message(
                        chat_id,
                        "Usage: /check <relationship> p=p1,p2,p3 v=v1,v2,v3 pb=<value>\n\n"
                        "Example (Rs check):\n"
                        "/check rs p=500,1000,1500,2000 v=300,300,250,180 pb=1500\n\n"
                        "Example (liquid dropout):\n"
                        "/check dropout p=1000,2000,3000,4000 v=0,8,15,10 pb=4000"
                    )
                    continue

                pressures = [float(x) for x in p_match.group(1).split(",")]
                values    = [float(x) for x in v_match.group(1).split(",")]
                pb_or_pd  = float(pb_match.group(1)) if pb_match else None

                send_message(chat_id, check_pvt_trend(rel_key, pressures, values, pb_or_pd))
                continue

            # ── /pvto ──
            if is_pvto_cmd(text):
                send_message(chat_id, generate_pvto_skeleton())
                if context:
                    followup = ask_ai(
                        "Using the uploaded document, check if Rs(P), Bo(P), and "
                        "mu_o(P) data from Differential Liberation are present. "
                        "Summarize the values if found. List exactly what is missing "
                        "if incomplete. State whether a Separator Test correction is "
                        "required to convert DV data to field Bo/Rs.",
                        context
                    )
                    send_message(chat_id, followup)
                continue

            # ── /pvdo ──
            if is_pvdo_cmd(text):
                send_message(chat_id, generate_pvdo_skeleton())
                if context:
                    followup = ask_ai(
                        "Using the uploaded document, check if Bo(P) and mu_o(P) "
                        "data are present for a dead oil PVDO table. "
                        "Confirm that Rs is negligible (dead oil condition). "
                        "List exactly what is missing if incomplete.",
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
                        "Summarize the values if found. State whether PVDG "
                        "(dry gas, no Rv) would be more appropriate based on the data.",
                        context
                    )
                    send_message(chat_id, followup)
                continue

            # ── /pvdg ──
            if is_pvdg_cmd(text):
                send_message(chat_id, generate_pvdg_skeleton())
                if context:
                    followup = ask_ai(
                        "Using the uploaded document, check if Bg(P) and mu_g(P) "
                        "data are present for a dry gas PVDG table. "
                        "Confirm that Rv (vaporized oil) is negligible. "
                        "List exactly what is missing if incomplete.",
                        context
                    )
                    send_message(chat_id, followup)
                continue

            # ── /export_sim ──
            if is_export_sim_cmd(text):
                body = text[len("/export_sim"):].strip().lower()
                if not body:
                    send_message(
                        chat_id,
                        "Usage: /export_sim <fluid_type> [near_critical]\n\n"
                        "Fluid types:\n"
                        "  black oil, volatile oil, gas condensate, wet gas, dry gas\n"
                        "  (أو بالعربي: زيت أسود، زيت متطاير، غاز مكثف، غاز رطب، غاز جاف)\n\n"
                        "Example: /export_sim gas condensate near_critical"
                    )
                    continue
                near_critical = "near_critical" in body or "near critical" in body
                fluid_str = body.replace("near_critical", "").replace("near critical", "").strip()
                send_message(chat_id, export_sim_decision(fluid_str, near_critical))
                continue

            # ── /analyze ──
            if is_analyze_cmd(text):
                if not context:
                    send_message(chat_id, "لا يوجد ملف مرفوع. أرسل PDF أو DOCX أولاً.")
                    continue
                prompt = (
                    "قم بتحليل هذا التقرير الهندسي بشكل كامل واحترافي:\n\n"
                    "1. نوع العينة ونوع السائل (استخدم BLOCK 6 للتصنيف إن توفرت GOR/API)\n"
                    "2. الاختبارات المنفذة وجودتها (راجع تسلسل BLOCK 7)\n"
                    "3. القيم الرئيسية (Pb/Pd، Bo، Rs، API، Viscosity، Bg، Z)\n"
                    "4. تحقق من اتساق الاتجاهات مع BLOCK 5:\n"
                    "   - إذا ظهر Bo يزداد تحت Pb: هذا غير فيزيائي، أذكره صراحة\n"
                    "   - إذا ظهر Rs يزداد فوق Pb: هذا خطأ، أذكره صراحة\n"
                    "   أي تناقض مع BLOCK 5 أذكره كـ POSSIBLE DATA QUALITY ISSUE\n"
                    "5. توصيات للمحاكاة (PVTO/PVDO/PVTG/PVDG/Compositional حسب BLOCK 11)\n"
                    "6. البيانات الناقصة (DATA REQUIRED)\n"
                    "7. الخلاصة الهندسية في سطر واحد"
                )
                send_message(chat_id, ask_ai(prompt, context))
                continue

            # ── /graph or /interpret_graph ──
            if is_graph_cmd(text):
                img = IMAGE_CONTEXT.get(chat_id)
                if not img:
                    send_message(chat_id, "أرسل صورة الرسم أولاً ثم اكتب /graph.")
                    continue
                prompt = build_graph_prompt(text)
                send_message(chat_id, ask_vision_ai(prompt, img, context))
                continue

            # ── /eclipse ──
            if is_eclipse_cmd(text):
                query = text[len("/eclipse"):].strip()
                prompt = (
                    (query if query else "General Eclipse guidance request") + "\n\n"
                    "قدم إرشادات Eclipse منظمة:\n"
                    "- حدد جدول PVT المناسب (PVTO/PVDO/PVTG/PVDG) وسبب الاختيار (BLOCK 11)\n"
                    "- الكلمات المفتاحية ذات الصلة في Eclipse\n"
                    "- تحقق من الوحدات والاتساق\n"
                    "- قرار Black-Oil (E100) vs Compositional (E300) حسب BLOCK 6\n"
                    "- البيانات الناقصة إن وجدت (DATA REQUIRED)"
                )
                send_message(chat_id, ask_ai(prompt, context))
                continue

            # ── /cmg ──
            if is_cmg_cmd(text):
                query = text[len("/cmg"):].strip()
                prompt = (
                    (query if query else "General CMG guidance request") + "\n\n"
                    "قدم إرشادات CMG منظمة:\n"
                    "- حدد ما إذا كان IMEX (Black-Oil) أو GEM (Compositional/EOS) هو الأنسب\n"
                    "  بناءً على BLOCK 6 (نوع السائل) و BLOCK 11 (متطلبات البيانات)\n"
                    "- متطلبات بيانات PVT لكل خيار\n"
                    "- EOS Tuning إذا كان GEM هو الخيار\n"
                    "- البيانات الناقصة إن وجدت (DATA REQUIRED)"
                )
                send_message(chat_id, ask_ai(prompt, context))
                continue

            # ── Surface separator keyword shortcut ──
            if is_surface_separator(text):
                send_message(chat_id, surface_separator_answer())
                continue

            # ── Default: AI response ──
            send_message(chat_id, ask_ai(text, context))

    except Exception as e:
        print(f"Main loop error: {e}")

    time.sleep(1)
