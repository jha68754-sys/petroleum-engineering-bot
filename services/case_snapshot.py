"""Portable, secret-free Markdown snapshots for stored Engineering Cases.

The snapshot keeps its human-readable Markdown report and also carries a
non-visible, authenticated-by-reconstruction case envelope.  The envelope is
used only when a user explicitly asks to restore/resume from the uploaded
snapshot; it is never interpreted as a free-form AI instruction.
"""

from __future__ import annotations

import base64
from collections.abc import Mapping
import json
import re
from typing import Any

from services.engineering_case import EngineeringCase
from services.engineering_context import input_origins_for_case
from services.engineering_report import generate_report_v1


_SNAPSHOT_SCHEMA = "portable_engineering_case_snapshot_v1"
_RESTORE_BEGIN = "<!-- ENGINEERING_CASE_RESTORE_PAYLOAD_V1_BEGIN"
_RESTORE_END = "ENGINEERING_CASE_RESTORE_PAYLOAD_V1_END -->"
_MAX_RESTORE_PAYLOAD_BYTES = 8 * 1024 * 1024
_CASE_ID_LINE_RE = re.compile(r"^- Case ID:\s*`([0-9a-fA-F]{64})`\s*$", re.MULTILINE)
_PAYLOAD_RE = re.compile(
    re.escape(_RESTORE_BEGIN) + r"\s*\n([A-Za-z0-9_-]+={0,2})\s*\n" + re.escape(_RESTORE_END),
    re.MULTILINE,
)


class CaseSnapshotError(ValueError):
    """Typed, user-safe error for an invalid or incomplete Snapshot."""

    code = "SNAPSHOT_INVALID"

    def __init__(self, message: str) -> None:
        text = str(message)
        code, separator, detail = text.partition(":")
        if separator and re.fullmatch(r"[A-Z][A-Z0-9_]+", code.strip()):
            self.code = code.strip()
            message = detail.strip() or text
        else:
            self.code = "SNAPSHOT_INVALID"
        super().__init__(str(message))



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



def is_case_snapshot_text(text: Any) -> bool:
    """Return True for the established human-readable Snapshot header."""
    return isinstance(text, str) and text.lstrip().startswith("# Portable Engineering Case Snapshot V1")



def _restore_payload(case: EngineeringCase) -> str:
    """Encode the secret-scrubbed canonical case envelope for explicit restore."""
    raw = case.to_json().encode("utf-8")
    if len(raw) > _MAX_RESTORE_PAYLOAD_BYTES:
        raise CaseSnapshotError("SNAPSHOT_INVALID: case envelope is too large to export")
    return base64.urlsafe_b64encode(raw).decode("ascii")



def extract_case_id(text: str) -> str:
    """Return the visible Case ID after validating the Snapshot header."""
    if not isinstance(text, str) or not is_case_snapshot_text(text):
        raise CaseSnapshotError("SNAPSHOT_INVALID: this is not a Portable Engineering Case Snapshot")
    match = _CASE_ID_LINE_RE.search(text)
    if match is None:
        raise CaseSnapshotError("SNAPSHOT_INVALID: Snapshot Case ID is missing or malformed")
    return match.group(1).lower()



def parse_case_snapshot(text: str) -> EngineeringCase:
    """Reconstruct an EngineeringCase from a bot-generated Snapshot.

    The parser requires the exact Snapshot header, a restore payload, and an
    identity match between the visible Case ID and the reconstructed envelope.
    No Markdown prose is interpreted as engineering input.
    """
    if not isinstance(text, str) or not is_case_snapshot_text(text):
        raise CaseSnapshotError("SNAPSHOT_INVALID: this is not a Portable Engineering Case Snapshot")

    visible_case_id = extract_case_id(text)

    payload_match = _PAYLOAD_RE.search(text)
    if payload_match is None:
        raise CaseSnapshotError(
            "SNAPSHOT_PAYLOAD_MISSING: this older Snapshot cannot be restored; "
            "generate a new Snapshot from the bot"
        )
    token = payload_match.group(1)
    try:
        raw = base64.b64decode(token.encode("ascii"), altchars=b"-_", validate=True)
        if len(raw) > _MAX_RESTORE_PAYLOAD_BYTES:
            raise ValueError("payload too large")
        payload = json.loads(raw.decode("utf-8"))
        case = EngineeringCase.from_dict(payload)
    except CaseSnapshotError:
        raise
    except (ValueError, TypeError, UnicodeError, json.JSONDecodeError) as exc:
        raise CaseSnapshotError("SNAPSHOT_INVALID: restore payload is unreadable") from exc

    if case.case_id.lower() != visible_case_id:
        raise CaseSnapshotError("SNAPSHOT_INTEGRITY_FAILURE: Case ID does not match the restore payload")
    return case



def build_case_snapshot(case: EngineeringCase) -> bytes:
    """Return a downloadable Markdown snapshot with an explicit restore envelope."""
    if not isinstance(case, EngineeringCase):
        raise TypeError("build_case_snapshot requires an EngineeringCase")

    origins = input_origins_for_case(case)
    restore_payload = _restore_payload(case)
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
        # The payload is deliberately opaque and non-visible in rendered
        # Markdown.  It contains only EngineeringCase.to_json(), which already
        # removes transport identifiers and credentials.
        _RESTORE_BEGIN,
        restore_payload,
        _RESTORE_END,
        "",
    ])
    return "\n".join(lines).encode("utf-8")


__all__ = [
    "CaseSnapshotError",
    "build_case_snapshot",
    "is_case_snapshot_text",
    "extract_case_id",
    "parse_case_snapshot",
]
