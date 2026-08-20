"""Deterministic Markdown Report V1 for canonical engineering cases."""

from __future__ import annotations

import json
from typing import Any

from services.engineering_case import EngineeringCase, _canonicalize


_REPORT_NOTE = (
    "Model-based deterministic engineering calculation; not measured field data, "
    "a production forecast, an autonomous optimization, or an operating instruction."
)


def _pretty(value: Any) -> str:
    return json.dumps(
        _canonicalize(value), ensure_ascii=False, sort_keys=True,
        indent=2, separators=(",", ": "), allow_nan=False,
    )


def _section(title: str, value: Any) -> list[str]:
    return [f"## {title}", "", "```json", _pretty(value), "```", ""]


def generate_report_v1(case: EngineeringCase) -> str:
    """Return a stable Markdown report derived exclusively from ``case``."""
    if not isinstance(case, EngineeringCase):
        raise TypeError("generate_report_v1 requires an EngineeringCase")

    lines = [
        "# Engineering Case Report V1",
        "",
        "> " + _REPORT_NOTE,
        "",
        "## Case Identity",
        "",
        f"- **Case ID:** `{case.case_id}`",
        f"- **Calculation type:** `{case.calculation_type}`",
        f"- **Status:** `{case.status}`",
        f"- **Release:** `{case.release}`",
        "",
        "## Model and Selectors",
        "",
        f"- **Model:** `{_pretty(case.model)}`",
        f"- **Selectors:** `{_pretty(case.selectors)}`",
        "",
    ]
    lines.extend(_section("Request", case.request))
    lines.extend(_section("Inputs", case.inputs))
    lines.extend(_section("Units", case.units))
    lines.extend(_section("PVT and Provenance", case.pvt))
    lines.extend(_section("Assumptions", case.assumptions))

    lines.extend(["## Result", ""])
    if case.status != "OK" or (
        isinstance(case.result, dict) and "error" in case.result
    ):
        lines.extend([
            "The calculation did not produce a valid engineering operating result.",
            "The typed failure is preserved exactly as case data:",
            "",
            "```json",
            _pretty(case.result),
            "```",
            "",
        ])
    else:
        lines.extend(["```json", _pretty(case.result), "```", ""])

    lines.extend(_section("Limitations", case.limitations))
    lines.extend(_section("Warnings", case.warnings))
    lines.extend(_section("Reproducibility", case.reproducibility))
    lines.extend([
        "## Engineering Honesty",
        "",
        _REPORT_NOTE,
        "",
        "This report preserves the selected model, inputs, units, provenance, "
        "limitations, warnings, and status. It does not add field measurements "
        "or recommendations that are not present in the underlying calculation.",
        "",
    ])
    return "\n".join(lines).rstrip() + "\n"


# Explicit alias for callers that prefer a renderer-style name.
render_report_v1 = generate_report_v1


__all__ = ["generate_report_v1", "render_report_v1"]
