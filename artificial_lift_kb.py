"""
Comprehensive Artificial Lift Knowledge Base adhering to SPE, Weatherford, and Brown standards.
"""

from __future__ import annotations
from typing import Dict
from models.artificial_lift_models import LiftSystemDetails

ARTIFICIAL_LIFT_KNOWLEDGE_BASE: Dict[str, LiftSystemDetails] = {
    "esp": {
        "system_id": "esp",
        "name_en": "Electrical Submersible Pump (ESP)",
        "name_ar": "المضخات الغاطسة الكهربائية (ESP)",
        "theory_ar": "مضخة طرد مركزي متعددة المراحل تُدار بمحرك كهربائي غاطس في الأسفل، تحول الطاقة الكهربائية إلى طاقة هيدروليكية لرفع كميات كبيرة من السوائل من قاع البئر إلى السطح. مرجع: SPE Petroleum Engineering Handbook, Vol. IV.",
        "selection_criteria_ar": [
            "معدلات إنتاج عالية (من 500 إلى أكثر من 50,000 برميل/يوم)",
            "أعماق متوسطة إلى كبيرة",
            "نسبة ماء عالية (Water Cut)",
            "تحمل درجات حرارة المكمن مع اختيار الكابلات والمحركات المناسبة"
        ],
        "advantages_ar": [
            "معدلات إنتاج عالية جداً",
            "خفض ضغط التدفق القاعي (Pwf) بكفاءة عالية",
            "مناسبة للآبار المائلة والأفقية",
            "إمكانية التحكم بالسرعة عبر VFD"
        ],
        "limitations_ar": [
            "حساسية عالية لوجود الغاز الحر (Free Gas) وتأثرها بالتقبض (Gas Lock)",
            "تتأثر سلباً بوجود الرمل (Abrasive wear)",
            "تكلفة رأس مالية عالية جداً عند الفشل (Workover cost)",
            "اعتماد كامل على توفر الطاقة الكهربائية المستقرة"
        ],
        "design_parameters_ar": [
            "عدد المراحل (Number of Stages)",
            "القدرة الحصانية للمحرك (Motor HP)",
            "معدل التدفق التصميمي (BEP - Best Efficiency Point)",
            "التردد والسرعة (Hz / RPM via VFD)"
        ],
        "key_equations_ar": [
            "Total Dynamic Head (TDH) = Vertical Lift + Friction Losses + Wellhead Pressure",
            "Hydraulic HP = (Q * TDH * SG) / 3960",
            "Brake HP = Hydraulic HP / Pump Efficiency"
        ],
        "field_applications_ar": [
            "حقول النفط البحرية والبرية ذات الإنتاج العالي",
            "حقن الماء ودعم الضغط المكمني",
            "الآبار ذات نسبة الماء المرتفعة متأخرة العمر"
        ],
        "troubleshooting_ar": [
            "المشكلة: Gas Lock -> الحل: تركيب غاز أنكور (Gas Separator / Gas Anchor) أو تعديل معدل السحب",
            "المشكلة: Motor Overload -> الحل: فحص لزوجة السوائل ودرجة الحرارة ومراجعة تردد VFD",
            "المشكلة: Shaft Failure -> الحل: تقليل العزم المبدئي ومراقبة الاهتزازات"
        ],
        "failure_analysis_ar": [
            "فشل العزل الكهربائي للكابل بسبب تغلغل الغاز أو ارتفاع الحرارة",
            "تآكل ريش المضخة بسبب الرمل (Sand Erosion)",
            "احتراق المحرك نتيجة التشغيل الجاف (Pump-off / Underload)"
        ],
        "reference": "Takacs, G., Electrical Submersible Pumps Manual, Gulf Professional Publishing; SPE Handbook Vol. IV.",
        "confidence": "High"
    },
    "gas_lift": {
        "system_id": "gas_lift",
        "name_en": "Gas Lift",
        "name_ar": "الرفع بالغاز",
        "theory_ar": "حقن غاز عالي الضغط في عمود السوائل داخل أنابيب الإنتاج (Tubing) لتقليل الكثافة الهيدروستاتيكية وزيادة مرونة التدفق إلى السطح. مرجع: Brown, K.E., The Technology of Artificial Lift Methods.",
        "selection_criteria_ar": [
            "توفر مصدر غاز ضغط عالي في الموقع",
            "GOR مرتفع أو متوسط",
            "آبار ذات عمق كبير وميل كبير",
            "تحمل وجود الرمال بشكل ممتاز مقارنة بالمضخات الميكانيكية"
        ],
        "advantages_ar": [
            "تحمل ممتاز للرمال والموائع التآكلية",
            "سهولة الصيانة عبر سحب الصمامات بالأسلاك (Wireline retrieval)",
            "مرونة عالية في تعديل معدلات الإنتاج",
            "تكلفة صيانة منخفضة في الآبار البحرية"
        ],
        "limitations_ar": [
            "يتطلب شبكة إمداد غاز ضغط عالي وضواغط سطحية",
            "لا يحقق أدنى ضغط قاعي ممكن (Lowest Pwf) مقارنة بـ ESP",
            "كفاءة طاقة أقل في الآبار الضحلة جداً أو ذات الإنتاج المنخفض جداً"
        ],
        "design_parameters_ar": [
            "معدل حقن الغاز (Injection Gas Rate)",
            "ضغط الحقن السطحي (Operating Injection Pressure)",
            "تباعد أعماق صمامات الرفع بالغاز (Valve Spacing)",
            "حجم وقُطر أنابيب الإنتاج (Tubing Size)"
        ],
        "key_equations_ar": [
            "Hydrostatic Gradient Reduction: P_hydro = 0.052 * (MW_effective) * TVD",
            "GLR = (Q_injection + Q_formation_gas) / Q_oil"
        ],
        "field_applications_ar": [
            "حقول النفط الكبرى ذات البنية التحتية لشبكات الغاز",
            "الآبار البحرية العميقة",
            "الآبار ذات المشاكل الرملية المستمرة"
        ],
        "troubleshooting_ar": [
            "المشكلة: Port Freezing -> الحل: حقن مواد مانعة للتجمد (Glycol/Methanol) وتجفيف الغاز",
            "المشكلة: Valve Leakage -> الحل: استبدال الصمام عبر سلك الـ Wireline",
            "المشكلة: Tubing/Casing Communication -> الحل: إجراء اختبار ضغط (Mechanical Packer Test)"
        ],
        "failure_analysis_ar": [
            "تآكل صمامات الرفع بالغاز (Valve Erosion) نتيجة السرعات العالية للغاز",
            "تكون ترسبات الاسكالا (Scale) على صمامات الحقن"
        ],
        "reference": "Brown, K.E., The Technology of Artificial Lift Methods, Vol. 2a/2b; SPE PetroWiki.",
        "confidence": "High"
    },
    "srp": {
        "system_id": "srp",
        "name_en": "Sucker Rod Pumping (SRP / Beam Pump)",
        "name_ar": "مضخات الماصات الميكانيكية (الرزازة / Beam Pump)",
        "theory_ar": "نظام رفع ميكانيكي تقليدي يعتمد على حركة ترددية على السطح تُنقل عبر عمود الماصات (Rod String) لتشغيل مضخة قاعية ذات مكبس (Plunger Pump). مرجع: API Spec 11E / SPE Monograph.",
        "selection_criteria_ar": [
            "الآبار الضحلة إلى متوسطة العمق",
            "معدلات إنتاج منخفضة إلى متوسطة (تصل إلى 1000 برميل/يوم)",
            "الآبار البرية ذات الصيانة المتاحة بسهولة"
        ],
        "advantages_ar": [
            "بساطة التصميم وسهولة التشغيل والصيانة الحقلية",
            "كفاءة عالية في التعامل مع اللزوجة المتوسطة",
            "عمر افتراضي طويل وموثوقية عالية في الظروف العادية",
            "إمكانية تعديل السرعة و طول الشوط بسهولة"
        ],
        "limitations_ar": [
            "غير مناسب للآبار العميقة جداً بسبب وزن أعمدة الماصات",
            "حساسية عالية للانحراف الشديد في الآبار (Rod wear & tubing friction)",
            "حجم المعدات السطحية الكبير غير مناسب للمناطق المزدحمة"
        ],
        "design_parameters_ar": [
            "طول الشوط وسرعة الضربات (Stroke Length & SPM)",
            "حجم المكبس (Plunger Diameter)",
            "تصميم تدرج أعمدة الماصات (Rod String Taper)",
            "الوزن الموازن (Counterbalance)"
        ],
        "key_equations_ar": [
            "Peak Rod Load (PRL) = Buoyant Weight of Rods + Fluid Load + Acceleration Factors",
            "Volumetric Displacement = 0.1166 * D^2 * S * N (BF)"
        ],
        "field_applications_ar": [
            "حقول البر الرئيسي الناضجة ذات الآبار ذات معدلات الإنتاج المتوسطة/المنخفضة",
            "إنتاج النفط الثقيل مع تسخين أو تخفيف اللزوجة"
        ],
        "troubleshooting_ar": [
            "المشكلة: Rod Parting (انقطاع الأعمدة) -> الحل: إعادة تصميم تدرج الأعمدة وتقليل الحمل الأقصى",
            "المشكلة: Fluid Pound -> الحل: ضبط مؤقت الخمول (Pump-off controller) لمنع ضربات السوائل",
            "المشكلة: Tubing Leak -> الحل: فحص أنابيب الإنتاج واستبدال التالف"
        ],
        "failure_analysis_ar": [
            "الإجهاد التعبوي لأعمدة الماصات (Fatigue failure of sucker rods)",
            "التآكل الكيميائي الحاصل بسبب غازات $H_2S$ أو $CO_2$"
        ],
        "reference": "API Spec 11E; Gibbs, S.G., Beam Pump Manual, Weatherford; SPE Monograph.",
        "confidence": "High"
    },
    "pcp": {
        "system_id": "pcp",
        "name_en": "Progressive Cavity Pump (PCP)",
        "name_ar": "المضخات ذات التجويف التقدمي (PCP)",
        "theory_ar": "مضخة إزاحة إيجابية تتكون من دوار معدني حلزوني الشكل (Rotor) يدور داخل عِضادة مطاطية ذات تجويف حلزوني مزدوج (Stator), مما ينقل السوائل بسلاسة إلى السطح. مرجع: SPE Monograph on PCP.",
        "selection_criteria_ar": [
            "النفط الثقيل واللزج جداً (Heavy & Viscous Oil)",
            "وجود كميات عالية من الرمال (High Sand Production)",
            "معدلات إنتاج متوسطة"
        ],
        "advantages_ar": [
            "كفاءة استثنائية مع النفط الثقيل والرمال",
            "تدفق منتج سلس غير نبضي (Non-pulsating flow)",
            "تكلفة رأس مالية وصيانة منخفضة نسبياً"
        ],
        "limitations_ar": [
            "تأثر العِضادة المطاطية بالحرارة العالية والمذيبات العطرية (Aromatics / Swelling)",
            "محدودية الضغط العالي والعمق الكبير مقارنة بـ ESP",
            "حساسية التشغيل الجاف (حرق المطاط فوراً عند عدم وجود سوائل)"
        ],
        "design_parameters_ar": [
            "سرعة الدوران (RPM)",
            "مواصفات elastomer (درجة تحمل الحرارة والمذيبات)",
            "الإزاحة لكل دورة (Displacement per revolution)"
        ],
        "key_equations_ar": [
            "Flow Rate Q = 4 * e * D * L * N",
            "Torque = f(Pressure Differential, Displacement)"
        ],
        "field_applications_ar": [
            "حقول الرمال النفطية (Oil Sands - SAGD support)",
            "النفط الثقيل في حقول كاليفورنيا وكندا وأمريكا الجنوبية"
        ],
        "troubleshooting_ar": [
            "المشكلة: Stator Swelling/Failure -> الحل: اختيار مادة مطاطية مقاومة للمذيبات ودرجات الحرارة",
            "المشكلة: Dry Running -> الحل: تركيب نظام حماية تلقائي للحرارة والجفاف"
        ],
        "failure_analysis_ar": [
            "تلف المطاط الداخلي بسبب الحرارة الناتجة عن الاحتكاك الجاف",
            "انفصال أو كسر عمود القيادة (Drive string failure)"
        ],
        "reference": "SPE Monograph Series, Progressive Cavity Pumping; Weatherford PCP Engineering Manual.",
        "confidence": "High"
    },
    "hydraulic": {
        "system_id": "hydraulic",
        "name_en": "Hydraulic Jet / Pumping System",
        "name_ar": "المضخات الهيدروليكية ونظام النفث (Hydraulic / Jet Pump)",
        "theory_ar": "استخدام سائل طاقة عالي الضغط (Power Fluid) يُضخ من السطح لتشغيل مضخة قاعية إما عبر محرك هيدروليكي تبادلي أو عبر تأثير فنتوري (Jet Nozzle/Throat) لرفع سوائل المكمن. مرجع: SPE Handbook.",
        "selection_criteria_ar": [
            "الآبار العميقة والنائية",
            "الآبار التي تتطلب غياب الأجزاء الميكانيكية المتحركة المعقدة في القاع (في حالة Jet Pump)",
            "إمكانية استخدام سائل الطاقة من نفس النفط المنتج"
        ],
        "advantages_ar": [
            "لا توجد أعمدة حركة طويلة في البئر",
            "سهولة الاستبدال عبر عكس تدفق سائل الطاقة (Reverse Circulation)",
            "مناسبة للآبار المنحرفة والعميقة جداً"
        ],
        "limitations_ar": [
            "كفاءة طاقة منخفضة نسبياً مقارنة بـ ESP",
            "يتطلب نظام معالجة سطحية لسائل الطاقة (Power Fluid Conditioning)",
            "تعقيد تشغيلي في السطح"
        ],
        "design_parameters_ar": [
            "ضغط ومعدل سائل الطاقة (Power Fluid Pressure & Rate)",
            "حجم الفوهة والحنجرة (Nozzle & Throat Area Ratio in Jet Pumps)"
        ],
        "key_equations_ar": [
            "Jet Pump Momentum Equation: Conservation of momentum between power fluid and entrained fluid in the mixing throat."
        ],
        "field_applications_ar": [
            "الحقول النائية والبرية الصعبة",
            "الآبار العميقة ذات الإنتاج المتوسط"
        ],
        "troubleshooting_ar": [
            "المشكلة: Nozzle Plugging -> الحل: تنشيط ترشيح سائل الطاقة وفلترته بدقة",
            "المشكلة: Low Efficiency -> الحل: إعادة ضبط حجم النفاث (Nozzle sizing)"
        ],
        "failure_analysis_ar": [
            "تآكل الفوهات النفاثة (Nozzle erosion) بسبب الجزيئات الصلبة في سائل الطاقة"
        ],
        "reference": "SPE Petroleum Engineering Handbook, Vol. IV; API Guidelines.",
        "confidence": "High"
    },
    "plunger_lift": {
        "system_id": "plunger_lift",
        "name_en": "Plunger Lift",
        "name_ar": "الرفع المكبسي (Plunger Lift)",
        "theory_ar": "نظام رفع دوري (Cyclic) يعتمد على استخدام مككب حر الصعود والنزول داخل أنابيب الإنتاج, حيث يستغل طاقة ضغط الغاز المكمني لدفع السوائل المتراكمة فوق المكبس إلى السطح دون الحاجة لمصدر طاقة خارجي. مرجع: SPE Monograph.",
        "selection_criteria_ar": [
            "آبار الغاز ذات الإنتاج المنخفض وسوائل متراكمة (Liquid loading in gas wells)",
            "الآبار ذات GOR مرتفع وضغط مكمني متراجع",
            "معدلات إنتاج سوائل منخفضة"
        ],
        "advantages_ar": [
            "تكلفة رأسمالية وتشغيلية منخفضة للغاية (لا يتطلب كهرباء أو وقود)",
            "منع تاراكم السوائل وسد البئر (Liquid loading prevention)",
            "بساطة المكونات وصيانة قليلة"
        ],
        "limitations_ar": [
            "غير مناسب للآبار ذات معدلات إنتاج السوائل العالية",
            "يتطلب طاقة غاز مكمنية كافية لدفع المكبس والعمود إلى السطح",
            "تشغيل دوري وليس مستمراً"
        ],
        "design_parameters_ar": [
            "دورات الفتح والإغلاق (Casing/Tubing Controller Timers)",
            "وزن وتصميم المكبس (Brush/Piston Plunger)",
            "أعماق وموقع مخازن المكبس (Plunger Catcher)"
        ],
        "key_equations_ar": [
            "Critical Gas Rate for Liquid Unloading (Turner Equation): V_crit = 1.917 * (sigma * (rho_l - rho_g) / rho_g^2)^0.25"
        ],
        "field_applications_ar": [
            "حقول الغاز الناضجة في مراحلها الأخيرة",
            "آبار الفحم الحلقي (Coalbed Methane - CBM support)"
        ],
        "troubleshooting_ar": [
            "المشكلة: Plunger sticking -> الحل: إزالة البارافين أو الترسبات من أنابيب الإنتاج",
            "المشكلة: Failure to surface -> الحل: تعديل أوقات الدورات أو فحص ضغط الغاز"
        ],
        "failure_analysis_ar": [
            "تآكل حلقات المكبس (Plunger pads wear)",
            "تراكم البارافين أو الاسكالا مما يعيق حركة المكبس"
        ],
        "reference": "SPE Monograph Series, Plunger Lift; Weatherford Manual.",
        "confidence": "High"
    }
}
