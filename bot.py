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

# تم تحديث الموديل لتجنب مشاكل الـ Rate Limit
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

الأوامر:
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
فحص حالة العينات، التسريب، ضغط العينة، وتمثيلية العينة.

2. Compositional Analysis
تحليل تركيبي للغاز والزيت، مع توصيف C7+ أو C12+ حسب نظام المختبر.

3. Recombination
إعادة تركيب زيت الفاصل مع غاز الفاصل باستخدام Producing GOR أو معدلات الزيت والغاز وظروف الفاصل.

4. Validation of Recombined Fluid
التأكد من أن العينة المعاد تركيبها مستقرة وتمثل سائل المكمن بشكل مقبول.

5. CCE أو CME
لتحديد ضغط التشبع وسلوك الحجم مع الضغط.

6. DV Differential Vaporization
إذا كان النظام Black Oil أو Volatile Oil، للحصول على Rs و Bo والكثافة واللزوجة.

7. CVD Constant Volume Depletion
إذا كان النظام Gas Condensate، لدراسة Liquid Dropout و Dew Point و CGR.

8. Separator Test
لتقييم تأثير ظروف الفاصل على GOR و Stock Tank Oil و API و shrinkage.

9. Viscosity Test
لقياس لزوجة الزيت والغاز عند الحاجة.

الحسابات الممكنة عند توفر البيانات

- Recombination Ratio.
- Total GOR.
- Rs نسبة الغاز المذاب.
- Bo معامل حجم التكوين للزيت.
- Bg معامل حجم التكوين للغاز.
- Z-factor.
- Oil Density.
- API Gravity.
- Oil Viscosity.
- Gas Viscosity.
- Compressibility.
- Y-Function.

المنحنيات المطلوبة

- Pressure vs Bo.
- Pressure vs Rs.
- Pressure vs Oil Viscosity.
- Pressure vs Density.
- Pressure vs Relative Volume.
- Pressure vs Y-Function.
- للغاز المكثف: Pressure vs Liquid Dropout و Pressure vs CGR.

إعداد المحاكاة

إذا كان السائل Black Oil:
تستخدم بيانات DV و Separator Test لتجهيز PVTO في Eclipse، بشرط توفر Pressure و Rs و Bo و Oil Viscosity.

إذا كان السائل Gas Condensate أو Volatile Oil:
الأفضل استخدام Compositional Model مع EOS Tuning في CMG أو Eclipse Compositional.

الخلاصة

الخطوة الصحيحة ليست اعتبار عينات السطح ممثلة مباشرة للمكمن، بل إجراء Recombination ثم اختبارات PVT المناسبة. بدون بيانات الفاصل و GOR والتركيب لا يمكن حساب قيم نهائية موثوقة مثل Bo أو Rs أو Bubble Point Pressure.
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
                send_message(chat_id, "أرسلي نصاً أو ملف PDF/DOCX أو صورة.")
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
                    send_message(chat_id, "أرسلي صورة الرسم أو Figure أولاً، وبعدها اكتبي /graph.")
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

