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
MAX_CONTEXT_CHARS = 8000

SYSTEM_PROMPT = """
You are Petroleum Engineering AI Bot.
Act as a professional petroleum engineer.

Rules:
- Do not invent numbers.
- If data is missing, write DATA REQUIRED.
- Separate lab value, correlation estimate, assumption, and engineering judgment.
- Arabic question -> Arabic answer.
- English question -> English answer.
- Keep terms: Bo, Bg, Rs, Rv, GOR, CGR, PVT, CCE, CVD, PVTO, PVTG.

Correct PVT rules:
Bo = Reservoir oil volume / stock tank oil volume.
For black oil and volatile oil:
Above Pb: Rs constant. Bo increases slightly as pressure decreases toward Pb.
At Pb: Bo is maximum Bob. Never say Bo is minimum at Pb.
Below Pb: Rs decreases. Bo decreases as pressure decreases. Never say Bo increases below Pb.

Rs:
Above Pb constant at Rsi. Below Pb decreases as pressure decreases.

Bg:
Bg decreases as pressure increases.

Z-factor:
Gas Compressibility Factor, dimensionless, used in PV = ZnRT. Not Cg.

Liquid dropout:
Above Pd = 0. Below Pd rises, reaches peak, may decrease.

Forbidden wrong terms:
الضغط البيني، المعامل البيني، الترشيح as Rs، الليزج، الويسكوزية، الحفرة as reservoir، Pressuring Volume and Temperature.
"""

PLOTS = {
    "bo": """Bo vs Pressure
Correct behavior:
Above Pb: Bo increases as pressure decreases toward Pb.
At Pb: Bo reaches maximum Bob.
Below Pb: Bo decreases as pressure decreases.

Bo
^
|              * Bob max at Pb
|           .-' \\
|        .-'     \\____
|_____.-'
+--------------------------> Pressure
 low P        Pb        high P
""",
    "rs": """Rs vs Pressure
Above Pb: constant Rsi.
Below Pb: decreases as pressure decreases.

Rs
^
|          __________ Rsi
|        /
|      /
|____/
+--------------------------> Pressure
 low P        Pb        high P
""",
    "bg": """Bg vs Pressure
Bg decreases as pressure increases.

Bg
^
|\\
| \\___
|     \\_____
+--------------------------> Pressure
 low P                 high P
""",
    "z": """Z-factor vs Pressure
Z-factor is dimensionless gas compressibility factor.
Typical shape can be U-shaped/checkmark.

Z
^
| \\____        ____
|      \\______/
+--------------------------> Pressure
""",
    "dropout": """Liquid Dropout vs Pressure
Above Pd: 0.
Below Pd: rises, reaches peak, may decrease.

Dropout
^
|       ___
|    .-'   '-.__
|___.'
+--------------------------> Pressure
 low P        Pd        high P
"""
}

def clean_text(text):
    fixes = {
        "Pressuring Volume and Temperature": "Pressure-Volume-Temperature",
        "الضغط البيني": "معامل حجم التكوين",
        "المعامل البيني": "معامل حجم التكوين",
        "الترشيح": "نسبة الغاز المذاب",
        "الويسكوزية": "اللزوجة",
        "الليزج": "اللزوجة",
        "الحفرة": "المكمن",
    }
    text = str(text)
    for wrong, right in fixes.items():
        text = text.replace(wrong, right)
    return text.strip()

def send_message(chat_id, text):
    text = clean_text(text)
    for i in range(0, len(text), 3900):
        requests.post(
            f"{TELEGRAM_URL}/sendMessage",
            json={"chat_id": chat_id, "text": text[i:i+3900]},
            timeout=20
        )
        time.sleep(0.2)

def download_file(file_id, suffix=".bin"):
    info = requests.get(
        f"{TELEGRAM_URL}/getFile",
        params={"file_id": file_id},
        timeout=20
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

def extract_pdf_text(path):
    reader = PdfReader(path)
    pages = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            pages.append(text)
    return "\n\n".join(pages).strip()

def extract_docx_text(path):
    doc = Document(path)
    lines = []
    for p in doc.paragraphs:
        text = p.text.strip()
        if text:
            lines.append(text)
    return "\n".join(lines)

def encode_image(path):
    mime, _ = mimetypes.guess_type(path)
    if not mime:
        mime = "image/jpeg"
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return f"data:{mime};base64,{b64}"

def ask_ai(user_text, file_context=None):
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if file_context:
        messages.append({
            "role": "user",
            "content": "Reference document:\n" + file_context[:MAX_CONTEXT_CHARS]
        })
    messages.append({"role": "user", "content": user_text[:3000]})

    r = requests.post(
        GROQ_URL,
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": TEXT_MODEL,
            "messages": messages,
            "temperature": 0.05,
            "max_tokens": 1200
        },
        timeout=90
    )
    if r.status_code == 413:
        return "الطلب كبير جداً. اكتب سؤال أقصر أو ارفع ملف أصغر."
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]

def ask_vision_ai(prompt, image_path):
    messages = [{
        "role": "user",
        "content": [
            {"type": "text", "text": prompt[:2000]},
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
            "temperature": 0.05,
            "max_tokens": 1000
        },
        timeout=120
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]

def start_message():
    return """Petroleum Engineering AI Bot

الأوامر:
/check bo
/check rs
/check z
/check dropout
/plot bo
/plot rs
/plot bg
/plot z
/plot dropout
/calc api sg=0.85
/calc hydrostatic mw=10 tvd=5000
/calc ooip area=500 h=50 phi=0.2 sw=0.3 bo=1.3
/estimate pb_standing rs=650 gas_sg=0.75 tres=180 api=35
/classify gor=4500 api=45
/pvto
/pvtg
/analyze بعد رفع PDF/DOCX
/graph بعد رفع صورة
/reset
"""

def check_command(text):
    q = text.lower()

    if "bo" in q:
        return """Bo Check Rule

Correct behavior:
Above Pb: Bo increases slightly as pressure decreases toward Pb.
At Pb: Bo reaches maximum Bob.
Below Pb: Bo decreases as pressure decreases.

Wrong statements:
Bo minimum at Pb = wrong.
Bo increases below Pb = wrong.
"""

    if "rs" in q:
        return """Rs Check Rule

Above Pb: Rs is constant at Rsi.
At Pb: Rs = Rsi.
Below Pb: Rs decreases as pressure decreases.
"""

    if "z" in q:
        return """Z-factor Check Rule

Z-factor = Gas Compressibility Factor.
Unit: dimensionless.
Used in PV = ZnRT.
It is not gas compressibility Cg.
"""

    if "dropout" in q:
        return """Liquid Dropout Check Rule

Above Pd: 0%.
At Pd: first liquid appears.
Below Pd: dropout rises, reaches peak, then may decrease.
"""

    return "Usage: /check bo OR /check rs OR /check z OR /check dropout"

def plot_command(text):
    key = text.replace("/plot", "", 1).strip().lower()
    if key in PLOTS:
        return PLOTS[key]
    return "Available plots: bo, rs, bg, z, dropout"

def calc_command(text):
    q = text.lower()
    nums = {k: float(v) for k, v in re.findall(r"(\w+)=([-+]?\d*\.?\d+)", q)}

    if "api" in q:
        if "sg" not in nums:
            return "DATA REQUIRED: sg\nExample: /calc api sg=0.85"
        api = (141.5 / nums["sg"]) - 131.5
        return f"API = {api:.2f}"

    if "hydrostatic" in q:
        if "mw" not in nums or "tvd" not in nums:
            return "DATA REQUIRED: mw, tvd"
        p = 0.052 * nums["mw"] * nums["tvd"]
        return f"Hydrostatic Pressure = {p:.2f} psi"

    if "ooip" in q:
        req = ["area", "h", "phi", "sw", "bo"]
        missing = [x for x in req if x not in nums]
        if missing:
            return "DATA REQUIRED: area, h, phi, sw, bo"
        ooip = 7758 * nums["area"] * nums["h"] * nums["phi"] * (1 - nums["sw"]) / nums["bo"]
        return f"OOIP = {ooip:,.0f} STB"

    return "Available: /calc api, /calc hydrostatic, /calc ooip"

def estimate_command(text):
    q = text.lower()
    nums = {k: float(v) for k, v in re.findall(r"(\w+)=([-+]?\d*\.?\d+)", q)}

    if "pb_standing" in q:
        req = ["rs", "gas_sg", "tres", "api"]
        missing = [x for x in req if x not in nums]
        if missing:
            return "DATA REQUIRED: rs, gas_sg, tres, api"
        rs = nums["rs"]
        gas_sg = nums["gas_sg"]
        tres = nums["tres"]
        api = nums["api"]
        pb = 18.2 * (((rs / gas_sg) ** 0.83) * (10 ** (0.00091 * tres - 0.0125 * api)) - 1.4)
        return f"CORRELATION ESTIMATE\nStanding Pb = {pb:.2f} psia\nVerify with CCE/CME lab data."

    return "Available: /estimate pb_standing rs=650 gas_sg=0.75 tres=180 api=35"

def classify_command(text):
    nums = {k: float(v) for k, v in re.findall(r"(\w+)=([-+]?\d*\.?\d+)", text.lower())}
    if "gor" not in nums or "api" not in nums:
        return "DATA REQUIRED: gor, api"

    gor = nums["gor"]
    api = nums["api"]

    if gor < 2000 and api < 40:
        return "Fluid Type: Black Oil"
    if 2000 <= gor < 8000 and 40 <= api <= 50:
        return "Fluid Type: Volatile Oil"
    if 8000 <= gor < 100000 and 50 <= api <= 70:
        return "Fluid Type: Gas Condensate"
    if gor >= 100000:
        return "Fluid Type: Wet/Dry Gas"

    return "Fluid type uncertain. DATA REQUIRED: composition and reservoir temperature."

def pvto():
    return """PVTO Skeleton

Required columns:
Rs
Pressure
Bo
Oil viscosity

DATA REQUIRED:
DV data below Pb.
CCE data above Pb.
Never fabricate values.
"""

def pvtg():
    return """PVTG Skeleton

Required columns:
Pressure
Bg
Gas viscosity
Rv

DATA REQUIRED:
CVD data.
Gas composition.
Never fabricate values.
"""

def handle_document(chat_id, document):
    file_id = document["file_id"]
    file_name = document.get("file_name", "file")
    ext = os.path.splitext(file_name)[1].lower() or ".bin"
    path = download_file(file_id, ext)

    if not path:
        send_message(chat_id, "Could not download file.")
        return

    try:
        if file_name.lower().endswith(".pdf"):
            text = extract_pdf_text(path)
            FILE_CONTEXT[chat_id] = text[:MAX_CONTEXT_CHARS]
            send_message(chat_id, "PDF received. Use /analyze.")
            return

        if file_name.lower().endswith(".docx"):
            text = extract_docx_text(path)
            FILE_CONTEXT[chat_id] = text[:MAX_CONTEXT_CHARS]
            send_message(chat_id, "DOCX received. Use /analyze.")
            return

        if file_name.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
            IMAGE_CONTEXT[chat_id] = path
            send_message(chat_id, "Image received. Use /graph.")
            return

        send_message(chat_id, "Supported: PDF, DOCX, JPG, PNG, WEBP.")
    except Exception as e:
        send_message(chat_id, f"File error: {e}")

def handle_photo(chat_id, photos):
    path = download_file(photos[-1]["file_id"], ".jpg")
    IMAGE_CONTEXT[chat_id] = path
    send_message(chat_id, "Image received. Use /graph.")

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
                send_message(chat_id, "Context cleared.")
                continue

            if text.startswith("/check"):
                send_message(chat_id, check_command(text))
                continue

            if text.startswith("/plot"):
                send_message(chat_id, plot_command(text))
                continue

            if text.startswith("/calc"):
                send_message(chat_id, calc_command(text))
                continue

            if text.startswith("/estimate"):
                send_message(chat_id, estimate_command(text))
                continue

            if text.startswith("/classify"):
                send_message(chat_id, classify_command(text))
                continue

            if text == "/pvto":
                send_message(chat_id, pvto())
                continue

            if text == "/pvtg":
                send_message(chat_id, pvtg())
                continue

            if text.startswith("/analyze"):
                context = FILE_CONTEXT.get(chat_id)
                if not context:
                    send_message(chat_id, "لا يوجد ملف مرفوع. أرسل PDF أو DOCX أولاً.")
                else:
                    send_message(chat_id, ask_ai("Analyze this petroleum engineering document. Do not invent values.", context))
                continue

            if text.startswith("/graph"):
                img = IMAGE_CONTEXT.get(chat_id)
                if not img:
                    send_message(chat_id, "أرسل صورة أولاً.")
                else:
                    send_message(chat_id, ask_vision_ai("Analyze this petroleum engineering graph. Identify axes and trend.", img))
                continue

            context = FILE_CONTEXT.get(chat_id)
            send_message(chat_id, ask_ai(text, context))

    except Exception as e:
        print("Main loop error:", e)

    time.sleep(1)
