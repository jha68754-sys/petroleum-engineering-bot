"""Persistent SQLite registry and audit trail for released engineering cases.

This module is intentionally limited to persistence, serialization, integrity
verification, and human-safe audit formatting.  It contains no petroleum
engineering equations and does not change any released calculation engine.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import threading
from typing import Any, Mapping, Optional

from services.engineering_case import EngineeringCase
from services.engineering_context import EngineeringSessionContext, SessionContextError


_DEFAULT_DB_PATH = "./engineering_cases.sqlite3"
_MAX_AUDIT_DETAILS_BYTES = 8192
_VALID_EVENT_TYPES = frozenset(
    {
        "CASE_CREATED",
        "CASE_RETRIEVED",
        "REPORT_REQUESTED",
        "REPLAY_REQUESTED",
        "REPLAY_MATCH",
        "REPLAY_MISMATCH",
        "VALIDATION_FAILURE",
        "CASE_NOT_FOUND",
    }
)
_VALID_COMPARISON_EVENT_TYPES = frozenset(
    {
        "COMPARISON_CREATED",
        "COMPARISON_RETRIEVED",
        "COMPARISON_REPORT_REQUESTED",
        "COMPARISON_REPLAY_REQUESTED",
        "COMPARISON_REPLAY_MATCH",
        "COMPARISON_REPLAY_MISMATCH",
        "COMPARISON_NOT_FOUND",
    }
)
_CASE_ID_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_SESSION_KEY_RE = _CASE_ID_RE
_SESSION_SCHEMA = "engineering_session_context_v2"
_SECRET_VALUE_PATTERNS = (
    re.compile(r"\bghp_[A-Za-z0-9_]+\b"),
    re.compile(r"\bbot\d+:[A-Za-z0-9_-]+\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]+\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]+\b", re.IGNORECASE),
)
_SENSITIVE_KEY_RE = re.compile(
    r"(?:^|[_-])(token|secret|password|passwd|api[_-]?key|authorization|bearer|credential|private[_-]?key)(?:$|[_-])",
    re.IGNORECASE,
)
_TELEGRAM_KEY_RE = re.compile(
    r"(?:^|[_-])(telegram|chat[_-]?id|user[_-]?id|message[_-]?id|update[_-]?id|username|first[_-]?name|last[_-]?name)(?:$|[_-])",
    re.IGNORECASE,
)
_PRIVATE_DETAIL_KEYS = {
    "request",
    "raw_request",
    "raw_request_string",
    "input_payload",
    "payload",
    "arguments",
    "message",
    "message_text",
    "text",
    "update",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalise_case_id(case_id: Any) -> str:
    if not isinstance(case_id, str):
        raise CaseNotFoundError("CASE_NOT_FOUND: case ID must be a SHA-256 hexadecimal string")
    candidate = case_id.strip()
    if not _CASE_ID_RE.fullmatch(candidate):
        raise CaseNotFoundError("CASE_NOT_FOUND: invalid engineering case ID")
    return candidate.lower()


def _scrub_string(value: str) -> str:
    result = value
    for pattern in _SECRET_VALUE_PATTERNS:
        result = pattern.sub("[REDACTED]", result)
    return result


def _key_is_sensitive(key: Any) -> bool:
    text = str(key).strip().lower()
    return bool(_SENSITIVE_KEY_RE.search(text) or _TELEGRAM_KEY_RE.search(text))


def _is_private_detail_key(key: Any) -> bool:
    text = str(key).strip().lower()
    return text in _PRIVATE_DETAIL_KEYS or text.endswith("_payload") or text.startswith("raw_")


def _safe_plain(value: Any, *, details: bool = False) -> Any:
    """Make a strict JSON-safe copy while removing transport credentials."""
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _scrub_string(value)
    if isinstance(value, Mapping):
        output: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if _key_is_sensitive(key) or (details and _is_private_detail_key(key)):
                continue
            output[key_text] = _safe_plain(item, details=details)
        return output
    if isinstance(value, (list, tuple)):
        return [_safe_plain(item, details=details) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted((_safe_plain(item, details=details) for item in value), key=lambda item: repr(item))
    raise ValueError("value is not JSON serializable")


def _safe_json(value: Any, *, details: bool = False) -> str:
    try:
        plain = _safe_plain(value, details=details)
        return json.dumps(plain, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("value is not JSON serializable") from exc


def _safe_report(report_text: Optional[str]) -> Optional[str]:
    if report_text is None:
        return None
    if not isinstance(report_text, str):
        raise ValueError("report_text must be a string")
    if "\x00" in report_text:
        raise ValueError("report_text contains an unsupported null byte")
    # Explicit credential headers are rejected.  Ordinary report text is kept
    # verbatim except for credential-shaped values, which are redacted before
    # persistence so they cannot be recovered from the SQLite file.
    if re.search(r"(?:authorization|x-api-key|api-key)\s*:\s*bearer\s+", report_text, re.IGNORECASE):
        raise ValueError("report_text contains a credential header")
    if re.search(r"(?:password|passwd|api[_-]?key|secret|token)\s*=", report_text, re.IGNORECASE):
        raise ValueError("report_text contains credential material")
    return _scrub_string(report_text)


def _json_object_or_none(value: Optional[str]) -> Any:
    if value is None:
        return None
    try:
        return json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise CaseIntegrityError("CASE_INTEGRITY_FAILURE: stored replay metadata is invalid") from exc


class CaseNotFoundError(LookupError):
    """Typed, user-safe error for an absent or malformed case identifier."""

    code = "CASE_NOT_FOUND"


class CaseIntegrityError(ValueError):
    """Typed, user-safe error for a tampered or unreadable case record."""

    code = "CASE_INTEGRITY_FAILURE"


class SessionNotFoundError(LookupError):
    """Typed error for a chat session with no persisted context."""

    code = "SESSION_NOT_FOUND"


class SessionIntegrityError(ValueError):
    """Typed error for a tampered or incompatible persisted session."""

    code = "SESSION_INTEGRITY_FAILURE"


@dataclass(frozen=True)
class AuditEvent:
    case_id: str
    case_type: str
    event_type: str
    sequence: int
    created_at: str
    details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "case_type": self.case_type,
            "event_type": self.event_type,
            "sequence": int(self.sequence),
            "created_at": self.created_at,
            "details": _safe_plain(self.details, details=True),
        }


class EngineeringCaseRegistry:
    """Thread-safe SQLite-backed store for immutable EngineeringCase payloads."""

    def __init__(
        self,
        db_path: str | os.PathLike[str],
        cache_enabled: bool = True,
        timeout_seconds: float = 5.0,
    ) -> None:
        self.db_path = str(db_path)
        self.cache_enabled = bool(cache_enabled)
        self.timeout_seconds = float(timeout_seconds)
        self._lock = threading.RLock()
        self._closed = False
        self._cache: dict[str, EngineeringCase] = {}
        self._comparison_cache: dict[str, Any] = {}

        if self.db_path != ":memory:":
            path = Path(self.db_path).expanduser()
            path.parent.mkdir(parents=True, exist_ok=True)
            self.db_path = str(path)
        self._connection = sqlite3.connect(
            self.db_path,
            timeout=self.timeout_seconds,
            check_same_thread=False,
        )
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA foreign_keys=ON")
        self._connection.execute("PRAGMA busy_timeout=5000")
        self._initialise_schema()

    @classmethod
    def from_environment(cls, **kwargs: Any) -> "EngineeringCaseRegistry":
        configured_path = os.getenv("ENGINEERING_CASE_DB_PATH")
        if configured_path:
            db_path = configured_path
        else:
            # Railway exposes the mount point automatically when a Volume is
            # attached.  Use it by default so persistence does not depend on a
            # second manually synchronized environment variable.
            mount_path = os.getenv("RAILWAY_VOLUME_MOUNT_PATH")
            db_path = (
                str(Path(mount_path) / "engineering_cases.sqlite3")
                if mount_path
                else _DEFAULT_DB_PATH
            )
        return cls(db_path, **kwargs)

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("engineering case registry is closed")

    def _initialise_schema(self) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS engineering_cases (
                    case_id TEXT PRIMARY KEY,
                    case_json TEXT NOT NULL,
                    case_sha256 TEXT NOT NULL,
                    report_text TEXT,
                    status TEXT NOT NULL,
                    case_type TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    replay_match INTEGER,
                    replay_count INTEGER NOT NULL DEFAULT 0,
                    replay_at TEXT,
                    replay_result TEXT,
                    updated_at TEXT,
                    schema_version TEXT NOT NULL DEFAULT 'engineering_case_v1',
                    case_content_sha256 TEXT
                )
                """
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS engineering_case_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    details_json TEXT NOT NULL,
                    UNIQUE(case_id, sequence)
                )
                """
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS engineering_comparisons (
                    comparison_id TEXT PRIMARY KEY,
                    comparison_json TEXT NOT NULL,
                    comparison_sha256 TEXT NOT NULL,
                    report_text TEXT,
                    status TEXT NOT NULL,
                    scenario_count INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    replay_match INTEGER,
                    replay_count INTEGER NOT NULL DEFAULT 0,
                    replay_at TEXT,
                    replay_result TEXT,
                    updated_at TEXT,
                    schema_version TEXT NOT NULL DEFAULT 'scenario_comparison_v1',
                    comparison_content_sha256 TEXT
                )
                """
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS engineering_comparison_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    comparison_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    details_json TEXT NOT NULL,
                    UNIQUE(comparison_id, sequence)
                )
                """
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS engineering_sessions (
                    session_key TEXT PRIMARY KEY,
                    session_json TEXT NOT NULL,
                    session_sha256 TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    schema_version TEXT NOT NULL DEFAULT 'engineering_session_context_v2'
                )
                """
            )
            self._ensure_column("engineering_cases", "updated_at", "TEXT")
            self._ensure_column(
                "engineering_cases", "schema_version", "TEXT NOT NULL DEFAULT 'engineering_case_v1'"
            )
            self._ensure_column("engineering_cases", "case_content_sha256", "TEXT")
            self._connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_engineering_cases_case_id ON engineering_cases(case_id)"
            )
            self._connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_engineering_cases_type ON engineering_cases(case_type)"
            )
            self._connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_engineering_cases_status ON engineering_cases(status)"
            )
            self._connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_engineering_case_audit_case_id ON engineering_case_audit(case_id)"
            )
            self._connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_engineering_case_audit_sequence ON engineering_case_audit(case_id, sequence)"
            )
            self._connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_engineering_comparisons_id ON engineering_comparisons(comparison_id)"
            )
            self._connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_engineering_comparison_audit_id ON engineering_comparison_audit(comparison_id)"
            )
            self._connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_engineering_comparison_audit_sequence ON engineering_comparison_audit(comparison_id, sequence)"
            )
            self._connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_engineering_sessions_updated_at ON engineering_sessions(updated_at)"
            )

    def _ensure_column(self, table: str, column: str, definition: str) -> None:
        existing = {
            str(row[1])
            for row in self._connection.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column not in existing:
            self._connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def _row_for_case(self, case_id: str) -> Optional[sqlite3.Row]:
        return self._connection.execute(
            "SELECT * FROM engineering_cases WHERE case_id = ? COLLATE NOCASE",
            (case_id,),
        ).fetchone()

    def _case_from_row(self, row: sqlite3.Row) -> EngineeringCase:
        stored_id = str(row["case_id"]).lower()
        case_json = row["case_json"]
        stored_hash = row["case_sha256"]
        if not isinstance(case_json, str) or not isinstance(stored_hash, str):
            raise CaseIntegrityError("CASE_INTEGRITY_FAILURE: stored case record is incomplete")
        if stored_hash.lower() != stored_id:
            raise CaseIntegrityError("CASE_INTEGRITY_FAILURE: stored case hash does not match case ID")
        content_hash = row["case_content_sha256"] if "case_content_sha256" in row.keys() else None
        if content_hash:
            actual_content_hash = hashlib.sha256(case_json.encode("utf-8")).hexdigest()
            if str(content_hash).lower() != actual_content_hash:
                raise CaseIntegrityError("CASE_INTEGRITY_FAILURE: stored case payload was modified")
        try:
            case = EngineeringCase.from_json(case_json)
        except Exception as exc:
            raise CaseIntegrityError("CASE_INTEGRITY_FAILURE: stored case payload is invalid") from exc
        if case.case_id.lower() != stored_id:
            raise CaseIntegrityError("CASE_INTEGRITY_FAILURE: stored case identity does not match case ID")
        # EngineeringCase.to_json is canonical.  This also detects edits to
        # the payload when an older database predates case_content_sha256.
        if case.to_json() != case_json:
            raise CaseIntegrityError("CASE_INTEGRITY_FAILURE: stored case payload is not canonical")
        return case

    def _event_from_row(self, row: sqlite3.Row) -> AuditEvent:
        try:
            details = json.loads(row["details_json"])
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise CaseIntegrityError("CASE_INTEGRITY_FAILURE: stored audit details are invalid") from exc
        if not isinstance(details, dict):
            raise CaseIntegrityError("CASE_INTEGRITY_FAILURE: stored audit details are invalid")
        safe_details = _safe_plain(details, details=True)
        return AuditEvent(
            case_id=str(row["case_id"]).lower(),
            case_type=str(row["case_type"]),
            event_type=str(row["event_type"]),
            sequence=int(row["sequence"]),
            created_at=str(row["created_at"]),
            details=safe_details,
        )

    def _next_sequence(self, case_id: str) -> int:
        row = self._connection.execute(
            "SELECT COALESCE(MAX(sequence), 0) + 1 FROM engineering_case_audit WHERE case_id = ? COLLATE NOCASE",
            (case_id,),
        ).fetchone()
        return int(row[0])

    def _insert_event(
        self,
        case_id: str,
        case_type: str,
        event_type: str,
        details: Optional[Mapping[str, Any]] = None,
    ) -> AuditEvent:
        if event_type not in _VALID_EVENT_TYPES:
            raise ValueError("unknown engineering case audit event")
        raw_details: Mapping[str, Any] = {} if details is None else details
        if not isinstance(raw_details, Mapping):
            raise ValueError("audit details must be a mapping")
        details_json = _safe_json(raw_details, details=True)
        if len(details_json.encode("utf-8")) > _MAX_AUDIT_DETAILS_BYTES:
            raise ValueError("audit details exceed the permitted size")
        sequence = self._next_sequence(case_id)
        created_at = _utc_now()
        self._connection.execute(
            """
            INSERT INTO engineering_case_audit
                (case_id, event_type, sequence, created_at, details_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (case_id, event_type, sequence, created_at, details_json),
        )
        return AuditEvent(case_id, str(case_type), event_type, sequence, created_at, json.loads(details_json))

    def _missing_event(self, case_id: str, action: Optional[str]) -> AuditEvent:
        with self._lock, self._connection:
            # A missing-case audit row is deliberately allowed without a case
            # row; this makes failed report/replay requests auditable without
            # creating a phantom EngineeringCase.
            event = self._insert_event(
                case_id,
                "unknown",
                "CASE_NOT_FOUND",
                {"action": str(action)} if action else {},
            )
            return event

    def save_case(
        self,
        case: EngineeringCase,
        report_text: Optional[str] = None,
        schema_version: Optional[str] = None,
    ) -> AuditEvent:
        if not isinstance(case, EngineeringCase):
            raise ValueError("case must be an EngineeringCase")
        case_id = _normalise_case_id(case.case_id)
        safe_report = _safe_report(report_text)
        case_json = case.to_json()
        if "\x00" in case_json:
            raise ValueError("case payload contains an unsupported null byte")
        content_hash = hashlib.sha256(case_json.encode("utf-8")).hexdigest()
        now = _utc_now()
        schema = str(schema_version or "engineering_case_v1")

        with self._lock, self._connection:
            self._ensure_open()
            existing = self._row_for_case(case_id)
            if existing is not None:
                existing_json = existing["case_json"]
                if existing_json != case_json:
                    raise ValueError("case ID already exists with a different case payload")
                existing_report = existing["report_text"]
                if safe_report is not None and existing_report != safe_report:
                    raise ValueError("case ID already exists with a different report")
                if self.cache_enabled:
                    self._cache[case_id] = case
                # Idempotent save: do not update timestamps or append an event.
                events = self._connection.execute(
                    """
                    SELECT a.*, c.case_type FROM engineering_case_audit a
                    JOIN engineering_cases c ON c.case_id = a.case_id
                    WHERE a.case_id = ? COLLATE NOCASE
                    ORDER BY a.sequence DESC LIMIT 1
                    """,
                    (case_id,),
                ).fetchone()
                if events is not None:
                    return self._event_from_row(events)
                # A legacy row without CASE_CREATED is repaired once.
                return self._insert_event(case_id, case.calculation_type, "CASE_CREATED", {"model": case.model})

            # If a producer supplies the same non-empty request envelope
            # again with a different engineering payload, fail closed rather
            # than treating it as a duplicate retry.  Normal cases created by
            # different requests remain independently addressable by case ID.
            if case.request:
                candidates = self._connection.execute(
                    "SELECT case_json FROM engineering_cases WHERE case_type = ?",
                    (case.calculation_type,),
                ).fetchall()
                requested_envelope = {
                    "calculation_type": case.calculation_type,
                    "request": case.request,
                    "units": case.units,
                    "selectors": case.selectors,
                    "model": case.model,
                    "pvt": case.pvt,
                    "assumptions": case.assumptions,
                    "release": case.release,
                }
                for candidate in candidates:
                    try:
                        candidate_payload = json.loads(candidate["case_json"])
                    except (TypeError, ValueError, json.JSONDecodeError):
                        continue
                    candidate_envelope = {
                        "calculation_type": candidate_payload.get("calculation_type"),
                        "request": candidate_payload.get("request", {}),
                        "units": candidate_payload.get("units", {}),
                        "selectors": candidate_payload.get("selectors", {}),
                        "model": candidate_payload.get("model", {}),
                        "pvt": candidate_payload.get("pvt", {}),
                        "assumptions": candidate_payload.get("assumptions", {}),
                        "release": candidate_payload.get("release", ""),
                    }
                    if _safe_json(requested_envelope) == _safe_json(candidate_envelope):
                        raise ValueError("case request already exists with a different case payload")

            self._connection.execute(
                """
                INSERT INTO engineering_cases
                    (case_id, case_json, case_sha256, report_text, status, case_type,
                     created_at, replay_match, replay_count, replay_at, replay_result,
                     updated_at, schema_version, case_content_sha256)
                VALUES (?, ?, ?, ?, ?, ?, ?, NULL, 0, NULL, NULL, ?, ?, ?)
                """,
                (
                    case_id,
                    case_json,
                    case_id,
                    safe_report,
                    case.status,
                    case.calculation_type,
                    now,
                    now,
                    schema,
                    content_hash,
                ),
            )
            event = self._insert_event(
                case_id,
                case.calculation_type,
                "CASE_CREATED",
                {"model": case.model},
            )
            if self.cache_enabled:
                self._cache[case_id] = case
            return event

    @staticmethod
    def _comparison_status(comparison: Any) -> str:
        statuses = [str(item.case.status) for item in comparison.scenarios]
        return "OK" if statuses and all(status == "OK" for status in statuses) else "PARTIAL"

    def _row_for_comparison(self, comparison_id: str) -> Optional[sqlite3.Row]:
        return self._connection.execute(
            "SELECT * FROM engineering_comparisons WHERE comparison_id = ? COLLATE NOCASE",
            (comparison_id,),
        ).fetchone()

    def _comparison_from_row(self, row: sqlite3.Row) -> Any:
        from services.scenario_comparison import ScenarioComparison

        stored_id = str(row["comparison_id"]).lower()
        comparison_json = row["comparison_json"]
        stored_hash = row["comparison_sha256"]
        if not isinstance(comparison_json, str) or not isinstance(stored_hash, str):
            raise CaseIntegrityError("COMPARISON_INTEGRITY_FAILURE: stored comparison record is incomplete")
        if stored_hash.lower() != stored_id:
            raise CaseIntegrityError("COMPARISON_INTEGRITY_FAILURE: stored comparison hash does not match ID")
        content_hash = row["comparison_content_sha256"]
        if content_hash:
            actual_content_hash = hashlib.sha256(comparison_json.encode("utf-8")).hexdigest()
            if str(content_hash).lower() != actual_content_hash:
                raise CaseIntegrityError("COMPARISON_INTEGRITY_FAILURE: stored comparison payload was modified")
        try:
            comparison = ScenarioComparison.from_json(comparison_json)
        except Exception as exc:
            raise CaseIntegrityError("COMPARISON_INTEGRITY_FAILURE: stored comparison payload is invalid") from exc
        if comparison.comparison_id.lower() != stored_id:
            raise CaseIntegrityError("COMPARISON_INTEGRITY_FAILURE: stored comparison identity does not match ID")
        if comparison.to_json() != comparison_json:
            raise CaseIntegrityError("COMPARISON_INTEGRITY_FAILURE: stored comparison payload is not canonical")
        return comparison

    def _next_comparison_sequence(self, comparison_id: str) -> int:
        row = self._connection.execute(
            "SELECT COALESCE(MAX(sequence), 0) + 1 FROM engineering_comparison_audit WHERE comparison_id = ? COLLATE NOCASE",
            (comparison_id,),
        ).fetchone()
        return int(row[0])

    def _insert_comparison_event(
        self,
        comparison_id: str,
        event_type: str,
        details: Optional[Mapping[str, Any]] = None,
    ) -> AuditEvent:
        if event_type not in _VALID_COMPARISON_EVENT_TYPES:
            raise ValueError("unknown scenario comparison audit event")
        raw_details: Mapping[str, Any] = {} if details is None else details
        if not isinstance(raw_details, Mapping):
            raise ValueError("comparison audit details must be a mapping")
        details_json = _safe_json(raw_details, details=True)
        if len(details_json.encode("utf-8")) > _MAX_AUDIT_DETAILS_BYTES:
            raise ValueError("comparison audit details exceed the permitted size")
        sequence = self._next_comparison_sequence(comparison_id)
        created_at = _utc_now()
        self._connection.execute(
            """
            INSERT INTO engineering_comparison_audit
                (comparison_id, event_type, sequence, created_at, details_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (comparison_id, event_type, sequence, created_at, details_json),
        )
        return AuditEvent(
            comparison_id,
            "scenario_comparison",
            event_type,
            sequence,
            created_at,
            json.loads(details_json),
        )

    def _comparison_missing_event(self, comparison_id: str, action: Optional[str]) -> AuditEvent:
        with self._lock, self._connection:
            return self._insert_comparison_event(
                comparison_id,
                "COMPARISON_NOT_FOUND",
                {"action": str(action)} if action else {},
            )

    def save_comparison(
        self,
        comparison: Any,
        report_text: Optional[str] = None,
        schema_version: Optional[str] = None,
    ) -> AuditEvent:
        from services.scenario_comparison import ScenarioComparison

        if not isinstance(comparison, ScenarioComparison):
            raise ValueError("comparison must be a ScenarioComparison")
        comparison_id = _normalise_case_id(comparison.comparison_id)
        safe_report = _safe_report(report_text)
        try:
            comparison_payload = json.loads(comparison.to_json())
            comparison_json = _safe_json(comparison_payload)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError("comparison payload is not JSON serializable") from exc
        if "\x00" in comparison_json:
            raise ValueError("comparison payload contains an unsupported null byte")
        content_hash = hashlib.sha256(comparison_json.encode("utf-8")).hexdigest()
        now = _utc_now()
        schema = str(schema_version or "scenario_comparison_v1")
        status = self._comparison_status(comparison)
        scenario_count = len(comparison.scenarios)

        with self._lock, self._connection:
            self._ensure_open()
            existing = self._row_for_comparison(comparison_id)
            if existing is not None:
                if existing["comparison_json"] != comparison_json:
                    raise ValueError("comparison ID already exists with a different payload")
                existing_report = existing["report_text"]
                if safe_report is not None and existing_report != safe_report:
                    raise ValueError("comparison ID already exists with a different report")
                if self.cache_enabled:
                    self._comparison_cache[comparison_id] = comparison
                event = self._connection.execute(
                    """
                    SELECT * FROM engineering_comparison_audit
                    WHERE comparison_id = ? COLLATE NOCASE
                    ORDER BY sequence DESC LIMIT 1
                    """,
                    (comparison_id,),
                ).fetchone()
                if event is not None:
                    return AuditEvent(
                        comparison_id,
                        "scenario_comparison",
                        str(event["event_type"]),
                        int(event["sequence"]),
                        str(event["created_at"]),
                        _safe_plain(json.loads(event["details_json"]), details=True),
                    )
                return self._insert_comparison_event(comparison_id, "COMPARISON_CREATED", {})

            self._connection.execute(
                """
                INSERT INTO engineering_comparisons
                    (comparison_id, comparison_json, comparison_sha256, report_text,
                     status, scenario_count, created_at, replay_match, replay_count,
                     replay_at, replay_result, updated_at, schema_version,
                     comparison_content_sha256)
                VALUES (?, ?, ?, ?, ?, ?, ?, NULL, 0, NULL, NULL, ?, ?, ?)
                """,
                (
                    comparison_id,
                    comparison_json,
                    comparison_id,
                    safe_report,
                    status,
                    scenario_count,
                    now,
                    now,
                    schema,
                    content_hash,
                ),
            )
            event = self._insert_comparison_event(comparison_id, "COMPARISON_CREATED", {})
            if self.cache_enabled:
                self._comparison_cache[comparison_id] = comparison
            return event

    def get_comparison(
        self,
        comparison_id: str,
        record_event: bool = False,
        action: Optional[str] = None,
    ) -> Any:
        normalized = _normalise_case_id(comparison_id)
        with self._lock:
            self._ensure_open()
            row = self._row_for_comparison(normalized)
            if row is None:
                raise CaseNotFoundError(f"COMPARISON_NOT_FOUND: no scenario comparison for {normalized}")
            comparison = self._comparison_from_row(row)
            if self.cache_enabled:
                self._comparison_cache[normalized] = comparison
            if record_event:
                with self._connection:
                    self._insert_comparison_event(normalized, "COMPARISON_RETRIEVED", {"action": action} if action else {})
            return comparison

    def get_comparison_report(self, comparison_id: str, record_event: bool = False) -> str:
        normalized = _normalise_case_id(comparison_id)
        with self._lock:
            self._ensure_open()
            row = self._row_for_comparison(normalized)
            if row is None:
                raise CaseNotFoundError(f"COMPARISON_NOT_FOUND: no scenario comparison for {normalized}")
            report = row["report_text"]
            if report is None:
                report = ""
            if not isinstance(report, str):
                raise CaseIntegrityError("COMPARISON_INTEGRITY_FAILURE: stored comparison report is invalid")
            if record_event:
                with self._connection:
                    self._insert_comparison_event(normalized, "COMPARISON_REPORT_REQUESTED", {})
            return str(report)

    def get_comparison_metadata(self, comparison_id: str) -> dict[str, Any]:
        normalized = _normalise_case_id(comparison_id)
        with self._lock:
            self._ensure_open()
            row = self._row_for_comparison(normalized)
            if row is None:
                raise CaseNotFoundError(f"COMPARISON_NOT_FOUND: no scenario comparison for {normalized}")
            comparison = self._comparison_from_row(row)
            replay_result = _json_object_or_none(row["replay_result"])
            return {
                "comparison_id": normalized,
                "comparison_type": "scenario_comparison",
                "status": str(row["status"]),
                "scenario_count": int(row["scenario_count"]),
                "report_text": str(row["report_text"] or ""),
                "replay_match": None if row["replay_match"] is None else bool(row["replay_match"]),
                "replay_count": int(row["replay_count"] or 0),
                "replay_at": row["replay_at"],
                "replay_result": replay_result,
                "created_at": str(row["created_at"]),
                "updated_at": str(row["updated_at"] or row["created_at"]),
                "comparison_sha256": str(row["comparison_sha256"]),
                "schema_version": str(row["schema_version"] or "scenario_comparison_v1"),
                "persistent": True,
            }

    def audit_comparison(self, comparison_id: str) -> list[AuditEvent]:
        normalized = _normalise_case_id(comparison_id)
        with self._lock:
            self._ensure_open()
            rows = self._connection.execute(
                """
                SELECT * FROM engineering_comparison_audit
                WHERE comparison_id = ? COLLATE NOCASE
                ORDER BY sequence ASC, id ASC
                """,
                (normalized,),
            ).fetchall()
            if not rows:
                raise CaseNotFoundError(f"COMPARISON_NOT_FOUND: no audit events for {normalized}")
            return [
                AuditEvent(
                    normalized,
                    "scenario_comparison",
                    str(row["event_type"]),
                    int(row["sequence"]),
                    str(row["created_at"]),
                    _safe_plain(json.loads(row["details_json"]), details=True),
                )
                for row in rows
            ]

    def record_comparison_event(
        self,
        comparison_id: str,
        event_type: str,
        details: Optional[Mapping[str, Any]] = None,
    ) -> AuditEvent:
        normalized = _normalise_case_id(comparison_id)
        if event_type not in _VALID_COMPARISON_EVENT_TYPES:
            raise ValueError("unknown scenario comparison audit event")
        with self._lock, self._connection:
            self._ensure_open()
            if self._row_for_comparison(normalized) is None:
                raise CaseNotFoundError(f"COMPARISON_NOT_FOUND: no scenario comparison for {normalized}")
            return self._insert_comparison_event(normalized, event_type, details)

    def record_comparison_replay_result(
        self,
        comparison_id: str,
        matched: bool,
        result: Optional[Mapping[str, Any]],
    ) -> AuditEvent:
        normalized = _normalise_case_id(comparison_id)
        if not isinstance(matched, bool):
            raise ValueError("matched must be a boolean")
        if result is not None and not isinstance(result, Mapping):
            raise ValueError("comparison replay result must be a mapping or None")
        result_json = None if result is None else _safe_json(result, details=True)
        with self._lock, self._connection:
            self._ensure_open()
            row = self._row_for_comparison(normalized)
            if row is None:
                raise CaseNotFoundError(f"COMPARISON_NOT_FOUND: no scenario comparison for {normalized}")
            replay_count = int(row["replay_count"] or 0) + 1
            replay_at = _utc_now()
            self._connection.execute(
                """
                UPDATE engineering_comparisons
                SET replay_match = ?, replay_count = ?, replay_at = ?, replay_result = ?, updated_at = ?
                WHERE comparison_id = ? COLLATE NOCASE
                """,
                (1 if matched else 0, replay_count, replay_at, result_json, replay_at, normalized),
            )
            event_type = "COMPARISON_REPLAY_MATCH" if matched else "COMPARISON_REPLAY_MISMATCH"
            return self._insert_comparison_event(normalized, event_type, {"matched": matched})

    def format_comparison_audit(self, comparison_id: str) -> str:
        events = self.audit_comparison(comparison_id)
        normalized = _normalise_case_id(comparison_id)
        lines = [
            "Scenario Comparison Audit",
            "=========================",
            f"Comparison ID: {normalized}",
            f"Event count: {len(events)}",
            "",
        ]
        for event in events:
            timestamp = event.created_at.replace("T", " ", 1)
            prefix = "Created " if event.event_type == "COMPARISON_CREATED" else ""
            line = f"{event.sequence}. {event.event_type} — {prefix}{timestamp}"
            display_details: list[str] = []
            for key, value in event.details.items():
                if key in {"action", "surface", "code", "reason", "matched"}:
                    display_details.append(f"{key}: {self._display_detail_value(value)}")
            if display_details:
                line += " — " + "; ".join(display_details)
            lines.append(line)
        return "\n".join(lines)

    def get_case(
        self,
        case_id: str,
        record_event: bool = False,
        action: Optional[str] = None,
    ) -> EngineeringCase:
        normalized = _normalise_case_id(case_id)
        with self._lock:
            self._ensure_open()
            row = self._row_for_case(normalized)
            if row is None:
                # Missing-case audit rows are recorded by the command layer,
                # where the requested action is known.  Retrieval itself must
                # remain a pure lookup, including when record_event is true.
                raise CaseNotFoundError(f"CASE_NOT_FOUND: no engineering case for {normalized}")
            case = self._case_from_row(row)
            if self.cache_enabled:
                self._cache[normalized] = case
            if record_event:
                with self._connection:
                    self._insert_event(normalized, case.calculation_type, "CASE_RETRIEVED", {})
            return case

    def get_report(self, case_id: str, record_event: bool = False) -> str:
        normalized = _normalise_case_id(case_id)
        with self._lock:
            self._ensure_open()
            row = self._row_for_case(normalized)
            if row is None:
                raise CaseNotFoundError(f"CASE_NOT_FOUND: no engineering case for {normalized}")
            report = row["report_text"]
            if report is None:
                report = ""
            if not isinstance(report, str):
                raise CaseIntegrityError("CASE_INTEGRITY_FAILURE: stored report is invalid")
            if record_event:
                with self._connection:
                    case_type = str(row["case_type"])
                    self._insert_event(normalized, case_type, "REPORT_REQUESTED", {})
            return str(report)

    def get_case_metadata(self, case_id: str) -> dict[str, Any]:
        normalized = _normalise_case_id(case_id)
        with self._lock:
            self._ensure_open()
            row = self._row_for_case(normalized)
            if row is None:
                raise CaseNotFoundError(f"CASE_NOT_FOUND: no engineering case for {normalized}")
            case = self._case_from_row(row)
            replay_result = _json_object_or_none(row["replay_result"])
            return {
                "case_id": normalized,
                "case_type": str(row["case_type"]),
                "calculation_type": case.calculation_type,
                "status": case.status,
                "model": _safe_plain(case.model),
                "pvt": _safe_plain(case.pvt),
                "report_text": str(row["report_text"] or ""),
                "replay_match": None if row["replay_match"] is None else bool(row["replay_match"]),
                "replay_count": int(row["replay_count"] or 0),
                "replay_at": row["replay_at"],
                "replay_result": replay_result,
                "created_at": str(row["created_at"]),
                "updated_at": str(row["updated_at"] or row["created_at"]),
                "case_sha256": str(row["case_sha256"]),
                "schema_version": str(row["schema_version"] or "engineering_case_v1"),
                "persistent": True,
            }

    def audit_case(self, case_id: str) -> list[AuditEvent]:
        normalized = _normalise_case_id(case_id)
        with self._lock:
            self._ensure_open()
            rows = self._connection.execute(
                """
                SELECT a.*, COALESCE(c.case_type, 'unknown') AS case_type
                FROM engineering_case_audit a
                LEFT JOIN engineering_cases c ON c.case_id = a.case_id
                WHERE a.case_id = ? COLLATE NOCASE
                ORDER BY a.sequence ASC, a.id ASC
                """,
                (normalized,),
            ).fetchall()
            if not rows:
                raise CaseNotFoundError(f"CASE_NOT_FOUND: no audit events for {normalized}")
            return [self._event_from_row(row) for row in rows]

    def record_event(
        self,
        case_id: str,
        event_type: str,
        details: Optional[Mapping[str, Any]] = None,
    ) -> AuditEvent:
        normalized = _normalise_case_id(case_id)
        if event_type not in _VALID_EVENT_TYPES:
            raise ValueError("unknown engineering case audit event")
        with self._lock, self._connection:
            self._ensure_open()
            row = self._row_for_case(normalized)
            if row is None:
                raise CaseNotFoundError(f"CASE_NOT_FOUND: no engineering case for {normalized}")
            event = self._insert_event(normalized, str(row["case_type"]), event_type, details)
            return event

    def record_replay_result(
        self,
        case_id: str,
        matched: bool,
        result: Optional[Mapping[str, Any]],
    ) -> AuditEvent:
        normalized = _normalise_case_id(case_id)
        if not isinstance(matched, bool):
            raise ValueError("matched must be a boolean")
        if result is not None and not isinstance(result, Mapping):
            raise ValueError("replay result must be a mapping or None")
        result_json = None if result is None else _safe_json(result, details=True)
        with self._lock, self._connection:
            self._ensure_open()
            row = self._row_for_case(normalized)
            if row is None:
                raise CaseNotFoundError(f"CASE_NOT_FOUND: no engineering case for {normalized}")
            replay_count = int(row["replay_count"] or 0) + 1
            replay_at = _utc_now()
            self._connection.execute(
                """
                UPDATE engineering_cases
                SET replay_match = ?, replay_count = ?, replay_at = ?, replay_result = ?
                WHERE case_id = ? COLLATE NOCASE
                """,
                (1 if matched else 0, replay_count, replay_at, result_json, normalized),
            )
            event_type = "REPLAY_MATCH" if matched else "REPLAY_MISMATCH"
            return self._insert_event(
                normalized,
                str(row["case_type"]),
                event_type,
                {"matched": matched},
            )

    def list_cases(
        self,
        case_type: Optional[str] = None,
        status: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> list[EngineeringCase]:
        if limit is not None:
            if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
                raise ValueError("limit must be a non-negative integer")
        with self._lock:
            self._ensure_open()
            clauses: list[str] = []
            params: list[Any] = []
            if case_type is not None:
                clauses.append("case_type = ?")
                params.append(str(case_type))
            if status is not None:
                clauses.append("status = ?")
                params.append(str(status))
            query = "SELECT * FROM engineering_cases"
            if clauses:
                query += " WHERE " + " AND ".join(clauses)
            query += " ORDER BY created_at DESC, case_id DESC"
            if limit is not None:
                query += " LIMIT ?"
                params.append(limit)
            rows = self._connection.execute(query, params).fetchall()
            cases = [self._case_from_row(row) for row in rows]
            if self.cache_enabled:
                for case in cases:
                    self._cache[case.case_id] = case
            return cases

    @staticmethod
    def _display_detail_value(value: Any) -> str:
        if isinstance(value, bool):
            return "yes" if value else "no"
        if value is None:
            return "not provided"
        if isinstance(value, (str, int, float)):
            return _scrub_string(str(value)).replace("{", "(").replace("}", ")")
        return "recorded"

    def format_case_list(self, status: Optional[str] = None, limit: Optional[int] = None) -> str:
        cases = self.list_cases(status=status, limit=limit)
        lines = ["Engineering Case Registry", "=========================", f"Cases found: {len(cases)}", ""]
        if not cases:
            lines.append("No engineering cases are stored.")
            return "\n".join(lines)
        for index, case in enumerate(cases, start=1):
            lines.extend(
                [
                    f"Case ID: {case.case_id}",
                    f"Type: {case.calculation_type}",
                    f"Status: {case.status}",
                ]
            )
            if index != len(cases):
                lines.append("")
        return "\n".join(lines)

    def format_audit(self, case_id: str) -> str:
        events = self.audit_case(case_id)
        normalized = _normalise_case_id(case_id)
        case_type = events[0].case_type if events else "unknown"
        lines = [
            "Engineering Case Audit",
            "======================",
            f"Case ID: {normalized}",
            f"Calculation type: {case_type}",
            f"Event count: {len(events)}",
            "",
        ]
        for event in events:
            timestamp = event.created_at.replace("T", " ", 1)
            prefix = "Created " if event.event_type == "CASE_CREATED" else ""
            line = f"{event.sequence}. {event.event_type} — {prefix}{timestamp}"
            display_details: list[str] = []
            for key, value in event.details.items():
                if key in {"action", "surface", "code", "reason", "matched"}:
                    display_details.append(f"{key}: {self._display_detail_value(value)}")
            if display_details:
                line += " — " + "; ".join(display_details)
            lines.append(line)
        return "\n".join(lines)

    @staticmethod
    def _normalise_session_key(session_key: Any) -> str:
        candidate = str(session_key or "").strip().lower()
        if not _SESSION_KEY_RE.fullmatch(candidate):
            raise SessionNotFoundError("SESSION_NOT_FOUND: invalid session key")
        return candidate

    def save_session(
        self,
        session_key: str,
        context: EngineeringSessionContext,
    ) -> None:
        """Persist a secret-free chat context in the existing Workspace database."""
        normalized = self._normalise_session_key(session_key)
        if not isinstance(context, EngineeringSessionContext):
            raise ValueError("context must be an EngineeringSessionContext")
        try:
            payload = json.loads(context.to_json())
            session_json = _safe_json(payload)
        except (TypeError, ValueError, json.JSONDecodeError, SessionContextError) as exc:
            raise ValueError("session context is not JSON serializable") from exc
        content_hash = hashlib.sha256(session_json.encode("utf-8")).hexdigest()
        now = _utc_now()
        with self._lock, self._connection:
            self._ensure_open()
            self._connection.execute(
                """
                INSERT INTO engineering_sessions
                    (session_key, session_json, session_sha256, created_at, updated_at, schema_version)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_key) DO UPDATE SET
                    session_json=excluded.session_json,
                    session_sha256=excluded.session_sha256,
                    updated_at=excluded.updated_at,
                    schema_version=excluded.schema_version
                """,
                (normalized, session_json, content_hash, now, now, _SESSION_SCHEMA),
            )

    def get_session(self, session_key: str) -> EngineeringSessionContext:
        """Reload a context independently of the in-process cache."""
        normalized = self._normalise_session_key(session_key)
        with self._lock:
            self._ensure_open()
            row = self._connection.execute(
                "SELECT * FROM engineering_sessions WHERE session_key = ?",
                (normalized,),
            ).fetchone()
        if row is None:
            raise SessionNotFoundError(f"SESSION_NOT_FOUND: no session for {normalized}")
        session_json = row["session_json"]
        stored_hash = str(row["session_sha256"] or "").lower()
        if not isinstance(session_json, str) or stored_hash != hashlib.sha256(session_json.encode("utf-8")).hexdigest():
            raise SessionIntegrityError("SESSION_INTEGRITY_FAILURE: stored session payload was modified")
        if str(row["schema_version"] or "") != _SESSION_SCHEMA:
            raise SessionIntegrityError("SESSION_INTEGRITY_FAILURE: unsupported session schema")
        try:
            payload = json.loads(session_json)
            context = EngineeringSessionContext.from_dict(payload)
        except (TypeError, ValueError, json.JSONDecodeError, SessionContextError) as exc:
            raise SessionIntegrityError("SESSION_INTEGRITY_FAILURE: stored session payload is invalid") from exc
        if context.to_json() != session_json:
            raise SessionIntegrityError("SESSION_INTEGRITY_FAILURE: stored session payload is not canonical")
        return context

    def delete_session(self, session_key: str) -> None:
        """Delete one chat context, used by explicit /reset only."""
        normalized = self._normalise_session_key(session_key)
        with self._lock, self._connection:
            self._ensure_open()
            self._connection.execute(
                "DELETE FROM engineering_sessions WHERE session_key = ?",
                (normalized,),
            )

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            try:
                self._connection.close()
            finally:
                self._closed = True
                self._cache.clear()
            self._comparison_cache.clear()


__all__ = [
    "AuditEvent",
    "CaseIntegrityError",
    "CaseNotFoundError",
    "EngineeringCaseRegistry",
]
