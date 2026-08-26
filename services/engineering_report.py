"""Human-readable deterministic engineering reports.

The EngineeringCase object remains the canonical source of truth.  This module
only translates its secret-free fields into petroleum-engineering prose; it
never performs a calculation and never exposes the machine serialization used
for deterministic identity or replay.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from services.engineering_case import EngineeringCase
from services.engineering_context import EngineeringValueOrigin, input_origins_for_case
from services.engineering_language import (
    arabic_calculation_title,
    arabic_label,
    arabic_status,
)


_REPORT_NOTE = (
    "Model-based deterministic engineering calculation; not measured field data, "
    "a production forecast, an autonomous optimization, or an operating instruction."
)

_REPORT_SUCCESS_STATUSES = frozenset({
    "OK",
    "CONVERGED",
    "UNIQUE_OPERATING_POINT",
})

_INTERNAL_KEYS = frozenset({
    "canonical_json",
    "engine_version",
    "schema",
    "pvt_context",
    "provider",
    "pvt_provider",
    "request",
    "release",
    "provenance",
    "z_factor_provenance",
    "source_versions",
})

_KEY_LABELS = {
    "pr": "Reservoir pressure",
    "thp": "Tubing-head pressure (THP)",
    "tvd": "True vertical depth",
    "id": "Tubing inside diameter",
    "tubing_id_in": "Tubing inside diameter",
    "gor": "Gas–oil ratio (GOR)",
    "gor_scf_stb": "Gas–oil ratio (GOR)",
    "rs": "Solution gas–oil ratio",
    "rs_scf_stb": "Solution gas–oil ratio",
    "api": "Oil gravity",
    "gamma_g": "Gas specific gravity",
    "gamma_w": "Water specific gravity",
    "mu_l": "Liquid viscosity",
    "mu_l_cp": "Liquid viscosity",
    "bo": "Oil formation-volume factor",
    "bo_rb_stb": "Oil formation-volume factor",
    "bw": "Water formation-volume factor",
    "wc": "Water cut",
    "water_cut": "Water cut",
    "j": "Productivity index",
    "q_op": "Operating production rate",
    "operating_rate_bpd": "Operating liquid rate",
    "operating_rate_stbd": "Operating production rate",
    "calculated_rate_bpd": "Calculated liquid rate",
    "pwf_op": "Flowing bottomhole pressure",
    "pwf_psia": "Flowing bottomhole pressure",
    "bottomhole_pressure_psia": "Bottomhole pressure",
    "pwf": "Flowing bottomhole pressure",
    "rate": "Production rate",
    "predicted_oil_rate_stbd": "Predicted oil production rate",
    "bottomhole_pressure_without_lift_psia": "Bottomhole pressure without gas lift",
    "bottomhole_pressure_with_lift_psia": "Bottomhole pressure with gas lift",
    "wellhead_pressure_psia": "Wellhead pressure",
    "upstream_pressure_psia": "Upstream pressure",
    "downstream_pressure_psia": "Downstream pressure",
    "pressure_ratio": "Pressure ratio",
    "residual": "Pressure residual",
    "solver_residual_psi": "Solver pressure residual",
    "pressure_residual_psi": "Solver pressure residual",
    "choke_size_64th_in": "Choke size",
    "liquid_rate_bpd": "Supplied liquid rate",
    "gas_injection_rate_mscfd": "Gas injection rate",
    "injection_pressure_psia": "Injection pressure",
    "reservoir_pressure_psia": "Reservoir pressure",
    "productivity_index_stbd_psi": "Productivity index",
    "average_temperature_f": "Average temperature",
    "injection_depth_ft": "Injection depth",
    "tubing_gradient_psi_ft": "Tubing pressure gradient",
    "t_wh": "Wellhead temperature",
    "t_wh_f": "Wellhead temperature",
    "geothermal": "Geothermal gradient",
    "geothermal_f_100ft": "Geothermal gradient",
    "sigma": "Surface tension",
    "q_min": "Minimum production rate",
    "q_max": "Maximum production rate",
    "tol": "Pressure tolerance",
    "pressure_tol": "Pressure tolerance",
    "max_refine_iter": "Maximum refinement iterations",
    "objective": "Optimization target",
    "variable": "Evaluated variable",
    "parameter_value": "Parameter value",
    "classification": "Engineering classification",
    "flow_regime": "Flow regime",
    "status": "Engineering status",
    "reason": "Engineering interpretation",
    "solver_iterations": "Solver iterations",
    "solver_method": "Solver method",
    "n_points": "Number of evaluated points",
    "segments": "Tubing segments",
    "n_segments": "Tubing segments",
    "vlp_model": "Outflow model",
    "ipr_model": "Inflow model",
    "choke_model": "Choke correlation",
}

_UNIT_BY_KEY = {
    "pr": "psia",
    "thp": "psia",
    "tvd": "ft",
    "id": "in",
    "tubing_id_in": "in",
    "gor": "scf/STB",
    "gor_scf_stb": "scf/STB",
    "rs": "scf/STB",
    "rs_scf_stb": "scf/STB",
    "api": "deg API",
    "gamma_g": "specific gravity",
    "gamma_w": "specific gravity",
    "mu_l": "cP",
    "mu_l_cp": "cP",
    "bo": "rb/STB",
    "bo_rb_stb": "rb/STB",
    "bw": "rb/STB",
    "wc": "fraction",
    "water_cut": "fraction",
    "j": "STB/day/psi",
    "q_op": "STB/day",
    "operating_rate_bpd": "bbl/day",
    "operating_rate_stbd": "STB/day",
    "calculated_rate_bpd": "bbl/day",
    "pwf_op": "psia",
    "pwf_psia": "psia",
    "bottomhole_pressure_psia": "psia",
    "pwf": "psia",
    "rate": "STB/day",
    "predicted_oil_rate_stbd": "STB/day",
    "bottomhole_pressure_without_lift_psia": "psia",
    "bottomhole_pressure_with_lift_psia": "psia",
    "wellhead_pressure_psia": "psia",
    "upstream_pressure_psia": "psia",
    "downstream_pressure_psia": "psia",
    "residual": "psi",
    "solver_residual_psi": "psi",
    "pressure_residual_psi": "psi",
    "choke_size_64th_in": "64ths of an inch",
    "liquid_rate_bpd": "bbl/day",
    "gas_injection_rate_mscfd": "Mscf/day",
    "injection_pressure_psia": "psia",
    "reservoir_pressure_psia": "psia",
    "productivity_index_stbd_psi": "STB/day/psi",
    "average_temperature_f": "degF",
    "injection_depth_ft": "ft",
    "tubing_gradient_psi_ft": "psi/ft",
    "t_wh": "degF",
    "t_wh_f": "degF",
    "geothermal": "degF/100ft",
    "geothermal_f_100ft": "degF/100ft",
    "solver_iterations": "iterations",
    "n_points": "points",
    "segments": "segments",
    "n_segments": "segments",
}


def _safe_text(value: Any) -> str:
    """Return text that cannot recreate a JSON-looking object in the report."""
    return (
        str(value)
        .replace("{", "(")
        .replace("}", ")")
        .replace("BlackOilPvtProvider", "Pressure-dependent Black-Oil PVT")
        .replace("black_oil_v1", "Pressure-dependent Black-Oil PVT")
        .replace("pressure_dependent", "pressure-dependent")
        .replace("gilbert_1954", "Gilbert correlation")
        .replace("beggs_brill", "Beggs–Brill")
        .replace("phase5c_increment13_case_report_v1", "released engineering report")
    )


def _number(value: Any) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float):
        if value.is_integer():
            return f"{value:,.0f}"
        return f"{value:,.6g}"
    return _safe_text(value)


def _label(key: Any) -> str:
    text = str(key)
    if text in _KEY_LABELS:
        return _KEY_LABELS[text]
    words = text.replace("_", " ").strip()
    return words[:1].upper() + words[1:] if words else "Value"


def _unit(key: Any, units: Mapping[str, Any] | None = None) -> str:
    text = str(key)
    if text in _UNIT_BY_KEY:
        return _UNIT_BY_KEY[text]
    if units:
        for unit_key, unit_value in units.items():
            if text == unit_key or text.endswith("_" + str(unit_key)):
                return _safe_text(unit_value)
    return ""


def _origin_tag(origin: Any) -> str:
    """Render a deterministic input-origin tag without exposing internal JSON."""
    value = getattr(origin, "value", str(origin or "UNKNOWN")).upper()
    return value if value in {item.value for item in EngineeringValueOrigin} else "UNKNOWN"


def _origin_suffix(origin: Any) -> str:
    return f" [origin: {_origin_tag(origin)}]"


def _value_text(key: Any, value: Any, units: Mapping[str, Any] | None = None) -> str:
    if value is None:
        return "not supplied"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (int, float)):
        rendered = _number(value)
        unit = _unit(key, units)
        return f"{rendered} {unit}".strip()
    if isinstance(value, str):
        return _safe_text(value)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return ", ".join(_value_text(key, item, units) for item in value)
    return _safe_text(value)


def _append_mapping_lines(
    lines: list[str], data: Mapping[str, Any], *, units: Mapping[str, Any] | None = None,
    indent: str = "", skip: frozenset[str] = _INTERNAL_KEYS,
    origins: Mapping[str, Any] | None = None,
) -> None:
    for key, value in data.items():
        key_text = str(key)
        if key_text in skip:
            continue
        if value is None:
            continue
        if isinstance(value, Mapping):
            lines.append(f"{indent}{_label(key_text)}:")
            _append_mapping_lines(lines, value, units=units, indent=indent + "  ", skip=skip)
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            if value and all(not isinstance(item, (Mapping, Sequence)) for item in value):
                lines.append(f"{indent}{_label(key_text)}: {_value_text(key_text, value, units)}")
            else:
                lines.append(f"{indent}{_label(key_text)}:")
                for item in value:
                    if isinstance(item, Mapping):
                        _append_mapping_lines(lines, item, units=units, indent=indent + "  ", skip=skip)
                    else:
                        lines.append(f"{indent}  {_value_text(key_text, item, units)}")
        else:
            suffix = _origin_suffix(origins.get(key_text)) if origins and key_text in origins else ""
            lines.append(f"{indent}{_label(key_text)}: {_value_text(key_text, value, units)}{suffix}")


def _calculation_title(calculation_type: str) -> str:
    titles = {
        "system_v1": "Integrated Well and Choke System",
        "choke_v1": "Choke Performance",
        "nodal_v1": "Nodal Analysis",
        "vlp_v1": "Vertical Lift Performance",
        "gas_lift_v1": "Continuous Gas-Lift Performance",
        "sensitivity_v1": "Sensitivity Analysis",
        "optimize_v1": "Production Optimization",
    }
    return titles.get(calculation_type, "Engineering Calculation")


def _variable_display(value: Any) -> str:
    names = {
        "thp": "THP",
        "tubing_id": "tubing inside diameter",
        "wc": "water cut",
        "water_cut": "water cut",
        "gor": "GOR",
    }
    return names.get(str(value).lower(), _label(value))


def _status_line(case: EngineeringCase) -> str:
    status = _safe_text(case.status)
    if status in _REPORT_SUCCESS_STATUSES:
        return "Engineering status: calculation completed successfully."
    return f"Engineering status: {status}."


def _pvt_lines(pvt: Any) -> list[str]:
    if not isinstance(pvt, Mapping) or not pvt:
        return [
            "PVT description: The calculation used the selected conventional property inputs; a pressure-dependent Black-Oil evaluation was not requested."
        ]

    mode = str(pvt.get("mode", "")).lower()
    model = str(pvt.get("model", "")).lower()
    provenance = pvt.get("provenance")
    if mode == "pressure_dependent" or model == "black_oil_v1" or (
        isinstance(provenance, Mapping) and provenance.get("enabled")
    ):
        metadata = provenance if isinstance(provenance, Mapping) else {}
        pressure_range = metadata.get("pressure_range_psia")
        if not pressure_range:
            pressure_range = metadata.get("pressure_ranges")
        if isinstance(pressure_range, Sequence) and not isinstance(pressure_range, (str, bytes, bytearray)):
            flat: list[float] = []
            for item in pressure_range:
                if isinstance(item, Sequence) and not isinstance(item, (str, bytes, bytearray)):
                    flat.extend(float(x) for x in item if isinstance(x, (int, float)))
                elif isinstance(item, (int, float)):
                    flat.append(float(item))
            pressure_range = flat
        lines = [
            "PVT description: Pressure-dependent Black-Oil PVT.",
        ]
        if isinstance(pressure_range, Sequence) and len(pressure_range) >= 2:
            lines.append(
                "The evaluated pressure range was "
                f"{_number(float(pressure_range[0]))} to {_number(float(pressure_range[-1]))} psia."
            )
        else:
            context = pvt.get("context") if isinstance(pvt.get("context"), Mapping) else {}
            pressure = context.get("pressure_psia")
            if pressure is not None:
                lines.append(f"The evaluated pressure range was {_number(pressure)} psia at the supplied state.")
            else:
                lines.append("The pressure range was recorded in the engineering case for replay.")
        phase_regions = metadata.get("phase_regions")
        if phase_regions:
            lines.append(f"Phase region identified: {_value_text('phase_region', phase_regions)}.")
        if metadata.get("pb_crossed") is not None:
            lines.append(f"Bubble-point crossing during evaluation: {_value_text('pb_crossed', metadata.get('pb_crossed'))}.")
        evaluations = metadata.get("pvt_evaluations")
        if evaluations:
            lines.append(f"Pressure-property evaluations: {_number(evaluations)} states.")
        return lines

    return ["PVT description: The selected conventional property inputs were used."]


def _result_error(case: EngineeringCase) -> tuple[str, str] | None:
    if case.status in _REPORT_SUCCESS_STATUSES and not (
        isinstance(case.result, Mapping) and "error" in case.result
    ):
        return None
    payload = case.result.get("error") if isinstance(case.result, Mapping) else case.result
    if isinstance(payload, Mapping):
        code = payload.get("code", case.status)
        message = payload.get("message", "The engineering engine returned no further detail.")
    else:
        code = case.status
        message = payload or "The engineering engine returned no further detail."
    return _safe_text(code), _safe_text(message)


def _nodal_point_lines(
    lines: list[str],
    point: Mapping[str, Any],
    prefix: str = "",
    *,
    include_classification: bool = True,
) -> None:
    if not isinstance(point, Mapping):
        return
    parameter = point.get("parameter_value")
    if parameter is not None:
        lines.append(f"{prefix}Parameter value: {_value_text('parameter_value', parameter)}")
    q = point.get("q_op", point.get("q"))
    pwf = point.get("pwf_op", point.get("pwf"))
    if q is not None:
        lines.append(f"{prefix}Production rate: {_value_text('q_op', q)}")
    if pwf is not None:
        lines.append(f"{prefix}Flowing bottomhole pressure: {_value_text('pwf_op', pwf)}")
    if point.get("residual") is not None:
        lines.append(f"{prefix}Pressure residual: {_value_text('residual', point['residual'])}")
    if include_classification and point.get("classification"):
        lines.append(f"{prefix}Engineering classification: {_safe_text(point['classification'])}")
    if point.get("solve_error"):
        lines.append(f"{prefix}Calculation note: {_safe_text(point['solve_error'])}")


def _sensitivity_result(result: Mapping[str, Any], units: Mapping[str, Any]) -> list[str]:
    variable = _variable_display(result.get("variable", "parameter"))
    lines = [
        "## Sensitivity Analysis",
        "",
        f"This analysis evaluates how the selected well response changes with {variable}.",
        "Each operating point is a calculated model result from the supplied IPR and VLP inputs.",
        "",
    ]
    base_point = result.get("base_point")
    if isinstance(base_point, Mapping):
        lines.append("Operating point — base case")
        _nodal_point_lines(lines, base_point, prefix="  ")
        lines.append("")
    points = result.get("points") or []
    if points:
        lines.append(f"Evaluated {variable} cases")
        for point in points:
            if isinstance(point, Mapping):
                value = point.get("parameter_value")
                lines.append(f"  {variable}: {_value_text('parameter_value', value, units)}")
                _nodal_point_lines(lines, point, prefix="    ")
        lines.append("")
    sweep = result.get("sweep")
    if sweep and not points:
        lines.append(f"Evaluated {variable} values: {_value_text('parameter_value', sweep, units)}")
        lines.append("")
    return lines


def _optimize_result(result: Mapping[str, Any], units: Mapping[str, Any]) -> list[str]:
    variable = _variable_display(result.get("variable", "parameter"))
    objective = str(result.get("objective", "the selected production target"))
    objective_text = {
        "max_oil_rate": "maximize oil production rate",
    }.get(objective, objective.replace("_", " "))
    lines = [
        "## Production Optimization",
        "",
        f"The calculation compares supplied {variable} candidates to {objective_text}.",
        "This is a calculated model result within the supplied constraints, not an operating instruction.",
        "",
    ]
    base = result.get("base_candidate")
    if isinstance(base, Mapping):
        lines.append("Base operating point")
        _nodal_point_lines(lines, base.get("point", base), prefix="  ")
        lines.append("")
    candidates = result.get("candidates") or []
    if candidates:
        lines.append("Candidate evaluation")
        for candidate in candidates:
            if not isinstance(candidate, Mapping):
                continue
            value = candidate.get("parameter_value")
            classification = candidate.get("classification")
            lines.append(f"  {variable}: {_value_text('parameter_value', value, units)}")
            if classification:
                lines.append(f"    Engineering classification: {_safe_text(classification)}")
            _nodal_point_lines(
                lines,
                candidate.get("point", {}),
                prefix="    ",
                include_classification=False,
            )
            violations = candidate.get("constraint_violations") or []
            for violation in violations:
                if isinstance(violation, Mapping):
                    constraint = _label(violation.get("constraint", "constraint"))
                    limit = _value_text(violation.get("constraint", "constraint"), violation.get("limit"), units)
                    actual = _value_text(violation.get("constraint", "constraint"), violation.get("actual"), units)
                    lines.append(f"    Constraint note: {constraint}; limit {limit}, calculated value {actual}.")
        lines.append("")
    best = result.get("best")
    if isinstance(best, Mapping):
        lines.append("Best feasible candidate within the supplied model")
        lines.append(f"  {variable}: {_value_text('parameter_value', best.get('parameter_value'), units)}")
        _nodal_point_lines(lines, best.get("point", best), prefix="  ")
        lines.append("")
    elif result.get("all_infeasible"):
        lines.append("No feasible candidate was found within the supplied constraints.")
        lines.append("")
    return lines


def _generic_result(result: Any, units: Mapping[str, Any]) -> list[str]:
    lines: list[str] = []
    if isinstance(result, Mapping):
        # Keep the common operating metrics prominent before the remaining
        # typed details.  The details are rendered as labels, never as a map.
        for key in (
            "operating_rate_bpd", "calculated_rate_bpd", "operating_rate_stbd",
            "q_op", "pwf_op", "wellhead_pressure_psia", "bottomhole_pressure_psia",
            "bottomhole_pressure_without_lift_psia", "bottomhole_pressure_with_lift_psia",
            "pressure_residual_psi", "residual", "flow_regime", "classification",
        ):
            if key in result and result[key] is not None:
                lines.append(f"{_label(key)}: {_value_text(key, result[key], units)}")
        remaining = {
            key: value for key, value in result.items()
            if key not in _INTERNAL_KEYS and key not in {
                "operating_rate_bpd", "calculated_rate_bpd", "operating_rate_stbd",
                "q_op", "pwf_op", "wellhead_pressure_psia", "bottomhole_pressure_psia",
                "bottomhole_pressure_without_lift_psia", "bottomhole_pressure_with_lift_psia",
                "pressure_residual_psi", "residual", "flow_regime", "classification",
                "warnings", "limitations", "pvt_metadata", "provenance",
                "choke_result", "vlp_result",
            }
        }
        if remaining:
            _append_mapping_lines(lines, remaining, units=units)
    elif result:
        lines.append(_safe_text(result))
    return lines


def _case_inputs(case: EngineeringCase) -> list[str]:
    lines: list[str] = []
    if isinstance(case.inputs, Mapping) and case.inputs:
        origins = input_origins_for_case(case)
        lines.append(
            "Input origin labels: USER_PROVIDED = supplied in the request; "
            "DEFAULTED = filled by the released input contract; "
            "DERIVED = inherited during a context override; UNKNOWN = origin not recorded."
        )
        _append_mapping_lines(lines, case.inputs, units=case.units, origins=origins)
    return lines


_AR_REPORT_NOTE = (
    "نتيجة حساب هندسي حتمية مبنية على النموذج المختار؛ وليست قياسًا حقليًا، "
    "ولا توقعًا للإنتاج، ولا توصية تشغيلية."
)


_ARABIC_REPORT_LABELS = {
    "pr": "ضغط المكمن (Pr)",
    "thp": "ضغط رأس البئر (THP)",
    "tvd": "العمق الرأسي الحقيقي (TVD)",
    "id": "القطر الداخلي للأنبوب (Tubing ID)",
    "tubing_id_in": "القطر الداخلي للأنبوب (Tubing ID)",
    "gor": "نسبة الغاز إلى النفط (GOR)",
    "gor_scf_stb": "نسبة الغاز إلى النفط (GOR)",
    "rs": "نسبة الغاز المذاب إلى النفط (Rs)",
    "rs_scf_stb": "نسبة الغاز المذاب إلى النفط (Rs)",
    "api": "درجة API للنفط (Oil API gravity)",
    "gamma_g": "الكثافة النوعية للغاز (Gas specific gravity)",
    "gamma_w": "الكثافة النوعية للماء (Water specific gravity)",
    "mu_l": "لزوجة السائل (Liquid viscosity)",
    "mu_l_cp": "لزوجة السائل (Liquid viscosity)",
    "bo": "معامل حجم تكوين النفط (Bo)",
    "bo_rb_stb": "معامل حجم تكوين النفط (Bo)",
    "bw": "معامل حجم تكوين الماء (Bw)",
    "wc": "القطع المائي (Water cut)",
    "water_cut": "القطع المائي (Water cut)",
    "j": "معامل الإنتاجية (PI)",
    "operating_rate_bpd": "معدل السائل التشغيلي",
    "operating_rate_stbd": "معدل الإنتاج التشغيلي",
    "calculated_rate_bpd": "معدل السائل المحسوب",
    "q_op": "معدل الإنتاج التشغيلي",
    "pwf_op": "ضغط قاع البئر أثناء الجريان (Pwf)",
    "pwf_psia": "ضغط قاع البئر أثناء الجريان (Pwf)",
    "wellhead_pressure_psia": "ضغط رأس البئر (Pwh)",
    "upstream_pressure_psia": "ضغط المنبع (Upstream pressure)",
    "downstream_pressure_psia": "ضغط المصب (Downstream pressure)",
    "pressure_ratio": "نسبة الضغط (Pressure ratio)",
    "residual": "المتبقي الضغطي (Pressure residual)",
    "solver_residual_psi": "المتبقي الضغطي للحل (Solver pressure residual)",
    "pressure_residual_psi": "المتبقي الضغطي للحل (Solver pressure residual)",
    "choke_size_64th_in": "Choke size",
    "liquid_rate_bpd": "معدل السائل المقدم",
    "t_wh": "درجة حرارة رأس البئر (Twh)",
    "t_wh_f": "درجة حرارة رأس البئر (Twh)",
    "geothermal": "التدرج الحراري الأرضي (Geothermal gradient)",
    "geothermal_f_100ft": "التدرج الحراري الأرضي (Geothermal gradient)",
    "sigma": "التوتر السطحي (Surface tension)",
    "q_min": "الحد الأدنى لمعدل الإنتاج",
    "q_max": "الحد الأقصى لمعدل الإنتاج",
    "tol": "سماحية الضغط (Pressure tolerance)",
    "pressure_tol": "سماحية الضغط (Pressure tolerance)",
    "max_refine_iter": "الحد الأقصى لتكرارات التحسين (Maximum refinement iterations)",
    "parameter_value": "قيمة المتغير (Parameter value)",
    "classification": "التصنيف الهندسي (Engineering classification)",
    "flow_regime": "نظام الجريان (Flow regime)",
    "choke_flow_regime": "Choke flow regime",
    "reason": "التفسير الهندسي",
    "solver_iterations": "تكرارات Solver (Solver iterations)",
    "solver_method": "طريقة Solver (Solver method)",
    "convergence": "التقارب العددي (Convergence)",
    "n_points": "عدد النقاط المقيمة (Evaluated points)",
    "segments": "مقاطع الأنبوب (Tubing segments)",
    "n_segments": "مقاطع الأنبوب (Tubing segments)",
    "vlp_model": "نموذج VLP (VLP model)",
    "ipr_model": "نموذج IPR (IPR model)",
    "choke_model": "Choke correlation",
    "z_factor": "عامل الانضغاطية (Z factor)",
}


def _arabic_report_label(key: Any) -> str:
    return _ARABIC_REPORT_LABELS.get(str(key), arabic_label(key))


def _arabic_report_model(value: Any) -> str:
    models = {
        "linear": "Linear",
        "linear ipr": "Linear IPR",
        "vogel": "Vogel",
        "composite": "Composite",
        "auto": "Auto",
        "beggs_brill": "Beggs–Brill",
        "gilbert_1954": "Gilbert correlation",
        "black_oil_v1": "Black-Oil",
        "pressure_dependent": "pressure-dependent",
        "blackoilpvtprovider": "Black-Oil PVT",
    }
    text = str(value)
    return models.get(text.lower(), text)


def _arabic_report_status(value: Any) -> str:
    statuses = {
        "ok": "OK",
        "converged": "converged",
        "unique_operating_point": "UNIQUE_OPERATING_POINT",
        "critical": "CRITICAL",
        "subcritical": "SUBCRITICAL",
        "no_operating_point": "NO_OPERATING_POINT",
        "physically_invalid_state": "PHYSICALLY_INVALID_STATE",
    }
    text = str(value).strip()
    return statuses.get(text.lower(), text)


def _arabic_value_text(key: Any, value: Any, units: Mapping[str, Any] | None = None) -> str:
    if value is None:
        return "غير مقدم"
    if isinstance(value, bool):
        return "نعم" if value else "لا"
    if isinstance(value, (int, float)):
        rendered = _number(value)
        unit = _unit(key, units)
        return f"{rendered} {unit}".strip()
    if isinstance(value, str):
        lower = value.strip().lower()
        if lower in {"ok", "converged", "unique_operating_point", "critical", "subcritical", "no_operating_point", "physically_invalid_state"}:
            return _arabic_report_status(value)
        if lower in {"linear", "linear ipr", "vogel", "composite", "auto", "beggs_brill", "gilbert_1954", "black_oil_v1", "pressure_dependent", "blackoilpvtprovider"}:
            return _arabic_report_model(value)
        if lower == "rate_scan + bracketed_bisection":
            return "rate_scan + bracketed_bisection"
        if lower == "well-side and choke-side pressure relationships agree within tolerance.":
            return "توافقت علاقة الضغط في جانب البئر مع علاقة الضغط في جانب Choke ضمن السماحية المحددة."
        if lower == "black-oil":
            return "Black-Oil"
        if lower == "pressure-dependent":
            return "pressure-dependent"
        return _safe_text(value)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return "، ".join(_arabic_value_text(key, item, units) for item in value)
    return "بيانات هندسية محفوظة"


def _arabic_append_mapping_lines(
    lines: list[str],
    data: Mapping[str, Any],
    *,
    units: Mapping[str, Any] | None = None,
    indent: str = "",
    skip: frozenset[str] = _INTERNAL_KEYS,
    origins: Mapping[str, Any] | None = None,
) -> None:
    for key, value in data.items():
        key_text = str(key)
        if key_text in skip or value is None:
            continue
        if isinstance(value, Mapping):
            lines.append(f"{indent}{_arabic_report_label(key_text)}:")
            _arabic_append_mapping_lines(lines, value, units=units, indent=indent + "  ", skip=skip)
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            if value and all(not isinstance(item, (Mapping, Sequence)) for item in value):
                lines.append(f"{indent}{_arabic_report_label(key_text)}: {_arabic_value_text(key_text, value, units)}")
            else:
                lines.append(f"{indent}{_arabic_report_label(key_text)}:")
                for item in value:
                    if isinstance(item, Mapping):
                        _arabic_append_mapping_lines(lines, item, units=units, indent=indent + "  ", skip=skip)
                    else:
                        lines.append(f"{indent}  {_arabic_value_text(key_text, item, units)}")
        else:
            suffix = _origin_suffix(origins.get(key_text)) if origins and key_text in origins else ""
            lines.append(f"{indent}{_arabic_report_label(key_text)}: {_arabic_value_text(key_text, value, units)}{suffix}")


def _arabic_pvt_lines(pvt: Any) -> list[str]:
    if not isinstance(pvt, Mapping) or not pvt:
        return [
            "وصف خواص الموائع (PVT): استُخدمت المدخلات التقليدية المحددة؛ ولم يُطلب تقييم Black-Oil المعتمد على الضغط."
        ]
    mode = str(pvt.get("mode", "")).lower()
    model = str(pvt.get("model", "")).lower()
    provenance = pvt.get("provenance")
    enabled = mode == "pressure_dependent" or model == "black_oil_v1" or (
        isinstance(provenance, Mapping) and provenance.get("enabled")
    )
    if not enabled:
        return ["وصف خواص الموائع (PVT): استُخدمت خواص الموائع التقليدية المحددة في الحالة."]
    metadata = provenance if isinstance(provenance, Mapping) else {}
    pressure_range = metadata.get("pressure_range_psia") or metadata.get("pressure_ranges")
    values: list[float] = []
    if isinstance(pressure_range, Sequence) and not isinstance(pressure_range, (str, bytes, bytearray)):
        for item in pressure_range:
            if isinstance(item, (int, float)):
                values.append(float(item))
            elif isinstance(item, Sequence) and not isinstance(item, (str, bytes, bytearray)):
                values.extend(float(x) for x in item if isinstance(x, (int, float)))
    lines = [
        "وصف خواص الموائع (PVT): خواص Black-Oil معتمدة على الضغط.",
        f"نمط خواص الموائع: {_arabic_report_model(mode) if mode else 'pressure-dependent'}.",
        f"نموذج خواص الموائع: {_arabic_report_model(model) if model else 'Black-Oil'}.",
    ]
    if len(values) >= 2:
        lines.append(f"نطاق الضغط المقيم: {_number(values[0])} إلى {_number(values[-1])} psia.")
    elif isinstance(pvt.get("context"), Mapping) and pvt["context"].get("pressure_psia") is not None:
        lines.append(f"ضغط التقييم المسجل: {_number(pvt['context']['pressure_psia'])} psia.")
    phases = metadata.get("phase_regions")
    if phases:
        lines.append("منطقة الطور: " + "، ".join(_safe_text(item) for item in phases) + ".")
    evaluations = metadata.get("pvt_evaluations")
    if evaluations:
        lines.append(f"عدد تقييمات خواص الضغط: {_number(evaluations)} حالة.")
    return lines


def _arabic_generic_result(result: Any, units: Mapping[str, Any]) -> list[str]:
    lines: list[str] = []
    if isinstance(result, Mapping):
        prominent = (
            "operating_rate_bpd", "calculated_rate_bpd", "operating_rate_stbd", "q_op",
            "pwf_op", "wellhead_pressure_psia", "bottomhole_pressure_psia",
            "pressure_residual_psi", "residual", "flow_regime", "classification",
        )
        rendered: set[str] = set()
        for key in prominent:
            if key in result and result[key] is not None:
                rendered.add(key)
                lines.append(f"{_arabic_report_label(key)}: {_arabic_value_text(key, result[key], units)}")
        remaining = {
            key: value for key, value in result.items()
            if key not in rendered and key not in _INTERNAL_KEYS
            and key not in {"warnings", "limitations", "pvt_metadata", "provenance", "choke_result", "vlp_result"}
        }
        if remaining:
            _arabic_append_mapping_lines(lines, remaining, units=units)
    elif result:
        lines.append(_safe_text(result))
    return lines


def generate_report_arabic_v1(case: EngineeringCase) -> str:
    """Return a deterministic, Arabic-first report from the stored Case envelope."""
    if not isinstance(case, EngineeringCase):
        raise TypeError("generate_report_arabic_v1 requires an EngineeringCase")
    lines = [
        "# تقرير الحالة الهندسية V1",
        "",
        f"## {arabic_calculation_title(case.calculation_type)}",
        "",
        "> " + _AR_REPORT_NOTE,
        "",
        "## هوية الحالة",
        "",
        f"- **معرّف الحالة:** `{_safe_text(case.case_id)}`",
        f"- **الحالة:** `{arabic_status(case.status)}`",
        "",
        f"الحالة الهندسية: {arabic_status(case.status)}.",
        "",
        "## النموذج الهندسي",
        "",
        "يعرض هذا التقرير النموذج النفطي المختار، والمدخلات المقدمة، والنتائج المحسوبة، والقيود المسجلة دون إضافة بيانات غير موجودة في الحالة.",
        "",
    ]
    if isinstance(case.model, Mapping):
        model_name = case.model.get("engine") or case.model.get("model")
        if model_name:
            lines.append(f"نموذج الحساب: {_arabic_report_model(model_name)}.")
        if isinstance(case.selectors, Mapping) and case.selectors:
            controls: list[str] = []
            for key, value in case.selectors.items():
                if str(key) in _INTERNAL_KEYS or value is None:
                    continue
                controls.append(f"{_arabic_report_label(key)} = {_arabic_value_text(key, value)}")
            if controls:
                lines.append("ضوابط النموذج المختارة: " + "؛ ".join(controls) + ".")
        lines.append("")
    lines.extend(["## المدخلات الهندسية المقدمة", ""])
    if isinstance(case.inputs, Mapping) and case.inputs:
        origins = input_origins_for_case(case)
        lines.append(
            "مصدر المدخلات: USER_PROVIDED = مقدم في الطلب؛ DEFAULTED = قيمة افتراضية "
            "من عقد المدخلات؛ DERIVED = موروث أثناء تعديل سياقي؛ UNKNOWN = المصدر غير مسجل."
        )
        _arabic_append_mapping_lines(lines, case.inputs, units=case.units, origins=origins)
    else:
        lines.append("استُخدمت حالة المدخلات الهندسية الكاملة المحفوظة مع معرّف الحالة.")
    lines.extend(["", "## وصف خواص الموائع (PVT)", ""])
    lines.extend(_arabic_pvt_lines(case.pvt))
    lines.append("")
    error = _result_error(case)
    if error is not None:
        code, message = error
        lines.extend([
            "## النتيجة",
            "",
            "لم ينتج الحساب نقطة تشغيل هندسية صالحة.",
            f"الحالة الهندسية: {_safe_text(code)}.",
            f"التفصيل الهندسي: {_safe_text(message)}",
            "",
        ])
    else:
        lines.extend(["## النتيجة", ""])
        result_lines = _arabic_generic_result(case.result, case.units)
        lines.extend(result_lines or ["اكتمل الحساب دون حقول عددية إضافية للنتيجة."])
        lines.extend(["", "هذه نتيجة محسوبة من المحرك الهندسي الحتمي المختار، وليست قياسًا حقليًا.", ""])
    if case.limitations:
        lines.extend(["## القيود الهندسية", ""])
        lines.extend(f"- القيد المسجل من المحرك: {_safe_text(item)}" for item in case.limitations if item)
        lines.append("")
    if case.warnings:
        lines.extend(["## التحذيرات الهندسية", ""])
        lines.extend(f"- التحذير المسجل من المحرك: {_safe_text(item)}" for item in case.warnings if item)
        lines.append("")
    lines.extend([
        "## قابلية إعادة الحساب",
        "",
        "يحفظ معرّف الحالة حالة المدخلات، واختيار النموذج، وسياق خواص الموائع، ومسار الحساب الحتمي لإتاحة إعادة الحساب داخل البوت.",
        "",
        "## الأمانة الهندسية",
        "",
        _AR_REPORT_NOTE,
        "لا يضيف التقرير قياسات حقلية أو توصيات أو تعليمات تشغيلية غير موجودة في نتيجة المحرك.",
        "",
    ])
    return "\n".join(lines).rstrip() + "\n"


def generate_report_v1(case: EngineeringCase, language: str = "en") -> str:
    """Return a stable, human-readable engineering report derived from ``case``."""
    if str(language).lower() in {"ar", "arabic", "العربية"}:
        return generate_report_arabic_v1(case)
    if not isinstance(case, EngineeringCase):
        raise TypeError("generate_report_v1 requires an EngineeringCase")

    title = _calculation_title(case.calculation_type)
    lines = [
        "# Engineering Case Report V1",
        "",
        f"## {title}",
        "",
        "> " + _REPORT_NOTE,
        "",
        "## Case Identity",
        "",
        f"- **Case ID:** `{_safe_text(case.case_id)}`",
        f"- **Status:** `{_safe_text(case.status)}`",
        "",
        _status_line(case),
        "",
        "## Engineering model",
        "",
        "The report presents the selected petroleum-engineering model, supplied inputs, calculated response, and stated limitations in readable form.",
        "",
    ]

    if isinstance(case.model, Mapping):
        model_name = case.model.get("engine") or case.model.get("model")
        if model_name:
            lines.append(f"Calculation model: {_safe_text(model_name)}")
        if case.selectors and isinstance(case.selectors, Mapping):
            selector_parts = []
            for key, value in case.selectors.items():
                if str(key) in _INTERNAL_KEYS:
                    continue
                if str(key) == "variable":
                    selector_parts.append(f"{_label(key)} = {_variable_display(value)}")
                elif str(key) == "objective":
                    selector_parts.append(f"Optimization target = {_safe_text(value).replace('_', ' ')}")
                elif value is not None:
                    selector_parts.append(f"{_label(key)} = {_safe_text(value)}")
            if selector_parts:
                lines.append("Selected model controls: " + "; ".join(selector_parts) + ".")
        lines.append("")

    lines.extend(["## Supplied engineering inputs", ""])
    input_lines = _case_inputs(case)
    if input_lines:
        lines.extend(input_lines)
    else:
        lines.append("The calculation used the complete input state stored with this engineering case.")
    lines.append("")

    lines.extend(["## PVT description", ""])
    lines.extend(_pvt_lines(case.pvt))
    lines.append("")

    error = _result_error(case)
    if error is not None:
        code, message = error
        lines.extend([
            "## Result",
            "",
            "The calculation did not produce a valid engineering operating result.",
            f"Engineering status: {code}.",
            f"Engineering detail: {message}",
            "",
        ])
    else:
        result = case.result if isinstance(case.result, Mapping) else {}
        if case.calculation_type == "sensitivity_v1":
            lines.extend(_sensitivity_result(result, case.units))
        elif case.calculation_type == "optimize_v1":
            lines.extend(_optimize_result(result, case.units))
        else:
            lines.extend(["## Result", ""])
            result_lines = _generic_result(result, case.units)
            if result_lines:
                lines.extend(result_lines)
            else:
                lines.append("The engineering engine completed without additional scalar result fields.")
            lines.append("")
        lines.extend([
            "This is a calculated model result based on the selected deterministic engineering engine; it is not measured field data.",
            "",
        ])

    limitations = [item for item in (case.limitations or []) if item]
    warnings = [item for item in (case.warnings or []) if item]
    if limitations:
        lines.extend(["## Engineering limitations", ""])
        for item in limitations:
            lines.append(f"- {_safe_text(item)}")
        lines.append("")
    if warnings:
        lines.extend(["## Engineering warnings", ""])
        for item in warnings:
            lines.append(f"- {_safe_text(item)}")
        lines.append("")

    lines.extend([
        "## Reproducibility",
        "",
        "The same input state, model selection, PVT context, and deterministic calculation path are retained with the Case ID so the case can be replayed while it remains in the bot process.",
        "",
        "## Engineering honesty",
        "",
        _REPORT_NOTE,
        "The report does not add field measurements, recommendations, or operating instructions that are not present in the underlying calculation.",
        "",
    ])
    return "\n".join(lines).rstrip() + "\n"


# Explicit alias for callers that prefer a renderer-style name.
render_report_v1 = generate_report_v1


__all__ = ["generate_report_arabic_v1", "generate_report_v1", "render_report_v1"]
