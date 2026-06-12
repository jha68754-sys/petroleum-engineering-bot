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
Reservoir = Ø§ÙÙÙÙÙ Reservoir.
Well = Ø§ÙØ¨Ø¦Ø± Well.
Formation = Ø§ÙØªÙÙÙÙ Formation.
Bottom Hole Sample = Ø¹ÙÙØ© ÙØ§Ø¹ Ø§ÙØ¨Ø¦Ø± Bottom Hole Sample.
Surface Separator Oil Sample = Ø¹ÙÙØ© Ø²ÙØª ÙÙ Ø§ÙÙØ§ØµÙ Ø§ÙØ³Ø·Ø­Ù Surface Separator Oil Sample.
Separator Gas Sample = Ø¹ÙÙØ© ØºØ§Ø² ÙÙ Ø§ÙÙØ§ØµÙ Separator Gas Sample.
Stock Tank Oil = Ø²ÙØª Ø§ÙØ®Ø²Ø§Ù Ø§ÙØ³Ø·Ø­Ù Stock Tank Oil.
Recombined Sample = Ø¹ÙÙØ© ÙØ¹Ø§Ø¯ ØªØ±ÙÙØ¨ÙØ§ Recombined Sample.
Recombination = Ø¥Ø¹Ø§Ø¯Ø© ØªØ±ÙÙØ¨ Ø§ÙØ¹ÙÙØ© Recombination.
Bubble Point Pressure = Ø¶ØºØ· ÙÙØ·Ø© Ø§ÙÙÙØ§Ø¹Ø© Bubble Point Pressure.
Dew Point Pressure = Ø¶ØºØ· ÙÙØ·Ø© Ø§ÙÙØ¯Ù Dew Point Pressure.
Bo = ÙØ¹Ø§ÙÙ Ø­Ø¬Ù Ø§ÙØªÙÙÙÙ ÙÙØ²ÙØª Oil Formation Volume Factor.
Bg = ÙØ¹Ø§ÙÙ Ø­Ø¬Ù Ø§ÙØªÙÙÙÙ ÙÙØºØ§Ø² Gas Formation Volume Factor.
Rs = ÙØ³Ø¨Ø© Ø§ÙØºØ§Ø² Ø§ÙÙØ°Ø§Ø¨ Solution Gas-Oil Ratio.
GOR = ÙØ³Ø¨Ø© Ø§ÙØºØ§Ø² Ø¥ÙÙ Ø§ÙØ²ÙØª Gas-Oil Ratio.
CGR = ÙØ³Ø¨Ø© Ø§ÙÙÙØ«ÙØ§Øª Ø¥ÙÙ Ø§ÙØºØ§Ø² Condensate-Gas Ratio.
Z-factor = ÙØ¹Ø§ÙÙ Ø§ÙØ§ÙØ­Ø±Ø§Ù Ø§ÙØºØ§Ø²Ù Gas Deviation Factor.
Viscosity = Ø§ÙÙØ²ÙØ¬Ø© Viscosity.
Density = Ø§ÙÙØ«Ø§ÙØ© Density.
Specific Gravity = Ø§ÙÙØ«Ø§ÙØ© Ø§ÙÙÙØ¹ÙØ© Specific Gravity.
API Gravity = Ø¯Ø±Ø¬Ø© API.
CCE = Constant Composition Expansion.
CME = Constant Mass Expansion.
DV = Differential Vaporization / Differential Liberation.
CVD = Constant Volume Depletion.
Separator Test = Ø§Ø®ØªØ¨Ø§Ø± Ø§ÙÙØ§ØµÙ Separator Test.
Flash Test = Ø§Ø®ØªØ¨Ø§Ø± Ø§ÙÙÙÙØ¶ Flash Test.
Compositional Analysis = Ø§ÙØªØ­ÙÙÙ Ø§ÙØªØ±ÙÙØ¨Ù Compositional Analysis.
EOS Tuning = ÙÙØ§Ø¡ÙØ© ÙØ¹Ø§Ø¯ÙØ© Ø§ÙØ­Ø§ÙØ© EOS Tuning.
PVTO = Ø¬Ø¯ÙÙ PVTO ÙÙØ­Ø§ÙÙ Eclipse.
PVTG = Ø¬Ø¯ÙÙ PVTG ÙÙØ­Ø§ÙÙ Eclipse.
CMG PVT Input = ÙØ¯Ø®ÙØ§Øª PVT ÙÙØ­Ø§ÙÙ CMG.

Forbidden terms:
- Do not call Bo Ø§ÙØ¶ØºØ· Ø§ÙØ¨ÙÙÙ or Ø§ÙÙØ¹Ø§ÙÙ Ø§ÙØ¨ÙÙÙ.
- Do not call Rs Ø§ÙØªØ±Ø´ÙØ­.
- Do not call GOR Ø§ÙÙØ³Ø¨Ø© Ø§ÙÙØ¦ÙÙØ© ÙÙØºØ§Ø².
- Do not say Ø§ÙÙÙØ²Ø¬ for Viscosity.
- Do not say Ø§ÙØ­ÙØ±Ø© for Reservoir.
- Do not say Ø§ÙØ³Ø·ÙØ¹ Ø§ÙÙÙØ¹Ù or Ø§Ø®ØªØ¨Ø§Ø± Ø§ÙØ³Ø·ÙØ¹.
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
        "Ø§ÙØ¶ØºØ· Ø§ÙØ¨ÙÙÙ": "ÙØ¹Ø§ÙÙ Ø­Ø¬Ù Ø§ÙØªÙÙÙÙ",
        "Ø§ÙÙØ¹Ø§ÙÙ Ø§ÙØ¨ÙÙÙ": "ÙØ¹Ø§ÙÙ Ø­Ø¬Ù Ø§ÙØªÙÙÙÙ",
        "Ø§ÙØªØ±Ø´ÙØ­": "ÙØ³Ø¨Ø© Ø§ÙØºØ§Ø² Ø§ÙÙØ°Ø§Ø¨",
        "Ø§ÙÙØ³Ø¨Ø© Ø§ÙÙØ¦ÙÙØ© ÙÙØºØ§Ø²": "ÙØ³Ø¨Ø© Ø§ÙØºØ§Ø² Ø¥ÙÙ Ø§ÙØ²ÙØª",
        "ÙØ³Ø¨Ø© Ø§ÙØºØ§Ø² Ø§ÙÙØ¦ÙÙØ©": "ÙØ³Ø¨Ø© Ø§ÙØºØ§Ø² Ø¥ÙÙ Ø§ÙØ²ÙØª",
        "Ø§ÙÙÛØ³ÙÙØ²ÙØ©": "Ø§ÙÙØ²ÙØ¬Ø©",
        "Ø§ÙÙÙØ²Ø¬": "Ø§ÙÙØ²ÙØ¬Ø©",
        "Ø§ÙØ­ÙØ±Ø©": "Ø§ÙÙÙÙÙ",
        "Ø§ÙØ³Ø·ÙØ¹ Ø§ÙÙÙØ¹Ù": "Ø§ÙÙØ«Ø§ÙØ© Ø§ÙÙÙØ¹ÙØ©",
        "Ø§Ø®ØªØ¨Ø§Ø± Ø§ÙØ³Ø·ÙØ¹": "Ø§Ø®ØªØ¨Ø§Ø± Ø§ÙÙØ«Ø§ÙØ© Ø§ÙÙÙØ¹ÙØ©",
        "Volume Expansion Factor": "Oil Formation Volume Factor",
    }
    for wrong, correct in replacements.items():
        text = text.replace(wrong, correct)
    return text.strip()

def send_message(chat_id, text):
    text = clean_text(text)
    if not text:
        text = "ÙÙ Ø£ØªÙÙÙ ÙÙ ØªÙÙÙØ¯ Ø±Ø¯ ÙØ§Ø¶Ø­."
    for i in range(0, len(text), 3900):
        requests.post(
            f"{TELEGRAM_URL}/sendMessage",
            data={"chat_id": chat_id, "text": text[i:i+3900]},
            timeout=30
        )
        time.sleep(0.4)

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
        return "Ø­Ø¯Ø« Ø®Ø·Ø£ ÙÙ Groq:\n" + str(data)[:1500]
    except Exception as e:
        return "Ø­Ø¯Ø« Ø®Ø·Ø£ ÙÙ Ø§ÙØ§ØªØµØ§Ù Ø¨Ø®Ø¯ÙØ© Ø§ÙØ°ÙØ§Ø¡ Ø§ÙØ§ØµØ·ÙØ§Ø¹Ù:\n" + str(e)

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
        return "Ø­Ø¯Ø« Ø®Ø·Ø£ ÙÙ Groq Vision:\n" + str(data)[:1500]
    except Exception as e:
        return "Ø­Ø¯Ø« Ø®Ø·Ø£ ÙÙ ØªØ­ÙÙÙ Ø§ÙØµÙØ±Ø©:\n" + str(e)

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
                send_message(chat_id, "ÙØ±Ø£Øª ÙÙÙ PDF ÙÙÙ ÙÙ Ø£Ø³ØªØ®Ø±Ø¬ ÙØµØ§Ù ÙØ§Ø¶Ø­Ø§Ù. ØºØ§ÙØ¨Ø§Ù Ø§ÙÙÙÙ Ø³ÙØ§Ù ØµÙØ±Ø©. Ø£Ø±Ø³ÙÙ Ø§ÙØµÙØ­Ø§Øª Ø£Ù Ø§ÙØ±Ø³ÙÙØ§Øª ÙØµÙØ±Ø Ø£Ù Ø§Ø±ÙØ¹Ù PDF ÙØµÙ.")
                return
            FILE_CONTEXT[chat_id] = text
            send_message(chat_id, "ØªÙ ÙØ±Ø§Ø¡Ø© PDF Ø¨ÙØ¬Ø§Ø­. Ø§ÙÙÙÙ Ø£ØµØ¨Ø­ ÙØ±Ø¬Ø¹Ø§Ù ÙÙØ°Ù Ø§ÙÙØ­Ø§Ø¯Ø«Ø©. Ø§ÙØªØ¨Ù /analyze ÙØªØ­ÙÙÙ Ø§ÙØªÙØ±ÙØ± ÙÙØ¯Ø³ÙØ§Ù.")
            return

        if lower.endswith(".docx"):
            text = extract_docx_text(local_path)
            if not text:
                send_message(chat_id, "ÙØ±Ø£Øª ÙÙÙ DOCX ÙÙÙ ÙÙ Ø£Ø¬Ø¯ ÙØµØ§Ù ÙØ§Ø¶Ø­Ø§Ù.")
                return
            FILE_CONTEXT[chat_id] = text
            send_message(chat_id, "ØªÙ ÙØ±Ø§Ø¡Ø© DOCX Ø¨ÙØ¬Ø§Ø­. Ø§ÙÙÙÙ Ø£ØµØ¨Ø­ ÙØ±Ø¬Ø¹Ø§Ù ÙÙØ°Ù Ø§ÙÙØ­Ø§Ø¯Ø«Ø©.")
            return

        if mime_type.startswith("image/") or lower.endswith((".png", ".jpg", ".jpeg", ".webp")):
            IMAGE_CONTEXT[chat_id] = local_path
            send_message(chat_id, "ØªÙ Ø§Ø³ØªÙØ§Ù Ø§ÙØµÙØ±Ø© Ø¨ÙØ¬Ø§Ø­. Ø§ÙØªØ¨Ù /graph ÙØªØ­ÙÙÙ Ø§ÙØ±Ø³Ù Ø£Ù Ø§ÙØ´ÙÙ ÙÙØ¯Ø³ÙØ§Ù.")
            return

        send_message(chat_id, "Ø§ÙÙÙÙ ÙØ§Ø²Ù ÙÙÙÙ PDF Ø£Ù DOCX Ø£Ù ØµÙØ±Ø©.")
    except Exception as e:
        send_message(chat_id, "Ø­Ø¯Ø« Ø®Ø·Ø£ Ø£Ø«ÙØ§Ø¡ ÙØ±Ø§Ø¡Ø© Ø§ÙÙÙÙ:\n" + str(e))

def handle_photo(chat_id, photos):
    try:
        best = photos[-1]
        file_id = best["file_id"]
        local_path = download_telegram_file(file_id, "uploaded_image.jpg")
        IMAGE_CONTEXT[chat_id] = local_path
        send_message(chat_id, "ØªÙ Ø§Ø³ØªÙØ§Ù Ø§ÙØµÙØ±Ø© Ø¨ÙØ¬Ø§Ø­. Ø§ÙØªØ¨Ù /graph ÙØªØ­ÙÙÙ Ø§ÙØ±Ø³Ù Ø£Ù Ø§ÙØ´ÙÙ ÙÙØ¯Ø³ÙØ§Ù.")
    except Exception as e:
        send_message(chat_id, "Ø­Ø¯Ø« Ø®Ø·Ø£ Ø£Ø«ÙØ§Ø¡ ØªØ­ÙÙÙ Ø§ÙØµÙØ±Ø©:\n" + str(e))

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
    has_oil = "surface separator oil" in t or "separator oil" in t or "Ø²ÙØª ÙÙ Ø§ÙÙØ§ØµÙ" in t or "Ø¹ÙÙØ© Ø²ÙØª" in t
    has_gas = "separator gas" in t or "ØºØ§Ø² ÙÙ Ø§ÙÙØ§ØµÙ" in t or "Ø¹ÙÙØ© ØºØ§Ø²" in t
    return has_oil and has_gas

def start_message():
    return """
Ø£ÙÙØ§Ù Ø¨Ù ÙÙ PVT Lab AI Bot.

Ø£ÙØ§ ÙØ³Ø§Ø¹Ø¯ ÙÙØ¯Ø³Ù ÙØªØ®ØµØµ ÙÙ:
- PVT Laboratory
- Reservoir Fluid Analysis
- Reservoir Simulation
- PDF/DOCX report analysis
- Graph and figure interpretation
- Eclipse / CMG PVT guidance

Ø§ÙØ£ÙØ§ÙØ±:
/analyze
/report
/calc
/plot
/graph
/interpret_graph
/check
/export_sim
/pvto
/pvtg
/eclipse
/cmg

ÙÙØ§Ø­Ø¸Ø©:
ÙØ§ Ø£Ø­Ø³Ø¨ ÙÙÙØ§Ù ÙÙØ§Ø¦ÙØ© Ø£Ù Ø£ÙØªØ¨ Ø¨ÙØ§ÙØ§Øª ÙØ®ØªØ¨Ø±ÙØ© Ø±ÙÙÙØ© Ø¥ÙØ§ Ø¥Ø°Ø§ Ø²ÙØ¯ØªÙÙ Ø¨Ø§ÙØ¨ÙØ§ÙØ§Øª.
"""

def surface_separator_direct_answer():
    return """
ØªØ­ÙÙÙ ÙÙØ¯Ø³Ù ÙØ¹ÙÙØ© Ø²ÙØª ÙÙ Ø§ÙÙØ§ØµÙ Ø§ÙØ³Ø·Ø­Ù ÙØ¹ Ø¹ÙÙØ© ØºØ§Ø² ÙÙ Ø§ÙÙØ§ØµÙ

ÙÙØ¹ Ø§ÙØ¹ÙÙØ§Øª

Ø§ÙØ¹ÙÙØ§Øª Ø§ÙÙØ°ÙÙØ±Ø© ÙÙ Ø¹ÙÙØ§Øª Ø³Ø·Ø­ÙØ© ÙÙÙØµÙØ©:
- Surface Separator Oil Sample: Ø¹ÙÙØ© Ø²ÙØª ÙÙ Ø§ÙÙØ§ØµÙ Ø§ÙØ³Ø·Ø­Ù.
- Separator Gas Sample: Ø¹ÙÙØ© ØºØ§Ø² ÙÙ Ø§ÙÙØ§ØµÙ.

ÙØ°Ù Ø§ÙØ¹ÙÙØ§Øª ÙØ§ ØªÙØ«Ù Ø³Ø§Ø¦Ù Ø§ÙÙÙÙÙ Ø§ÙØ£ØµÙÙ ÙØ¨Ø§Ø´Ø±Ø© ÙØ«Ù Bottom Hole SampleØ ÙØ£Ù Ø§ÙØ²ÙØª ÙØ§ÙØºØ§Ø² Ø§ÙÙØµÙØ§ Ø¹ÙØ¯ Ø¸Ø±ÙÙ Ø§ÙÙØ§ØµÙ Ø§ÙØ³Ø·Ø­Ù. ÙØ°ÙÙ ÙÙØ²Ù Ø¹Ø§Ø¯Ø© Ø¥Ø¬Ø±Ø§Ø¡ Recombination ÙØ¥Ø¹Ø§Ø¯Ø© Ø¨ÙØ§Ø¡ Ø³Ø§Ø¦Ù Ø§ÙÙÙÙÙ ÙØ¨Ù Ø§ÙØ­ÙÙ Ø¹ÙÙ Ø®ÙØ§Øµ PVT Ø§ÙÙÙØ§Ø¦ÙØ©.

Ø§ÙØ¨ÙØ§ÙØ§Øª Ø§ÙÙØ·ÙÙØ¨Ø©

- Separator Pressure Ø¶ØºØ· Ø§ÙÙØ§ØµÙ.
- Separator Temperature Ø¯Ø±Ø¬Ø© Ø­Ø±Ø§Ø±Ø© Ø§ÙÙØ§ØµÙ.
- Oil Rate ÙØ¹Ø¯Ù Ø¥ÙØªØ§Ø¬ Ø§ÙØ²ÙØª.
- Gas Rate ÙØ¹Ø¯Ù Ø¥ÙØªØ§Ø¬ Ø§ÙØºØ§Ø².
- Producing GOR Ø£Ù Separator GOR ÙØ³Ø¨Ø© Ø§ÙØºØ§Ø² Ø¥ÙÙ Ø§ÙØ²ÙØª.
- Separator Gas Composition ØªØ±ÙÙØ¨ ØºØ§Ø² Ø§ÙÙØ§ØµÙ.
- Separator Oil Ø£Ù Stock Tank Oil Composition ØªØ±ÙÙØ¨ Ø§ÙØ²ÙØª.
- Oil Density ÙØ«Ø§ÙØ© Ø§ÙØ²ÙØª.
- API Gravity Ø¯Ø±Ø¬Ø© API.
- Gas Specific Gravity Ø§ÙÙØ«Ø§ÙØ© Ø§ÙÙÙØ¹ÙØ© ÙÙØºØ§Ø².
- Water Cut Ø£Ù ÙØ¬ÙØ¯ ÙØ³ØªØ­ÙØ¨.
- CO2 Ù H2S Ø¥Ù ÙØ¬Ø¯Øª.

Ø§ÙØ§Ø®ØªØ¨Ø§Ø±Ø§Øª Ø§ÙÙØ·ÙÙØ¨Ø©

1. Sample QC
ÙØ­Øµ Ø­Ø§ÙØ© Ø§ÙØ¹ÙÙØ§ØªØ Ø§ÙØªØ³Ø±ÙØ¨Ø Ø¶ØºØ· Ø§ÙØ¹ÙÙØ©Ø ÙØªÙØ«ÙÙÙØ© Ø§ÙØ¹ÙÙØ©.

2. Compositional Analysis
ØªØ­ÙÙÙ ØªØ±ÙÙØ¨Ù ÙÙØºØ§Ø² ÙØ§ÙØ²ÙØªØ ÙØ¹ ØªÙØµÙÙ C7+ Ø£Ù C12+ Ø­Ø³Ø¨ ÙØ¸Ø§Ù Ø§ÙÙØ®ØªØ¨Ø±.

3. Recombination
Ø¥Ø¹Ø§Ø¯Ø© ØªØ±ÙÙØ¨ Ø²ÙØª Ø§ÙÙØ§ØµÙ ÙØ¹ ØºØ§Ø² Ø§ÙÙØ§ØµÙ Ø¨Ø§Ø³ØªØ®Ø¯Ø§Ù Producing GOR Ø£Ù ÙØ¹Ø¯ÙØ§Øª Ø§ÙØ²ÙØª ÙØ§ÙØºØ§Ø² ÙØ¸Ø±ÙÙ Ø§ÙÙØ§ØµÙ.

4. Validation of Recombined Fluid
Ø§ÙØªØ£ÙØ¯ ÙÙ Ø£Ù Ø§ÙØ¹ÙÙØ© Ø§ÙÙØ¹Ø§Ø¯ ØªØ±ÙÙØ¨ÙØ§ ÙØ³ØªÙØ±Ø© ÙØªÙØ«Ù Ø³Ø§Ø¦Ù Ø§ÙÙÙÙÙ Ø¨Ø´ÙÙ ÙÙØ¨ÙÙ.

5. CCE Ø£Ù CME
ÙØªØ­Ø¯ÙØ¯ Ø¶ØºØ· Ø§ÙØªØ´Ø¨Ø¹ ÙØ³ÙÙÙ Ø§ÙØ­Ø¬Ù ÙØ¹ Ø§ÙØ¶ØºØ·.

6. DV Differential Vaporization
Ø¥Ø°Ø§ ÙØ§Ù Ø§ÙÙØ¸Ø§Ù Black Oil Ø£Ù Volatile OilØ ÙÙØ­ØµÙÙ Ø¹ÙÙ Rs Ù Bo ÙØ§ÙÙØ«Ø§ÙØ© ÙØ§ÙÙØ²ÙØ¬Ø©.

7. CVD Constant Volume Depletion
Ø¥Ø°Ø§ ÙØ§Ù Ø§ÙÙØ¸Ø§Ù Gas CondensateØ ÙØ¯Ø±Ø§Ø³Ø© Liquid Dropout Ù Dew Point Ù CGR.

8. Separator Test
ÙØªÙÙÙÙ ØªØ£Ø«ÙØ± Ø¸Ø±ÙÙ Ø§ÙÙØ§ØµÙ Ø¹ÙÙ GOR Ù Stock Tank Oil Ù API Ù shrinkage.

9. Viscosity Test
ÙÙÙØ§Ø³ ÙØ²ÙØ¬Ø© Ø§ÙØ²ÙØª ÙØ§ÙØºØ§Ø² Ø¹ÙØ¯ Ø§ÙØ­Ø§Ø¬Ø©.

Ø§ÙØ­Ø³Ø§Ø¨Ø§Øª Ø§ÙÙÙÙÙØ© Ø¹ÙØ¯ ØªÙÙØ± Ø§ÙØ¨ÙØ§ÙØ§Øª

- Recombination Ratio.
- Total GOR.
- Rs ÙØ³Ø¨Ø© Ø§ÙØºØ§Ø² Ø§ÙÙØ°Ø§Ø¨.
- Bo ÙØ¹Ø§ÙÙ Ø­Ø¬Ù Ø§ÙØªÙÙÙÙ ÙÙØ²ÙØª.
- Bg ÙØ¹Ø§ÙÙ Ø­Ø¬Ù Ø§ÙØªÙÙÙÙ ÙÙØºØ§Ø².
- Z-factor.
- Oil Density.
- API Gravity.
- Oil Viscosity.
- Gas Viscosity.
- Compressibility.
- Y-Function.

Ø§ÙÙÙØ­ÙÙØ§Øª Ø§ÙÙØ·ÙÙØ¨Ø©

- Pressure vs Bo.
- Pressure vs Rs.
- Pressure vs Oil Viscosity.
- Pressure vs Density.
- Pressure vs Relative Volume.
- Pressure vs Y-Function.
- ÙÙØºØ§Ø² Ø§ÙÙÙØ«Ù: Pressure vs Liquid Dropout Ù Pressure vs CGR.

Ø¥Ø¹Ø¯Ø§Ø¯ Ø§ÙÙØ­Ø§ÙØ§Ø©

Ø¥Ø°Ø§ ÙØ§Ù Ø§ÙØ³Ø§Ø¦Ù Black Oil:
ØªØ³ØªØ®Ø¯Ù Ø¨ÙØ§ÙØ§Øª DV Ù Separator Test ÙØªØ¬ÙÙØ² PVTO ÙÙ EclipseØ Ø¨Ø´Ø±Ø· ØªÙÙØ± Pressure Ù Rs Ù Bo Ù Oil Viscosity.

Ø¥Ø°Ø§ ÙØ§Ù Ø§ÙØ³Ø§Ø¦Ù Gas Condensate Ø£Ù Volatile Oil:
Ø§ÙØ£ÙØ¶Ù Ø§Ø³ØªØ®Ø¯Ø§Ù Compositional Model ÙØ¹ EOS Tuning ÙÙ CMG Ø£Ù Eclipse Compositional.

Ø§ÙØ®ÙØ§ØµØ©

Ø§ÙØ®Ø·ÙØ© Ø§ÙØµØ­ÙØ­Ø© ÙÙØ³Øª Ø§Ø¹ØªØ¨Ø§Ø± Ø¹ÙÙØ§Øª Ø§ÙØ³Ø·Ø­ ÙÙØ«ÙØ© ÙØ¨Ø§Ø´Ø±Ø© ÙÙÙÙÙÙØ Ø¨Ù Ø¥Ø¬Ø±Ø§Ø¡ Recombination Ø«Ù Ø§Ø®ØªØ¨Ø§Ø±Ø§Øª PVT Ø§ÙÙÙØ§Ø³Ø¨Ø©. Ø¨Ø¯ÙÙ Ø¨ÙØ§ÙØ§Øª Ø§ÙÙØ§ØµÙ Ù GOR ÙØ§ÙØªØ±ÙÙØ¨ ÙØ§ ÙÙÙÙ Ø­Ø³Ø§Ø¨ ÙÙÙ ÙÙØ§Ø¦ÙØ© ÙÙØ«ÙÙØ© ÙØ«Ù Bo Ø£Ù Rs Ø£Ù Bubble Point Pressure.
"""

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
                send_message(chat_id, "Ø£Ø±Ø³ÙÙ ÙØµØ§Ù Ø£Ù ÙÙÙ PDF/DOCX Ø£Ù ØµÙØ±Ø©.")
                continue

            text = message["text"]
            context = FILE_CONTEXT.get(chat_id)

            if text.strip() == "/start":
                send_message(chat_id, start_message())
                continue

            if is_surface_separator_question(text):
                send_message(chat_id, surface_separator_direct_answer())
                continue

            if is_graph_command(text):
                image_path = IMAGE_CONTEXT.get(chat_id)
                if not image_path:
                    send_message(chat_id, "Ø£Ø±Ø³ÙÙ ØµÙØ±Ø© Ø§ÙØ±Ø³Ù Ø£Ù Figure Ø£ÙÙØ§ÙØ ÙØ¨Ø¹Ø¯ÙØ§ Ø§ÙØªØ¨Ù /graph.")
                    continue
                prompt = text + "\n\nAnalyze this engineering figure professionally. Identify axes, units, trend, anomalies, non-physical behavior, retrograde behavior if applicable, contamination indicators, separator performance issues, engineering meaning, possible causes, and recommendations."
                reply = ask_vision_ai(prompt, image_path, context)
                send_message(chat_id, reply)
                continue

            if is_plot_command(text):
                prompt = text + "\n\nIf numerical data are provided, explain which PVT plot should be prepared and interpret the expected trend. If data are missing, list the exact arrays needed. Do not invent values."
                reply = ask_ai(prompt, context)
                send_message(chat_id, reply)
                continue

            if is_export_command(text):
                prompt = text + "\n\nGenerate simulator export guidance. Decide black-oil vs compositional based on data. Include unit checks, consistency checks, Eclipse/CMG keyword guidance, warnings, and missing required data."
                reply = ask_ai(prompt, context)
                send_message(chat_id, reply)
                continue

            reply = ask_ai(text, context)
            send_message(chat_id, reply)

    except Exception as e:
        print(e)

    time.sleep(1)
