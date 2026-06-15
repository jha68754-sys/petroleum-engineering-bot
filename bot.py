"""
╔══════════════════════════════════════════════════════════════╗
║         PetroMind — Petroleum Engineering Telegram Bot       ║
║         Groq API | llama-3.3-70b / llama-4-scout            ║
║         Production-Ready v2.0                                ║
╚══════════════════════════════════════════════════════════════╝

Requirements:
    pip install groq python-telegram-bot python-dotenv

.env file:
    TELEGRAM_BOT_TOKEN=your_telegram_token
    GROQ_API_KEY=your_groq_api_key
"""

import os
import logging
from datetime import datetime
from dotenv import load_dotenv
from groq import Groq
from telegram import Update, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ─── Load Environment ────────────────────────────────────────
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY   = os.getenv("GROQ_API_KEY")

# ─── Logging ─────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ─── Groq Client ─────────────────────────────────────────────
client = Groq(api_key=GROQ_API_KEY)

# ─── Model Config ────────────────────────────────────────────
MODELS = {
    "fast":    "llama-3.3-70b-versatile",          # default — fast & accurate
    "scout":   "meta-llama/llama-4-scout-17b-16e-instruct",  # multimodal
}
DEFAULT_MODEL = MODELS["fast"]

# ─── Conversation Memory (per user) ──────────────────────────
# Stores last N messages per user_id for context
conversation_history: dict[int, list[dict]] = {}
MAX_HISTORY = 10   # keep last 10 exchanges

# ════════════════════════════════════════════════════════════════
# SYSTEM PROMPT — Petroleum Engineering Expert
# ════════════════════════════════════════════════════════════════
SYSTEM_PROMPT = """أنت PetroMind — مساعد هندسة نفط متخصص بخبرة +20 سنة في:
1. مختبر PVT
2. هندسة المكامن
3. محاكاة المكامن
4. هندسة الحفر
5. هندسة الإنتاج

تدعم العربية والإنجليزية. إذا السؤال بالعربية → رد بالعربية. إذا بالإنجليزية → رد بالإنجليزية.

═══════════════════════════════════════════════════
بروتوكول مكافحة الأخطاء الهندسية (إلزامي)
═══════════════════════════════════════════════════
1. لا تخترع معاملات أو بيانات حقلية غير موجودة
2. عند استخدام علاقة تجريبية → اذكر اسمها ونطاق تطبيقها
3. دائماً اذكر نظام الوحدات (Field / SI / Metric)
4. إذا البيانات خارج النطاق → حذّر المستخدم صراحةً
5. لا تستقرئ منحنيات PVT خارج نطاق البيانات المقاسة
6. عند تفسير المخططات: صف الشكل أولاً ثم استنتج الفيزياء
7. إذا البيانات ناقصة → اذكر بالضبط ما ينقص
8. فرّق دائماً: بيانات مقاسة / محسوبة بعلاقة / محاكاة / مفترضة
9. معاملات ضبط معادلة الحالة (EOS) ≠ بيانات مختبرية
10. دائماً اذكر المصدر عند استخدام معادلة أو علاقة تجريبية

═══════════════════════════════════════════════════
قسم PVT ومختبر الطوارئ
═══════════════════════════════════════════════════
الاختبارات المدعومة:
• CCE — اختبار التمدد عند ثبات التركيب
• DLE — اختبار التحرير التفاضلي
• CVD — اختبار الاستنفاد عند ثبات الحجم
• اختبار الفاصل (Separator Test)
• قياس اللزوجة: نفط ميت / حي / مشبع / غير مشبع
• تحليل التركيب الجزيئي C1–C7+
• درجة حرارة ظهور الشمع (WAT)
• ضغط بداية ترسب الإسفلتين (AOP)

قواعد مراقبة الجودة (QC):
• Bo < 1.0 في المكمن → مستحيل، خطأ في البيانات
• Rs يزيد مع انخفاض الضغط → مستحيل، خطأ في البيانات
• Z-factor > 1.5 عند ضغط منخفض → مشكوك فيه، راجع البيانات
• API < 10° → نفط ثقيل جداً، العلاقات التجريبية القياسية قد لا تنطبق

العلاقات التجريبية:
• Standing (1947): API 16-63°، GOR 20-1425 scf/STB، T 100-258°F
• Al-Marhoun (1988): API 19.4-44.6°، GOR 26-1602 scf/STB ← الأنسب للشرق الأوسط
• Vazquez & Beggs (1980): API 15-59°، GOR 0-2199 scf/STB
• Glaso (1980): API 22-48°، GOR 90-2637 scf/STB ← بحر الشمال
• Petrosky & Farshad (1993): API 25-46.1°، GOR 217-1406 scf/STB ← خليج المكسيك

تفسير المخططات:
CCE: ضغط نقطة الفقاعة (Pb) عند نقطة الانكسار في المنحنى وليس عند الحجم الأقصى
DLE: Rs يتناقص بشكل رتيب من Pb حتى الضغط الجوي — أي زيادة = خطأ
منحنى Bo: الحد الأقصى دائماً عند Pb
CVD: التكثف الرجعي — السائل يزيد مع انخفاض الضغط (سلوك غير عادي طبيعي للغاز المكثف)
Z-factor: منحنى على شكل U طبيعي للغاز الطبيعي
اللزوجة: النفط الميت تتناقص لزوجته مع الحرارة (سلوك أرهينيوس)

═══════════════════════════════════════════════════
قسم هندسة المكامن
═══════════════════════════════════════════════════
موازنة المادة (Havlena-Odeh):
F = Eo·N + Efw·N + Eg·mN + We
حيث:
  F  = الاستخلاص تحت سطح الأرض
  Eo = تمدد النفط + الغاز المنحل
  Efw = انضغاطية الماء الرابط + الصخر
  Eg = تمدد الغطاء الغازي
  We = تدفق الماء من الحوض المائي
  N  = الاحتياطي النفطي الأصلي في باطن الأرض (STOIIP)

آليات الإنتاج ومعاملات الاسترداد:
• محرك الغاز المنحل: 5-25%
• محرك اندفاع الماء: 20-50%
• التصريف الثقالي: 60-80%
• محرك الغطاء الغازي: 20-40%

منحنيات تناقص الإنتاج (Arps):
• أسي (Exponential): q = qi·exp(-Di·t)، b=0
• هذبي (Hyperbolic): q = qi·(1+b·Di·t)^(-1/b)، 0<b<1
• توافقي (Harmonic): q = qi/(1+Di·t)، b=1

اختبار الآبار:
• مخطط هورنر: (Pws-Pwf) مقابل log[(tp+Δt)/Δt]
• عامل الجلد: موجب = تلف، سالب = تحسين
• تأثير التخزين في البئر: ميل وحدوي على المخطط اللوغاريتمي

═══════════════════════════════════════════════════
قسم محاكاة المكامن
═══════════════════════════════════════════════════
المحاكيات المدعومة: Eclipse (E100/E300)، CMG (IMEX/GEM/STARS)
أنواع المحاكاة:
• نموذج النفط الأسود: Eclipse E100، CMG IMEX
• النموذج التركيبي: Eclipse E300، CMG GEM
• النموذج الحراري/EOR: CMG STARS

مراحل مطابقة البيانات التاريخية:
1. مطابقة ضغط الحقل (ضبط HCPV، الحوض المائي)
2. مطابقة معدلات الإنتاج (ضبط النفاذية، عامل الجلد)
3. مطابقة WCT و GOR (ضبط kr، Kv/Kh)
4. مطابقة أداء الآبار المنفردة

التحقق من التهيئة:
• STOIIP المحاكاة مقابل الحجمية: يجب أن يتطابقا ضمن 2-5%
• تلامس السوائل GOC و OWC يجب أن يتوافق مع تفسير السجلات

═══════════════════════════════════════════════════
قسم الحفر
═══════════════════════════════════════════════════
نافذة كثافة الطين الآمنة:
  الحد الأدنى = تدرج ضغط المسام + هامش أمان (0.5 ppg)
  الحد الأقصى = تدرج ضغط التكسير - هامش أمان (0.5 ppg)
  دائماً ارسم: PP، FG، MW على نفس محور العمق

تصميم الأغلفة:
• فحص الانفجار (Burst): Pi - Po > 0
• فحص الانهيار (Collapse): Po - Pi > 0
• التحليل الثلاثي المحاور للأحمال المركبة

استقرار جدار البئر:
• الانهيار الانضغاطي (Breakout) → زيادة كثافة الطين
• الشقوق التوترية الناجمة عن الحفر → تخفيض كثافة الطين

═══════════════════════════════════════════════════
قسم هندسة الإنتاج
═══════════════════════════════════════════════════
تحليل العقدة:
• IPR (داخلي): Vogel، Darcy، Jones-Blount-Glaze
• VLP (خارجي): Beggs-Brill، Hagedorn-Brown، Mukherjee-Brill
• نقطة التشغيل: تقاطع IPR مع VLP

اختيار الرفع الاصطناعي:
• ESP: معدل إنتاج عالي، بحري، آبار منحرفة
• رفع الغاز: GOR عالي، بحري، مرونة تشغيلية
• مضخة الساق (Sucker Rod): إنتاج منخفض، بري، بسيطة
• PCP: نفط لزج، تكوينات رملية

ضمان انسياب التدفق:
• تكوين الهيدرات: مخطط P-T
• ترسب الشمع: تحت درجة حرارة WAT
• ترسب الإسفلتين: قرب منطقة Pb

═══════════════════════════════════════════════════
المصطلحات النفطية العربية المعتمدة
═══════════════════════════════════════════════════
ضغط نقطة الفقاعة = Bubble Point Pressure (Pb)
ضغط نقطة الندى = Dew Point Pressure (Pd)
معامل حجم تكوين النفط = Bo
نسبة الغاز المنحل = Solution GOR (Rs)
اختبار التمدد عند ثبات التركيب = CCE
اختبار التحرير التفاضلي = DLE
اختبار الاستنفاد عند ثبات الحجم = CVD
معامل انضغاطية الغاز = Z-factor
اللزوجة الديناميكية للنفط = Oil Viscosity (μo)
معادلة الحالة = EOS
موازنة المادة = Material Balance
آلية الإنتاج = Drive Mechanism
محرك الغاز المنحل = Solution Gas Drive
محرك اندفاع الماء = Water Drive
منحنى تناقص الإنتاج = Production Decline Curve
الإنتاج التراكمي النهائي المتوقع = EUR
علاقة الأداء الداخلي للبئر = IPR
منحنى أداء الأنبوب الرأسي = VLP
مؤشر الإنتاجية = Productivity Index (J)
عامل الجلد = Skin Factor (S)
الاحتياطي النفطي الأصلي في باطن الأرض = STOIIP
الاحتياطي الغازي الأصلي في باطن الأرض = GIIP
معامل الاسترداد = Recovery Factor
النفاذية النسبية = Relative Permeability (kr)
المسامية = Porosity (φ)
تشبع الماء = Water Saturation (Sw)
نسبة الماء المنتج = Water Cut (WCT)
نسبة الغاز إلى النفط المنتج = Producing GOR
مطابقة البيانات التاريخية = History Matching
محاكاة المكمن = Reservoir Simulation
كثافة طين الحفر = Mud Weight (MW)
تدرج ضغط التكسير = Fracture Gradient (FG)
ضغط المسام = Pore Pressure (PP)
الغلاف الوقائي = Casing
مجموعة قاع البئر = BHA
الرفع الاصطناعي = Artificial Lift
المضخة الكهربائية الغاطسة = ESP
رفع الغاز = Gas Lift
ضمان انسياب التدفق = Flow Assurance
تقييم التكوين = Formation Evaluation
سجلات الآبار = Well Logs
النفاذية المطلقة = Absolute Permeability (k)
الحوض المائي = Aquifer
التصريف الثقالي = Gravity Drainage
مستوى تلامس النفط والماء = OWC
مستوى تلامس الغاز والنفط = GOC
ضغط قاع البئر المتدفق = FBHP
ضغط قاع البئر الساكن = SBHP

═══════════════════════════════════════════════════
تنسيق الرد (إلزامي)
═══════════════════════════════════════════════════
1. التخصص: [PVT / مكامن / حفر / إنتاج / محاكاة]
2. الطريقة أو العلاقة التجريبية المستخدمة
3. المعادلة
4. الحساب مع الوحدات
5. النتائج
6. التفسير الهندسي
7. التوصيات
⚠️ تحذير: للبيانات المشكوك فيها أو خارج النطاق
📌 افتراض: للبيانات المفترضة"""


# ════════════════════════════════════════════════════════════════
# GLOSSARY — Arabic ↔️ English
# ════════════════════════════════════════════════════════════════
GLOSSARY = {
    "bubble point pressure":        "ضغط نقطة الفقاعة (Pb)",
    "dew point pressure":           "ضغط نقطة الندى (Pd)",
    "oil formation volume factor":  "معامل حجم تكوين النفط (Bo)",
    "gas formation volume factor":  "معامل حجم تكوين الغاز (Bg)",
    "solution gor":                 "نسبة الغاز المنحل (Rs)",
    "cce":                          "اختبار التمدد عند ثبات التركيب",
    "dle":                          "اختبار التحرير التفاضلي",
    "cvd":                          "اختبار الاستنفاد عند ثبات الحجم",
    "z-factor":                     "معامل انضغاطية الغاز (Z)",
    "oil viscosity":                "اللزوجة الديناميكية للنفط (μo)",
    "eos":                          "معادلة الحالة",
    "material balance":             "موازنة المادة",
    "stoiip":                       "الاحتياطي النفطي الأصلي في باطن الأرض",
    "giip":                         "الاحتياطي الغازي الأصلي في باطن الأرض",
    "recovery factor":              "معامل الاسترداد",
    "ipr":                          "علاقة الأداء الداخلي للبئر",
    "vlp":                          "منحنى أداء الأنبوب الرأسي",
    "skin factor":                  "عامل الجلد (S)",
    "productivity index":           "مؤشر الإنتاجية (J)",
    "water cut":                    "نسبة الماء المنتج (WCT)",
    "history matching":             "مطابقة البيانات التاريخية",
    "mud weight":                   "كثافة طين الحفر (MW)",
    "pore pressure":                "ضغط المسام (PP)",
    "fracture gradient":            "تدرج ضغط التكسير (FG)",
    "esp":                          "المضخة الكهربائية الغاطسة",
    "gas lift":                     "رفع الغاز",
    "nodal analysis":               "تحليل العقدة",
    "flow assurance":               "ضمان انسياب التدفق",
    "permeability":                 "النفاذية (k)",
    "porosity":                     "المسامية (φ)",
    "water saturation":             "تشبع الماء (Sw)",
    "decline curve":                "منحنى تناقص الإنتاج",
    "eur":                          "الإنتاج التراكمي النهائي المتوقع",
    "bha":                          "مجموعة قاع البئر",
    "owc":                          "مستوى تلامس النفط والماء",
    "goc":                          "مستوى تلامس الغاز والنفط",
    "fbhp":                         "ضغط قاع البئر المتدفق",
    "sbhp":                         "ضغط قاع البئر الساكن",
    "wat":                          "درجة حرارة ظهور الشمع",
    "aop":                          "ضغط بداية ترسب الإسفلتين",
    "aquifer":                      "الحوض المائي",
    "gravity drainage":             "التصريف الثقالي",
    "casing":                       "الغلاف الوقائي (Casing)",
    "wob":                          "قوة الضغط على الرأس الثاقب",
    "rop":                          "معدل الاختراق",
    "wellbore stability":           "استقرار جدار البئر",
    "pvt":                          "خصائص الضغط والحجم والحرارة",
    "formation evaluation":         "تقييم التكوين",
    "relative permeability":        "النفاذية النسبية (kr)",
    "capillary pressure":           "ضغط الشعيرات الدموية (Pc)",
    "drive mechanism":              "آلية الإنتاج",
    "artificial lift":              "الرفع الاصطناعي",
    "reservoir simulation":         "محاكاة المكمن",
}

UNIT_CONVERSIONS = {
    ("psia", "kpa"):   lambda x: x * 6.895,
    ("kpa", "psia"):   lambda x: x / 6.895,
    ("bar", "psia"):   lambda x: x * 14.504,
    ("psia", "bar"):   lambda x: x / 14.504,
    ("ft", "m"):       lambda x: x * 0.3048,
    ("m", "ft"):       lambda x: x / 0.3048,
    ("in", "mm"):      lambda x: x * 25.4,
    ("mm", "in"):      lambda x: x / 25.4,
    ("f", "c"):        lambda x: (x - 32) * 5 / 9,
    ("c", "f"):        lambda x: x * 9 / 5 + 32,
    ("stb/d", "m3/d"): lambda x: x * 0.15899,
    ("m3/d", "stb/d"): lambda x: x / 0.15899,
    ("ppg", "sg"):     lambda x: x / 8.33,
    ("sg", "ppg"):     lambda x: x * 8.33,
    ("ppg", "psi/ft"): lambda x: x * 0.05195,
    ("psi/ft", "ppg"): lambda x: x / 0.05195,
    ("md", "m2"):      lambda x: x * 9.869e-16,
    ("cp", "mpas"):    lambda x: x * 1.0,
}


# ════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ════════════════════════════════════════════════════════════════

def get_history(user_id: int) -> list[dict]:
    return conversation_history.get(user_id, [])


def add_to_history(user_id: int, role: str, content: str):
    if user_id not in conversation_history:
        conversation_history[user_id] = []
    conversation_history[user_id].append({"role": role, "content": content})
    # Keep only last MAX_HISTORY messages
    if len(conversation_history[user_id]) > MAX_HISTORY * 2:
        conversation_history[user_id] = conversation_history[user_id][-MAX_HISTORY * 2:]


def clear_history(user_id: int):
    conversation_history[user_id] = []


def call_groq(user_id: int, user_message: str, model: str = DEFAULT_MODEL) -> str:
    """Send message to Groq API with conversation history."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages += get_history(user_id)
    messages.append({"role": "user", "content": user_message})

    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.3,        # low temp for technical accuracy
            max_tokens=2048,
            top_p=0.9,
        )
        reply = response.choices[0].message.content
        add_to_history(user_id, "user", user_message)
        add_to_history(user_id, "assistant", reply)
        return reply

    except Exception as e:
        logger.error(f"Groq API error: {e}")
        return f"⚠️ خطأ في الاتصال بالنموذج:\n{str(e)}"


def lookup_glossary(term: str) -> str:
    term_lower = term.strip().lower()
    # exact match
    if term_lower in GLOSSARY:
        return f"📖 *{term}*\n🇦🇪 {GLOSSARY[term_lower]}"
    # partial match
    matches = [(k, v) for k, v in GLOSSARY.items() if term_lower in k]
    if matches:
        result = "📖 *نتائج البحث:*\n"
        for k, v in matches[:5]:
            result += f"• *{k}* → {v}\n"
        return result
    return f"❌ المصطلح '{term}' غير موجود في القاموس.\nجرب مصطلحاً آخر أو اسأل مباشرة."


def convert_units(args: list[str]) -> str:
    """Convert between petroleum engineering units."""
    if len(args) < 3:
        return (
            "❌ الاستخدام الصحيح:\n`/convert [القيمة] [الوحدة من] [الوحدة إلى]`\n\n"
            "مثال: `/convert 3000 psia kpa`\n\n"
            "الوحدات المدعومة:\n"
            "ضغط: psia, kpa, bar\n"
            "طول: ft, m\n"
            "حرارة: f, c\n"
            "معدل: stb/d, m3/d\n"
            "كثافة الطين: ppg, sg, psi/ft\n"
            "لزوجة: cp, mpas"
        )
    try:
        value = float(args[0])
        from_unit = args[1].lower()
        to_unit = args[2].lower()
        key = (from_unit, to_unit)
        if key in UNIT_CONVERSIONS:
            result = UNIT_CONVERSIONS[key](value)
            return f"🔄 *تحويل الوحدات*\n`{value} {args[1]}` = `{result:.4f} {args[2]}`"
        else:
            return f"❌ لا يوجد تحويل بين `{args[1]}` و `{args[2]}`\nتحقق من قائمة الوحدات المدعومة."
    except ValueError:
        return "❌ القيمة غير صحيحة. أدخل رقماً صحيحاً.\nمثال: `/convert 3000 psia kpa`"


# ════════════════════════════════════════════════════════════════
# COMMAND HANDLERS
# ════════════════════════════════════════════════════════════════

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    clear_history(update.effective_user.id)
    text = (
        f"🛢️ *أهلاً {user.first_name}!*\n\n"
        "*PetroMind* — مساعد هندسة النفط المتخصص\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🔬 مختبر PVT\n"
        "⚖️ هندسة المكامن\n"
        "💻 محاكاة المكامن\n"
        "🔩 هندسة الحفر\n"
        "⚙️ هندسة الإنتاج\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "اكتب سؤالك مباشرة بالعربية أو الإنجليزية.\n"
        "أو استخدم الأوامر التالية:\n\n"
        "/help — قائمة جميع الأوامر"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📋 *قائمة الأوامر — PetroMind*\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🔬 *PVT*\n"
        "`/pvt` — تحليل بيانات PVT\n"
        "`/pvt_qc` — مراقبة جودة بيانات PVT\n"
        "`/pvt_plot` — تفسير مخططات PVT\n"
        "`/pvt_cor` — حساب بعلاقات تجريبية\n\n"
        "⚖️ *هندسة المكامن*\n"
        "`/mb` — موازنة المادة\n"
        "`/decline` — منحنيات تناقص الإنتاج\n"
        "`/ipr` — علاقة الأداء الداخلي للبئر\n"
        "`/drive` — تحديد آلية الإنتاج\n\n"
        "🔩 *الحفر*\n"
        "`/mw` — نافذة كثافة الطين الآمنة\n"
        "`/casing` — تصميم الأغلفة\n"
        "`/stability` — استقرار جدار البئر\n\n"
        "⚙️ *الإنتاج*\n"
        "`/nodal` — تحليل العقدة\n"
        "`/lift` — اختيار الرفع الاصطناعي\n"
        "`/fa` — ضمان انسياب التدفق\n\n"
        "💻 *المحاكاة*\n"
        "`/sim_init` — التحقق من التهيئة\n"
        "`/sim_hm` — مطابقة البيانات التاريخية\n"
        "`/sim_kw` — مساعدة كلمات Eclipse/CMG\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🛠️ *أدوات*\n"
        "`/convert [قيمة] [من] [إلى]` — تحويل الوحدات\n"
        "`/glossary [مصطلح]` — قاموس المصطلحات\n"
        "`/model` — تغيير نموذج الذكاء الاصطناعي\n"
        "`/new` — محادثة جديدة (مسح السياق)\n"
        "`/status` — حالة البوت والنموذج الحالي\n"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_new(update: Update, context: ContextTypes.DEFAULT_TYPE):
    clear_history(update.effective_user.id)
    await update.message.reply_text(
        "🔄 تم مسح سياق المحادثة.\nابدأ سؤالاً جديداً.",
        parse_mode="Markdown"
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    history_len = len(get_history(user_id)) // 2
    model_name = context.user_data.get("model", DEFAULT_MODEL)
    text = (
        "📊 *حالة PetroMind*\n\n"
        f"🤖 النموذج الحالي: `{model_name}`\n"
        f"💬 رسائل في السياق: `{history_len}`\n"
        f"🕐 الوقت: `{datetime.now().strftime('%Y-%m-%d %H:%M')}`\n\n"
        "الوحدات النشطة:\n"
        "✅ مختبر PVT\n"
        "✅ هندسة المكامن\n"
        "✅ محاكاة المكامن\n"
        "✅ هندسة الحفر\n"
        "✅ هندسة الإنتاج"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        current = context.user_data.get("model", DEFAULT_MODEL)
        text = (
            f"🤖 *النموذج الحالي:* `{current}`\n\n"
            "النماذج المتاحة:\n"
            f"• `fast`
