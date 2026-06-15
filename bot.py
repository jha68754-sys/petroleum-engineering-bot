"""
Petroleum Engineering AI Bot
General Petroleum Engineering Telegram Bot
Provider: Groq API
Mode: Telegram polling
No matplotlib
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

if not TELEGRAM_BOT_TOKEN:
    raise ValueError("Missing TELEGRAM_BOT_TOKEN")
if not GROQ_API_KEY:
    raise ValueError("Missing OPENAI_API_KEY")

TELEGRAM_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

TEXT_MODEL = os.getenv("GROQ_TEXT_MODEL", "llama-3.3-70b-versatile")
VISION_MODEL = os.getenv("GROQ_VISION_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")

offset = 0
FILE_CONTEXT = {}
IMAGE_CONTEXT = {}
MAX_CONTEXT_CHARS = 22000


SYSTEM_PROMPT = """
You are Petroleum Engineering AI Bot.

Act as a professional and academic petroleum engineer, not as a translator or generic chatbot.

Scope:
- PVT Laboratory
- Reservoir Engineering
- Drilling Engineering
- Production Engineering
- Reservoir Simulation
- Petroleum Economics
- Well Testing
- Fluid Properties

Highest priority rules:
1. Do not invent numerical values.
2. Do not calculate without real input data.
3. If data are missing, write DATA REQUIRED.
4. Distinguish clearly between:
   - Lab measured value
   - Correlation estimate
   - User-provided assumption
   - Engineering judgment
5. For PVT relationships, deterministic engineering rules override AI interpretation.

Language:
- Arabic question -> answer in professional Arabic using correct petroleum terminology.
- English question -> answer in professional petroleum engineering English.
- Mixed question -> answer naturally in the same style.
- Keep technical abbreviations in English: Bo, Bg, Rs, Rv, GOR, CGR, API, PVT, CCE, CME, DV, CVD, EOS, PVTO, PVTG.

Approved technical terms:
PVT = Pressure-Volume-Temperature
Reservoir = المكمن
Well = البئر
Formation = التكوين
Bottom Hole Sample = عينة قاع البئر
Surface Separator Oil Sample = عينة زيت من الفاصل السطحي
Separator Gas Sample = عينة غاز من الفاصل
Recombined Sample = عينة معاد تركيبها
Recombination = إعادة تركيب العينة
Bubble Point Pressure = ضغط نقطة الفقاعة
Dew Point Pressure = ضغط نقطة الندى
Bo = Oil Formation Volume Factor = معامل حجم التكوين للزيت
Bg = Gas Formation Volume Factor = معامل حجم التكوين للغاز
Rs = Solution Gas-Oil Ratio = نسبة الغاز المذاب
Rv = Vaporized Oil-Gas Ratio = نسبة الزيت المتبخر في الغاز
GOR = Gas-Oil Ratio = نسبة الغاز إلى الزيت
CGR = Condensate-Gas Ratio = نسبة المكثفات إلى الغاز
Z-factor = Gas Compressibility Factor = معامل الانضغاطية للغاز = dimensionless
Viscosity = اللزوجة
Density = الكثافة
Specific Gravity = الكثافة النوعية
API Gravity = درجة API
CCE = Constant Composition Expansion
CME = Constant Mass Expansion
DV = Differential Vaporization / Differential Liberation
CVD = Constant Volume Depletion
Separator Test = اختبار الفاصل
Flash Test = اختبار الوميض
Compositional Analysis = التحليل التركيبي
EOS Tuning = مواءمة معادلة الحالة
PVTO = Eclipse live oil PVT table
PVDO = Eclipse dead oil PVT table
PVTG = Eclipse live/wet gas PVT table
PVDG = Eclipse dry gas PVT table

Forbidden terms:
Never use:
- الضغط البيني
- المعامل البيني
- الترشيح as Rs
- الليزج
- الويسكوزية
- الحفرة as reservoir
- السطوع النوعي
- Pressuring Volume and Temperature

PVT ground-truth rules:

Bo:
Bo = Reservoir Oil Volume / Stock Tank Oil Volume.
Above Pb: oil is undersaturated, Rs is constant, Bo decreases slightly as pressure increases.
As pressure decreases toward Pb, Bo increases gently.
At Pb: Bo reaches maximum value Bob.
Below Pb: gas evolves from solution, Rs decreases, Bo decreases as pressure decreases.
Do not confuse Bo with Bt.
Higher Bo decreases calculated OOIP because OOIP is divided by Bo.

Rs:
Above Pb: Rs is constant at Rsi.
At Pb: Rs = Rsi.
Below Pb: Rs decreases as pressure decreases.

Bg:
Bg generally decreases as pressure increases.
Bg generally increases as pressure decreases.
Bg does not have a Bo-like peak.

Z-factor:
Z-factor is Gas Compressibility Factor.
It is dimensionless.
It corrects real gas behavior in PV = ZnRT.
Do not confuse Z-factor with gas compressibility Cg.

Oil viscosity:
Oil viscosity is often minimum near Pb.
Below Pb, oil viscosity increases as pressure decreases because gas leaves oil.

Liquid Dropout:
Above Pd: 0.
At Pd: first liquid appears.
Below Pd: dropout rises, reaches peak, then may decrease due to revaporization.

Phase envelope:
Bubble-point and dew-point lines meet at critical point.
Cricondentherm = maximum temperature of two-phase envelope.
Cricondenbar = maximum pressure of two-phase envelope.

PVT workflow:
Surface Separator Oil + Separator Gas are not direct reservoir fluid.
Correct workflow:
1. Sample QC
2. Separator P/T and rates
3. Oil and gas compositions
4. Recombination
5. Validation
6. CCE/CME
7. DV for oil systems
8. CVD for gas condensate
9. Separator Test
10. Viscosity Test
11. EOS Tuning if compositional simulation is required

Simulation:
PVTO: live oil with Rs, Bo, oil viscosity.
PVDO: dead oil or negligible Rs.
PVTG: live/wet gas or gas condensate with Rv.
PVDG: dry gas.
Compositional/EOS: near-critical volatile oil, rich gas condensate, miscibility, CO2/H2S, strong compositional effects.

Formatting:
No markdown symbols like ** or ###.
No vertical-line tables.
Use clean headings and concise professional explanation.
"""


TERMS = {
    "bo": {
        "en": "Oil Formation Volume Factor (Bo)",
        "unit": "rb/STB or m3/m3",
        "definition": "Reservoir Oil Volume / Stock Tank Oil Volume",
        "note": "Bo reaches maximum at Bubble Point Pressure Pb, then decreases below Pb."
    },

    "bg": {
        "en": "Gas Formation Volume Factor (Bg)",
        "unit": "rb/scf or reservoir m3/standard m3",
        "definition": "Gas volume at reservoir conditions divided by gas volume at standard conditions.",
        "note": "Bg decreases as pressure increases."
    },

    "rs": {
        "en": "Solution Gas-Oil Ratio (Rs)",
        "unit": "scf/STB or m3/m3",
        "definition": "Gas dissolved in oil per stock tank barrel of oil.",
        "note": "Rs is constant above Pb and decreases below Pb."
    },

    "rv": {
        "en": "Vaporized Oil-Gas Ratio (Rv)",
        "unit": "STB/MMscf",
        "definition": "Amount of oil vaporized in gas.",
        "note": "Important in gas-condensate and wet-gas systems."
    },

    "gor": {
        "en": "Gas-Oil Ratio (GOR)",
        "unit": "scf/STB",
        "definition": "Produced gas volume divided by produced oil volume.",
        "note": "GOR is a production ratio. It is not the same as Rs."
    },

    "cgr": {
        "en": "Condensate-Gas Ratio (CGR)",
        "unit": "STB/MMscf",
        "definition": "Condensate liquid volume divided by produced gas volume.",
        "note": "Important for gas condensate systems."
    },

    "z": {
        "en": "Gas Compressibility Factor (Z-Factor)",
        "unit": "dimensionless",
        "definition": "Correction factor accounting for deviation from ideal gas behavior.",
        "note": "Z-factor is not gas compressibility Cg."
    },

    "pb": {
        "en": "Bubble Point Pressure",
        "unit": "psia or bar",
        "definition": "Pressure at which the first gas bubble evolves from oil at constant temperature.",
        "note": "Usually determined from CCE/CME behavior."
    },

    "pd": {
        "en": "Dew Point Pressure",
        "unit": "psia or bar",
        "definition": "Pressure at which the first liquid drop condenses from gas at constant temperature.",
        "note": "Critical for gas condensate systems."
    },

    "pvt": {
        "en": "Pressure-Volume-Temperature",
        "unit": "N/A",
        "definition": "Laboratory study of reservoir fluid behavior under pressure and temperature.",
        "note": "Never define PVT as Pressuring Volume and Temperature."
    }
}PVT_PLOTS = {
    "bo": {
        "title": "Bo vs Pressure",
        "trend": "Bo increases toward Pb, reaches maximum at Pb, then decreases below Pb.",
        "ascii": """
Bo
^
|                    * Bob maximum at Pb
|                 .-' \\
|              .-'     \\
|           .-'          \\____
|_______.-'
+------------------------------------> Pressure
 low P              Pb             high P
"""
    },

    "rs": {
        "title": "Rs vs Pressure",
        "trend": "Rs is constant above Pb and decreases below Pb.",
        "ascii": """
Rs
^
|                 __________________ Rsi
|               /
|             /
|           /
|_________/
+------------------------------------> Pressure
 low P              Pb             high P
"""
    },

    "bg": {
        "title": "Bg vs Pressure",
        "trend": "Bg decreases as pressure increases.",
        "ascii": """
Bg
^
|\\
| \\
|  \\___
|      \\____
|           \\________
+------------------------------------> Pressure
 low P                           high P
"""
    },

    "z": {
        "title": "Z-Factor vs Pressure",
        "trend": "Z-factor often shows checkmark or U-shaped behavior at fixed temperature.",
        "ascii": """
Z-factor
^
| \\____                       ____
|      \\___              ____/
|          \\____________/
+------------------------------------> Pressure
 low P                           high P
"""
    },

    "viscosity": {
        "title": "Oil Viscosity vs Pressure",
        "trend": "Oil viscosity is often minimum near Pb and increases below Pb as pressure decreases.",
        "ascii": """
Oil Viscosity
^
|\\                              /
| \\                           /
|  \\____                 ____/
|       \\____ min _____/
+------------------------------------> Pressure
 low P              Pb             high P
"""
    },

    "dropout": {
        "title": "Liquid Dropout vs Pressure",
        "trend": "Liquid dropout is 0 above Pd, rises below Pd, reaches a peak, then may decrease.",
        "ascii": """
Liquid Dropout
^
|           _______
|        .-'       '-.
|      .'             '-.__
|____.'
+------------------------------------> Pressure
 low P              Pd             high P
"""
    },

    "cgr": {
        "title": "CGR vs Pressure",
        "trend": "CGR is roughly constant above Pd and decreases below Pd.",
        "ascii": """
CGR
^
|               ____________
|              /
|            /
|__________/
+------------------------------------> Pressure
 low P              Pd             high P
"""
    },

    "phase": {
        "title": "P-T Phase Envelope",
        "trend": "Bubble-point and dew-point lines meet at the critical point.",
        "ascii": """
Pressure
^
|        Cricondenbar
|            *
|         .-' '-.
|      .-'       '-.
|    .'  two-phase   '.
|   * Critical Point   '.
|    '.                 '-. * Cricondentherm
+------------------------------------> Temperature
"""
    }
}


FLUID_CLASS = [
    ("Black Oil", "Conventional black oil", 0, 2000, 0, 40),
    ("Volatile Oil", "Volatile oil", 2000, 8000, 40, 50),
    ("Gas Condensate", "Gas condensate", 8000, 100000, 50, 70),
    ("Wet Gas", "Wet gas", 100000, 10**9, 60, 120)
]


def clean_text(text: str) -> str:
    fixes = {
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
        "الويسكوزية": "اللزوجة",
        "الویسكوزية": "اللزوجة",
        "الليزج": "اللزوجة",
        "الحفرة": "المكمن",
        "السطوع النوعي": "الكثافة النوعية",
        "اختبار السطوع": "اختبار الكثافة النوعية",
        "معامل حجم تكوين الزيت": "معامل حجم التكوين للزيت",
        "معامل حجم تكوين الغاز": "معامل حجم التكوين للغاز",
    }

    text = str(text)

    for wrong, right in fixes.items():
        text = text.replace(wrong, right)

    return text.strip()


def send_message(chat_id, text):
    text = clean_text(text)

    if not text:
        text = "لم أتمكن من توليد رد واضح."

    for i in range(0, len(text), 3900):
        try:
            requests.post(
                f"{TELEGRAM_URL}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": text[i:i+3900]
                },
                timeout=15
            )
        except Exception as e:
            print("send_message error:", e)

        time.sleep(0.3)


def send_document(chat_id, file_bytes, filename, caption, mime="text/plain"):
    try:
        requests.post(
            f"{TELEGRAM_URL}/sendDocument",
            data={
                "chat_id": chat_id,
                "caption": caption
            },
            files={
                "document": (filename, file_bytes, mime)
            },
            timeout=30
        )
    except Exception as e:
        send_message(chat_id, f"خطأ في إرسال الملف: {e}")


def download_file(file_id, suffix=".bin"):
    try:
        info = requests.get(
            f"{TELEGRAM_URL}/getFile",
            params={"file_id": file_id},
            timeout=15
        ).json()

        if not info.get("ok"):
            return None

        file_path = info["result"]["file_path"]
        url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"

        data = requests.get(url, timeout=60).content

        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        tmp.write(data)
        tmp.close()

        return tmp.name

    except Exception as e:
        print("download_file error:", e)
        return None


def extract_pdf_text(path):
    try:
        reader = PdfReader(path)
        pages = []

        for page in reader.pages:
            text = page.extract_text()
            if text:
                pages.append(text)

        return "\n\n".join(pages).strip()

    except Exception as e:
        print("PDF error:", e)
        return ""


def extract_docx_text(path):
    try:
        doc = Document(path)

        return "\n".join(
            p.text.strip()
            for p in doc.paragraphs
            if p.text.strip()
        )

    except Exception as e:
        print("DOCX error:", e)
        return ""def encode_image(path):
    mime, _ = mimetypes.guess_type(path)

    if not mime:
        mime = "image/jpeg"

    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")

    return f"data:{mime};base64,{b64}"


def ask_ai(user_text, file_context=None):

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT
        }
    ]

    if file_context:
        messages.append({
            "role": "user",
            "content": (
                "Reference document context:\n\n"
                + file_context[:20000]
            )
        })

    messages.append({
        "role": "user",
        "content": user_text
    })

    try:

        response = requests.post(
            GROQ_URL,
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": TEXT_MODEL,
                "messages": messages,
                "temperature": 0.1,
                "max_tokens": 3000
            },
            timeout=90
        )

        response.raise_for_status()

        data = response.json()

        return data["choices"][0]["message"]["content"]

    except Exception as e:
        return f"AI Error: {e}"


def ask_vision_ai(prompt, image_path):

    try:

        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": prompt
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": encode_image(image_path)
                        }
                    }
                ]
            }
        ]

        response = requests.post(
            GROQ_URL,
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": VISION_MODEL,
                "messages": messages,
                "temperature": 0.1,
                "max_tokens": 2500
            },
            timeout=120
        )

        response.raise_for_status()

        data = response.json()

        return data["choices"][0]["message"]["content"]

    except Exception as e:
        return f"Vision Error: {e}"


def classify_fluid(gor, api):

    for name, desc, gmin, gmax, amin, amax in FLUID_CLASS:

        if gmin <= gor < gmax and amin <= api <= amax:

            return (
                f"Fluid Type: {name}\n\n"
                f"Description: {desc}\n\n"
                f"GOR = {gor:,.0f} scf/STB\n"
                f"API = {api}"
            )

    return (
        "Unable to classify fluid accurately.\n\n"
        "DATA REQUIRED:\n"
        "- Reservoir temperature\n"
        "- Composition\n"
        "- Additional PVT data"
    )


def plot_relationship(name):

    key = name.lower().strip()

    if key not in PVT_PLOTS:
        return (
            "Available plots:\n\n"
            "bo\n"
            "rs\n"
            "bg\n"
            "z\n"
            "viscosity\n"
            "dropout\n"
            "cgr\n"
            "phase"
        )

    plot = PVT_PLOTS[key]

    return (
        f"{plot['title']}\n\n"
        f"{plot['trend']}\n\n"
        f"{plot['ascii']}"
    )


def generate_pvto_skeleton():

    return """
PVTO TABLE (LIVE OIL)

DATA REQUIRED:

Rs
Pb
Bo
Oil Viscosity

Example Structure

Rs     P      Bo      Mu_o
--------------------------------
DATA REQUIRED
DATA REQUIRED
DATA REQUIRED

Notes:
- Use Differential Liberation data.
- Use CCE above Pb.
- Never fabricate values.
"""


def generate_pvtg_skeleton():

    return """
PVTG TABLE (LIVE GAS)

DATA REQUIRED:

Pressure
Bg
Gas Viscosity
Rv

Example Structure

P      Bg      Mu_g      Rv
--------------------------------
DATA REQUIRED
DATA REQUIRED
DATA REQUIRED

Notes:
- Use CVD data.
- Use compositional analysis.
- Never fabricate values.
"""


def export_simulation(fluid_type):

    fluid_type = fluid_type.lower()

    if "black" in fluid_type:
        return (
            "Recommended Model:\n"
            "Black Oil\n\n"
            "Table:\n"
            "PVTO or PVDO"
        )

    if "volatile" in fluid_type:
        return (
            "Recommended Model:\n"
            "Black Oil or Compositional\n\n"
            "Verify near-critical behavior."
        )

    if "condensate" in fluid_type:
        return (
            "Recommended Model:\n"
            "Compositional EOS\n\n"
            "Use PVTG and EOS tuning."
        )

    if "wet gas" in fluid_type:
        return (
            "Recommended Model:\n"
            "PVTG"
        )

    if "dry gas" in fluid_type:
        return (
            "Recommended Model:\n"
            "PVDG"
        )

    return (
        "Unknown fluid type.\n\n"
        "Options:\n"
        "Black Oil\n"
        "Volatile Oil\n"
        "Gas Condensate\n"
        "Wet Gas\n"
        "Dry Gas"
    )def calculate_command(text):

    args = text.lower().split()

    if len(args) < 2:
        return """
Available calculations:

/calc api sg=0.85
/calc hydrostatic mw=10 tvd=5000
/calc ooip area=500 h=50 phi=0.2 sw=0.3 bo=1.3
/calc pi q=1000 pr=3000 pwf=2500
/calc watercut qw=800 qo=200
"""

    query = text.lower()

    numbers = {
        k: float(v)
        for k, v in re.findall(r"(\w+)=([-+]?\d*\.?\d+)", query)
    }

    if "api" in query:
        if "sg" not in numbers:
            return "DATA REQUIRED: sg\nExample: /calc api sg=0.85"

        sg = numbers["sg"]
        api = (141.5 / sg) - 131.5

        return (
            "API Gravity Calculation\n\n"
            "Formula:\n"
            "API = (141.5 / SG) - 131.5\n\n"
            f"SG = {sg}\n"
            f"API = {api:.2f}"
        )

    if "hydrostatic" in query:
        if "mw" not in numbers or "tvd" not in numbers:
            return "DATA REQUIRED: mw, tvd\nExample: /calc hydrostatic mw=10 tvd=5000"

        mw = numbers["mw"]
        tvd = numbers["tvd"]
        pressure = 0.052 * mw * tvd

        return (
            "Hydrostatic Pressure Calculation\n\n"
            "Formula:\n"
            "P = 0.052 × MW × TVD\n\n"
            f"MW = {mw} ppg\n"
            f"TVD = {tvd} ft\n"
            f"P = {pressure:.2f} psi"
        )

    if "ooip" in query:
        required = ["area", "h", "phi", "sw", "bo"]

        missing = [x for x in required if x not in numbers]

        if missing:
            return (
                "DATA REQUIRED:\n"
                "area, h, phi, sw, bo\n\n"
                "Example:\n"
                "/calc ooip area=500 h=50 phi=0.2 sw=0.3 bo=1.3"
            )

        area = numbers["area"]
        h = numbers["h"]
        phi = numbers["phi"]
        sw = numbers["sw"]
        bo = numbers["bo"]

        ooip = (7758 * area * h * phi * (1 - sw)) / bo

        return (
            "OOIP Calculation\n\n"
            "Formula:\n"
            "OOIP = 7758 × A × h × φ × (1 - Sw) / Bo\n\n"
            f"Area = {area} acres\n"
            f"h = {h} ft\n"
            f"φ = {phi}\n"
            f"Sw = {sw}\n"
            f"Bo = {bo}\n\n"
            f"OOIP = {ooip:,.0f} STB\n\n"
            "Engineering note:\n"
            "Higher Bo gives lower calculated OOIP because Bo is in the denominator."
        )

    if "pi" in query:
        required = ["q", "pr", "pwf"]

        missing = [x for x in required if x not in numbers]

        if missing:
            return (
                "DATA REQUIRED:\n"
                "q, pr, pwf\n\n"
                "Example:\n"
                "/calc pi q=1000 pr=3000 pwf=2500"
            )

        q = numbers["q"]
        pr = numbers["pr"]
        pwf = numbers["pwf"]

        if pr <= pwf:
            return "Invalid data: Pr must be greater than Pwf."

        pi = q / (pr - pwf)

        return (
            "Productivity Index Calculation\n\n"
            "Formula:\n"
            "PI = q / (Pr - Pwf)\n\n"
            f"q = {q} STB/day\n"
            f"Pr = {pr} psi\n"
            f"Pwf = {pwf} psi\n\n"
            f"PI = {pi:.4f} STB/day/psi"
        )

    if "watercut" in query or "water_cut" in query:
        required = ["qw", "qo"]

        missing = [x for x in required if x not in numbers]

        if missing:
            return (
                "DATA REQUIRED:\n"
                "qw, qo\n\n"
                "Example:\n"
                "/calc watercut qw=800 qo=200"
            )

        qw = numbers["qw"]
        qo = numbers["qo"]

        if qw + qo == 0:
            return "Invalid data: qw + qo cannot be zero."

        wc = (qw / (qw + qo)) * 100

        return (
            "Water Cut Calculation\n\n"
            "Formula:\n"
            "WC = qw / (qw + qo) × 100\n\n"
            f"qw = {qw}\n"
            f"qo = {qo}\n\n"
            f"Water Cut = {wc:.2f}%"
        )

    return "Unknown calculation type."


def estimate_command(text):

    query = text.lower()

    numbers = {
        k: float(v)
        for k, v in re.findall(r"(\w+)=([-+]?\d*\.?\d+)", query)
    }

    if "pb_standing" in query:

        required = ["rs", "gas_sg", "tres", "api"]

        missing = [x for x in required if x not in numbers]

        if missing:
            return (
                "DATA REQUIRED:\n"
                "rs, gas_sg, tres, api\n\n"
                "Example:\n"
                "/estimate pb_standing rs=650 gas_sg=0.75 tres=180 api=35"
            )

        rs = numbers["rs"]
        gas_sg = numbers["gas_sg"]
        tres = numbers["tres"]
        api = numbers["api"]

        pb = 18.2 * (
            ((rs / gas_sg) ** 0.83)
            * (10 ** (0.00091 * tres - 0.0125 * api))
            - 1.4
        )

        return (
            "CORRELATION ESTIMATE\n"
            "Standing Bubble Point Pressure Correlation\n\n"
            "Formula:\n"
            "Pb = 18.2 × [(Rs/γg)^0.83 × 10^(0.00091T - 0.0125API) - 1.4]\n\n"
            f"Rs = {rs} scf/STB\n"
            f"Gas SG = {gas_sg}\n"
            f"T = {tres} °F\n"
            f"API = {api}\n\n"
            f"Estimated Pb = {pb:.2f} psia\n\n"
            "Note:\n"
            "This is a correlation estimate, not a lab-measured value. "
            "Verify with CCE/CME data."
        )

    return (
        "Available estimates:\n\n"
        "/estimate pb_standing rs=650 gas_sg=0.75 tres=180 api=35"
    )


def check_command(text):

    q = text.lower()

    if "bo" in q:
        return (
            "Bo Check Rule\n\n"
            "Correct behavior:\n"
            "- Above Pb: Bo increases as pressure decreases toward Pb.\n"
            "- At Pb: Bo reaches maximum Bob.\n"
            "- Below Pb: Bo decreases as pressure decreases.\n\n"
            "If Bo increases continuously below Pb, this is physically wrong "
            "or the curve may represent Bt, not Bo."
        )

    if "rs" in q:
        return (
            "Rs Check Rule\n\n"
            "Correct behavior:\n"
            "- Above Pb: Rs is constant at Rsi.\n"
            "- Below Pb: Rs decreases as pressure decreases."
        )

    if "z" in q:
        return (
            "Z-Factor Check Rule\n\n"
            "Correct definition:\n"
            "Z-factor = Gas Compressibility Factor.\n"
            "Unit: dimensionless.\n\n"
            "It corrects real gas behavior in PV = ZnRT.\n"
            "It is not Gas Compressibility Cg."
        )

    if "dropout" in q or "liquid" in q:
        return (
            "Liquid Dropout Check Rule\n\n"
            "Correct behavior for gas condensate:\n"
            "- Above Pd: 0 liquid dropout.\n"
            "- At Pd: first liquid appears.\n"
            "- Below Pd: liquid dropout rises, reaches a peak, then may decrease."
        )

    return (
        "Available checks:\n\n"
        "/check bo\n"
        "/check rs\n"
        "/check z\n"
        "/check dropout"
    )def start_message():
    return """
Petroleum Engineering AI Bot

مجالات البوت:
- PVT Laboratory
- Reservoir Engineering
- Drilling Engineering
- Production Engineering
- Reservoir Simulation
- Petroleum Economics
- Well Testing
- Fluid Properties

الأوامر:
/glossary
/plot bo
/plot rs
/plot bg
/plot z
/plot viscosity
/plot dropout
/check bo
/check rs
/check z
/check dropout
/calc api sg=0.85
/calc hydrostatic mw=10 tvd=5000
/calc ooip area=500 h=50 phi=0.2 sw=0.3 bo=1.3
/calc pi q=1000 pr=3000 pwf=2500
/calc watercut qw=800 qo=200
/estimate pb_standing rs=650 gas_sg=0.75 tres=180 api=35
/classify gor=4500 api=45
/pvto
/pvtg
/export_sim gas condensate
/analyze بعد رفع PDF/DOCX
/graph بعد رفع صورة
/reset
"""


def glossary_command():
    lines = ["Petroleum Engineering Glossary\n"]

    for key, value in TERMS.items():
        lines.append(key.upper())
        lines.append(f"Name: {value['en']}")
        lines.append(f"Unit: {value['unit']}")
        lines.append(f"Definition: {value['definition']}")
        lines.append(f"Note: {value['note']}")
        lines.append("")

    return "\n".join(lines)


def classify_command(text):

    numbers = {
        k: float(v)
        for k, v in re.findall(r"(\w+)=([-+]?\d*\.?\d+)", text.lower())
    }

    if "gor" not in numbers or "api" not in numbers:
        return (
            "DATA REQUIRED:\n"
            "gor, api\n\n"
            "Example:\n"
            "/classify gor=4500 api=45"
        )

    gor = numbers["gor"]
    api = numbers["api"]

    return classify_fluid(gor, api)


def analyze_command(chat_id):

    context = FILE_CONTEXT.get(chat_id)

    if not context:
        return (
            "DATA REQUIRED:\n"
            "Upload PDF or DOCX first, then use /analyze."
        )

    prompt = """
Analyze this petroleum engineering document professionally.

Required output:
1. Document type
2. Sample type
3. Fluid type if possible
4. Tests mentioned
5. Key PVT values mentioned
6. Missing data
7. Data quality issues
8. Simulation recommendation
9. Engineering conclusion

Remember:
- Do not invent values.
- Distinguish lab measured values from assumptions.
- If data are missing, say DATA REQUIRED.
"""

    return ask_ai(prompt, context)


def graph_command(chat_id, text):

    image_path = IMAGE_CONTEXT.get(chat_id)

    if not image_path:
        return (
            "DATA REQUIRED:\n"
            "Send a graph/image first, then use /graph."
        )

    reference = "\n".join(
        f"- {item['title']}: {item['trend']}"
        for item in PVT_PLOTS.values()
    )

    prompt = f"""
Analyze this petroleum engineering graph/image professionally.

Reference PVT trends:
{reference}

Required output:
1. Identify axes and units.
2. Identify the relationship type.
3. Compare the observed curve with correct engineering behavior.
4. Flag non-physical behavior.
5. Mention possible causes.
6. Give engineering recommendation.

User question:
{text}
"""

    return ask_vision_ai(prompt, image_path)


def surface_separator_command():
    return """
Surface Separator Oil Sample + Separator Gas Sample

Sample type:
These are surface-separated samples, not direct reservoir fluid.

Correct workflow:
1. Sample QC
2. Separator pressure and temperature
3. Oil rate and gas rate
4. Producing GOR or Separator GOR
5. Oil and gas composition
6. Recombination
7. Validation of recombined sample
8. CCE/CME
9. DV for oil systems or CVD for gas condensate
10. Separator Test
11. Viscosity Test
12. PVTO/PVTG/EOS preparation

DATA REQUIRED:
- Separator pressure
- Separator temperature
- Oil rate
- Gas rate
- GOR
- Gas composition
- Oil composition
- API
- Gas specific gravity
- Water cut
- H2S/CO2 if present
"""


def is_surface_separator_question(text):

    t = text.lower()

    has_oil = (
        "surface separator oil" in t
        or "separator oil" in t
        or "زيت من الفاصل" in t
        or "عينة زيت" in t
    )

    has_gas = (
        "separator gas" in t
        or "غاز من الفاصل" in t
        or "عينة غاز" in t
    )

    return has_oil and has_gas


def handle_document(chat_id, document):

    file_id = document["file_id"]
    file_name = document.get("file_name", "file")
    mime_type = document.get("mime_type", "")
    ext = os.path.splitext(file_name)[1].lower() or ".bin"

    path = download_file(file_id, ext)

    if not path:
        send_message(chat_id, "Error: could not download file.")
        return

    lower = file_name.lower()

    if lower.endswith(".pdf"):

        text = extract_pdf_text(path)

        if not text:
            send_message(
                chat_id,
                "PDF was received, but no readable text was extracted. "
                "It may be scanned. Send pages as images for /graph analysis."
            )
            return

        FILE_CONTEXT[chat_id] = text[:MAX_CONTEXT_CHARS]

        send_message(
            chat_id,
            "PDF received and text extracted successfully.\nUse /analyze to analyze it."
        )

        return

    if lower.endswith(".docx"):

        text = extract_docx_text(path)

        if not text:
            send_message(chat_id, "DOCX received, but no readable text was found.")
            return

        FILE_CONTEXT[chat_id] = text[:MAX_CONTEXT_CHARS]

        send_message(
            chat_id,
            "DOCX received and text extracted successfully.\nUse /analyze to analyze it."
        )

        return

    if mime_type.startswith("image/") or lower.endswith((".png", ".jpg", ".jpeg", ".webp")):

        IMAGE_CONTEXT[chat_id] = path

        send_message(
            chat_id,
            "Image received successfully.\nUse /graph to analyze it."
        )

        return

    send_message(
        chat_id,
        "Unsupported file type. Supported files: PDF, DOCX, PNG, JPG, JPEG, WEBP."
    )


def handle_photo(chat_id, photos):

    best_photo = photos[-1]
    file_id = best_photo["file_id"]

    path = download_file(file_id, ".jpg")

    if not path:
        send_message(chat_id, "Error: could not download image.")
        return

    IMAGE_CONTEXT[chat_id] = path

    send_message(
        chat_id,
        "Image received successfully.\nUse /graph to analyze it."
    )


print("Petroleum Engineering AI Bot running...")


while True:

    try:

        updates = requests.get(
            f"{TELEGRAM_URL}/getUpdates",
            params={
                "offset": offset + 1,
                "timeout": 30
            },
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
                send_message(chat_id, "Send text, PDF/DOCX, or image.")
                continue

            text = message["text"].strip()

            if text == "/start":
                send_message(chat_id, start_message())
                continue

            if text == "/reset":
                FILE_CONTEXT.pop(chat_id, None)
                IMAGE_CONTEXT.pop(chat_id, None)
                send_message(chat_id, "Stored file and image context cleared.")
                continue

            if text == "/glossary":
                send_message(chat_id, glossary_command())
                continue

            if text.startswith("/plot"):
                query = text.replace("/plot", "", 1).strip()
                send_message(chat_id, plot_relationship(query))
                continue

            if text.startswith("/check"):
                send_message(chat_id, check_command(text))
                continue

            if text.startswith("/calc"):
                send_message(chat_id, calculate_command(text))
                continue

            if text.startswith("/estimate"):
                send_message(chat_id, estimate_command(text))
                continue

            if text.startswith("/classify"):
                send_message(chat_id, classify_command(text))
                continue

            if text == "/pvto":
                send_message(chat_id, generate_pvto_skeleton())
                continue

            if text == "/pvtg":
                send_message(chat_id, generate_pvtg_skeleton())
                continue

            if text.startswith("/export_sim"):
                fluid_type = text.replace("/export_sim", "", 1).strip()
                send_message(chat_id, export_simulation(fluid_type))
                continue

            if text.startswith("/analyze"):
                send_message(chat_id, analyze_command(chat_id))
                continue

            if text.startswith("/graph"):
                send_message(chat_id, graph_command(chat_id, text))
                continue

            if is_surface_separator_question(text):
                send_message(chat_id, surface_separator_command())
                continue

            context = FILE_CONTEXT.get(chat_id)
            reply = ask_ai(text, context)
            send_message(chat_id, reply)

    except Exception as e:
        print("Main loop error:", e)

    time.sleep(1)
