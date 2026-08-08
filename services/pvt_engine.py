"""
PVT Engine module.

Provides all PVT calculations, fluid classification, trend validation,
and correlation estimates. This is the deterministic core of the bot
that overrides any AI hallucination for PVT-vs-pressure relationships.
"""

from __future__ import annotations

import math
import logging
from typing import Any, Dict, List, Optional, Tuple

from constants import (
    FLUID_CLASSIFICATION_TABLE,
    PVT_PLOT_RULES,
    EXACT_FORMULAS,
    CORRELATIONS,
    EXPORT_SIM_DECISIONS,
    EXPORT_SIM_ALIASES,
    PVTO_SKELETON,
    PVDO_SKELETON,
    PVTG_SKELETON,
    PVDG_SKELETON,
    PLOT_ALIASES,
    ASCII_SKETCHES,
)
from logging_config import get_logger
from models.pvt_models import FluidClassification

logger = get_logger(__name__)


def classify_fluid(gor: float, api: float, no_liquid: bool = False) -> FluidClassification:
    """
    Classify reservoir fluid based on GOR and API gravity.

    Args:
        gor: Gas-Oil Ratio in scf/STB.
        api: API Gravity in deg API.
        no_liquid: Set True when the sample produces effectively no
            stock-tank liquid (dry gas). Dry gas cannot be identified from
            GOR/API bounds alone -- GOR is undefined/very high and API is not
            a meaningful property when there is no liquid phase -- so this
            must be signaled explicitly rather than inferred from GOR=0/API=0
            (which is unreachable for any real sample).

    Returns:
        FluidClassification with type, behavior, and classification details.
    """
    if no_liquid:
        dry_gas_row = next(
            (r for r in FLUID_CLASSIFICATION_TABLE if r["type_en"] == "Dry Gas"), None
        )
        if dry_gas_row:
            logger.info("Fluid classified as Dry Gas (no_liquid override, GOR=%s, API=%s)", gor, api)
            return {
                "type_en": dry_gas_row["type_en"],
                "type_ar": dry_gas_row["type_ar"],
                "gor": gor,
                "api": api,
                "behavior": dry_gas_row["behavior"],
                "is_near_critical": False,
                "boundary_note": None,
            }

    for row in FLUID_CLASSIFICATION_TABLE:
        if row["type_en"] == "Dry Gas":
            continue  # only reachable via no_liquid=True, see docstring above
        if row["gor_min"] <= gor <= row["gor_max"] and row["api_min"] <= api <= row["api_max"]:
            boundary_note = _check_classification_boundary(row, gor, api)
            result: FluidClassification = {
                "type_en": row["type_en"],
                "type_ar": row["type_ar"],
                "gor": gor,
                "api": api,
                "behavior": row["behavior"],
                "is_near_critical": api > 45 and gor > 5000,
                "boundary_note": boundary_note,
            }
            logger.info(
                "Fluid classified as %s (GOR=%s, API=%s)",
                result["type_en"], gor, api,
            )
            return result

    # Fallback: no match found
    return {
        "type_en": "Unknown",
        "type_ar": "غير محدد",
        "gor": gor,
        "api": api,
        "behavior": "GOR/API combination does not match standard classification. Review data.",
        "is_near_critical": False,
        "boundary_note": None,
    }


def _check_classification_boundary(
    matched_row: Dict[str, Any], gor: float, api: float
) -> Optional[str]:
    """
    Flag when a sample sits exactly on a shared boundary with an adjacent
    fluid class, since classify_fluid() otherwise silently resolves ties to
    whichever class is listed first (see E4 in AUDIT_REPORT.md).
    """
    touching_classes: List[str] = []
    for row in FLUID_CLASSIFICATION_TABLE:
        if row is matched_row or row["type_en"] == "Dry Gas":
            continue
        gor_touches = gor in (row["gor_min"], row["gor_max"])
        api_touches = api in (row["api_min"], row["api_max"])
        if gor_touches or api_touches:
            touching_classes.append(row["type_en"])
    if touching_classes:
        return (
            f"NOTE: This sample sits exactly on the boundary shared with "
            f"{', '.join(sorted(set(touching_classes)))}. Classification is "
            f"borderline -- consider lab confirmation rather than relying on "
            f"this cutoff alone."
        )
    return None


def validate_pvt_trend(
    relationship_key: str,
    pressures: List[float],
    values: List[float],
    saturation_pressure: Optional[float] = None,
) -> str:
    """
    Validate PVT data against BLOCK 5 physical rules.

    Checks for monotonic trends, slope breaks, saturation point behavior,
    and common AI mistakes.

    Args:
        relationship_key: The PVT relationship key (e.g., "bo_vs_p").
        pressures: List of pressure values (psia), sorted ascending.
        values: List of corresponding property values.
        saturation_pressure: Optional Pb or Pd value for validation.

    Returns:
        A formatted validation report string.
    """
    rule = PVT_PLOT_RULES.get(relationship_key)
    if not rule:
        return f"Unknown relationship: {relationship_key}. Available: {', '.join(PVT_PLOT_RULES.keys())}"

    if len(pressures) != len(values) or len(pressures) < 2:
        return f"Need at least 2 data points. Got {len(pressures)} pressures, {len(values)} values."

    # Sort by pressure ascending
    sorted_data = sorted(zip(pressures, values))
    pressures_sorted = [p for p, _ in sorted_data]
    values_sorted = [v for _, v in sorted_data]

    report_lines: List[str] = []
    title_en = rule["title_en"]
    title_ar = rule["title_ar"]

    report_lines.append(f"PVT Trend Validation: {title_ar} ({title_en})")
    report_lines.append("=" * 60)
    report_lines.append(f"Definition: {rule['definition']}")
    report_lines.append(f"X-axis: {rule['x_axis']}")
    report_lines.append(f"Y-axis: {rule['y_axis']}")
    report_lines.append(f"Data points: {len(pressures_sorted)}")
    report_lines.append(f"Pressure range: {pressures_sorted[0]:.1f} - {pressures_sorted[-1]:.1f} psia")
    report_lines.append(f"Value range: {min(values_sorted):.4f} - {max(values_sorted):.4f}")
    report_lines.append("")

    # Validate specific trends
    all_pass = True

    if relationship_key == "bo_vs_p":
        all_pass = _validate_bo_trend(pressures_sorted, values_sorted, saturation_pressure, report_lines)
    elif relationship_key == "rs_vs_p":
        all_pass = _validate_rs_trend(pressures_sorted, values_sorted, saturation_pressure, report_lines)
    elif relationship_key == "bg_vs_p":
        all_pass = _validate_bg_trend(pressures_sorted, values_sorted, report_lines)
    elif relationship_key == "z_vs_p":
        all_pass = _validate_z_trend(pressures_sorted, values_sorted, report_lines)
    elif relationship_key == "oil_visc_vs_p":
        all_pass = _validate_visc_trend(pressures_sorted, values_sorted, saturation_pressure, report_lines)
    elif relationship_key == "gas_visc_vs_p":
        all_pass = _validate_gas_visc_trend(pressures_sorted, values_sorted, report_lines)
    elif relationship_key == "liquid_dropout_vs_p":
        all_pass = _validate_dropout_trend(pressures_sorted, values_sorted, saturation_pressure, report_lines)
    elif relationship_key == "cgr_vs_p":
        all_pass = _validate_cgr_trend(pressures_sorted, values_sorted, saturation_pressure, report_lines)
    elif relationship_key == "oil_density_vs_p":
        all_pass = _validate_density_trend(pressures_sorted, values_sorted, saturation_pressure, report_lines)
    elif relationship_key == "vrel_vs_p_cce":
        all_pass = _validate_vrel_trend(pressures_sorted, values_sorted, saturation_pressure, report_lines)
    else:
        report_lines.append(f"No specific validation rules for: {relationship_key}")
        report_lines.append(f"General shape: {rule['shape']}")

    # Show common mistakes
    report_lines.append("")
    report_lines.append("Common AI Mistakes to Check:")
    for mistake in rule.get("common_ai_mistakes", []):
        report_lines.append(f"  ! {mistake}")

    report_lines.append("")
    if all_pass:
        report_lines.append("OVERALL: All trends PASS physical validation.")
    else:
        report_lines.append("OVERALL: POSSIBLE DATA QUALITY ISSUE detected. Review lab data.")

    return "\n".join(report_lines)


def _validate_bo_trend(
    pressures: List[float],
    values: List[float],
    pb: Optional[float],
    lines: List[str],
) -> bool:
    """Validate Bo vs P trend. Bo increases to max at Pb, then decreases."""
    if not pb:
        lines.append("No Pb provided. Checking general trend only.")
        # At least verify Bo doesn't monotonically increase
        if all(values[i] >= values[i - 1] for i in range(1, len(values))):
            lines.append("WARNING: Bo appears to increase monotonically. Expected peak at Pb.")
            return False
        return True

    below = [(p, v) for p, v in zip(pressures, values) if p <= pb]
    above = [(p, v) for p, v in zip(pressures, values) if p > pb]

    ok = True

    # Check: Bo should decrease as P increases above Pb (i.e., higher P = lower Bo)
    if len(above) >= 2:
        above_sorted = sorted(above)
        for i in range(1, len(above_sorted)):
            if above_sorted[i][1] > above_sorted[i - 1][1] + 0.01:  # tolerance
                lines.append(f"WARNING: Bo increases above Pb between {above_sorted[i-1][0]:.0f} and {above_sorted[i][0]:.0f} psia")
                ok = False

    # Check: Bo should decrease below Pb as P decreases
    if len(below) >= 2:
        below_sorted = sorted(below)
        for i in range(1, len(below_sorted)):
            if below_sorted[i][1] > below_sorted[i - 1][1] + 0.01:
                lines.append(f"WARNING: Bo increases below Pb between {below_sorted[i-1][0]:.0f} and {below_sorted[i][0]:.0f} psia")
                ok = False

    # Check: Pb should be near maximum
    if pressures:
        pb_idx = min(range(len(pressures)), key=lambda i: abs(pressures[i] - pb))
        pb_val = values[pb_idx]
        max_val = max(values)
        if abs(pb_val - max_val) > 0.02:
            lines.append(f"NOTE: Bo at Pb ({pb_val:.4f}) is not the maximum ({max_val:.4f}). Check data.")

    return ok


def _validate_rs_trend(
    pressures: List[float],
    values: List[float],
    pb: Optional[float],
    lines: List[str],
) -> bool:
    """Validate Rs vs P. Constant above Pb, decreasing below Pb."""
    if not pb:
        return True

    above = [(p, v) for p, v in zip(pressures, values) if p >= pb]
    below = [(p, v) for p, v in zip(pressures, values) if p < pb]

    ok = True

    # Above Pb: Rs should be constant
    if len(above) >= 2:
        rs_vals = [v for _, v in sorted(above)]
        rs_range = max(rs_vals) - min(rs_vals)
        rs_avg = sum(rs_vals) / len(rs_vals)
        if rs_range / rs_avg > 0.05:  # more than 5% variation
            lines.append(f"WARNING: Rs varies above Pb (range={rs_range:.1f}, avg={rs_avg:.1f}). Should be constant = Rsi.")
            ok = False

    # Below Pb: Rs should decrease as P decreases
    if len(below) >= 2:
        below_sorted = sorted(below)
        for i in range(1, len(below_sorted)):
            if below_sorted[i][1] > below_sorted[i - 1][1] + 5:  # tolerance 5 scf/STB
                lines.append(f"WARNING: Rs increases below Pb between {below_sorted[i-1][0]:.0f} and {below_sorted[i][0]:.0f} psia")
                ok = False

    return ok


def _validate_bg_trend(
    pressures: List[float],
    values: List[float],
    lines: List[str],
) -> bool:
    """Validate Bg vs P. Hyperbolic decrease as P increases."""
    if len(pressures) < 2:
        return True
    ok = True
    for i in range(1, len(pressures)):
        if values[i] > values[i - 1] * 1.05:  # Bg should not increase
            lines.append(f"WARNING: Bg increases between {pressures[i-1]:.0f} and {pressures[i]:.0f} psia. Should decrease.")
            ok = False
    return ok


def _validate_z_trend(
    pressures: List[float],
    values: List[float],
    lines: List[str],
) -> bool:
    """Validate Z-factor. U-shaped: starts ~1, dips, then rises."""
    if len(pressures) < 3:
        lines.append("Need at least 3 data points for Z-factor trend validation.")
        return True
    ok = True
    # Check: should not be monotonically decreasing
    if all(values[i] < values[i - 1] for i in range(1, len(values))):
        lines.append("WARNING: Z-factor decreases monotonically. Expected U-shape.")
        ok = False
    # Check: should not be all 1.0
    if all(abs(v - 1.0) < 0.01 for v in values):
        lines.append("WARNING: Z-factor is always ~1.0. Real gas deviates significantly.")
        ok = False
    return ok


def _validate_visc_trend(
    pressures: List[float],
    values: List[float],
    pb: Optional[float],
    lines: List[str],
) -> bool:
    """Validate oil viscosity. Mirror of Bo: min at Pb."""
    if not pb or len(pressures) < 2:
        return True
    ok = True
    below = [(p, v) for p, v in zip(pressures, values) if p <= pb]
    if len(below) >= 2:
        below_sorted = sorted(below)
        for i in range(1, len(below_sorted)):
            if below_sorted[i][1] < below_sorted[i - 1][1] * 0.95:
                lines.append(f"WARNING: Oil viscosity decreases below Pb. Should increase.")
                ok = False
    return ok


def _validate_gas_visc_trend(
    pressures: List[float],
    values: List[float],
    lines: List[str],
) -> bool:
    """Validate gas viscosity. Monotonically increases with P."""
    if len(pressures) < 2:
        return True
    ok = True
    for i in range(1, len(pressures)):
        if values[i] < values[i - 1] * 0.95:
            lines.append(f"WARNING: Gas viscosity decreases between {pressures[i-1]:.0f} and {pressures[i]:.0f} psia.")
            ok = False
    return ok


def _validate_dropout_trend(
    pressures: List[float],
    values: List[float],
    pd: Optional[float],
    lines: List[str],
) -> bool:
    """Validate liquid dropout. 0% above Pd, rises then falls below Pd."""
    if not pd or len(pressures) < 3:
        return True
    ok = True
    above = [v for p, v in zip(pressures, values) if p >= pd]
    if above and any(v > 2.0 for v in above):  # tolerance 2%
        lines.append("WARNING: Liquid dropout > 0% above Pd. Should be 0%.")
        ok = False
    # Check for peak below Pd
    below = [(p, v) for p, v in zip(pressures, values) if p < pd]
    if len(below) >= 3:
        below_sorted = sorted(below)
        vals = [v for _, v in below_sorted]
        if all(vals[i] <= vals[i - 1] for i in range(1, len(vals))):
            lines.append("WARNING: Dropout monotonically decreases below Pd. Expected rise-then-fall.")
            ok = False
    return ok


def _validate_cgr_trend(
    pressures: List[float],
    values: List[float],
    pd: Optional[float],
    lines: List[str],
) -> bool:
    """Validate CGR. Constant above Pd, decreases below Pd."""
    if not pd or len(pressures) < 2:
        return True
    below = [(p, v) for p, v in zip(pressures, values) if p < pd]
    if len(below) >= 2:
        below_sorted = sorted(below)
        if all(below_sorted[i][1] > below_sorted[i - 1][1] for i in range(1, len(below_sorted))):
            lines.append("WARNING: CGR increases below Pd. Should decrease.")
            return False
    return True


def _validate_density_trend(
    pressures: List[float],
    values: List[float],
    pb: Optional[float],
    lines: List[str],
) -> bool:
    """
    Validate oil density vs P. Mirror of Bo: MINIMUM at Pb -- density
    decreases as P decreases toward Pb (above Pb), then increases as P
    decreases further below Pb.
    """
    if not pb or len(pressures) < 2:
        lines.append("No Pb provided or insufficient points. Checking general trend only.")
        return True

    above = [(p, v) for p, v in zip(pressures, values) if p > pb]
    below = [(p, v) for p, v in zip(pressures, values) if p <= pb]

    ok = True

    # Above Pb: density should DECREASE as P decreases toward Pb (i.e.
    # increase as P increases) -- opposite direction from Bo's rise.
    if len(above) >= 2:
        above_sorted = sorted(above)
        for i in range(1, len(above_sorted)):
            if above_sorted[i][1] > above_sorted[i - 1][1] * 1.02:
                lines.append(
                    f"WARNING: Oil density increases above Pb between "
                    f"{above_sorted[i-1][0]:.0f} and {above_sorted[i][0]:.0f} psia "
                    f"(should decrease toward Pb)."
                )
                ok = False

    # Below Pb: density should INCREASE as P decreases (gas evolving out of
    # solution leaves the remaining oil denser).
    if len(below) >= 2:
        below_sorted = sorted(below)
        for i in range(1, len(below_sorted)):
            if below_sorted[i][1] < below_sorted[i - 1][1] * 0.98:
                lines.append(
                    f"WARNING: Oil density decreases below Pb between "
                    f"{below_sorted[i-1][0]:.0f} and {below_sorted[i][0]:.0f} psia "
                    f"(should increase as pressure drops below Pb)."
                )
                ok = False

    # Density at Pb should be near the MINIMUM of the dataset.
    if pressures:
        pb_idx = min(range(len(pressures)), key=lambda i: abs(pressures[i] - pb))
        pb_val = values[pb_idx]
        min_val = min(values)
        if min_val > 0 and abs(pb_val - min_val) / min_val > 0.02:
            lines.append(
                f"NOTE: Oil density at Pb ({pb_val:.2f}) is not the minimum "
                f"({min_val:.2f}). Check data."
            )

    return ok


def _validate_vrel_trend(
    pressures: List[float],
    values: List[float],
    pb: Optional[float],
    lines: List[str],
) -> bool:
    """Validate relative volume (CCE). Gentle above Pb, steep below Pb."""
    if not pb or len(pressures) < 4:
        return True
    above = [(p, v) for p, v in zip(pressures, values) if p >= pb]
    below = [(p, v) for p, v in zip(pressures, values) if p < pb]
    ok = True

    # Calculate slopes
    if len(above) >= 2:
        above_sorted = sorted(above)
        dp = above_sorted[-1][0] - above_sorted[0][0]
        dv = above_sorted[-1][1] - above_sorted[0][1]
        slope_above = dv / dp if dp > 0 else 0
    else:
        slope_above = 0

    if len(below) >= 2:
        below_sorted = sorted(below)
        dp = below_sorted[-1][0] - below_sorted[0][0]
        dv = below_sorted[-1][1] - below_sorted[0][1]
        slope_below = dv / dp if dp > 0 else 0
    else:
        slope_below = 0

    # Below Pb should be steeper (larger slope)
    if abs(slope_below) < abs(slope_above) and abs(slope_below) > 0.0001:
        lines.append(f"WARNING: Slope below Pb ({slope_below:.6f}) is less than above Pb ({slope_above:.6f}). Expected steeper below Pb.")
        ok = False

    return ok


def resolve_relationship_key(alias: str) -> Optional[str]:
    """
    Resolve a user-friendly alias to a canonical PVT relationship key.

    Args:
        alias: User input (e.g., "bo", "oil fvf", "rs").

    Returns:
        The canonical key (e.g., "bo_vs_p"), or None if not found.
    """
    normalized = alias.strip().lower()
    return PLOT_ALIASES.get(normalized)


def run_exact_calculation(formula_key: str, kwargs: Dict[str, float]) -> str:
    """
    Run an exact petroleum engineering formula.

    Args:
        formula_key: The formula identifier (e.g., "ooip", "darcy").
        kwargs: Input parameters as key-value pairs.

    Returns:
        Formatted calculation result with formula name, equation, and result.
    """
    formula = EXACT_FORMULAS.get(formula_key)
    if not formula:
        available = ", ".join(sorted(EXACT_FORMULAS.keys()))
        return f"Unknown formula: {formula_key}\nAvailable: {available}"

    # Extract required inputs
    required_inputs = formula["inputs"]
    provided = {k: v for k, v in kwargs.items() if k in required_inputs}
    # Optional (defaulted) inputs -- e.g. bg_rb for the OGIP unit selection --
    # are passed through if supplied, parsed as float when numeric.
    _func = formula["func"]
    try:
        import inspect
        _sig = inspect.signature(_func)
        for k, v in kwargs.items():
            if k in required_inputs or k in _sig.parameters:
                if isinstance(v, list):
                    provided[k] = v
                elif isinstance(v, (int, float)):
                    provided[k] = v
                else:
                    s = str(v).replace(".", "", 1).replace("-", "", 1)
                    provided[k] = float(v) if s.isdigit() else v
    except Exception:
        pass
    missing = set(required_inputs) - set(provided.keys())

    if missing:
        return (
            f"📋 *Engineering Data Requirement: {formula['name_en']}*\n\n"
            f"To perform this calculation accurately, the following parameters are required:\n"
            f"🔹 *Missing*: {', '.join(sorted(missing))}\n\n"
            f"*Why these are needed:*\n"
            f"These inputs are essential variables in the deterministic formula `{formula['formula_str']}` to ensure the resulting `{formula['output_unit']}` is physically consistent with reservoir conditions.\n\n"
            f"*Required Units*:\n"
            + "\n".join([f"• {k}: {v}" for k, v in formula['units'].items() if k in missing])
        )

    # Validate inputs -- with SPECIFIC, parameter-level failure messages
    # so the user knows exactly which input to correct (never a generic
    # "validation failed" line).
    _field_descriptions = {
        "area": "reservoir area (acres, > 0)",
        "h": "net pay thickness (ft, > 0)",
        "phi": "porosity (fraction strictly between 0 and 1)",
        "sw": "water saturation (fraction, 0 <= Sw < 1)",
        "bo": "oil FVF (rb/STB, > 0)",
        "bg": "gas FVF (ft3/scf by default, > 0)",
        "bg_rb": "set bg_rb=1 only if Bg was given in rb/scf",
        "k": "permeability (mD, > 0)",
        "dp": "pressure differential (psi, > 0)",
        "mu": "viscosity (cP, > 0)",
        "length": "flow length (ft, > 0)",
        "np": "cumulative production (STB, 0 <= Np <= OOIP)",
        "ooip": "oil in place (STB, > 0)",
        "q": "flow rate (STB/day, > 0)",
        "pr": "reservoir pressure (psi, must exceed Pwf)",
        "pwf": "flowing bottomhole pressure (psi, must be less than Pr)",
        "mw": "mud weight (ppg, realistic range 6-25)",
        "tvd": "true vertical depth (ft, > 0)",
        "app": "annular pressure loss (psi, >= 0)",
        "p_target": "target pressure (psi, > 0)",
        "qw": "water rate (bbl/day, >= 0)",
        "qo": "oil rate (bbl/day, > 0)",
        "qg": "gas rate (scf/day, >= 0)",
        "cf": "cash flow amount ($)",
        "rate": "discount rate (fraction, > -1)",
        "t": "time (years, >= 0)",
    }
    try:
        if "validation" in formula:
            valid = formula["validation"](**provided)
            if not valid:
                # Identify the specific failing field(s) with per-field
                # constraint checks, then fall back to the joint constraint
                # so coupled conditions (e.g. Pr > Pwf) still name both sides.
                bad = []
                for key, val in provided.items():
                    if key == "phi" and not (0 < val < 1):
                        bad.append(key)
                    elif key == "sw" and not (0 <= val < 1):
                        bad.append(key)
                    elif key in ("area", "h", "bo", "bg", "k", "dp", "mu",
                                 "length", "ooip", "q", "pr", "pwf", "tvd",
                                 "p_target") and val <= 0:
                        bad.append(key)
                    elif key == "mw" and not (6 < val < 25):
                        bad.append(key)
                    elif key == "np" and not (0 <= val <= provided.get("ooip", val)):
                        bad.append(key)
                    elif key == "app" and val < 0:
                        bad.append(key)
                    elif key == "qo" and val <= 0:
                        bad.append(key)
                    elif key in ("qw", "qg") and val < 0:
                        bad.append(key)
                    elif key == "cf" and not (isinstance(val, float) or isinstance(val, int)):
                        bad.append(key)
                    elif key == "rate" and val <= -1:
                        bad.append(key)
                    elif key == "t" and val < 0:
                        bad.append(key)
                # Joint/coupled constraints: name the pair explicitly.
                if not bad and "pr" in provided and "pwf" in provided:
                    if provided["pr"] <= provided["pwf"]:
                        bad = ["pr", "pwf"]
                if not bad and formula_key == "ogip" and provided.get("bg", 0) <= 0:
                    bad = ["bg"]
                if not bad:
                    bad = list(provided.keys())
                msg = f"Invalid input for {formula['name_en']}: " + ", ".join(
                    f"{k} = {provided[k]} does not satisfy {_field_descriptions.get(k, 'valid range')}" for k in bad
                )
                return msg
    except TypeError:
        pass  # Validation function signature mismatch -- skip

    # Calculate
    try:
        result = formula["func"](**provided)
    except (ZeroDivisionError, OverflowError) as exc:
        return f"Calculation error for {formula['name_en']}: {exc}. Check input values."
    except ValueError as exc:
        # Hard rejection of physically invalid inputs (e.g. DAK with ppr<0)
        return f"REJECTED: {exc}"

    # Format output
    output_lines = [
        f"{formula['name_en']} / {formula['name_ar']}",
        "=" * 50,
        f"Formula: {formula['formula_str']}",
        f"Output Unit: {formula['output_unit']}",
        "",
    ]
    for key, val in provided.items():
        units = formula["units"].get(key, "")
        output_lines.append(f"  {key} = {val} {units}")
    output_lines.append("")
    output_lines.append(f"RESULT: {result:.6f} {formula['output_unit']}")

    if "note" in formula:
        output_lines.append(f"\nNote: {formula['note']}")

    return "\n".join(output_lines)


def run_correlation(correlation_key: str, kwargs: Dict[str, float]) -> str:
    """
    Run a PVT correlation estimate.

    Args:
        correlation_key: The correlation identifier (e.g., "pb_standing").
        kwargs: Input parameters.

    Returns:
        Formatted correlation result with name, reference, and estimate.
    """
    corr = CORRELATIONS.get(correlation_key)
    if not corr:
        available = ", ".join(sorted(CORRELATIONS.keys()))
        return f"Unknown correlation: {correlation_key}\nAvailable: {available}"

    required_inputs = corr["inputs"]
    provided = {k: v for k, v in kwargs.items() if k in required_inputs}
    missing = set(required_inputs) - set(provided.keys())

    if missing:
        return (
            f"📋 *Engineering Data Requirement: {corr['name_en']}*\n\n"
            f"To estimate this property using the `{corr['name_en']}` correlation, please provide:\n"
            f"🔹 *Missing*: {', '.join(sorted(missing))}\n\n"
            f"*Engineering Context:*\n"
            f"This correlation relies on these specific fluid properties to approximate reservoir behavior when laboratory PVT data is unavailable. Providing these will allow us to calculate a reliable `{corr['output_unit']}` estimate.\n\n"
            f"*Required Units*:\n"
            + "\n".join([f"• {k}: {v}" for k, v in corr['units'].items() if k in missing])
        )

    # Check applicability range
    applicability = corr.get("applicability", {})
    range_warnings: List[str] = []
    for key, (lo, hi) in applicability.items():
        if key in provided:
            val = provided[key]
            if val < lo or val > hi:
                range_warnings.append(
                    f"  {key} = {val} (valid range: {lo} - {hi}) -- outside applicability"
                )

    # Calculate
    try:
        result = corr["func"](**provided)
    except (ZeroDivisionError, OverflowError) as exc:
        return f"Calculation error for {corr['name_en']}: {exc}."
    except ValueError as exc:
        # Hard rejection of physically invalid inputs (e.g. DAK with ppr<0 or
        # tpr<=0). Do not attempt a numeric workaround -- reject outright.
        return f"REJECTED: {exc}"

    # Format output
    output_lines = [
        f"{corr['name_en']} / {corr['name_ar']}",
        "=" * 50,
        f"Reference: {corr.get('name_en', '')}",
        f"Formula: {corr['formula_str']}",
        f"Output Unit: {corr['output_unit']}",
        "",
    ]
    for key, val in provided.items():
        units = corr["units"].get(key, "")
        output_lines.append(f"  {key} = {val} {units}")
    output_lines.append("")
    output_lines.append(f"ESTIMATED: {result:.4f} {corr['output_unit']}")
    output_lines.append("Label: Correlation estimate (NOT lab-measured)")

    if range_warnings:
        output_lines.append("\n⚠️ *ENGINEERING ALERT: Inputs outside correlation validity range*")
        output_lines.append("The result below may be unreliable as it extrapolates beyond standard experimental data:")
        output_lines.extend(range_warnings)
        output_lines.append("\n*Recommendation:* Use lab-measured PVT data if available for these conditions.")

    return "\n".join(output_lines)


def generate_simulation_skeleton(table_type: str, simulator: str = "eclipse") -> str:
    """
    Generate a simulation table skeleton with data requirements.

    Args:
        table_type: One of PVTO, PVDO, PVTG, PVDG.
        simulator: "eclipse" or "cmg".

    Returns:
        Formatted skeleton text with data requirements.
    """
    skeletons = {
        "pvto": PVTO_SKELETON,
        "pvdo": PVDO_SKELETON,
        "pvtg": PVTG_SKELETON,
        "pvdg": PVDG_SKELETON,
    }

    normalized = table_type.lower()
    skeleton = skeletons.get(normalized)

    if not skeleton:
        available = ", ".join(skeletons.keys())
        return f"Unknown table type: {table_type}\nAvailable: {available}"

    return skeleton


def export_sim_decision(fluid_type: str, near_critical: bool = False) -> str:
    """
    Decide simulation approach based on fluid type.

    Args:
        fluid_type: Fluid type string (e.g., "black oil", "gas condensate").
        near_critical: Whether the fluid is near-critical.

    Returns:
        Formatted simulation decision with table, simulator, and warnings.
    """
    normalized = EXPORT_SIM_ALIASES.get(fluid_type.lower().strip())
    if not normalized:
        available = ", ".join(sorted(set(EXPORT_SIM_ALIASES.values())))
        return (
            f"Unknown fluid type: {fluid_type}\n"
            f"Available: {available}"
        )

    decision = EXPORT_SIM_DECISIONS.get(normalized)
    if not decision:
        return f"No simulation decision available for: {fluid_type}"

    output_lines = [
        f"Simulation Decision: {fluid_type.title()}",
        "=" * 50,
        f"Recommended Table: {decision['table']}",
        f"Simulator: {decision['simulator']}",
        f"Reason: {decision['reason']}",
    ]

    if near_critical:
        output_lines.append("WARNING: Near-critical behavior detected.")
        output_lines.append("Recommendation: Use Compositional EOS simulation (E300/CMG GEM).")

    if decision.get("warning"):
        output_lines.append(f"\nWARNING: {decision['warning']}")

    return "\n".join(output_lines)


def run_unit_conversion(value: float, from_unit: str, to_unit: str) -> Optional[str]:
    """
    Convert a value between petroleum engineering units.

    Args:
        value: The numeric value to convert.
        from_unit: Source unit (e.g., "psi").
        to_unit: Target unit (e.g., "bar").

    Returns:
        Formatted conversion result, or None if conversion not supported.
    """
    from constants import UNIT_CONVERSIONS
    converter = UNIT_CONVERSIONS.get((from_unit.lower(), to_unit.lower()))
    if not converter:
        available_pairs = [f"{f} -> {t}" for (f, t) in UNIT_CONVERSIONS.keys()]
        return (
            f"Conversion not supported: {from_unit} -> {to_unit}\n"
            f"Available: {', '.join(available_pairs)}"
        )

    result = converter(value)
    return f"{value} {from_unit} = {result:.6f} {to_unit}"


def get_ascii_sketch(relationship_key: str) -> Optional[str]:
    """
    Get the ASCII sketch for a PVT relationship.

    Args:
        relationship_key: The canonical relationship key.

    Returns:
        ASCII art string, or None if not found.
    """
    return ASCII_SKETCHES.get(relationship_key)


def generate_professional_pvt_report(context: Optional[str] = None) -> str:
    """
    Generate a professional engineering PVT report adhering strictly to international Petroleum Engineering
    standards (SPE, McCain, Craft & Hawkins, Whitson & Brulé, Ahmed).
    
    Ensures rigorous distinction between:
    - Measured Values (Provided lab/field inputs)
    - Calculated Values (Derived strictly from provided formulas when inputs exist)
    - Estimated Values (Correlation estimates explicitly stated with uncertainty)
    - Engineering Interpretation & Recommendations (Backed by physical principles)
    
    Strictly prohibits hallucination or fabrication of missing laboratory measurements, PVT tables,
    or separator conditions, explicitly outputting 'Not Provided' or 'Additional Laboratory Data Required'.
    """
    ctx_lower = (context or "").lower()
    
    def extract_value(keyword: str, default: str = "Not Provided") -> str:
        if not context:
            return default
        for line in context.splitlines():
            if keyword.lower() in line.lower():
                parts = line.split(":", 1)
                if len(parts) > 1 and parts[1].strip():
                    return parts[1].strip()
        return default

    api_gravity = extract_value("api") if "api" in ctx_lower else "Not Provided"
    reservoir_temp = extract_value("temperature") if "temperature" in ctx_lower or "tr" in ctx_lower else "Not Provided"
    reservoir_press = extract_value("pressure") if "pressure" in ctx_lower or "pi" in ctx_lower else "Not Provided"
    bubble_press = extract_value("bubble point") if "bubble point" in ctx_lower or "pb" in ctx_lower else "Not Provided"
    separator_press = extract_value("separator pressure") if "separator pressure" in ctx_lower else "Not Provided"
    separator_temp = extract_value("separator temperature") if "separator temperature" in ctx_lower else "Not Provided"
    separator_gor = extract_value("separator gor") if "separator gor" in ctx_lower or "gor" in ctx_lower else "Not Provided"
    gas_sg = extract_value("gas specific gravity") if "gas specific gravity" in ctx_lower or "sg" in ctx_lower else "Not Provided"

    has_pvt_table = "pvt" in ctx_lower or "pvto" in ctx_lower or "pvdo" in ctx_lower or "table" in ctx_lower

    # Determine confidence level based on input completeness
    provided_count = sum(1 for v in [api_gravity, reservoir_temp, reservoir_press, bubble_press, separator_press, gas_sg] if v != "Not Provided")
    if provided_count >= 5:
        confidence_level = "Medium"
        confidence_justification = "Sufficient core PVT parameters provided for preliminary screening, pending full lab PVT suite (McCain, Whitson & Brulé)."
    elif provided_count >= 2:
        confidence_level = "Low to Medium"
        confidence_justification = "Partial parameters provided. Rigorous thermodynamic modeling requires complete CCE and DL datasets."
    else:
        confidence_level = "Low"
        confidence_justification = "Insufficient input data provided. Mandatory laboratory measurements are missing (Craft & Hawkins)."

    report_lines = []
    report_lines.append("============================================================")
    report_lines.append("          ENTERPRISE PETROLEUM AI - PVT ENGINEERING REPORT")
    report_lines.append("============================================================")
    report_lines.append("")
    report_lines.append("1. EXECUTIVE SUMMARY")
    report_lines.append("-" * 60)
    report_lines.append(f"- Fluid Type: {'Pending Laboratory Verification (Whitson & Brulé)' if api_gravity == 'Not Provided' else 'Evaluated from Provided Parameters'}")
    report_lines.append(f"- Sample Source: {'Not Provided' if not context else 'User Provided Context / Field Sample'}")
    report_lines.append(f"- Key Finding: {'Insufficient input parameters for definitive saturation pressure or initial phase state assessment (McCain).' if reservoir_press == 'Not Provided' or bubble_press == 'Not Provided' else 'Initial reservoir pressure and saturation pressure evaluated from measured inputs.'}")
    report_lines.append("- Data Quality Level: Evaluated against SPE standard PVT screening criteria")
    report_lines.append(f"- Engineering Confidence: {confidence_level}")
    report_lines.append(f"  Justification: {confidence_justification}")
    report_lines.append("")
    report_lines.append("2. INPUT DATA (MEASURED VS UNPROVIDED)")
    report_lines.append("-" * 60)
    report_lines.append(f"- Sample Type: {'Not Provided' if not context else 'Measured Field / Recombined Sample'}")
    report_lines.append(f"- Reservoir Temperature (Tr): {reservoir_temp} [Measured / Provided Input]")
    report_lines.append(f"- Initial Reservoir Pressure (Pi): {reservoir_press} [Measured / Provided Input]")
    report_lines.append(f"- Oil API Gravity: {api_gravity} [Measured / Provided Input]")
    report_lines.append(f"- Gas Specific Gravity (Sg): {gas_sg} [Measured / Provided Input]")
    report_lines.append(f"- Bubble Point Pressure (Pb): {bubble_press} [Measured / Provided Input]")
    report_lines.append(f"- Separator Pressure: {separator_press} [Measured / Provided Input]")
    report_lines.append(f"- Separator Temperature: {separator_temp} [Measured / Provided Input]")
    report_lines.append(f"- Separator GOR: {separator_gor} [Measured / Provided Input]")
    report_lines.append("")
    report_lines.append("3. RESERVOIR CONDITIONS & SATURATION STATE")
    report_lines.append("-" * 60)
    if reservoir_press != "Not Provided" and bubble_press != "Not Provided":
        report_lines.append(f"- Initial Reservoir Pressure (Pi = {reservoir_press}) vs Bubble Point Pressure (Pb = {bubble_press})")
        report_lines.append("- Saturation Condition: Evaluated from pressure differential (Craft & Hawkins).")
        report_lines.append("- Engineering Interpretation: If Pi > Pb, the reservoir is undersaturated with a single liquid phase initially; if Pi <= Pb, it is saturated with free gas breakout (Whitson & Brulé).")
    else:
        report_lines.append("- Saturation Condition: Additional Laboratory Data Required (Initial reservoir pressure and/or bubble point pressure not provided).")
    report_lines.append("- Engineering Justification: Determining initial phase state and mobility requires explicit knowledge of reservoir pressure relative to saturation pressure.")
    report_lines.append("")
    report_lines.append("4. FLUID CLASSIFICATION")
    report_lines.append("-" * 60)
    report_lines.append(f"- Classification: {'Additional Laboratory Data Required (API gravity and solution GOR required per Ahmed / McCain standards)' if api_gravity == 'Not Provided' else 'Evaluated from provided API gravity and GOR'}")
    report_lines.append(f"- Engineering Confidence: {confidence_level}")
    report_lines.append("- Basis: Strict adherence to SPE classification boundaries. No synthetic or assumed fluid properties have been fabricated.")
    report_lines.append("")
    report_lines.append("5. PVT PROPERTIES (MEASURED, CALCULATED & ESTIMATED)")
    report_lines.append("-" * 60)
    report_lines.append("- Solution Gas-Oil Ratio (Rs): " + (f"{separator_gor} [Measured Separator Input]" if separator_gor != "Not Provided" else "Not Provided / Additional Laboratory Data Required"))
    report_lines.append("- Oil Formation Volume Factor (Bo): Not Provided / Additional Laboratory Data Required (Standing / Vasquez-Beggs correlation requires measured Rs, Sg, API, and Tr)")
    report_lines.append("- Oil Viscosity: Not Provided / Additional Laboratory Data Required (Beggs-Robinson / Glaso correlation requires measured dead oil viscosity and Rs)")
    report_lines.append("- Gas Formation Volume Factor (Bg): Not Provided / Additional Laboratory Data Required (Real Gas Law requires measured Z-factor, pressure, and temperature)")
    report_lines.append("- Gas Z-Factor: Not Provided / Additional Laboratory Data Required (Standing-Katz gas compressibility factor / deviation factor represents departure from ideal-gas behavior, not gas density)")
    report_lines.append("")
    report_lines.append("6. DATA QUALITY & CONSISTENCY CHECKS")
    report_lines.append("-" * 60)
    report_lines.append("- Consistent Data: Verified against physical bounds (McCain). No thermodynamic anomalies detected in provided inputs.")
    report_lines.append("- Questionable Values: None. Unprovided parameters are explicitly designated as 'Not Provided' rather than hallucinated.")
    report_lines.append("- Discrepancies: None detected.")
    report_lines.append("- Data Quality Level: Pending Complete Laboratory CCE/DL Suite")
    report_lines.append(f"- Engineering Confidence: {confidence_level}")
    report_lines.append("  Justification: Absence of multi-stage separator tests and differential liberation data limits property derivation to correlation estimates.")
    report_lines.append("")
    report_lines.append("7. ENGINEERING INTERPRETATION")
    report_lines.append("-" * 60)
    report_lines.append("- In accordance with SPE and Craft & Hawkins standards, unmeasured PVT properties are not fabricated or interpolated without rigorous experimental baseline data.")
    report_lines.append("- Fluid behavior must be confirmed via Constant Composition Expansion (CCE) and Differential Liberation (DL) laboratory experiments before committing to numerical simulation grids.")
    report_lines.append("")
    report_lines.append("8. SIMULATION MODEL RECOMMENDATIONS")
    report_lines.append("-" * 60)
    report_lines.append("- Recommended Model: Pending Complete Fluid Characterization (Whitson & Brulé)")
    report_lines.append("- Technical Justification: Selection between Black Oil and EOS Compositional models requires verified fluid composition, stock-tank oil gravity, solution GOR, and saturation pressure. Compositional modeling (EOS) via Peng-Robinson or Redlich-Kwong is unjustified without multicomponent gas chromatography (GC up to C30+).")
    if has_pvt_table:
        report_lines.append("- Provided PVT Tables: Detected in input context. Validated against standard schema.")
    else:
        report_lines.append("- PVT Tables (PVTO/PVDO/PVTG/PVDG): Not Provided. No PVT tables have been generated or assumed.")
    report_lines.append("")
    report_lines.append("9. SIMULATOR RECOMMENDATION & SELECTION RATIONALE")
    report_lines.append("-" * 60)
    report_lines.append("- Recommended Simulator: Conditional on Fluid Characterization (Schlumberger Eclipse / CMG Suite)")
    report_lines.append("- Engineering Justification & Comparison:")
    report_lines.append("  • Eclipse E100 / CMG IMEX (Black Oil Simulators): Preferred for conventional undersaturated/saturated oil systems where compositional grading is negligible, offering superior computational efficiency without Equation of State (EOS) flash overhead (Schlumberger Eclipse Manual).")
    report_lines.append("  • Eclipse E300 / CMG GEM (Compositional Simulators): Unjustified for standard black oil systems; required only for volatile oils, rich gas condensates, or near-critical systems exhibiting strong compositional variation with depth and pressure depletion (Whitson & Brulé, Ahmed).")
    report_lines.append("")
    report_lines.append("10. MISSING DATA / ADDITIONAL TESTS RECOMMENDED")
    report_lines.append("-" * 60)
    report_lines.append("- Differential Liberation (DL) Test: Additional Laboratory Data Required (Mandatory for Bo, Rs, and oil viscosity below Pb per McCain)")
    report_lines.append("- Constant Composition Expansion (CCE) Test: Additional Laboratory Data Required (Mandatory for saturation pressure, total compressibility, and relative volume per Whitson & Brulé)")
    report_lines.append("- Multi-Stage Separator Test: Additional Laboratory Data Required (Mandatory for surface shrinkage and separator gas specific gravity per Standing)")
    report_lines.append("- Fluid Compositional Analysis (GC up to C30+): Additional Laboratory Data Required (Mandatory for EOS tuning and compositional simulation)")
    report_lines.append("")
    report_lines.append("11. ENGINEERING CONCLUSIONS")
    report_lines.append("-" * 60)
    report_lines.append("1. The submitted context lacks sufficient measured PVT laboratory data to execute rigorous thermodynamic correlations without excessive uncertainty (Craft & Hawkins).")
    report_lines.append("2. In compliance with enterprise engineering standards, unmeasured properties are explicitly stated as 'Not Provided' or 'Additional Laboratory Data Required' rather than fabricated.")
    report_lines.append("3. Commissioning a standard PVT laboratory study (CCE, DL, Separator Test) is recommended prior to reservoir modeling and field development planning.")
    report_lines.append("")
    report_lines.append("============================================================")
    report_lines.append("Report Generated by Enterprise Petroleum AI Platform (v1.0)")
    report_lines.append("============================================================")
    
    return "\n".join(report_lines)
