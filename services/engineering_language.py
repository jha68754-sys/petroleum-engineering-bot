"""Deterministic Arabic petroleum-engineering presentation helpers.

This module contains terminology and display translations only.  It does not
calculate, resolve Knowledge records, or change any engineering model.
"""

from __future__ import annotations

import re
from typing import Any


_ARABIC_RE = re.compile(r"[\u0600-\u06FF]")


def is_arabic_text(text: Any) -> bool:
    """Return True when the user message contains Arabic script."""
    return bool(_ARABIC_RE.search(str(text or "")))


def language_for_text(text: Any) -> str:
    return "ar" if is_arabic_text(text) else "en"


_ARABIC_LABELS = {
    "pr": "ضغط المكمن",
    "reservoir_pressure_psia": "ضغط المكمن",
    "thp": "ضغط رأس البئر (THP)",
    "thp_psia": "ضغط رأس البئر (THP)",
    "tvd": "العمق الرأسي الحقيقي",
    "id": "القطر الداخلي لأنبوب الإنتاج",
    "tubing_id_in": "القطر الداخلي لأنبوب الإنتاج",
    "gor": "نسبة الغاز إلى النفط (GOR)",
    "gor_scf_stb": "نسبة الغاز إلى النفط (GOR)",
    "rs": "نسبة الغاز المذاب إلى النفط (Rs)",
    "rs_scf_stb": "نسبة الغاز المذاب إلى النفط (Rs)",
    "api": "درجة API للنفط",
    "oil_api": "درجة API للنفط",
    "gamma_g": "الكثافة النوعية للغاز",
    "gas_specific_gravity": "الكثافة النوعية للغاز",
    "gamma_w": "الكثافة النوعية للماء",
    "water_specific_gravity": "الكثافة النوعية للماء",
    "mu_l": "لزوجة السائل",
    "mu_l_cp": "لزوجة السائل",
    "bo": "معامل حجم تكوين النفط (Bo)",
    "bo_rb_stb": "معامل حجم تكوين النفط (Bo)",
    "bw": "معامل حجم تكوين الماء (Bw)",
    "bw_rb_stb": "معامل حجم تكوين الماء (Bw)",
    "wc": "القطع المائي (Water Cut)",
    "water_cut": "القطع المائي (Water Cut)",
    "j": "معامل الإنتاجية (PI)",
    "q_op": "معدل الإنتاج التشغيلي",
    "operating_rate_bpd": "معدل السائل التشغيلي",
    "operating_rate_stbd": "معدل الإنتاج التشغيلي",
    "calculated_rate_bpd": "معدل السائل المحسوب",
    "predicted_oil_rate_stbd": "معدل النفط المتوقع",
    "pwf_op": "ضغط قاع البئر أثناء الجريان (Pwf)",
    "pwf_psia": "ضغط قاع البئر أثناء الجريان (Pwf)",
    "pwf": "ضغط قاع البئر أثناء الجريان (Pwf)",
    "bottomhole_pressure_psia": "ضغط قاع البئر",
    "bottomhole_pressure_without_lift_psia": "ضغط قاع البئر دون رفع اصطناعي",
    "bottomhole_pressure_with_lift_psia": "ضغط قاع البئر مع الرفع الاصطناعي",
    "wellhead_pressure_psia": "ضغط رأس البئر (Pwh)",
    "upstream_pressure_psia": "ضغط المنبع",
    "downstream_pressure_psia": "ضغط المصب",
    "pressure_ratio": "نسبة الضغط",
    "residual": "المتبقي الضغطي",
    "solver_residual_psi": "المتبقي الضغطي للحل",
    "pressure_residual_psi": "المتبقي الضغطي للحل",
    "choke_size_64th_in": "مقاس الخنّاق (Choke)",
    "liquid_rate_bpd": "معدل السائل المقدم",
    "gas_injection_rate_mscfd": "معدل حقن الغاز",
    "injection_pressure_psia": "ضغط الحقن",
    "average_temperature_f": "متوسط درجة الحرارة",
    "injection_depth_ft": "عمق الحقن",
    "tubing_gradient_psi_ft": "تدرج ضغط أنبوب الإنتاج",
    "t_wh": "درجة حرارة رأس البئر",
    "t_wh_f": "درجة حرارة رأس البئر",
    "geothermal": "التدرج الحراري الأرضي",
    "geothermal_f_100ft": "التدرج الحراري الأرضي",
    "sigma": "التوتر السطحي",
    "q_min": "الحد الأدنى لمعدل الإنتاج",
    "q_max": "الحد الأقصى لمعدل الإنتاج",
    "tol": "سماحية الضغط",
    "pressure_tol": "سماحية الضغط",
    "max_refine_iter": "الحد الأقصى لتكرارات التحسين",
    "objective": "هدف التحسين",
    "variable": "المتغير المقيم",
    "parameter_value": "قيمة المتغير",
    "classification": "التصنيف الهندسي",
    "flow_regime": "نظام الجريان",
    "status": "الحالة الهندسية",
    "reason": "التفسير الهندسي",
    "solver_iterations": "تكرارات الحل",
    "solver_method": "طريقة الحل",
    "n_points": "عدد النقاط المقيمة",
    "segments": "عدد مقاطع الأنبوب",
    "n_segments": "عدد مقاطع الأنبوب",
    "vlp_model": "نموذج الجريان الخارج (VLP)",
    "ipr_model": "نموذج الجريان الداخل (IPR)",
    "choke_model": "ارتباط الخنّاق",
    "base_kwargs": "مدخلات الحالة الأساسية",
    "ipr_kwargs": "مدخلات نموذج الجريان الداخل",
    "sweep": "قيم المسح الهندسي",
    "points": "نقاط التشغيل المقيمة",
}


def arabic_label(key: Any, default: str | None = None) -> str:
    text = str(key)
    if text in _ARABIC_LABELS:
        return _ARABIC_LABELS[text]
    if default and default in _ARABIC_LABELS:
        return _ARABIC_LABELS[default]
    return "بيان هندسي"


_ARABIC_TITLES = {
    "system_v1": "نقطة التشغيل المتكاملة للبئر والخنّاق",
    "integrated_system_v1": "نقطة التشغيل المتكاملة للبئر والخنّاق",
    "choke_v1": "أداء الخنّاق",
    "nodal_v1": "التحليل العقدي",
    "vlp_v1": "أداء الرفع الرأسي",
    "gas_lift_v1": "أداء الرفع بالغاز المستمر",
    "sensitivity_v1": "تحليل الحساسية",
    "optimize_v1": "تحسين الإنتاج",
}


def arabic_calculation_title(calculation_type: Any) -> str:
    return _ARABIC_TITLES.get(str(calculation_type), "حساب هندسي")


_ARABIC_MODELS = {
    "linear": "النموذج الخطي",
    "vogel": "نموذج فوغل",
    "composite": "النموذج المركب",
    "auto": "اختيار تلقائي للنموذج",
    "beggs_brill": "ارتباط بيغز–بريل",
    "gilbert_1954": "ارتباط جيلبرت (1954)",
    "black_oil_v1": "خواص Black-Oil المعتمدة على الضغط",
    "pressure_dependent": "معتمد على الضغط",
    "BlackOilPvtProvider": "مزود خواص Black-Oil",
    "IPR": "الجريان الداخل (IPR)",
    "VLP": "الجريان الخارج (VLP)",
}


def arabic_model_name(value: Any) -> str:
    text = str(value)
    return _ARABIC_MODELS.get(text, _ARABIC_MODELS.get(text.lower(), text))


_ARABIC_NOTES = {
    "bo": "تكون Bo غالبًا أكبر من 1.0 لأن نفط المكمن قد يحتوي على غاز مذاب.",
    "bg": "ينتمي الثابت العددي إلى اصطلاح وحدات حقلية محدد؛ لذلك يجب بيان الوحدات المستخدمة.",
    "bw": "تعتمد القيمة على حالة المائع، ولا ينبغي افتراض ثباتها من دون بيان هذا الافتراض.",
    "rs": "لا تساوي Rs نسبة الغاز إلى النفط المنتج؛ فقد تشمل النسبة المنتجة غازًا حرًا.",
    "gor": "يعرّف هذا المصطلح نسبة الغاز المنتج إلى النفط المنتج وفق أساس القياس المعلن.",
    "rp": "يجب بيان فترة التقرير والظروف القياسية عند استخدام هذه النسبة التراكمية.",
}

_ARABIC_LIMITATIONS = {
    "bo": "تحتاج قيمة Bo الرقمية إلى حالة مائع محددة وطريقة PVT معتمدة؛ وسجل المصطلح شرحٌ وليس حاسبة PVT مستقلة.",
    "bg": "تحتاج قيمة Bg الرقمية إلى ضغط ودرجة حرارة وطريقة معتمدة لتقييم خواص الغاز.",
    "bw": "لا يحسب هذا السجل قيمة Bw من الملوحة أو الضغط أو درجة الحرارة.",
    "rs": "تحتاج قيمة Rs الرقمية إلى حالة PVT محددة واصطلاح فصل معلن.",
    "gor": "قد تكون قيمة GOR غامضة من دون بيان الظروف القياسية والأساس الزمني للقياس.",
    "rp": "لا تُستنتج قيمة رقمية من دون بيانات إنتاج محددة.",
}


def arabic_note(value: Any) -> str:
    return _ARABIC_NOTES.get(str(value).lower(), "يجب تفسير هذه الخاصية عند حالة مائع ووحدات قياس معلنة.")


def arabic_limitation(value: Any) -> str:
    return _ARABIC_LIMITATIONS.get(str(value).lower(), "لا تُستنتج قيمة رقمية من سجل الشرح وحده؛ يجب تحديد المدخلات والطريقة الهندسية المعتمدة.")


def arabic_status(value: Any) -> str:
    statuses = {
        "OK": "مكتملة بنجاح",
        "CONVERGED": "متقاربة",
        "UNIQUE_OPERATING_POINT": "نقطة تشغيل وحيدة",
        "CRITICAL": "جريان حرج",
        "SUBCRITICAL": "جريان دون حرج",
        "NO_OPERATING_POINT": "لا توجد نقطة تشغيل",
        "PHYSICALLY_INVALID_STATE": "حالة فيزيائية غير صالحة",
    }
    return statuses.get(str(value), str(value))


def arabic_domain(value: Any) -> str:
    mapping = {
        "PVT": "خواص الموائع (PVT)",
        "Production": "هندسة الإنتاج",
        "Reservoir / Rock": "المكمن والصخر",
        "PVT / Reservoir": "خواص الموائع والمكمن",
        "Artificial Lift / Production": "الرفع الاصطناعي والإنتاج",
        "PVT / Fluid Characterization": "خواص الموائع وتوصيفها",
    }
    return mapping.get(str(value), str(value))


def arabic_source_heading() -> str:
    return "أساس التحقق والمصدر"


__all__ = [
    "arabic_calculation_title",
    "arabic_domain",
    "arabic_label",
    "arabic_limitation",
    "arabic_note",
    "arabic_model_name",
    "arabic_source_heading",
    "arabic_status",
    "is_arabic_text",
    "language_for_text",
]
