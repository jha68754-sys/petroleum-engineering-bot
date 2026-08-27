"""Deterministic preflight checks for user-facing engineering inputs.

This module is deliberately limited to obvious data-quality failures. It does
not replace or duplicate any petroleum-engineering engine validation, equation,
correlation, solver, or numerical method.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping, Optional


@dataclass(frozen=True)
class QualityIssue:
    """A concise, user-safe preflight issue."""

    field: str
    code: str
    message: str
    severity: str = "ERROR"


# These are generic domain checks only. Engine-specific admissibility remains
# owned by the released engine contracts.
_POSITIVE_FIELDS = {
    "pr": "Reservoir pressure (Pr)",
    "thp": "Tubing-head pressure (THP)",
    "thp_guess": "Tubing-head pressure (THP)",
    "tvd": "True vertical depth (TVD)",
    "id": "Tubing inside diameter",
    "tubing_id_in": "Tubing inside diameter",
    "gor": "Gas-oil ratio (GOR)",
    "rs": "Solution gas-oil ratio (Rs)",
    "gamma_g": "Gas specific gravity",
    "mu_l": "Liquid viscosity",
    "bo": "Oil formation-volume factor (Bo)",
    "choke": "Choke size",
    "choke_size": "Choke size",
    "choke_size_64th_in": "Choke size",
    "j": "Productivity index (J)",
    "qmax": "Maximum rate (qmax)",
    "q_test": "Test rate (q_test)",
    "pwf_test": "Test flowing pressure (Pwf_test)",
    "gamma_w": "Water specific gravity",
    "bw": "Water formation-volume factor (Bw)",
    "z": "Gas compressibility factor (Z)",
    "z_factor": "Gas compressibility factor (Z)",
    "q_min": "Minimum production rate",
    "pressure_tol": "Pressure tolerance",
}

_NON_NEGATIVE_FIELDS = {
    "p_down": "Downstream pressure",
    "downstream_pressure_psia": "Downstream pressure",
    "wc": "Water cut",
    "sigma": "Surface tension",
    "q_max": "Maximum rate",
}

_FRACTION_FIELDS = {"wc": "Water cut"}


def _numeric(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def validate_numeric_inputs(values: Mapping[str, Any]) -> list[QualityIssue]:
    """Return only obvious preflight issues for already-parsed numeric values."""
    issues: list[QualityIssue] = []
    for raw_key, raw_value in values.items():
        key = str(raw_key).strip().lower()
        if key in {"model", "vlp_model", "choke_model", "case", "report", "plot"}:
            continue
        number = _numeric(raw_value)
        if number is None:
            # The released parser owns malformed-token handling. Do not add a
            # second parser or change its established missing-data behavior.
            continue

        if key in _POSITIVE_FIELDS and number <= 0:
            issues.append(QualityIssue(
                field=_POSITIVE_FIELDS[key],
                code="NON_POSITIVE_VALUE",
                message="must be greater than zero.",
            ))
            continue
        if key in _NON_NEGATIVE_FIELDS and number < 0:
            issues.append(QualityIssue(
                field=_NON_NEGATIVE_FIELDS[key],
                code="NEGATIVE_VALUE",
                message="cannot be negative.",
            ))
            continue
        if key in _FRACTION_FIELDS and not 0.0 <= number <= 1.0:
            issues.append(QualityIssue(
                field=_FRACTION_FIELDS[key],
                code="OUT_OF_RANGE",
                message="must be between 0 and 1.",
            ))
            continue
        if key == "api" and not 0.0 <= number <= 100.0:
            issues.append(QualityIssue(
                field="Oil API gravity",
                code="OUT_OF_RANGE",
                message="must be between 0 and 100 deg API.",
            ))
            continue
        if key in {"t_wh", "temperature_f"} and number <= -459.67:
            issues.append(QualityIssue(
                field="Temperature",
                code="BELOW_ABSOLUTE_ZERO",
                message="must be above absolute zero in Fahrenheit.",
            ))
            continue
        if key in {"segments", "n_segments"} and int(number) != number:
            issues.append(QualityIssue(
                field="Tubing segments",
                code="NOT_INTEGER",
                message="must be a whole number.",
            ))
            continue
        if key in {"n_points"} and int(number) != number:
            issues.append(QualityIssue(
                field="Evaluated points",
                code="NOT_INTEGER",
                message="must be a whole number.",
            ))
            continue
        if key in {"max_refine_iter"} and int(number) != number:
            issues.append(QualityIssue(
                field="Maximum refinement iterations",
                code="NOT_INTEGER",
                message="must be a whole number.",
            ))

    return issues


def format_quality_issues(issues: list[QualityIssue], *, language: str = "en") -> str:
    """Render a deterministic, concise quality-gate response."""
    if str(language).lower() in {"ar", "arabic", "العربية"}:
        lines = [
            "بوابة جودة البيانات الهندسية",
            "============================",
            "توقّف الحساب قبل استدعاء المحرك بسبب مشكلة واضحة في المدخلات.",
            "",
        ]
        for issue in issues:
            lines.append(f"- {issue.field}: {issue.message} ({issue.code})")
        lines.extend([
            "",
            "لم تُحسب نتيجة، ولم تُستنتج قيمة بديلة. صحّح المدخلات ثم أعد الطلب.",
        ])
        return "\n".join(lines)

    lines = [
        "Engineering Data Quality Gate",
        "==============================",
        "Calculation stopped before the engine because an obvious input-quality issue was found.",
        "",
    ]
    for issue in issues:
        lines.append(f"- {issue.field}: {issue.message} ({issue.code})")
    lines.extend([
        "",
        "No result was calculated and no replacement value was inferred. Correct the inputs and retry.",
    ])
    return "\n".join(lines)


__all__ = ["QualityIssue", "validate_numeric_inputs", "format_quality_issues"]
