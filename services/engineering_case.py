"""Canonical, replayable engineering cases for the released calculation engines.

This module is deliberately an orchestration/serialization layer.  It contains
no petroleum equations and does not replace any released engineering engine.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from typing import Any, Callable, Dict, Optional


_SCHEMA_VERSION = "engineering_case_v1"
_DEFAULT_RELEASE = "phase5c_increment13_case_report_v1"
_MISSING = object()

# Keys that identify transport credentials, user/session metadata, or secrets.
# Engineering keys such as ``api`` and ``provider`` intentionally remain valid.
_SECRET_KEY_RE = re.compile(
    r"(?:^|[_-])(token|secret|password|passwd|api[_-]?key|authorization|bearer|credential|private[_-]?key)(?:$|[_-])",
    re.IGNORECASE,
)
_TELEGRAM_KEY_RE = re.compile(
    r"(?:^|[_-])(telegram|chat[_-]?id|user[_-]?id|message[_-]?id|update[_-]?id|username|first[_-]?name|last[_-]?name)(?:$|[_-])",
    re.IGNORECASE,
)
_SECRET_VALUE_PATTERNS = (
    re.compile(r"\bghp_[A-Za-z0-9_]+\b"),
    re.compile(r"\bbot\d+:[A-Za-z0-9_-]+\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]+\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]+\b", re.IGNORECASE),
)


class CaseReplayError(ValueError):
    """Typed, user-safe error raised when a case cannot be replayed."""


class _OmitValue:
    pass


_OMIT = _OmitValue()


def _key_is_sensitive(key: Any) -> bool:
    text = str(key).strip().lower()
    return bool(_SECRET_KEY_RE.search(text) or _TELEGRAM_KEY_RE.search(text))


def _scrub_string(value: str) -> str:
    result = value
    for pattern in _SECRET_VALUE_PATTERNS:
        result = pattern.sub("[REDACTED]", result)
    return result


def _plain(value: Any) -> Any:
    """Convert engine/dataclass values to JSON-compatible plain values."""
    if value is None or isinstance(value, (str, bool, int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("non-finite numeric value cannot enter an engineering case")
        return _scrub_string(value) if isinstance(value, str) else value
    if is_dataclass(value):
        return _plain(asdict(value))
    if isinstance(value, Mapping):
        output: Dict[str, Any] = {}
        for key, item in value.items():
            if _key_is_sensitive(key):
                continue
            cleaned = _plain(item)
            if cleaned is not _OMIT:
                output[str(key)] = cleaned
        return output
    if isinstance(value, (list, tuple)):
        return [item for item in (_plain(item) for item in value) if item is not _OMIT]
    if isinstance(value, (set, frozenset)):
        items = [_plain(item) for item in value]
        return sorted((item for item in items if item is not _OMIT), key=_sort_key)
    if isinstance(value, BaseException):
        return {"type": type(value).__name__, "message": _scrub_string(str(value))}
    if hasattr(value, "__dict__"):
        return _plain(vars(value))
    return _scrub_string(str(value))


def _sort_key(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _normalize_numeric(value: Any) -> Any:
    """Normalize 1, 1.0, and numeric Decimal values to the same hash form."""
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite numeric value cannot enter an engineering case")
        if value == 0.0:
            return 0
        try:
            decimal = Decimal(str(value)).normalize()
        except InvalidOperation as exc:
            raise ValueError("invalid numeric value cannot enter an engineering case") from exc
        if decimal == decimal.to_integral_value():
            return int(decimal)
        return float(decimal)
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("non-finite numeric value cannot enter an engineering case")
        normalized = value.normalize()
        if normalized == normalized.to_integral_value():
            return int(normalized)
        return float(normalized)
    return value


def _canonicalize(value: Any) -> Any:
    value = _plain(value)
    if isinstance(value, Mapping):
        return {str(key): _canonicalize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_canonicalize(item) for item in value]
    return _normalize_numeric(value)


def canonical_json(value: Any) -> str:
    """Return the stable JSON representation used for case identity."""
    normalized = _canonicalize(value)
    return json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def build_case_id(canonical_dict: Mapping[str, Any]) -> str:
    """Build a deterministic SHA-256 identity from a canonicalizable mapping."""
    if not isinstance(canonical_dict, Mapping):
        raise TypeError("canonical_dict must be a mapping")
    digest = hashlib.sha256(canonical_json(canonical_dict).encode("utf-8"))
    return digest.hexdigest()


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set, frozenset)):
        return list(value)
    return [value]


@dataclass(frozen=True)
class EngineeringCase:
    """Immutable engineering-case envelope around a released calculation."""

    case_id: str
    calculation_type: str
    request: Any = field(default_factory=dict)
    inputs: Dict[str, Any] = field(default_factory=dict)
    units: Dict[str, Any] = field(default_factory=dict)
    selectors: Dict[str, Any] = field(default_factory=dict)
    model: Any = field(default_factory=dict)
    pvt: Any = field(default_factory=dict)
    assumptions: Any = field(default_factory=dict)
    result: Any = field(default_factory=dict)
    status: str = "OK"
    limitations: list[Any] = field(default_factory=list)
    warnings: list[Any] = field(default_factory=list)
    release: str = _DEFAULT_RELEASE
    reproducibility: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Frozen prevents field reassignment; deep plain copies prevent callers
        # from injecting non-serializable engine objects after construction.
        for name in (
            "request", "inputs", "units", "selectors", "model", "pvt",
            "assumptions", "result", "limitations", "warnings", "reproducibility",
        ):
            object.__setattr__(self, name, _plain(getattr(self, name)))
        object.__setattr__(self, "calculation_type", str(self.calculation_type))
        object.__setattr__(self, "status", str(self.status))
        object.__setattr__(self, "release", str(self.release))

    @property
    def identity_payload(self) -> Dict[str, Any]:
        """The engineering state used to derive ``case_id``."""
        return {
            "calculation_type": self.calculation_type,
            "inputs": self.inputs,
            "units": self.units,
            "selectors": self.selectors,
            "model": self.model,
            "pvt": self.pvt,
            "assumptions": self.assumptions,
            "release": self.release,
        }

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the case to a secret-free plain dictionary."""
        payload = {
            "case_id": self.case_id,
            "calculation_type": self.calculation_type,
            "request": self.request,
            "inputs": self.inputs,
            "units": self.units,
            "selectors": self.selectors,
            "model": self.model,
            "pvt": self.pvt,
            "assumptions": self.assumptions,
            "result": self.result,
            "status": self.status,
            "limitations": self.limitations,
            "warnings": self.warnings,
            "release": self.release,
            "reproducibility": self.reproducibility,
        }
        return _plain(payload)

    def to_json(self) -> str:
        """Serialize the case with stable key ordering and separators."""
        return json.dumps(
            self.to_dict(), ensure_ascii=False, sort_keys=True,
            separators=(",", ":"), allow_nan=False,
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "EngineeringCase":
        """Reconstruct a case and recompute its identity from the state."""
        if not isinstance(payload, Mapping):
            raise TypeError("engineering case payload must be a mapping")
        data = _plain(payload)
        return build_case(
            calculation_type=data.get("calculation_type", "unknown"),
            request=data.get("request", {}),
            inputs=data.get("inputs", {}),
            units=data.get("units", {}),
            selectors=data.get("selectors", {}),
            model=data.get("model", {}),
            pvt=data.get("pvt", {}),
            assumptions=data.get("assumptions", {}),
            result=data.get("result", {}),
            status=data.get("status", "OK"),
            limitations=data.get("limitations", []),
            warnings=data.get("warnings", []),
            release=data.get("release", _DEFAULT_RELEASE),
            reproducibility=data.get("reproducibility", {}),
        )

    @classmethod
    def from_json(cls, payload: str) -> "EngineeringCase":
        if not isinstance(payload, str):
            raise TypeError("engineering case JSON must be a string")
        return cls.from_dict(json.loads(payload))


def build_case(
    calculation_type: str,
    inputs: Mapping[str, Any] | None = None,
    units: Mapping[str, Any] | None = None,
    selectors: Mapping[str, Any] | None = None,
    model: Any = None,
    pvt: Any = None,
    assumptions: Any = None,
    result: Any = None,
    status: str = "OK",
    limitations: Any = None,
    warnings: Any = None,
    release: str = _DEFAULT_RELEASE,
    request: Any = None,
    reproducibility: Mapping[str, Any] | None = None,
) -> EngineeringCase:
    """Create a secret-free case and derive its deterministic identity."""
    case = EngineeringCase(
        case_id="pending",
        calculation_type=calculation_type,
        request={} if request is None else request,
        inputs={} if inputs is None else inputs,
        units={} if units is None else units,
        selectors={} if selectors is None else selectors,
        model={} if model is None else model,
        pvt={} if pvt is None else pvt,
        assumptions={} if assumptions is None else assumptions,
        result={} if result is None else result,
        status=status,
        limitations=_as_list(limitations),
        warnings=_as_list(warnings),
        release=release,
        reproducibility={
            "schema": _SCHEMA_VERSION,
            "hash": "sha256",
            "canonical_json": "sorted_keys_stable_separators_normalized_numerics",
            "replayable": str(calculation_type).strip().lower()
            in {
                "system", "calc_system", "integrated_system", "integrated_system_v1",
                "choke", "choke_v1",
                "nodal", "nodal_v1",
            },
            **({} if reproducibility is None else dict(reproducibility)),
        },
    )
    return EngineeringCase(
        case_id=build_case_id(case.identity_payload),
        calculation_type=case.calculation_type,
        request=case.request,
        inputs=case.inputs,
        units=case.units,
        selectors=case.selectors,
        model=case.model,
        pvt=case.pvt,
        assumptions=case.assumptions,
        result=case.result,
        status=case.status,
        limitations=case.limitations,
        warnings=case.warnings,
        release=case.release,
        reproducibility=case.reproducibility,
    )


def _system_input_from_case(case: EngineeringCase) -> Any:
    from services.system_engine import SystemInput

    data = dict(case.inputs)
    aliases = {
        "tubing_id": "tubing_id_in",
        "choke_size": "choke_size_64th_in",
        "downstream_pressure": "downstream_pressure_psia",
        "bo": "bo_rb_stb",
        "rs": "rs_scf_stb",
        "gor": "gor_scf_stb",
        "mu_l": "mu_l_cp",
        "t_wh": "t_wh_f",
        "geothermal": "geothermal_f_100ft",
        "segments": "n_segments",
        "z": "z_factor",
    }
    for old, new in aliases.items():
        if new not in data and old in data:
            data[new] = data[old]
    allowed = set(SystemInput.__dataclass_fields__)
    clean = {key: value for key, value in data.items() if key in allowed}
    # Let the engine own validation/error wording; constructor TypeError is
    # translated to a typed replay error at this boundary.
    try:
        return SystemInput(**clean)
    except (TypeError, ValueError) as exc:
        raise CaseReplayError(f"INVALID_CASE_INPUT: {exc}") from exc


def _nodal_input_from_case(case: EngineeringCase) -> Dict[str, Any]:
    """Return only released NodalEngine keyword arguments from a case."""
    from services.nodal_engine import NodalEngine

    data = dict(case.inputs)
    aliases = {
        "id": "tubing_id_in",
        "z": "z_factor",
        "segments": "n_segments",
        "model": "ipr_model",
    }
    for old, new in aliases.items():
        if new not in data and old in data:
            data[new] = data[old]
    allowed = set(__import__("inspect").signature(NodalEngine.solve).parameters)
    clean = {key: value for key, value in data.items() if key in allowed}
    pvt_data = case.pvt if isinstance(case.pvt, Mapping) else {}
    mode = str(pvt_data.get("mode", "")).strip().lower()
    model = str(pvt_data.get("model", "")).strip().lower()
    if mode == "pressure_dependent" or model == "black_oil_v1":
        if mode != "pressure_dependent" or model != "black_oil_v1":
            raise CaseReplayError(
                "UNSUPPORTED_PVT_SELECTOR: explicit Black-Oil replay requires "
                "pressure_dependent/black_oil_v1"
            )
        context = pvt_data.get("context")
        if not isinstance(context, Mapping):
            raise CaseReplayError(
                "PHYSICALLY_INVALID_STATE: replay case lacks Black-Oil PVT context"
            )
        from services.black_oil_pvt import BlackOilPvtProvider
        clean["pvt_provider"] = BlackOilPvtProvider()
        clean["pvt_context"] = dict(context)
    try:
        return clean
    except (TypeError, ValueError) as exc:
        raise CaseReplayError(f"INVALID_CASE_INPUT: {exc}") from exc


def _choke_input_from_case(case: EngineeringCase) -> Any:
    from services.choke_engine import ChokeInput

    data = dict(case.inputs)
    aliases = {
        "upstream_pressure": "upstream_pressure_psia",
        "downstream_pressure": "downstream_pressure_psia",
        "choke_size": "choke_size_64th_in",
        "gor": "gor_scf_stb",
        "liquid_rate": "liquid_rate_bpd",
        "model": "choke_model",
    }
    for old, new in aliases.items():
        if new not in data and old in data:
            data[new] = data[old]
    allowed = set(ChokeInput.__dataclass_fields__)
    clean = {key: value for key, value in data.items() if key in allowed}
    try:
        return ChokeInput(**clean)
    except (TypeError, ValueError) as exc:
        raise CaseReplayError(f"INVALID_CASE_INPUT: {exc}") from exc


def replay_case(
    case: EngineeringCase,
    runner: Optional[Callable[[EngineeringCase], EngineeringCase]] = None,
) -> EngineeringCase:
    """Replay a supported case through its original released engine.

    A runner is accepted for deterministic test doubles and future adapters;
    the production Increment 13 path supports IntegratedSystemEngine V1.
    """
    if not isinstance(case, EngineeringCase):
        raise TypeError("replay_case requires an EngineeringCase")
    if runner is not None:
        replayed = runner(case)
        if not isinstance(replayed, EngineeringCase):
            raise CaseReplayError("runner must return an EngineeringCase")
        return replayed

    kind = case.calculation_type.strip().lower()
    if kind in {"choke", "choke_v1"}:
        from services.black_oil_pvt import BlackOilPvtProvider
        from services.choke_engine import ChokeEngine, ChokeError

        inputs = _choke_input_from_case(case)
        pvt_data = case.pvt if isinstance(case.pvt, Mapping) else {}
        mode = str(pvt_data.get("mode", "")).strip().lower()
        model = str(pvt_data.get("model", "")).strip().lower()
        provider = None
        context = None
        if mode == "pressure_dependent" or model == "black_oil_v1":
            if mode != "pressure_dependent" or model != "black_oil_v1":
                raise CaseReplayError(
                    "UNSUPPORTED_PVT_SELECTOR: explicit Black-Oil replay requires "
                    "pressure_dependent/black_oil_v1"
                )
            provider = BlackOilPvtProvider()
            context = pvt_data.get("context")
            if not isinstance(context, Mapping):
                raise CaseReplayError(
                    "PHYSICALLY_INVALID_STATE: replay case lacks Black-Oil PVT context"
                )
            context = dict(context)
        try:
            result = ChokeEngine().calculate(
                inputs, pvt_provider=provider, pvt_context=context
            )
        except ChokeError as exc:
            return build_case(
                calculation_type=case.calculation_type,
                request=case.request,
                inputs=case.inputs,
                units=case.units,
                selectors=case.selectors,
                model=case.model,
                pvt=case.pvt,
                assumptions=case.assumptions,
                result={"error": {"code": exc.code, "message": exc.message}},
                status=exc.code,
                limitations=case.limitations,
                warnings=case.warnings,
                release=case.release,
                reproducibility=case.reproducibility,
            )
        if provider is not None:
            # The handler records explicit selector provenance under these keys.
            # Replay must reconstruct the same result envelope so comparison is
            # deterministic; the released ChokeEngine itself remains untouched.
            result.pvt_metadata["mode_selector"] = mode
            result.pvt_metadata["model_selector"] = model
        return build_case(
            calculation_type=case.calculation_type,
            request=case.request,
            inputs=case.inputs,
            units=case.units,
            selectors=case.selectors,
            model=case.model,
            pvt=case.pvt,
            assumptions=case.assumptions,
            result=result,
            status=getattr(result, "status", case.status),
            limitations=getattr(result, "limitations", case.limitations),
            warnings=getattr(result, "warnings", case.warnings),
            release=case.release,
            reproducibility=case.reproducibility,
        )

    if kind in {"nodal", "nodal_v1"}:
        from services.black_oil_pvt import BlackOilPvtProvider
        from services.nodal_engine import NodalEngine, NodalError

        kwargs = _nodal_input_from_case(case)
        try:
            result = NodalEngine().solve(**kwargs)
        except NodalError as exc:
            return build_case(
                calculation_type=case.calculation_type,
                request=case.request,
                inputs=case.inputs,
                units=case.units,
                selectors=case.selectors,
                model=case.model,
                pvt=case.pvt,
                assumptions=case.assumptions,
                result={"error": {"code": exc.kind, "message": str(exc)}},
                status=exc.kind,
                limitations=case.limitations,
                warnings=case.warnings,
                release=case.release,
                reproducibility=case.reproducibility,
            )
        return build_case(
            calculation_type=case.calculation_type,
            request=case.request,
            inputs=case.inputs,
            units=case.units,
            selectors=case.selectors,
            model=case.model,
            pvt=case.pvt,
            assumptions=case.assumptions,
            result=result,
            status=getattr(result, "status", case.status),
            limitations=getattr(result, "limitations", case.limitations),
            warnings=getattr(result, "warnings", case.warnings),
            release=case.release,
            reproducibility=case.reproducibility,
        )

    if kind not in {"system", "calc_system", "integrated_system", "integrated_system_v1"}:
        raise CaseReplayError(f"UNSUPPORTED_REPLAY_TYPE: {case.calculation_type}")

    from services.black_oil_pvt import BlackOilPvtProvider
    from services.system_engine import IntegratedSystemEngine, SystemError

    inputs = _system_input_from_case(case)
    pvt_data = case.pvt if isinstance(case.pvt, Mapping) else {}
    mode = str(pvt_data.get("mode", "")).strip().lower()
    model = str(pvt_data.get("model", "")).strip().lower()
    provider = None
    context = None
    if mode == "pressure_dependent" or model == "black_oil_v1":
        if mode != "pressure_dependent" or model != "black_oil_v1":
            raise CaseReplayError("UNSUPPORTED_PVT_SELECTOR: explicit Black-Oil replay requires pressure_dependent/black_oil_v1")
        provider = BlackOilPvtProvider()
        context = pvt_data.get("context")
        if not isinstance(context, Mapping):
            raise CaseReplayError("PHYSICALLY_INVALID_STATE: replay case lacks Black-Oil PVT context")
        context = dict(context)
    try:
        result = IntegratedSystemEngine().calculate(
            inputs, pvt_provider=provider, pvt_context=context
        )
    except SystemError as exc:
        # Keep the typed failure as data; this is the same public engineering
        # error contract and never leaks a Python traceback.
        result_payload = {"error": {"code": exc.code, "message": exc.message}}
        return build_case(
            calculation_type=case.calculation_type,
            request=case.request,
            inputs=case.inputs,
            units=case.units,
            selectors=case.selectors,
            model=case.model,
            pvt=case.pvt,
            assumptions=case.assumptions,
            result=result_payload,
            status=exc.code,
            limitations=case.limitations,
            warnings=case.warnings,
            release=case.release,
            reproducibility=case.reproducibility,
        )

    if provider is not None:
        # Match the released handler's explicit selector annotation exactly;
        # the frozen engine intentionally reports provider metadata only.
        result.pvt_metadata["mode"] = mode
        result.pvt_metadata["model"] = model

    return build_case(
        calculation_type=case.calculation_type,
        request=case.request,
        inputs=case.inputs,
        units=case.units,
        selectors=case.selectors,
        model=case.model,
        pvt=case.pvt,
        assumptions=case.assumptions,
        result=result,
        status=getattr(result, "status", case.status),
        limitations=getattr(result, "limitations", case.limitations),
        warnings=getattr(result, "warnings", case.warnings),
        release=case.release,
        reproducibility=case.reproducibility,
    )


def choke_input_to_dict(inputs: Any) -> Dict[str, Any]:
    """Serialize a released ``ChokeInput`` without Telegram metadata."""
    return _plain(asdict(inputs) if is_dataclass(inputs) else inputs)


def build_choke_case(
    inputs: Any,
    result: Any,
    *,
    request: Any = None,
    pvt_context: Optional[Mapping[str, Any]] = None,
    pvt_mode: Optional[str] = None,
    pvt_model: Optional[str] = None,
    status: Optional[str] = None,
    limitations: Any = None,
    warnings: Any = None,
) -> EngineeringCase:
    """Build a reproducible case around an already-computed Choke V1 result."""
    pvt: Dict[str, Any] = {}
    if pvt_mode is not None or pvt_model is not None or pvt_context is not None:
        pvt = {
            "mode": pvt_mode or "pressure_dependent",
            "model": pvt_model or "black_oil_v1",
            "context": {} if pvt_context is None else dict(pvt_context),
            "provenance": _plain(getattr(result, "pvt_metadata", {})),
        }
    return build_case(
        calculation_type="choke_v1",
        request={} if request is None else request,
        inputs=choke_input_to_dict(inputs),
        units={
            "pressure": "psia",
            "rate": "bbl/day",
            "gor": "scf/STB",
            "choke_size": "64ths of inch",
        },
        selectors={"choke_model": getattr(inputs, "choke_model", None)},
        model={"choke": getattr(inputs, "choke_model", None), "engine": "Gilbert (1954)"},
        pvt=pvt,
        assumptions={"choke_engine": "ChokeEngine V1"},
        result=result,
        status=status or getattr(result, "status", "OK"),
        limitations=limitations if limitations is not None else getattr(result, "limitations", []),
        warnings=warnings if warnings is not None else getattr(result, "warnings", []),
        reproducibility={"engine": "ChokeEngine", "engine_version": "V1"},
    )


def build_choke_failure_case(
    inputs: Any,
    *,
    code: str,
    message: str,
    request: Any = None,
    pvt_context: Optional[Mapping[str, Any]] = None,
    pvt_mode: Optional[str] = None,
    pvt_model: Optional[str] = None,
) -> EngineeringCase:
    """Represent a typed Choke failure without fabricating a result."""
    return build_choke_case(
        inputs,
        {"error": {"code": str(code), "message": str(message)}},
        request=request,
        pvt_context=pvt_context,
        pvt_mode=pvt_mode,
        pvt_model=pvt_model,
        status=code,
    )


def system_input_to_dict(inputs: Any) -> Dict[str, Any]:
    """Serialize a released ``SystemInput`` without Telegram metadata."""
    return _plain(asdict(inputs) if is_dataclass(inputs) else inputs)


def nodal_input_to_dict(inputs: Any) -> Dict[str, Any]:
    """Serialize released NodalEngine keyword inputs without chat metadata."""
    if isinstance(inputs, Mapping):
        return _plain(dict(inputs))
    return _plain(inputs)


def build_nodal_case(
    inputs: Any,
    result: Any,
    *,
    request: Any = None,
    pvt_context: Optional[Mapping[str, Any]] = None,
    pvt_mode: Optional[str] = None,
    pvt_model: Optional[str] = None,
    status: Optional[str] = None,
    limitations: Any = None,
    warnings: Any = None,
) -> EngineeringCase:
    """Build a reproducible case around an already-computed Nodal V1 result."""
    data = nodal_input_to_dict(inputs)
    pvt: Dict[str, Any] = {}
    if pvt_mode is not None or pvt_model is not None or pvt_context is not None:
        pvt = {
            "mode": pvt_mode or "pressure_dependent",
            "model": pvt_model or "black_oil_v1",
            "context": {} if pvt_context is None else dict(pvt_context),
            "provenance": _plain(getattr(result, "pvt_metadata", {})),
        }
    model = {
        "ipr": getattr(result, "ipr_model", data.get("ipr_model")),
        "vlp": getattr(result, "vlp_model", data.get("vlp_model")),
        "solver": getattr(result, "root_method", None),
    }
    selectors = {
        "ipr_model": data.get("ipr_model", data.get("model")),
        "vlp_model": data.get("vlp_model", "beggs_brill"),
    }
    return build_case(
        calculation_type="nodal_v1",
        request={} if request is None else request,
        inputs=data,
        units={
            "pressure": "psia",
            "rate": "STB/day",
            "tubing_id": "in",
            "depth": "ft",
            "gor": "scf/STB",
            "viscosity": "cP",
            "temperature": "degF",
            "geothermal_gradient": "degF/100ft",
        },
        selectors=selectors,
        model=model,
        pvt=pvt,
        assumptions={
            "nodal_engine": "NodalEngine V1",
            "residual_tolerance_psi": data.get("pressure_tol"),
            "n_points": data.get("n_points"),
            "segments": data.get("n_segments", data.get("segments")),
        },
        result=result,
        status=status or getattr(result, "status", "OK"),
        limitations=limitations if limitations is not None else getattr(result, "limitations", []),
        warnings=warnings if warnings is not None else getattr(result, "warnings", []),
        reproducibility={"engine": "NodalEngine", "engine_version": "V1"},
    )


def build_nodal_failure_case(
    inputs: Any,
    *,
    code: str,
    message: str,
    request: Any = None,
    pvt_context: Optional[Mapping[str, Any]] = None,
    pvt_mode: Optional[str] = None,
    pvt_model: Optional[str] = None,
) -> EngineeringCase:
    """Represent a typed Nodal failure without fabricating an operating result."""
    return build_nodal_case(
        inputs,
        {"error": {"code": str(code), "message": str(message)}},
        request=request,
        pvt_context=pvt_context,
        pvt_mode=pvt_mode,
        pvt_model=pvt_model,
        status=code,
    )


def build_system_case(
    inputs: Any,
    result: Any,
    *,
    request: Any = None,
    pvt_context: Optional[Mapping[str, Any]] = None,
    pvt_mode: Optional[str] = None,
    pvt_model: Optional[str] = None,
    status: Optional[str] = None,
    limitations: Any = None,
    warnings: Any = None,
) -> EngineeringCase:
    """Build an Increment 12 case from an already-computed engine result."""
    pvt: Dict[str, Any] = {}
    if pvt_mode is not None or pvt_model is not None or pvt_context is not None:
        pvt = {
            "mode": pvt_mode or "pressure_dependent",
            "model": pvt_model or "black_oil_v1",
            "context": {} if pvt_context is None else dict(pvt_context),
            "provenance": _plain(getattr(result, "pvt_metadata", {})),
        }
    model = {
        "ipr": getattr(result, "ipr_model", None),
        "vlp": getattr(result, "vlp_model", None),
        "choke": getattr(result, "choke_model", None),
        "solver": getattr(result, "solver_method", None),
    }
    selectors = {
        "ipr_model": getattr(inputs, "ipr_model", None),
        "vlp_model": getattr(inputs, "vlp_model", None),
        "choke_model": getattr(inputs, "choke_model", None),
    }
    units = {
        "pressure": "psia",
        "rate": "STB/day",
        "tubing_id": "in",
        "depth": "ft",
        "gor": "scf/STB",
        "viscosity": "cP",
        "temperature": "degF",
        "geothermal_gradient": "degF/100ft",
        "choke_size": "64ths of inch",
    }
    assumptions = {
        "system_engine": "IntegratedSystemEngine V1",
        "residual_tolerance_psi": getattr(inputs, "pressure_tol", None),
        "n_points": getattr(inputs, "n_points", None),
        "segments": getattr(inputs, "n_segments", None),
    }
    return build_case(
        calculation_type="integrated_system_v1",
        request={} if request is None else request,
        inputs=system_input_to_dict(inputs),
        units=units,
        selectors=selectors,
        model=model,
        pvt=pvt,
        assumptions=assumptions,
        result=result,
        status=status or getattr(result, "status", "OK"),
        limitations=limitations if limitations is not None else getattr(result, "limitations", []),
        warnings=warnings if warnings is not None else getattr(result, "warnings", []),
        reproducibility={"engine": "IntegratedSystemEngine", "engine_version": "V1"},
    )


def build_system_failure_case(
    inputs: Any,
    *,
    code: str,
    message: str,
    request: Any = None,
    pvt_context: Optional[Mapping[str, Any]] = None,
    pvt_mode: Optional[str] = None,
    pvt_model: Optional[str] = None,
) -> EngineeringCase:
    """Represent a typed system failure without fabricating a result."""
    return build_system_case(
        inputs,
        {"error": {"code": str(code), "message": str(message)}},
        request=request,
        pvt_context=pvt_context,
        pvt_mode=pvt_mode,
        pvt_model=pvt_model,
        status=code,
    )


def replay_matches(original: EngineeringCase, replayed: EngineeringCase) -> bool:
    """Compare deterministic calculation state, excluding identity metadata."""
    return (
        original.status == replayed.status
        and canonical_json(original.result) == canonical_json(replayed.result)
        and canonical_json(original.limitations) == canonical_json(replayed.limitations)
        and canonical_json(original.warnings) == canonical_json(replayed.warnings)
    )


__all__ = [
    "CaseReplayError",
    "EngineeringCase",
    "build_case",
    "build_case_id",
    "canonical_json",
    "replay_case",
    "replay_matches",
    "system_input_to_dict",
    "choke_input_to_dict",
    "build_choke_case",
    "build_choke_failure_case",
    "nodal_input_to_dict",
    "build_nodal_case",
    "build_nodal_failure_case",
    "build_system_case",
    "build_system_failure_case",
]
