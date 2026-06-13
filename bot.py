import os
import time
import base64
import tempfile
import mimetypes
import requests
from PyPDF2 import PdfReader
from docx import Document

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.getenv("OPENAI_API_KEY")

TELEGRAM_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

TEXT_MODEL = os.getenv("GROQ_TEXT_MODEL", "llama-3.3-70b-versatile")
VISION_MODEL = os.getenv("GROQ_VISION_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")

offset = 0
FILE_CONTEXT = {}
IMAGE_CONTEXT = {}

SYSTEM_PROMPT = """
You are a professional Petroleum Engineering, PVT Laboratory, Reservoir Fluid Analysis, and Reservoir Simulation assistant.

You must answer like a real PVT laboratory engineer and reservoir fluid specialist, not like a generic chatbot.

Language rules:
- If the user writes Arabic, answer in strong professional Arabic.
- If the user writes English, answer in professional petroleum engineering English.
- If the user mixes Arabic and English, answer naturally in the same style.
- Keep important technical terms in English beside Arabic when useful.

Correct terminology:
PVT = Pressure-Volume-Temperature.
Reservoir = المكمن Reservoir.
Well = البئر Well.
Formation = التكوين Formation.
Bottom Hole Sample = عينة قاع البئر Bottom Hole Sample.
Surface Separator Oil Sample = عينة زيت من الفاصل السطحي Surface Separator Oil Sample.
Separator Gas Sample = عينة غاز من الفاصل Separator Gas Sample.
Stock Tank Oil = زيت الخزان السطحي Stock Tank Oil.
Recombined Sample = عينة معاد تركيبها Recombined Sample.
Recombination = إعادة تركيب العينة Recombination.
Bubble Point Pressure = ضغط نقطة الفقاعة Bubble Point Pressure.
Dew Point Pressure = ضغط نقطة الندى Dew Point Pressure.
Bo = معامل حجم التكوين للزيت Oil Formation Volume Factor.
Bg = معامل حجم التكوين للغاز Gas Formation Volume Factor.
Rs = نسبة الغاز المذاب Solution Gas-Oil Ratio.
GOR = نسبة الغاز إلى الزيت Gas-Oil Ratio.
CGR = نسبة المكثفات إلى الغاز Condensate-Gas Ratio.
Z-factor = معامل الانحراف الغازي Gas Deviation Factor.
Viscosity = اللزوجة Viscosity.
Density = الكثافة Density.
Specific Gravity = الكثافة النوعية Specific Gravity.
API Gravity = درجة API.
CCE = Constant Composition Expansion.
CME = Constant Mass Expansion.
DV = Differential Vaporization / Differential Liberation.
CVD = Constant Volume Depletion.
Separator Test = اختبار الفاصل Separator Test.
Flash Test = اختبار الوميض Flash Test.
Compositional Analysis = التحليل التركيب Compositional Analysis.
EOS Tuning = مواءمة معادلة الحالة EOS Tuning.
PVTO = جدول PVTO لمحاكي Eclipse.
PVTG = جدول PVTG لمحاكي Eclipse.
CMG PVT Input = مدخلات PVT لمحاكي CMG.

Forbidden terms:
- Do not call Bo الضغط البيني or المعامل البيني.
- Do not call Rs الترشيح.
- Do not call GOR النسبة المئوية للغاز.
- Do not say الليزج for Viscosity.
- Do not say الحفرة for Reservoir.
- Do not say السطوع النوعي or اختبار السطوع.
- Do not define PVT as Pressuring Volume and Temperature.
- Do not invent numerical PVT values unless the user clearly asks for demo/sample values.
- Do not create fake lab tables with fake values.

For every technical answer:
1. Identify the sample type.
2. Identify likely fluid system if possible.
3. Select the correct PVT workflow.
4. Explain required laboratory tests.
5. Explain calculations only if data are available.
6. Explain required plots if applicable.
7. Explain simulation relevance if applicable.
8. Mention missing data clearly.
9. Give engineering interpretation.

Surface Separator Oil Sample + Separator Gas Sample logic:
- These are surface separated samples, not original reservoir fluid directly.
- They usually require Recombination to reconstruct reservoir fluid.
- Required data: separator pressure, separator temperature, oil rate, gas rate, producing GOR or separator GOR, gas composition, oil/stock tank oil composition, oil density, API gravity, gas specific gravity, water/emulsion content, H2S/CO2 if present.
- Correct workflow: sample QC, compositional analysis, recombination, validation of recombined fluid, CCE/CME, DV for oil systems, CVD for gas condensate, separator test, viscosity test.
- For black oil simulation use PVTO when pressure, Rs, Bo, and oil viscosity are available.
- For gas systems use PVTG when gas PVT data are available.
- For volatile oil or gas condensate use EOS/compositional simulation.

Report philosophy:
- A reference PDF is an example only, not a fixed template.
- Adapt report structure to sample type, fluid system, available data, lab objective, report scope, client requirements, and simulation objective.

Graph interpretation:
- For uploaded images/graphs, identify axes, units, trend, anomalies, non-physical behavior, possible contamination, retrograde behavior if applicable, separator performance issues, engineering meaning, causes, and recommendations.

Formatting:
- Do not use markdown symbols like ** or ###.
- Do not use vertical-line tables.
- Use clean Telegram text with clear headings.
"""

# ─────────────────────────────────────────────
#  PETROLEUM GLOSSARY HTML (مدمج في البوت)
# ─────────────────────────────────────────────
GLOSSARY_HTML = r"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>المصطلحات النفطية | Petroleum Glossary</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@300;400;600;700;900&family=Fira+Code:wght@400;600&display=swap');
  :root{--ink:#0d1117;--surface:#f5f0e8;--paper:#fdfaf4;--crude:#3d1f00;--amber:#c8760a;--gold:#e8a020;--light-amber:#fef3dc;--steel:#2a4a5e;--muted:#7a6a58;--border:#ddd0b8;--formula-bg:#0d1117;--formula-text:#e8a020}
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:'Cairo',sans-serif;background:var(--surface);color:var(--ink);line-height:1.7}
  header{background:var(--crude);color:var(--paper);padding:3rem 2rem 2rem;text-align:center;position:relative;overflow:hidden}
  header::before{content:'';position:absolute;inset:0;background:repeating-linear-gradient(45deg,transparent,transparent 40px,rgba(200,118,10,.06) 40px,rgba(200,118,10,.06) 41px)}
  header h1{font-size:clamp(1.8rem,4vw,2.8rem);font-weight:900;letter-spacing:-.02em;position:relative}
  header h1 span{color:var(--gold)}
  header p{margin-top:.6rem;font-size:1rem;color:rgba(255,255,255,.6);position:relative}
  nav{display:flex;justify-content:center;gap:.5rem;flex-wrap:wrap;padding:1.4rem 1rem;background:var(--paper);border-bottom:2px solid var(--border);position:sticky;top:0;z-index:100;box-shadow:0 2px 12px rgba(0,0,0,.08)}
  nav button{padding:.5rem 1.2rem;border:2px solid var(--border);border-radius:999px;background:transparent;font-family:'Cairo',sans-serif;font-size:.85rem;font-weight:600;color:var(--muted);cursor:pointer;transition:all .2s}
  nav button:hover{border-color:var(--amber);color:var(--amber)}
  nav button.active{background:var(--amber);border-color:var(--amber);color:white}
  main{max-width:1100px;margin:0 auto;padding:2rem 1.5rem 4rem}
  .section{display:none}.section.active{display:block}
  .search-bar{display:flex;gap:.6rem;margin-bottom:2rem}
  .search-bar input{flex:1;padding:.7rem 1.2rem;border:2px solid var(--border);border-radius:8px;font-family:'Cairo',sans-serif;font-size:1rem;background:var(--paper);color:var(--ink);transition:border-color .2s}
  .search-bar input:focus{outline:none;border-color:var(--amber)}
  .terms-grid{display:grid;gap:1.2rem}
  .term-card{background:var(--paper);border:1.5px solid var(--border);border-radius:12px;overflow:hidden;transition:box-shadow .2s,border-color .2s}
  .term-card:hover{box-shadow:0 4px 20px rgba(200,118,10,.15);border-color:var(--amber)}
  .term-header{display:flex;align-items:center;justify-content:space-between;padding:1rem 1.4rem;cursor:pointer;gap:1rem}
  .term-en{font-family:'Fira Code',monospace;font-size:.9rem;font-weight:600;color:var(--amber);background:var(--light-amber);padding:.25rem .7rem;border-radius:6px;white-space:nowrap;direction:ltr}
  .term-ar{font-size:1.05rem;font-weight:700;color:var(--crude);flex:1}
  .term-tag{font-size:.7rem;padding:.2rem .6rem;border-radius:999px;font-weight:600;white-space:nowrap}
  .tag-reservoir{background:#dbeafe;color:#1e40af}.tag-drilling{background:#dcfce7;color:#166534}
  .tag-production{background:#fef9c3;color:#854d0e}.tag-geology{background:#f3e8ff;color:#6b21a8}
  .tag-fluid{background:#ffe4e6;color:#9f1239}.tag-economics{background:#e0f2fe;color:#0369a1}
  .term-body{display:none;padding:0 1.4rem 1.4rem;border-top:1px solid var(--border)}
  .term-body.open{display:block}
  .term-definition{margin-top:1rem;font-size:.98rem;color:#333;line-height:1.9}
  .formula-section-title{font-size:1.5rem;font-weight:900;color:var(--crude);margin-bottom:1.5rem;padding-bottom:.5rem;border-bottom:3px solid var(--amber)}
  .formula-card{background:var(--formula-bg);border-radius:12px;overflow:hidden;margin-bottom:1.4rem;border:1px solid #2a3040}
  .formula-card-header{display:flex;align-items:center;justify-content:space-between;padding:.9rem 1.4rem;background:rgba(200,118,10,.12);border-bottom:1px solid #2a3040}
  .formula-name-en{font-family:'Fira Code',monospace;color:var(--gold);font-size:.9rem;font-weight:600;direction:ltr}
  .formula-name-ar{color:rgba(255,255,255,.85);font-size:.95rem;font-weight:600}
  .formula-body{padding:1.2rem 1.4rem}
  .formula-eq{font-family:'Fira Code',monospace;color:var(--formula-text);font-size:1.1rem;direction:ltr;text-align:center;padding:.8rem 0;letter-spacing:.04em}
  .formula-vars{margin-top:1rem;border-top:1px solid #2a3040;padding-top:1rem}
  .formula-var{display:flex;align-items:flex-start;gap:.8rem;margin-bottom:.5rem;direction:rtl}
  .var-sym{font-family:'Fira Code',monospace;color:var(--gold);font-size:.85rem;min-width:80px;direction:ltr;text-align:right}
  .var-desc{color:rgba(255,255,255,.7);font-size:.85rem;line-height:1.6}
  .formula-note{margin-top:.8rem;padding:.6rem .9rem;background:rgba(232,160,32,.08);border-right:3px solid var(--gold);border-radius:0 6px 6px 0;color:rgba(255,255,255,.65);font-size:.82rem;line-height:1.6}
  .map-container{background:var(--paper);border-radius:16px;border:2px solid var(--border);padding:2rem}
  .map-title{text-align:center;font-size:1.4rem;font-weight:900;color:var(--crude);margin-bottom:1.5rem}
  svg.concept-map{width:100%;height:auto;display:block}
  .map-legend{display:flex;flex-wrap:wrap;gap:1rem;justify-content:center;margin-top:1.5rem}
  .legend-item{display:flex;align-items:center;gap:.4rem;font-size:.82rem;color:var(--muted)}
  .legend-dot{width:12px;height:12px;border-radius:50%}
  .no-results{text-align:center;padding:3rem;color:var(--muted);font-size:1rem}
  @media(max-width:600px){.term-header{flex-wrap:wrap}nav button{font-size:.78rem;padding:.4rem .9rem}.formula-eq{font-size:.95rem}}
</style>
</head>
<body>
<header>
  <h1>المصطلحات <span>النفطية</span> التقنية<br><small style="font-size:.55em;font-weight:300;opacity:.7">Petroleum Engineering Terminology</small></h1>
  <p>تعريفات علمية شاملة · معادلات · خريطة المفاهيم</p>
</header>
<nav>
  <button class="active" onclick="showSection('terms',this)">📚 المصطلحات والتعريفات</button>
  <button onclick="showSection('formulas',this)">📐 المعادلات</button>
  <button onclick="showSection('map',this)">🗺️ خريطة المفاهيم</button>
</nav>
<main>
<div id="terms" class="section active">
  <div class="search-bar"><input type="text" id="searchInput" placeholder="🔍  ابحث بالمصطلح الإنجليزي أو العربي..." oninput="filterTerms()"/></div>
  <div class="terms-grid" id="termsGrid"></div>
  <div class="no-results" id="noResults" style="display:none">لا توجد نتائج مطابقة</div>
</div>
<div id="formulas" class="section">
  <p class="formula-section-title">⚙️ المعادلات الهندسية النفطية</p>
  <div id="formulasGrid"></div>
</div>
<div id="map" class="section">
  <div class="map-container">
    <div class="map-title">🗺️ خريطة المفاهيم المركزية في هندسة النفط والغاز</div>
    <svg class="concept-map" viewBox="0 0 900 640" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <marker id="arrow" markerWidth="10" markerHeight="7" refX="10" refY="3.5" orient="auto"><polygon points="0 0, 10 3.5, 0 7" fill="#c8760a" opacity=".7"/></marker>
        <filter id="shadow"><feDropShadow dx="0" dy="2" stdDeviation="4" flood-opacity="0.15"/></filter>
      </defs>
      <rect width="900" height="640" fill="#fdfaf4" rx="14"/>
      <line x1="450" y1="320" x2="450" y2="145" stroke="#c8760a" stroke-width="2" stroke-dasharray="6,4" marker-end="url(#arrow)" opacity=".6"/>
      <line x1="450" y1="320" x2="210" y2="200" stroke="#166534" stroke-width="2" stroke-dasharray="6,4" marker-end="url(#arrow)" opacity=".6"/>
      <line x1="450" y1="320" x2="690" y2="200" stroke="#9f1239" stroke-width="2" stroke-dasharray="6,4" marker-end="url(#arrow)" opacity=".6"/>
      <line x1="450" y1="320" x2="200" y2="460" stroke="#7c3aed" stroke-width="2" stroke-dasharray="6,4" marker-end="url(#arrow)" opacity=".6"/>
      <line x1="450" y1="320" x2="700" y2="460" stroke="#0369a1" stroke-width="2" stroke-dasharray="6,4" marker-end="url(#arrow)" opacity=".6"/>
      <line x1="450" y1="320" x2="450" y2="530" stroke="#854d0e" stroke-width="2" stroke-dasharray="6,4" marker-end="url(#arrow)" opacity=".6"/>
      <line x1="450" y1="100" x2="210" y2="200" stroke="#aaa" stroke-width="1.2" opacity=".35" marker-end="url(#arrow)"/>
      <line x1="450" y1="100" x2="690" y2="200" stroke="#aaa" stroke-width="1.2" opacity=".35" marker-end="url(#arrow)"/>
      <line x1="200" y1="460" x2="700" y2="460" stroke="#aaa" stroke-width="1.2" opacity=".25" stroke-dasharray="4,4"/>
      <line x1="690" y1="200" x2="700" y2="460" stroke="#aaa" stroke-width="1.2" opacity=".3" marker-end="url(#arrow)"/>
      <g filter="url(#shadow)">
        <ellipse cx="450" cy="320" rx="90" ry="48" fill="#3d1f00"/>
        <text x="450" y="314" text-anchor="middle" fill="#fef3dc" font-family="Cairo,sans-serif" font-size="14" font-weight="700">هندسة النفط</text>
        <text x="450" y="332" text-anchor="middle" fill="#c8760a" font-family="Fira Code,monospace" font-size="10">Petroleum Eng.</text>
      </g>
      <g filter="url(#shadow)">
        <rect x="340" y="60" width="220" height="80" rx="12" fill="#fef3dc" stroke="#c8760a" stroke-width="2"/>
        <text x="450" y="92" text-anchor="middle" fill="#3d1f00" font-family="Cairo,sans-serif" font-size="13" font-weight="700">المكمن النفطي</text>
        <text x="450" y="107" text-anchor="middle" fill="#c8760a" font-family="Fira Code,monospace" font-size="10">Reservoir</text>
        <text x="450" y="125" text-anchor="middle" fill="#7a6a58" font-family="Cairo,sans-serif" font-size="10">المسامية · النفاذية · الضغط</text>
      </g>
      <g filter="url(#shadow)">
        <rect x="80" y="155" width="200" height="80" rx="12" fill="#dcfce7" stroke="#166534" stroke-width="2"/>
        <text x="180" y="187" text-anchor="middle" fill="#14532d" font-family="Cairo,sans-serif" font-size="13" font-weight="700">الحفر</text>
        <text x="180" y="202" text-anchor="middle" fill="#166534" font-family="Fira Code,monospace" font-size="10">Drilling</text>
        <text x="180" y="220" text-anchor="middle" fill="#7a6a58" font-family="Cairo,sans-serif" font-size="10">WOB · ROP · طين الحفر</text>
      </g>
      <g filter="url(#shadow)">
        <rect x="620" y="155" width="210" height="80" rx="12" fill="#ffe4e6" stroke="#9f1239" stroke-width="2"/>
        <text x="725" y="187" text-anchor="middle" fill="#9f1239" font-family="Cairo,sans-serif" font-size="13" font-weight="700">الإنتاج</text>
        <text x="725" y="202" text-anchor="middle" fill="#9f1239" font-family="Fira Code,monospace" font-size="10">Production</text>
        <text x="725" y="220" text-anchor="middle" fill="#7a6a58" font-family="Cairo,sans-serif" font-size="10">GOR · معدل الإنتاج · PI</text>
      </g>
      <g filter="url(#shadow)">
        <rect x="70" y="415" width="210" height="80" rx="12" fill="#f3e8ff" stroke="#7c3aed" stroke-width="2"/>
        <text x="175" y="447" text-anchor="middle" fill="#4c1d95" font-family="Cairo,sans-serif" font-size="13" font-weight="700">خواص الموائع</text>
        <text x="175" y="462" text-anchor="middle" fill="#7c3aed" font-family="Fira Code,monospace" font-size="10">Fluid Properties</text>
        <text x="175" y="480" text-anchor="middle" fill="#7a6a58" font-family="Cairo,sans-serif" font-size="10">API · FVF · نقطة الفقاعة</text>
      </g>
      <g filter="url(#shadow)">
        <rect x="620" y="415" width="210" height="80" rx="12" fill="#e0f2fe" stroke="#0369a1" stroke-width="2"/>
        <text x="725" y="447" text-anchor="middle" fill="#0c4a6e" font-family="Cairo,sans-serif" font-size="13" font-weight="700">الاقتصاديات</text>
        <text x="725" y="462" text-anchor="middle" fill="#0369a1" font-family="Fira Code,monospace" font-size="10">Economics</text>
        <text x="725" y="480" text-anchor="middle" fill="#7a6a58" font-family="Cairo,sans-serif" font-size="10">NPV · EUR · معدل الاسترداد</text>
      </g>
      <g filter="url(#shadow)">
        <rect x="340" y="490" width="220" height="80" rx="12" fill="#fef9c3" stroke="#854d0e" stroke-width="2"/>
        <text x="450" y="522" text-anchor="middle" fill="#713f12" font-family="Cairo,sans-serif" font-size="13" font-weight="700">الجيولوجيا</text>
        <text x="450" y="537" text-anchor="middle" fill="#854d0e" font-family="Fira Code,monospace" font-size="10">Geology</text>
        <text x="450" y="555" text-anchor="middle" fill="#7a6a58" font-family="Cairo,sans-serif" font-size="10">التكوين · الفالق · المصيدة</text>
      </g>
    </svg>
    <div class="map-legend">
      <div class="legend-item"><div class="legend-dot" style="background:#c8760a"></div>المكمن</div>
      <div class="legend-item"><div class="legend-dot" style="background:#166534"></div>الحفر</div>
      <div class="legend-item"><div class="legend-dot" style="background:#9f1239"></div>الإنتاج</div>
      <div class="legend-item"><div class="legend-dot" style="background:#7c3aed"></div>الموائع</div>
      <div class="legend-item"><div class="legend-dot" style="background:#0369a1"></div>الاقتصاديات</div>
      <div class="legend-item"><div class="legend-dot" style="background:#854d0e"></div>الجيولوجيا</div>
    </div>
    <div style="margin-top:2rem;padding:1.2rem;background:#f5f0e8;border-radius:10px;border:1px solid #ddd0b8">
      <p style="font-size:.9rem;color:#3d1f00;font-weight:700;margin-bottom:.8rem">🔗 العلاقات المحورية بين المفاهيم:</p>
      <ul style="list-style:none;display:grid;gap:.6rem;font-size:.88rem;color:#7a6a58">
        <li>📌 الجيولوجيا تحدد شكل وأبعاد المكمن من خلال دراسة التكوينات والمصائد</li>
        <li>📌 المسامية والنفاذية للمكمن تتحكم مباشرة في معدلات الإنتاج</li>
        <li>📌 خواص الموائع (API، FVF) تؤثر على قيمة النفط وكفاءة الاستخراج</li>
        <li>📌 تقنيات الحفر هي الجسر بين الجيولوجيا السطحية والمكمن تحت الأرض</li>
        <li>📌 الاقتصاديات (NPV، EUR) تحدد جدوى كل عملية إنتاج وحفر</li>
        <li>📌 نسبة الغاز إلى النفط (GOR) تربط بين خواص الموائع ومعدلات الإنتاج</li>
      </ul>
    </div>
  </div>
</div>
</main>
<script>
const TERMS=[
  {en:"Porosity",ar:"المسامية",tag:"reservoir",tagLabel:"المكمن",def:"النسبة المئوية لحجم الفراغات (المسام) داخل الصخرة إلى حجمها الإجمالي. تمثل الحيز المتاح لتخزين الموائع كالنفط والغاز والماء. تُعدّ من أهم خصائص المكمن وتتراوح عادةً بين 5% و35%."},
  {en:"Permeability",ar:"النفاذية",tag:"reservoir",tagLabel:"المكمن",def:"مقياس لقدرة الصخرة على السماح بتدفق الموائع خلالها تحت تأثير فرق الضغط. تُقاس بوحدة الداري (Darcy). تُحدد معدل تدفق النفط والغاز نحو بئر الإنتاج."},
  {en:"Reservoir Pressure",ar:"ضغط المكمن",tag:"reservoir",tagLabel:"المكمن",def:"الضغط الموجود داخل المكمن الناجم عن وزن الطبقات الصخرية فوقه وتمدد الموائع المحبوسة. يُعدّ المحرك الرئيسي لدفع الموائع نحو البئر."},
  {en:"Water Saturation (Sw)",ar:"تشبع الماء",tag:"reservoir",tagLabel:"المكمن",def:"النسبة المئوية لحجم الماء إلى إجمالي حجم المسامية في الصخرة الخازنة. كلما قلّ تشبع الماء، زادت احتمالية وجود الهيدروكربونات."},
  {en:"Net Pay",ar:"سماكة الطبقة الإنتاجية",tag:"reservoir",tagLabel:"المكمن",def:"السُّمك الفعلي المفيد من الصخرة الخازنة التي تحتوي على هيدروكربونات قابلة للإنتاج اقتصادياً بعد استبعاد الطبقات الفاقدة للجودة أو المشبعة بالماء."},
  {en:"OOIP",ar:"كمية النفط الأصلية في المكمن",tag:"reservoir",tagLabel:"المكمن",def:"الحجم الإجمالي للنفط الخام المتوفر في المكمن قبل بدء الإنتاج. لا يعني كل هذا الحجم قابلاً للاستخراج؛ فقط جزء منه يُشكّل الاحتياطيات القابلة للاستخراج اعتماداً على عامل الاسترداد."},
  {en:"Recovery Factor",ar:"عامل الاسترداد",tag:"reservoir",tagLabel:"المكمن",def:"النسبة المئوية من الكمية الأصلية للنفط في المكمن التي يمكن استخراجها فعلياً. تتراوح عادةً بين 20% و50%."},
  {en:"Weight on Bit (WOB)",ar:"الحمل على القاطعة",tag:"drilling",tagLabel:"الحفر",def:"الحمل العمودي الذي يُطبَّق على أسنان لقمة الحفر لتحطيم الصخر. يُقاس بالأطنان. التحكم الدقيق فيه يمنع ثني عمود الحفر أو تلف اللقمة."},
  {en:"Rate of Penetration (ROP)",ar:"معدل الحفر",tag:"drilling",tagLabel:"الحفر",def:"السرعة التي يتقدم بها لقم الحفر خلال التكوينات الصخرية، تُقاس بالمتر في الساعة. تعتمد على طبيعة الصخر وحمل اللقمة وسرعة دوران عمود الحفر."},
  {en:"Mud Weight",ar:"وزن طين الحفر",tag:"drilling",tagLabel:"الحفر",def:"كثافة سائل الحفر، تُقاس بالرطل للغالون (ppg). يجب أن يكون بين ضغط المكمن وضغط الكسر لمنع انهيار البئر أو فقدان الدورة."},
  {en:"Casing",ar:"غلاف البئر",tag:"drilling",tagLabel:"الحفر",def:"أنابيب فولاذية تُثبَّت على جدران البئر وتُعزل التكوينات الجيولوجية المختلفة. تحمي البئر من الانهيار وتمنع تلوث طبقات المياه الجوفية."},
  {en:"Blowout Preventer (BOP)",ar:"مانع الانفجار",tag:"drilling",tagLabel:"الحفر",def:"جهاز متخصص يُركَّب أعلى البئر لإغلاقه فورياً عند حدوث ارتفاع غير مُتحكَّم في الضغط. يُشكّل خط الدفاع الأول لمنع انفجار البئر."},
  {en:"Gas-Oil Ratio (GOR)",ar:"نسبة الغاز إلى النفط",tag:"production",tagLabel:"الإنتاج",def:"نسبة حجم الغاز المصاحب المنتَج إلى حجم النفط الخام. تُقاس بـ scf/STB. تزداد مع تناقص ضغط المكمن وتُشير إلى طبيعة المكمن."},
  {en:"Productivity Index (PI)",ar:"مؤشر الإنتاجية",tag:"production",tagLabel:"الإنتاج",def:"مقياس لكفاءة البئر في إنتاج الموائع. يُعبَّر عنه بمعدل الإنتاج لكل وحدة انخفاض في الضغط (psi)."},
  {en:"Water Cut",ar:"نسبة الماء المنتج",tag:"production",tagLabel:"الإنتاج",def:"النسبة المئوية لحجم الماء في إجمالي السوائل المنتجة. تزداد مع تقدم عمر البئر نتيجة تقدم الماء في المكمن."},
  {en:"Artificial Lift",ar:"الرفع الاصطناعي",tag:"production",tagLabel:"الإنتاج",def:"تقنيات تُستخدم لرفع الموائع من المكمن إلى السطح عندما لا يكفي الضغط الطبيعي. تشمل ESP وGas Lift ومضخات قضيب الشفط."},
  {en:"API Gravity",ar:"درجة الثقل النوعي API",tag:"fluid",tagLabel:"الموائع",def:"مقياس نسبي لكثافة النفط الخام وفقاً لمعهد البترول الأمريكي. كلما ارتفعت درجة API كان النفط أخف وأكثر قيمة. النفط الخفيف أكثر من 35 درجة."},
  {en:"Formation Volume Factor (Bo)",ar:"معامل الحجم التكويني",tag:"fluid",tagLabel:"الموائع",def:"النسبة بين حجم النفط وغازه المذاب داخل المكمن إلى حجمه في ظروف السطح القياسية. يُستخدم لحساب احتياطيات المكمن الحقيقية."},
  {en:"Bubble Point Pressure",ar:"ضغط نقطة الفقاعة",tag:"fluid",tagLabel:"الموائع",def:"الضغط الذي يبدأ عنده الغاز المذاب في النفط بالانفصال وتكوين فقاعات. ذو أهمية بالغة لإدارة ضغط المكمن."},
  {en:"Viscosity",ar:"اللزوجة",tag:"fluid",tagLabel:"الموائع",def:"مقياس لمقاومة الموائع للتدفق، تُقاس بوحدة السنتيبواز (cP). تؤثر بشكل مباشر على نفاذية الزيت وقابليته للتدفق."},
  {en:"Z-Factor",ar:"معامل الانضغاطية للغاز",tag:"fluid",tagLabel:"الموائع",def:"عامل تصحيحي يُستخدم في معادلة حالة الغاز الحقيقي. يُعبّر عن مدى انحراف سلوك الغاز الحقيقي عن السلوك المثالي."},
  {en:"Anticline",ar:"الطية المحدبة",tag:"geology",tagLabel:"الجيولوجيا",def:"طية صخرية مقوسة للأعلى تشكّل من أهم المصائد الجيولوجية لتراكم النفط والغاز لأن الهيدروكربونات تصعد وتتجمع في القمة."},
  {en:"Fault",ar:"الفالق",tag:"geology",tagLabel:"الجيولوجيا",def:"كسر في الصخور ينزلق على طوله أحد جانبيه. يمكن أن يكون مصيدة جيدة للنفط أو قناة تسرب حسب طبيعته."},
  {en:"Cap Rock / Seal",ar:"الصخرة العازلة",tag:"geology",tagLabel:"الجيولوجيا",def:"طبقة صخرية غير نافذة تعلو التكوين الخازن وتمنع هروب الهيدروكربونات للأعلى. غيابها يعني عدم تراكم النفط."},
  {en:"Source Rock",ar:"صخرة المصدر",tag:"geology",tagLabel:"الجيولوجيا",def:"صخرة رسوبية غنية بالمادة العضوية تعرضت للحرارة والضغط فأنتجت الهيدروكربونات. الطين الأسود من أشهر صخور المصدر."},
  {en:"Trap",ar:"المصيدة الجيولوجية",tag:"geology",tagLabel:"الجيولوجيا",def:"أي تشكّل جيولوجي يوقف هجرة الهيدروكربونات ويسمح بتراكمها. تشمل المصائد البنيوية والمصائد الطباقية."},
  {en:"Net Present Value (NPV)",ar:"صافي القيمة الحالية",tag:"economics",tagLabel:"الاقتصاد",def:"الفرق بين القيمة الحالية للتدفقات النقدية الداخلة والخارجة بمشروع نفطي باستخدام معدل خصم محدد. المقياس الأساسي لتقييم الجدوى الاقتصادية."},
  {en:"Estimated Ultimate Recovery (EUR)",ar:"الاحتياطيات الإجمالية المتوقعة",tag:"economics",tagLabel:"الاقتصاد",def:"إجمالي الكمية المتوقعة استخراجها من البئر خلال حياته الإنتاجية الكاملة. تُستخدم لتقييم قيمة الأصل النفطي."},
  {en:"Break-Even Price",ar:"سعر التعادل",tag:"economics",tagLabel:"الاقتصاد",def:"سعر البيع الأدنى للنفط الذي يُغطي عنده مشروع ما جميع تكاليف التطوير والإنتاج والتشغيل دون ربح أو خسارة."}
];
const FORMULAS=[
  {en:"Porosity",ar:"معادلة المسامية",eq:"φ = V_pore / V_bulk × 100%",
   vars:[{sym:"φ",desc:"المسامية (نسبة مئوية)"},{sym:"V_pore",desc:"حجم الفراغات داخل الصخرة"},{sym:"V_bulk",desc:"الحجم الكلي للصخرة"}],
   note:"المسامية المطلقة تقيس إجمالي الفراغات، أما الفعّالة فتقيس الفراغات المتصلة فقط."},
  {en:"Darcy's Law",ar:"قانون دارسي لمعدل التدفق",eq:"q = (k × A × ΔP) / (μ × L)",
   vars:[{sym:"q",desc:"معدل تدفق الموائع (سم³/ثانية)"},{sym:"k",desc:"النفاذية (داري)"},{sym:"A",desc:"مساحة المقطع العرضي (سم²)"},{sym:"ΔP",desc:"فرق الضغط (أتم)"},{sym:"μ",desc:"اللزوجة (سنتيبواز)"},{sym:"L",desc:"طول مسار التدفق (سم)"}],
   note:"قانون دارسي هو الأساس الرياضي لفهم حركة الموائع عبر الصخور المسامية."},
  {en:"API Gravity",ar:"درجة الثقل النوعي API",eq:"API° = (141.5 / SG) - 131.5",
   vars:[{sym:"API°",desc:"درجة الثقل النوعي"},{sym:"SG",desc:"الكثافة النسبية للنفط بالنسبة للماء عند 60°F"}],
   note:"الماء النقي = 10°API. النفط الخفيف أكثر من 35°، الثقيل أقل من 22°."},
  {en:"OOIP",ar:"كمية النفط الأصلية في المكمن",eq:"OOIP = (7758 × A × h × φ × (1 - Sw)) / Bo",
   vars:[{sym:"7758",desc:"ثابت التحويل من أكر-قدم إلى برميل"},{sym:"A",desc:"مساحة المكمن (أكر)"},{sym:"h",desc:"سماكة الطبقة الإنتاجية (قدم)"},{sym:"φ",desc:"المسامية (كسر عشري)"},{sym:"Sw",desc:"تشبع الماء (كسر عشري)"},{sym:"Bo",desc:"معامل الحجم التكويني (bbl/STB)"}],
   note:"المعادلة الحجمية الأكثر استخداماً في تقدير الاحتياطيات."},
  {en:"Productivity Index (PI)",ar:"مؤشر الإنتاجية",eq:"PI = q / (Pr - Pwf)",
   vars:[{sym:"PI",desc:"مؤشر الإنتاجية (bbl/day/psi)"},{sym:"q",desc:"معدل الإنتاج (برميل/يوم)"},{sym:"Pr",desc:"ضغط المكمن الساكن (psi)"},{sym:"Pwf",desc:"الضغط في القاع عند التدفق (psi)"}],
   note:"فرق الضغط (Pr - Pwf) يُسمى Draw-down. البئر الأعلى إنتاجية هو الأعلى PI."},
  {en:"Recovery Factor",ar:"عامل الاسترداد",eq:"RF = NP / OOIP",
   vars:[{sym:"RF",desc:"عامل الاسترداد (كسر عشري)"},{sym:"NP",desc:"إجمالي النفط المنتج (برميل)"},{sym:"OOIP",desc:"كمية النفط الأصلية (برميل)"}],
   note:"رفع العامل من 30% إلى 40% في مكمن كبير يعادل اكتشاف حقل جديد."},
  {en:"Real Gas Law",ar:"معادلة الغاز الحقيقي",eq:"PV = nZRT",
   vars:[{sym:"P",desc:"الضغط المطلق (psia)"},{sym:"V",desc:"حجم الغاز"},{sym:"n",desc:"عدد مولات الغاز"},{sym:"Z",desc:"معامل الانضغاطية"},{sym:"R",desc:"ثابت الغاز = 10.73"},{sym:"T",desc:"درجة الحرارة المطلقة (°R)"}],
   note:"عند Z=1 تصبح معادلة الغاز المثالي."},
  {en:"Formation Volume Factor (Bo)",ar:"معامل الحجم التكويني",eq:"Bo = V_res / V_surface",
   vars:[{sym:"Bo",desc:"معامل الحجم التكويني (bbl/STB)"},{sym:"V_res",desc:"حجم النفط داخل المكمن"},{sym:"V_surface",desc:"حجم النفط في ظروف السطح"}],
   note:"Bo عادةً أكبر من 1.0 لأن النفط يحتوي على غاز مذاب يتمدد عند السطح."},
  {en:"Water Cut",ar:"نسبة الماء المنتج",eq:"WC% = (q_w / (q_o + q_w)) × 100",
   vars:[{sym:"WC%",desc:"نسبة الماء المنتج"},{sym:"q_w",desc:"معدل إنتاج الماء (برميل/يوم)"},{sym:"q_o",desc:"معدل إنتاج النفط (برميل/يوم)"}],
   note:"عندما تتجاوز نسبة الماء 95% يصبح الإنتاج غير اقتصادي في معظم الحالات."},
  {en:"NPV",ar:"صافي القيمة الحالية",eq:"NPV = Σ [ CF_t / (1 + r)^t ] - C_0",
   vars:[{sym:"CF_t",desc:"التدفق النقدي في السنة t"},{sym:"r",desc:"معدل الخصم"},{sym:"t",desc:"السنة رقم t"},{sym:"C_0",desc:"الاستثمار الأولي"}],
   note:"NPV > 0 يعني المشروع مربح. NPV = 0 يعني معدل العائد الداخلي يساوي معدل الخصم."}
];
const tags={reservoir:"tag-reservoir",drilling:"tag-drilling",production:"tag-production",geology:"tag-geology",fluid:"tag-fluid",economics:"tag-economics"};
function renderTerms(list){
  const g=document.getElementById("termsGrid");
  g.innerHTML=list.map((t,i)=>`<div class="term-card"><div class="term-header" onclick="toggleCard(${i})"><span class="term-ar">${t.ar}</span><span class="term-en">${t.en}</span><span class="term-tag ${tags[t.tag]}">${t.tagLabel}</span></div><div class="term-body" id="body-${i}"><p class="term-definition">${t.def}</p></div></div>`).join("");
}
function toggleCard(i){document.getElementById("body-"+i).classList.toggle("open")}
function filterTerms(){
  const q=document.getElementById("searchInput").value.trim().toLowerCase();
  const f=q?TERMS.filter(t=>t.en.toLowerCase().includes(q)||t.ar.includes(q)||t.def.includes(q)):TERMS;
  renderTerms(f);
  document.getElementById("noResults").style.display=f.length?"none":"block";
}
function renderFormulas(){
  document.getElementById("formulasGrid").innerHTML=FORMULAS.map(f=>`<div class="formula-card"><div class="formula-card-header"><span class="formula-name-ar">${f.ar}</span><span class="formula-name-en">${f.en}</span></div><div class="formula-body"><div class="formula-eq">${f.eq}</div><div class="formula-vars">${f.vars.map(v=>`<div class="formula-var"><span class="var-sym">${v.sym} =</span><span class="var-desc">${v.desc}</span></div>`).join("")}</div>${f.note?`<div class="formula-note">💡 ${f.note}</div>`:""}</div></div>`).join("");
}
function showSection(id,btn){
  document.querySelectorAll(".section").forEach(s=>s.classList.remove("active"));
  document.querySelectorAll("nav button").forEach(b=>b.classList.remove("active"));
  document.getElementById(id).classList.add("active");
  btn.classList.add("active");
}
renderTerms(TERMS);
renderFormulas();
</script>
</body>
</html>"""


# ─────────────────────────────────────────────
#  HELPER FUNCTIONS
# ─────────────────────────────────────────────

def clean_text(text):
    text = str(text)
    replacements = {
        "**": "",
        "###": "",
        "##": "",
        "#": "",
        "|": " ",
        "[": "",
        "]": "",
        "Pressuring Volume and Temperature": "Pressure-Volume-Temperature",
        "الضغط البيني": "معامل حجم التكوين",
        "المعامل البيني": "معامل حجم التكوين",
        "الترشيح": "نسبة الغاز المذاب",
        "النسبة المئوية للغاز": "نسبة الغاز إلى الزيت",
        "نسبة الغاز المئوية": "نسبة الغاز إلى الزيت",
        "الويسكوزية": "اللزوجة",
        "الليزج": "اللزوجة",
        "الحفرة": "المكمن",
        "السطوع النوعي": "الكثافة النوعية",
        "اختبار السطوع": "اختبار الكثافة النوعية",
        "Volume Expansion Factor": "Oil Formation Volume Factor",
    }
    for wrong, correct in replacements.items():
        text = text.replace(wrong, correct)
    return text.strip()


def send_message(chat_id, text):
    text = clean_text(text)
    if not text:
        text = "لم أتمكن من توليد رد واضح."
    for i in range(0, len(text), 3900):
        requests.post(
            f"{TELEGRAM_URL}/sendMessage",
            data={"chat_id": chat_id, "text": text[i:i+3900]},
            timeout=30
        )
        time.sleep(0.4)


def send_glossary(chat_id):
    """إرسال ملف المصطلحات النفطية HTML مباشرة من الكود"""
    try:
        html_bytes = GLOSSARY_HTML.encode("utf-8")
        requests.post(
            f"{TELEGRAM_URL}/sendDocument",
            data={
                "chat_id": chat_id,
                "caption": (
                    "📚 المصطلحات النفطية الشاملة\n\n"
                    "يحتوي الملف على:\n"
                    "- 29 مصطلحاً نفطياً بتعريفات علمية\n"
                    "- 10 معادلات هندسية مع شرح الرموز\n"
                    "- خريطة مفاهيم تفاعلية\n\n"
                    "افتح الملف في أي متصفح للاستفادة الكاملة."
                )
            },
            files={"document": ("petroleum_glossary.html", html_bytes, "text/html")},
            timeout=30
        )
    except Exception as e:
        send_message(chat_id, "حدث خطأ أثناء إرسال ملف المصطلحات:\n" + str(e))


def download_telegram_file(file_id, file_name):
    info = requests.get(
        f"{TELEGRAM_URL}/getFile",
        params={"file_id": file_id},
        timeout=30
    ).json()
    file_path = info["result"]["file_path"]
    file_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"

    suffix = os.path.splitext(file_name)[1] or ".bin"
    temp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    temp.close()

    data = requests.get(file_url, timeout=60).content
    with open(temp.name, "wb") as f:
        f.write(data)
    return temp.name


def extract_pdf_text(path):
    text = ""
    reader = PdfReader(path)
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text += page_text + "\n\n"
    return text.strip()


def extract_docx_text(path):
    doc = Document(path)
    lines = []
    for p in doc.paragraphs:
        if p.text.strip():
            lines.append(p.text.strip())
    return "\n".join(lines)


def encode_image_to_data_url(path):
    mime_type, _ = mimetypes.guess_type(path)
    if not mime_type:
        mime_type = "image/jpeg"
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return f"data:{mime_type};base64,{b64}"


# ─────────────────────────────────────────────
#  AI FUNCTIONS
# ─────────────────────────────────────────────

def ask_ai(user_text, file_context=None):
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if file_context:
        messages.append({
            "role": "user",
            "content": "Reference PVT report or uploaded engineering context for this chat only:\n\n" + file_context[:25000]
        })
    messages.append({"role": "user", "content": user_text})

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": TEXT_MODEL,
        "messages": messages,
        "temperature": 0.08,
        "max_tokens": 3000
    }

    try:
        r = requests.post(GROQ_URL, headers=headers, json=payload, timeout=90)
        data = r.json()
        if "choices" in data:
            return data["choices"][0]["message"]["content"]
        return "حدث خطأ من Groq:\n" + str(data)[:1500]
    except Exception as e:
        return "حدث خطأ في الاتصال بخدمة الذكاء الاصطناعي:\n" + str(e)


def ask_vision_ai(prompt, image_path, file_context=None):
    image_url = encode_image_to_data_url(image_path)
    full_prompt = SYSTEM_PROMPT + "\n\nTask:\n" + prompt
    if file_context:
        full_prompt += "\n\nReference context:\n" + file_context[:12000]

    messages = [{
        "role": "user",
        "content": [
            {"type": "text", "text": full_prompt},
            {"type": "image_url", "image_url": {"url": image_url}}
        ]
    }]
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": VISION_MODEL,
        "messages": messages,
        "temperature": 0.08,
        "max_tokens": 2200
    }

    try:
        r = requests.post(GROQ_URL, headers=headers, json=payload, timeout=90)
        data = r.json()
        if "choices" in data:
            return data["choices"][0]["message"]["content"]
        return "حدث خطأ من Groq Vision:\n" + str(data)[:1500]
    except Exception as e:
        return "حدث خطأ في تحليل الصورة:\n" + str(e)


# ─────────────────────────────────────────────
#  HANDLERS
# ─────────────────────────────────────────────

def handle_document(chat_id, document):
    try:
        file_id = document["file_id"]
        file_name = document.get("file_name", "uploaded_file")
        mime_type = document.get("mime_type", "")
        local_path = download_telegram_file(file_id, file_name)
        lower = file_name.lower()

        if lower.endswith(".pdf"):
            text = extract_pdf_text(local_path)
            if not text:
                send_message(chat_id, "قرأت ملف PDF لكن لم أستخرج نصاً واضحاً. غالباً الملف سكان صورة. أرسل الصفحات أو الرسومات كصور، أو ارفعي PDF نصي.")
                return
            FILE_CONTEXT[chat_id] = text
            send_message(chat_id, "تم قراءة PDF بنجاح. الملف أصبح مرجعاً لهذه المحادثة. اكتب /analyze لتحليل التقرير هندسياً.")
            return

        if lower.endswith(".docx"):
            text = extract_docx_text(local_path)
            if not text:
                send_message(chat_id, "قرأت ملف DOCX لكن لم أجد نصاً واضحاً.")
                return
            FILE_CONTEXT[chat_id] = text
            send_message(chat_id, "تم قراءة DOCX بنجاح. الملف أصبح مرجعاً لهذه المحادثة.")
            return

        if mime_type.startswith("image/") or lower.endswith((".png", ".jpg", ".jpeg", ".webp")):
            IMAGE_CONTEXT[chat_id] = local_path
            send_message(chat_id, "تم استلام الصورة بنجاح. اكتب /graph لتحليل الرسم أو الشكل هندسياً.")
            return

        send_message(chat_id, "الملف لازم يكون PDF أو DOCX أو صورة.")
    except Exception as e:
        send_message(chat_id, "حدث خطأ أثناء قراءة الملف:\n" + str(e))


def handle_photo(chat_id, photos):
    try:
        best = photos[-1]
        file_id = best["file_id"]
        local_path = download_telegram_file(file_id, "uploaded_image.jpg")
        IMAGE_CONTEXT[chat_id] = local_path
        send_message(chat_id, "تم استلام الصورة بنجاح. اكتب /graph لتحليل الرسم أو الشكل هندسياً.")
    except Exception as e:
        send_message(chat_id, "حدث خطأ أثناء تحميل الصورة:\n" + str(e))


# ─────────────────────────────────────────────
#  COMMAND DETECTORS
# ─────────────────────────────────────────────

def is_graph_command(text):
    t = text.lower().strip()
    return t.startswith("/graph") or t.startswith("/interpret_graph")

def is_export_command(text):
    t = text.lower().strip()
    return t.startswith(("/export_sim", "/pvto", "/pvtg", "/eclipse", "/cmg"))

def is_plot_command(text):
    return text.lower().strip().startswith("/plot")

def is_surface_separator_question(text):
    t = text.lower()
    has_oil = "surface separator oil" in t or "separator oil" in t or "زيت من الفاصل" in t or "عينة زيت" in t
    has_gas = "separator gas" in t or "غاز من الفاصل" in t or "عينة غاز" in t
    return has_oil and has_gas


# ─────────────────────────────────────────────
#  STATIC RESPONSES
# ─────────────────────────────────────────────

def start_message():
    return """
أهلاً بك في PVT Lab AI Bot.

أنا مساعد هندسي متخصص في:
- PVT Laboratory
- Reservoir Fluid Analysis
- Reservoir Simulation
- PDF/DOCX report analysis
- Graph and figure interpretation
- Eclipse / CMG PVT guidance

الأوامر المتاحة:

/glossary - المصطلحات النفطية الشاملة مع المعادلات وخريطة المفاهيم
/analyze  - تحليل تقرير PVT مرفوع
/report   - هيكل تقرير PVT
/calc     - حسابات PVT
/plot     - رسومات PVT
/graph    - تحليل رسم أو صورة هندسية
/check    - فحص بيانات
/export_sim - تصدير بيانات للمحاكاة
/pvto     - جدول PVTO لـ Eclipse
/pvtg     - جدول PVTG لـ Eclipse
/eclipse  - إرشادات Eclipse
/cmg      - إرشادات CMG

ملاحظة:
لا أحسب قيماً نهائية أو أكتب بيانات مخبرية رقمية إلا إذا زودتني بالبيانات.
"""


def surface_separator_direct_answer():
    return """
تحليل هندسي لعينة زيت من الفاصل السطحي مع عينة غاز من الفاصل

نوع العينات

العينات المذكورة هي عينات سطحية منفصلة:
- Surface Separator Oil Sample: عينة زيت من الفاصل السطحي.
- Separator Gas Sample: عينة غاز من الفاصل.

هذه العينات لا تمثل سائل المكمن الأصلي مباشرة مثل Bottom Hole Sample، لأن الزيت والغاز انفصلا عند ظروف الفاصل السطحي. لذلك يلزم عادة إجراء Recombination لإعادة بناء سائل المكمن قبل الحكم على خواص PVT النهائية.

البيانات المطلوبة

- Separator Pressure ضغط الفاصل.
- Separator Temperature درجة حرارة الفاصل.
- Oil Rate معدل إنتاج الزيت.
- Gas Rate معدل إنتاج الغاز.
- Producing GOR أو Separator GOR نسبة الغاز إلى الزيت.
- Separator Gas Composition تركيب غاز الفاصل.
- Separator Oil أو Stock Tank Oil Composition تركيب الزيت.
- Oil Density كثافة الزيت.
- API Gravity درجة API.
- Gas Specific Gravity الكثافة النوعية للغاز.
- Water Cut أو وجود مستحلب.
- CO2 و H2S إن وجدت.

الاختبارات المطلوبة

1. Sample QC
2. Compositional Analysis
3. Recombination
4. Validation of Recombined Fluid
5. CCE أو CME
6. DV Differential Vaporization (للزيت)
7. CVD Constant Volume Depletion (للغاز المكثف)
8. Separator Test
9. Viscosity Test

المنحنيات المطلوبة

- Pressure vs Bo
- Pressure vs Rs
- Pressure vs Oil Viscosity
- Pressure vs Density
- Pressure vs Relative Volume
- Pressure vs Y-Function

إعداد المحاكاة

إذا كان السائل Black Oil:
تستخدم بيانات DV و Separator Test لتجهيز PVTO في Eclipse.

إذا كان السائل Gas Condensate أو Volatile Oil:
الأفضل استخدام Compositional Model مع EOS Tuning.

الخلاصة

الخطوة الصحيحة هي إجراء Recombination أولاً ثم اختبارات PVT المناسبة. بدون بيانات الفاصل و GOR والتركيب لا يمكن حساب قيم نهائية موثوقة.
"""


# ─────────────────────────────────────────────
#  MAIN LOOP
# ─────────────────────────────────────────────

while True:
    try:
        updates = requests.get(
            f"{TELEGRAM_URL}/getUpdates",
            params={"offset": offset + 1, "timeout": 30},
            timeout=40
        ).json()

        for update in updates.get("result", []):
            offset = update["update_id"]
            if "message" not in update:
                continue

            message = update["message"]
            chat_id = message["chat"]["id"]

            if "document" in message:
                handle_document(chat_id, message["document"])
                continue

            if "photo" in message:
                handle_photo(chat_id, message["photo"])
                continue

            if "text" not in message:
                send_message(chat_id, "أرسلي نصاً أو ملف PDF/DOCX أو صورة.")
                continue

            text = message["text"]
            context = FILE_CONTEXT.get(chat_id)

            # ── COMMANDS ──
            if text.strip() == "/start":
                send_message(chat_id, start_message())
                continue

            if text.strip() == "/glossary":
                send_glossary(chat_id)
                continue

            if is_surface_separator_question(text):
                send_message(chat_id, surface_separator_direct_answer())
                continue

            if is_graph_command(text):
                image_path = IMAGE_CONTEXT.get(chat_id)
                if not image_path:
                    send_message(chat_id, "أرسلي صورة الرسم أو Figure أولاً، وبعدها اكتبي /graph.")
                    continue
                prompt = (
                    text +
                    "\n\nAnalyze this engineering figure professionally. "
                    "Identify axes, units, trend, anomalies, non-physical behavior, "
                    "retrograde behavior if applicable, contamination indicators, "
                    "separator performance issues, engineering meaning, possible causes, and recommendations."
                )
                reply = ask_vision_ai(prompt, image_path, context)
                send_message(chat_id, reply)
                continue

            if is_plot_command(text):
                prompt = (
                    text +
                    "\n\nIf numerical data are provided, explain which PVT plot should be prepared "
                    "and interpret the expected trend. If data are missing, list the exact arrays needed. "
                    "Do not invent values."
                )
                reply = ask_ai(prompt, context)
                send_message(chat_id, reply)
                continue

            if is_export_command(text):
                prompt = (
                    text +
                    "\n\nGenerate simulator export guidance. Decide black-oil vs compositional based on data. "
                    "Include unit checks, consistency checks, Eclipse/CMG keyword guidance, warnings, "
                    "and missing required data."
                )
                reply = ask_ai(prompt, context)
                send_message(chat_id, reply)
                continue

            # ── DEFAULT: AI RESPONSE ──
            reply = ask_ai(text, context)
            send_message(chat_id, reply)

      except Exception as e:
        print(e)

    time.sleep(1)
