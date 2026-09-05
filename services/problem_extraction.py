"""Deterministic extraction of petroleum-engineering values from free text.

This module is intentionally not a numerical engine and does not call an LLM.
It extracts only explicit values stated by the user, preserves provenance, and
returns a confirmation-ready summary before any calculation is attempted.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Dict, Iterable, List, Optional, Tuple


@dataclass(frozen=True)
class ExtractedField:
    key: str
    label: str
    value: float
    unit: str
    source: str = "USER_PROVIDED_FREE_TEXT"


_FIELD_SPECS: Tuple[Tuple[str, str, str, Tuple[str, ...]], ...] = (
    ("pr", "ضغط المكمن (Pr)", "psia", (r"reservoir\s+pressure", r"\bpr\b", r"ضغط\s+(?:المكمن|الخزان)")),
    ("thp", "ضغط رأس البئر (THP)", "psia", (r"tubing[-\s]*head\s+pressure", r"\bthp\b", r"ضغط\s+رأس\s+البئر")),
    ("tvd", "العمق الرأسي الحقيقي (TVD)", "ft", (r"true\s+vertical\s+depth", r"\btvd\b", r"العمق\s+الرأسي")),
    ("id", "القطر الداخلي للأنبوب (Tubing ID)", "in", (r"tubing\s+(?:inside\s+)?diameter", r"tubing\s+id", r"\bid\b", r"قطر\s+(?:الأنبوب|أنبوب\s+الإنتاج)")),
    ("gor", "نسبة الغاز إلى النفط (GOR)", "scf/STB", (r"gas[-\s]*oil\s+ratio", r"\bgor\b", r"نسبة\s+الغاز\s+إلى\s+النفط")),
    ("rs", "نسبة الغاز المذاب إلى النفط (Rs)", "scf/STB", (r"solution\s+gas[-\s]*oil\s+ratio", r"\brs\b", r"نسبة\s+الغاز\s+المذاب")),
    ("api", "درجة API", "deg API", (r"api\s+gravity", r"\bapi\b", r"درجة\s+api")),
    ("gamma_g", "الكثافة النوعية للغاز", "specific gravity", (r"gas\s+specific\s+gravity", r"gamma[_\s-]*g", r"كثافة\s+الغاز\s+النوعية")),
    ("mu_l", "لزوجة السائل", "cP", (r"liquid\s+viscosity", r"mu[_\s-]*l", r"لزوجة\s+السائل")),
    ("bo", "معامل حجم تكوين النفط (Bo)", "rb/STB", (r"oil\s+formation[-\s]*volume\s+factor", r"\bbo\b", r"معامل\s+حجم\s+تكوين\s+النفط")),
    ("t_wh", "درجة حرارة رأس البئر", "degF", (r"wellhead\s+temperature", r"t[_\s-]*wh", r"درجة\s+حرارة\s+رأس\s+البئر")),
    ("geothermal", "التدرج الحراري الأرضي", "degF/100ft", (r"geothermal", r"التدرج\s+الحراري")),
    ("choke", "مقاس Choke", "64ths of inch", (r"choke\s+(?:size|bean)", r"\bchoke\b", r"مقاس\s+الخنّاق")),
    ("p_down", "ضغط المصب", "psia", (r"downstream\s+pressure", r"p[_\s-]*down", r"ضغط\s+المصب")),
    ("j", "معامل الإنتاجية (PI)", "STB/day/psi", (r"productivity\s+index", r"\bpi\b", r"\bj\b", r"معامل\s+الإنتاجية")),
    ("qmax", "معدل الإنتاج الأقصى (qmax)", "STB/day", (r"maximum\s+(?:oil|liquid\s+)?rate", r"q[_\s-]*max", r"معدل\s+الإنتاج\s+الأقصى")),
    ("q_test", "معدل اختبار الإنتاج", "STB/day", (r"test\s+(?:production\s+)?rate", r"q[_\s-]*test", r"معدل\s+اختبار\s+الإنتاج")),
    ("pwf_test", "ضغط قاع البئر في الاختبار", "psia", (r"test\s+flowing\s+bottomhole\s+pressure", r"pwf[_\s-]*test", r"ضغط\s+قاع\s+البئر\s+في\s+الاختبار")),
    ("wc", "القطع المائي (Water Cut)", "fraction", (r"water\s+cut", r"\bwc\b", r"القطع\s+المائي")),
)

_NUMBER = r"(-?\d+(?:[.,]\d+)?)"
_ASSIGNMENT = r"\s*(?:(?:is|=|:|equals|equal\s+to|حوالي|تقريبًا|تقريبا|يساوي|يعادل)\s*)?"


def _number(value: str) -> Optional[float]:
    try:
        raw = str(value).strip()
        if "," in raw and "." not in raw:
            # In Arabic prose a comma is commonly a decimal separator; retain
            # thousand separators only when three digits follow the comma.
            tail = raw.rsplit(",", 1)[1]
            raw = raw.replace(",", "" if len(tail) == 3 else ".")
        else:
            raw = raw.replace(",", "")
        return float(raw)
    except (TypeError, ValueError):
        return None


def _matches(text: str, aliases: Iterable[str]) -> List[Tuple[int, str]]:
    found: List[Tuple[int, str]] = []
    for alias in aliases:
        # Python's Unicode word boundary does not split Arabic letters from
        # Latin abbreviations in strings such as "وTHP". Use ASCII-aware
        # boundaries for petroleum abbreviations instead.
        if r"\b" in alias:
            alias = (
                r"(?<![A-Za-z0-9_])"
                + alias.replace(r"\b", "")
                + r"(?![A-Za-z0-9_])"
            )
        pattern = re.compile(alias + _ASSIGNMENT + _NUMBER, re.IGNORECASE)
        for match in pattern.finditer(text):
            value = _number(match.group(1))
            if value is not None:
                found.append((match.start(), match.group(1)))
    return found


def extract_engineering_fields(text: str) -> List[ExtractedField]:
    """Extract explicit numeric engineering values, retaining first mention."""
    if not isinstance(text, str):
        return []
    fields: List[ExtractedField] = []
    for key, label, unit, aliases in _FIELD_SPECS:
        matches = _matches(text, aliases)
        if not matches:
            continue
        _, raw_value = sorted(matches, key=lambda item: item[0])[0]
        value = _number(raw_value)
        if value is not None:
            fields.append(ExtractedField(key, label, value, unit))
    return fields


def _fmt(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:g}"


def format_problem_extraction(text: str) -> str:
    """Return an Arabic confirmation-ready extraction report."""
    fields = extract_engineering_fields(text)
    by_key: Dict[str, ExtractedField] = {field.key: field for field in fields}
    lines = [
        "تحليل وصف مشكلة البئر — استخراج أولي",
        "====================================",
        "",
        "لم أشغّل أي محرك حسابي بعد. استخرجت فقط القيم الرقمية المذكورة صراحةً في النص.",
        "كل قيمة أدناه مصدرها نص المستخدم، وتحتاج إلى تأكيد قبل استعمالها في الحساب.",
        "",
    ]
    if fields:
        lines.append("البيانات الهندسية المستخرجة")
        lines.append("----------------------------")
        for field in fields:
            lines.append(f"- {field.label}: {_fmt(field.value)} {field.unit} | المصدر: المستخدم")
    else:
        lines.extend([
            "لم أجد قيمة هندسية رقمية واضحة في النص.",
            "اذكر القيمة مع اسمها ووحدتها، مثل: Pr=3200 psia أو THP=180 psia.",
        ])

    lines.extend(["", "مؤشرات المشكلة المذكورة في النص", "-------------------------------"])
    lowered = text.casefold()
    indicators: List[str] = []
    if any(term in lowered for term in ("انخفض", "انخفاض", "drop", "decline", "decrease")):
        indicators.append("وردت إشارة إلى انخفاض أو تراجع في الإنتاج.")
    if any(term in lowered for term in ("ضغط", "pressure", "thp", "pwf")):
        indicators.append("وردت إشارة إلى مشكلة أو تغير متعلق بالضغط.")
    if any(term in lowered for term in ("choke", "خنّاق", "الخنّاق")):
        indicators.append("وردت إشارة إلى Choke أو تغيّر في مقاسه.")
    if indicators:
        lines.extend(f"- {indicator}" for indicator in indicators)
    else:
        lines.append("- لم أحدد مؤشر مشكلة بصيغة واضحة؛ هذا لا يعني عدم وجود مشكلة.")

    lines.extend(["", "بيانات يلزم التحقق منها قبل الحساب", "---------------------------------"])
    required = ("pr", "thp", "tvd", "id", "gor", "rs", "api", "gamma_g", "mu_l", "bo", "t_wh", "geothermal", "choke", "p_down")
    missing = [key for key in required if key not in by_key]
    if missing:
        labels = {key: next(spec[1] for spec in _FIELD_SPECS if spec[0] == key) for key in missing}
        lines.append("- قيم غير مذكورة: " + "؛ ".join(labels.values()))
    if "j" not in by_key and "qmax" not in by_key and not ({"q_test", "pwf_test"} <= by_key.keys()):
        lines.append("- يلزم اختيار أساس IPR: PI، أو qmax، أو زوج q_test وpwf_test.")
    if not missing and ("j" in by_key or "qmax" in by_key or {"q_test", "pwf_test"} <= by_key.keys()):
        lines.append("- لم تظهر فجوة واضحة في مجموعة مدخلات System الأساسية، لكن يجب مراجعة الوحدات والقيم.")

    lines.extend([
        "",
        "الخطوة التالية",
        "--------------",
        "إذا كانت البيانات صحيحة، أرسل: اعتمد البيانات المستخرجة.",
        "بعد الاعتماد يمكن تحديد نوع الحساب، مثل: احسب نقطة التشغيل باستخدام Linear IPR.",
        "لم أستنتج سبب المشكلة ولم أُنشئ نتيجة رقمية من النص وحده.",
    ])
    return "\n".join(lines)


__all__ = ["ExtractedField", "extract_engineering_fields", "format_problem_extraction"]


if __name__ == "__main__":
    import sys
    print(format_problem_extraction(" ".join(sys.argv[1:])))
