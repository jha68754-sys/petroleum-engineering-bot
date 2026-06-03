import os
import requests
import time
import tempfile
from PyPDF2 import PdfReader
from docx import Document

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.getenv("OPENAI_API_KEY")

TELEGRAM_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

GROQ_MODEL = "llama-3.3-70b-versatile"

offset = 0

FILE_CONTEXT = {}

SYSTEM_PROMPT = """
You are a professional petroleum engineering assistant specialized in PVT laboratory reports.

You write like an experienced PVT laboratory engineer, not like a chatbot.

Main task:
Read real PVT report text provided by the user, understand its structure, style, terminology, tables, sections, and reporting logic, then generate professional PVT reports based on the same reporting style.

Language rules:
- If the user writes Arabic, answer in Arabic.
- If the user writes English, answer in English.
- If the user mixes Arabic and English, answer in the same mixed style.
- Use correct petroleum engineering terminology.

Professional PVT report style:
When writing a report, follow a real Reservoir Fluid Analysis / PVT Study structure:

Report Title
Report Information
Client
Field
Well
Sample Type
Introduction
Objectives
Methods of Analysis and Presentation of Results
Well Information
Sample Inventory and History
Summary of Quality Control Data
Validity Check of Samples
Selected Sample for Complete PVT Study
Constant Mass Expansion / Constant Composition Expansion Test
Differential Vaporization Test
Separator Test
Reservoir Fluid Viscosity Test
Summary of PVT Data
Tables
Figures
Discussion and Engineering Interpretation
Conclusion
Recommendations
Required Additional Data

Important rules:
- Use the uploaded real report only as a reference for style, structure, and engineering logic.
- Do not copy confidential company names, well names, field names, report numbers, dates, or private values unless the user asks to analyze the same report.
- Do not invent real laboratory values.
- If values are missing, leave blanks using: ______
- If the user asks for a sample report, clearly write: SAMPLE DATA FOR DEMONSTRATION ONLY.
- If the user provides numerical data, use only those values.
- If the user asks for calculations, show Given Data, Formula, Substitution, Calculation, Final Answer, and Engineering Interpretation.
- If the user asks for plots and provides data, organize the data and describe the curve.

Formatting rules:
- Do not use markdown symbols like **, ###, or vertical-line tables.
- Write clean plain text suitable for Telegram.
- Use clear section titles.
- Keep paragraphs readable.
"""

def clean_text(text):
    text = str(text)
    text = text.replace("**", "")
    text = text.replace("###", "")
    text = text.replace("##", "")
    text = text.replace("#", "")
    text = text.replace("|", " ")
    text = text.replace("[", "")
    text = text.replace("]", "")
    return text

def send_message(chat_id, text):
    text = clean_text(text)

    if len(text) <= 3900:
        requests.post(
            f"{TELEGRAM_URL}/sendMessage",
            data={"chat_id": chat_id, "text": text}
        )
    else:
        for i in range(0, len(text), 3900):
            part = text[i:i + 3900]
            requests.post(
                f"{TELEGRAM_URL}/sendMessage",
                data={"chat_id": chat_id, "text": part}
            )
            time.sleep(0.5)

def ask_ai(user_text, file_context=None):
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT}
    ]

    if file_context:
        messages.append({
            "role": "user",
            "content": "This is extracted text from a real PVT report. Use it as reference style and context only:\n\n" + file_context[:25000]
        })

    messages.append({"role": "user", "content": user_text})

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": GROQ_MODEL,
        "messages": messages,
        "temperature": 0.25,
        "max_tokens": 3500
    }

    response = requests.post(
        GROQ_URL,
        headers=headers,
        json=payload,
        timeout=90
    )

    data = response.json()

    if "choices" in data:
        return data["choices"][0]["message"]["content"]

    return str(data)[:1500]

def extract_pdf_text(file_path):
    text = ""
    reader = PdfReader(file_path)

    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text += page_text + "\n\n"

    return text.strip()

def extract_docx_text(file_path):
    doc = Document(file_path)
    text = ""

    for paragraph in doc.paragraphs:
        if paragraph.text.strip():
            text += paragraph.text + "\n"

    return text.strip()

def download_telegram_file(file_id, file_name):
    file_info = requests.get(
        f"{TELEGRAM_URL}/getFile",
        params={"file_id": file_id},
        timeout=30
    ).json()

    file_path = file_info["result"]["file_path"]
    file_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"

    suffix = os.path.splitext(file_name)[1]

    temp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    temp.close()

    file_data = requests.get(file_url, timeout=60).content

    with open(temp.name, "wb") as f:
        f.write(file_data)

    return temp.name

def handle_document(chat_id, document):
    file_id = document["file_id"]
    file_name = document.get("file_name", "uploaded_file")

    try:
        local_path = download_telegram_file(file_id, file_name)

        if file_name.lower().endswith(".pdf"):
            extracted_text = extract_pdf_text(local_path)
        elif file_name.lower().endswith(".docx"):
            extracted_text = extract_docx_text(local_path)
        else:
            send_message(chat_id, "الملف لازم يكون PDF أو DOCX فقط.")
            return

        if not extracted_text:
            send_message(chat_id, "قرأت الملف لكن ما قدرتش نستخرج نص واضح منه. ممكن يكون الملف سكان صورة.")
            return

        FILE_CONTEXT[chat_id] = extracted_text

        send_message(
            chat_id,
            "تم قراءة الملف بنجاح.\n\n"
            "توا نقدر نعتمد عليه كسياق لتقرير PVT.\n\n"
            "جربي تكتبي:\n"
            "/report\n"
            "اكتب تقرير PVT جديد بنفس أسلوب الملف، لعينة Bottom Hole Fluid Sample، كقالب فقط بدون أرقام افتراضية."
        )

    except Exception as e:
        send_message(chat_id, "صار خطأ أثناء قراءة الملف:\n" + str(e))

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

            if "text" in message:
                text = message["text"]

                if text == "/start":
                    reply = (
                        "أهلاً بك في PVT Lab AI Bot.\n\n"
                        "أرسل ملف PDF أو DOCX لتقرير PVT حقيقي، وبعدها اطلب تقرير جديد بنفس الأسلوب.\n\n"
                        "الأوامر:\n"
                        "/report لكتابة تقرير\n"
                        "/calc للحسابات\n"
                        "/plot لتنظيم بيانات الرسم"
                    )
                else:
                    context = FILE_CONTEXT.get(chat_id)
                    reply = ask_ai(text, context)

                send_message(chat_id, reply)

    except Exception as e:
        print(e)

    time.sleep(1)
