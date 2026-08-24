"""Engineering data and chat-scoped context for Engineering Assistant Core V2.

This module is deliberately an orchestration/data contract layer.  It owns no
petroleum equations, does not call AI, and never infers a missing engineering
value.  Numerical results remain owned by the released engineering engines and
EngineeringCase envelope.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
import hashlib
import json
import math
import re
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple


DATA_MODEL_SCHEMA = "engineering_data_model_v2"
SESSION_SCHEMA = "engineering_session_context_v2"
MAX_PRIOR_CASES = 32
MAX_PRIOR_COMPARISONS = 16
_ID_RE = re.compile(r"^[0-9a-fA-F]{64}$")


class SessionContextError(ValueError):
    """Typed, user-safe failure in the Core V2 context contract."""

    def __init__(self, code: str, message: str):
        self.code = str(code)
        self.message = str(message)
        super().__init__(f"{self.code}: {self.message}")


class ContextResolutionError(SessionContextError):
    """Typed failure when a conversational engineering reference is unsafe."""


class EngineeringValueOrigin(str, Enum):
    USER_PROVIDED = "USER_PROVIDED"
    DEFAULTED = "DEFAULTED"
    CALCULATED = "CALCULATED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class EngineeringValue:
    """One value with explicit origin and optional engineering unit."""

    value: Any = None
    unit: Optional[str] = None
    origin: EngineeringValueOrigin = EngineeringValueOrigin.UNKNOWN
    source: Optional[str] = None

    def __post_init__(self) -> None:
        origin = self.origin
        if not isinstance(origin, EngineeringValueOrigin):
            try:
                origin = EngineeringValueOrigin(str(origin).upper())
            except ValueError as exc:
                raise SessionContextError("INVALID_DATA_MODEL", "unsupported value origin") from exc
            object.__setattr__(self, "origin", origin)
        if origin is EngineeringValueOrigin.UNKNOWN and self.value is not None:
            raise SessionContextError(
                "INVALID_DATA_MODEL",
                "UNKNOWN values must not carry an inferred value",
            )
        if isinstance(self.value, float) and not math.isfinite(self.value):
            raise SessionContextError("INVALID_DATA_MODEL", "non-finite values are not permitted")
        if self.unit is not None:
            object.__setattr__(self, "unit", str(self.unit))
        if self.source is not None:
            object.__setattr__(self, "source", str(self.source))

    @classmethod
    def unknown(cls, unit: Optional[str] = None) -> "EngineeringValue":
        return cls(value=None, unit=unit, origin=EngineeringValueOrigin.UNKNOWN)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "EngineeringValue":
        if not isinstance(payload, Mapping):
            raise SessionContextError("SCHEMA_INCOMPATIBLE", "engineering value must be an object")
        return cls(
            value=payload.get("value"),
            unit=payload.get("unit"),
            origin=payload.get("origin", EngineeringValueOrigin.UNKNOWN.value),
            source=payload.get("source"),
        )

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "value": self.value,
            "unit": self.unit,
            "origin": self.origin.value,
        }
        if self.source:
            result["source"] = self.source
        return result


def _coerce_values(section: Mapping[str, Any]) -> Dict[str, EngineeringValue]:
    if not isinstance(section, Mapping):
        raise SessionContextError("SCHEMA_INCOMPATIBLE", "data model sections must be objects")
    result: Dict[str, EngineeringValue] = {}
    for key, value in section.items():
        name = str(key).strip()
        if not name:
            raise SessionContextError("INVALID_DATA_MODEL", "data model field names cannot be empty")
        result[name] = value if isinstance(value, EngineeringValue) else EngineeringValue.from_dict(value)
    return result


@dataclass(frozen=True)
class EngineeringDataModel:
    """Serializable optional engineering profile used by the session layer."""

    well: Mapping[str, EngineeringValue] = field(default_factory=dict)
    reservoir_fluid: Mapping[str, EngineeringValue] = field(default_factory=dict)
    flow: Mapping[str, EngineeringValue] = field(default_factory=dict)
    equipment: Mapping[str, EngineeringValue] = field(default_factory=dict)
    measurements: Mapping[str, EngineeringValue] = field(default_factory=dict)
    traceability: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = DATA_MODEL_SCHEMA

    def __post_init__(self) -> None:
        if self.schema_version != DATA_MODEL_SCHEMA:
            raise SessionContextError("SCHEMA_INCOMPATIBLE", f"unsupported data model schema: {self.schema_version}")
        for section in ("well", "reservoir_fluid", "flow", "equipment", "measurements"):
            object.__setattr__(self, section, _coerce_values(getattr(self, section)))
        if not isinstance(self.traceability, Mapping):
            raise SessionContextError("SCHEMA_INCOMPATIBLE", "traceability must be an object")
        object.__setattr__(self, "traceability", dict(self.traceability))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "well": {key: value.to_dict() for key, value in self.well.items()},
            "reservoir_fluid": {key: value.to_dict() for key, value in self.reservoir_fluid.items()},
            "flow": {key: value.to_dict() for key, value in self.flow.items()},
            "equipment": {key: value.to_dict() for key, value in self.equipment.items()},
            "measurements": {key: value.to_dict() for key, value in self.measurements.items()},
            "traceability": dict(self.traceability),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "EngineeringDataModel":
        if not isinstance(payload, Mapping):
            raise SessionContextError("SCHEMA_INCOMPATIBLE", "engineering data model must be an object")
        return cls(
            well=payload.get("well", {}),
            reservoir_fluid=payload.get("reservoir_fluid", {}),
            flow=payload.get("flow", {}),
            equipment=payload.get("equipment", {}),
            measurements=payload.get("measurements", {}),
            traceability=payload.get("traceability", {}),
            schema_version=str(payload.get("schema_version", DATA_MODEL_SCHEMA)),
        )

    @classmethod
    def from_json(cls, payload: str) -> "EngineeringDataModel":
        if not isinstance(payload, str):
            raise SessionContextError("SCHEMA_INCOMPATIBLE", "engineering data model JSON must be a string")
        try:
            return cls.from_dict(json.loads(payload))
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise SessionContextError("SCHEMA_INCOMPATIBLE", "engineering data model JSON is invalid") from exc

    def get(self, section: str, field_name: str) -> EngineeringValue:
        values = getattr(self, str(section), None)
        if not isinstance(values, Mapping):
            raise SessionContextError("INVALID_DATA_MODEL", f"unknown data model section: {section}")
        return values.get(str(field_name), EngineeringValue.unknown())

    def with_value(
        self,
        section: str,
        field_name: str,
        value: Any,
        *,
        unit: Optional[str] = None,
        origin: EngineeringValueOrigin = EngineeringValueOrigin.USER_PROVIDED,
        source: Optional[str] = None,
    ) -> "EngineeringDataModel":
        if section not in {"well", "reservoir_fluid", "flow", "equipment", "measurements"}:
            raise SessionContextError("INVALID_DATA_MODEL", f"unknown data model section: {section}")
        values = dict(getattr(self, section))
        values[str(field_name)] = EngineeringValue(value, unit, origin, source)
        return replace(self, **{section: values})


# Only stable aliases from released case input envelopes are mapped.  Unknown
# input keys remain absent; they are never assigned to an invented domain.
_FIELD_MAP: Dict[str, Tuple[str, str, str]] = {
    "pr": ("reservoir_fluid", "reservoir_pressure_psia", "psia"),
    "reservoir_pressure_psia": ("reservoir_fluid", "reservoir_pressure_psia", "psia"),
    "tvd": ("well", "tvd_ft", "ft"),
    "tvd_ft": ("well", "tvd_ft", "ft"),
    "id": ("well", "tubing_id_in", "in"),
    "tubing_id_in": ("well", "tubing_id_in", "in"),
    "tubing_id": ("well", "tubing_id_in", "in"),
    "thp": ("well", "thp_psia", "psia"),
    "thp_psia": ("well", "thp_psia", "psia"),
    "t_wh": ("well", "wellhead_temperature_f", "degF"),
    "t_wh_f": ("well", "wellhead_temperature_f", "degF"),
    "geothermal": ("well", "geothermal_f_100ft", "degF/100ft"),
    "geothermal_f_100ft": ("well", "geothermal_f_100ft", "degF/100ft"),
    "api": ("reservoir_fluid", "oil_api", "deg API"),
    "oil_api": ("reservoir_fluid", "oil_api", "deg API"),
    "gamma_g": ("reservoir_fluid", "gas_specific_gravity", "specific gravity"),
    "gas_specific_gravity": ("reservoir_fluid", "gas_specific_gravity", "specific gravity"),
    "rs": ("reservoir_fluid", "solution_gor_scf_stb", "scf/STB"),
    "rs_scf_stb": ("reservoir_fluid", "solution_gor_scf_stb", "scf/STB"),
    "bo": ("reservoir_fluid", "oil_fvf_rb_stb", "rb/STB"),
    "bo_rb_stb": ("reservoir_fluid", "oil_fvf_rb_stb", "rb/STB"),
    "gor": ("flow", "gor_scf_stb", "scf/STB"),
    "gor_scf_stb": ("flow", "gor_scf_stb", "scf/STB"),
    "wc": ("flow", "water_cut", "fraction"),
    "water_cut": ("flow", "water_cut", "fraction"),
    "q": ("flow", "rate_stbd", "STB/day"),
    "q_liquid": ("flow", "rate_stbd", "STB/day"),
    "q_liquid_bpd": ("flow", "rate_stbd", "bbl/day"),
    "liquid_rate_bpd": ("flow", "rate_stbd", "STB/day"),
    "liquid_rate_stbd": ("flow", "rate_stbd", "STB/day"),
    "choke": ("equipment", "choke_size_64th_in", "64ths of inch"),
    "choke_size_64th_in": ("equipment", "choke_size_64th_in", "64ths of inch"),
    "p_down": ("equipment", "downstream_pressure_psia", "psia"),
    "downstream_pressure_psia": ("equipment", "downstream_pressure_psia", "psia"),
    "p_up": ("equipment", "upstream_pressure_psia", "psia"),
    "upstream_pressure_psia": ("equipment", "upstream_pressure_psia", "psia"),
    "j": ("reservoir_fluid", "productivity_index_stbd_psi", "STB/day/psi"),
    "productivity_index_stbd_psi": ("reservoir_fluid", "productivity_index_stbd_psi", "STB/day/psi"),
    "pvt_pressure_psia": ("reservoir_fluid", "pvt_pressure_psia", "psia"),
    "pvt_temperature_f": ("reservoir_fluid", "pvt_temperature_f", "degF"),
    "pvt_oil_api": ("reservoir_fluid", "pvt_oil_api", "deg API"),
    "pvt_gas_specific_gravity": ("reservoir_fluid", "pvt_gas_specific_gravity", "specific gravity"),
    "pvt_separator_pressure_psia": ("reservoir_fluid", "separator_pressure_psia", "psia"),
    "pvt_separator_temperature_f": ("reservoir_fluid", "separator_temperature_f", "degF"),
    "pvt_bubble_point_psia": ("reservoir_fluid", "bubble_point_psia", "psia"),
}


def _request_keys(case: Any) -> set[str]:
    request = getattr(case, "request", {})
    if not isinstance(request, Mapping):
        return set()
    arguments = request.get("arguments", request)
    if not isinstance(arguments, Mapping):
        return set()
    return {str(key).strip().lower() for key in arguments}


def _case_value_origin(key: str, explicit_keys: set[str], field_name: Optional[str] = None) -> EngineeringValueOrigin:
    candidates = {key.lower()}
    if field_name:
        candidates.add(str(field_name).lower())
    for alias, target in _FIELD_MAP.items():
        if field_name and target[1] == field_name:
            candidates.add(alias.lower())
    return EngineeringValueOrigin.USER_PROVIDED if candidates & explicit_keys else EngineeringValueOrigin.DEFAULTED


def data_model_from_case(case: Any) -> EngineeringDataModel:
    """Build a safe profile from case data and released result provenance only."""
    model = EngineeringDataModel()
    explicit_keys = _request_keys(case)
    inputs = getattr(case, "inputs", {})
    if isinstance(inputs, Mapping):
        for raw_key, raw_value in inputs.items():
            key = str(raw_key).lower()
            target = _FIELD_MAP.get(key)
            if target is None or raw_value is None or isinstance(raw_value, (Mapping, list, tuple)):
                continue
            section, field_name, unit = target
            model = model.with_value(
                section,
                field_name,
                raw_value,
                unit=unit,
                origin=_case_value_origin(key, explicit_keys, field_name),
                source=f"case.inputs.{raw_key}",
            )
    pvt = getattr(case, "pvt", {})
    if isinstance(pvt, Mapping):
        context = pvt.get("context", {})
        if isinstance(context, Mapping):
            for raw_key, raw_value in context.items():
                key = str(raw_key).lower()
                aliases = {
                    "pressure_psia": "pvt_pressure_psia",
                    "temperature_f": "pvt_temperature_f",
                    "oil_api": "pvt_oil_api",
                    "gas_specific_gravity": "pvt_gas_specific_gravity",
                    "separator_pressure_psia": "pvt_separator_pressure_psia",
                    "separator_temperature_f": "pvt_separator_temperature_f",
                    "bubble_point_psia": "pvt_bubble_point_psia",
                }
                mapped = aliases.get(key, key)
                target = _FIELD_MAP.get(mapped)
                if target is not None and raw_value is not None and not isinstance(raw_value, (Mapping, list, tuple)):
                    section, field_name, unit = target
                    model = model.with_value(
                        section,
                        field_name,
                        raw_value,
                        unit=unit,
                        origin=_case_value_origin(mapped, explicit_keys, field_name),
                        source=f"case.pvt.context.{raw_key}",
                    )
    result = getattr(case, "result", {})
    if isinstance(result, Mapping):
        for raw_key, raw_value in result.items():
            if raw_key in {"status", "warnings", "limitations", "pvt_metadata", "error"}:
                continue
            if isinstance(raw_value, (bool, int, float)) and not isinstance(raw_value, bool):
                model = model.with_value(
                    "measurements",
                    str(raw_key),
                    raw_value,
                    unit=None,
                    origin=EngineeringValueOrigin.CALCULATED,
                    source=f"case.result.{raw_key}",
                )
    traceability = {
        "case_id": str(getattr(case, "case_id", "")),
        "calculation_type": str(getattr(case, "calculation_type", "")),
        "status": str(getattr(case, "status", "")),
        "release": str(getattr(case, "release", "")),
        "model": getattr(case, "model", {}),
        "selectors": getattr(case, "selectors", {}),
        "pvt_mode": pvt.get("mode") if isinstance(pvt, Mapping) else None,
        "pvt_model": pvt.get("model") if isinstance(pvt, Mapping) else None,
    }
    return replace(model, traceability=traceability)


@dataclass(frozen=True)
class EngineeringSessionContext:
    """Bounded, serializable context for one Telegram chat."""

    current_case_id: Optional[str] = None
    prior_case_ids: Tuple[str, ...] = ()
    current_comparison_id: Optional[str] = None
    prior_comparison_ids: Tuple[str, ...] = ()
    current_calculation_type: Optional[str] = None
    domain: Optional[str] = None
    selected_model: Mapping[str, Any] = field(default_factory=dict)
    pvt_context: Mapping[str, Any] = field(default_factory=dict)
    current_profile: EngineeringDataModel = field(default_factory=EngineeringDataModel)
    schema_version: str = SESSION_SCHEMA

    def __post_init__(self) -> None:
        if self.schema_version != SESSION_SCHEMA:
            raise SessionContextError("SCHEMA_INCOMPATIBLE", f"unsupported session schema: {self.schema_version}")
        for identifier in (
            self.current_case_id,
            *self.prior_case_ids,
            self.current_comparison_id,
            *self.prior_comparison_ids,
        ):
            if identifier is not None and not _ID_RE.fullmatch(str(identifier)):
                raise SessionContextError("INVALID_SESSION", "session contains an invalid deterministic ID")
        object.__setattr__(self, "prior_case_ids", tuple(str(item) for item in self.prior_case_ids if item))
        object.__setattr__(self, "prior_comparison_ids", tuple(str(item) for item in self.prior_comparison_ids if item))
        object.__setattr__(self, "selected_model", dict(self.selected_model))
        object.__setattr__(self, "pvt_context", dict(self.pvt_context))
        if not isinstance(self.current_profile, EngineeringDataModel):
            object.__setattr__(self, "current_profile", EngineeringDataModel.from_dict(self.current_profile))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "current_case_id": self.current_case_id,
            "prior_case_ids": list(self.prior_case_ids),
            "current_comparison_id": self.current_comparison_id,
            "prior_comparison_ids": list(self.prior_comparison_ids),
            "current_calculation_type": self.current_calculation_type,
            "domain": self.domain,
            "selected_model": dict(self.selected_model),
            "pvt_context": dict(self.pvt_context),
            "current_profile": self.current_profile.to_dict(),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "EngineeringSessionContext":
        if not isinstance(payload, Mapping):
            raise SessionContextError("SCHEMA_INCOMPATIBLE", "session context must be an object")
        return cls(
            current_case_id=payload.get("current_case_id"),
            prior_case_ids=tuple(payload.get("prior_case_ids", ())),
            current_comparison_id=payload.get("current_comparison_id"),
            prior_comparison_ids=tuple(payload.get("prior_comparison_ids", ())),
            current_calculation_type=payload.get("current_calculation_type"),
            domain=payload.get("domain"),
            selected_model=payload.get("selected_model", {}),
            pvt_context=payload.get("pvt_context", {}),
            current_profile=EngineeringDataModel.from_dict(payload.get("current_profile", {})),
            schema_version=str(payload.get("schema_version", SESSION_SCHEMA)),
        )

    @classmethod
    def from_json(cls, payload: str) -> "EngineeringSessionContext":
        if not isinstance(payload, str):
            raise SessionContextError("SCHEMA_INCOMPATIBLE", "session context JSON must be a string")
        try:
            return cls.from_dict(json.loads(payload))
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise SessionContextError("SCHEMA_INCOMPATIBLE", "session context JSON is invalid") from exc

    def with_case(self, case: Any) -> "EngineeringSessionContext":
        case_id = str(getattr(case, "case_id", "")).lower()
        if not _ID_RE.fullmatch(case_id):
            raise SessionContextError("INVALID_SESSION", "cannot track a case without a valid case ID")
        previous = [item for item in self.prior_case_ids if item != case_id and item != self.current_case_id]
        if self.current_case_id and self.current_case_id != case_id:
            previous.append(self.current_case_id)
        previous = previous[-MAX_PRIOR_CASES:]
        pvt = getattr(case, "pvt", {})
        return replace(
            self,
            current_case_id=case_id,
            prior_case_ids=tuple(previous),
            current_calculation_type=str(getattr(case, "calculation_type", "")),
            domain=str(getattr(case, "calculation_type", "")).split("_")[0] or None,
            selected_model=getattr(case, "model", {}) if isinstance(getattr(case, "model", {}), Mapping) else {},
            pvt_context=pvt.get("context", {}) if isinstance(pvt, Mapping) else {},
            current_profile=data_model_from_case(case),
        )

    def with_comparison(self, comparison: Any) -> "EngineeringSessionContext":
        comparison_id = str(getattr(comparison, "comparison_id", "")).lower()
        if not _ID_RE.fullmatch(comparison_id):
            raise SessionContextError("INVALID_SESSION", "cannot track a comparison without a valid ID")
        prior = [item for item in self.prior_comparison_ids if item != comparison_id and item != self.current_comparison_id]
        if self.current_comparison_id and self.current_comparison_id != comparison_id:
            prior.append(self.current_comparison_id)
        return replace(self, current_comparison_id=comparison_id, prior_comparison_ids=tuple(prior[-MAX_PRIOR_COMPARISONS:]))

    def resolve_case_id(self, reference: Optional[str] = None) -> str:
        """Resolve only explicit, unambiguous references; never choose by guess."""
        ref = "" if reference is None else str(reference).strip().lower()
        if not ref:
            ref = "current"
        if _ID_RE.fullmatch(ref):
            known = {self.current_case_id, *self.prior_case_ids}
            if ref not in known:
                raise ContextResolutionError("CASE_NOT_IN_CONTEXT", "the supplied case ID is not in this chat context")
            return ref
        current_terms = {"current", "current case", "this case", "it", "its", "case", "same well", "الحالة الحالية", "هذه الحالة", "الحالة", "نفس البئر"}
        previous_terms = {"previous", "previous case", "last case", "the one before", "الحالة السابقة", "اللي قبلها", "قبلها"}
        first_terms = {"first", "first case", "الحالة الأولى", "الحالة الاولي", "اول حالة", "أول حالة"}
        if ref in current_terms:
            if not self.current_case_id:
                raise ContextResolutionError("NO_CURRENT_CASE", "there is no current engineering case in this chat")
            return self.current_case_id
        if ref in previous_terms:
            if not self.prior_case_ids:
                raise ContextResolutionError("NO_PREVIOUS_CASE", "there is no previous engineering case in this chat")
            return self.prior_case_ids[-1]
        if ref in first_terms:
            candidates = list(self.prior_case_ids)
            if self.current_case_id:
                candidates.append(self.current_case_id)
            if not candidates:
                raise ContextResolutionError("NO_CASE_CONTEXT", "there is no engineering case in this chat")
            return candidates[0]
        raise ContextResolutionError("AMBIGUOUS_REFERENCE", "please specify current case, previous case, first case, or a full Case ID")


def session_key_for_chat(chat_id: Any) -> str:
    """Return a non-reversible storage key; raw Telegram IDs are not persisted."""
    return hashlib.sha256(str(chat_id).encode("utf-8")).hexdigest()


__all__ = [
    "DATA_MODEL_SCHEMA",
    "SESSION_SCHEMA",
    "EngineeringValueOrigin",
    "EngineeringValue",
    "EngineeringDataModel",
    "EngineeringSessionContext",
    "SessionContextError",
    "ContextResolutionError",
    "data_model_from_case",
    "session_key_for_chat",
]
