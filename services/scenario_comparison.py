"""Deterministic Scenario & Comparison orchestration for released engines.

This module owns no petroleum equations. It evaluates a bounded, explicitly
ordered set of scenarios through the released System and Choke engines, wraps
each result in an EngineeringCase, and provides deterministic serialization and
replay for the comparison set.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
import re
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from services.choke_engine import ChokeEngine, ChokeError, ChokeInput
from services.engineering_case import (
    EngineeringCase,
    build_case_id,
    build_choke_case,
    build_choke_failure_case,
    build_system_case,
    build_system_failure_case,
    canonical_json,
    replay_case,
)
from services.system_engine import IntegratedSystemEngine, SystemError, SystemInput


COMPARISON_RELEASE = "scenario_comparison_v1"
MAX_SCENARIOS = 16
_LABEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,31}$")


class ComparisonError(ValueError):
    """Typed, user-safe failure for invalid comparison definitions."""

    def __init__(self, code: str, message: str):
        self.code = str(code)
        self.message = str(message)
        super().__init__(f"{self.code}: {self.message}")


class ComparisonInputError(ComparisonError):
    """Typed invalid-input failure raised by mapping adapters."""


@dataclass(frozen=True)
class ScenarioSpec:
    """One scenario definition before it is evaluated by a released engine."""

    label: str
    calculation_type: str
    inputs: Any
    request: Any = None
    pvt_provider: Any = None
    pvt_context: Optional[Mapping[str, Any]] = None
    pvt_mode: Optional[str] = None
    pvt_model: Optional[str] = None
    validation_error: Optional[Tuple[str, str]] = None


@dataclass(frozen=True)
class ScenarioOutcome:
    """One labeled scenario and its reproducible EngineeringCase."""

    label: str
    case: EngineeringCase

    def to_dict(self) -> Dict[str, Any]:
        return {"label": self.label, "case": self.case.to_dict()}


@dataclass(frozen=True)
class ScenarioComparison:
    """Immutable comparison envelope with a deterministic comparison ID."""

    comparison_id: str
    scenarios: Tuple[ScenarioOutcome, ...]
    request: Any = None
    release: str = COMPARISON_RELEASE

    @property
    def identity_payload(self) -> Dict[str, Any]:
        return {
            "comparison_type": "scenario_comparison",
            "release": self.release,
            "scenarios": [
                {
                    "label": item.label,
                    "case_identity": item.case.identity_payload,
                }
                for item in self.scenarios
            ],
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "comparison_id": self.comparison_id,
            "comparison_type": "scenario_comparison",
            "request": _plain(self.request if self.request is not None else {}),
            "release": self.release,
            "scenarios": [item.to_dict() for item in self.scenarios],
            "reproducibility": {
                "schema": "scenario_comparison_v1",
                "hash": "sha256",
                "canonical_json": "sorted_keys_stable_separators_normalized_numerics",
                "replayable": True,
            },
        }

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(), ensure_ascii=False, sort_keys=True,
            separators=(",", ":"), allow_nan=False,
        )


# ---------------------------------------------------------------------------
# Input adapters used by the Telegram orchestration surface
# ---------------------------------------------------------------------------

_SYSTEM_ALIASES = {
    "id": "tubing_id_in",
    "tubing_id": "tubing_id_in",
    "gor": "gor_scf_stb",
    "rs": "rs_scf_stb",
    "mu_l": "mu_l_cp",
    "bo": "bo_rb_stb",
    "t_wh": "t_wh_f",
    "geothermal": "geothermal_f_100ft",
    "choke": "choke_size_64th_in",
    "choke_size": "choke_size_64th_in",
    "p_down": "downstream_pressure_psia",
    "p_downstream": "downstream_pressure_psia",
    "thp_guess": "thp",
    "segments": "n_segments",
    "z": "z_factor",
}

_CHOKE_ALIASES = {
    "p_up": "upstream_pressure_psia",
    "upstream_pressure": "upstream_pressure_psia",
    "p_down": "downstream_pressure_psia",
    "downstream_pressure": "downstream_pressure_psia",
    "choke": "choke_size_64th_in",
    "choke_size": "choke_size_64th_in",
    "gor": "gor_scf_stb",
    "q_liquid": "liquid_rate_bpd",
    "liquid_rate": "liquid_rate_bpd",
    "model": "choke_model",
}


def _as_float(raw: Any, key: str) -> float:
    if isinstance(raw, bool):
        raise ComparisonInputError("INVALID_INPUT", f"{key} must be numeric.")
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise ComparisonInputError("INVALID_INPUT", f"{key} must be numeric.") from exc
    if not math.isfinite(value):
        raise ComparisonInputError("INVALID_INPUT", f"{key} must be finite.")
    return value


def _lookup(mapping: Mapping[str, Any], aliases: Sequence[str], default: Any = None) -> Any:
    for key in aliases:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return default


def _normalized(mapping: Mapping[str, Any], aliases: Mapping[str, str]) -> Dict[str, Any]:
    result = {str(key).lower(): value for key, value in mapping.items()}
    for old, new in aliases.items():
        if new not in result and old in result:
            result[new] = result[old]
    return result


def build_choke_input(mapping: Mapping[str, Any]) -> ChokeInput:
    """Build a released ChokeInput from Telegram-style aliases."""
    allowed = {
        "upstream_pressure_psia", "p_up", "upstream_pressure",
        "downstream_pressure_psia", "p_down", "downstream_pressure",
        "choke_size_64th_in", "choke", "choke_size", "gor_scf_stb", "gor",
        "liquid_rate_bpd", "q_liquid", "liquid_rate", "oil_api", "api",
        "gas_specific_gravity", "gamma_g", "choke_model", "model",
    }
    unknown = sorted(set(mapping) - allowed)
    if unknown:
        raise ComparisonInputError("INVALID_INPUT", "unsupported scenario key(s): " + ", ".join(unknown) + ".")
    data = _normalized(mapping, _CHOKE_ALIASES)
    required = {
        "upstream_pressure_psia": ("upstream_pressure_psia", "p_up"),
        "downstream_pressure_psia": ("downstream_pressure_psia", "p_down"),
        "choke_size_64th_in": ("choke_size_64th_in", "choke"),
        "gor_scf_stb": ("gor_scf_stb", "gor"),
    }
    missing = [name for name, aliases in required.items()
               if _lookup(data, aliases) is None]
    if missing:
        raise ComparisonInputError(
            "MISSING_DATA", "Scenario is missing: " + ", ".join(missing) + ".")
    values: Dict[str, Any] = {
        "upstream_pressure_psia": _as_float(data["upstream_pressure_psia"], "p_up"),
        "downstream_pressure_psia": _as_float(data["downstream_pressure_psia"], "p_down"),
        "choke_size_64th_in": _as_float(data["choke_size_64th_in"], "choke"),
        "gor_scf_stb": _as_float(data["gor_scf_stb"], "gor"),
    }
    for key, aliases in {
        "liquid_rate_bpd": ("liquid_rate_bpd", "q_liquid"),
        "oil_api": ("oil_api", "api"),
        "gas_specific_gravity": ("gas_specific_gravity", "gamma_g"),
    }.items():
        value = _lookup(data, aliases)
        if value is not None:
            values[key] = _as_float(value, key)
    values["choke_model"] = str(data.get("choke_model", "gilbert_1954"))
    return ChokeInput(**values)


def build_system_input(mapping: Mapping[str, Any]) -> SystemInput:
    """Build a released SystemInput from Telegram-style aliases."""
    allowed = {
        "pr", "thp", "thp_guess", "tvd", "id", "tubing_id", "tubing_id_in",
        "gor", "gor_scf_stb", "rs", "rs_scf_stb", "api", "gamma_g", "mu_l",
        "mu_l_cp", "bo", "bo_rb_stb", "t_wh", "t_wh_f", "geothermal",
        "geothermal_f_100ft", "choke", "choke_size", "choke_size_64th_in",
        "p_down", "p_downstream", "downstream_pressure_psia", "choke_model",
        "model", "ipr_model", "vlp_model", "pb", "j", "j_star", "qmax",
        "q_test", "pwf_test", "wc", "gamma_w", "bw", "z", "z_factor",
        "sigma", "segments", "n_segments", "q_min", "q_max", "n_points",
        "pressure_tol", "max_refine_iter",
    }
    unknown = sorted(set(mapping) - allowed)
    if unknown:
        raise ComparisonInputError("INVALID_INPUT", "unsupported scenario key(s): " + ", ".join(unknown) + ".")
    data = _normalized(mapping, _SYSTEM_ALIASES)
    required = {
        "pr": ("pr",), "tvd": ("tvd",), "tubing_id_in": ("tubing_id_in",),
        "gor_scf_stb": ("gor_scf_stb",), "rs_scf_stb": ("rs_scf_stb",),
        "api": ("api",), "gamma_g": ("gamma_g",), "mu_l_cp": ("mu_l_cp",),
        "bo_rb_stb": ("bo_rb_stb",), "t_wh_f": ("t_wh_f",),
        "geothermal_f_100ft": ("geothermal_f_100ft",),
        "choke_size_64th_in": ("choke_size_64th_in",),
        "downstream_pressure_psia": ("downstream_pressure_psia",),
    }
    missing = [name for name, aliases in required.items()
               if _lookup(data, aliases) is None]
    model = str(data.get("model", data.get("ipr_model", "auto"))).lower()
    if model == "linear" and data.get("j") is None and (data.get("q_test") is None or data.get("pwf_test") is None):
        missing.append("j or q_test plus pwf_test")
    elif model == "vogel" and data.get("qmax") is None and (data.get("q_test") is None or data.get("pwf_test") is None):
        missing.append("qmax or q_test plus pwf_test")
    elif model == "composite":
        if data.get("pb") is None:
            missing.append("pb")
        if data.get("j_star", data.get("j")) is None and (data.get("q_test") is None or data.get("pwf_test") is None):
            missing.append("j or q_test plus pwf_test")
    elif model == "auto" and data.get("j") is None and data.get("qmax") is None and (data.get("q_test") is None or data.get("pwf_test") is None):
        missing.append("j or qmax or q_test plus pwf_test")
    if missing:
        raise ComparisonInputError(
            "MISSING_DATA", "Scenario is missing: " + ", ".join(missing) + ".")

    def num(key: str, default: Any = None) -> Any:
        value = data.get(key, default)
        return default if value is None else _as_float(value, key)

    def integer(key: str, default: int) -> int:
        value = data.get(key, default)
        try:
            result = int(value)
        except (TypeError, ValueError) as exc:
            raise ComparisonInputError("INVALID_INPUT", f"{key} must be an integer.") from exc
        return result

    return SystemInput(
        pr=num("pr"), thp=num("thp", 100.0), tvd=num("tvd"),
        tubing_id_in=num("tubing_id_in"), gor_scf_stb=num("gor_scf_stb"),
        rs_scf_stb=num("rs_scf_stb"), api=num("api"), gamma_g=num("gamma_g"),
        mu_l_cp=num("mu_l_cp"), bo_rb_stb=num("bo_rb_stb"), t_wh_f=num("t_wh_f"),
        geothermal_f_100ft=num("geothermal_f_100ft"),
        choke_size_64th_in=num("choke_size_64th_in"),
        downstream_pressure_psia=num("downstream_pressure_psia"),
        choke_model=str(data.get("choke_model", "gilbert_1954")),
        ipr_model=model, vlp_model=str(data.get("vlp_model", "beggs_brill")),
        pb=num("pb") if data.get("pb") is not None else None,
        j=num("j") if data.get("j") is not None else None,
        j_star=num("j_star") if data.get("j_star") is not None else None,
        qmax=num("qmax") if data.get("qmax") is not None else None,
        q_test=num("q_test") if data.get("q_test") is not None else None,
        pwf_test=num("pwf_test") if data.get("pwf_test") is not None else None,
        wc=num("wc", 0.0), gamma_w=num("gamma_w", 1.07), bw=num("bw", 1.01),
        z_factor=num("z_factor", 0.9), sigma=num("sigma", 30.0),
        n_segments=integer("n_segments", 80), q_min=num("q_min", 1.0),
        q_max=num("q_max") if data.get("q_max") is not None else None,
        n_points=integer("n_points", 41), pressure_tol=num("pressure_tol", 0.1),
        max_refine_iter=integer("max_refine_iter", 60),
    )


def _plain(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_plain(item) for item in value]
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return _plain(value.to_dict())
    if hasattr(value, "__dataclass_fields__"):
        return _plain(asdict(value))
    return str(value)


def _validate_spec(spec: ScenarioSpec) -> None:
    if spec.validation_error is not None:
        code, message = spec.validation_error
        raise ComparisonError(code, message)
    label = str(spec.label).strip()
    if not _LABEL_RE.fullmatch(label):
        raise ComparisonError(
            "INVALID_INPUT",
            "Scenario labels must be unique and use 1-32 letters, numbers, '.', '_' or '-'.",
        )
    kind = str(spec.calculation_type).strip().lower()
    if kind not in {"system", "integrated_system_v1", "choke", "choke_v1"}:
        raise ComparisonError(
            "UNSUPPORTED_CALCULATION",
            "Comparison supports only calculation_type=system or choke.",
        )
    pvt_values = (spec.pvt_provider, spec.pvt_context, spec.pvt_mode, spec.pvt_model)
    if all(value is None for value in pvt_values):
        return
    mode = str(spec.pvt_mode or "").strip().lower()
    model = str(spec.pvt_model or "").strip().lower()
    if mode != "pressure_dependent" or model != "black_oil_v1":
        raise ComparisonError(
            "UNSUPPORTED_PVT_SELECTOR",
            "explicit Black-Oil scenario requires pressure_dependent/black_oil_v1.",
        )
    if spec.pvt_provider is None or not callable(getattr(spec.pvt_provider, "evaluate", None)):
        raise ComparisonError(
            "INVALID_INPUT", "pressure-dependent scenario requires an explicit PVT provider."
        )
    if not isinstance(spec.pvt_context, Mapping):
        raise ComparisonError(
            "PHYSICALLY_INVALID_STATE", "pressure-dependent scenario requires explicit PVT context."
        )


def _failure_case(spec: ScenarioSpec, code: str, message: str) -> EngineeringCase:
    kind = str(spec.calculation_type).strip().lower()
    if kind in {"choke", "choke_v1"}:
        return build_choke_failure_case(
            spec.inputs, code=code, message=message, request=spec.request,
            pvt_context=spec.pvt_context, pvt_mode=spec.pvt_mode,
            pvt_model=spec.pvt_model,
        )
    if kind in {"system", "integrated_system_v1"}:
        return build_system_failure_case(
            spec.inputs, code=code, message=message, request=spec.request,
            pvt_context=spec.pvt_context, pvt_mode=spec.pvt_mode,
            pvt_model=spec.pvt_model,
        )
    raise ComparisonError(code, message)


def _evaluate_one(spec: ScenarioSpec) -> EngineeringCase:
    try:
        _validate_spec(spec)
    except ComparisonError as exc:
        return _failure_case(spec, exc.code, exc.message)

    kind = str(spec.calculation_type).strip().lower()
    try:
        if kind in {"choke", "choke_v1"}:
            result = ChokeEngine().calculate(
                spec.inputs,
                pvt_provider=spec.pvt_provider,
                pvt_context=None if spec.pvt_context is None else dict(spec.pvt_context),
            )
            if spec.pvt_provider is not None:
                result.pvt_metadata["mode_selector"] = str(spec.pvt_mode)
                result.pvt_metadata["model_selector"] = str(spec.pvt_model)
            return build_choke_case(
                spec.inputs, result, request=spec.request,
                pvt_context=spec.pvt_context, pvt_mode=spec.pvt_mode,
                pvt_model=spec.pvt_model,
            )

        result = IntegratedSystemEngine().calculate(
            spec.inputs,
            pvt_provider=spec.pvt_provider,
            pvt_context=None if spec.pvt_context is None else dict(spec.pvt_context),
        )
        if spec.pvt_provider is not None:
            result.pvt_metadata["mode"] = str(spec.pvt_mode)
            result.pvt_metadata["model"] = str(spec.pvt_model)
        return build_system_case(
            spec.inputs, result, request=spec.request,
            pvt_context=spec.pvt_context, pvt_mode=spec.pvt_mode,
            pvt_model=spec.pvt_model,
        )
    except ChokeError as exc:
        return _failure_case(spec, exc.code, exc.message)
    except SystemError as exc:
        return _failure_case(spec, exc.code, exc.message)
    except (TypeError, ValueError) as exc:
        return _failure_case(spec, "INVALID_INPUT", str(exc))


def _assemble(outcomes: Sequence[ScenarioOutcome], request: Any = None,
              comparison_id: Optional[str] = None) -> ScenarioComparison:
    if comparison_id is None:
        seed = {
            "comparison_type": "scenario_comparison",
            "release": COMPARISON_RELEASE,
            "scenarios": [
                {"label": outcome.label, "case_identity": outcome.case.identity_payload}
                for outcome in outcomes
            ],
        }
        comparison_id = build_case_id(seed)
    return ScenarioComparison(
        comparison_id=comparison_id,
        scenarios=tuple(outcomes),
        request={} if request is None else request,
    )


def evaluate_comparison(scenarios: Sequence[ScenarioSpec], *, request: Any = None) -> ScenarioComparison:
    """Evaluate an ordered, bounded scenario set independently."""
    if not isinstance(scenarios, Sequence) or isinstance(scenarios, (str, bytes)):
        raise ComparisonError("INVALID_INPUT", "scenarios must be an ordered sequence.")
    if len(scenarios) < 2:
        raise ComparisonError("MISSING_DATA", "comparison requires at least two scenarios.")
    if len(scenarios) > MAX_SCENARIOS:
        raise ComparisonError("INVALID_INPUT", f"comparison supports at most {MAX_SCENARIOS} scenarios.")
    labels = [str(spec.label).strip() for spec in scenarios]
    if len(set(labels)) != len(labels):
        raise ComparisonError("INVALID_INPUT", "scenario labels must be unique.")
    outcomes = [ScenarioOutcome(label=label, case=_evaluate_one(spec))
                for label, spec in zip(labels, scenarios)]
    return _assemble(outcomes, request=request)


def replay_comparison(comparison: ScenarioComparison) -> ScenarioComparison:
    """Replay every scenario through the original EngineeringCase dispatcher."""
    if not isinstance(comparison, ScenarioComparison):
        raise TypeError("replay_comparison requires a ScenarioComparison")
    replayed = tuple(
        ScenarioOutcome(label=item.label, case=replay_case(item.case))
        for item in comparison.scenarios
    )
    return _assemble(replayed, request=comparison.request,
                     comparison_id=comparison.comparison_id)


def comparison_replay_matches(original: ScenarioComparison,
                              replayed: ScenarioComparison) -> bool:
    """Compare deterministic scenario state, excluding no engineering data."""
    if original.comparison_id != replayed.comparison_id:
        return False
    if [item.label for item in original.scenarios] != [item.label for item in replayed.scenarios]:
        return False
    for left, right in zip(original.scenarios, replayed.scenarios):
        if left.case.case_id != right.case.case_id:
            return False
        if left.case.status != right.case.status:
            return False
        if canonical_json(left.case.result) != canonical_json(right.case.result):
            return False
        if canonical_json(left.case.limitations) != canonical_json(right.case.limitations):
            return False
        if canonical_json(left.case.warnings) != canonical_json(right.case.warnings):
            return False
    return True


def _metric_line(outcome: ScenarioOutcome) -> str:
    case = outcome.case
    result = case.result if isinstance(case.result, Mapping) else {}
    if case.status != "OK" and "error" in result:
        error = result.get("error", {})
        return f"{outcome.label}: {case.status} — {error.get('message', 'typed engineering failure')}"
    if case.calculation_type in {"choke", "choke_v1"}:
        return (
            f"{outcome.label}: status={case.status}, "
            f"q={result.get('calculated_rate_bpd', 'n/a')} bbl/day, "
            f"regime={result.get('flow_regime', 'n/a')}"
        )
    return (
        f"{outcome.label}: status={case.status}, "
        f"q_op={result.get('operating_rate_bpd', 'n/a')} STB/day, "
        f"Pwf={result.get('pwf_psia', 'n/a')} psia, "
        f"Pwh={result.get('wellhead_pressure_psia', 'n/a')} psia"
    )


def format_comparison(comparison: ScenarioComparison) -> str:
    """Create concise Telegram-safe side-by-side output."""
    lines = [
        "Scenario Comparison V1",
        "=======================",
        "Deterministic side-by-side evaluation of the supplied scenarios.",
        "",
        f"Comparison ID: {comparison.comparison_id}",
        f"Scenario count: {len(comparison.scenarios)}",
        "",
        "SCENARIOS",
    ]
    lines.extend(f" • {_metric_line(item)}" for item in comparison.scenarios)
    lines.extend([
        "",
        "Engineering honesty: results are model calculations, not measured field data, production forecasts, or operating instructions.",
    ])
    return "\n".join(lines)


def generate_comparison_report_v1(comparison: ScenarioComparison) -> str:
    """Render a traceable comparison report without adding recommendations."""
    lines = [
        "# Scenario Comparison Report V1",
        "",
        "> Model-based deterministic engineering calculation; not measured field data, a production forecast, an autonomous optimization, or an operating instruction.",
        "",
        "## Comparison Identity",
        "",
        f"- Comparison ID: `{comparison.comparison_id}`",
        f"- Scenario count: `{len(comparison.scenarios)}`",
        f"- Release: `{comparison.release}`",
        "",
        "## Side-by-Side Results",
        "",
        "| Scenario | Calculation | Status | Primary result | Case ID |",
        "|---|---|---|---|---|",
    ]
    for item in comparison.scenarios:
        result = item.case.result if isinstance(item.case.result, Mapping) else {}
        if item.case.calculation_type in {"choke", "choke_v1"}:
            primary = f"q={result.get('calculated_rate_bpd', 'n/a')} bbl/day"
        else:
            primary = f"q_op={result.get('operating_rate_bpd', 'n/a')} STB/day; Pwf={result.get('pwf_psia', 'n/a')} psia"
        lines.append(
            f"| `{item.label}` | `{item.case.calculation_type}` | `{item.case.status}` | {primary} | `{item.case.case_id}` |"
        )
    lines.extend(["", "## Scenario Details", ""])
    for item in comparison.scenarios:
        case = item.case
        lines.extend([
            f"### `{item.label}`",
            "",
            f"- Engineering Case ID: `{case.case_id}`",
            f"- Status: `{case.status}`",
            f"- Model: `{json.dumps(case.model, ensure_ascii=False, sort_keys=True)}`",
            f"- Selectors: `{json.dumps(case.selectors, ensure_ascii=False, sort_keys=True)}`",
            f"- PVT: `{json.dumps(case.pvt, ensure_ascii=False, sort_keys=True)}`",
            "",
            "Result",
            "```json",
            json.dumps(case.result, ensure_ascii=False, sort_keys=True, indent=2),
            "```",
        ])
        if case.limitations:
            lines.extend(["", "Limitations", "", *[f"- {value}" for value in case.limitations]])
        if case.warnings:
            lines.extend(["", "Warnings", "", *[f"- {value}" for value in case.warnings]])
        lines.append("")
    lines.extend([
        "## Reproducibility",
        "",
        "This comparison preserves scenario order, model selectors, inputs, PVT provenance, typed status, limitations, warnings, and the Engineering Case ID for each scenario. It can be replayed through the released engine dispatcher.",
    ])
    return "\n".join(lines)


__all__ = [
    "COMPARISON_RELEASE",
    "MAX_SCENARIOS",
    "ComparisonError",
    "ComparisonInputError",
    "ScenarioSpec",
    "ScenarioOutcome",
    "ScenarioComparison",
    "build_choke_input",
    "build_system_input",
    "evaluate_comparison",
    "replay_comparison",
    "comparison_replay_matches",
    "format_comparison",
    "generate_comparison_report_v1",
]
