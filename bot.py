import os
import time
import base64
import tempfile
import mimetypes
import requests
import re
import math
from PyPDF2 import PdfReader
from docx import Document

# ─────────────────────────────────────────────
#  CONFIGURATION & ENVIRONMENT
# ─────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.getenv("OPENAI_API_KEY") # Note: Ensure env var name matches your setup

if not TELEGRAM_BOT_TOKEN or not GROQ_API_KEY:
    raise ValueError("Missing Environment Variables: TELEGRAM_BOT_TOKEN or OPENAI_API_KEY")

TELEGRAM_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

TEXT_MODEL = os.getenv("GROQ_TEXT_MODEL", "llama-3.3-70b-versatile")
VISION_MODEL = os.getenv("GROQ_VISION_MODEL", "llama-3.2-90b-vision-preview") # Updated to a stable vision model on Groq

offset = 0
FILE_CONTEXT = {}
IMAGE_CONTEXT = {}

# ─────────────────────────────────────────────
#  SYSTEM PROMPT (Professional Petroleum Engineer)
# ─────────────────────────────────────────────
SYSTEM_PROMPT = """
You are a senior Petroleum Engineering Consultant specializing in PVT, Reservoir Engineering, and Drilling.

Language Rules:
- Match the user's language (Arabic/English).
- Use professional technical terminology.
- Keep key technical terms in English (e.g., Permeability, Porosity, Bubble Point).

Strict Technical Guidelines:
1. PVT Definitions:
   - Bo is Oil Formation Volume Factor (NOT interfacial pressure).
   - Rs is Solution Gas-Oil Ratio (NOT filtration).
   - Viscosity is اللزوجة (NOT الليزج).
   - Reservoir is المكمن (NOT الحفرة).

2. Workflow Logic:
   - If user provides Surface Separator Samples -> Recommend Recombination first.
   - If user asks for Black Oil Simulation -> Recommend PVTO table generation.
   - If user asks for Gas Condensate -> Recommend CVD test and Compositional Model.

3. Calculations:
   - Do NOT invent lab data.
   - If data is missing, list exactly what is needed (e.g., "I need Separator Pressure and GOR").
   - For simple calculations (API, Hydrostatic Pressure), provide the formula and result if inputs are clear.

4. Formatting:
   - No Markdown bolding (**). Use clean text.
   - Use clear headings.
   - Be concise and direct.
"""

# ─────────────────────────────────────────────
#  PETROLEUM KNOWLEDGE BASE (The Scientific Edifice)
# ─────────────────────────────────────────────

GLOSSARY_TERMS = [
    {"en": "Porosity", "ar": "المسامية", "cat": "Reservoir", "def": "Ratio of void volume to bulk volume. Storage capacity."},
    {"en": "Permeability", "ar": "النفاذية", "cat": "Reservoir", "def": "Ability of rock to transmit fluids. Measured in Darcy/mD."},
    {"en": "Bubble Point", "ar": "نقطة الفقاعة", "cat": "PVT", "def": "Pressure at which first gas bubble forms from oil."},
    {"en": "Dew Point", "ar": "نقطة الندى", "cat": "PVT", "def": "Pressure at which first liquid droplet forms from gas."},
    {"en": "Formation Volume Factor (Bo)", "ar": "معامل حجم التكوين", "cat": "PVT", "def": "Ratio of oil volume at reservoir conditions to stock tank conditions."},
    {"en": "Skin Factor", "ar": "عامل الجلد", "cat": "Production", "def": "Measure of formation damage or stimulation around wellbore."},
    {"en": "Hydrostatic Pressure", "ar": "الضغط الهيدروستاتيكي", "cat": "Drilling", "def": "Pressure exerted by a column of fluid. P = 0.052 * MW * TVD."},
    {"en": "Kick", "ar": "اندفاع", "cat": "Drilling", "def": "Unwanted influx of formation fluids into the wellbore."},
    {"en": "Water Cut", "ar": "نسبة الماء", "cat": "Production", "def": "Fraction of water in total liquid production."},
    {"en": "GOR", "ar": "نسبة الغاز للنفط", "cat": "Production", "def": "Volume of gas produced per unit of oil (scf/stb)."}
]

ENGINEERING_FORMULAS = {
    "api": {
        "name": "API Gravity",
        "formula": "lambda sg: (141.5 / sg) - 131.5",
        "inputs": ["Specific Gravity (sg)"],
        "unit": "deg API"
    },
    "hydrostatic": {
        "name": "Hydrostatic Pressure",
        "formula": "lambda mw, tvd: 0.052 * mw * tvd",
        "inputs": ["Mud Weight (ppg)", "TVD (ft)"],
        "unit": "psi"
    },
    "ooip": {
        "name": "OOIP (Stock Tank Barrels)",
        "formula": "lambda a, h, phi, sw, bo: (7758 * a * h * phi * (1 - sw)) / bo",
        "inputs": ["Area (acres)", "Height (ft)", "Porosity (fraction)", "Sw (fraction)", "Bo"],
        "unit": "STB"
    },
    "darcy_linear": {
        "name": "Linear Darcy Flow",
        "formula": "lambda k, a, dp, mu, l: (k * a * dp) / (mu * l)",
        "inputs": ["k (mD)", "Area (ft2)", "Delta P (psi)", "Viscosity (cp)", "Length (ft)"],
        "unit": "bbl/day (approx with constant)" 
        # Note: Simplified for demo, real field units need constant 0.001127
    }
}

# ─────────────────────────────────────────────
#  HELPER FUNCTIONS
# ─────────────────────────────────────────────

def send_message(chat_id, text, parse_mode="Markdown"):
    """Send message with error handling and splitting long texts"""
    if not text:
        return
    
    # Clean up markdown if needed based on prompt rules, but Telegram supports basic MD
    # We will use simple text formatting to be safe as per prompt instructions
    clean_text = str(text).replace("**", "").replace("###", "")
    
    max_len = 4000
    for i in range(0, len(clean_text), max_len):
        chunk = clean_text[i:i+max_len]
        try:
            requests.post(
                f"{TELEGRAM_URL}/sendMessage",
                json={"chat_id": chat_id, "text": chunk, "parse_mode": None},
                timeout=10
            )
        except Exception as e:
            print(f"Error sending message: {e}")
        time.sleep(0.5)

def send_document(chat_id, file_content, filename, caption):
    """Send generated HTML or other files"""
    try:
        requests.post(
            f"{TELEGRAM_URL}/sendDocument",
            data={"chat_id": chat_id, "caption": caption},
            files={"document": (filename, file_content, "text/html")},
            timeout=15
        )
    except Exception as e:
        send_message(chat_id, f"Error sending file: {str(e)}")

def download_file(file_id, file_name_suffix=".bin"):
    """Download file from Telegram servers"""
    file_info = requests.get(f"{TELEGRAM_URL}/getFile", params={"file_id": file_id}).json()
    if file_info.get("ok"):
        file_path = file_info["result"]["file_path"]
        url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"
        
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=file_name_suffix)
        response = requests.get(url, timeout=30)
        if response.status_code == 200:
            temp_file.write(response.content)
            temp_file.close()
            return temp_file.name
    return None

def extract_text_from_pdf(path):
    try:
        reader = PdfReader(path)
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        return text
    except:
        return ""

def extract_text_from_docx(path):
    try:
        doc = Document(path)
        return "\n".join([p.text for p in doc.paragraphs])
    except:
        return ""

# ─────────────────────────────────────────────
#  CALCULATION ENGINE (The "Brain" for Math)
# ─────────────────────────────────────────────

def handle_calculation(text):
    """
    Parses simple engineering calculations from text.
    Example: "calculate API for SG 0.85" or "hydrostatic pressure mw 10 tvd 5000"
    """
    text_lower = text.lower()
    
    # 1. API Gravity
    if "api" in text_lower and ("sg" in text_lower or "specific gravity" in text_lower):
        numbers = re.findall(r"[-+]?\d*\.\d+|\d+", text)
        if numbers:
            sg = float(numbers[0])
            api = (141.5 / sg) - 131.5
            return f"📊 Result:\nAPI Gravity = {api:.2f} deg API\n(Specific Gravity = {sg})"

    # 2. Hydrostatic Pressure
    if "hydrostatic" in text_lower or "pressure" in text_lower:
        numbers = re.findall(r"[-+]?\d*\.\d+|\d+", text)
        if len(numbers) >= 2:
            mw = float(numbers[0])
            tvd = float(numbers[1])
            hp = 0.052 * mw * tvd
            return f"📊 Result:\nHydrostatic Pressure = {hp:.2f} psi\n(MW={mw} ppg, TVD={tvd} ft)"

    # 3. OOIP
    if "ooip" in text_lower:
        numbers = re.findall(r"[-+]?\d*\.\d+|\d+", text)
        if len(numbers) >= 5:
            a, h, phi, sw, bo = map(float, numbers[:5])
            ooip = (7758 * a * h * phi * (1 - sw)) / bo
            return f"📊 Result:\nOOIP = {ooip:,.0f} STB\n(Area={a} acres, h={h} ft, Phi={phi}, Sw={sw}, Bo={bo})"

    return None # Return None if no calculation matched

# ─────────────────────────────────────────────
#  AI INTEGRATION
# ─────────────────────────────────────────────

def ask_groq(messages, model=TEXT_MODEL):
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.1,
        "max_tokens": 2000
    }
    try:
        resp = requests.post(GROQ_URL, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"⚠️ AI Error: {str(e)}"

def generate_glossary_html():
    """Generates the interactive HTML glossary"""
    terms_json = str(GLOSSARY_TERMS).replace("'", '"')
    
    html = f"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<title>Petroleum Glossary</title>
<style>
    body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #f4f4f9; color: #333; padding: 20px; }}
    .card {{ background: white; border-radius: 8px; padding: 15px; margin-bottom: 10px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); border-right: 5px solid #007bff; }}
    h1 {{ color: #0056b3; text-align: center; }}
    .en {{ font-weight: bold; color: #d63384; direction: ltr; display: inline-block; }}
    .ar {{ font-size: 1.1em; font-weight: bold; margin-right: 10px; }}
    .def {{ color: #555; margin-top: 5px; font-size: 0.95em; }}
    .cat {{ background: #e9ecef; padding: 2px 6px; border-radius: 4px; font-size: 0.8em; float: left; }}
</style>
</head>
<body>
    <h1>🛢️ Petroleum Engineering Glossary</h1>
    <div id="terms"></div>
    <script>
        const terms = {terms_json};
        const container = document.getElementById('terms');
        terms.forEach(t => {{
            const div = document.createElement('div');
            div.className = 'card';
            div.innerHTML = `
                <span class="cat">${{t.cat}}</span>
                <div style="clear:both; margin-top:5px;"></div>
                <span class="ar">${{t.ar}}</span>
                <span class="en">${{t.en}}</span>
                <p class="def">${{t.def}}</p>
            `;
            container.appendChild(div);
        }});
    </script>
</body>
</html>"""
    return html.encode('utf-8')

# ─────────────────────────────────────────────
#  MAIN BOT LOOP
# ─────────────────────────────────────────────

print("🚀 Bot is running...")

while True:
    try:
        updates = requests.get(f"{TELEGRAM_URL}/getUpdates", params={"offset": offset + 1, "timeout": 30}, timeout=40).json()
        
        for update in updates.get("result", []):
            offset = update["update_id"]
            message = update.get("message")
            if not message: continue
            
            chat_id = message["chat"]["id"]
            text = message.get("text", "").strip()
            
            # 1. Handle Documents (PDF/DOCX)
            if "document" in message:
                doc = message["document"]
                file_id = doc["file_id"]
                file_name = doc.get("file_name", "")
                
                path = download_file(file_id, "." + file_name.split(".")[-1] if "." in file_name else ".pdf")
                if path:
                    content = ""
                    if file_name.endswith(".pdf"):
                        content = extract_text_from_pdf(path)
                    elif file_name.endswith(".docx"):
                        content = extract_text_from_docx(path)
                    
                    if content:
                        FILE_CONTEXT[chat_id] = content[:15000] # Limit context size
                        send_message(chat_id, "✅ File processed. I have read the document. You can now ask questions about it.")
                    else:
                        send_message(chat_id, "⚠️ Could not extract text. Make sure it's not a scanned image.")
                continue

            # 2. Handle Photos (for Graph Analysis)
            if "photo" in message:
                photo = message["photo"][-1] # Get highest resolution
                path = download_file(photo["file_id"], ".jpg")
                if path:
                    IMAGE_CONTEXT[chat_id] = path
                    send_message(chat_id, "🖼️ Image received. Send /graph to analyze it.")
                continue

            # 3. Handle Commands
            if text == "/start":
                send_message(chat_id, 
                    "Welcome to Petroleum AI Assistant.\n\n"
                    "Commands:\n"
                    "/glossary - Get Interactive HTML Glossary\n"
                    "/calc [query] - Quick Calculation (e.g., /calc API for SG 0.85)\n"
                    "/graph - Analyze uploaded image\n"
                    "/analyze - Analyze uploaded PDF/DOCX\n"
                    "\nJust type your question naturally!"
                )
                continue

            if text == "/glossary":
                html_data = generate_glossary_html()
                send_document(chat_id, html_data, "petroleum_glossary.html", "📚 Interactive Petroleum Glossary")
                continue

            if text.startswith("/calc"):
                query = text.replace("/calc", "")
                result = handle_calculation(query)
                if result:
                    send_message(chat_id, result)
                else:
                    send_message(chat_id, "Could not calculate. Try format: '/calc API for SG 0.85' or '/calc hydrostatic mw 10 tvd 5000'")
                continue

            if text == "/graph":
                img_path = IMAGE_CONTEXT.get(chat_id)
                if not img_path:
                    send_message(chat_id, "Please upload an image first.")
                    continue
                
                # Prepare Vision Request
                with open(img_path, "rb") as f:
                    b64_img = base64.b64encode(f.read()).decode("utf-8")
                
                messages = [
                    {"role": "system", "content": SYSTEM_PROMPT + "\nYou are analyzing an engineering graph/image."},
                    {"role": "user", "content": [
                        {"type": "text", "text": "Analyze this petroleum engineering graph. Identify axes, trends, and anomalies."},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"}}
                    ]}
                ]
                reply = ask_groq(messages, model=VISION_MODEL)
                send_message(chat_id, reply)
                continue

            # 4. Default AI Chat (Text)
            messages = [{"role": "system", "content": SYSTEM_PROMPT}]
            
            # Add File Context if exists
            if chat_id in FILE_CONTEXT:
                messages.append({"role": "system", "content": f"Context from uploaded file:\n{FILE_CONTEXT[chat_id][:5000]}"})
            
            messages.append({"role": "user", "content": text})
            
            reply = ask_groq(messages)
            send_message(chat_id, reply)

    except Exception as e:
        print(f"Main Loop Error: {e}")
        time.sleep(5)

