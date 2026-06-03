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

GLOBAL_PVT_REFERENCE = """
REFERENCE STYLE FOR ALL USERS:

The bot must write PVT reports following the style of a real Reservoir Fluid Analysis / PVT Study report.

The professional report structure should follow this order when suitable:

1. Cover / Report Title
- Reservoir Fluid Analysis
- PVT Study for Bottom Hole Fluid Sample
- Client: ______
- Field: ______
- Well No.: ______
- Formation: ______
- Sample Type: ______
- Report Date: ______

2. Introduction
This section explains that the report represents a PVT study carried out on reservoir fluid samples collected from the specified well. It should mention that the analyses were performed at the request of the client.

3. Objectives
State the main objective of the study, such as performing PVT analysis on bottom hole fluid samples collected at a specified depth and date.

4. Methods of Analysis and Presentation of Results
Include the laboratory workflow:
- Validity check of bottom hole samples
- Restoration of samples to reservoir conditions
- Constant Mass Expansion / Constant Composition Expansion test
- Differential Vaporization test
- Separator test
- Reservoir fluid viscosity test
- Compositional analysis
- Presentation of results in tables and figures

5. Well Information
Include:
- Sampling date
- Formation name
- Sampling depth
- Bottom hole pressure
- Bottom hole temperature
- Separator pressure and temperature if available
- Oil rate, gas rate, water rate if available
- Oil gravity, gas gravity, GOR if available

6. Sample Inventory and History
Include:
- Sample type
- Sample number
- Sampling point/depth
- Sampling date
- Opening pressure
- Opening temperature
- Sample volume
- Notes about water/emulsion if provided

7. Summary of Bottom Hole Samples Received and Validation Data
Include:
- Cylinder number
- Shipping pressure and temperature
- Laboratory pressure and temperature
- Bubble point / saturation pressure
- Validation comments

8. Summary of PVT Data
Include only values provided by the user:
- Bubble point pressure
- Reservoir temperature
- Thermal expansion coefficient
- Compressibility
- Solution gas-oil ratio
- Oil formation volume factor
- Density
- Viscosity
- Separator test data
- Tank oil gravity

9. Validity Check
Write professionally:
The samples were checked for validation to ensure that no leakage occurred during sampling or transportation. Opening pressure was compared with field transfer pressure. Samples were restored to reservoir conditions to ensure homogeneity before conducting laboratory tests.

10. Constant Mass Expansion / Constant Composition Expansion Test
Mention:
- The sample was charged into a PVT cell
- Heated to reservoir temperature
- Pressure-volume relationship was measured
- Saturation pressure was determined
- Relative volume, Y-function, compressibility, and thermal expansion can be reported

11. Differential Vaporization Test
Mention:
- The test was carried out below saturation pressure at reservoir temperature
- Liberated gas at each stage was removed
- Results include Rs, liberated GOR, Bo, density, gas gravity, Z-factor, Bg, gas composition, and residual oil composition

12. Separator Test
Mention:
- Separator test was performed at specified pressure and temperature
- Results include separator GOR, Bo, gas composition, stock tank oil composition, and total GOR

13. Reservoir Fluid Viscosity Test
Mention:
- Viscosity was measured at reservoir temperature
- Measurements may cover pressures above and below saturation pressure
- Stock tank oil kinematic viscosity may be measured at different temperatures

14. Tables
Generate table-like plain text without markdown symbols:
Table 1: Well Information
Table 2: Sample Inventory and History
Table 3: Summary of Validation Data
Table 4: Summary of PVT Data
Table 5: Constant Mass Expansion Test
Table 6: Differential Vaporization Test
Table 7: Separator Test
Table 8: Reservoir Fluid Viscosity

15. Figures
List expected figures:
Figure 1: Pressure vs Relative Volume
Figure 2: Pressure vs Y-Function
Figure 3: Pressure vs Fluid Density
Figure 4: Pressure vs Oil Formation Volume Factor
Figure 5: Pressure vs Gas Oil Ratio
Figure 6: Pressure vs Gas Gravity
Figure 7: Pressure vs Gas Deviation Factor
Figure 8: Pressure vs Gas Formation Volume Factor
Figure 9: Pressure vs Oil Viscosity

16. Discussion and Engineering Interpretation
Interpret the fluid behavior professionally using only provided values. Do not invent conclusions from missing values.

17. Conclusion
Summarize the main findings. If data are missing, state that the final conclusion requires complete laboratory data.

18. Recommendations
Mention required additional data, further validation, EOS tuning, separator optimization, or simulation input preparation when appropriate.

Rules:
- Do not copy confidential company names, well names, field names, report numbers, or exact values from any uploaded reference unless the user asks to analyze that exact report.
- Do not invent real PVT values.
- If values are missing, write blank fields like: ______
- If the user asks for a template, create a clean template without fake numbers.
- If the user asks for sample data, clearly write: SAMPLE DATA FOR DEMONSTRATION ONLY.
"""

SYSTEM_PROMPT = """
You are a professional petroleum engineering assistant specialized in PVT laboratory reports.

You write like an experienced PVT laboratory engineer, not like a chatbot.

Main task:
Write professional Reservoir Fluid Analysis / PVT Study reports using the fixed reference style provided.

Language rules:
- If the user writes Arabic, answer in Arabic.
- If the user writes English, answer in English.
- If the user mixes Arabic and English, answer in the same mixed style.
- Use correct petroleum engineering terminology.

Report rules:
- Follow the fixed PVT reference structure.
- Write in a strong real laboratory report style.
- Do not invent real laboratory values.
- Use blanks when data are missing.
- Use uploaded PDF/DOCX text as extra context if available.
- Do not use markdown symbols like **, ###, or vertical-line tables.
- Write clean plain text suitable for Telegram.

For /report:
Create a professional PVT report or report section.

For /calc:
Perform calculations step by step:
Given Data
Formula
Substitution
Calculation
Final Answer
Engineering Interpretation

For /plot:
Organize the data and explain the curve. If graph image generation is not enabled, say that plotting support is required.
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
            requests.post(
                f"{TELEGRAM_URL}/sendMessage",
                data={"chat_id": chat_id, "text": text[i:i + 3900]}
            )
            time.sleep(0.5)

def ask_ai(user_text, file_context=None):
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": GLOBAL_PVT_REFERENCE}
    ]

    if file_context:
        messages.append({
            "role": "user",
            "content": "Extra uploaded PVT report context for this user:\n\n" + file_context[:25000]
        })

    messages.append({"role": "user", "content": user_text})

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": GROQ_MODEL,
        "messages": messages,
        "temperature": 0.22,
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
            "التقرير الثابت موجود أصلاً كمرجع عام للجميع.\n"
            "وهذا الملف حيكون مرجع إضافي لهذه المحادثة فقط.\n\n"
            "اكتب مثلاً:\n"
            "/report\n"
            "اكتب تقرير PVT جديد بنفس أسلوب التقرير الحقيقي، لعينة Bottom Hole Fluid Sample، كقالب فقط بدون أرقام افتراضية."
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
                        "يمكنني كتابة تقارير PVT بأسلوب تقرير مختبري حقيقي.\n"
                        "المرجع الأساسي محفوظ داخل البوت ويعمل مع جميع المستخدمين.\n\n"
                        "يمكنك أيضاً إرسال PDF أو DOCX كتقرير إضافي.\n\n"
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
