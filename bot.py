import os
import re
import time
import base64
import tempfile
import mimetypes
import requests

from PyPDF2 import PdfReader
from docx import Document

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
GROQ_API_KEY = os.getenv('OPENAI_API_KEY')
TELEGRAM_URL = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}'
GROQ_URL = 'https://api.groq.com/openai/v1/chat/completions'
TEXT_MODEL = os.getenv('GROQ_TEXT_MODEL', 'llama-3.3-70b-versatile')
VISION_MODEL = os.getenv('GROQ_VISION_MODEL', 'meta-llama/llama-4-scout-17b-16e-instruct')

offset = 0
FILE_CONTEXT = {}
IMAGE_CONTEXT = {}

GLOBAL_PVT_REFERENCE = '''
Professional PVT Engineering Reference System

Role: act as a real PVT laboratory engineer, reservoir fluid specialist, and reservoir simulation engineer.
The reference report is an example for workflow and style only. It is not a rigid template.
Always adapt to sample type, fluid system, reservoir type, available data, lab objective, report scope, client requirements, and simulation objective.

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
Rv = نسبة الزيت المتبخر في الغاز Vaporized Oil-Gas Ratio.
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
PVTO = Eclipse black-oil oil PVT table.
PVTG = Eclipse gas PVT table.
CMG PVT Input = مدخلات PVT لمحاكي CMG.

Forbidden terms:
Do not call Bo الضغط البيني or المعامل البيني.
Do not call Rs الترشيح.
Do not call GOR النسبة المئوية للغاز.
Do not say الليزج for Viscosity.
Do not say الحفرة for Reservoir.
Do not say السطوع النوعي or اختبار السطوع.
Do not define PVT as Pressuring Volume and Temperature.
Do not use vague tests like اختبار الضغط والحرارة when actual tests are CCE/CME, DV, CVD, Separator Test, Recombination, Compositional Analysis, or Viscosity Test.

Engineering workflow:
1. Bottom Hole Sample: validation, opening pressure/leak check, restoration to reservoir conditions, CCE/CME, DV for oil systems, CVD for gas condensate, Separator Test, Viscosity, Composition, PVT tables and plots.
2. Surface Separator Oil + Separator Gas: surface separated samples do not directly represent original reservoir fluid. Need separator P/T, oil/gas rates, separator GOR or producing GOR, oil and gas composition, API, density, water/emulsion check. Recombine oil and gas, validate recombined fluid, then run CCE/CME, DV or CVD, Separator Test, Viscosity.
3. Black Oil: Bubble Point Pressure, Rs, Bo, Density, Viscosity, DV/Differential Liberation, Separator Test, Stock Tank Oil API, PVTO.
4. Volatile Oil: saturation pressure, high GOR, shrinkage, composition, separator optimization, likely EOS/compositional simulation.
5. Gas Condensate: Dew Point, CVD, liquid dropout, CGR, Z-factor, retrograde condensation, PVTG or compositional/EOS.

Simulation logic:
Use PVTO for black-oil oil systems with pressure-Rs-Bo-viscosity tables.
Use PVTG for gas systems when gas PVT data are available.
Use compositional/EOS for volatile oil, gas condensate, rich gas, miscibility, CO2/H2S, or strong compositional effects.
DV supports black-oil tables. CVD supports gas condensate and EOS work. Separator conditions affect GOR, Bo, Rs, API and simulator surface conditions.

Graph interpretation:
Identify axes and units, trend, non-physical behavior, anomalies, retrograde behavior, contamination indicators, engineering meaning, causes and recommendations.
'''

SYSTEM_PROMPT = '''
You are a professional Petroleum Engineering and PVT Laboratory AI assistant.
Answer like a real PVT engineer, reservoir fluid specialist, and reservoir simulation engineer.
Never give generic textbook answers. Never invent PVT values. Use engineering judgment.
If Arabic: use strong professional Arabic with correct petroleum terms. If English: use professional petroleum engineering English.

For every technical answer:
1. Identify sample type.
2. Identify likely fluid system.
3. Select correct PVT workflow.
4. Explain required lab tests.
5. Explain calculations only if data are available.
6. Explain required plots.
7. Explain simulation relevance.
8. Mention missing data.
9. Give engineering interpretation.

Commands: /analyze, /report, /calc, /plot, /graph, /interpret_graph, /check, /export_sim, /pvto, /pvtg, /eclipse, /cmg.
Formatting: no markdown symbols like ** or ###, no vertical-line tables, clean Telegram text, clear headings.
'''

def fix_terms(text):
    text = str(text)
    repl = {
        'Pressuring Volume and Temperature': 'Pressure-Volume-Temperature',
        'الضغط البيني': 'معامل حجم التكوين',
        'المعامل البيني': 'معامل حجم التكوين',
        'الترشيح': 'نسبة الغاز المذاب',
        'النسبة المئوية للغاز': 'نسبة الغاز إلى الزيت',
        'نسبة الغاز المئوية': 'نسبة الغاز إلى الزيت',
        'الويسكوزية': 'اللزوجة',
        'الليزج': 'اللزوجة',
        'الحفرة': 'المكمن',
        'السطوع النوعي': 'الكثافة النوعية',
        'اختبار السطوع': 'اختبار الكثافة النوعية',
        'نحو PVT': 'منحنيات PVT',
        'النموذج البيني': 'Black Oil Model أو Compositional Model',
        'النموذج المضغوط': 'Black Oil Model أو Compositional Model',
        'Volume Expansion Factor': 'Oil Formation Volume Factor',
        'Bo (Volume Expansion Factor)': 'Bo معامل حجم التكوين للزيت Oil Formation Volume Factor',
        'Bo Volume Expansion Factor': 'Bo معامل حجم التكوين للزيت Oil Formation Volume Factor',
        'Rs (Solution Gas-Oil Ratio)': 'Rs نسبة الغاز المذاب Solution Gas-Oil Ratio',
        'GOR النسبة': 'GOR نسبة الغاز إلى الزيت',
        'الضغط البالغ': 'ضغط التشبع أو ضغط الاختبار حسب السياق',
        'الحرارة البالغة': 'درجة حرارة المكمن أو درجة حرارة الاختبار حسب السياق',
    }
    for a, b in repl.items():
        text = text.replace(a, b)
    return text

def clean_text(text):
    text = fix_terms(text)
    for s in ['**', '###', '##', '#', '|', '[', ']']:
        text = text.replace(s, ' ' if s == '|' else '')
    return text.strip()

def send_message(chat_id, text):
    text = clean_text(text)
    if len(text) <= 3900:
        requests.post(f'{TELEGRAM_URL}/sendMessage', data={'chat_id': chat_id, 'text': text})
    else:
        for i in range(0, len(text), 3900):
            requests.post(f'{TELEGRAM_URL}/sendMessage', data={'chat_id': chat_id, 'text': text[i:i+3900]})
            time.sleep(0.5)

def send_photo(chat_id, photo_path, caption=''):
    with open(photo_path, 'rb') as photo:
        requests.post(f'{TELEGRAM_URL}/sendPhoto', data={'chat_id': chat_id, 'caption': caption}, files={'photo': photo})

def surface_separator_analysis_ar():
    return '''
تحليل هندسي لعينة زيت من الفاصل السطحي مع عينة غاز من الفاصل

نوع العينات
العينات المذكورة هي عينات سطحية منفصلة:
- Surface Separator Oil Sample: عينة زيت من الفاصل السطحي.
- Separator Gas Sample: عينة غاز من الفاصل.

هذه العينات لا تمثل سائل المكمن الأصلي مباشرة مثل عينة قاع البئر Bottom Hole Sample، لأن الغاز والزيت انفصلا عند ظروف الفاصل السطحي. لذلك لا يمكن بناء سلوك PVT كامل للمكمن منها مباشرة إلا بعد إعادة تركيب العينة Recombination بطريقة صحيحة.

الفكرة الهندسية الأساسية
الهدف هو إعادة بناء سائل المكمن الأصلي تقريبياً من خلال عينة الزيت السطحية، عينة الغاز المنفصل، ظروف الفاصل، ونسبة الغاز إلى الزيت GOR أو معدلات الإنتاج. بعد ذلك تُجرى اختبارات PVT على العينة المعاد تركيبها Recombined Sample.

البيانات المطلوبة
1. بيانات الفاصل السطحي:
- Separator Pressure ضغط الفاصل.
- Separator Temperature درجة حرارة الفاصل.
- عدد مراحل الفصل إن وجدت.
- Stock Tank Conditions إن وجدت.

2. بيانات الإنتاج:
- Oil Rate معدل إنتاج الزيت.
- Gas Rate معدل إنتاج الغاز.
- Producing GOR أو Separator GOR نسبة الغاز إلى الزيت.
- Water Cut أو وجود ماء/مستحلب إن وجد.

3. بيانات العينات:
- حجم عينة الزيت.
- ضغط ودرجة حرارة أخذ العينة.
- Separator Gas Composition تركيب الغاز.
- Stock Tank Oil Composition أو تركيب الزيت.
- Oil Density كثافة الزيت.
- API Gravity.
- Gas Specific Gravity.
- H2S و CO2 إن وجدت.

الاختبارات المطلوبة
1. Compositional Analysis التحليل التركيبي:
تحليل الغاز C1 إلى C7+ مع CO2 و N2 و H2S، وتحليل السائل وتوصيف C7+ أو C12+ حسب المختبر.

2. Recombination إعادة تركيب العينة:
خلط زيت الفاصل مع غاز الفاصل بنسبة مناسبة اعتماداً على Producing GOR أو Separator GOR أو معدلات الزيت والغاز وظروف الفاصل.

3. Validation of Recombined Fluid:
التأكد من استقرار العينة، عدم فقدان الغاز، وتوافق ضغط التشبع المتوقع مع البيانات الحقلية إن وجدت.

4. CCE أو CME:
لتحديد Bubble Point Pressure إذا كان النظام زيتي، أو Dew Point Pressure إذا كان غازياً مكثفاً، مع Relative Volume و Y-Function و Compressibility.

5. DV Differential Vaporization:
مناسب غالباً لـ Black Oil أو Volatile Oil، ويعطي Rs و Bo والكثافة و Gas Gravity و Z-factor و Bg.

6. CVD Constant Volume Depletion:
يستخدم إذا كان النظام Gas Condensate، ويعطي Liquid Dropout و Retrograde Condensation و CGR و Z-factor.

7. Separator Test:
مهم جداً لأن العينة أصلها من السطح، ويعطي Separator GOR و Stock Tank Oil properties و Surface shrinkage وتأثير ظروف الفاصل على Bo و Rs و API.

8. Viscosity Test:
قياس Oil Viscosity و Gas Viscosity عند الحاجة فوق وتحت ضغط التشبع.

الحسابات الصحيحة
لا يتم حساب قيم نهائية بدون بيانات رقمية، لكن الحسابات المطلوبة عادة هي:
- Recombination Ratio.
- Total GOR.
- Rs نسبة الغاز المذاب.
- Bo معامل حجم التكوين للزيت.
- Bg معامل حجم التكوين للغاز.
- Oil Density.
- Gas Specific Gravity.
- API Gravity.
- Z-factor.
- Oil and Gas Viscosity.
- Compressibility.
- Y-Function.

المنحنيات المطلوبة
للزيت:
- Pressure vs Bo.
- Pressure vs Rs.
- Pressure vs Oil Viscosity.
- Pressure vs Oil Density.
- Pressure vs Relative Volume.
- Pressure vs Y-Function.

للغاز:
- Pressure vs Z-factor.
- Pressure vs Bg.
- Pressure vs Gas Viscosity.

لـ Gas Condensate:
- Pressure vs Liquid Dropout.
- Pressure vs CGR.
- Phase Envelope إذا كان التركيب متوفر.

إعداد البيانات للمحاكاة Eclipse أو CMG
إذا كان السائل Black Oil: الأفضل تجهيز PVTO في Eclipse باستخدام Pressure, Rs, Bo, Oil Viscosity، مع PVTG للغاز إذا لزم.
إذا كان السائل Volatile Oil أو Gas Condensate: الأفضل استخدام Compositional Model مع EOS Tuning في CMG GEM أو Eclipse Compositional.

تحذيرات هندسية مهمة
- لا تُستخدم عينات السطح مباشرة كأنها عينة مكمن.
- يجب إجراء Recombination قبل الحكم النهائي على سلوك المكمن.
- قيم Bo و Rs و Bubble Point Pressure لا تُستنتج بدقة من السطح بدون إعادة تركيب واختبار PVT.
- ظروف الفاصل تؤثر مباشرة على GOR و API و Stock Tank Properties.
- اختيار Black Oil Model أو Compositional Model يعتمد على نوع السائل والهدف من المحاكاة.

الخلاصة الهندسية
العينتان تمثلان زيتاً وغازاً منفصلين عند السطح. الخطوة الصحيحة هي Recombination ثم إجراء اختبارات PVT المناسبة. إذا أظهرت البيانات أن السائل Black Oil يمكن تجهيز PVTO. أما إذا كان Volatile Oil أو Gas Condensate أو غني بالمركبات الخفيفة، فالأفضل استخدام EOS و Compositional Simulation.
'''

def ask_ai(user_text, file_context=None):
    messages = [
        {'role': 'system', 'content': SYSTEM_PROMPT},
        {'role': 'user', 'content': GLOBAL_PVT_REFERENCE}
    ]
    if file_context:
        messages.append({'role': 'user', 'content': 'Extra uploaded PVT report context for this chat only:\n\n' + file_context[:25000]})
    messages.append({'role': 'user', 'content': user_text})
    headers = {'Authorization': f'Bearer {GROQ_API_KEY}', 'Content-Type': 'application/json'}
    payload = {'model': TEXT_MODEL, 'messages': messages, 'temperature': 0.10, 'max_tokens': 3500}
    try:
        response = requests.post(GROQ_URL, headers=headers, json=payload, timeout=90)
        data = response.json()
        if 'choices' in data:
            return data['choices'][0]['message']['content']
        return str(data)[:1500]
    except Exception as e:
        return 'صار خطأ في الاتصال بالذكاء الاصطناعي:\n' + str(e)

def encode_image_to_data_url(file_path):
    mime_type, _ = mimetypes.guess_type(file_path)
    if not mime_type:
        mime_type = 'image/jpeg'
    with open(file_path, 'rb') as f:
        b64 = base64.b64encode(f.read()).decode('utf-8')
    return f'data:{mime_type};base64,{b64}'

def ask_vision_ai(prompt, image_path, file_context=None):
    image_data_url = encode_image_to_data_url(image_path)
    full_prompt = SYSTEM_PROMPT + '\n\n' + GLOBAL_PVT_REFERENCE + '\n\nGraph Interpretation Task:\n' + prompt
    if file_context:
        full_prompt += '\n\nExtra report context:\n' + file_context[:12000]
    messages = [{'role': 'user', 'content': [{'type': 'text', 'text': full_prompt}, {'type': 'image_url', 'image_url': {'url': image_data_url}}]}]
    headers = {'Authorization': f'Bearer {GROQ_API_KEY}', 'Content-Type': 'application/json'}
    payload = {'model': VISION_MODEL, 'messages': messages, 'temperature': 0.10, 'max_tokens': 2500}
    try:
        response = requests.post(GROQ_URL, headers=headers, json=payload, timeout=90)
        data = response.json()
        if 'choices' in data:
            return data['choices'][0]['message']['content']
        return str(data)[:1500]
    except Exception as e:
        return 'صار خطأ في تحليل الصورة:\n' + str(e)

def extract_pdf_text(file_path):
    text = ''
    reader = PdfReader(file_path)
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text += page_text + '\n\n'
    return text.strip()

def extract_docx_text(file_path):
    doc = Document(file_path)
    text = ''
    for paragraph in doc.paragraphs:
        if paragraph.text.strip():
            text += paragraph.text + '\n'
    return text.strip()

def download_telegram_file(file_id, file_name):
    file_info = requests.get(f'{TELEGRAM_URL}/getFile', params={'file_id': file_id}, timeout=30).json()
    file_path = file_info['result']['file_path']
    file_url = f'https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}'
    suffix = os.path.splitext(file_name)[1] or '.bin'
    temp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    temp.close()
    file_data = requests.get(file_url, timeout=60).content
    with open(temp.name, 'wb') as f:
        f.write(file_data)
    return temp.name

def handle_document(chat_id, document):
    file_id = document['file_id']
    file_name = document.get('file_name', 'uploaded_file')
    mime_type = document.get('mime_type', '')
    try:
        local_path = download_telegram_file(file_id, file_name)
        lower_name = file_name.lower()
        if lower_name.endswith('.pdf'):
            extracted_text = extract_pdf_text(local_path)
            if not extracted_text:
                send_message(chat_id, 'قرأت ملف PDF لكن ما قدرت نستخرج نص واضح. ممكن يكون الملف سكان صورة. ارسلي صورة الرسم أو التقرير كصورة للتحليل البصري.')
                return
            FILE_CONTEXT[chat_id] = extracted_text
            send_message(chat_id, 'تم قراءة PDF بنجاح.\n\nالملف صار مرجع إضافي لهذه المحادثة.\n\nجربي:\n/analyze\nحلل التقرير وحدد نوع العينة والاختبارات والحسابات والرسوم المطلوبة.')
            return
        if lower_name.endswith('.docx'):
            extracted_text = extract_docx_text(local_path)
            if not extracted_text:
                send_message(chat_id, 'قرأت ملف DOCX لكن ما لقيتش نص واضح.')
                return
            FILE_CONTEXT[chat_id] = extracted_text
            send_message(chat_id, 'تم قراءة DOCX بنجاح.\n\nالملف صار مرجع إضافي لهذه المحادثة.')
            return
        if mime_type.startswith('image/') or lower_name.endswith(('.png', '.jpg', '.jpeg', '.webp')):
            IMAGE_CONTEXT[chat_id] = local_path
            send_message(chat_id, 'تم استلام الصورة بنجاح.\n\nاكتب:\n/graph\nحلل الرسم هندسياً')
            return
        send_message(chat_id, 'الملف لازم يكون PDF أو DOCX أو صورة.')
    except Exception as e:
        send_message(chat_id, 'صار خطأ أثناء قراءة الملف:\n' + str(e))

def handle_photo(chat_id, photos):
    try:
        best_photo = photos[-1]
        file_id = best_photo['file_id']
        local_path = download_telegram_file(file_id, 'uploaded_graph.jpg')
        IMAGE_CONTEXT[chat_id] = local_path
        send_message(chat_id, 'تم استلام الصورة بنجاح.\n\nاكتب:\n/graph\nحلل الرسم هندسياً وحدد السلوك والملاحظات')
    except Exception as e:
        send_message(chat_id, 'صار خطأ أثناء تحميل الصورة:\n' + str(e))

def parse_numbers_list(text, key):
    pattern = key + r'\s*=\s*\[([^\]]+)\]'
    match = re.search(pattern, text, re.IGNORECASE)
    if not match:
        return None
    numbers = []
    for item in match.group(1).split(','):
        try:
            numbers.append(float(item.strip()))
        except Exception:
            pass
    return numbers

# تم تعطيل دالة الرسم المؤقتة لتجنب خطأ التثبيت
def try_generate_plot(chat_id, text):
    send_message(chat_id, 'عذراً، ميزة رسم المنحنيات (/plot) معطلة حالياً للصيانة. يمكنك طلب تحليل البيانات نصياً عبر أمر /analyze.')
    return True 

def is_graph_command(text):
    t = text.lower().strip()
    return t.startswith('/graph') or t.startswith('/interpret_graph') or t.startswith('/interpret graph')

def is_plot_command(text):
    return text.lower().strip().startswith('/plot')

def is_export_command(text):
    t = text.lower().strip()
    return t.startswith('/export_sim') or t.startswith('/pvto') or t.startswith('/pvtg') or t.startswith('/eclipse') or t.startswith('/cmg')

def is_surface_separator_question(text):
    t = text.lower()
    has_oil = ('surface separator oil' in t or 'separator oil' in t or 'عينة زيت من الفاصل' in t or 'زيت من الفاصل' in t or 'زيت من الفاصل السطحي' in t)
    has_gas = ('separator gas' in t or 'عينة غاز من الفاصل' in t or 'غاز من الفاصل' in t or 'غاز من الفاصل السطحي' in t)
    return has_oil and has_gas

while True:
    try:
        updates = requests.get(f'{TELEGRAM_URL}/getUpdates', params={'offset': offset + 1, 'timeout': 30}, timeout=40).json()
        for update in updates.get('result', []):
            offset = update['update_id']
            if 'message' not in update:
                continue
            message = update['message']
            chat_id = message['chat']['id']
            if 'document' in message:
                handle_document(chat_id, message['document'])
                continue
            if 'photo' in message:
                handle_photo(chat_id, message['photo'])
                continue
            if 'text' not in message:
                continue
            text = message['text']
            context = FILE_CONTEXT.get(chat_id)
            if text == '/start':
                reply = 'أهلاً بك في PVT Lab AI Bot.\n\nأنا مساعد هندسي متخصص في PVT Lab و Reservoir Fluid Analysis و Reservoir Simulation.\n\nالأوامر:\n/analyze\n/report\n/calc\n/plot\n/graph\n/interpret_graph\n/check\n/export_sim\n/pvto\n/pvtg\n/eclipse\n/cmg'
                send_message(chat_id, reply)
                continue
            if is_surface_separator_question(text):
                send_message(chat_id, surface_separator_analysis_ar())
                continue
            if is_graph_command(text):
                image_path = IMAGE_CONTEXT.get(chat_id)
                if not image_path:
                    send_message(chat_id, 'ارسلي صورة الرسم أو Figure أولاً، وبعدها اكتبي /graph.')
                    continue
                prompt = text + '\n\nAnalyze this engineering graph professionally. Identify graph type, axes, trend, anomalies, non-physical behavior, retrograde behavior if applicable, contamination indicators, separator performance issues, engineering meaning, possible causes, and recommendations.'
                reply = ask_vision_ai(prompt, image_path, context)
                send_message(chat_id, reply)
                continue
            if is_plot_command(text):
                try_generate_plot(chat_id, text)
                # تم إزالة استدعاء ask_ai هنا لتجنب الرد المكرر عند تعطيل الرسم
                continue
            if is_export_command(text):
                export_prompt = text + '\n\nGenerate simulator export guidance or formatting. Adapt to fluid type and data availability. Include unit validation, consistency checks, simulator warnings, black-oil vs compositional decision, Eclipse/CMG keyword guidance, and missing required data if needed.'
                reply = ask_ai(export_prompt, context)
                send_message(chat_id, reply)
                continue
            reply = ask_ai(text, context)
            send_message(chat_id, reply)
    except Exception as e:
        print(e)
    time.sleep(1)

