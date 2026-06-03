import os
import re
import time
import base64
import tempfile
import mimetypes
import requests
import matplotlib.pyplot as plt
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

GLOBAL_PVT_REFERENCE = """
Professional PVT Engineering Reference System

This assistant is not a simple template writer.
It must act like a real PVT laboratory engineer and reservoir fluid specialist.

The uploaded or fixed reference report is only a professional reference example used to:
- Understand engineering workflow.
- Learn report writing style.
- Recognize useful sections.
- Improve interpretation quality.
- Identify possible engineering enhancements.

Future PVT reports may differ depending on:
- Company standards.
- Client requirements.
- Reservoir type.
- Fluid system.
- Test scope.
- Laboratory objectives.
- Simulation needs.
- Data availability.

Missing sections identified in a reference report must be treated only as optional engineering improvement suggestions, not mandatory requirements for every report.

Always adapt dynamically to:
- Sample type.
- Fluid type.
- Reservoir type.
- Available data.
- Laboratory objectives.
- Report scope.
- Simulation objectives.
- Client requirements.

Never force a rigid template.

Main PVT report sections that may be used when suitable:
- Report Title
- Report Information
- Client
- Field
- Well
- Formation
- Sample Type
- Introduction
- Objectives
- Methods of Analysis and Presentation of Results
- Well Information
- Sample Inventory and History
- Summary of Quality Control Data
- Validity Check of Samples
- Selected Sample for Complete PVT Study
- CCE / CME Test
- Differential Vaporization Test
- CVD Test
- Separator Test
- Recombination
- Compositional Analysis
- Reservoir Fluid Viscosity
- Summary of PVT Data
- Tables
- Figures
- Engineering Discussion
- Fluid Classification
- Simulator Input Preparation
- Conclusion
- Recommendations
- Required Additional Data

Engineering workflow by sample type:

1. Bottom Hole Fluid Sample:
Focus on:
- Sample validation.
- Opening pressure check.
- Leak check.
- Restoration to reservoir conditions.
- CCE/CME.
- Differential Vaporization for oil systems.
- CVD for gas condensate systems.
- Separator test.
- Viscosity.
- Composition.
- PVT summary tables.
- Pressure-property plots.

2. Surface Separator Oil Sample:
Focus on:
- Separator oil properties.
- Recombination with separator gas if required.
- Stock tank oil properties.
- Flash test.
- Separator test.
- API gravity.
- Oil composition.
- GOR.
- Fluid characterization.
- Simulation input preparation.

3. Separator Gas Sample:
Focus on:
- Gas composition.
- Gas molecular weight.
- Gas specific gravity.
- Z-factor.
- Bg.
- Gas viscosity.
- Heating value.
- Recombination if paired with separator liquid.

4. Recombined Sample:
Focus on:
- Recombination ratio.
- Validation of recombined fluid.
- CCE/CME.
- DV or CVD depending on fluid system.
- Separator test.
- Viscosity.
- Composition.
- EOS tuning if required.

5. Black Oil:
Focus on:
- Bubble point pressure.
- Rs.
- Bo.
- Density.
- Viscosity.
- Differential Liberation.
- Separator test.
- Stock tank oil API gravity.
- PVTO export.

6. Volatile Oil:
Focus on:
- Saturation pressure.
- High GOR.
- Shrinkage behavior.
- Composition.
- Separator optimization.
- EOS/compositional simulation if needed.

7. Gas Condensate:
Focus on:
- Dew point pressure.
- CVD.
- Liquid dropout.
- CGR.
- Z-factor.
- Gas viscosity.
- Retrograde condensation.
- Separator conditions.
- PVTG or compositional model.

8. Dry Gas / Wet Gas:
Focus on:
- Gas composition.
- Z-factor.
- Bg.
- Gas viscosity.
- Gas density.
- Heating value.
- Condensate content if present.

Graph Interpretation AI:
When analyzing engineering graphs, adapt to graph type.
Supported graph types:
- PVT curves.
- Pressure vs Relative Volume.
- Pressure vs Y-Function.
- Pressure vs Bo.
- Pressure vs Rs.
- Pressure vs Density.
- Pressure vs Viscosity.
- Z-factor curves.
- CVD liquid dropout plots.
- Separator trends.
- Pressure-volume behavior.
- Phase envelope graphs.
- Gas condensate liquid dropout.
- Retrograde behavior.

For graph interpretation:
- Identify axes and units if visible.
- Identify trend direction.
- Detect anomalies.
- Detect non-physical trends.
- Detect retrograde behavior when applicable.
- Detect possible contamination indicators.
- Detect bad separator performance indicators.
- Explain engineering meaning.
- Give possible causes.
- Give recommendations.
- Never assume a fixed graph template.

Reservoir Simulator Export System:
Support:
- PVTO tables.
- PVTG tables.
- Eclipse-compatible formatting.
- CMG-ready formatting.
- EOS export guidance.
- Black-oil conversion guidance.
- Compositional simulation guidance.
- Unit validation.
- Consistency checks.
- Simulator warnings.
- Keyword explanations.
- Export formatting rules.

Simulation engineering logic:
- Use black-oil simulation when fluid behavior can be represented by pressure-dependent Rs, Bo, viscosity, and gas/oil tables.
- Use compositional simulation when composition, phase behavior, gas condensate behavior, volatile oil behavior, miscibility, CO2/H2S, or EOS tuning is important.
- DV data supports black-oil oil tables.
- CVD data supports gas condensate behavior and compositional/EOS work.
- Separator conditions affect stock tank properties, GOR, Bo, and simulator surface conditions.
- EOS tuning must be consistent with saturation pressure, CCE/CME, CVD/DV, separator data, and viscosity.
"""

SYSTEM_PROMPT = """
You are a professional Petroleum Engineering and PVT Laboratory AI assistant.

You must behave like a real PVT laboratory engineer, reservoir fluid specialist, and simulation engineer.

Do not act like a chatbot.
Do not say: As an AI language model.
Do not give generic answers.
Use engineering judgment.

Main capabilities:
- Analyze PVT reports.
- Read uploaded PDF/DOCX context.
- Interpret uploaded graph images.
- Identify sample type.
- Select suitable lab tests.
- Write professional PVT reports.
- Perform calculations when data are provided.
- Generate plots from numerical data.
- Interpret PVT plots.
- Export simulator-ready guidance and formats.
- Produce PVTO, PVTG, Eclipse, and CMG-style outputs when data are available.

Language rules:
- If the user writes Arabic, answer in Arabic.
- If the user writes English, answer in English.
- If the user mixes Arabic and English, answer in the same mixed style.
- Use correct petroleum engineering terminology.

Adaptive engineering philosophy:
- No rigid templates.
- Adapt to fluid type.
- Adapt to reservoir type.
- Adapt to available data.
- Adapt to simulation objectives.
- Adapt to report scope.
- Adapt to client requirements.
- Treat reference reports as examples, not laws.

Commands:

/analyze
Analyze provided text, PDF context, or engineering data.
Identify:
- Sample type.
- Fluid system.
- Suitable tests.
- Missing data.
- Possible calculations.
- Possible plots.
- Engineering observations.
- Optional improvements.

/report
Write a professional PVT report or report section.
Do not only fill blanks.
Use engineering judgment.
Use provided data only.
Do not invent real values.
If data are missing, state what is missing.
If the user asks for sample values, clearly write: SAMPLE DATA FOR DEMONSTRATION ONLY.

/calc
Perform calculations step by step:
Given Data
Formula
Substitution
Calculation
Final Answer
Engineering Interpretation

/plot
Generate and/or interpret graph data if numerical arrays are provided.
If image plotting is generated by the code, also interpret the trend.

/graph
Analyze the latest uploaded image or graph.
Interpret axes, trend, anomalies, fluid behavior, engineering meaning, possible causes, and recommendations.

/interpret_graph
Same as /graph.

/check
Review whether available data are sufficient for a real PVT report.
List:
Available data
Missing data
Suitable tests
Limitations
Recommendations

/export_sim
Create simulator export guidance.
Decide whether black-oil or compositional simulation is more suitable based on data.

/pvto
Generate Eclipse-style PVTO guidance/table if data are available.
If data are missing, list exactly what is required.

/pvtg
Generate Eclipse-style PVTG guidance/table if data are available.
If data are missing, list exactly what is required.

/eclipse
Explain or generate Eclipse-compatible PVT formatting based on available data.

/cmg
Explain or generate CMG-ready PVT formatting based on available data.

Formatting rules:
- Do not use markdown symbols like **, ###, or vertical-line tables.
- Write clean plain text suitable for Telegram.
- Use clear section titles.
- Avoid unnecessary long paragraphs.
- Be practical, human, and professional.
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

def send_photo(chat_id, photo_path, caption=""):
    with open(photo_path, "rb") as photo:
        requests.post(
            f"{TELEGRAM_URL}/sendPhoto",
            data={"chat_id": chat_id, "caption": caption},
            files={"photo": photo}
        )

def ask_ai(user_text, file_context=None):
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": GLOBAL_PVT_REFERENCE}
    ]

    if file_context:
        messages.append({
            "role": "user",
            "content": "Extra uploaded PVT report context for this chat only:\n\n" + file_context[:25000]
        })

    messages.append({"role": "user", "content": user_text})

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": TEXT_MODEL,
        "messages": messages,
        "temperature": 0.20,
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

def encode_image_to_data_url(file_path):
    mime_type, _ = mimetypes.guess_type(file_path)
    if not mime_type:
        mime_type = "image/jpeg"

    with open(file_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")

    return f"data:{mime_type};base64,{b64}"

def ask_vision_ai(prompt, image_path, file_context=None):
    image_data_url = encode_image_to_data_url(image_path)

    full_prompt = (
        SYSTEM_PROMPT
        + "\n\n"
        + GLOBAL_PVT_REFERENCE
        + "\n\n"
        + "Graph Interpretation Task:\n"
        + prompt
    )

    if file_context:
        full_prompt += "\n\nExtra report context:\n" + file_context[:12000]

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": full_prompt},
                {"type": "image_url", "image_url": {"url": image_data_url}}
            ]
        }
    ]

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": VISION_MODEL,
        "messages": messages,
        "temperature": 0.20,
        "max_tokens": 2500
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
    if not suffix:
        suffix = ".bin"

    temp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    temp.close()

    file_data = requests.get(file_url, timeout=60).content

    with open(temp.name, "wb") as f:
        f.write(file_data)

    return temp.name

def handle_document(chat_id, document):
    file_id = document["file_id"]
    file_name = document.get("file_name", "uploaded_file")
    mime_type = document.get("mime_type", "")

    try:
        local_path = download_telegram_file(file_id, file_name)

        lower_name = file_name.lower()

        if lower_name.endswith(".pdf"):
            extracted_text = extract_pdf_text(local_path)

            if not extracted_text:
                send_message(chat_id, "قرأت ملف PDF لكن ما قدرتش نستخرج نص واضح. ممكن يكون سكان صورة. ارسلي صورة الرسم أو التقرير كصورة للتحليل البصري.")
                return

            FILE_CONTEXT[chat_id] = extracted_text

            send_message(
                chat_id,
                "تم قراءة PDF بنجاح.\n\n"
                "الملف صار مرجع إضافي لهذه المحادثة.\n\n"
                "جربي:\n"
                "/analyze\n"
                "حلل التقرير وحدد نوع العينة والاختبارات والحسابات والرسومات المطلوبة.\n\n"
                "أو:\n"
                "/report\n"
                "اكتب تقرير PVT حسب نوع العينة والبيانات المتوفرة."
            )
            return

        if lower_name.endswith(".docx"):
            extracted_text = extract_docx_text(local_path)

            if not extracted_text:
                send_message(chat_id, "قرأت ملف DOCX لكن ما لقيتش نص واضح.")
                return

            FILE_CONTEXT[chat_id] = extracted_text

            send_message(
                chat_id,
                "تم قراءة DOCX بنجاح.\n\n"
                "الملف صار مرجع إضافي لهذه المحادثة."
            )
            return

        if mime_type.startswith("image/") or lower_name.endswith((".png", ".jpg", ".jpeg", ".webp")):
            IMAGE_CONTEXT[chat_id] = local_path
            send_message(
                chat_id,
                "تم استلام الصورة بنجاح.\n\n"
                "اكتب:\n"
                "/graph\n"
                "حلل الرسم هندسياً"
            )
            return

        send_message(chat_id, "الملف لازم يكون PDF أو DOCX أو صورة.")

    except Exception as e:
        send_message(chat_id, "صار خطأ أثناء قراءة الملف:\n" + str(e))

def handle_photo(chat_id, photos):
    try:
        best_photo = photos[-1]
        file_id = best_photo["file_id"]
        local_path = download_telegram_file(file_id, "uploaded_graph.jpg")
        IMAGE_CONTEXT[chat_id] = local_path

        send_message(
            chat_id,
            "تم استلام الصورة بنجاح.\n\n"
            "اكتب:\n"
            "/graph\n"
            "حلل الرسم هندسياً وحدد السلوك والملاحظات"
        )

    except Exception as e:
        send_message(chat_id, "صار خطأ أثناء تحميل الصورة:\n" + str(e))

def parse_numbers_list(text, key):
    pattern = key + r"\s*=\s*\[([^\]]+)\]"
    match = re.search(pattern, text, re.IGNORECASE)

    if not match:
        return None

    values = match.group(1)
    numbers = []

    for item in values.split(","):
        try:
            numbers.append(float(item.strip()))
        except:
            pass

    return numbers

def try_generate_plot(chat_id, text):
    pressure = parse_numbers_list(text, "Pressure")

    properties = [
        ("Bo", "Oil Formation Volume Factor"),
        ("Rs", "Solution Gas Oil Ratio"),
        ("Density", "Fluid Density"),
        ("Viscosity", "Oil Viscosity"),
        ("RelativeVolume", "Relative Volume"),
        ("YFunction", "Y-Function"),
        ("Z", "Gas Deviation Factor"),
        ("Bg", "Gas Formation Volume Factor"),
        ("LiquidDropout", "Liquid Dropout"),
        ("CGR", "Condensate Gas Ratio")
    ]

    if not pressure:
        return False

    selected_key = None
    selected_label = None
    selected_values = None

    for key, label in properties:
        values = parse_numbers_list(text, key)
        if values and len(values) == len(pressure):
            selected_key = key
            selected_label = label
            selected_values = values
            break

    if not selected_values:
        return False

    fig, ax = plt.subplots()
    ax.plot(pressure, selected_values, marker="o")
    ax.set_xlabel("Pressure")
    ax.set_ylabel(selected_label)
    ax.set_title("Pressure vs " + selected_label)
    ax.grid(True)

    image_path = tempfile.NamedTemporaryFile(delete=False, suffix=".png").name
    plt.savefig(image_path, dpi=200, bbox_inches="tight")
    plt.close(fig)

    send_photo(chat_id, image_path, "Graph generated: Pressure vs " + selected_label)
    IMAGE_CONTEXT[chat_id] = image_path
    return True

def is_graph_command(text):
    t = text.lower().strip()
    return (
        t.startswith("/graph") or
        t.startswith("/interpret_graph") or
        t.startswith("/interpret graph")
    )

def is_plot_command(text):
    return text.lower().strip().startswith("/plot")

def is_export_command(text):
    t = text.lower().strip()
    return (
        t.startswith("/export_sim") or
        t.startswith("/pvto") or
        t.startswith("/pvtg") or
        t.startswith("/eclipse") or
        t.startswith("/cmg")
    )

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
                continue

            text = message["text"]
            context = FILE_CONTEXT.get(chat_id)

            if text == "/start":
                reply = (
                    "أهلاً بك في PVT Lab AI Bot.\n\n"
                    "أنا مساعد هندسي لتقارير PVT والمحاكاة.\n\n"
                    "أقدر:\n"
                    "- نقرأ PDF و DOCX\n"
                    "- نحلل صور ورسومات PVT\n"
                    "- نحدد نوع العينة\n"
                    "- نحدد الاختبارات المناسبة\n"
                    "- نكتب تقرير PVT احترافي\n"
                    "- نحسب القيم من البيانات\n"
                    "- نرسم منحنيات PVT\n"
                    "- نفسر المنحنيات هندسياً\n"
                    "- نجهز PVTO / PVTG / Eclipse / CMG guidance\n\n"
                    "الأوامر:\n"
                    "/analyze\n"
                    "/report\n"
                    "/calc\n"
                    "/plot\n"
                    "/graph\n"
                    "/interpret_graph\n"
                    "/check\n"
                    "/export_sim\n"
                    "/pvto\n"
                    "/pvtg\n"
                    "/eclipse\n"
                    "/cmg"
                )
                send_message(chat_id, reply)
                continue

            if is_graph_command(text):
                image_path = IMAGE_CONTEXT.get(chat_id)

                if not image_path:
                    send_message(chat_id, "ارسلي صورة الرسم أو Figure أولاً، وبعدها اكتبي /graph.")
                    continue

                prompt = (
                    text + "\n\n"
                    "Analyze this engineering graph professionally. "
                    "Identify graph type, axes, trend, anomalies, non-physical behavior, "
                    "retrograde behavior if applicable, contamination indicators, separator performance issues, "
                    "engineering meaning, possible causes, and recommendations."
                )

                reply = ask_vision_ai(prompt, image_path, context)
                send_message(chat_id, reply)
                continue

            if is_plot_command(text):
                plotted = try_generate_plot(chat_id, text)
                reply = ask_ai(text, context)
                send_message(chat_id, reply)
                continue

            if is_export_command(text):
                export_prompt = (
                    text + "\n\n"
                    "Generate simulator export guidance or formatting. "
                    "Adapt to fluid type and data availability. "
                    "Include unit validation, consistency checks, simulator warnings, "
                    "black-oil vs compositional decision, Eclipse/CMG keyword guidance, "
                    "and missing required data if needed."
                )
                reply = ask_ai(export_prompt, context)
                send_message(chat_id, reply)
                continue

            reply = ask_ai(text, context)
            send_message(chat_id, reply)

    except Exception as e:
        print(e)

    time.sleep(1)
