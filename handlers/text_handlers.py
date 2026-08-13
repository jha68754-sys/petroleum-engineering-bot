"""
Text command handlers for the Petroleum Engineering Bot.

Handles all text-based commands: /classify, /calc, /estimate, /convert,
/plot, /check, /pvto, /pvdo, /pvtg, /pvdg, /export_sim, /eclipse,
/cmg, /report, /glossary, /reset, /start, /analyze.

Each handler receives the Telegram message dict and the TelegramService
instance, and returns a response string (and optionally file bytes).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from constants import (
    START_MESSAGE,
    HELP_MESSAGE,
    SURFACE_SEPARATOR_ANSWER,
)
from handlers.command_registry import registry
from services.pvt_engine import (
    classify_fluid,
    validate_pvt_trend,
    resolve_relationship_key,
    run_exact_calculation,
    run_correlation,
    run_unit_conversion,
    generate_simulation_skeleton,
    export_sim_decision,
)
from services.calculation_engine import parse_kv_args
from services.visualization import format_plot_response, generate_pvt_plot
from services.production_engine import IPREngine, MODEL_DISPLAY
from services import vlp_engine
from logging_config import get_logger


def _fmt_loss(value: float) -> str:
    """Format a pressure-loss component so tiny (but real) losses are never
    displayed as 0.0: use more decimals when the value is < 1 psi so the
    user can distinguish 'physically negligible' from 'not computed'."""
    v = abs(value) if value is not None else 0.0
    if v >= 1.0:
        return f"{value:.1f}"
    if v >= 0.01:
        return f"{value:.2f}"
    if v > 0.0:
        return f"{value:.4f}"
    return "0.0"

logger = get_logger(__name__)


# ═══════════════════════════════════════════════════════════════════════
#  COMMAND HANDLERS
# ═══════════════════════════════════════════════════════════════════════

@registry.register("start")
def handle_start(message: Dict[str, Any], tg) -> Tuple[str, Optional[bytes], Optional[str]]:
    """الترحيب بالمستخدم باللغة العربية."""
    # Ensure fresh import to get the latest message
    import constants
    return constants.START_MESSAGE, None, None


@registry.register("help")
def handle_help(message: Dict[str, Any], tg) -> Tuple[str, Optional[bytes], Optional[str]]:
    """عرض قائمة الأوامر الهندسية التفصيلية."""
    from constants import HELP_MESSAGE
    return HELP_MESSAGE, None, None


@registry.register("reset", aliases=["clear", "clear_context"])
def handle_reset(message: Dict[str, Any], tg) -> Tuple[str, Optional[bytes], Optional[str]]:
    """Handle /reset command - clear file context."""
    chat_id = message.get("chat", {}).get("id", "")
    # Clear context via global state
    from main import FILE_CONTEXT, IMAGE_CONTEXT, _delete_temp_image
    if chat_id in FILE_CONTEXT:
        del FILE_CONTEXT[chat_id]
    if chat_id in IMAGE_CONTEXT:
        _delete_temp_image(IMAGE_CONTEXT[chat_id])
        del IMAGE_CONTEXT[chat_id]
    return "Context cleared. Upload a new file or ask a question.", None, None


@registry.register("classify", aliases=["classify_fluid"])
def handle_classify(message: Dict[str, Any], tg) -> Tuple[str, Optional[bytes], Optional[str]]:
    """Handle /classify gor=<val> api=<val> [no_liquid=1] command."""
    text = message.get("text", "")
    # Parse after /classify
    args_str = text.split(None, 1)[1] if " " in text else ""
    kwargs = parse_kv_args(args_str)

    no_liquid = bool(kwargs.get("no_liquid") or kwargs.get("dry_gas"))
    gor = kwargs.get("gor")
    api = kwargs.get("api")

    if not no_liquid and (gor is None or api is None):
        return (
            "Usage: /classify gor=<value> api=<value> [no_liquid=1]\n\n"
            "Examples:\n"
            "  /classify gor=500 api=35\n"
            "  /classify gor=15000 api=55\n"
            "  /classify gor=800 api=30\n"
            "  /classify no_liquid=1   (dry gas -- no stock-tank liquid produced;\n"
            "                          GOR/API are not meaningful for this fluid type)"
        ), None, None

    result = classify_fluid(gor or 0.0, api or 0.0, no_liquid=no_liquid)
    output = [
        "Fluid Classification Result",
        "=" * 50,
        f"Input: GOR = {gor if gor is not None else 'n/a'} scf/STB, "
        f"API = {api if api is not None else 'n/a'} deg API"
        + (" (no_liquid override)" if no_liquid else ""),
        "",
        f"Type: {result['type_ar']} ({result['type_en']})",
        f"Behavior: {result['behavior']}",
    ]
    if result["is_near_critical"]:
        output.append("WARNING: Near-critical behavior likely.")
        output.append("Recommendation: Compositional EOS simulation required.")
    if result.get("boundary_note"):
        output.append("")
        output.append(result["boundary_note"])
    output.append("")
    output.append("Use /pvto, /pvtg, /pvdg for simulation table requirements.")

    return "\n".join(output), None, None


@registry.register("calc", aliases=["calculate", "formula"])
def handle_calc(message: Dict[str, Any], tg) -> Tuple[str, Optional[bytes], Optional[str]]:
    """Handle /calc <type> key=value ... command."""
    text = message.get("text", "")
    parts = text.split(None, 2)
    if len(parts) < 2:
        return (
            "Usage: /calc <type> key=value ...\n\n"
            "Types: api, ooip, ogip, darcy, recovery_factor,\n"
            "  productivity_index, hydrostatic, mud_weight_required,\n"
            "  ecd, water_cut, wor, gor_produced, npv\n\n"
            "Example: /calc ooip area=500 h=50 phi=0.2 sw=0.3 bo=1.3"
        ), None, None

    formula_key = parts[1]
    args_str = parts[2] if len(parts) > 2 else ""

    if formula_key.lower() == "vlp":
        # Deterministic Production VLP engine (Phase 2: VLP only); handled
        # separately from EXACT_FORMULAS so that Beggs-Brill guardrails and
        # curve/plot generation apply. Same parse_kv_args caution as IPR:
        # string keys (plot=) are kept before numeric parsing.
        text, png, caption = handle_calc_vlp(
            {"text": "/vlp " + args_str}, tg
        )
        return text, png, caption

    if formula_key.lower() == "ipr":
        # Deterministic Production IPR engine (Phase 1); handled separately
        # from EXACT_FORMULAS so that IPR model selection/guardrails apply.
        # NOTE: do NOT pre-parse with parse_kv_args — handle_calc_ipr keeps
        # the string keys (model=, plot=) that the generic numeric parser
        # would otherwise drop.
        text, png, caption = handle_calc_ipr(
            {"text": "/ipr " + args_str}, tg
        )
        return text, png, caption

    kwargs = parse_kv_args(args_str)

    result = run_exact_calculation(formula_key, kwargs)
    return result, None, None


# ═══════════════════════════════════════════════════════════════════════
#  /calc ipr  —  Deterministic IPR Engine (Phase 1: IPR only)
# ═══════════════════════════════════════════════════════════════════════

_IPR_USAGE = (
    "Usage: /calc ipr [model=auto|linear|vogel|composite] [plot=1] key=value ...\n\n"
    "All pressures in psia (psi); rates in STB/day; J in STB/day/psi.\n\n"
    "Saturated reservoir (Pr <= Pb) or no Pb given:\n"
    "  /calc ipr pr=3000 qmax=1500 pwf=1200\n"
    "  /calc ipr model=vogel pr=3000 q_test=600 pwf_test=1500\n\n"
    "Undersaturated, single-phase inflow (Pwf >= Pb):\n"
    "  /calc ipr model=linear pr=3000 j=1.5 pwf=2000\n"
    "  /calc ipr model=linear pr=3000 q_test=900 pwf_test=2400\n\n"
    "Undersaturated reservoir, inflow crosses bubble point (Composite IPR):\n"
    "  /calc ipr model=composite pr=3000 pb=2200 q_test=900 pwf_test=2400 pwf=1200\n\n"
    "Automatic model selection by reservoir conditions:\n"
    "  /calc ipr model=auto pr=3000 pb=2200 q_test=900 pwf_test=2400 pwf=1200\n\n"
    "Add plot=1 for a calculated IPR model plot:\n"
    "  /calc ipr model=auto pr=3000 pb=2200 q_test=900 pwf_test=2400 plot=1"
)

_IPR_REQUIRED_HINTS = {
    "pr": "Reservoir pressure Pr (psia) — defines the start of the IPR curve",
    "pb": "Bubble-point pressure Pb (psia) — needed to split linear/Vogel regimes",
    "qmax": "Maximum Vogel rate qmax (STB/day) — anchors the Vogel curve",
    "j": "Productivity index J (STB/day/psi) — anchors the linear inflow line",
    "q_test": "Measured test rate q_test (STB/day) — calibrates the IPR slope",
    "pwf_test": "Test flowing pressure Pwf_test (psia) — pairs with q_test",
    "pwf": "Requested flowing pressure Pwf (psia) — rate is evaluated at this pressure",
    "model": "IPR model: auto (default), linear, vogel, or composite",
    "plot": "Set plot=1 to also return the calculated IPR model plot as PNG",
}


def _ipr_missing_message(missing: List[str]) -> str:
    """Engineering Data Requirement message for insufficient IPR data."""
    lines = ["Engineering Data Requirement — insufficient data for IPR calculation.", ""]
    lines.append("Missing parameters:")
    for m in missing:
        lines.append(f"  • {m}: {_IPR_REQUIRED_HINTS.get(m, '')}")
    lines.append("")
    lines.append("Units: pressures in psia (psi), rates in STB/day, J in STB/day/psi.")
    lines.append("")
    lines.append("Example:")
    lines.append("  /calc ipr model=auto pr=3000 pb=2200 q_test=900 pwf_test=2400 pwf=1200")
    lines.append("  /calc ipr model=vogel pr=3000 qmax=1500 pwf=1200")
    return "\n".join(lines)


def _ipr_result_lines(model: str, reason: str, pr: float,
                      pwf: Optional[float], q: Optional[float],
                      j: Optional[float], qmax: Optional[float],
                      pb: Optional[float], qb: Optional[float],
                      qo_max: Optional[float],
                      test: Optional[Tuple[float, float]]) -> List[str]:
    lines = [
        "IPR Calculation Result",
        "=" * 50,
        f"Selected model: {MODEL_DISPLAY.get(model, model)}",
        f"Reason: {reason}",
        "",
        f"Pr = {pr:g} psia",
    ]
    if pb is not None:
        lines.append(f"Pb = {pb:g} psia")
    if test is not None:
        lines.append(f"Test point (measured): q_test = {test[0]:g} STB/day @ Pwf_test = {test[1]:g} psia")
    if j is not None:
        lines.append(f"Productivity index J = {j:g} STB/day/psi")
    if qmax is not None:
        lines.append(f"qmax = {qmax:g} STB/day")
    if qb is not None:
        lines.append(f"qb at Pb = {qb:g} STB/day")
    if qo_max is not None:
        lines.append(f"qo_max (AOF, model extrapolation) = {qo_max:g} STB/day")
    lines.append("")
    if pwf is not None and q is not None:
        lines.append(f"Rate at Pwf = {pwf:g} psia:  q = {q:g} STB/day")
    else:
        lines.append("No Pwf requested — full curve parameters only.")
    lines.append("")
    lines.append("NOTE: Results are CALCULATED (empirical correlation or model-based),")
    lines.append("not measured data. Use a backpressure/single-point test to validate.")
    return lines


@registry.register("ipr")
def handle_calc_ipr(message: Dict[str, Any], tg) -> Tuple[str, Optional[bytes], Optional[str]]:
    """Handle /calc ipr [model=...] key=value ... — deterministic IPR engine.

    Reachable via /calc ipr (dispatched through handle_calc) or directly
    as /ipr with the same key=value syntax.
    """
    text = message.get("text", "")
    # Both "/calc ipr model=..." and "/ipr model=..." parse the same way:
    # strip the command prefix (first token) and take everything after it.
    first_space = text.find(" ")
    args_str = text[first_space + 1:] if first_space >= 0 else ""
    # parse_kv_args silently drops non-numeric values (model=, plot=), so
    # parse IPR-specific string keys first, then numeric kv parsing.
    kwargs: Dict[str, Any] = {}
    if args_str and args_str.strip():
        for _part in args_str.split():
            if "=" not in _part:
                continue
            _key, _, _val = _part.partition("=")
            _key, _val = _key.strip().lower(), _val.strip()
            if _key in ("model", "plot"):
                kwargs[_key] = _val
                continue
    _numeric = parse_kv_args(args_str)
    _numeric.update(kwargs)
    kwargs = _numeric
    engine = IPREngine()

    model_req = (kwargs.get("model") or "auto").lower()
    if model_req not in ("auto", "linear", "vogel", "composite"):
        return ("Error: model must be one of auto, linear, vogel, composite.\n\n" + _IPR_USAGE), None, None

    pr = kwargs.get("pr")
    pb = kwargs.get("pb")
    pwf = kwargs.get("pwf")
    qmax = kwargs.get("qmax")
    j = kwargs.get("j")
    q_test = kwargs.get("q_test")
    pwf_test = kwargs.get("pwf_test")

    # --- Collect known values & check missing data per requested model ---
    required: List[str] = []
    if pr is None:
        required.append("pr")
    if model_req in ("vogel",) and qmax is None and (q_test is None or pwf_test is None):
        required += ["qmax", "q_test", "pwf_test"]
    if model_req in ("linear",) and j is None and (q_test is None or pwf_test is None):
        required += ["j", "q_test", "pwf_test"]
    if model_req in ("composite",) and (q_test is None or pwf_test is None):
        required += ["q_test", "pwf_test"]
    if model_req == "auto" and (q_test is None or pwf_test is None):
        required += ["q_test", "pwf_test"]
    if model_req in ("composite", "auto") and pb is None and pr is not None:
        required.append("pb")
    if required:
        return _ipr_missing_message(required), None, None

    try:
        pr = float(pr)
        pb = float(pb) if pb is not None else None
        pwf = float(pwf) if pwf is not None else None
        qmax = float(qmax) if qmax is not None else None
        j = float(j) if j is not None else None
        q_test = float(q_test) if q_test is not None else None
        pwf_test = float(pwf_test) if pwf_test is not None else None
    except (TypeError, ValueError):
        return "Error: all parameter values must be numeric.\n\n" + _IPR_USAGE, None, None

    if q_test is not None and pwf_test is not None:
        if pwf_test >= pr:
            return (
                "Error: test flowing pressure Pwf_test must be below reservoir "
                "pressure Pr to calibrate the IPR."
            ), None, None
        if q_test <= 0 or pwf_test < 0:
            return (
                "Error: invalid test point — q_test must be > 0 STB/day and "
                "Pwf_test >= 0 psia."
            ), None, None

    # --- Effective model selection (deterministic) ---
    effective_model = model_req
    if model_req == "auto":
        effective_model, reason = engine.select_model(pr, pb, pwf)
    elif model_req == "vogel":
        if pb is not None and pr > pb and pwf is not None and pwf < pb:
            return (
                "Error: requested Pwf is below Pb, so linear/Vogel-only treatment is "
                "outside the Vogel model assumptions. Use model=composite (or model=auto) "
                "for the inflow path that crosses the bubble point."
            ), None, None
        reason = ("Vogel IPR requested explicitly (saturated-oil treatment). "
                  "Applicable only for Pr <= Pb or calibration from a test point.")
    elif model_req == "linear":
        if pb is not None and pr > pb and pwf is not None and pwf < pb:
            return (
                "Error: requested Pwf is below Pb; a single-phase linear model is not "
                "applicable. Use model=composite (or model=auto)."
            ), None, None
        reason = ("Linear PI requested explicitly. Valid only while inflow stays in the "
                  "single-phase (undersaturated) regime, i.e. Pwf >= Pb.")
    else:  # composite
        if pb is None or pr <= pb:
            return (
                "Error: Composite IPR requires Pr > Pb with the inflow path crossing Pb. "
                "For a saturated reservoir (Pr <= Pb) use model=vogel."
            ), None, None
        reason = (
            "Composite IPR requested: the inflow path is treated linear above Pb "
            "and with a Vogel-shaped curve below Pb, joined continuously at Pb."
        )

    # --- Anchor derivations ---
    derived_qmax: Optional[float] = None
    derived_j: Optional[float] = None
    derived_j_star: Optional[float] = None
    if effective_model == "vogel":
        if qmax is None:
            qmax = engine.vogel_qmax_from_test(pr, pwf_test, q_test)
            derived_qmax = qmax
    elif effective_model == "linear":
        if j is None:
            j = engine.linear_j(q_test, pr, pwf_test)
            derived_j = j
    else:  # composite
        derived_j_star = engine.linear_j(q_test, pr, pwf_test)

    # --- Point evaluation ---
    q: Optional[float] = None
    try:
        if pwf is not None:
            if effective_model == "vogel":
                q = engine.vogel_q(pr, qmax, pwf)
            elif effective_model == "linear":
                q = engine.linear_q(pr, j, pwf)
            else:
                q = engine.composite_q(pr, pb, derived_j_star, pwf)

        qb, qo_max = (None, None)
        if effective_model == "composite":
            qb, qo_max = engine.composite_segments(pr, pb, derived_j_star)
    except ValueError as _err:
        # Hard guardrails: PHYSICALLY_INVALID / INSUFFICIENT_DATA messages.
        _msg = str(_err)
        if "PHYSICALLY_INVALID" in _msg:
            return ("Engineering Guardrail — inputs rejected as physically "
                    "invalid.\n" + _msg), None, None
        return ("Engineering Guardrail — inputs rejected.\n" + _msg), None, None
    except Exception as _err:
        return (f"IPR calculation error: {_err}. Please check your inputs."), None, None

    test = (q_test, pwf_test) if q_test is not None else None
    out = _ipr_result_lines(
        effective_model, reason, pr, pwf, q, j, qmax, pb, qb, qo_max, test
    )

    # --- Optional calculated-IPR plot ---
    png: Optional[bytes] = None
    if bool(kwargs.get("plot")):
        # PVT_PLOT_RULES "ipr_plot" defines x_axis = rate, y_axis = pressure,
        # so pass (x=rates, y=pressures) to render the customary IPR orientation.
        ps_curve = engine._curve_pressures(pr, 10, include_pb=(pb is not None), pb=pb)
        qs_curve = engine.build_curve(
            effective_model, pr, pwf=pwf, pb=pb,
            j=j, j_star=derived_j_star, qmax=qmax,
        )
        well_name = f"Calculated IPR Model — {effective_model}"
        if pb is not None:
            well_name += f" (Pb = {pb:g})"
        png = generate_pvt_plot(
            "ipr_plot", qs_curve, ps_curve, pb,
            well_name, labels=[f"Calculated — {effective_model}"],
        )
        if png is None:
            out.append("")
            out.append("NOTE: could not generate the calculated IPR plot.")
        else:
            out.append("")
            out.append("Calculated IPR Model Plot attached (rate on X, pressure on Y).")
            out.append("This is a model-generated curve, not measured data.")

        return "\n".join(out), png, None


# ═══════════════════════════════════════════════════════════════════════
#  /calc vlp  —  Deterministic VLP Engine (Phase 2: VLP only)
# ═══════════════════════════════════════════════════════════════════════

_VLP_USAGE = (
    "Usage: /calc vlp [plot=1] key=value ...\n\n"
    "Pressures in psia (psi); rates in STB/day; depths in ft; diameters in in;\n"
    "temperatures in degF; viscosities in cP.\n\n"
    "Required: thp tvd id q gor api gamma_g mu_l bo rs t_wh geothermal\n"
    "Optional: wc (default 0), q_w (alternative to wc), gamma_w (1.07),\n"
    "  bw (1.01), z (1.0), sigma (30 dyne/cm), segments (80)\n\n"
    "Single-rate example:\n"
    "  /calc vlp thp=100 tvd=8000 id=1.995 q=3000 gor=1000 rs=600 api=35\n"
    "    gamma_g=0.65 mu_l=1 bo=1.4 t_wh=120 geothermal=1.5\n\n"
    "Calculated VLP curve (Pwf vs rate from q_min to q_max):\n"
    "  /calc vlp thp=100 tvd=8000 id=1.995 q_min=0 q_max=8000 gor=1000 rs=600\n"
    "    api=35 gamma_g=0.65 mu_l=1 bo=1.4 t_wh=120 geothermal=1.5 plot=1"
)

_VLP_REQUIRED_HINTS = {
    "thp": "Wellhead (tubing-head) pressure, psia",
    "tvd": "True vertical depth, ft",
    "id": "Tubing inside diameter, in",
    "q": "Oil production rate, STB/day (use q_w or wc for water)",
    "q_min": "Minimum rate for the VLP curve sweep, STB/day",
    "q_max": "Maximum rate for the VLP curve sweep, STB/day",
    "gor": "Produced GOR, scf/STB",
    "rs": "Solution GOR at the average pressure, scf/STB",
    "api": "Oil API gravity",
    "gamma_g": "Gas specific gravity (air = 1)",
    "mu_l": "Liquid (oil) viscosity, cP",
    "bo": "Oil formation volume factor, rb/STB",
    "t_wh": "Wellhead temperature, degF",
    "geothermal": "Geothermal gradient, degF/100 ft",
    "wc": "Water cut, fraction 0..1 (default 0)",
    "q_w": "Water rate, STB/day (alternative to wc)",
    "gamma_w": "Water specific gravity (default 1.07)",
    "bw": "Water FVF, rb/STB (default 1.01)",
    "z": "Gas compressibility factor (default 1.0)",
    "sigma": "Surface tension, dyne/cm (default 30)",
    "segments": "Number of traverse segments (default 80)",
    "plot": "Set plot=1 to also return the calculated VLP plot as PNG",
}


def _vlp_missing_message(missing: List[str]) -> str:
    """Engineering Data Requirement message for insufficient VLP data."""
    lines = ["Engineering Data Requirement — insufficient data for VLP calculation.", ""]
    lines.append("Missing parameters:")
    for m in missing:
        lines.append(f"  \u2022 {m}: {_VLP_REQUIRED_HINTS.get(m, '')}")
    lines.append("")
    lines.append("Units: pressures in psia (psi), rates in STB/day, depths in ft,\n"
                 "  diameters in in, temperatures in degF, viscosity in cP.")
    lines.append("")
    lines.append("Example:")
    lines.append("  /calc vlp thp=100 tvd=8000 id=1.995 q=3000 gor=1000 rs=600\n"
                 "    api=35 gamma_g=0.65 mu_l=1 bo=1.4 t_wh=120 geothermal=1.5")
    return "\n".join(lines)


def _vlp_result_lines(thp: float, tvd: float, q_o: float, q_w: float,
                      result) -> List[str]:
    """Format a single-rate VLP engine result for Telegram."""
    lines = [
        "VLP Calculation Result",
        "=" * 50,
        f"Method: {vlp_engine.MODEL_DISPLAY['beggs_brill']}",
        f"Segments: {result.segments}",
        "",
        f"Wellhead pressure THP = {thp:g} psia",
        f"TVD = {tvd:g} ft",
        f"Rate: qo = {q_o:g} STB/day, qw = {q_w:g} STB/day",
        f"Total = {q_o + q_w:g} STB/day",
        "",
        f"Required BHP (Pwf) = {result.pwf:g} psia",
    ]
    comps = result.components or {}
    lines.append("")
    lines.append("Pressure-loss components (wellhead -> bottomhole):")
    lines.append(f"  \u2022 Hydrostatic/elevation: {comps.get('elevation', 0.0):.1f} psi")
    lines.append(f"  \u2022 Friction: {_fmt_loss(comps.get('friction', 0.0))} psi")
    lines.append(f"  \u2022 Acceleration: {_fmt_loss(comps.get('acceleration', 0.0))} psi")
    if result.flow_pattern_counts:
        lines.append("")
        lines.append("Flow-pattern distribution along the tubing (Beggs-Brill):")
        for pat, cnt in sorted(result.flow_pattern_counts.items()):
            lines.append(f"  \u2022 {pat}: {cnt} segments")
    if result.warnings:
        lines.append("")
        lines.append("Warnings:")
        for w in result.warnings:
            lines.append(f"  \u2022 {w}")
    if result.limitations:
        lines.append("")
        lines.append("Correlation limitations:")
        for lim in result.limitations:
            lines.append(f"  \u2022 {lim}")
    lines.append("")
    lines.append("NOTE: Results are CALCULATED (Beggs-Brill 1973 correlation with a\n"
                 "segmented midpoint traverse), not measured data.")
    return lines


@registry.register("vlp")
def handle_calc_vlp(message: Dict[str, Any], tg) -> Tuple[str, Optional[bytes], Optional[str]]:
    """Handle /calc vlp [plot=1] key=value ... — deterministic VLP engine.

    Reachable via /calc vlp (dispatched through handle_calc) or directly
    as /vlp with the same key=value syntax.
    """
    text = message.get("text", "")
    first_space = text.find(" ")
    args_str = text[first_space + 1:] if first_space >= 0 else ""
    # parse_kv_args silently drops non-numeric values (plot=), so keep
    # string keys first, then numeric kv parsing (same as IPR handler).
    kwargs: Dict[str, Any] = {}
    if args_str and args_str.strip():
        for _part in args_str.split():
            if "=" not in _part:
                continue
            _key, _, _val = _part.partition("=")
            _key, _val = _key.strip().lower(), _val.strip()
            if _key in ("plot",):
                kwargs[_key] = _val
                continue
    _numeric = parse_kv_args(args_str)
    _numeric.update(kwargs)
    kwargs = _numeric

    # --- Hard validation (guardrails) ---
    err = vlp_engine.validate_inputs(kwargs)
    if err is not None:
        return ("Engineering Guardrail — inputs rejected as physically "
                "invalid.\n" + err.message), None, None

    # --- Curve-sweep mode vs single-rate mode ---
    q_min = kwargs.get("q_min")
    q_max = kwargs.get("q_max")
    wc = kwargs.get("wc") if kwargs.get("wc") is not None else 0.0
    q_w = kwargs.get("q_w")

    # --- Engineering Data Requirement ---
    curve_mode = q_min is not None or q_max is not None
    if curve_mode:
        # Curve mode replaces the single-rate "q" requirement with a sweep.
        required = [k for k in vlp_engine.missing_inputs(kwargs, "beggs_brill")
                    if k != "q"]
        if q_min is None:
            required.append("q_min")
        if q_max is None:
            required.append("q_max")
        if q_min is not None and q_max is not None and q_min > q_max:
            return ("Error: q_min must be <= q_max for the VLP curve sweep."), None, None
    else:
        required = vlp_engine.missing_inputs(kwargs, "beggs_brill")
        if kwargs.get("q") is None:
            required.append("q")
    # Deduplicate while preserving order.
    required = list(dict.fromkeys(required))
    if required:
        return _vlp_missing_message(required), None, None

    # --- Float conversion ---
    try:
        floats = {}
        for _k in ("thp", "tvd", "id", "q", "gor", "api", "gamma_g", "mu_l",
                   "bo", "rs", "t_wh", "geothermal", "wc", "q_w", "gamma_w",
                   "bw", "z", "sigma", "segments", "q_min", "q_max"):
            _v = kwargs.get(_k)
            if _v is not None:
                floats[_k] = float(_v)
    except (TypeError, ValueError):
        return ("Error: all parameter values must be numeric.\n\n" + _VLP_USAGE), None, None

    if curve_mode:
        # --- Calculated VLP curve + plot ---
        wc = floats.get("wc", 0.0)
        # Sweep total rate in 20 points; the zero-rate point is resolved
        # with the static hydrostatic engine (multiphase friction is
        # undefined at zero flow).
        q_min_v, q_max_v = floats["q_min"], floats["q_max"]
        n_pts = 20
        if q_min_v == q_max_v:
            qs, ps = [q_min_v], []
            if q_min_v <= 0.0:
                ps.append(vlp_engine.static_gradient(
                    floats["thp"], floats["tvd"], floats["t_wh"],
                    floats.get("geothermal", 1.5), floats["gamma_g"],
                    floats.get("gamma_w", 1.07), floats.get("z", 1.0)).pwf)
            else:
                q_o_s, q_w_s = q_min_v * (1.0 - wc), q_min_v * wc
                ps.append(vlp_engine.traverse(
                    floats["thp"], floats["tvd"], q_o_s, q_w_s,
                    floats["gor"], floats["bo"], floats.get("bw", 1.01),
                    floats.get("z", 1.0), floats["gamma_g"],
                    floats.get("gamma_w", 1.07), floats["mu_l"],
                    floats["api"], wc, floats["id"], floats["rs"],
                    floats["t_wh"], floats.get("geothermal", 1.5),
                    n_segments=int(floats.get("segments", 80))).pwf)
        else:
            qs, ps = [], []
            for i in range(n_pts):
                q_total = q_min_v + (q_max_v - q_min_v) * i / (n_pts - 1)
                if q_total <= 0.0:
                    qs.append(q_total)
                    ps.append(vlp_engine.static_gradient(
                        floats["thp"], floats["tvd"], floats["t_wh"],
                        floats.get("geothermal", 1.5), floats["gamma_g"],
                        floats.get("gamma_w", 1.07),
                        floats.get("z", 1.0)).pwf)
                else:
                    q_o_s, q_w_s = q_total * (1.0 - wc), q_total * wc
                    qs.append(q_total)
                    ps.append(vlp_engine.traverse(
                        floats["thp"], floats["tvd"], q_o_s, q_w_s,
                        floats["gor"], floats["bo"], floats.get("bw", 1.01),
                        floats.get("z", 1.0), floats["gamma_g"],
                        floats.get("gamma_w", 1.07), floats["mu_l"],
                        floats["api"], wc, floats["id"], floats["rs"],
                        floats["t_wh"], floats.get("geothermal", 1.5),
                        n_segments=int(floats.get("segments", 80))).pwf)
        if not qs:
            return "VLP curve error: empty rate sweep.", None, None
        out = [
            "Calculated VLP Curve",
            "=" * 50,
            f"Method: {vlp_engine.MODEL_DISPLAY['beggs_brill']}",
            f"THP = {floats['thp']:g} psia  |  TVD = {floats['tvd']:g} ft  |  "
            f"ID = {floats['id']:g} in",
            f"GOR = {floats['gor']:g} scf/STB (Rs = {floats['rs']:g})  |  "
            f"wc = {wc:.2f}",
            f"Sweep: q = {floats['q_min']:g} .. {floats['q_max']:g} STB/day "
            f"(20 points, segmented traverse)",
            "",
            "Rate (STB/day) -> Required Pwf (psia):",
        ]
        for _q, _p in zip(qs, ps):
            out.append(f"  q = {_q:g}  ->  Pwf = {_p:.1f}")
        png = None
        if bool(kwargs.get("plot")):
            png = generate_pvt_plot(
                "vlp_plot", qs, ps, None,
                f"Calculated VLP — THP {floats['thp']:g} psia",
                labels=["Calculated — Beggs-Brill (1973)"],
            )
            if png is None:
                out.append("")
                out.append("NOTE: could not generate the calculated VLP plot.")
            else:
                out.append("")
                out.append("Calculated VLP Plot attached (rate on X, required BHP on Y).")
                out.append("This is a model-generated curve, not measured data.")
        return "\n".join(out), png, None

    # --- Single-rate mode ---
    wc = floats.get("wc", 0.0)
    q_o = floats["q"] * (1.0 - wc) if q_w is None else floats["q"]
    q_w = q_w if q_w is not None else floats["q"] * wc
    try:
        result = vlp_engine.traverse(
            floats["thp"], floats["tvd"], q_o, q_w, floats["gor"],
            floats["bo"], floats.get("bw", 1.01), floats.get("z", 1.0),
            floats["gamma_g"], floats.get("gamma_w", 1.07), floats["mu_l"],
            floats["api"], wc, floats["id"], floats["rs"], floats["t_wh"],
            floats.get("geothermal", 1.5),
            sigma=floats.get("sigma", 30.0),
            n_segments=int(floats.get("segments", 80)),
        )
    except ValueError as _e:
        _msg = str(_e)
        if "PHYSICALLY_INVALID" in _msg:
            return ("Engineering Guardrail — inputs rejected as physically "
                    "invalid.\n" + _msg), None, None
        return ("Engineering Guardrail — inputs rejected.\n" + _msg), None, None
    except Exception as _e:
        return f"VLP calculation error: {_e}. Please check your inputs.", None, None

    out = _vlp_result_lines(floats["thp"], floats["tvd"], q_o, q_w, result)

    png = None
    if bool(kwargs.get("plot")):
        png = generate_pvt_plot(
            "vlp_plot", [q_o + q_w], [result.pwf], None,
            f"Calculated VLP — single rate {q_o + q_w:g} STB/day",
            labels=["Calculated — Beggs-Brill (1973)"],
        )
        if png is None:
            out.append("")
            out.append("NOTE: could not generate the calculated VLP plot.")
        else:
            out.append("")
            out.append("Calculated VLP Plot attached (rate on X, required BHP on Y).")
            out.append("This is a model-generated curve, not measured data.")
    return "\n".join(out), png, None


@registry.register("estimate", aliases=["corr", "correlation"])
def handle_estimate(message: Dict[str, Any], tg) -> Tuple[str, Optional[bytes], Optional[str]]:
    """Handle /estimate <type> key=value ... command."""
    text = message.get("text", "")
    parts = text.split(None, 2)
    if len(parts) < 2:
        return (
            "Usage: /estimate <type> key=value ...\n\n"
            "Types: pb_standing, rs_standing, pb_vasquez_beggs,\n"
            "  rs_vasquez_beggs, bo_standing, z_standing_katz\n\n"
            "Example: /estimate pb_standing rs=650 gas_sg=0.75 tres=180 api=35"
        ), None, None

    corr_key = parts[1]
    args_str = parts[2] if len(parts) > 2 else ""
    kwargs = parse_kv_args(args_str)

    result = run_correlation(corr_key, kwargs)
    return result, None, None


@registry.register("convert", aliases=["unit", "units"])
def handle_convert(message: Dict[str, Any], tg) -> Tuple[str, Optional[bytes], Optional[str]]:
    """Handle /convert <value> <from> to <to> command."""
    text = message.get("text", "")
    parts = text.split(None, 4)

    if len(parts) < 5 or parts[3].lower() != "to":
        return (
            "Usage: /convert <value> <from_unit> to <to_unit>\n\n"
            "Examples:\n"
            "  /convert 5000 psi to bar\n"
            "  /convert 1500 ppg to sg\n"
            "  /convert 35 degf to degc"
        ), None, None

    try:
        value = float(parts[1])
    except ValueError:
        return "Error: First argument must be a number.", None, None

    from_unit = parts[2].lower()
    to_unit = parts[4].lower()

    result = run_unit_conversion(value, from_unit, to_unit)
    return result if result else f"Unknown conversion: {from_unit} -> {to_unit}", None, None


@registry.register("plot", aliases=["pvt_plot"])
def handle_plot(message: Dict[str, Any], tg) -> Tuple[str, Optional[bytes], Optional[str]]:
    """
    Handle /plot command for direct numerical data plotting.
    Accepts user-supplied values directly from Telegram and returns a
    professional PNG via reply_photo. Never asks for document upload and
    never routes to any legacy/file-based plotting handler.

    Supported types: bo, rs, bg, z, viscosity, mu_g, dropout, cgr,
    density, vrel, gor, wor, watercut, pressure, production, kr,
    ipr, vlp, nodal.

    Syntax:
      /plot <type> p=<x1>,<x2>,... v=<y1>,<y2>,... [pb=val] [well=name]
      Multi-series: v1=..., v2=..., labels=<l1>,<l2>
      Custom X-axis name: x=<values> (equivalent to p=)
    """
    import re
    text = message.get("text", "")
    parts = text.split(None, 1)

    usage = (
        "📊 Plot Engineering Data\n\n"
        "Choose a plot type:\n\n"
        "Bo   Rs   Bg   Z\n"
        "Viscosity   Density\n"
        "GOR   WOR   Water Cut\n"
        "Pressure   Production\n"
        "Kr   IPR   VLP   Nodal\n\n"
        "Example:\n"
        "/plot bo p=500,1000,1500,2000 v=1.15,1.25,1.35,1.30 pb=1500\n\n"
        "Send the command with your data and the bot will generate "
        "the engineering plot."
    )

    if len(parts) < 2:
        return usage, None, None

    cmd_args = parts[1].split()
    type_alias = cmd_args[0].lower()
    rel_key = resolve_relationship_key(type_alias)

    if not rel_key:
        return f"Unknown plot type: {type_alias}\n\n{usage}", None, None

    # Parse direct numerical arguments (X-axis and Y-axis series only)
    x_values: Optional[List[float]] = None
    y_series: List[List[float]] = []
    labels: Optional[List[str]] = None
    pb: Optional[float] = None
    well_name: Optional[str] = None

    for token in cmd_args[1:]:
        if token.startswith("p=") or token.startswith("x="):
            try:
                x_values = [float(v) for v in token.split("=", 1)[1].split(",") if v.strip()]
            except ValueError:
                return "Error: X-axis values must be numeric (e.g. p=500,1000,1500).", None, None
        elif token == "v=" or re.match(r"v\d+=$", token):
            continue  # empty series token, ignore
        elif token.startswith("v=") or re.match(r"v\d+=", token):
            try:
                val_str = token.split("=", 1)[1]
                series = [float(v) for v in val_str.split(",") if v.strip()]
                if series:
                    y_series.append(series)
            except ValueError:
                return "Error: Y-axis values must be numeric (e.g. v=1.1,1.2,1.3).", None, None
        elif token.startswith("pb="):
            try:
                pb = float(token.split("=", 1)[1])
            except ValueError:
                pass
        elif token.startswith("well="):
            well_name = token.split("=", 1)[1]
        elif token.startswith("labels="):
            labels = token.split("=", 1)[1].split(",")

    # Validate direct data (user supplied values only; no file/document fallback)
    if x_values is None:
        return "Error: X-axis values are required.\n\nExample: /plot bo p=500,1000,1500,2000 v=2.5,2.0,1.8,2.2", None, None
    if not y_series:
        return "Error: Y-axis values (v=) are required.\n\nExample: /plot bo p=500,1000 v=2.5,2.0", None, None

    for i, series in enumerate(y_series):
        if len(series) != len(x_values):
            return (
                f"Error: Array length mismatch for series {i+1}.\n"
                f"X-axis has {len(x_values)} points, but Y-axis has {len(series)} points."
            ), None, None

    # Generate professional PNG from user-supplied data only
    text_response, png_bytes = format_plot_response(
        rel_key, x_values, y_series, pb, well_name, labels
    )
    return text_response, png_bytes, None


@registry.register("check", aliases=["validate", "validate_pvt"])
def handle_check(message: Dict[str, Any], tg) -> Tuple[str, Optional[bytes], Optional[str]]:
    """Handle /check <rel> p=v1,v2 v=v1,v2 [pb=val] command."""
    text = message.get("text", "")
    parts = text.split(None, 1)
    if len(parts) < 2:
        return (
            "Usage: /check <rel> p=v1,v2,... v=v1,v2,... [pb=val]\n\n"
            "Example: /check rs p=500,1000,1500,2000 v=300,300,250,180 pb=1500"
        ), None, None

    args_str = parts[1]
    rel_alias = args_str.split()[0]
    rel_key = resolve_relationship_key(rel_alias)
    if not rel_key:
        return f"Unknown relationship: {rel_alias}", None, None

    pressures: List[float] = []
    values: List[float] = []
    pb: Optional[float] = None

    for token in args_str.split():
        if token.startswith("p="):
            pressures = [float(x) for x in token[2:].split(",")]
        elif token.startswith("v="):
            values = [float(x) for x in token[2:].split(",")]
        elif token.startswith("pb="):
            pb = float(token[3:])

    if not pressures or not values:
        return "Error: Need both p= and v= arguments.", None, None
    if len(pressures) != len(values):
        return f"Error: {len(pressures)} pressures but {len(values)} values.", None, None

    result = validate_pvt_trend(rel_key, pressures, values, pb)
    return result, None, None


@registry.register("pvto")
def handle_pvto(message: Dict[str, Any], tg) -> Tuple[str, Optional[bytes], Optional[str]]:
    """Handle /pvto command."""
    result = generate_simulation_skeleton("pvto")
    return result, None, None


@registry.register("pvdo")
def handle_pvdo(message: Dict[str, Any], tg) -> Tuple[str, Optional[bytes], Optional[str]]:
    """Handle /pvdo command."""
    result = generate_simulation_skeleton("pvdo")
    return result, None, None


@registry.register("pvtg")
def handle_pvtg(message: Dict[str, Any], tg) -> Tuple[str, Optional[bytes], Optional[str]]:
    """Handle /pvtg command."""
    result = generate_simulation_skeleton("pvtg")
    return result, None, None


@registry.register("pvdg")
def handle_pvdg(message: Dict[str, Any], tg) -> Tuple[str, Optional[bytes], Optional[str]]:
    """Handle /pvdg command."""
    result = generate_simulation_skeleton("pvdg")
    return result, None, None


@registry.register("export_sim", aliases=["sim_export"])
def handle_export_sim(message: Dict[str, Any], tg) -> Tuple[str, Optional[bytes], Optional[str]]:
    """Handle /export_sim <fluid_type> [near_critical] command."""
    text = message.get("text", "")
    parts = text.split(None, 1)
    if len(parts) < 2:
        return (
            "Usage: /export_sim <fluid_type> [near_critical]\n\n"
            "Examples:\n"
            "  /export_sim black oil\n"
            "  /export_sim gas condensate near_critical\n"
            "  /export_sim volatile oil\n"
            "  /export_sim dry gas"
        ), None, None

    fluid_type = parts[1]
    near_critical = "near_critical" in fluid_type.lower()
    if near_critical:
        fluid_type = fluid_type.replace("near_critical", "").strip()

    result = export_sim_decision(fluid_type, near_critical)
    return result, None, None


@registry.register("eclipse")
def handle_eclipse(message: Dict[str, Any], tg) -> Tuple[str, Optional[bytes], Optional[str]]:
    """Handle /eclipse command."""
    result = (
        "Eclipse Simulation Guidance\n"
        + "=" * 50
        + "\n\n"
        "Eclipse 100 (E100) -- Black Oil\n"
        "Use for: Black Oil, Volatile Oil, Dry Gas, Wet Gas\n"
        "Tables: PVTO, PVDO, PVTG, PVDG\n"
        "Features: Waterflooding, gas injection, natural depletion\n"
        "Grid: Structured (corner-point or Cartesian)\n\n"
        "Eclipse 300 (E300) -- Compositional\n"
        "Use for: Gas Condensate, Volatile Oil (near-critical), Miscible EOR\n"
        "Requires: EOS (Peng-Robinson, SRK) + Tuning\n"
        "Tables: PVTC (compositional)\n\n"
        "Key Files:\n"
        "  .DATA -- main deck file\n"
        "  PVT section: PVTO/PVDO/PVTG/PVDG tables\n"
        "  SCAL section: Relative permeability curves\n\n"
        "PVT Table Selection:\n"
        "  Black Oil Rs>0 -> PVTO\n"
        "  Dead Oil Rs~0 -> PVDO\n"
        "  Gas Condensate -> PVTG\n"
        "  Dry Gas -> PVDG\n\n"
        "Use /pvto, /pvdo, /pvtg, /pvdg for table format details."
    )
    return result, None, None


@registry.register("cmg")
def handle_cmg(message: Dict[str, Any], tg) -> Tuple[str, Optional[bytes], Optional[str]]:
    """Handle /cmg command."""
    result = (
        "CMG Simulation Guidance\n"
        + "=" * 50
        + "\n\n"
        "CMG IMEX -- Compositional / Black Oil\n"
        "Use for: Most reservoir simulation cases\n"
        "Supports: Black Oil, Compositional, Thermal\n"
        "PVT Tables: Similar format to Eclipse\n\n"
        "CMG GEM -- Advanced Compositional\n"
        "Use for: Complex EOS, EOR, Gas Injection, SAGD\n"
        "Requires: Full EOS characterization\n"
        "PVT: EOS-based (no tables needed)\n\n"
        "CMG STARS -- Thermal / Heavy Oil\n"
        "Use for: SAGD, CSS, In-situ combustion\n"
        "Heavy Oil PVT: Requires viscosity models\n\n"
        "PVT Table Compatibility:\n"
        "  CMG IMEX accepts Eclipse-format PVTO/PVDO tables\n"
        "  CMG GEM uses EOS directly (less table-dependent)\n\n"
        "Workflow:\n"
        "  1. PVT Lab Data\n"
        "  2. EOS Tuning (GEM) or Table Generation (IMEX)\n"
        "  3. History Matching\n"
        "  4. Prediction"
    )
    return result, None, None


@registry.register("report", aliases=["pvt_report"])
def handle_report(message: Dict[str, Any], tg) -> Tuple[str, Optional[bytes], Optional[str]]:
    """Handle /report command with professional engineering PVT report generator."""
    from services.pvt_engine import generate_professional_pvt_report
    chat_id = message.get("chat", {}).get("id", "")
    from main import FILE_CONTEXT
    context = FILE_CONTEXT.get(chat_id)
    result = generate_professional_pvt_report(context)
    return result, None, None


@registry.register("glossary")
def handle_glossary(message: Dict[str, Any], tg) -> Tuple[str, Optional[bytes], Optional[str]]:
    """Handle /glossary command."""
    # Note: don't pass the HTML bytes in the png_bytes slot -- main.py's
    # dispatch checks `if png_bytes:` before `if doc_filename:`, so any
    # truthy value there gets wrongly sent as a photo instead of a document.
    # main.py's document-send path regenerates the HTML bytes itself.
    return "Glossary generated. Sending as HTML document...", None, "glossary.html"


@registry.register("analyze", aliases=["document", "doc"])
def handle_analyze(message: Dict[str, Any], tg) -> Tuple[str, Optional[bytes], Optional[str]]:
    """Handle /analyze command."""
    chat_id = message.get("chat", {}).get("id", "")
    from main import FILE_CONTEXT
    context = FILE_CONTEXT.get(chat_id)
    if not context:
        return "No document uploaded. Upload a PDF, DOCX, Excel, or CSV file first.", None, None
    return None, None, None  # Signal that AI analysis is needed


@registry.register("surface_separator", aliases=["separator"])
def handle_surface_separator(message: Dict[str, Any], tg) -> Tuple[str, Optional[bytes], Optional[str]]:
    """Handle /surface_separator command."""
    return SURFACE_SEPARATOR_ANSWER, None, None
