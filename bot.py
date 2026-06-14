"""
PVT Lab AI Bot — Final Professional Version
Critical Bo vs Pressure rules added.
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

if not TELEGRAM_BOT_TOKEN or not GROQ_API_KEY:
    raise ValueError("Missing env vars: TELEGRAM_BOT_TOKEN or OPENAI_API_KEY")

TELEGRAM_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
TEXT_MODEL = os.getenv("GROQ_TEXT_MODEL", "llama-3.3-70b-versatile")
VISION_MODEL = os.getenv("GROQ_VISION_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")

offset = 0
FILE_CONTEXT = {}
IMAGE_CONTEXT = {}

SYSTEM_PROMPT = """
You are a professional Petroleum Engineering, PVT Laboratory, Reservoir Fluid Analysis,
and Reservoir Simulation assistant. Answer like a real PVT laboratory engineer, not a generic chatbot.

Language rules:
- Arabic message -> answer in strong professional Arabic.
- English message -> answer in professional petroleum engineering English.
- Mixed -> match the user style naturally.
- Keep key technical terms in English beside Arabic when useful.
- Do not force weak Arabic translation. If the Arabic wording sounds uncommon, keep the English technical term.

Preferred technical terms:
PVT = Pressure-Volume-Temperature.
Reservoir = المكمن.
Well = البئر.
Formation = التكوين.
Bottom Hole Sample = عينة قاع البئر.
Surface Separator Oil Sample = عينة زيت من الفاصل السطحي.
Separator Gas Sample = عينة غاز من الفاصل.
Recombination = إعادة تركيب العينة.
Bubble Point Pressure = ضغط نقطة الفقاعة.
Dew Point Pressure = ضغط نقطة الندى.
Bo = Oil Formation Volume Factor.
Bg = Gas Formation Volume Factor.
Rs = Solution Gas-Oil Ratio.
GOR = Gas-Oil Ratio.
CGR = Condensate-Gas Ratio.
Z-factor = Gas Deviation Factor.
Viscosity.
Density.
Specific Gravity.
API Gravity.
CCE = Constant Composition Expansion.
CME = Constant Mass Expansion.
DV = Differential Vaporization / Differential Liberation.
CVD = Constant Volume Depletion.
Separator Test.
Flash Test.
Compositional Analysis.
EOS Tuning.
PVTO.
PVTG.
Black Oil Model.
Compositional Model.
Eclipse.
CMG.

Strict engineering rules:
- Do not invent numerical PVT values unless the user clearly asks for demo data.
- Do not create fake lab tables as if they are real.
- Calculations require real input values.
- If data are missing, list exactly what is missing.
- Use engineering judgment, not generic textbook lists.

Answer structure:
1. Identify sample type or question category.
2. Identify fluid system when possible: Black Oil, Volatile Oil, Gas Condensate, Dry Gas.
3. Select correct workflow.
4. Explain required lab tests or engineering steps.
5. Show calculations only if real input data are provided.
6. List required plots if applicable.
7. Mention simulation relevance: Eclipse / CMG when applicable.
8. State missing data clearly.
9. Give concise engineering interpretation.

Surface Separator logic:
- Surface Separator Oil + Gas samples are not direct reservoir fluid.
- Always recommend Recombination first when reservoir-fluid behavior is required.
- Required: Separator Pressure, Separator Temperature, Oil Rate, Gas Rate, GOR, gas composition, oil composition, API Gravity, Gas Specific Gravity, Water Cut, H2S/CO2 if present.

Critical PVT plot rules:

For Black Oil systems:

Bo versus Pressure:
- Bo reaches its maximum value at Bubble Point Pressure Pb.
- Below Pb, Bo decreases as pressure decreases because gas is liberated from oil.
- Above Pb, Bo changes only slightly and generally decreases as pressure increases due to oil compressibility.
- Never say that Pb is the minimum Bo point.
- Never say that Bo continuously increases with pressure.

Rs versus Pressure:
- Rs increases with pressure below Pb.
- Rs becomes constant above Pb because the oil is undersaturated.
- Never say Rs keeps increasing above Pb.

Oil Viscosity versus Pressure:
- Below Pb, oil viscosity generally increases as pressure decreases because dissolved gas leaves the oil.
- Above Pb, viscosity may increase slightly with pressure depending on compressibility and fluid type.

Bg versus Pressure:
- Bg generally decreases as pressure increases.
- Bg generally increases as pressure decreases.

Z-factor:
- Z-factor is not always greater than 1 at high pressure.
- Z may be less than 1 or greater than 1 depending on pressure, temperature, and gas composition.
- Near atmospheric conditions, Z approaches 1.

Graph answer rule:
When the user asks for a sketch or plot only, give the plot first and keep explanation very short.
For ASCII sketches, make the axes clear and put Pb or Pd in the correct location.

Formatting:
- No markdown ** or ###.
- No vertical-line tables.
- Clean plain text with clear section headings.
- Be concise, direct, professional.
"""

def clean_text(text: str) -> str:
    text = str(text)
    fixes = {
        "**": "", "###": "", "##": "", "#": "", "|": " ", "[": "", "]": "",
        "Pressuring Volume and Temperature": "Pressure-Volume-Temperature",
        "Volume Expansion Factor": "Oil Formation Volume Factor",
        "الضغط البيني": "Oil Formation Volume Factor Bo",
        "المعامل البيني": "Oil Formation Volume Factor Bo",
        "الترشيح": "Solution Gas-Oil Ratio Rs",
        "النسبة المئوية للغاز": "Gas-Oil Ratio GOR",
        "نسبة الغاز المئوية": "Gas-Oil Ratio GOR",
        "الويسكوزية": "Viscosity",
        "الویسكوزية": "Viscosity",
        "الليزج": "Viscosity",
        "الحفرة": "Reservoir",
        "السطوح النوعي": "Specific Gravity",
        "اختبار السطوح": "Specific Gravity Measurement",
        "السطوع النوعي": "Specific Gravity",
        "اختبار السطوع": "Specific Gravity Measurement",
        "نحو PVT": "PVT curves",
    }
    for wrong, right in fixes.items():
        text = text.replace(wrong, right)
    return text.strip()

def handle_calculation(query: str):
    q = query.lower()
    nums = [float(x) for x in re.findall(r"[-+]?\d*\.?\d+", query) if x]

    if "api" in q and any(k in q for k in ["sg", "specific gravity", "gravity"]):
        if nums:
            sg = nums[0]
            if 0.5 < sg < 1.5:
                api = (141.5 / sg) - 131.5
                cls = "Light Oil" if api > 35 else "Medium Oil" if api > 22 else "Heavy Oil"
                return f"حساب API Gravity\n\nFormula: API = (141.5 / SG) - 131.5\nSpecific Gravity = {sg}\nResult = {api:.2f} API\nClassification = {cls}"

    if "hydrostatic" in q or ("pressure" in q and any(k in q for k in ["mw", "mud", "tvd"])):
        if len(nums) >= 2:
            mw, tvd = nums[0], nums[1]
            hp = 0.052 * mw * tvd
            return f"حساب Hydrostatic Pressure\n\nFormula: P = 0.052 x MW x TVD\nMW = {mw} ppg\nTVD = {tvd} ft\nResult = {hp:.2f} psi"

    if "ooip" in q:
        if len(nums) >= 5:
            a, h, phi, sw, bo = nums[0], nums[1], nums[2], nums[3], nums[4]
            ooip = (7758 * a * h * phi * (1 - sw)) / bo
            return f"حساب OOIP\n\nFormula: OOIP = (7758 x A x h x phi x (1-Sw)) / Bo\nArea = {a} acres\nh = {h} ft\nphi = {phi}\nSw = {sw}\nBo = {bo}\nResult = {ooip:,.0f} STB"
        return "لحساب OOIP احتاج 5 قيم:\nExample: /calc ooip 500 50 0.2 0.3 1.3\nA acres, h ft, porosity, Sw, Bo"

    if "darcy" in q or "flow rate" in q:
        if len(nums) >= 5:
            k, a, dp, mu, l = nums[0], nums[1], nums[2], nums[3], nums[4]
            q_rate = (0.001127 * k * a * dp) / (mu * l)
            return f"حساب Darcy Linear Flow\n\nFormula: q = 0.001127 x k x A x dP / (mu x L)\nk = {k} mD\nA = {a} ft2\ndP = {dp} psi\nmu = {mu} cP\nL = {l} ft\nResult = {q_rate:.4f} bbl/day"

    if "recovery" in q or " rf " in q:
        if len(nums) >= 2:
            np_v, ooip_v = nums[0], nums[1]
            rf = (np_v / ooip_v) * 100
            return f"حساب Recovery Factor\n\nFormula: RF = NP / OOIP x 100\nNP = {np_v:,.0f}\nOOIP = {ooip_v:,.0f}\nResult = RF = {rf:.2f}%"

    if "water cut" in q or "wc" in q:
        if len(nums) >= 2:
            qw, qo = nums[0], nums[1]
            wc = (qw / (qo + qw)) * 100
            return f"حساب Water Cut\n\nFormula: WC = qw / (qo + qw) x 100\nqw = {qw}\nqo = {qo}\nResult = WC = {wc:.2f}%"

    return None

GLOSSARY_HTML = r"""<!DOCTYPE html><html lang="ar" dir="rtl"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>Petroleum Glossary</title><style>body{font-family:Arial,sans-serif;background:#f7f2e8;color:#1f1f1f;line-height:1.8;padding:20px}h1{color:#3d1f00;text-align:center}.card{background:white;border:1px solid #ddd0b8;border-radius:10px;padding:14px;margin:10px 0}.en{direction:ltr;color:#c8760a;font-weight:bold}.eq{direction:ltr;background:#111827;color:#facc15;padding:10px;border-radius:8px;margin-top:8px}</style></head><body><h1>المصطلحات النفطية — Petroleum Glossary</h1><div class="card"><div class="en">Bo — Oil Formation Volume Factor</div><div>معامل حجم التكوين للزيت. يصل عادة إلى أعلى قيمة عند Bubble Point Pressure.</div></div><div class="card"><div class="en">Rs — Solution Gas-Oil Ratio</div><div>كمية الغاز المذاب في الزيت عند ضغط ودرجة حرارة محددين.</div></div><div class="card"><div class="en">GOR — Gas-Oil Ratio</div><div>نسبة الغاز المنتج إلى الزيت المنتج.</div></div><div class="card"><div class="en">Bg — Gas Formation Volume Factor</div><div>معامل حجم التكوين للغاز.</div></div><div class="card"><div class="en">Z-factor — Gas Deviation Factor</div><div>معامل يصف انحراف الغاز الحقيقي عن الغاز المثالي.</div></div><div class="card"><div class="en">Bubble Point Pressure</div><div>ضغط نقطة الفقاعة، يبدأ عنده الغاز المذاب بالخروج من الزيت.</div></div><div class="card"><div class="en">Dew Point Pressure</div><div>ضغط نقطة الندى، يبدأ عنده السائل بالتكون من الغاز.</div></div><h2>معادلات مهمة</h2><div class="card"><div class="en">API Gravity</div><div class="eq">API = (141.5 / SG) - 131.5</div></div><div class="card"><div class="en">Hydrostatic Pressure</div><div class="eq">P = 0.052 x MW x TVD</div></div><div class="card"><div class="en">OOIP</div><div class="eq">OOIP = (7758 x A x h x phi x (1-Sw)) / Bo</div></div></body></html>"""

def send_message(chat_id: int, text: str) -> None:
    text = clean_text(text)
    if not text:
        text = "لم أتمكن من توليد رد واضح."
    for i in range(0, len(text), 3900):
        try:
            requests.post(f"{TELEGRAM_URL}/sendMessage", json={"chat_id": chat_id, "text": text[i:i+3900]}, timeout=15)
        except Exception as e:
            print(f"send_message error: {e}")
        time.sleep(0.4)

def send_document(chat_id: int, file_bytes: bytes, filename: str, caption: str) -> None:
    try:
        requests.post(f"{TELEGRAM_URL}/sendDocument", data={"chat_id": chat_id, "caption": caption}, files={"document": (filename, file_bytes, "text/html")}, timeout=20)
    except Exception as e:
        send_message(chat_id, f"خطأ في إرسال الملف: {e}")

def download_file(file_id: str, suffix: str = ".bin"):
    try:
        info = requests.get(f"{TELEGRAM_URL}/getFile", params={"file_id": file_id}, timeout=15).json()
        if not info.get("ok"):
            return None
        url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{info['result']['file_path']}"
        data = requests.get(url, timeout=60).content
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        tmp.write(data)
        tmp.close()
        return tmp.name
    except Exception as e:
        print(f"download_file error: {e}")
        return None

def extract_pdf_text(path: str) -> str:
    try:
        reader = PdfReader(path)
        return "\n\n".join(p.extract_text() for p in reader.pages if p.extract_text()).strip()
    except Exception as e:
        print(f"PDF error: {e}")
        return ""

def extract_docx_text(path: str) -> str:
    try:
        doc = Document(path)
        return "\n".join(p.text.strip() for p in doc.paragraphs if p.text.strip())
    except Exception as e:
        print(f"DOCX error: {e}")
        return ""

def encode_image(path: str) -> str:
    mime, _ = mimetypes.guess_type(path)
    if not mime:
        mime = "image/jpeg"
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return f"data:{mime};base64,{b64}"

def ask_ai(user_text: str, file_context=None) -> str:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if file_context:
        messages.append({"role": "user", "content": "Reference document context:\n\n" + file_context[:18000]})
    messages.append({"role": "user", "content": user_text})
    try:
        r = requests.post(GROQ_URL, headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}, json={"model": TEXT_MODEL, "messages": messages, "temperature": 0.08, "max_tokens": 2000}, timeout=90)
        data = r.json()
        if "choices" in data:
            return data["choices"][0]["message"]["content"]
        return "خطأ من Groq:\n" + str(data)[:800]
    except Exception as e:
        return f"خطأ في الاتصال بالذكاء الاصطناعي:\n{e}"

def ask_vision_ai(prompt: str, image_path: str, file_context=None) -> str:
    full_prompt = SYSTEM_PROMPT + "\n\nTask:\n" + prompt
    if file_context:
        full_prompt += "\n\nReference context:\n" + file_context[:8000]
    messages = [{"role": "user", "content": [{"type": "text", "text": full_prompt}, {"type": "image_url", "image_url": {"url": encode_image(image_path)}}]}]
    try:
        r = requests.post(GROQ_URL, headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}, json={"model": VISION_MODEL, "messages": messages, "temperature": 0.08, "max_tokens": 1200}, timeout=90)
        data = r.json()
        if "choices" in data:
            return data["choices"][0]["message"]["content"]
        return "خطأ من Groq Vision:\n" + str(data)[:800]
    except Exception as e:
        return f"خطأ في تحليل الصورة:\n{e}"

def handle_document_upload(chat_id, doc):
    file_id = doc["file_id"]
    file_name = doc.get("file_name", "file")
    mime = doc.get("mime_type", "")
    ext = os.path.splitext(file_name)[1].lower() or ".bin"
    path = download_file(file_id, ext)
    if not path:
        send_message(chat_id, "حدث خطأ أثناء تحميل الملف.")
        return
    lower = file_name.lower()
    if lower.endswith(".pdf"):
        text = extract_pdf_text(path)
        if not text:
            send_message(chat_id, "قرأت PDF لكن لم أستخرج نصاً واضحاً. الملف غالباً سكان صورة. أرسل صفحاته كصور أو ارفع PDF نصي.")
            return
        FILE_CONTEXT[chat_id] = text
        send_message(chat_id, "تم قراءة PDF بنجاح. الملف أصبح مرجعاً لهذه المحادثة.\nاكتب /analyze لتحليله هندسياً.")
    elif lower.endswith(".docx"):
        text = extract_docx_text(path)
        if not text:
            send_message(chat_id, "قرأت DOCX لكن لم أجد نصاً.")
            return
        FILE_CONTEXT[chat_id] = text
        send_message(chat_id, "تم قراءة DOCX بنجاح. اكتب /analyze للتحليل.")
    elif mime.startswith("image/") or lower.endswith((".png", ".jpg", ".jpeg", ".webp")):
        IMAGE_CONTEXT[chat_id] = path
        send_message(chat_id, "تم استلام الصورة. اكتب /graph لتحليل الرسم هندسياً.")
    else:
        send_message(chat_id, "الملف المدعوم: PDF أو DOCX أو صورة PNG/JPG/JPEG/WEBP.")

def handle_photo_upload(chat_id, photos):
    path = download_file(photos[-1]["file_id"], ".jpg")
    if path:
        IMAGE_CONTEXT[chat_id] = path
        send_message(chat_id, "تم استلام الصورة. اكتب /graph لتحليل الرسم هندسياً.")
    else:
        send_message(chat_id, "خطأ في تحميل الصورة.")

def is_graph_cmd(t):
    return t.lower().startswith(("/graph", "/interpret_graph"))

def is_export_cmd(t):
    return t.lower().startswith(("/export_sim", "/pvto", "/pvtg", "/eclipse", "/cmg"))

def is_plot_cmd(t):
    return t.lower().startswith("/plot")

def is_analyze_cmd(t):
    return t.lower().startswith("/analyze")

def is_calc_cmd(t):
    return t.lower().startswith("/calc")

def is_check_cmd(t):
    return t.lower().startswith("/check")

def is_surface_separator(t):
    t = t.lower()
    oil = any(k in t for k in ["surface separator oil", "separator oil", "زيت من الفاصل", "عينة زيت"])
    gas = any(k in t for k in ["separator gas", "غاز من الفاصل", "عينة غاز"])
    return oil and gas

def start_message() -> str:
    return """أهلاً بك في PVT Lab AI Bot

أنا مساعد هندسي متخصص في:
- PVT Laboratory and Reservoir Fluid Analysis
- Reservoir Simulation (Eclipse / CMG)
- Drilling Engineering
- PDF/DOCX Report Analysis
- Graph and Figure Interpretation

الأوامر المتاحة:

/glossary    — المصطلحات النفطية
/calc        — حسابات هندسية سريعة
  /calc API for SG 0.85
  /calc hydrostatic mw 10 tvd 5000
  /calc ooip 500 50 0.2 0.3 1.3
  /calc water cut qw 800 qo 200
  /calc recovery np 5000000 ooip 20000000
/analyze     — تحليل تقرير PDF/DOCX مرفوع
/graph       — تحليل رسم بياني أو صورة هندسية
/plot        — توجيه رسومات PVT
/check       — فحص بيانات PVT
/export_sim  — تصدير بيانات للمحاكاة
/pvto        — جدول PVTO لـ Eclipse
/pvtg        — جدول PVTG لـ Eclipse
/eclipse     — إرشادات Eclipse
/cmg         — إرشادات CMG

يمكنك كتابة سؤالك مباشرة بالعربي أو الإنجليزي."""

def surface_separator_answer() -> str:
    return """تحليل هندسي — عينة زيت من الفاصل السطحي مع عينة غاز

نوع العينات
هذه عينات سطحية منفصلة وليست سائل مكمن مباشراً مثل Bottom Hole Sample.
الزيت والغاز انفصلا عند ظروف الفاصل السطحي لذلك يلزم Recombination أولاً.

البيانات المطلوبة
- Separator Pressure و Temperature
- Oil Rate و Gas Rate
- Producing GOR أو Separator GOR
- Gas Composition و Oil/Stock Tank Oil Composition
- API Gravity و Gas Specific Gravity
- Water Cut و وجود H2S/CO2

الاختبارات المطلوبة
1. Sample QC — فحص سلامة العينات
2. Compositional Analysis — تحليل تركيبي كامل
3. Recombination — إعادة بناء سائل المكمن
4. Validation — التحقق من تمثيلية العينة المعاد تركيبها
5. CCE/CME — لتحديد Saturation Pressure وسلوك الحجم
6. DV للزيت أو CVD للغاز المكثف
7. Separator Test و Viscosity Test

الرسومات المطلوبة
- Pressure vs Bo
- Pressure vs Rs
- Pressure vs Oil Viscosity
- Pressure vs Relative Volume / Y-Function
- للغاز المكثف: Pressure vs Liquid Dropout

إعداد المحاكاة
Black Oil: PVTO في Eclipse يحتاج Bo و Rs و Viscosity عند كل ضغط.
Gas Condensate / Volatile Oil: Compositional Model مع EOS Tuning.

الخلاصة
لا يمكن حساب Bo أو Rs أو Bubble Point بدون بيانات الفاصل والتركيب.
أرسل البيانات وسأبدأ الحسابات مباشرة."""

print("PVT Lab AI Bot running...")

while True:
    try:
        updates = requests.get(f"{TELEGRAM_URL}/getUpdates", params={"offset": offset + 1, "timeout": 30}, timeout=40).json()
        for update in updates.get("result", []):
            offset = update["update_id"]
            msg = update.get("message")
            if not msg:
                continue
            chat_id = msg["chat"]["id"]
            if "document" in msg:
                handle_document_upload(chat_id, msg["document"])
                continue
            if "photo" in msg:
                handle_photo_upload(chat_id, msg["photo"])
                continue
            if "text" not in msg:
                send_message(chat_id, "أرسل نصاً أو ملف PDF/DOCX أو صورة.")
                continue
            text = msg["text"].strip()
            context = FILE_CONTEXT.get(chat_id)
            if text == "/start":
                send_message(chat_id, start_message())
                continue
            if text == "/glossary":
                send_document(chat_id, GLOSSARY_HTML.encode("utf-8"), "petroleum_glossary.html", "المصطلحات النفطية الشاملة")
                continue
            if is_calc_cmd(text):
                query = text[5:].strip()
                result = handle_calculation(query)
                if result:
                    send_message(chat_id, result)
                else:
                    send_message(chat_id, "لم أتعرف على الحساب. أمثلة:\n\n/calc API for SG 0.85\n/calc hydrostatic mw 10 tvd 5000\n/calc ooip 500 50 0.2 0.3 1.3\n/calc darcy 50 100 200 2 500\n/calc recovery 5000000 20000000\n/calc water cut 800 200")
                continue
            if is_analyze_cmd(text):
                if not context:
                    send_message(chat_id, "لا يوجد ملف مرفوع. أرسل PDF أو DOCX أولاً.")
                    continue
                prompt = "قم بتحليل هذا التقرير الهندسي:\n1. نوع العينة ونظام السائل\n2. الاختبارات المنفذة وجودتها\n3. القيم الرئيسية Pb, Bo, Rs, API, Viscosity\n4. انتقادات أو مشاكل في البيانات\n5. توصيات للمحاكاة\n6. الخلاصة الهندسية"
                send_message(chat_id, ask_ai(prompt, context))
                continue
            if is_graph_cmd(text):
                img = IMAGE_CONTEXT.get(chat_id)
                if not img:
                    send_message(chat_id, "أرسل صورة الرسم أولاً ثم اكتب /graph.")
                    continue
                prompt = text + "\n\nحلل هذا الرسم الهندسي النفطي:\n- حدد المحاور والوحدات\n- فسر الاتجاه العام\n- اكشف أي سلوك غير طبيعي\n- اذكر أي ظاهرة Retrograde إن وجدت\n- أعط التفسير الهندسي والتوصيات"
                send_message(chat_id, ask_vision_ai(prompt, img, context))
                continue
            if is_plot_cmd(text):
                prompt = text + "\n\nThe user is asking for a PVT plot or sketch. Use correct petroleum engineering trends. For Bo vs Pressure, Bo must peak at Bubble Point Pressure Pb. Below Pb, Bo decreases as pressure decreases. Above Pb, Bo changes slightly and generally decreases as pressure increases. Do not say Pb is minimum Bo. If the user asks for drawing only, provide a simple ASCII sketch first, then very short notes. If data are missing, say it is a schematic plot only."
                send_message(chat_id, ask_ai(prompt, context))
                continue
            if is_check_cmd(text):
                prompt = text + "\n\nافحص البيانات المقدمة هندسياً:\n- تحقق من المنطقية والاتساق\n- حدد أي قيم غير طبيعية أو مشبوهة\n- اذكر البيانات الناقصة\n- أعط توصيات التصحيح"
                send_message(chat_id, ask_ai(prompt, context))
                continue
            if is_export_cmd(text):
                prompt = text + "\n\nقدم توجيهات تصدير المحاكاة:\n- حدد نوع النموذج Black Oil / Compositional\n- الكلمات المفتاحية المطلوبة في Eclipse/CMG\n- تحقق من الوحدات والاتساق\n- اذكر البيانات الناقصة"
                send_message(chat_id, ask_ai(prompt, context))
                continue
            if is_surface_separator(text):
                send_message(chat_id, surface_separator_answer())
                continue
            send_message(chat_id, ask_ai(text, context))
    except Exception as e:
        print(f"Main loop error: {e}")
    time.sleep(1)
