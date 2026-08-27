"""Portable, secret-free Markdown snapshots for stored Engineering Cases.

The snapshot is an export/presentation layer. It does not recalculate, mutate,
or create a second persistence system.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from services.engineering_case import EngineeringCase
from services.engineering_context import input_origins_for_case
from services.engineering_report import generate_report_v1


_SNAPSHOT_SCHEMA = "portable_engineering_case_snapshot_v1"


def _safe_value(value: Any) -> str:
    if value is None:
        return "not recorded"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float, str)):
        return str(value).replace("\r", " ").replace("\n", " ")
    return "recorded"


def _mapping_lines(title: str, values: Any) -> list[str]:
    lines = [f"## {title}", ""]
    if not isinstance(values, Mapping) or not values:
        lines.append("Not recorded.")
        lines.append("")
        return lines
    for key in sorted(values, key=str):
        lines.append(f"- `{key}`: {_safe_value(values[key])}")
    lines.append("")
    return lines


def build_case_snapshot(case: EngineeringCase) -> bytes:
    """Return a downloadable Markdown snapshot without raw JSON or credentials."""
    if not isinstance(case, EngineeringCase):
        raise TypeError("build_case_snapshot requires an EngineeringCase")

    origins = input_origins_for_case(case)
    lines = [
        "# Portable Engineering Case Snapshot V1",
        "",
        "> External-safe snapshot for preserving a deterministic Engineering Case outside the bot runtime. It is not a new database record and does not perform a calculation.",
        "",
        "## Snapshot identity",
        "",
        f"- Snapshot schema: `{_SNAPSHOT_SCHEMA}`",
        f"- Case ID: `{_safe_value(case.case_id)}`",
        f"- Calculation type: `{_safe_value(case.calculation_type)}`",
        f"- Status: `{_safe_value(case.status)}`",
        f"- Release: `{_safe_value(case.release)}`",
        "",
    ]
    lines.extend(_mapping_lines("Model and selectors", case.model))
    lines.extend(_mapping_lines("Selectors", case.selectors))
    lines.extend(["## Input values and origins", ""])
    if isinstance(case.inputs, Mapping) and case.inputs:
        units = case.units if isinstance(case.units, Mapping) else {}
        for key in sorted(case.inputs, key=str):
            origin = origins.get(key)
            origin_text = getattr(origin, "value", str(origin or "UNKNOWN"))
            unit = units.get(key)
            unit_text = f" {unit}" if unit else ""
            lines.append(
                f"- `{key}`: {_safe_value(case.inputs[key])}{unit_text} "
                f"[origin: `{origin_text}`]"
            )
    else:
        lines.append("No input values were recorded.")
    lines.append("")

    lines.extend(_mapping_lines("PVT provenance", case.pvt))
    lines.extend(_mapping_lines("Calculated result", case.result))
    lines.extend(_mapping_lines("Reproducibility metadata", case.reproducibility))

    lines.append("## Warnings and limitations")
    lines.append("")
    if case.warnings:
        for item in case.warnings:
            lines.append(f"- Warning: {_safe_value(item)}")
    if case.limitations:
        for item in case.limitations:
            lines.append(f"- Limitation: {_safe_value(item)}")
    if not case.warnings and not case.limitations:
        lines.append("No warnings or limitations were recorded in the case envelope.")
    lines.append("")

    lines.extend([
        "## Human-readable engineering report",
        "",
        generate_report_v1(case),
        "",
        "## Safety and use note",
        "",
        "This snapshot contains the secret-free stored Case envelope and a human-readable report. It is for preservation and review. It is not measured field data, a production forecast, an autonomous optimization, or an operating instruction.",
        "",
    ])
    return "\n".join(lines).encode("utf-8")


__all__ = ["build_case_snapshot"]
