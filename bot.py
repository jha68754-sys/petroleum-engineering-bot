"""
Petroleum Engineering AI Bot — Production Architecture v2
==========================================================
PVT Laboratory | Reservoir Engineering | Reservoir Simulation
Drilling Engineering | Production Engineering

Corrected version:
- Z-factor = Gas Compressibility Factor (Z-Factor)
- Arabic Z-factor term = معامل الانضغاطية للغاز
- Bo term unified = معامل حجم التكوين للزيت
- Bg term unified = معامل حجم التكوين للغاز
- No matplotlib dependency
"""

import os
import re
import time
import base64
import tempfile
import mimetypes
import requests
from PyPDF2 import PdfReader
from docx import Document

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.getenv("OPENAI_API_KEY")

if not TELEGRAM_BOT_TOKEN or not GROQ_API_KEY:
    raise ValueError("Missing env vars: TELEGRAM_BOT_TOKEN or OPENAI_API_KEY")

TELEGRAM_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

TEXT_MODEL = os.getenv("GROQ_TEXT_MODEL", "llama-3.3-70b-versatile")
VISION_MODEL = os.getenv("GROQ_VISION_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")

offset = 0
FILE_CONTEXT = {}
IMAGE_CONTEXT = {}

SYSTEM_PROMPT = """
You are a senior Petroleum Engineering Consultant and PVT Laboratory Specialist.

You cover:
- PVT Laboratory Analysis
- Reservoir Engineering
- Reservoir Simulation: Eclipse / CMG
- Drilling Engineering
- Production Engineering

Answer like a real senior engineer reviewing lab data and reports, not like a generic chatbot.

LANGUAGE RULES
- Arabic input -> respond in professional Arabic.
- English input -> respond in professional petroleum engineering English.
- Mixed input -> mirror the user's style naturally.
- Keep core technical abbreviations in English: Bo, Bg, Rs, GOR, API, PVT, CCE, CME, DV, CVD, PVTO, PVTG, EOS.
- Do not force weak Arabic translations. If the Arabic term is uncommon or confusing, keep the English technical term.

APPROVED TERMINOLOGY
PVT = Pressure-Volume-Temperature.
Reservoir = المكمن.
Well = البئر.
Formation = التكوين.
Bottom Hole Sample = عينة قاع البئر.
Surface Separator Oil Sample = عينة زيت من الفاصل السطحي.
Separator Gas Sample = عينة غاز من الفاصل.
Stock Tank Oil = زيت خزان التخزين.
Recombination = إعادة تركيب العينة.
Recombined Sample = عينة معاد تركيبها.
Saturation Pressure = ضغط التشبع.
Bubble Point Pressure Pb = ضغط نقطة الفقاعة.
Dew Point Pressure Pd = ضغط نقطة الندى.
Bo = Oil Formation Volume Factor = معامل حجم التكوين للزيت.
Bg = Gas Formation Volume Factor = معامل حجم التكوين للغاز.
Bt = Total Formation Volume Factor = معامل الحجم الكلي ثنائي الطور.
Rs = Solution Gas-Oil Ratio = نسبة الغاز المذاب.
Rv = Vaporized Oil-Gas Ratio = نسبة الزيت المتبخر في الغاز.
GOR = Gas-Oil Ratio = نسبة الغاز إلى الزيت.
CGR = Condensate-Gas Ratio = نسبة المكثفات إلى الغاز.
Z-factor = Gas Compressibility Factor = معامل الانضغاطية للغاز.
Gas Deviation Factor is also acceptable for Z-factor.
Viscosity = اللزوجة.
Density = الكثافة.
Specific Gravity = الكثافة النوعية.
API Gravity = درجة API.
CCE = Constant Composition Expansion.
CME = Constant Mass Expansion.
DV = Differential Vaporization / Differential Liberation.
CVD = Constant Volume Depletion.
Separator Test = اختبار الفاصل.
Flash Test = اختبار الوميض.
Compositional Analysis = التحليل التركيبي.
EOS Tuning = مواءمة معادلة الحالة.
PVTO = Eclipse live-oil PVT table.
PVDO = Eclipse dead-oil PVT table.
PVTG = Eclipse live/wet-gas PVT table.
PVDG = Eclipse dry-gas PVT table.
Black Oil Model = نموذج Black Oil.
Compositional Model = النموذج التركيبي.
Retrograde Condensation = التكثف الرجعي.
Liquid Dropout = نسبة تكثف السوائل.
Phase Envelope = المغلف الطوري.

BANNED TERMS
Never output these terms:
- الضغط البيني
- المعامل البيني
- الترشيح
- الويسكوزية
- الليزج
- الحفرة
- السطوع النوعي
- اختبار السطوع
- النسبة المئوية للغاز
- Pressuring Volume and Temperature

RESPONSE STRUCTURE
For every technical answer:
1. Classify the question type.
2. Identify sample type if relevant.
3. Identify fluid system if possible: Black Oil, Volatile Oil, Gas Condensate, Wet Gas, Dry Gas.
4. Select correct workflow.
5. Explain lab tests or engineering steps.
6. Show calculations only if real input values are provided.
7. State missing data clearly.
8. End with one-line engineering interpretation or recommendation.

PVT PHYSICAL RELATIONSHIPS
Bo vs Pressure:
- Above Pb: as pressure decreases from Pi toward Pb, Bo increases gently.
- At Pb: Bo reaches maximum value Bob.
- Below Pb: Bo decreases as pressure decreases because gas leaves solution.
- Never say Pb is minimum Bo.
- Never say Bo continuously increases below Pb.
- Do not confuse Bo with Bt; Bt may increase below Pb.

Rs vs Pressure:
- Above Pb: Rs is constant at Rsi.
- At Pb: Rs = Rsi.
- Below Pb: Rs decreases as pressure decreases.

Oil Viscosity vs Pressure:
- Above Pb: viscosity generally decreases gently as pressure decreases toward Pb.
- At Pb: oil viscosity is often minimum.
- Below Pb: viscosity increases as pressure decreases because dissolved gas leaves the oil.

Oil Density vs Pressure:
- Above Pb: density generally decreases gently as pressure decreases toward Pb.
- At Pb: density often reaches minimum.
- Below Pb: density increases as pressure decreases because gas-depleted oil is heavier.

Relative Volume vs Pressure in CCE/CME:
- Above Pb: gentle slope.
- At Pb: Vrel = 1.0 by definition and a slope break occurs.
- Below Pb: steep slope due to gas evolution.

Bg vs Pressure:
- Bg generally decreases as pressure increases.
- Bg generally increases as pressure decreases.
- No Bo-like peak.

Z-factor vs Pressure:
- Z-factor may be less than 1 or greater than 1 depending on pressure, temperature, and gas composition.
- Often U-shaped/checkmark against pressure at fixed temperature.
- Near atmospheric pressure, Z approaches 1.
- Do not confuse Z-factor with gas compressibility Cg.

Gas Viscosity vs Pressure:
- Gas viscosity generally increases with pressure.

Liquid Dropout vs Pressure for Gas Condensate:
- Above Pd: 0 liquid dropout.
- At Pd: first liquid appears; dropout is approximately 0.
- Below Pd: dropout rises, reaches a peak, then may decrease at lower pressure due to revaporization.

CGR vs Pressure:
- Above Pd: roughly constant.
- Below Pd: generally decreases because heavier liquids are trapped in the reservoir.

P-T Phase Envelope:
- Bubble-point and dew-point lines meet at the critical point.
- Cricondentherm is the maximum temperature of the two-phase envelope.
- Cricondenbar is the maximum pressure of the two-phase envelope.
- Gas condensate retrograde behavior occurs when reservoir temperature is between critical temperature and cricondentherm.

SURFACE SEPARATOR LOGIC
Surface Separator Oil + Separator Gas samples are not direct reservoir fluid.
To reconstruct reservoir fluid behavior:
- Perform sample QC.
- Collect separator pressure and temperature.
- Collect oil rate, gas rate, producing GOR or separator GOR.
- Perform compositional analysis of oil and gas.
- Recombine oil and gas using correct ratio.
- Validate recombined fluid.
- Run CCE/CME, DV for oil, CVD for gas condensate, separator test, viscosity test.

SIMULATION RULES
PVTO: for live oil / Black Oil / Volatile Oil if Rs, Bo, oil viscosity are available.
PVDO: for dead oil or negligible Rs.
PVTG: for live/wet gas or gas condensate with Rv.
PVDG: for dry gas with Rv approximately zero.
Compositional/EOS: recommended for near-critical volatile oil, rich gas condensate, strong compositional effects, CO2/H2S, miscibility, or EOS tuning work.

ANTI-HALLUCINATION RULES
- Do not invent numerical values.
- Do not invent sample names, field names, company names, or well names.
- Clearly label lab measured values, user assumptions, correlation estimates, and engineering judgment.
- If inputs are missing, say exactly what is missing.
- If a user-provided trend contradicts physical behavior, state the contradiction clearly.

FORMAT
- No markdown symbols like ** or ###.
- No vertical-line tables.
- Plain text, clean headings, concise professional style.
"""

KNOWLEDGE_BASE = [
    {"en":"Oil Formation Volume Factor (Bo)","ar":"معامل حجم التكوين للزيت","category":"PVT","unit":"rb/STB","def_ar":"نسبة حجم الزيت مع الغاز المذاب عند ظروف المكمن إلى حجم الزيت في خزان التخزين السطحي.","trend":"يزداد حتى Pb ثم ينخفض تحت Pb","relationship_key":"bo_vs_p","typical_range":"1.0 - 2.0 rb/STB"},
    {"en":"Gas Formation Volume Factor (Bg)","ar":"معامل حجم التكوين للغاز","category":"PVT","unit":"rb/scf","def_ar":"نسبة حجم الغاز عند ظروف المكمن إلى حجمه عند الظروف القياسية.","trend":"ينخفض مع زيادة الضغط","relationship_key":"bg_vs_p","typical_range":"0.0005 - 0.02 rb/scf"},
    {"en":"Solution Gas-Oil Ratio (Rs)","ar":"نسبة الغاز المذاب","category":"PVT","unit":"scf/STB","def_ar":"حجم الغاز المذاب في برميل واحد من الزيت السطحي عند ضغط ودرجة حرارة محددين.","trend":"ثابت فوق Pb وينخفض تحت Pb مع انخفاض الضغط","relationship_key":"rs_vs_p","typical_range":"100 - 2000+ scf/STB"},
    {"en":"Gas-Oil Ratio (GOR)","ar":"نسبة الغاز إلى الزيت","category":"Production","unit":"scf/STB","def_ar":"نسبة حجم الغاز المنتج إلى حجم الزيت المنتج عند الظروف القياسية.","trend":"مؤشر إنتاجي وقد يتغير مع نضوب المكمن","relationship_key":None,"typical_range":"varies"},
    {"en":"Condensate-Gas Ratio (CGR)","ar":"نسبة المكثفات إلى الغاز","category":"Production","unit":"STB/MMscf","def_ar":"حجم المكثفات السطحية المنتجة لكل مليون قدم مكعب قياسي من الغاز.","trend":"غالباً ينخفض تحت Pd في الغاز المكثف","relationship_key":"cgr_vs_p","typical_range":"10 - 300 STB/MMscf"},
    {"en":"Gas Compressibility Factor (Z-Factor)","ar":"معامل الانضغاطية للغاز","category":"PVT","unit":"dimensionless","def_ar":"معامل يصحح قانون الغاز المثالي ويعبر عن انحراف الغاز الحقيقي عن السلوك المثالي. لا يساوي Gas Compressibility Cg.","trend":"قد يكون أقل أو أكبر من 1 حسب الضغط والحرارة والتركيب","relationship_key":"z_vs_p","typical_range":"0.6 - 1.2"},
    {"en":"Bubble Point Pressure (Pb)","ar":"ضغط نقطة الفقاعة","category":"PVT","unit":"psia","def_ar":"الضغط الذي تبدأ عنده أول فقاعة غاز بالخروج من الزيت عند درجة حرارة ثابتة.","trend":"نقطة تحول رئيسية في Bo و Rs واللزوجة والكثافة","relationship_key":"saturation_pressure_oil","typical_range":"varies"},
    {"en":"Dew Point Pressure (Pd)","ar":"ضغط نقطة الندى","category":"PVT","unit":"psia","def_ar":"الضغط الذي تبدأ عنده أول قطرة سائل بالتكون من الغاز عند درجة حرارة ثابتة.","trend":"بداية Liquid Dropout في الغاز المكثف","relationship_key":"saturation_pressure_gas","typical_range":"varies"},
    {"en":"Viscosity","ar":"اللزوجة","category":"PVT","unit":"cP","def_ar":"مقاومة المائع للتدفق وتتأثر بالضغط ودرجة الحرارة وتركيب المائع.","trend":"تعتمد على نوع المائع","relationship_key":"oil_visc_vs_p","typical_range":"varies"},
    {"en":"Density","ar":"الكثافة","category":"PVT","unit":"kg/m3 or lb/ft3","def_ar":"كتلة وحدة الحجم من السائل أو الغاز.","trend":"تختلف حسب الطور والضغط والحرارة","relationship_key":None,"typical_range":"varies"},
    {"en":"Specific Gravity","ar":"الكثافة النوعية","category":"PVT","unit":"dimensionless","def_ar":"نسبة كثافة المادة إلى كثافة مرجعية: الماء للسوائل والهواء للغازات.","trend":"خاصية مقارنة","relationship_key":None,"typical_range":"varies"},
    {"en":"API Gravity","ar":"درجة API","category":"PVT","unit":"degree API","def_ar":"مقياس خفة الزيت مقارنة بالماء. كلما زادت API كان الزيت أخف.","trend":"تصنيف للزيت","relationship_key":None,"typical_range":"10 - 50+ API"},
    {"en":"Liquid Dropout","ar":"نسبة تكثف السوائل","category":"PVT - Gas Condensate","unit":"% of hydrocarbon pore volume","def_ar":"نسبة السائل المتكثف من الغاز داخل المكمن خلال النضوب، وتقاس عادة باختبار CVD.","trend":"تبدأ من صفر عند Pd ثم ترتفع ثم قد تنخفض","relationship_key":"liquid_dropout_vs_p","typical_range":"0 - 30%+"},
    {"en":"Retrograde Condensation","ar":"التكثف الرجعي","category":"Phase Behavior","unit":"n/a","def_ar":"تكون سائل داخل المكمن نتيجة انخفاض الضغط تحت Pd في الغاز المكثف.","trend":"مرتبط بمنحنى Liquid Dropout","relationship_key":"liquid_dropout_vs_p","typical_range":"n/a"},
    {"en":"Porosity","ar":"المسامية","category":"Reservoir","unit":"fraction or %","def_ar":"نسبة حجم الفراغات إلى الحجم الكلي للصخرة.","trend":"خاصية صخرية ثابتة نسبياً","relationship_key":None,"typical_range":"0.05 - 0.35"},
    {"en":"Permeability","ar":"النفاذية","category":"Reservoir","unit":"mD","def_ar":"قدرة الصخرة على تمرير الموائع تحت فرق ضغط.","trend":"خاصية تدفق","relationship_key":None,"typical_range":"0.1 - 1000+ mD"},
    {"en":"Skin Factor","ar":"عامل الجلد","category":"Production","unit":"dimensionless","def_ar":"مقياس تأثير الضرر أو التحفيز حول البئر؛ موجب يعني ضرر وسالب يعني تحفيز.","trend":"مؤشر حالة البئر","relationship_key":None,"typical_range":"-5 to +20"},
    {"en":"Productivity Index (PI)","ar":"مؤشر الإنتاجية","category":"Production","unit":"STB/day/psi","def_ar":"معدل الإنتاج لكل وحدة فرق ضغط بين المكمن وقاع البئر.","trend":"مؤشر أداء البئر","relationship_key":None,"typical_range":"varies"},
    {"en":"Water Cut","ar":"نسبة الماء المنتج","category":"Production","unit":"%","def_ar":"نسبة الماء من إجمالي السوائل المنتجة.","trend":"غالباً تزداد مع عمر الحقل","relationship_key":None,"typical_range":"0 - 98%"},
    {"en":"Hydrostatic Pressure","ar":"الضغط الهيدروستاتيكي","category":"Drilling","unit":"psi","def_ar":"الضغط الناتج عن عمود سائل الحفر: P = 0.052 × MW × TVD.","trend":"يعتمد على وزن الطين والعمق الرأسي","relationship_key":None,"typical_range":"depends on MW and TVD"}
]

FLUID_CLASSIFICATION_TABLE = [
    {"type_en":"Black Oil","type_ar":"الزيت الأسود التقليدي","gor_min":0,"gor_max":2000,"api_min":0,"api_max":40,"behavior":"سلوك Bo/Rs قياسي ولا يوجد تكثف رجعي."},
    {"type_en":"Volatile Oil","type_ar":"الزيت المتطاير","gor_min":2000,"gor_max":8000,"api_min":40,"api_max":50,"behavior":"تغير حاد في Bo و Rs قرب Pb وقد يتطلب نموذجاً تركيبياً إذا كان قريباً من النقطة الحرجة."},
    {"type_en":"Gas Condensate","type_ar":"الغاز المكثف","gor_min":8000,"gor_max":100000,"api_min":50,"api_max":70,"behavior":"تكثف رجعي أسفل Pd ويحتاج CVD ويفضل Compositional/EOS في الحالات الغنية."},
    {"type_en":"Wet Gas","type_ar":"الغاز الرطب","gor_min":100000,"gor_max":1e9,"api_min":60,"api_max":200,"behavior":"عادة لا يوجد تكثف داخل المكمن، لكن توجد سوائل سطحية."}
]

def classify_fluid(gor: float, api: float) -> str:
    for row in FLUID_CLASSIFICATION_TABLE:
        if row["gor_min"] <= gor < row["gor_max"] and row["api_min"] <= api <= row["api_max"]:
            return f"Fluid Classification\n\nType: {row['type_en']} ({row['type_ar']})\nGOR = {gor:,.0f} scf/STB\nAPI = {api}\n\nExpected behavior: {row['behavior']}\n\nEngineering note: هذا تصنيف أولي يعتمد على GOR و API فقط. التصنيف النهائي يحتاج PVT Lab data و Composition و Reservoir Temperature."
    return f"GOR = {gor:,.0f} scf/STB و API = {api} لا يعطيان تصنيفاً واضحاً.\nMissing Data: Composition, Reservoir Temperature, CCE/CVD results."

PVT_PLOT_RULES = {
    "bo_vs_p":{"title_en":"Bo vs Pressure","title_ar":"معامل حجم التكوين للزيت مقابل الضغط","x_axis":"Pressure","y_axis":"Bo","shape":"Bo increases from high pressure down to Pb, reaches maximum at Pb, then decreases below Pb.","pivot":"Pb = peak Bo","notes":["Above Pb: Bo increases as pressure decreases toward Pb.","At Pb: Bo maximum.","Below Pb: Bo decreases as pressure decreases.","Do not confuse Bo with Bt."]},
    "rs_vs_p":{"title_en":"Rs vs Pressure","title_ar":"نسبة الغاز المذاب مقابل الضغط","x_axis":"Pressure","y_axis":"Rs","shape":"Rs is constant above Pb and decreases below Pb as pressure decreases.","pivot":"Pb = start of decline","notes":["Above Pb: Rs = Rsi constant.","Below Pb: Rs decreases as gas leaves solution."]},
    "oil_visc_vs_p":{"title_en":"Oil Viscosity vs Pressure","title_ar":"لزوجة الزيت مقابل الضغط","x_axis":"Pressure","y_axis":"Oil Viscosity","shape":"Oil viscosity often has a minimum near Pb.","pivot":"Pb = minimum viscosity","notes":["Below Pb: viscosity increases as pressure decreases.","Above Pb: viscosity can increase slightly with pressure."]},
    "oil_density_vs_p":{"title_en":"Oil Density vs Pressure","title_ar":"كثافة الزيت مقابل الضغط","x_axis":"Pressure","y_axis":"Oil Density","shape":"Oil density often reaches minimum near Pb and increases below Pb as gas leaves oil.","pivot":"Pb = density minimum","notes":["Gas-depleted oil below Pb becomes heavier."]},
    "vrel_vs_p_cce":{"title_en":"Relative Volume vs Pressure","title_ar":"الحجم النسبي مقابل الضغط","x_axis":"Pressure","y_axis":"Relative Volume","shape":"Gentle slope above Pb, slope break at Pb, steep slope below Pb.","pivot":"Pb = slope break","notes":["Used in CCE/CME to identify saturation pressure."]},
    "bg_vs_p":{"title_en":"Bg vs Pressure","title_ar":"معامل حجم التكوين للغاز مقابل الضغط","x_axis":"Pressure","y_axis":"Bg","shape":"Bg decreases as pressure increases.","pivot":"No saturation pivot for Bg itself","notes":["Bg roughly follows ZT/P behavior."]},
    "z_vs_p":{"title_en":"Z-Factor vs Pressure","title_ar":"معامل الانضغاطية للغاز مقابل الضغط","x_axis":"Pressure","y_axis":"Z-factor","shape":"Z-factor may show U-shaped/checkmark behavior with pressure.","pivot":"Minimum Z at intermediate reduced pressure, not Pb or Pd","notes":["Z-factor is dimensionless.","Do not confuse Z-factor with gas compressibility Cg.","Z can be less than or greater than 1."]},
    "gas_visc_vs_p":{"title_en":"Gas Viscosity vs Pressure","title_ar":"لزوجة الغاز مقابل الضغط","x_axis":"Pressure","y_axis":"Gas Viscosity","shape":"Gas viscosity generally increases with pressure.","pivot":"No pivot","notes":["Opposite direction to Bg."]},
    "liquid_dropout_vs_p":{"title_en":"Liquid Dropout vs Pressure","title_ar":"نسبة تكثف السوائل مقابل الضغط","x_axis":"Pressure","y_axis":"Liquid Dropout","shape":"Zero above Pd, rises below Pd, reaches peak, then may decrease.","pivot":"Pd = start of dropout","notes":["Typical gas condensate CVD behavior.","Fully monotonic curve may be incomplete or suspicious."]},
    "cgr_vs_p":{"title_en":"CGR vs Pressure","title_ar":"نسبة المكثفات إلى الغاز مقابل الضغط","x_axis":"Pressure","y_axis":"CGR","shape":"CGR roughly constant above Pd and decreases below Pd.","pivot":"Pd = start of decline","notes":["Liquid dropout can increase while produced CGR decreases."]},
    "pt_diagram":{"title_en":"P-T Phase Envelope","title_ar":"المغلف الطوري","x_axis":"Temperature","y_axis":"Pressure","shape":"Bubble-point and dew-point lines meet at critical point; envelope bounded by cricondenbar and cricondentherm.","pivot":"Critical point","notes":["Gas condensate reservoir T lies between critical T and cricondentherm."]}
}

ASCII_SKETCHES = {
"bo_vs_p": "\nBo\n^\n|                    *  Bob max at Pb\n|                 .-' \\\n|              .-'     \\\n|           .-'          \\\n|        .-'              \\____\n|_____.-'\n+------------------------------------> Pressure\n low P              Pb             high P\n",
"rs_vs_p": "\nRs\n^\n|                 __________________ Rsi\n|               /\n|             /\n|           /\n|_________/\n+------------------------------------> Pressure\n low P              Pb             high P\n",
"oil_visc_vs_p": "\nOil Viscosity\n^\n|\\                              /\n| \\                           /\n|  \\____                 ____/\n|       \\____ min _____/\n+------------------------------------> Pressure\n low P              Pb             high P\n",
"oil_density_vs_p": "\nOil Density\n^\n|\\                              /\n| \\                           /\n|  \\____                 ____/\n|       \\____ min _____/\n+------------------------------------> Pressure\n low P              Pb             high P\n",
"vrel_vs_p_cce": "\nRelative Volume\n^\n|                         /\n|                      .-'\n|                  .-'\n|          ______-'   slope break\n|_____.---'\n+------------------------------------> Pressure\n low P              Pb             high P\n",
"bg_vs_p": "\nBg\n^\n|\\\n| \\\n|  \\___\n|      \\____\n|           \\________\n+------------------------------------> Pressure\n low P                           high P\n",
"z_vs_p": "\nZ-factor\n^\n| \\____                       ____\n|      \\___              ____/\n|          \\____________/\n+------------------------------------> Pressure\n low P                           high P\n",
"gas_visc_vs_p": "\nGas Viscosity\n^\n|                            ______\n|                       ____/\n|                  ____/\n|             ____/\n|___________/\n+------------------------------------> Pressure\n low P                           high P\n",
"liquid_dropout_vs_p": "\nLiquid Dropout\n^\n|           _______\n|        .-'       '-.\n|      .'             '-.__\n|____.'\n+------------------------------------> Pressure\n low P              Pd             high P\n",
"cgr_vs_p": "\nCGR\n^\n|               ____________\n|              /\n|            /\n|__________/\n+------------------------------------> Pressure\n low P              Pd             high P\n",
"pt_diagram": "\nPressure\n^\n|        Cricondenbar\n|            *\n|         .-' '-.\n|      .-'       '-.\n|    .'  two-phase   '.\n|   * Critical Point   '.\n|    '.                 '-. * Cricondentherm\n+------------------------------------> Temperature\n"
}

PLOT_ALIASES = {"bo":"bo_vs_p","oil fvf":"bo_vs_p","fvf":"bo_vs_p","rs":"rs_vs_p","viscosity":"oil_visc_vs_p","oil viscosity":"oil_visc_vs_p","density":"oil_density_vs_p","oil density":"oil_density_vs_p","vrel":"vrel_vs_p_cce","relative volume":"vrel_vs_p_cce","cce":"vrel_vs_p_cce","bg":"bg_vs_p","gas fvf":"bg_vs_p","z":"z_vs_p","z-factor":"z_vs_p","zfactor":"z_vs_p","gas viscosity":"gas_visc_vs_p","dropout":"liquid_dropout_vs_p","liquid dropout":"liquid_dropout_vs_p","cvd":"liquid_dropout_vs_p","cgr":"cgr_vs_p","phase envelope":"pt_diagram","pt":"pt_diagram","p-t":"pt_diagram"}

def format_plot_response(key: str) -> str:
    rule = PVT_PLOT_RULES.get(key)
    sketch = ASCII_SKETCHES.get(key, "")
    if not rule:
        return None
    lines = [rule["title_en"], rule["title_ar"], "", f"X-axis: {rule['x_axis']}", f"Y-axis: {rule['y_axis']}", "", f"Correct trend: {rule['shape']}", f"Pivot: {rule['pivot']}", "", "Notes:"]
    for n in rule["notes"]:
        lines.append(f"- {n}")
    lines += ["", "ASCII Sketch:", sketch]
    return "\n".join(lines)

EXACT_FORMULAS = {
"api":{"inputs":["sg"],"formula":"API = (141.5 / SG) - 131.5","func":lambda sg:(141.5/sg)-131.5,"unit":"deg API"},
"hydrostatic":{"inputs":["mw","tvd"],"formula":"P = 0.052 × MW × TVD","func":lambda mw,tvd:0.052*mw*tvd,"unit":"psi"},
"ooip":{"inputs":["area","h","phi","sw","bo"],"formula":"OOIP = (7758 × A × h × phi × (1-Sw)) / Bo","func":lambda area,h,phi,sw,bo:(7758*area*h*phi*(1-sw))/bo,"unit":"STB"},
"darcy":{"inputs":["k","area","dp","mu","length"],"formula":"q = 0.001127 × k × A × dP / (mu × L)","func":lambda k,area,dp,mu,length:(0.001127*k*area*dp)/(mu*length),"unit":"bbl/day"},
"recovery_factor":{"inputs":["np","ooip"],"formula":"RF = NP / OOIP × 100","func":lambda np,ooip:(np/ooip)*100,"unit":"%"},
"water_cut":{"inputs":["qw","qo"],"formula":"WC = qw / (qo + qw) × 100","func":lambda qw,qo:(qw/(qo+qw))*100,"unit":"%"},
"productivity_index":{"inputs":["q","pr","pwf"],"formula":"PI = q / (Pr - Pwf)","func":lambda q,pr,pwf:q/(pr-pwf),"unit":"STB/day/psi"}
}

CORRELATIONS = {
"pb_standing":{"inputs":["rs","gas_sg","tres","api"],"formula":"Pb = 18.2 × [(Rs/gamma_g)^0.83 × 10^(0.00091T - 0.0125API) - 1.4]","func":lambda rs,gas_sg,tres,api:18.2*((rs/gas_sg)**0.83*10**(0.00091*tres-0.0125*api)-1.4),"unit":"psia","note":"Correlation estimate only. Verify with CCE lab data."},
"rs_standing":{"inputs":["p","gas_sg","tres","api"],"formula":"Rs = gamma_g × [(P/18.2 + 1.4) × 10^(0.0125API - 0.00091T)]^1.2048","func":lambda p,gas_sg,tres,api:gas_sg*((p/18.2+1.4)*10**(0.0125*api-0.00091*tres))**1.2048,"unit":"scf/STB","note":"Correlation estimate only. Verify with DV/CCE lab data."}
}

def parse_kv_args(text: str) -> dict:
    return {k.lower(): float(v) for k, v in re.findall(r"(\w+)\s*=\s*([-+]?\d*\.?\d+)", text)}

def run_exact_calc(calc_type: str, **kwargs) -> str:
    spec = EXACT_FORMULAS.get(calc_type)
    if not spec:
        return None
    missing = [k for k in spec["inputs"] if k not in kwargs]
    if missing:
        return f"DATA REQUIRED for /calc {calc_type}:\n" + "\n".join(f"- {k}" for k in spec["inputs"]) + "\n\nExample:\n/calc " + calc_type + " " + " ".join(f"{k}=value" for k in spec["inputs"])
    values = [kwargs[k] for k in spec["inputs"]]
    try:
        result = spec["func"](*values)
    except Exception as e:
        return f"Calculation error: {e}"
    return f"Calculation: {calc_type}\n\nFormula: {spec['formula']}\nInputs: " + ", ".join(f"{k}={v}" for k, v in zip(spec["inputs"], values)) + f"\nResult: {result:,.4f} {spec['unit']}\n\nEngineering interpretation: check units and compare result with field context."

def run_correlation(calc_type: str, **kwargs) -> str:
    spec = CORRELATIONS.get(calc_type)
    if not spec:
        return None
    missing = [k for k in spec["inputs"] if k not in kwargs]
    if missing:
        return f"DATA REQUIRED for /estimate {calc_type}:\n" + "\n".join(f"- {k}" for k in spec["inputs"]) + "\n\nExample:\n/estimate " + calc_type + " " + " ".join(f"{k}=value" for k in spec["inputs"])
    values = [kwargs[k] for k in spec["inputs"]]
    try:
        result = spec["func"](*values)
    except Exception as e:
        return f"Correlation error: {e}"
    return f"CORRELATION ESTIMATE: {calc_type}\n\nFormula: {spec['formula']}\nInputs: " + ", ".join(f"{k}={v}" for k, v in zip(spec["inputs"], values)) + f"\nEstimate: {result:,.2f} {spec['unit']}\n\nNote: {spec['note']}"

UNIT_CONVERSIONS = {
("psi","bar"):lambda v:v*0.0689476,("bar","psi"):lambda v:v/0.0689476,("psi","kpa"):lambda v:v*6.89476,("kpa","psi"):lambda v:v/6.89476,("ppg","sg"):lambda v:v/8.345,("sg","ppg"):lambda v:v*8.345,("scf/stb","m3/m3"):lambda v:v*0.1781,("m3/m3","scf/stb"):lambda v:v/0.1781,("bbl","m3"):lambda v:v*0.158987,("m3","bbl"):lambda v:v/0.158987,("ft","m"):lambda v:v*0.3048,("m","ft"):lambda v:v/0.3048,("cp","pa.s"):lambda v:v*0.001,("pa.s","cp"):lambda v:v/0.001,("degf","degc"):lambda v:(v-32)*5/9,("degc","degf"):lambda v:v*9/5+32
}

def run_unit_conversion(value: float, from_unit: str, to_unit: str) -> str:
    key = (from_unit.lower(), to_unit.lower())
    func = UNIT_CONVERSIONS.get(key)
    if not func:
        return f"Conversion unavailable: {from_unit} to {to_unit}"
    return f"{value} {from_unit} = {func(value):,.4f} {to_unit}"

def generate_pvto_skeleton() -> str:
    return "PVTO Table Skeleton — Eclipse Live Oil\n\nRequired columns:\n- Rs\n- Pressure\n- Bo\n- Oil Viscosity\n\nRules:\n- For each Rs value, include saturated row at Pb(Rs).\n- Add undersaturated rows at higher pressures with same Rs.\n- Above Pb: Bo decreases slightly as pressure increases, oil viscosity generally increases.\n\nDATA REQUIRED:\n- Differential Liberation data: Rs(P), Bo(P), mu_o(P)\n- CCE data above Pb for compressibility and viscosity pressure behavior\n- Separator test correction if field separator conditions are required"

def generate_pvtg_skeleton() -> str:
    return "PVTG Table Skeleton — Eclipse Live/Wet Gas\n\nRequired columns:\n- Pressure\n- Rv\n- Bg\n- Gas Viscosity\n\nFor dry gas with Rv approximately zero, use PVDG instead.\n\nDATA REQUIRED:\n- CVD/CCE gas data: Bg(P), mu_g(P)\n- Composition or Rv(P) for wet gas / gas condensate\n- Z-factor or EOS-derived gas properties"

def export_sim_decision(text: str) -> str:
    t = text.lower()
    near = "near" in t and "critical" in t
    if "black" in t:
        return "Recommended: PVTO for live oil or PVDO for dead oil. Use Black Oil Model if composition effects are limited."
    if "volatile" in t:
        msg = "Recommended: PVTO if Black-Oil approximation is acceptable, with dense data near Pb."
        if near:
            msg += "\nNear-critical warning: Compositional/EOS model is recommended."
        return msg
    if "condensate" in t:
        msg = "Recommended: PVTG only for simplified wet-gas/gas-condensate modeling. For rich gas condensate, use Compositional/EOS."
        if near:
            msg += "\nNear-critical warning: Compositional/EOS is strongly recommended."
        return msg
    if "wet gas" in t:
        return "Recommended: PVTG with Rv if liquid content is significant."
    if "dry gas" in t:
        return "Recommended: PVDG. Required: Pressure, Bg, gas viscosity."
    return "Specify fluid type:\n- black oil\n- volatile oil\n- gas condensate\n- wet gas\n- dry gas"

def clean_text(text: str) -> str:
    text = str(text)
    fixes = {"**":"","###":"","##":"","#":"","|":" ","[":"","]":"","Pressuring Volume and Temperature":"Pressure-Volume-Temperature","الضغط البيني":"معامل حجم التكوين","المعامل البيني":"معامل حجم التكوين","الترشيح":"نسبة الغاز المذاب","النسبة المئوية للغاز":"نسبة الغاز إلى الزيت","نسبة الغاز المئوية":"نسبة الغاز إلى الزيت","الويسكوزية":"اللزوجة","الویسكوزية":"اللزوجة","الليزج":"اللزوجة","الحفرة":"المكمن","السطوع النوعي":"الكثافة النوعية","اختبار السطوع":"اختبار الكثافة النوعية","معامل حجم تكوين الزيت":"معامل حجم التكوين للزيت","معامل حجم تكوين الغاز":"معامل حجم التكوين للغاز","معامل الانضغاطية مقابل الضغط":"معامل الانضغاطية للغاز مقابل الضغط"}
    for wrong, right in fixes.items():
        text = text.replace(wrong, right)
    return text.strip()

def send_message(chat_id: int, text: str) -> None:
    text = clean_text(text)
    if not text:
        text = "لم أتمكن من توليد رد واضح."
    for i in range(0, len(text), 3900):
        try:
            requests.post(f"{TELEGRAM_URL}/sendMessage", json={"chat_id": chat_id, "text": text[i:i+3900]}, timeout=15)
        except Exception as e:
            print(f"send_message error: {e}")
        time.sleep(0.4)

def send_document(chat_id: int, file_bytes: bytes, filename: str, caption: str, mime: str = "text/html") -> None:
    try:
        requests.post(f"{TELEGRAM_URL}/sendDocument", data={"chat_id": chat_id, "caption": caption}, files={"document": (filename, file_bytes, mime)}, timeout=20)
    except Exception as e:
        send_message(chat_id, f"خطأ في إرسال الملف: {e}")

def download_file(file_id: str, suffix: str = ".bin"):
    try:
        info = requests.get(f"{TELEGRAM_URL}/getFile", params={"file_id": file_id}, timeout=15).json()
        if not info.get("ok"):
            return None
        url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{info['result']['file_path']}"
        data = requests.get(url, timeout=60).content
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        tmp.write(data)
        tmp.close()
        return tmp.name
    except Exception as e:
        print(f"download_file error: {e}")
        return None

def extract_pdf_text(path: str) -> str:
    try:
        reader = PdfReader(path)
        return "\n\n".join(p.extract_text() for p in reader.pages if p.extract_text()).strip()
    except Exception as e:
        print(f"PDF error: {e}")
        return ""

def extract_docx_text(path: str) -> str:
    try:
        doc = Document(path)
        return "\n".join(p.text.strip() for p in doc.paragraphs if p.text.strip())
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

MAX_CONTEXT_CHARS = 20000

def store_file_context(chat_id: int, text: str, filename: str) -> str:
    original_len = len(text)
    if original_len > MAX_CONTEXT_CHARS:
        FILE_CONTEXT[chat_id] = text[:MAX_CONTEXT_CHARS]
        return f"تم قراءة الملف {filename}. تم استخدام أول {MAX_CONTEXT_CHARS:,} حرف فقط كمرجع."
    FILE_CONTEXT[chat_id] = text
    return f"تم قراءة الملف {filename} بنجاح. أصبح مرجعاً لهذه المحادثة."

def handle_document_upload(chat_id, doc):
    file_id = doc["file_id"]
    file_name = doc.get("file_name", "file")
    mime = doc.get("mime_type", "")
    ext = os.path.splitext(file_name)[1].lower() or ".bin"
    path = download_file(file_id, ext)
    if not path:
        send_message(chat_id, "حدث خطأ أثناء تحميل الملف.")
        return
    lower = file_name.lower()
    if lower.endswith(".pdf"):
        text = extract_pdf_text(path)
        if not text:
            send_message(chat_id, "قرأت PDF لكن لم أستخرج نصاً واضحاً. أرسل الصفحات كصور أو PDF نصي.")
            return
        send_message(chat_id, store_file_context(chat_id, text, file_name) + "\nاكتب /analyze لتحليله.")
    elif lower.endswith(".docx"):
        text = extract_docx_text(path)
        if not text:
            send_message(chat_id, "قرأت DOCX لكن لم أجد نصاً.")
            return
        send_message(chat_id, store_file_context(chat_id, text, file_name) + "\nاكتب /analyze لتحليله.")
    elif mime.startswith("image/") or lower.endswith((".png", ".jpg", ".jpeg", ".webp")):
        IMAGE_CONTEXT[chat_id] = path
        send_message(chat_id, "تم استلام الصورة. اكتب /graph لتحليل الرسم.")
    else:
        send_message(chat_id, "الملف المدعوم: PDF أو DOCX أو صورة.")

def handle_photo_upload(chat_id, photos):
    path = download_file(photos[-1]["file_id"], ".jpg")
    if path:
        IMAGE_CONTEXT[chat_id] = path
        send_message(chat_id, "تم استلام الصورة. اكتب /graph لتحليل الرسم.")
    else:
        send_message(chat_id, "خطأ في تحميل الصورة.")

def ask_ai(user_text: str, file_context=None, max_retries: int = 2) -> str:
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            messages = [{"role": "system", "content": SYSTEM_PROMPT}]
            if file_context:
                messages.append({"role": "user", "content": "Reference document context:\n\n" + file_context[:MAX_CONTEXT_CHARS]})
            messages.append({"role": "user", "content": user_text})
            r = requests.post(GROQ_URL, headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}, json={"model": TEXT_MODEL, "messages": messages, "temperature": 0.08, "max_tokens": 2200}, timeout=90)
            if r.status_code == 429:
                last_error = "rate_limit"
                time.sleep(2 ** attempt)
                continue
            r.raise_for_status()
            data = r.json()
            if "choices" in data:
                return data["choices"][0]["message"]["content"]
            last_error = str(data)[:400]
        except Exception as e:
            last_error = str(e)
            time.sleep(1)
    if last_error == "rate_limit":
        return "النظام مشغول حالياً بسبب Rate Limit. حاول بعد لحظات."
    return f"حدث خطأ في الاتصال بالذكاء الاصطناعي: {last_error}"

def ask_vision_ai(prompt: str, image_path: str, file_context=None, max_retries: int = 2) -> str:
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            full_prompt = SYSTEM_PROMPT + "\n\nTask:\n" + prompt
            if file_context:
                full_prompt += "\n\nReference context:\n" + file_context[:10000]
            messages = [{"role":"user","content":[{"type":"text","text":full_prompt},{"type":"image_url","image_url":{"url":encode_image(image_path)}}]}]
            r = requests.post(GROQ_URL, headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}, json={"model": VISION_MODEL, "messages": messages, "temperature": 0.08, "max_tokens": 1500}, timeout=90)
            if r.status_code == 429:
                last_error = "rate_limit"
                time.sleep(2 ** attempt)
                continue
            r.raise_for_status()
            data = r.json()
            if "choices" in data:
                return data["choices"][0]["message"]["content"]
            last_error = str(data)[:400]
        except Exception as e:
            last_error = str(e)
            time.sleep(1)
    if last_error == "rate_limit":
        return "النظام مشغول حالياً بسبب Rate Limit. حاول بعد لحظات."
    return f"حدث خطأ في تحليل الصورة: {last_error}"

def generate_glossary_html() -> bytes:
    cards = []
    for t in KNOWLEDGE_BASE:
        cards.append(f"<div class='card'><h3>{t['ar']}</h3><div class='en'>{t['en']}</div><p>{t['def_ar']}</p><small>Category: {t['category']} | Unit: {t['unit']} | Trend: {t['trend']}</small></div>")
    plots = []
    for key, rule in PVT_PLOT_RULES.items():
        plots.append(f"<div class='card'><h3>{rule['title_ar']}</h3><div class='en'>{rule['title_en']}</div><p>{rule['shape']}</p><pre>{ASCII_SKETCHES.get(key, '')}</pre></div>")
    html = f"""<!DOCTYPE html><html lang="ar" dir="rtl"><head><meta charset="UTF-8"><title>Petroleum Glossary</title><style>body{{font-family:Arial,sans-serif;background:#f5f0e8;line-height:1.8;padding:20px}}h1{{color:#3d1f00;text-align:center}}.card{{background:white;border:1px solid #ddd0b8;border-radius:10px;padding:15px;margin:12px 0}}.en{{direction:ltr;color:#c8760a;font-weight:bold}}pre{{direction:ltr;text-align:left;background:#111;color:#9be9a8;padding:10px;border-radius:8px;overflow:auto}}small{{color:#666}}</style></head><body><h1>المصطلحات النفطية وعلاقات PVT</h1><h2>المصطلحات</h2>{''.join(cards)}<h2>علاقات PVT</h2>{''.join(plots)}</body></html>"""
    return html.encode("utf-8")

def is_graph_cmd(t): return t.lower().startswith(("/graph", "/interpret_graph"))
def is_analyze_cmd(t): return t.lower().startswith("/analyze")
def is_calc_cmd(t): return t.lower().startswith("/calc")
def is_estimate_cmd(t): return t.lower().startswith("/estimate")
def is_convert_cmd(t): return t.lower().startswith("/convert")
def is_classify_cmd(t): return t.lower().startswith("/classify")
def is_plot_cmd(t): return t.lower().startswith("/plot")
def is_check_cmd(t): return t.lower().startswith("/check")
def is_pvto_cmd(t): return t.lower().strip() == "/pvto"
def is_pvtg_cmd(t): return t.lower().strip() == "/pvtg"
def is_export_sim_cmd(t): return t.lower().startswith("/export_sim")
def is_reset_cmd(t): return t.lower().strip() == "/reset"

def is_surface_separator(t):
    lower = t.lower()
    oil = any(k in lower for k in ["surface separator oil", "separator oil", "زيت من الفاصل", "عينة زيت"])
    gas = any(k in lower for k in ["separator gas", "غاز من الفاصل", "عينة غاز"])
    return oil and gas

def check_pvt_trend(rel_key: str, pressures: list, values: list, pb_or_pd: float = None) -> str:
    if len(pressures) != len(values) or len(pressures) < 3:
        return "بيانات غير كافية. أحتاج 3 نقاط على الأقل للضغط والقيمة."
    if rel_key not in PVT_PLOT_RULES:
        return "نوع العلاقة غير معروف."
    return f"Trend Check: {PVT_PLOT_RULES[rel_key]['title_en']}\n\nExpected trend:\n{PVT_PLOT_RULES[rel_key]['shape']}\n\nمراجعة سريعة: قارن بياناتك بهذا السلوك. إذا أردت فحصاً صارماً، أرسل البيانات بصيغة منظمة أكثر."

def start_message() -> str:
    return "أهلاً بك في Petroleum Engineering AI Bot\n\nمساعد متخصص في PVT, Reservoir, Simulation, Drilling, Production.\n\nالأوامر:\n/glossary\n/classify gor=<value> api=<value>\n/calc api sg=0.85\n/calc hydrostatic mw=10 tvd=5000\n/calc ooip area=500 h=50 phi=0.2 sw=0.3 bo=1.3\n/estimate pb_standing rs=650 gas_sg=0.75 tres=180 api=35\n/convert 5000 psi to bar\n/plot bo\n/check bo p=500,1000,1500 v=1.1,1.2,1.3 pb=1500\n/pvto\n/pvtg\n/export_sim gas condensate near_critical\n/analyze بعد رفع PDF/DOCX\n/graph بعد رفع صورة\n/reset"

def surface_separator_answer() -> str:
    return "تحليل هندسي — Surface Separator Oil Sample + Separator Gas Sample\n\nهذه عينات سطحية منفصلة وليست سائل مكمن مباشر.\nلذلك لا يمكن اعتماد Bo أو Rs أو Pb منها مباشرة قبل Recombination.\n\nRequired Data:\n- Separator Pressure and Temperature\n- Oil Rate and Gas Rate\n- Producing GOR or Separator GOR\n- Gas Composition and Oil Composition\n- API Gravity and Gas Specific Gravity\n- Water Cut and H2S/CO2 if present\n\nWorkflow:\n1. Sample QC\n2. Compositional Analysis\n3. Recombination\n4. Validation\n5. CCE/CME\n6. DV for oil systems or CVD for gas condensate\n7. Separator Test and Viscosity Test\n\nEngineering recommendation: أرسل بيانات الفاصل والتركيب وGOR لنحدد الاختبارات والحسابات بدقة."

print("Petroleum Engineering AI Bot running...")

while True:
    try:
        updates = requests.get(f"{TELEGRAM_URL}/getUpdates", params={"offset": offset + 1, "timeout": 30}, timeout=40).json()
        for update in updates.get("result", []):
            offset = update["update_id"]
            msg = update.get("message")
            if not msg:
                continue

            chat_id = msg["chat"]["id"]

            if "document" in msg:
                handle_document_upload(chat_id, msg["document"])
                continue
            if "photo" in msg:
                handle_photo_upload(chat_id, msg["photo"])
                continue
            if "text" not in msg:
                send_message(chat_id, "أرسل نصاً أو ملف PDF/DOCX أو صورة.")
                continue

            text = msg["text"].strip()
            context = FILE_CONTEXT.get(chat_id)

            if text == "/start":
                send_message(chat_id, start_message())
                continue
            if is_reset_cmd(text):
                FILE_CONTEXT.pop(chat_id, None)
                IMAGE_CONTEXT.pop(chat_id, None)
                send_message(chat_id, "تم مسح الملفات والصور المحفوظة لهذه المحادثة.")
                continue
            if text == "/glossary":
                send_document(chat_id, generate_glossary_html(), "petroleum_glossary.html", "المصطلحات النفطية وعلاقات PVT")
                continue
            if is_classify_cmd(text):
                kwargs = parse_kv_args(text[len("/classify"):])
                if "gor" not in kwargs or "api" not in kwargs:
                    send_message(chat_id, "Usage: /classify gor=<value> api=<value>\nExample: /classify gor=3500 api=45")
                    continue
                send_message(chat_id, classify_fluid(kwargs["gor"], kwargs["api"]))
                continue
            if is_calc_cmd(text):
                parts = text.split(maxsplit=2)
                if len(parts) < 2:
                    send_message(chat_id, "Usage: /calc <type> key=value\nTypes: api, hydrostatic, ooip, darcy, recovery_factor, water_cut, productivity_index")
                    continue
                calc_type = parts[1].lower()
                kwargs = parse_kv_args(parts[2] if len(parts) > 2 else "")
                result = run_exact_calc(calc_type, **kwargs)
                send_message(chat_id, result or f"Unknown calculation type: {calc_type}")
                continue
            if is_estimate_cmd(text):
                parts = text.split(maxsplit=2)
                if len(parts) < 2:
                    send_message(chat_id, "Usage: /estimate <type> key=value\nTypes: pb_standing, rs_standing")
                    continue
                calc_type = parts[1].lower()
                kwargs = parse_kv_args(parts[2] if len(parts) > 2 else "")
                result = run_correlation(calc_type, **kwargs)
                send_message(chat_id, result or f"Unknown correlation type: {calc_type}")
                continue
            if is_convert_cmd(text):
                m = re.match(r"/convert\s+([-+]?\d*\.?\d+)\s+(\S+)\s+to\s+(\S+)", text, re.IGNORECASE)
                if not m:
                    send_message(chat_id, "Usage: /convert <value> <from_unit> to <to_unit>\nExample: /convert 5000 psi to bar")
                    continue
                send_message(chat_id, run_unit_conversion(float(m.group(1)), m.group(2), m.group(3)))
                continue
            if is_plot_cmd(text):
                query = text[5:].strip().lower()
                if not query:
                    send_message(chat_id, "Usage: /plot bo\nAvailable: bo, rs, viscosity, density, vrel, bg, z, gas viscosity, dropout, cgr, phase envelope")
                    continue
                rel_key = PLOT_ALIASES.get(query)
                if not rel_key:
                    for alias, key in PLOT_ALIASES.items():
                        if alias in query:
                            rel_key = key
                            break
                if not rel_key:
                    send_message(chat_id, "لم أتعرف على العلاقة. جرّب: /plot bo أو /plot z أو /plot dropout")
                    continue
                send_message(chat_id, format_plot_response(rel_key))
                continue
            if is_check_cmd(text):
                body = text[6:].strip()
                rel = body.split()[0].lower() if body else ""
                rel_key = PLOT_ALIASES.get(rel)
                p_match = re.search(r"p=\[?([\d,\.\s]+)\]?", body)
                v_match = re.search(r"v=\[?([\d,\.\s]+)\]?", body)
                pb_match = re.search(r"pb=([\d\.]+)", body)
                if not rel_key or not p_match or not v_match:
                    send_message(chat_id, "Usage: /check bo p=500,1000,1500 v=1.1,1.2,1.3 pb=1500")
                    continue
                pressures = [float(x) for x in p_match.group(1).split(",")]
                values = [float(x) for x in v_match.group(1).split(",")]
                pb = float(pb_match.group(1)) if pb_match else None
                send_message(chat_id, check_pvt_trend(rel_key, pressures, values, pb))
                continue
            if is_pvto_cmd(text):
                send_message(chat_id, generate_pvto_skeleton())
                continue
            if is_pvtg_cmd(text):
                send_message(chat_id, generate_pvtg_skeleton())
                continue
            if is_export_sim_cmd(text):
                send_message(chat_id, export_sim_decision(text[len("/export_sim"):].strip()))
                continue
            if is_analyze_cmd(text):
                if not context:
                    send_message(chat_id, "لا يوجد ملف مرفوع. أرسل PDF أو DOCX أولاً.")
                    continue
                prompt = "Analyze the uploaded petroleum/PVT report professionally. Identify sample type, fluid type, tests, key values, missing data, trend consistency, and simulation recommendation."
                send_message(chat_id, ask_ai(prompt, context))
                continue
            if is_graph_cmd(text):
                img = IMAGE_CONTEXT.get(chat_id)
                if not img:
                    send_message(chat_id, "أرسل صورة الرسم أولاً ثم اكتب /graph.")
                    continue
                prompt = "Analyze the uploaded petroleum engineering graph. Identify axes, units, relationship type, expected PVT trend, anomalies, non-physical behavior, and recommendations. Use the PVT physical rules strictly."
                send_message(chat_id, ask_vision_ai(prompt, img, context))
                continue
            if is_surface_separator(text):
                send_message(chat_id, surface_separator_answer())
                continue
            send_message(chat_id, ask_ai(text, context))
    except Exception as e:
        print(f"Main loop error: {e}")
    time.sleep(1)
