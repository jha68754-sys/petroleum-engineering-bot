"""Deterministic workflow intents and result interpretation for Core V2.

This module is deliberately limited to routing and presentation.  It does not
calculate, call AI, mutate cases, or select an engineering model.  Execution
remains in the released handlers and engines; this module only recognizes a
small allow-list of natural intents and compares already-calculated Case data.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Tuple

from services.engineering_case import EngineeringCase, canonical_json
from services.engineering_report import _KEY_LABELS, _UNIT_BY_KEY
from services.engineering_language import arabic_label, arabic_model_name, arabic_status


class WorkflowError(ValueError):
    """Typed, user-safe error for a bounded natural workflow request."""

    def __init__(self, code: str, message: str):
        self.code = str(code)
        self.message = str(message)
        super().__init__(f"{self.code}: {self.message}")


def guided_missing_thp_message(*, language: str = "en") -> str:
    """Explain the next required input without inferring a value."""
    if str(language).lower() in {"ar", "arabic", "العربية"}:
        return (
            "إرشاد الحساب الهندسي\n"
            "====================\n"
            "الحالة: MISSING_DATA — قيمة THP مطلوبة.\n\n"
            "أستطيع إعادة حساب معدل الإنتاج من الحالة الهندسية الحالية، "
            "لكن يجب تحديد THP صراحةً.\n\n"
            "أرسل قيمة ضغط رأس البئر بوحدة psia، مثل:\n"
            "احسب الإنتاج عند THP=200 psia\n\n"
            "لم أستخدم قيمة افتراضية ولم أستنتج قيمة من السياق."
        )
    return (
        "Engineering Calculation Guidance\n"
        "=================================\n"
        "Status: MISSING_DATA — THP value required.\n\n"
        "I can recalculate production from the current engineering case, "
        "but the THP value must be explicit.\n\n"
        "Provide wellhead pressure in psia, for example:\n"
        "calculate production at THP=200 psia\n\n"
        "No default or inferred value was used."
    )


@dataclass(frozen=True)
class WorkflowIntent:
    """Allow-listed natural-language intent; no free-form calculation parsing."""

    kind: str
    thp_psia: Optional[float] = None


_CALCULATION_PATTERNS = (
    re.compile(r"\b(?:calculate|compute)\s+(?:the\s+)?(?:production|rate|liquid\s+rate)\b", re.IGNORECASE),
    re.compile(r"\bcalculate\b.*\b(?:production|rate)\b", re.IGNORECASE),
    re.compile(r"احسب(?:لي|لنا)?\s+(?:الإنتاج|المعدل|الانتاج|معدل\s+الإنتاج|معدل\s+الانتاج)"),
)
_ARABIC_CALCULATION_MARKERS = (
    "احسب الإنتاج",
    "احسب الانتاج",
    "احسب معدل الإنتاج",
    "احسب معدل الانتاج",
    "احسب المعدل",
    "احسبلي الإنتاج",
    "احسبلي الانتاج",
)
_INTERPRETATION_PHRASES = (
    "what changed",
    "what has changed",
    "difference between the results",
    "difference between current and previous",
    "why did production change",
    "why did the rate change",
    "impact of changing thp",
    "effect of changing thp",
    "what is the effect of thp",
    "ماذا تغير",
    "ما الذي تغير",
    "ما الذي تغيّر",
    "شن تغير",
    "ما الفرق بين النتائج",
    "شن الفرق بين النتائج",
    "لماذا تغير الإنتاج",
    "لماذا تغير الانتاج",
    "شن تأثير تغيير thp",
    "ما تأثير تغيير thp",
    "تأثير تغيير thp",
)
_THP_RE = re.compile(
    r"(?:\bthp\b|ضغط\s*رأس\s*البئر|ضغط\s*رأس\s*البئر\s*السطحي)"
    r"\s*(?:=|to|at|عند|إلى|الى)\s*"
    r"(-?\d+(?:\.\d+)?)\s*(psia|psi)\b",
    re.IGNORECASE,
)

# Only result fields that are meaningful for a compact engineering delta.  The
# source labels and units are reused from the released report renderer rather
# than duplicated here.
_RESULT_METRICS: Tuple[Tuple[str, str], ...] = (
    ("operating_rate_bpd", "rate"),
    ("q_op", "rate"),
    ("calculated_rate_bpd", "rate"),
    ("pwf_psia", "pressure"),
    ("pwf_op", "pressure"),
    ("wellhead_pressure_psia", "pressure"),
    ("upstream_pressure_psia", "pressure"),
    ("downstream_pressure_psia", "pressure"),
    ("solver_residual_psi", "residual"),
    ("residual", "residual"),
)


def _normalise_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text).casefold()).strip()


def parse_workflow_intent(text: str) -> Optional[WorkflowIntent]:
    """Recognize only explicit, bounded natural workflow intents."""
    normalized = _normalise_text(text)
    if not normalized or normalized.startswith("/"):
        return None

    if any(phrase in normalized for phrase in _INTERPRETATION_PHRASES):
        return WorkflowIntent(kind="interpret")

    if any(marker in normalized for marker in _ARABIC_CALCULATION_MARKERS) or any(
        pattern.search(normalized) for pattern in _CALCULATION_PATTERNS
    ):
        match = _THP_RE.search(normalized)
        thp = float(match.group(1)) if match else None
        if match and match.group(2).lower() != "psia":
            raise WorkflowError("INVALID_UNIT", "natural THP calculation requires psia")
        return WorkflowIntent(kind="natural_calculation", thp_psia=thp)

    return None


def _result(case: EngineeringCase) -> Mapping[str, Any]:
    return case.result if isinstance(case.result, Mapping) else {}


def _inputs(case: EngineeringCase) -> Mapping[str, Any]:
    return case.inputs if isinstance(case.inputs, Mapping) else {}


def _model_signature(case: EngineeringCase) -> str:
    return canonical_json({
        "calculation_type": case.calculation_type,
        "model": case.model,
        "selectors": case.selectors,
        "pvt": case.pvt,
    })


def _display_number(value: Any) -> str:
    if isinstance(value, bool):
        return str(value)
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if not math.isfinite(number):
        return "not finite"
    if number.is_integer():
        return f"{int(number):,}"
    return f"{number:,.6g}"


def _format_metric(key: str, value: Any) -> str:
    label = _KEY_LABELS.get(key, key.replace("_", " ").title())
    unit = _UNIT_BY_KEY.get(key)
    rendered = _display_number(value)
    return f"{label}: {rendered}{(' ' + unit) if unit else ''}"


def _metric_value(result: Mapping[str, Any], key: str) -> Any:
    if key in result:
        return result[key]
    # System and comparison payloads use both q_op and operating_rate_bpd in
    # different released surfaces.  The allow-list above keeps this fallback
    # explicit and deterministic.
    return None


def _metric_deltas(previous: EngineeringCase, current: EngineeringCase) -> list[tuple[str, Any, Any, float | None, str]]:
    left = _result(previous)
    right = _result(current)
    deltas: list[tuple[str, Any, Any, float | None, str]] = []
    seen: set[str] = set()
    for key, category in _RESULT_METRICS:
        if key in seen:
            continue
        seen.add(key)
        before = _metric_value(left, key)
        after = _metric_value(right, key)
        if before is None or after is None:
            continue
        try:
            delta = float(after) - float(before)
        except (TypeError, ValueError):
            continue
        if math.isclose(delta, 0.0, abs_tol=1e-12):
            continue
        deltas.append((key, before, after, delta, category))
    return deltas


def _input_differences(previous: EngineeringCase, current: EngineeringCase) -> list[tuple[str, Any, Any]]:
    left = _inputs(previous)
    right = _inputs(current)
    differences: list[tuple[str, Any, Any]] = []
    for key in sorted(set(left) | set(right)):
        before = left.get(key)
        after = right.get(key)
        if canonical_json(before) != canonical_json(after):
            differences.append((str(key), before, after))
    return differences


_INPUT_LABEL_ALIASES = {
    "choke": "choke_size_64th_in",
    "choke_size": "choke_size_64th_in",
    "p_down": "downstream_pressure_psia",
    "p_up": "upstream_pressure_psia",
    "id": "tubing_id_in",
    "tvd": "tvd",
    "gor": "gor_scf_stb",
    "rs": "rs_scf_stb",
    "api": "api",
    "gamma_g": "gamma_g",
    "mu_l": "mu_l_cp",
    "bo": "bo_rb_stb",
    "t_wh": "t_wh",
    "geothermal": "geothermal",
}


def _label_key(key: str) -> str:
    return _INPUT_LABEL_ALIASES.get(key, key)


def _unit_for_input(key: str) -> Optional[str]:
    return _UNIT_BY_KEY.get(_label_key(key))


def _format_input_difference(key: str, before: Any, after: Any) -> str:
    label_key = _label_key(key)
    label = _KEY_LABELS.get(label_key, key.replace("_", " ").title())
    unit = _unit_for_input(key)
    unit_text = f" {unit}" if unit else ""
    return f"{label}: {_display_number(before)}{unit_text} → {_display_number(after)}{unit_text}"


def _format_delta_ar(key: str, before: Any, after: Any, delta: float, category: str) -> str:
    unit = _UNIT_BY_KEY.get(key)
    if category == "rate" and key == "calculated_rate_bpd":
        unit = "bbl/day"
    if category == "pressure":
        unit = "psia"
    if category == "residual":
        unit = "psi"
    unit_text = f" {unit}" if unit else ""
    percent = ""
    try:
        before_number = float(before)
        if not math.isclose(before_number, 0.0, abs_tol=1e-12):
            percent = f" ({(delta / before_number) * 100:+.3f}%)"
    except (TypeError, ValueError):
        pass
    return (
        f"- {arabic_label(key)}: قبل {_display_number(before)}{unit_text}؛ "
        f"بعد {_display_number(after)}{unit_text}؛ الفارق {delta:+,.6g}{unit_text}{percent}"
    )


def _format_delta(key: str, before: Any, after: Any, delta: float, category: str) -> str:
    unit = _UNIT_BY_KEY.get(key)
    if category == "rate" and key == "calculated_rate_bpd":
        unit = "bbl/day"
    if category == "pressure":
        unit = "psia"
    if category == "residual":
        unit = "psi"
    delta_text = f"{delta:+,.6g}{(' ' + unit) if unit else ''}"
    percent = ""
    try:
        before_number = float(before)
        if not math.isclose(before_number, 0.0, abs_tol=1e-12):
            percent = f" ({(delta / before_number) * 100:+.3f}%)"
    except (TypeError, ValueError):
        pass
    return (
        f"- {_format_metric(key, before)} → {_format_metric(key, after)}"
        f" | Delta: {delta_text}{percent}"
    )


def _render_result_interpretation_ar(previous: EngineeringCase, current: EngineeringCase) -> str:
    if previous.status != "OK" or current.status != "OK":
        return (
            "تفسير النتيجة الهندسية\n"
            "=====================\n"
            f"حالة الحالة السابقة: {arabic_status(previous.status)}\n"
            f"حالة الحالة الحالية: {arabic_status(current.status)}\n\n"
            "لم يُنتج تفسير عددي لأن الحالتين يجب أن تكونا بحالة OK."
        )
    input_changes = _input_differences(previous, current)
    result_changes = _metric_deltas(previous, current)
    model_changed = _model_signature(previous) != _model_signature(current)
    lines = [
        "تفسير النتيجة الهندسية",
        "=====================",
        "مقارنة حتمية بين حالتين هندسيتين محفوظتين.",
        "",
        f"الحالة السابقة: {previous.case_id}",
        f"الحالة الحالية: {current.case_id}",
        f"نوع الحساب: {current.calculation_type}",
        "",
        "الفروق في المدخلات الهندسية",
    ]
    if input_changes:
        for key, before, after in input_changes[:12]:
            label_key = _label_key(key)
            label = arabic_label(label_key)
            unit = _unit_for_input(key)
            unit_text = f" {unit}" if unit else ""
            lines.append(
                f"- {label}: {_display_number(before)}{unit_text} → {_display_number(after)}{unit_text}"
            )
        if len(input_changes) > 12:
            lines.append(f"- فروق إضافية في المدخلات: {len(input_changes) - 12}")
    else:
        lines.append("- لم يُرصد فرق في مدخلات الحالتين المحفوظتين.")
    lines.extend(["", "الفروق في النتائج المحسوبة"])
    if result_changes:
        lines.extend(_format_delta_ar(key, before, after, delta, category) for key, before, after, delta, category in result_changes)
    else:
        lines.append("- لم يُرصد فرق عددي في مقاييس النتيجة المختارة.")
    lines.extend(["", "التفسير الهندسي"])
    if result_changes and input_changes:
        changed_names = "، ".join(arabic_label(_label_key(key)) for key, _, _ in input_changes[:6])
        lines.append(
            "تختلف الحالة الحالية عن السابقة في المدخلات المحفوظة التالية: "
            f"{changed_names}. وتمثل الفروق المذكورة استجابة النموذج الحتمي المختار لهذه المدخلات المتغيرة."
        )
    elif result_changes:
        lines.append(
            "تختلف مقاييس النتيجة المحفوظة، لكن لم يُعثر على فرق في مدخلات الحالتين؛ "
            "لذلك تُعامل الحالة كنقطة مراجعة لقابلية إعادة الإنتاج ولا يُستنتج سبب سببي."
        )
    else:
        lines.append("لم تتغير مقاييس النتيجة المختارة بين الحالتين، ولا يُستنتج من ذلك استنتاج فيزيائي إضافي.")
    if model_changed:
        lines.append("تختلف أيضًا محددات النموذج أو اختيار الموديل أو مصدر خواص الموائع، ويجب أخذ ذلك في الاعتبار عند قراءة الفروق.")
    else:
        lines.append("محددات النموذج ومصدر خواص الموائع لم تتغير بين الحالتين.")
    lines.extend([
        "",
        "ملاحظة النطاق: هذه مقارنة حتمية لنموذج هندسي، وليست بيانات حقلية مقاسة أو توقعًا أو تعليمات تشغيلية.",
        "لم تُستنتج أي توصية أو خطوة تشغيلية.",
    ])
    return "\n".join(lines)


def render_result_interpretation(
    previous: EngineeringCase,
    current: EngineeringCase,
    *,
    language: str = "en",
) -> str:
    """Render a traceable, non-prescriptive interpretation of two Cases."""
    if str(language).lower() in {"ar", "arabic", "العربية"}:
        return _render_result_interpretation_ar(previous, current)
    if previous.status != "OK" or current.status != "OK":
        return (
            "Engineering Result Interpretation\n"
            "===============================\n"
            f"Previous case status: {previous.status}\n"
            f"Current case status: {current.status}\n\n"
            "A numeric interpretation was not produced because both referenced "
            "cases must have status OK."
        )

    input_changes = _input_differences(previous, current)
    result_changes = _metric_deltas(previous, current)
    model_changed = _model_signature(previous) != _model_signature(current)

    lines = [
        "Engineering Result Interpretation",
        "===============================",
        "Deterministic comparison of two stored engineering cases.",
        "",
        f"Previous Case: {previous.case_id}",
        f"Current Case: {current.case_id}",
        f"Calculation type: {current.calculation_type}",
        "",
        "INPUT DIFFERENCES",
    ]
    if input_changes:
        lines.extend(f"- {_format_input_difference(key, before, after)}" for key, before, after in input_changes[:12])
        if len(input_changes) > 12:
            lines.append(f"- Additional input differences: {len(input_changes) - 12}")
    else:
        lines.append("- No input difference detected in the stored case inputs.")

    lines.extend(["", "CALCULATED RESULT DIFFERENCES"])
    if result_changes:
        lines.extend(_format_delta(key, before, after, delta, category) for key, before, after, delta, category in result_changes)
    else:
        lines.append("- No numeric difference detected in the selected result metrics.")

    lines.extend(["", "ENGINEERING INTERPRETATION"])
    if result_changes and input_changes:
        changed_names = ", ".join(_KEY_LABELS.get(_label_key(key), key) for key, _, _ in input_changes[:6])
        lines.append(
            "The current case differs from the previous case in the stored input "
            f"field(s): {changed_names}. The listed result deltas are the deterministic "
            "response of the selected released model to those changed inputs."
        )
    elif result_changes:
        lines.append(
            "The stored result metrics differ, but no input difference was found in "
            "the compared envelopes. Treat this as a reproducibility review item; "
            "no causal explanation is inferred."
        )
    else:
        lines.append(
            "The selected result metrics did not change between the two stored cases. "
            "No additional physical conclusion is inferred."
        )

    if model_changed:
        lines.append("Model, selector, or PVT provenance also differs between the cases and must be considered when reading the deltas.")
    else:
        lines.append("Model selectors and PVT provenance are unchanged between the cases.")

    lines.extend([
        "",
        "Scope note: this is a deterministic model comparison, not measured field data, a forecast, or an operating instruction.",
        "No recommendation or operating action was inferred.",
    ])
    return "\n".join(lines)


__all__ = [
    "WorkflowError",
    "WorkflowIntent",
    "guided_missing_thp_message",
    "parse_workflow_intent",
    "render_result_interpretation",
]
