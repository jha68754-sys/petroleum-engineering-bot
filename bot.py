"""
PVT Lab AI Bot — Final Professional Version
============================================
v1: Full SYSTEM_PROMPT, clean_text(), surface_separator answer, rich Glossary HTML
v2: Calculation engine (API/Hydrostatic/OOIP/Darcy/RF/WC), /calc command, better error handling
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
FILE_CONTEXT  = {}   # chat_id -> extracted document text
IMAGE_CONTEXT = {}   # chat_id -> local image path

# ─────────────────────────────────────────────
#  SYSTEM PROMPT
# ─────────────────────────────────────────────
SYSTEM_PROMPT = """
You are a professional Petroleum Engineering, PVT Laboratory, Reservoir Fluid Analysis,
and Reservoir Simulation assistant. Answer like a real PVT laboratory engineer, not a generic chatbot.

Language rules:
- Arabic message -> answer in strong professional Arabic.
- English message -> answer in professional petroleum engineering English.
- Mixed -> match the user style naturally.
- Keep key technical terms in English beside Arabic when useful.

Correct terminology:
PVT = Pressure-Volume-Temperature.
Reservoir = المكمن.  Well = البئر.  Formation = التكوين.
Bottom Hole Sample = عينة قاع البئر.
Surface Separator Oil Sample = عينة زيت من الفاصل السطحي.
Separator Gas Sample = عينة غاز من الفاصل.
Recombination = اعادة تركيب العينة.
Bubble Point Pressure = ضغط نقطة الفقاعة.
Dew Point Pressure = ضغط نقطة الندى.
Bo = معامل حجم التكوين للزيت (Oil Formation Volume Factor).
Bg = معامل حجم التكوين للغاز (Gas Formation Volume Factor).
Rs = نسبة الغاز المذاب (Solution Gas-Oil Ratio).
GOR = نسبة الغاز الى الزيت (Gas-Oil Ratio).
CGR = نسبة المكثفات الى الغاز (Condensate-Gas Ratio).
Z-factor = معامل الانحراف الغازي.
Viscosity = اللزوجة.  Density = الكثافة.
Specific Gravity = الكثافة النوعية.  API Gravity = درجة API.
CCE = Constant Composition Expansion.
DV = Differential Vaporization / Differential Liberation.
CVD = Constant Volume Depletion.
Skin Factor = عامل الجلد.  Permeability = النفاذية.
Porosity = المسامية.  Hydrostatic Pressure = الضغط الهيدروستاتيكي.
Kick = اندفاع المكمن.

FORBIDDEN — never use these:
- Do NOT call Bo: الضغط البيني or المعامل البيني.
- Do NOT call Rs: الترشيح.
- Do NOT call GOR: النسبة المئوية للغاز.
- Do NOT say الليزج for Viscosity.
- Do NOT say الحفرة for Reservoir.
- Do NOT define PVT as Pressuring Volume and Temperature.
- Do NOT invent numerical PVT values unless user asks for demo data.
- Do NOT create fake lab tables.

Answer structure:
1. Identify sample type or question category.
2. Identify fluid system (Black Oil / Volatile Oil / Gas Condensate / Dry Gas).
3. Select correct workflow.
4. Explain required lab tests or engineering steps.
5. Show calculations ONLY if real input data are provided.
6. List required plots if applicable.
7. Mention simulation relevance (Eclipse/CMG) if applicable.
8. State missing data clearly.
9. Give concise engineering interpretation.

Surface Separator logic:
- Surface Separator Oil + Gas samples are NOT direct reservoir fluid.
- Always recommend Recombination first.
- Required: Separator P&T, Oil Rate, Gas Rate, GOR, Compositions, API, Gas SG, Water Cut, H2S/CO2.

Formatting:
- No markdown ** or ###.
- No vertical-line tables.
- Clean plain text with clear section headings.
- Be concise, direct, professional.
"""

# ─────────────────────────────────────────────
#  TEXT CLEANER  — fixes wrong Arabic petroleum terms
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
        "Volume Expansion Factor": "Oil Formation Volume Factor",
    }
    for wrong, right in fixes.items():
        text = text.replace(wrong, right)
    return text.strip()


# ─────────────────────────────────────────────
#  CALCULATION ENGINE
# ─────────────────────────────────────────────
def handle_calculation(query: str):
    q    = query.lower()
    nums = [float(x) for x in re.findall(r"[-+]?\d*\.?\d+", query) if x]

    # 1. API Gravity
    if "api" in q and any(k in q for k in ["sg", "specific gravity", "gravity"]):
        if nums:
            sg = nums[0]
            if 0.5 < sg < 1.5:
                api = (141.5 / sg) - 131.5
                cls = "نفط خفيف" if api > 35 else "نفط متوسط" if api > 22 else "نفط ثقيل"
                return (f"حساب درجة API\n\n"
                        f"المعادلة: API = (141.5 / SG) - 131.5\n"
                        f"Specific Gravity = {sg}\n"
                        f"النتيجة: {api:.2f} API\n"
                        f"التصنيف: {cls}")

    # 2. Hydrostatic Pressure
    if "hydrostatic" in q or ("pressure" in q and any(k in q for k in ["mw","mud","tvd"])):
        if len(nums) >= 2:
            mw, tvd = nums[0], nums[1]
            hp = 0.052 * mw * tvd
            return (f"حساب الضغط الهيدروستاتيكي\n\n"
                    f"المعادلة: P = 0.052 x MW x TVD\n"
                    f"MW = {mw} ppg\n"
                    f"TVD = {tvd} ft\n"
                    f"النتيجة: {hp:.2f} psi")

    # 3. OOIP
    if "ooip" in q:
        if len(nums) >= 5:
            a, h, phi, sw, bo = nums[0], nums[1], nums[2], nums[3], nums[4]
            ooip = (7758 * a * h * phi * (1 - sw)) / bo
            return (f"حساب OOIP\n\n"
                    f"المعادلة: OOIP = (7758 x A x h x phi x (1-Sw)) / Bo\n"
                    f"Area={a} acres | h={h} ft | phi={phi} | Sw={sw} | Bo={bo}\n"
                    f"النتيجة: {ooip:,.0f} STB")
        return ("لحساب OOIP احتاج 5 قيم:\n"
                "مثال: /calc ooip 500 50 0.2 0.3 1.3\n"
                "(Area acres, h ft, porosity, Sw, Bo)")

    # 4. Darcy Linear Flow
    if "darcy" in q or "flow rate" in q:
        if len(nums) >= 5:
            k, a, dp, mu, l = nums[0], nums[1], nums[2], nums[3], nums[4]
            q_rate = (0.001127 * k * a * dp) / (mu * l)
            return (f"حساب تدفق Darcy الخطي\n\n"
                    f"المعادلة: q = 0.001127 x k x A x dP / (mu x L)\n"
                    f"k={k} mD | A={a} ft2 | dP={dp} psi | mu={mu} cP | L={l} ft\n"
                    f"النتيجة: {q_rate:.4f} bbl/day")

    # 5. Recovery Factor
    if "recovery" in q or " rf " in q:
        if len(nums) >= 2:
            np_v, ooip_v = nums[0], nums[1]
            rf = (np_v / ooip_v) * 100
            return (f"حساب عامل الاسترداد\n\n"
                    f"المعادلة: RF = NP / OOIP x 100\n"
                    f"NP={np_v:,.0f} | OOIP={ooip_v:,.0f}\n"
                    f"النتيجة: RF = {rf:.2f}%")

    # 6. Water Cut
    if "water cut" in q or "wc" in q:
        if len(nums) >= 2:
            qw, qo = nums[0], nums[1]
            wc = (qw / (qo + qw)) * 100
            return (f"حساب نسبة الماء المنتج\n\n"
                    f"المعادلة: WC = qw / (qo + qw) x 100\n"
                    f"qw={qw} | qo={qo} bbl/day\n"
                    f"النتيجة: WC = {wc:.2f}%")

    return None


# ─────────────────────────────────────────────
#  GLOSSARY HTML  — complete interactive design
# ─────────────────────────────────────────────
GLOSSARY_HTML = open("/dev/stdin").read() if False else r"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>المصطلحات النفطية</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@300;400;600;700;900&family=Fira+Code:wght@400;600&display=swap');
:root{--crude:#3d1f00;--amber:#c8760a;--gold:#e8a020;--light:#fef3dc;--surface:#f5f0e8;--paper:#fdfaf4;--border:#ddd0b8;--muted:#7a6a58;--dbg:#0d1117}
*{box-sizing:border-box;margin:0;padding:0}body{font-family:'Cairo',sans-serif;background:var(--surface);color:#111;line-height:1.7}
header{background:var(--crude);color:var(--paper);padding:2.5rem 2rem 2rem;text-align:center}
header h1{font-size:clamp(1.6rem,4vw,2.5rem);font-weight:900}header h1 span{color:var(--gold)}
header p{margin-top:.4rem;font-size:.95rem;opacity:.65}
nav{display:flex;justify-content:center;gap:.5rem;flex-wrap:wrap;padding:1.2rem 1rem;background:var(--paper);border-bottom:2px solid var(--border);position:sticky;top:0;z-index:100;box-shadow:0 2px 10px rgba(0,0,0,.07)}
nav button{padding:.45rem 1.1rem;border:2px solid var(--border);border-radius:999px;background:transparent;font-family:'Cairo',sans-serif;font-size:.82rem;font-weight:600;color:var(--muted);cursor:pointer;transition:all .2s}
nav button:hover{border-color:var(--amber);color:var(--amber)}nav button.active{background:var(--amber);border-color:var(--amber);color:#fff}
main{max-width:1080px;margin:0 auto;padding:2rem 1.5rem 4rem}.sec{display:none}.sec.active{display:block}
.search input{width:100%;padding:.7rem 1.2rem;border:2px solid var(--border);border-radius:8px;font-family:'Cairo',sans-serif;font-size:1rem;background:var(--paper);margin-bottom:1.5rem;transition:border .2s}
.search input:focus{outline:none;border-color:var(--amber)}
.grid{display:grid;gap:1rem}.card{background:var(--paper);border:1.5px solid var(--border);border-radius:10px;overflow:hidden;transition:box-shadow .2s,border-color .2s}
.card:hover{box-shadow:0 4px 18px rgba(200,118,10,.14);border-color:var(--amber)}
.card-head{display:flex;align-items:center;gap:.8rem;padding:.9rem 1.3rem;cursor:pointer;flex-wrap:wrap}
.ar{font-size:1rem;font-weight:700;color:var(--crude);flex:1}.en{font-family:'Fira Code',monospace;font-size:.82rem;font-weight:600;color:var(--amber);background:var(--light);padding:.2rem .6rem;border-radius:5px;direction:ltr;white-space:nowrap}
.badge{font-size:.68rem;padding:.18rem .55rem;border-radius:999px;font-weight:700;white-space:nowrap}
.b-res{background:#dbeafe;color:#1e40af}.b-pvt{background:#fef9c3;color:#854d0e}.b-pro{background:#dcfce7;color:#166534}.b-drl{background:#ffe4e6;color:#9f1239}.b-geo{background:#f3e8ff;color:#6b21a8}.b-eco{background:#e0f2fe;color:#0369a1}
.card-body{display:none;padding:0 1.3rem 1.2rem;border-top:1px solid var(--border)}.card-body.open{display:block}
.def{margin-top:.9rem;font-size:.95rem;color:#333;line-height:1.85}
.ftitle{font-size:1.3rem;font-weight:900;color:var(--crude);margin-bottom:1.2rem;padding-bottom:.4rem;border-bottom:3px solid var(--amber)}
.fcard{background:var(--dbg);border-radius:10px;overflow:hidden;margin-bottom:1.2rem;border:1px solid #2a3040}
.fcard-head{display:flex;justify-content:space-between;align-items:center;padding:.8rem 1.3rem;background:rgba(200,118,10,.11);border-bottom:1px solid #2a3040}
.f-en{font-family:'Fira Code',monospace;color:var(--gold);font-size:.88rem;direction:ltr}.f-ar{color:rgba(255,255,255,.85);font-size:.9rem;font-weight:600}
.fcard-body{padding:1.1rem 1.3rem}.eq{font-family:'Fira Code',monospace;color:var(--gold);font-size:1.05rem;text-align:center;direction:ltr;padding:.7rem 0}
.vars{margin-top:.9rem;border-top:1px solid #2a3040;padding-top:.9rem}.vrow{display:flex;gap:.7rem;margin-bottom:.4rem;direction:rtl}
.vsym{font-family:'Fira Code',monospace;color:var(--gold);font-size:.82rem;min-width:75px;direction:ltr;text-align:right}
.vdesc{color:rgba(255,255,255,.68);font-size:.82rem;line-height:1.55}
.fnote{margin-top:.7rem;padding:.55rem .85rem;background:rgba(232,160,32,.07);border-right:3px solid var(--gold);border-radius:0 5px 5px 0;color:rgba(255,255,255,.6);font-size:.8rem}
.map-wrap{background:var(--paper);border-radius:14px;border:2px solid var(--border);padding:1.8rem}
.map-title{text-align:center;font-size:1.3rem;font-weight:900;color:var(--crude);margin-bottom:1.3rem}
svg.cmap{width:100%;height:auto;display:block}
.legend{display:flex;flex-wrap:wrap;gap:.9rem;justify-content:center;margin-top:1.3rem}
.li{display:flex;align-items:center;gap:.35rem;font-size:.8rem;color:var(--muted)}.ldot{width:11px;height:11px;border-radius:50%}
.rels{margin-top:1.5rem;padding:1.1rem;background:#f5f0e8;border-radius:9px;border:1px solid var(--border)}
.rels p{font-size:.88rem;color:var(--crude);font-weight:700;margin-bottom:.6rem}
.rels ul{list-style:none;display:grid;gap:.5rem;font-size:.85rem;color:var(--muted)}.nr{text-align:center;padding:3rem;color:var(--muted)}
</style></head><body>
<header><h1>المصطلحات <span>النفطية</span> التقنية<br><small style="font-size:.52em;font-weight:300;opacity:.65">Petroleum Engineering Terminology</small></h1><p>تعريفات علمية - معادلات هندسية - خريطة المفاهيم</p></header>
<nav><button class="active" onclick="show('terms',this)">المصطلحات</button><button onclick="show('formulas',this)">المعادلات</button><button onclick="show('map',this)">خريطة المفاهيم</button></nav>
<main>
<div id="terms" class="sec active"><div class="search"><input id="q" placeholder="ابحث عن مصطلح..." oninput="filter()"/></div><div class="grid" id="tgrid"></div><div class="nr" id="nr" style="display:none">لا توجد نتائج</div></div>
<div id="formulas" class="sec"><p class="ftitle">المعادلات الهندسية النفطية</p><div id="fgrid"></div></div>
<div id="map" class="sec"><div class="map-wrap"><div class="map-title">خريطة المفاهيم المركزية - هندسة النفط والغاز</div>
<svg class="cmap" viewBox="0 0 900 620" xmlns="http://www.w3.org/2000/svg">
<defs><marker id="arr" markerWidth="9" markerHeight="6" refX="9" refY="3" orient="auto"><polygon points="0 0,9 3,0 6" fill="#c8760a" opacity=".75"/></marker><filter id="sh"><feDropShadow dx="0" dy="2" stdDeviation="3" flood-opacity=".12"/></filter></defs>
<rect width="900" height="620" fill="#fdfaf4" rx="12"/>
<line x1="450" y1="310" x2="450" y2="138" stroke="#c8760a" stroke-width="1.8" stroke-dasharray="5,3" marker-end="url(#arr)" opacity=".6"/>
<line x1="450" y1="310" x2="205" y2="192" stroke="#166534" stroke-width="1.8" stroke-dasharray="5,3" marker-end="url(#arr)" opacity=".6"/>
<line x1="450" y1="310" x2="695" y2="192" stroke="#9f1239" stroke-width="1.8" stroke-dasharray="5,3" marker-end="url(#arr)" opacity=".6"/>
<line x1="450" y1="310" x2="195" y2="445" stroke="#7c3aed" stroke-width="1.8" stroke-dasharray="5,3" marker-end="url(#arr)" opacity=".6"/>
<line x1="450" y1="310" x2="700" y2="445" stroke="#0369a1" stroke-width="1.8" stroke-dasharray="5,3" marker-end="url(#arr)" opacity=".6"/>
<line x1="450" y1="310" x2="450" y2="510" stroke="#854d0e" stroke-width="1.8" stroke-dasharray="5,3" marker-end="url(#arr)" opacity=".6"/>
<g filter="url(#sh)"><ellipse cx="450" cy="310" rx="88" ry="46" fill="#3d1f00"/><text x="450" y="304" text-anchor="middle" fill="#fef3dc" font-family="Cairo,sans-serif" font-size="13" font-weight="700">هندسة النفط</text><text x="450" y="320" text-anchor="middle" fill="#c8760a" font-family="Fira Code,monospace" font-size="9">Petroleum Eng.</text></g>
<g filter="url(#sh)"><rect x="338" y="58" width="224" height="74" rx="11" fill="#fef3dc" stroke="#c8760a" stroke-width="1.8"/><text x="450" y="87" text-anchor="middle" fill="#3d1f00" font-family="Cairo,sans-serif" font-size="13" font-weight="700">المكمن النفطي</text><text x="450" y="101" text-anchor="middle" fill="#c8760a" font-family="Fira Code,monospace" font-size="9">Reservoir</text><text x="450" y="118" text-anchor="middle" fill="#7a6a58" font-family="Cairo,sans-serif" font-size="9">مسامية - نفاذية - ضغط</text></g>
<g filter="url(#sh)"><rect x="78" y="150" width="198" height="74" rx="11" fill="#dcfce7" stroke="#166534" stroke-width="1.8"/><text x="177" y="179" text-anchor="middle" fill="#14532d" font-family="Cairo,sans-serif" font-size="13" font-weight="700">الحفر</text><text x="177" y="193" text-anchor="middle" fill="#166534" font-family="Fira Code,monospace" font-size="9">Drilling</text><text x="177" y="210" text-anchor="middle" fill="#7a6a58" font-family="Cairo,sans-serif" font-size="9">WOB - ROP - BOP</text></g>
<g filter="url(#sh)"><rect x="624" y="150" width="198" height="74" rx="11" fill="#ffe4e6" stroke="#9f1239" stroke-width="1.8"/><text x="723" y="179" text-anchor="middle" fill="#9f1239" font-family="Cairo,sans-serif" font-size="13" font-weight="700">الانتاج</text><text x="723" y="193" text-anchor="middle" fill="#9f1239" font-family="Fira Code,monospace" font-size="9">Production</text><text x="723" y="210" text-anchor="middle" fill="#7a6a58" font-family="Cairo,sans-serif" font-size="9">GOR - PI - Water Cut</text></g>
<g filter="url(#sh)"><rect x="68" y="402" width="210" height="74" rx="11" fill="#f3e8ff" stroke="#7c3aed" stroke-width="1.8"/><text x="173" y="431" text-anchor="middle" fill="#4c1d95" font-family="Cairo,sans-serif" font-size="13" font-weight="700">خواص الموائع</text><text x="173" y="445" text-anchor="middle" fill="#7c3aed" font-family="Fira Code,monospace" font-size="9">PVT / Fluid Props</text><text x="173" y="462" text-anchor="middle" fill="#7a6a58" font-family="Cairo,sans-serif" font-size="9">Bo - Rs - Z-factor - API</text></g>
<g filter="url(#sh)"><rect x="622" y="402" width="210" height="74" rx="11" fill="#e0f2fe" stroke="#0369a1" stroke-width="1.8"/><text x="727" y="431" text-anchor="middle" fill="#0c4a6e" font-family="Cairo,sans-serif" font-size="13" font-weight="700">الاقتصاديات</text><text x="727" y="445" text-anchor="middle" fill="#0369a1" font-family="Fira Code,monospace" font-size="9">Economics</text><text x="727" y="462" text-anchor="middle" fill="#7a6a58" font-family="Cairo,sans-serif" font-size="9">NPV - EUR - Break-Even</text></g>
<g filter="url(#sh)"><rect x="338" y="478" width="224" height="74" rx="11" fill="#fef9c3" stroke="#854d0e" stroke-width="1.8"/><text x="450" y="507" text-anchor="middle" fill="#713f12" font-family="Cairo,sans-serif" font-size="13" font-weight="700">الجيولوجيا</text><text x="450" y="521" text-anchor="middle" fill="#854d0e" font-family="Fira Code,monospace" font-size="9">Geology</text><text x="450" y="538" text-anchor="middle" fill="#7a6a58" font-family="Cairo,sans-serif" font-size="9">تكوين - فالق - مصيدة</text></g>
</svg>
<div class="legend"><div class="li"><div class="ldot" style="background:#c8760a"></div>المكمن</div><div class="li"><div class="ldot" style="background:#166534"></div>الحفر</div><div class="li"><div class="ldot" style="background:#9f1239"></div>الانتاج</div><div class="li"><div class="ldot" style="background:#7c3aed"></div>الموائع</div><div class="li"><div class="ldot" style="background:#0369a1"></div>الاقتصاد</div><div class="li"><div class="ldot" style="background:#854d0e"></div>الجيولوجيا</div></div>
<div class="rels"><p>العلاقات المحورية:</p><ul><li>الجيولوجيا تحدد شكل المكمن وطبيعة مصيدة الهيدروكربونات</li><li>المسامية والنفاذية تتحكم مباشرة في معدلات الانتاج</li><li>خواص PVT تربط بين المكمن ومنظومة الانتاج السطحية</li><li>الحفر هو الجسر بين السطح والمكمن تحت الارض</li><li>الاقتصاديات تحكم جدوى كل قرار هندسي</li><li>GOR يربط خواص الموائع بكفاءة منظومة الانتاج</li></ul></div></div></div>
</main>
<script>
const T=[
{en:"Porosity",ar:"المسامية",cl:"b-res",lbl:"المكمن",def:"النسبة المئوية لحجم الفراغات الى الحجم الكلي للصخرة. طاقة التخزين. تتراوح بين 5% و35%."},
{en:"Permeability",ar:"النفاذية",cl:"b-res",lbl:"المكمن",def:"قدرة الصخرة على السماح بتدفق الموائع تحت فرق الضغط. تقاس بالداري (D) او الميلي-داري (mD)."},
{en:"Reservoir Pressure",ar:"ضغط المكمن",cl:"b-res",lbl:"المكمن",def:"الضغط الناجم عن وزن الطبقات وتمدد الموائع المحبوسة. المحرك الرئيسي لدفع الموائع نحو البئر."},
{en:"Water Saturation (Sw)",ar:"تشبع الماء",cl:"b-res",lbl:"المكمن",def:"نسبة حجم الماء الى حجم المسامية. كلما قل Sw زادت احتمالية وجود الهيدروكربونات."},
{en:"Net Pay",ar:"سماكة الطبقة الانتاجية",cl:"b-res",lbl:"المكمن",def:"السمك الفعلي من الصخرة الخازنة التي تحتوي هيدروكربونات قابلة للانتاج اقتصاديا."},
{en:"OOIP",ar:"النفط الاصلي في المكمن",cl:"b-res",lbl:"المكمن",def:"الحجم الكلي للنفط قبل بدء الانتاج. يعتمد على عامل الاسترداد لمعرفة ما يمكن استخراجه."},
{en:"Recovery Factor",ar:"عامل الاسترداد",cl:"b-res",lbl:"المكمن",def:"النسبة المئوية من OOIP التي يمكن استخراجها فعليا. تتراوح عادة بين 20% و50%."},
{en:"Bubble Point Pressure",ar:"ضغط نقطة الفقاعة",cl:"b-pvt",lbl:"PVT",def:"الضغط الذي يبدا عنده الغاز المذاب بالانفصال من النفط. فوقه النفط سائل نقي."},
{en:"Dew Point Pressure",ar:"ضغط نقطة الندى",cl:"b-pvt",lbl:"PVT",def:"الضغط الذي تبدا عنده اول قطرة سائل بالتكون من الغاز. خاص بانظمة الغاز المكثف."},
{en:"Formation Volume Factor (Bo)",ar:"معامل حجم التكوين للزيت",cl:"b-pvt",lbl:"PVT",def:"نسبة حجم النفط داخل المكمن الى حجمه في ظروف السطح. عادة اكبر من 1.0."},
{en:"Solution GOR (Rs)",ar:"نسبة الغاز المذاب",cl:"b-pvt",lbl:"PVT",def:"حجم الغاز المذاب في النفط داخل المكمن لكل برميل زيت سطحي. تتناقص مع انخفاض الضغط."},
{en:"Z-Factor",ar:"معامل الانضغاطية",cl:"b-pvt",lbl:"PVT",def:"معامل تصحيح سلوك الغاز الحقيقي عن المثالي. يدخل في كل حسابات الغاز."},
{en:"Viscosity",ar:"اللزوجة",cl:"b-pvt",lbl:"PVT",def:"مقاومة الموائع للتدفق. تقاس بالسنتيبواز (cP). للزيت تزيد مع انخفاض الضغط دون نقطة الفقاعة."},
{en:"API Gravity",ar:"درجة API",cl:"b-pvt",lbl:"PVT",def:"مقياس كثافة النفط النسبية. API = (141.5/SG) - 131.5. النفط الخفيف اكثر من 35 درجة."},
{en:"Skin Factor",ar:"عامل الجلد",cl:"b-pro",lbl:"الانتاج",def:"مقياس تاثير الضرر او التحفيز حول البئر. موجب يعني ضرر، سالب يعني تحفيز Stimulation."},
{en:"Productivity Index (PI)",ar:"مؤشر الانتاجية",cl:"b-pro",lbl:"الانتاج",def:"معدل الانتاج لكل وحدة فرق ضغط. PI = q / (Pr - Pwf). كلما ارتفع PI كان البئر اكفا."},
{en:"Gas-Oil Ratio (GOR)",ar:"نسبة الغاز الى الزيت",cl:"b-pro",lbl:"الانتاج",def:"حجم الغاز المنتج لكل برميل زيت. تقاس بـ scf/STB. تزداد مع تناقص ضغط المكمن."},
{en:"Water Cut",ar:"نسبة الماء المنتج",cl:"b-pro",lbl:"الانتاج",def:"نسبة الماء في اجمالي السوائل المنتجة. تزداد مع تقدم عمر البئر."},
{en:"Artificial Lift",ar:"الرفع الاصطناعي",cl:"b-pro",lbl:"الانتاج",def:"تقنيات لرفع الموائع عند انعدام الضغط الطبيعي: ESP، Gas Lift، Rod Pump."},
{en:"Weight on Bit (WOB)",ar:"الحمل على القاطعة",cl:"b-drl",lbl:"الحفر",def:"الحمل العمودي على لقمة الحفر لتكسير الصخر. التحكم فيه يمنع انحناء عمود الحفر."},
{en:"Rate of Penetration (ROP)",ar:"معدل الحفر",cl:"b-drl",lbl:"الحفر",def:"سرعة تقدم اللقمة في الصخر. م/ساعة. تعتمد على WOB وطبيعة الصخر."},
{en:"Mud Weight",ar:"وزن طين الحفر",cl:"b-drl",lbl:"الحفر",def:"كثافة سائل الحفر (ppg). يتحكم في توازن الضغط بين البئر والمكمن."},
{en:"Hydrostatic Pressure",ar:"الضغط الهيدروستاتيكي",cl:"b-drl",lbl:"الحفر",def:"الضغط الناجم عن عمود السائل. P(psi) = 0.052 x MW(ppg) x TVD(ft)."},
{en:"Blowout Preventer (BOP)",ar:"مانع الانفجار",cl:"b-drl",lbl:"الحفر",def:"جهاز طوارئ يغلق البئر فورا عند حدوث Kick. خط الدفاع الاول لسلامة البئر."},
{en:"Kick",ar:"اندفاع المكمن",cl:"b-drl",lbl:"الحفر",def:"دخول غير متحكم لسوائل المكمن الى البئر. يستلزم اغلاق BOP فورا."},
{en:"Anticline",ar:"الطية المحدبة",cl:"b-geo",lbl:"الجيولوجيا",def:"طية صخرية مقوسة للاعلى. اهم مصائد النفط البنيوية."},
{en:"Cap Rock / Seal",ar:"الصخرة العازلة",cl:"b-geo",lbl:"الجيولوجيا",def:"طبقة غير نافذة فوق المكمن تمنع هروب الهيدروكربونات. شرط اساسي لاي مكمن."},
{en:"Source Rock",ar:"صخرة المصدر",cl:"b-geo",lbl:"الجيولوجيا",def:"صخرة رسوبية غنية بالمادة العضوية انتجت النفط والغاز بالحرارة والضغط عبر الزمن."},
{en:"Trap",ar:"المصيدة الجيولوجية",cl:"b-geo",lbl:"الجيولوجيا",def:"اي تشكل يوقف هجرة الهيدروكربونات ويجمعها. بنيوية (طية/فالق) او طباقية."},
{en:"NPV",ar:"صافي القيمة الحالية",cl:"b-eco",lbl:"الاقتصاد",def:"مجموع التدفقات النقدية المخصومة ناقصا الاستثمار الاولي. NPV اكبر من صفر يعني المشروع مجدٍ."},
{en:"EUR",ar:"الاحتياطيات الاجمالية المتوقعة",cl:"b-eco",lbl:"الاقتصاد",def:"اجمالي الانتاج المتوقع من البئر طوال حياته الانتاجية الكاملة."},
{en:"Break-Even Price",ar:"سعر التعادل",cl:"b-eco",lbl:"الاقتصاد",def:"ادنى سعر نفط يغطي كل تكاليف التطوير والانتاج دون ربح او خسارة."}
];
const F=[
{en:"Porosity",ar:"معادلة المسامية",eq:"phi = V_pore / V_bulk x 100%",vars:[{s:"phi",d:"المسامية %"},{s:"V_pore",d:"حجم الفراغات"},{s:"V_bulk",d:"الحجم الكلي"}],note:"الفعالة تقيس المسامية المتصلة فقط — هي المهمة للانتاج."},
{en:"Darcy Law",ar:"قانون دارسي",eq:"q = (k x A x dP) / (mu x L)",vars:[{s:"q",d:"معدل التدفق (cc/s)"},{s:"k",d:"النفاذية (Darcy)"},{s:"A",d:"مساحة المقطع (cm2)"},{s:"dP",d:"فرق الضغط (atm)"},{s:"mu",d:"اللزوجة (cP)"},{s:"L",d:"طول المسار (cm)"}],note:"الاساس الرياضي لكل حركة موائع عبر الصخور المسامية."},
{en:"API Gravity",ar:"درجة API",eq:"API = (141.5 / SG) - 131.5",vars:[{s:"API",d:"درجة الثقل النوعي"},{s:"SG",d:"الكثافة النسبية عند 60F"}],note:"ماء نقي = 10 API. خفيف اكثر من 35، متوسط 22-35، ثقيل اقل من 22."},
{en:"Hydrostatic P",ar:"الضغط الهيدروستاتيكي",eq:"P (psi) = 0.052 x MW x TVD",vars:[{s:"P",d:"الضغط (psi)"},{s:"MW",d:"وزن الطين (ppg)"},{s:"TVD",d:"العمق الراسي الحقيقي (ft)"}],note:"قاعدة التوازن في الحفر: الضغط الهيدروستاتيكي يجب ان يتجاوز ضغط المكمن لمنع الـ Kick."},
{en:"OOIP",ar:"النفط الاصلي في المكمن",eq:"OOIP = (7758 x A x h x phi x (1-Sw)) / Bo",vars:[{s:"7758",d:"ثابت تحويل اكر.قدم -> برميل"},{s:"A",d:"المساحة (acres)"},{s:"h",d:"سماكة الطبقة (ft)"},{s:"phi",d:"المسامية (كسر)"},{s:"Sw",d:"تشبع الماء (كسر)"},{s:"Bo",d:"معامل حجم التكوين"}],note:"المعادلة الحجمية الاكثر استخداما لتقدير الاحتياطيات."},
{en:"Productivity Index",ar:"مؤشر الانتاجية",eq:"PI = q / (Pr - Pwf)",vars:[{s:"PI",d:"مؤشر الانتاجية (bbl/day/psi)"},{s:"q",d:"معدل الانتاج (bbl/day)"},{s:"Pr",d:"ضغط المكمن الساكن (psi)"},{s:"Pwf",d:"ضغط القاع عند التدفق (psi)"}],note:"فرق الضغط (Pr-Pwf) يسمى Draw-down."},
{en:"Recovery Factor",ar:"عامل الاسترداد",eq:"RF = NP / OOIP",vars:[{s:"RF",d:"عامل الاسترداد (كسر او %)"},{s:"NP",d:"النفط المنتج (bbl)"},{s:"OOIP",d:"النفط الاصلي (bbl)"}],note:"رفعه من 30% الى 40% في مكمن كبير يعادل اكتشاف حقل جديد."},
{en:"Real Gas Law",ar:"معادلة الغاز الحقيقي",eq:"PV = nZRT",vars:[{s:"P",d:"الضغط (psia)"},{s:"V",d:"الحجم"},{s:"n",d:"عدد المولات"},{s:"Z",d:"معامل الانضغاطية"},{s:"R",d:"ثابت الغاز = 10.73"},{s:"T",d:"درجة الحرارة المطلقة (R)"}],note:"عند Z=1 تصبح معادلة الغاز المثالي."},
{en:"Water Cut",ar:"نسبة الماء المنتج",eq:"WC% = qw / (qo + qw) x 100",vars:[{s:"WC%",d:"نسبة الماء %"},{s:"qw",d:"معدل انتاج الماء (bbl/day)"},{s:"qo",d:"معدل انتاج الزيت (bbl/day)"}],note:"عندما WC اكبر من 95% يصبح الانتاج غير اقتصادي في معظم الحالات."},
{en:"NPV",ar:"صافي القيمة الحالية",eq:"NPV = Sum[CF_t / (1+r)^t] - C0",vars:[{s:"CF_t",d:"التدفق النقدي في السنة t"},{s:"r",d:"معدل الخصم"},{s:"t",d:"السنة"},{s:"C0",d:"الاستثمار الاولي"}],note:"NPV اكبر من صفر المشروع مجدٍ. NPV يساوي صفر معدل العائد الداخلي يساوي معدل الخصم."}
];
function render(list){document.getElementById("tgrid").innerHTML=list.map((t,i)=>`<div class="card"><div class="card-head" onclick="tog(${i})"><span class="ar">${t.ar}</span><span class="en">${t.en}</span><span class="badge ${t.cl}">${t.lbl}</span></div><div class="card-body" id="b${i}"><p class="def">${t.def}</p></div></div>`).join("")}
function tog(i){document.getElementById("b"+i).classList.toggle("open")}
function filter(){const q=document.getElementById("q").value.toLowerCase();const f=q?T.filter(t=>t.en.toLowerCase().includes(q)||t.ar.includes(q)||t.def.includes(q)):T;render(f);document.getElementById("nr").style.display=f.length?"none":"block"}
function renderF(){document.getElementById("fgrid").innerHTML=F.map(f=>`<div class="fcard"><div class="fcard-head"><span class="f-ar">${f.ar}</span><span class="f-en">${f.en}</span></div><div class="fcard-body"><div class="eq">${f.eq}</div><div class="vars">${f.vars.map(v=>`<div class="vrow"><span class="vsym">${v.s} =</span><span class="vdesc">${v.d}</span></div>`).join("")}</div>${f.note?`<div class="fnote">${f.note}</div>`:""}</div></div>`).join("")}
function show(id,btn){document.querySelectorAll(".sec").forEach(s=>s.classList.remove("active"));document.querySelectorAll("nav button").forEach(b=>b.classList.remove("active"));document.getElementById(id).classList.add("active");btn.classList.add("active")}
render(T);renderF();
</script></body></html>"""


# ─────────────────────────────────────────────
#  MESSAGING HELPERS
# ─────────────────────────────────────────────
def send_message(chat_id: int, text: str) -> None:
    text = clean_text(text)
    if not text:
        text = "لم اتمكن من توليد رد واضح."
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


def send_document(chat_id: int, file_bytes: bytes, filename: str, caption: str) -> None:
    try:
        requests.post(
            f"{TELEGRAM_URL}/sendDocument",
            data={"chat_id": chat_id, "caption": caption},
            files={"document": (filename, file_bytes, "text/html")},
            timeout=20
        )
    except Exception as e:
        send_message(chat_id, f"خطا في ارسال الملف: {e}")


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
#  AI CALLS
# ─────────────────────────────────────────────
def ask_ai(user_text: str, file_context=None) -> str:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if file_context:
        messages.append({"role": "user", "content": "Reference document context:\n\n" + file_context[:20000]})
    messages.append({"role": "user", "content": user_text})
    try:
        r = requests.post(GROQ_URL,
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={"model": TEXT_MODEL, "messages": messages, "temperature": 0.08, "max_tokens": 3000},
            timeout=90)
        data = r.json()
        if "choices" in data:
            return data["choices"][0]["message"]["content"]
        return "خطا من Groq:\n" + str(data)[:600]
    except Exception as e:
        return f"خطا في الاتصال بالذكاء الاصطناعي:\n{e}"


def ask_vision_ai(prompt: str, image_path: str, file_context=None) -> str:
    full_prompt = SYSTEM_PROMPT + "\n\nTask:\n" + prompt
    if file_context:
        full_prompt += "\n\nReference context:\n" + file_context[:10000]
    messages = [{"role": "user", "content": [
        {"type": "text", "text": full_prompt},
        {"type": "image_url", "image_url": {"url": encode_image(image_path)}}
    ]}]
    try:
        r = requests.post(GROQ_URL,
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={"model": VISION_MODEL, "messages": messages, "temperature": 0.08, "max_tokens": 2200},
            timeout=90)
        data = r.json()
        if "choices" in data:
            return data["choices"][0]["message"]["content"]
        return "خطا من Groq Vision:\n" + str(data)[:600]
    except Exception as e:
        return f"خطا في تحليل الصورة:\n{e}"


# ─────────────────────────────────────────────
#  FILE / PHOTO HANDLERS
# ─────────────────────────────────────────────
def handle_document_upload(chat_id, doc):
    file_id   = doc["file_id"]
    file_name = doc.get("file_name", "file")
    mime      = doc.get("mime_type", "")
    ext       = os.path.splitext(file_name)[1].lower() or ".bin"
    path      = download_file(file_id, ext)
    if not path:
        send_message(chat_id, "حدث خطا اثناء تحميل الملف."); return
    lower = file_name.lower()
    if lower.endswith(".pdf"):
        text = extract_pdf_text(path)
        if not text:
            send_message(chat_id, "قرات PDF لكن لم استخرج نصا. الملف غالبا سكاني (صور). ارسل صفحاته كصور او ارفع PDF نصيا."); return
        FILE_CONTEXT[chat_id] = text
        send_message(chat_id, "تم قراءة PDF بنجاح. الملف اصبح مرجعا لهذه المحادثة.\nاكتب /analyze لتحليله هندسيا.")
    elif lower.endswith(".docx"):
        text = extract_docx_text(path)
        if not text:
            send_message(chat_id, "قرات DOCX لكن لم اجد نصا."); return
        FILE_CONTEXT[chat_id] = text
        send_message(chat_id, "تم قراءة DOCX بنجاح. اكتب /analyze للتحليل.")
    elif mime.startswith("image/") or lower.endswith((".png",".jpg",".jpeg",".webp")):
        IMAGE_CONTEXT[chat_id] = path
        send_message(chat_id, "تم استلام الصورة. اكتب /graph لتحليل الرسم هندسيا.")
    else:
        send_message(chat_id, "الملف المدعوم: PDF او DOCX او صورة (PNG/JPG/JPEG/WEBP).")


def handle_photo_upload(chat_id, photos):
    path = download_file(photos[-1]["file_id"], ".jpg")
    if path:
        IMAGE_CONTEXT[chat_id] = path
        send_message(chat_id, "تم استلام الصورة. اكتب /graph لتحليل الرسم هندسيا.")
    else:
        send_message(chat_id, "خطا في تحميل الصورة.")


# ─────────────────────────────────────────────
#  COMMAND DETECTORS
# ─────────────────────────────────────────────
def is_graph_cmd(t):   return t.lower().startswith(("/graph", "/interpret_graph"))
def is_export_cmd(t):  return t.lower().startswith(("/export_sim","/pvto","/pvtg","/eclipse","/cmg"))
def is_plot_cmd(t):    return t.lower().startswith("/plot")
def is_analyze_cmd(t): return t.lower().startswith("/analyze")
def is_calc_cmd(t):    return t.lower().startswith("/calc")
def is_check_cmd(t):   return t.lower().startswith("/check")

def is_surface_separator(t):
    t = t.lower()
    oil = any(k in t for k in ["surface separator oil","separator oil","زيت من الفاصل","عينة زيت"])
    gas = any(k in t for k in ["separator gas","غاز من الفاصل","عينة غاز"])
    return oil and gas


# ─────────────────────────────────────────────
#  STATIC RESPONSES
# ─────────────────────────────────────────────
def start_message() -> str:
    return (
        "اهلا بك في PVT Lab AI Bot\n\n"
        "انا مساعد هندسي متخصص في:\n"
        "- PVT Laboratory and Reservoir Fluid Analysis\n"
        "- Reservoir Simulation (Eclipse / CMG)\n"
        "- Drilling Engineering\n"
        "- PDF/DOCX Report Analysis\n"
        "- Graph and Figure Interpretation\n\n"
        "الاوامر المتاحة:\n\n"
        "/glossary    — المصطلحات النفطية (HTML تفاعلي: مصطلحات + معادلات + خريطة مفاهيم)\n"
        "/calc        — حسابات هندسية سريعة\n"
        "  /calc API for SG 0.85\n"
        "  /calc hydrostatic mw 10 tvd 5000\n"
        "  /calc ooip 500 50 0.2 0.3 1.3\n"
        "  /calc water cut qw 800 qo 200\n"
        "  /calc recovery np 5000000 ooip 20000000\n"
        "/analyze     — تحليل تقرير PDF/DOCX مرفوع\n"
        "/graph       — تحليل رسم بياني او صورة هندسية\n"
        "/plot        — توجيه رسومات PVT\n"
        "/check       — فحص بيانات PVT\n"
        "/export_sim  — تصدير بيانات للمحاكاة\n"
        "/pvto        — جدول PVTO لـ Eclipse\n"
        "/pvtg        — جدول PVTG لـ Eclipse\n"
        "/eclipse     — ارشادات Eclipse\n"
        "/cmg         — ارشادات CMG\n\n"
        "يمكنك كتابة سؤالك مباشرة بالعربي او الانجليزي."
    )


def surface_separator_answer() -> str:
    return (
        "تحليل هندسي — عينة زيت من الفاصل السطحي مع عينة غاز\n\n"
        "نوع العينات\n"
        "هذه عينات سطحية منفصلة وليست سائل مكمن مباشرا مثل Bottom Hole Sample.\n"
        "الزيت والغاز انفصلا عند ظروف الفاصل السطحي لذلك يلزم Recombination اولا.\n\n"
        "البيانات المطلوبة\n"
        "- Separator Pressure و Temperature\n"
        "- Oil Rate و Gas Rate\n"
        "- Producing GOR او Separator GOR\n"
        "- Gas Composition و Oil/Stock Tank Oil Composition\n"
        "- API Gravity و Gas Specific Gravity\n"
        "- Water Cut و وجود H2S/CO2\n\n"
        "الاختبارات المطلوبة\n"
        "1. Sample QC — فحص سلامة العينات\n"
        "2. Compositional Analysis — تحليل تركيبي كامل\n"
        "3. Recombination — اعادة بناء سائل المكمن\n"
        "4. Validation — التحقق من تمثيلية العينة المعاد تركيبها\n"
        "5. CCE/CME — لتحديد Saturation Pressure وسلوك الحجم\n"
        "6. DV للزيت او CVD للغاز المكثف\n"
        "7. Separator Test و Viscosity Test\n\n"
        "الرسومات المطلوبة\n"
        "- Pressure vs Bo\n"
        "- Pressure vs Rs\n"
        "- Pressure vs Oil Viscosity\n"
        "- Pressure vs Relative Volume (Y-Function)\n"
        "- للغاز المكثف: Pressure vs Liquid Dropout\n\n"
        "اعداد المحاكاة\n"
        "Black Oil: PVTO في Eclipse (يحتاج Bo، Rs، Viscosity عند كل ضغط)\n"
        "Gas Condensate / Volatile Oil: Compositional Model مع EOS Tuning\n\n"
        "الخلاصة\n"
        "لا يمكن حساب Bo او Rs او Bubble Point بدون بيانات الفاصل والتركيب.\n"
        "ارسل البيانات وسابدا الحسابات فورا."
    )


# ─────────────────────────────────────────────
#  MAIN LOOP
# ─────────────────────────────────────────────
print("PVT Lab AI Bot running...")

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
                send_message(chat_id, "ارسل نصا او ملف PDF/DOCX او صورة."); continue

            text    = msg["text"].strip()
            context = FILE_CONTEXT.get(chat_id)

            if text == "/start":
                send_message(chat_id, start_message()); continue

            if text == "/glossary":
                send_document(chat_id, GLOSSARY_HTML.encode("utf-8"), "petroleum_glossary.html",
                    "المصطلحات النفطية الشاملة\n\n"
                    "يحتوي الملف على:\n"
                    "- 32 مصطلحا بتعريفات علمية كاملة\n"
                    "- 10 معادلات هندسية مع شرح الرموز\n"
                    "- خريطة مفاهيم تفاعلية\n\n"
                    "افتح الملف في اي متصفح."); continue

            if is_calc_cmd(text):
                query  = text[5:].strip()
                result = handle_calculation(query)
                if result:
                    send_message(chat_id, result)
                else:
                    send_message(chat_id,
                        "لم اتعرف على الحساب. امثلة:\n\n"
                        "/calc API for SG 0.85\n"
                        "/calc hydrostatic mw 10 tvd 5000\n"
                        "/calc ooip 500 50 0.2 0.3 1.3\n"
                        "/calc darcy 50 100 200 2 500\n"
                        "/calc recovery 5000000 20000000\n"
                        "/calc water cut 800 200"); continue

            if is_analyze_cmd(text):
                if not context:
                    send_message(chat_id, "لا يوجد ملف مرفوع. ارسل PDF او DOCX اولا."); continue
                prompt = ("قم بتحليل هذا التقرير الهندسي:\n"
                          "1. نوع العينة ونظام السائل\n"
                          "2. الاختبارات المنفذة وجودتها\n"
                          "3. القيم الرئيسية (Pb، Bo، Rs، API، Viscosity)\n"
                          "4. انتقادات او مشاكل في البيانات\n"
                          "5. توصيات للمحاكاة\n"
                          "6. الخلاصة الهندسية")
                send_message(chat_id, ask_ai(prompt, context)); continue

            if is_graph_cmd(text):
                img = IMAGE_CONTEXT.get(chat_id)
                if not img:
                    send_message(chat_id, "ارسل صورة الرسم اولا ثم اكتب /graph."); continue
                prompt = (text + "\n\nحلل هذا الرسم الهندسي النفطي:\n"
                          "- حدد المحاور والوحدات\n"
                          "- فسر الاتجاه العام\n"
                          "- اكشف اي سلوك غير طبيعي\n"
                          "- اذكر اي ظاهرة Retrograde ان وجدت\n"
                          "- اعط التفسير الهندسي والتوصيات")
                send_message(chat_id, ask_vision_ai(prompt, img, context)); continue

            if is_plot_cmd(text):
                prompt = (text + "\n\nحدد الرسم المناسب لهذه البيانات وفسر الاتجاه المتوقع. "
                          "اذا كانت البيانات غير كافية اذكر بالضبط ما يلزم.")
                send_message(chat_id, ask_ai(prompt, context)); continue

            if is_check_cmd(text):
                prompt = (text + "\n\nافحص البيانات المقدمة هندسيا:\n"
                          "- تحقق من المنطقية والاتساق\n"
                          "- حدد اي قيم غير طبيعية او مشبوهة\n"
                          "- اذكر البيانات الناقصة\n"
                          "- اعط توصيات التصحيح")
                send_message(chat_id, ask_ai(prompt, context)); continue

            if is_export_cmd(text):
                prompt = (text + "\n\nقدم توجيهات تصدير المحاكاة:\n"
                          "- حدد نوع النموذج (Black Oil / Compositional)\n"
                          "- الكلمات المفتاحية المطلوبة في Eclipse/CMG\n"
                          "- تحقق من الوحدات والاتساق\n"
                          "- اذكر البيانات الناقصة")
                send_message(chat_id, ask_ai(prompt, context)); continue

            if is_surface_separator(text):
                send_message(chat_id, surface_separator_answer()); continue

            # Default AI response
            send_message(chat_id, ask_ai(text, context))

    except Exception as e:
        print(f"Main loop error: {e}")

    time.sleep(1)
