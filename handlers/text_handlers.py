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
from services import nodal_engine
from services.black_oil_pvt import BlackOilPvtProvider
from services import production_optimizer
from services.production_optimizer import (
    FEASIBLE, NO_OPERATING_POINT, MULTIPLE_OPERATING_POINTS,
    PHYSICALLY_INVALID,
)
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


def _build_vlp_pvt_binding(kwargs: Dict[str, Any],
                           floats: Dict[str, float]):
    """Resolve the optional Telegram Black-Oil provider binding.

    The VLP engine remains provider-free unless the user explicitly supplies
    ``pvt_model=black_oil`` (or an equivalent alias) and the minimum separator
    and saturation context. This keeps the Phase 5A handler path unchanged.
    """
    raw = str(kwargs.get("pvt_model", "none")).strip().lower()
    if raw in ("", "none", "default", "off", "false", "0"):
        return None, None, None
    if raw not in ("black_oil", "black-oil", "blackoil", "bo",
                   "black_oil_v1"):
        return None, None, (
            "Error: unknown pvt_model. Use 'none' (default) or "
            "'black_oil'.")

    def first_value(*keys):
        for key in keys:
            if key in floats:
                return floats[key]
        return None

    separator_pressure = first_value(
        "pvt_sep_p", "separator_pressure_psia", "sep_p")
    separator_temperature = first_value(
        "pvt_sep_t", "separator_temperature_f", "sep_t")
    bubble_point = first_value("pvt_pb", "bubble_point_psia", "pb")
    solution_gor = first_value(
        "pvt_rsb", "solution_gor_scf_stb", "rsb")
    missing = []
    if separator_pressure is None:
        missing.append("pvt_sep_p")
    if separator_temperature is None:
        missing.append("pvt_sep_t")
    if bubble_point is None and solution_gor is None:
        missing.append("pvt_pb or pvt_rsb")
    if missing:
        return None, None, (
            "Engineering Data Requirement — pvt_model=black_oil requires: "
            + ", ".join(missing) + ".")

    pvt_gamma_g = first_value(
        "pvt_gamma_g", "pvt_sg_g", "gas_specific_gravity")
    context = {
        "oil_api": floats["api"],
        "gas_specific_gravity": floats["gamma_g"] if pvt_gamma_g is None
        else pvt_gamma_g,
        "separator_pressure_psia": separator_pressure,
        "separator_temperature_f": separator_temperature,
    }
    if bubble_point is not None:
        context["bubble_point_psia"] = bubble_point
    if solution_gor is not None:
        context["solution_gor_scf_stb"] = solution_gor
    non_hydrocarbon = first_value(
        "pvt_non_hc", "non_hydrocarbon_fraction")
    if non_hydrocarbon is not None:
        context["non_hydrocarbon_fraction"] = non_hydrocarbon
    return BlackOilPvtProvider(), context, None


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
    if formula_key.lower() == "nodal":
        # Deterministic Production Nodal Analysis (Phase 3: orchestrator over
        # the verified IPR + VLP engines); kept separate from EXACT_FORMULAS
        # for the same parse_kv_args caution (model=, plot= string keys).
        text, png, caption = handle_calc_nodal(
            {"text": "/nodal " + args_str}, tg
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
    if formula_key.lower() in ("sensitivity", "sens"):
        # Phase 4: deterministic sensitivity layer over the verified Nodal
        # engine; string keys (type=, plot=) are kept first like IPR/VLP.
        text, png, caption = handle_calc_sensitivity(
            {"text": "/sensitivity " + args_str}, tg
        )
        return text, png, caption
    if formula_key.lower() in ("optimize", "optim"):
        # Phase 4: deterministic constrained candidate optimization over
        # the verified Nodal engine; string keys kept first like IPR/VLP.
        text, png, caption = handle_calc_optimize(
            {"text": "/optimize " + args_str}, tg
        )
        return text, png, caption
    if formula_key.lower() in ("vlp_compare", "vlp_compare_models"):
        # Phase 5A: deterministic comparison of the two verified VLP
        # correlations (Beggs-Brill 1973 vs Hagedorn-Brown 1965) with an
        # overlay plot; same parse_kv_args caution as /calc vlp.
        text, png, caption = handle_calc_vlp_compare(
            {"text": "/vlp_compare " + args_str}, tg
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
            if _key in ("model", "plot", "vlp_model"):
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
    "  bw (1.01), z (1.0), sigma (30 dyne/cm), segments (80)\n"
    "Optional pressure-dependent PVT: pvt_model=black_oil with\n"
    "  pvt_sep_p=100 pvt_sep_t=100 and pvt_pb=2500 (or pvt_rsb=700)\n\n"
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
    "vlp_model": "VLP correlation: 'beggs_brill' (default) or 'hagedorn_brown'",
    "pvt_model": "Optional PVT provider: 'black_oil' (default is none)",
    "pvt_sep_p": "Black-Oil separator pressure, psia",
    "pvt_sep_t": "Black-Oil separator temperature, degF",
    "pvt_pb": "Black-Oil bubble point pressure, psia",
    "pvt_rsb": "Black-Oil solution GOR at bubble point, scf/STB",
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
                      result,
                      vlp_model: str = "beggs_brill") -> List[str]:
    """Format a single-rate VLP engine result for Telegram."""
    lines = [
        "VLP Calculation Result",
        "=" * 50,
        f"Method: {vlp_engine.MODEL_DISPLAY.get(vlp_model, vlp_model)}",
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
    # Z-factor transparency: always report the active z and its provenance.
    z_active = result.z_factor if result.z_factor is not None else 1.0
    z_prov = result.z_factor_provenance or "default"
    if z_prov == "user supplied":
        lines.append("")
        lines.append(f"Gas Z-factor = {z_active:.2f} (user supplied)")
    elif z_prov == "BlackOilPvtProvider":
        lines.append("")
        lines.append(f"Gas Z-factor = {z_active:.2f} (Black-Oil provider)")
    else:
        lines.append("")
        lines.append(f"Gas Z-factor = {z_active:.2f} (default — not user "
                     "supplied)")
    pvt_meta = result.pvt_metadata or {}
    if pvt_meta.get("enabled"):
        lines.append("")
        lines.append("PVT model: Black-Oil V1 (pressure-dependent)")
        if pvt_meta.get("pressure_range_psia"):
            p_lo, p_hi = pvt_meta["pressure_range_psia"]
            lines.append(f"PVT pressure range: {p_lo:.1f} .. {p_hi:.1f} psia")
        if pvt_meta.get("phase_regions"):
            lines.append("PVT phase regions: " + ", ".join(
                pvt_meta["phase_regions"]))
    if result.input_defaults:
        lines.append("")
        lines.append("Engine defaults used (inputs not supplied by user):")
        for d in result.input_defaults:
            lines.append(f"  \u2022 {d}")
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
    model_name = vlp_engine.MODEL_DISPLAY.get(vlp_model, vlp_model)
    lines.append(f"NOTE: Results are CALCULATED ({model_name} correlation "
                 "with a\nsegmented midpoint traverse), not measured data.")
    return lines


# ---------------------------------------------------------------------------
# /calc nodal  —  Deterministic Nodal Analysis (Phase 3)
# ---------------------------------------------------------------------------
_NODAL_USAGE = (
    "Usage: /calc nodal [model=auto|linear|vogel|composite] [plot=1] "
    "key=value ...\n\n"
    "Required IPR inputs (one of the following):\n"
    "  Linear:   pr j\n"
    "  Vogel:    pr qmax (or pr q_test pwf_test — inverted)\n"
    "  Composite:pr pb q_test pwf_test\n"
    "Required VLP inputs (all):\n"
    "  thp tvd id gor api gamma_g mu_l bo rs t_wh geothermal\n"
    "Optional VLP inputs:\n"
    "  wc (default 0)  gamma_w (1.07)  bw (1.01)  z (0.9)\n"
    "  sigma (30 dyne/cm)  segments (80)\n"
    "Solver inputs:\n"
    "  q_min (default 0)  q_max (default IPR theoretical maximum)\n"
    "  n_points (default 201)\n\n"
    "Examples:\n"
    "  /calc nodal model=auto pr=3000 pb=2200 q_test=900 pwf_test=2400 \\\n"
    "      thp=100 tvd=8000 id=1.995 gor=1000 rs=600 api=35 gamma_g=0.65 \\\n"
    "      mu_l=1 bo=1.4 t_wh=120 geothermal=1.5 plot=1\n"
    "  /calc nodal model=vogel pr=3000 qmax=1500 thp=100 tvd=8000 \\\n"
    "      id=1.995 gor=1000 rs=600 api=35 gamma_g=0.65 mu_l=1 bo=1.4 \\\n"
    "      t_wh=120 geothermal=1.5 plot=1\n"
    "  /calc nodal model=linear pr=3000 j=1.5 thp=100 tvd=8000 id=1.995 \\\n"
    "      gor=1000 rs=600 api=35 gamma_g=0.65 mu_l=1 bo=1.4 t_wh=120 \\\n"
    "      geothermal=1.5"
)
_NODAL_HINTS = {
    "pr": "Reservoir pressure (psia)",
    "pb": "Bubble-point pressure (psia) — enables Composite/automatic selection",
    "j": "Productivity index (STB/day/psi) — for Linear IPR",
    "qmax": "Absolute open flow potential qmax (STB/day) — for Vogel IPR",
    "q_test": "Measured test rate (STB/day)",
    "pwf_test": "Measured test flowing pressure (psia)",
    "thp": "Tubing-head pressure (psia)",
    "tvd": "True vertical depth (ft)",
    "id": "Tubing inside diameter (in)",
    "gor": "Produced GOR (scf/STB)",
    "api": "Oil API gravity",
    "gamma_g": "Gas specific gravity (air = 1)",
    "mu_l": "Liquid viscosity (cP)",
    "bo": "Oil FVF (rb/STB)",
    "rs": "Solution GOR (scf/STB)",
    "t_wh": "Wellhead temperature (degF)",
    "geothermal": "Geothermal gradient (degF/100 ft)",
}


_NODAL_IPR_INPUT_SETS = (
    "Provide one valid IPR input set (pick ONE of the following):\n"
    "  \u2022 Linear        \u2192 pr= + j=\n"
    "  \u2022 Vogel         \u2192 pr= + qmax=  (or a valid test point "
    "q_test= + pwf_test=)\n"
    "  \u2022 Composite     \u2192 pr= + pb= + q_test= + pwf_test=\n"
    "  \u2022 Auto           \u2192 pr= + any of the sets above "
    "(model=auto is the default)"
)


def _nodal_missing_message(missing: List[str]) -> str:
    lines = ["Cannot run Nodal Analysis yet: missing data."]
    lines.append("")
    lines.append(_NODAL_IPR_INPUT_SETS)
    lines.append("")
    # VLP inputs are required in every mode, so list those explicitly.
    vlp_missing = [k for k in missing
                   if k in ("thp", "tvd", "id", "gor", "api", "gamma_g",
                            "mu_l", "bo", "rs", "t_wh", "geothermal")]
    if vlp_missing:
        lines.append("Required VLP inputs (not provided):")
        for k in vlp_missing:
            hint = _NODAL_HINTS.get(k, "")
            lines.append(f"  \u2022 {k}" + (f" ({hint})" if hint else ""))
        lines.append("")
    lines.append(_NODAL_USAGE)
    return "\n".join(lines)


def _nodal_result_lines(result: nodal_engine.NodalResult) -> List[str]:
    lines = ["Nodal Analysis Result", "=" * 50]
    lines.append("Status: " + result.status)
    lines.append("")
    if result.status == nodal_engine._STATUS_UNIQUE:
        rt = result.roots[0]
        lines.append("Operating point:")
        lines.append(f"  q  = {rt.q:.2f} STB/day")
        lines.append(f"  Pwf = {rt.pwf:.2f} psia")
        lines.append(f"  Residual |Pwf_IPR - Pwf_VLP| = {rt.residual:.4f} psi")
        if rt.slope_sign:
            lines.append(f"  Stability (interpretation only): {rt.slope_sign}")
    elif result.status == nodal_engine._STATUS_MULTIPLE:
        lines.append(f"{len(result.roots)} operating points detected:")
        for rt in result.roots:
            stab = rt.slope_sign or "unknown"
            lines.append(f"  ({rt.index}) q = {rt.q:.2f} STB/day, "
                         f"Pwf = {rt.pwf:.2f} psia, "
                         f"residual {rt.residual:.4f} psi, stability: {stab}")
        lines.append("")
        for w in result.warnings:
            lines.append(f"NOTE: {w}")
    elif result.status == nodal_engine._STATUS_NONE:
        lines.append("No operating point found in the analyzed range.")
        if result.reason:
            lines.append("Reason: " + result.reason)
    lines.append("")
    lines.append(f"Inflow model: {result.ipr_model} — {result.ipr_reason}")
    lines.append(f"Outflow model: {result.vlp_model}")
    lines.append(f"Rate range analyzed: {result.q_min:g} .. {result.q_max:g} "
                 f"STB/day ({result.n_scan_points} scan points)")
    lines.append(f"Solver: {result.root_method} "
                 f"(pressure tolerance {result.pressure_tol:g} psi)")
    if result.warnings:
        lines.append("")
        lines.append("Solver warnings:")
        for w in result.warnings:
            lines.append(f"  \u2022 {w}")
    lines.append("")
    lines.append("NOTE: Results are CALCULATED (verified deterministic IPR "
                 "and VLP engines coupled by a bracketed root solver), "
                 "not measured data.")
    return lines


@registry.register("nodal", aliases=["ipr_vlp", "node"])
def handle_calc_nodal(message: Dict[str, Any], tg) -> Tuple[str, Optional[bytes], Optional[str]]:
    """Handle /calc nodal [model=...] [plot=1] key=value ... — deterministic
    Nodal Analysis (orchestrator over the verified IPR + VLP engines).

    Reachable via /calc nodal (dispatched through handle_calc) or directly
    as /nodal with the same key=value syntax.
    """
    text = message.get("text", "")
    first_space = text.find(" ")
    args_str = text[first_space + 1:] if first_space >= 0 else ""
    # parse_kv_args silently drops non-numeric values (model=, plot=), so
    # keep string keys first, then numeric kv parsing (same as IPR/VLP).
    kwargs: Dict[str, Any] = {}
    if args_str and args_str.strip():
        for _part in args_str.split():
            if "=" not in _part:
                continue
            _key, _, _val = _part.partition("=")
            _key, _val = _key.strip().lower(), _val.strip()
            if _key in ("model", "plot", "vlp_model"):
                kwargs[_key] = _val
                continue
    _numeric = parse_kv_args(args_str)
    if isinstance(_numeric, dict):
        _numeric.update(kwargs)
        kwargs = _numeric

    # --- Hard validation (guardrails) ---
    vlp_model_raw = str(kwargs.get("vlp_model", "beggs_brill")).strip().lower()
    try:
        vlp_model = vlp_engine._resolve_model(vlp_model_raw)
    except ValueError:
        return ("Error: unknown vlp_model. Use 'beggs_brill' (default) or "
                "'hagedorn_brown'."), None, None
    ipr_model = (kwargs.get("model") or "auto").lower()
    if ipr_model not in ("auto", "linear", "vogel", "composite"):
        return ("Error: model must be one of auto, linear, vogel, composite.\n\n"
                + _NODAL_USAGE), None, None

    # Required inputs per mode (single-solve mode). Build the list of
    # MISSING keys only — never add a key that is already supplied.
    required = []
    if kwargs.get("pr") is None:
        required.append("pr")
    q_test = kwargs.get("q_test")
    pwf_test = kwargs.get("pwf_test")
    test_pair = q_test is not None and pwf_test is not None
    if ipr_model == "auto":
        if not test_pair:
            # Without a test point the user must give a slope (j) or qmax so
            # the inflow curve can be anchored; pb stays optional.
            if kwargs.get("j") is None and kwargs.get("qmax") is None:
                required += ["j", "q_test", "pwf_test"]
            # Without Pb the engine's auto policy resolves to Vogel IPR,
            # which needs qmax (or the test pair) — j alone cannot anchor it.
            elif kwargs.get("pb") is None and kwargs.get("qmax") is None:
                required.append("qmax")
    elif ipr_model == "linear":
        if kwargs.get("j") is None:
            if test_pair:
                required += ["q_test", "pwf_test"]
            else:
                required += ["j", "q_test", "pwf_test"]
    elif ipr_model == "vogel":
        if kwargs.get("qmax") is None:
            if test_pair:
                required += ["q_test", "pwf_test"]
            else:
                required += ["qmax", "q_test", "pwf_test"]
    else:  # composite — always needs the test point + pb
        for _k in ("q_test", "pwf_test", "pb"):
            if kwargs.get(_k) is None:
                required.append(_k)

    vlp_required = ["thp", "tvd", "id", "gor", "api", "gamma_g", "mu_l",
                    "bo", "rs", "t_wh", "geothermal"]
    for k in vlp_required:
        if kwargs.get(k) is None:
            required.append(k)
    # Deduplicate preserving order.
    required = list(dict.fromkeys(required))
    if required:
        return _nodal_missing_message(required), None, None

    # --- Float conversion ---
    try:
        floats = {}
        for _k in ("pr", "pb", "j", "qmax", "q_test", "pwf_test", "thp", "tvd",
                   "id", "gor", "api", "gamma_g", "mu_l", "bo", "rs", "t_wh",
                   "geothermal", "wc", "gamma_w", "bw", "z", "sigma",
                   "segments", "q_min", "q_max", "n_points"):
            _v = kwargs.get(_k)
            if _v is not None:
                floats[_k] = float(_v)
    except (TypeError, ValueError):
        return ("Error: all parameter values must be numeric.\n\n"
                + _NODAL_USAGE), None, None

    try:
        wc = floats.get("wc", 0.0)
        if not (0.0 <= wc <= 1.0):
            return "Error: wc must be between 0 and 1.", None, None
        if floats.get("q_min") is not None and floats["q_min"] < 0:
            return "Error: q_min must be >= 0.", None, None
        if (floats.get("q_min") is not None and
                floats.get("q_max") is not None and
                floats["q_min"] >= floats["q_max"]):
            return "Error: q_min must be < q_max.", None, None
        if floats.get("n_points") is not None:
            if floats["n_points"] != int(floats["n_points"]) or \
                    floats["n_points"] < 2:
                return "Error: n_points must be an integer >= 2.", None, None

        engine = nodal_engine.NodalEngine()
        result = engine.solve(
            ipr_model=ipr_model,
            pr=floats["pr"],
            pb=floats.get("pb"),
            j=floats.get("j"),
            qmax=floats.get("qmax"),
            q_test=floats.get("q_test"),
            pwf_test=floats.get("pwf_test"),
            thp=floats["thp"], tvd=floats["tvd"],
            tubing_id_in=floats["id"], gor=floats["gor"], rs=floats["rs"],
            api=floats["api"], gamma_g=floats["gamma_g"],
            mu_l=floats["mu_l"], bo=floats["bo"], t_wh=floats["t_wh"],
            geothermal=floats.get("geothermal", 1.5),
            wc=wc, gamma_w=floats.get("gamma_w", 1.07),
            bw=floats.get("bw", 1.01), z_factor=floats.get("z", 0.9),
            sigma=floats.get("sigma", 30.0),
            n_segments=int(floats.get("segments", 80)),
            vlp_model=vlp_model,
            q_min=floats.get("q_min"),
            q_max=floats.get("q_max"),
            n_points=int(floats.get("n_points", 201)),
        )
    except nodal_engine.NodalError as _e:
        _msg = str(_e)
        if "PHYSICALLY_INVALID" in _msg:
            return ("Engineering Guardrail — inputs rejected as physically "
                    "invalid.\n" + _msg), None, None
        return ("Engineering Guardrail — inputs rejected.\n" + _msg), None, None
    except Exception as _e:
        return f"Nodal analysis error: {_e}. Please check your inputs.", \
            None, None

    # --- Build IPR + VLP curves for the calculated Nodal plot ---
    # Curve points go through the engine's OWN inverters with the SAME
    # resolved params and VLP kwargs the solver used — no duplicated
    # calibration (j_star) or inversion logic.
    q_min_v = result.q_min
    q_max_v = result.q_max
    n_pts = 20
    qs_curve, ps_ipr, ps_vlp = [], [], []
    try:
        if result.ipr_params is not None and result.vlp_kwargs is not None:
            for i in range(n_pts):
                q_total = q_min_v + (q_max_v - q_min_v) * i / (n_pts - 1)
                qs_curve.append(q_total)
                try:
                    ps_ipr.append(engine.pwf_ipr_from_rate(
                        result.ipr_params, q_total))
                except nodal_engine.NodalError:
                    ps_ipr.append(None)
                try:
                    ps_vlp.append(engine.pwf_vlp(
                        q_total, result.ipr_params, result.vlp_kwargs))
                except nodal_engine.NodalError:
                    ps_vlp.append(None)
    except Exception:
        qs_curve, ps_ipr, ps_vlp = [], [], []

    # --- Response ---
    out = _nodal_result_lines(result)
    out.append("")
    out.append("Calculated Nodal curve points (rate on X):")
    for _q, _p_ipr, _p_vlp in zip(qs_curve, ps_ipr, ps_vlp):
        if _p_vlp is None:
            out.append(f"  q = {_q:g}  IPR Pwf = {_p_ipr:.1f}  VLP = N/C")
        else:
            out.append(f"  q = {_q:g}  IPR Pwf = {_p_ipr:.1f}  "
                       f"VLP Pwf = {_p_vlp:.1f}")
    png = None
    if bool(kwargs.get("plot")) and qs_curve:
        clean_vlp = [_v for _v in ps_vlp if _v is not None]
        clean_q = [q for q, v in zip(qs_curve, ps_vlp) if v is not None]
        clean_ipr = [p for p, v in zip(ps_ipr, ps_vlp) if v is not None]
        png = generate_pvt_plot(
            "nodal_plot", clean_q,
            [clean_ipr, clean_vlp], None,
            f"Calculated Nodal Analysis — {result.ipr_model} IPR vs VLP",
            labels=["IPR (inflow)", "VLP (outflow)"],
        )
        if png is None:
            out.append("")
            out.append("NOTE: could not generate the calculated Nodal plot.")
        else:
            out.append("")
            out.append("Calculated Nodal Plot attached: IPR and VLP curves "
                       "(rate on X, BHP on Y); the intersection is the "
                       "operating point.")
            out.append("This is a model-generated curve, not measured data.")
            if result.status == nodal_engine._STATUS_UNIQUE:
                out.append("")
                out.append("Operating point: q = "
                           f"{result.roots[0].q:.2f} STB/day, Pwf = "
                           f"{result.roots[0].pwf:.2f} psia.")
    return "\n".join(out), png, None


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
            if _key in ("plot", "vlp_model", "pvt_model"):
                kwargs[_key] = _val
                continue
    _numeric = parse_kv_args(args_str)
    _numeric.update(kwargs)
    kwargs = _numeric
    # Normalize the VLP correlation selector (string key, not numeric).
    vlp_model = str(kwargs.get("vlp_model", "beggs_brill")).strip().lower()
    try:
        vlp_model = vlp_engine._resolve_model(vlp_model)
    except ValueError:
        return ("Error: unknown vlp_model. Use 'beggs_brill' (default) or "
                "'hagedorn_brown'."), None, None

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
        required = [k for k in vlp_engine.missing_inputs(kwargs, vlp_model)
                    if k != "q"]
        if q_min is None:
            required.append("q_min")
        if q_max is None:
            required.append("q_max")
        if q_min is not None and q_max is not None and q_min > q_max:
            return ("Error: q_min must be <= q_max for the VLP curve sweep."), None, None
    else:
        required = vlp_engine.missing_inputs(kwargs, vlp_model)
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
                   "bw", "z", "sigma", "segments", "q_min", "q_max", "pb", "rsb",
                   "pvt_sep_p", "pvt_sep_t", "pvt_pb", "pvt_rsb", "pvt_gamma_g",
                   "pvt_sg_g", "pvt_non_hc", "separator_pressure_psia",
                   "separator_temperature_f", "bubble_point_psia",
                   "solution_gor_scf_stb", "gas_specific_gravity",
                   "non_hydrocarbon_fraction"):
            _v = kwargs.get(_k)
            if _v is not None:
                floats[_k] = float(_v)
    except (TypeError, ValueError):
        return ("Error: all parameter values must be numeric.\n\n" + _VLP_USAGE), None, None

    pvt_provider, pvt_context, pvt_error = _build_vlp_pvt_binding(
        kwargs, floats)
    if pvt_error:
        return pvt_error, None, None

    if curve_mode:
        # --- Calculated VLP curve + plot ---
        wc = floats.get("wc", 0.0)
        # Z-factor provenance: what the VLP calculations actually used.
        z_used = floats.get("z", 1.0)
        z_prov = "user supplied" if "z" in floats else "default — not user supplied"
        # Input defaults list for auditability: every engine default the
        # calculation relied on because the user did not supply the input.
        input_defaults = []
        if "gamma_w" not in floats:
            input_defaults.append("gamma_w = 1.07 (default)")
        if "bw" not in floats:
            input_defaults.append("bw = 1.01 (default)")
        if "z" not in floats:
            input_defaults.append("z = 1.00 (default)")
        if "geothermal" not in floats:
            input_defaults.append("geothermal = 1.5 degF/100 ft (default)")
        if "segments" not in floats:
            input_defaults.append("segments = 80 (default)")
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
                    n_segments=int(floats.get("segments", 80)),
                    vlp_model=vlp_model,
                    z_provenance=z_prov,
                    input_defaults=input_defaults,
                    pvt_provider=pvt_provider,
                    pvt_context=pvt_context).pwf)
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
                        n_segments=int(floats.get("segments", 80)),
                        vlp_model=vlp_model,
                        z_provenance=z_prov,
                        input_defaults=input_defaults).pwf)
        if not qs:
            return "VLP curve error: empty rate sweep.", None, None
        out = [
            "Calculated VLP Curve",
            "=" * 50,
            f"Method: {vlp_engine.MODEL_DISPLAY[vlp_model]}",
            *(["PVT model: Black-Oil V1 (pressure-dependent)"]
              if pvt_provider is not None else []),
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
                labels=["Calculated — " + vlp_engine.MODEL_DISPLAY[vlp_model]],
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
    # Z-factor provenance: what the VLP calculation actually used.
    z_prov_single = "user supplied" if "z" in floats \
        else "default — not user supplied"
    input_defaults_single = []
    for _dk, _dv in (("gamma_w", "gamma_w = 1.07 (default)"),
                     ("bw", "bw = 1.01 (default)"),
                     ("z", "z = 1.00 (default)"),
                     ("geothermal", "geothermal = 1.5 degF/100 ft (default)"),
                     ("sigma", "sigma = 30.0 dyn/cm (default)"),
                     ("segments", "segments = 80 (default)")):
        if _dk not in floats:
            input_defaults_single.append(_dv)
    try:
        result = vlp_engine.traverse(
            floats["thp"], floats["tvd"], q_o, q_w, floats["gor"],
            floats["bo"], floats.get("bw", 1.01), floats.get("z", 1.0),
            floats["gamma_g"], floats.get("gamma_w", 1.07), floats["mu_l"],
            floats["api"], wc, floats["id"], floats["rs"], floats["t_wh"],
            floats.get("geothermal", 1.5),
            sigma=floats.get("sigma", 30.0),
            n_segments=int(floats.get("segments", 80)),
            vlp_model=vlp_model,
            z_provenance=z_prov_single,
            input_defaults=input_defaults_single,
            pvt_provider=pvt_provider,
            pvt_context=pvt_context,
        )
    except ValueError as _e:
        _msg = str(_e)
        if "PHYSICALLY_INVALID" in _msg:
            return ("Engineering Guardrail — inputs rejected as physically "
                    "invalid.\n" + _msg), None, None
        return ("Engineering Guardrail — inputs rejected.\n" + _msg), None, None
    except Exception as _e:
        return f"VLP calculation error: {_e}. Please check your inputs.", None, None

    out = _vlp_result_lines(floats["thp"], floats["tvd"], q_o, q_w, result,
                            vlp_model=vlp_model)

    png = None
    if bool(kwargs.get("plot")):
        png = generate_pvt_plot(
            "vlp_plot", [q_o + q_w], [result.pwf], None,
            f"Calculated VLP — single rate {q_o + q_w:g} STB/day",
            labels=["Calculated — " + vlp_engine.MODEL_DISPLAY[vlp_model]],
        )
        if png is None:
            out.append("")
            out.append("NOTE: could not generate the calculated VLP plot.")
        else:
            out.append("")
            out.append("Calculated VLP Plot attached (rate on X, required BHP on Y).")
            out.append("This is a model-generated curve, not measured data.")
    return "\n".join(out), png, None


@registry.register("vlp_compare")
def handle_calc_vlp_compare(message: Dict[str, Any], tg
                            ) -> Tuple[str, Optional[bytes], Optional[str]]:
    """Handle /calc vlp_compare ... — deterministic comparison of the two
    VLP correlations (Beggs-Brill 1973 vs Hagedorn-Brown 1965) over the same
    rate sweep, with an overlay plot (rate on X, required BHP on Y)."""
    text = message.get("text", "")
    first_space = text.find(" ")
    args_str = text[first_space + 1:] if first_space >= 0 else ""
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

    # The comparison always sweeps both models, so the required VLP inputs
    # follow the most demanding correlation (BB envelope here).
    required = [k for k in vlp_engine.missing_inputs(kwargs, "beggs_brill")
                if k != "q"]
    if required:
        return _vlp_missing_message(required), None, None

    # --- Float conversion ---
    try:
        floats = {}
        for _k in ("thp", "tvd", "id", "gor", "api", "gamma_g", "mu_l",
                   "bo", "rs", "t_wh", "geothermal", "wc", "gamma_w",
                   "bw", "z", "sigma", "segments"):
            _v = kwargs.get(_k)
            if _v is not None:
                floats[_k] = float(_v)
    except (TypeError, ValueError):
        return "Error: all parameter values must be numeric.", None, None

    wc = floats.get("wc", 0.0)
    id_ = floats["id"]
    n_segments = int(floats.get("segments", 80))

    def _sweep(model: str):
        """Rate sweep through the same traverse API used by /calc vlp."""
        qs, ps = [], []
        for i in range(20):
            q_total = 0.0 + (5000.0 - 0.0) * i / 19.0
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
                    floats["api"], wc, id_, floats["rs"],
                    floats["t_wh"], floats.get("geothermal", 1.5),
                    sigma=floats.get("sigma", 30.0),
                    n_segments=n_segments,
                    vlp_model=model).pwf)
        return qs, ps

    try:
        qs_bb, ps_bb = _sweep("beggs_brill")
        qs_hb, ps_hb = _sweep("hagedorn_brown")
    except ValueError as _e:
        return ("VLP comparison error: " + str(_e) +
                "\nPlease check your inputs (the Hagedorn-Brown correlation "
                "applies strict envelope limits on GOR, tubing ID and "
                "liquid rate — see its limitations list)."), None, None
    except Exception as _e:
        return f"VLP comparison error: {_e}.", None, None

    deltas = [_hb - _bb for _hb, _bb in zip(ps_hb, ps_bb)]
    max_delta = max(abs(d) for d in deltas)

    out = [
        "VLP Model Comparison (CALCULATED — Beggs-Brill 1973 vs "
        "Hagedorn-Brown 1965)",
        "=" * 60,
        f"THP = {floats['thp']:g} psia  |  TVD = {floats['tvd']:g} ft  |  "
        f"ID = {id_:g} in",
        f"GOR = {floats['gor']:g} scf/STB (Rs = {floats['rs']:g})  |  "
        f"wc = {wc:.2f}",
        "Sweep: q = 0 .. 5000 STB/day (20 points, segmented traverse, "
        "same inputs to both correlations)",
        "",
        "Rate (STB/day) -> Pwf_BeggsBrill -> Pwf_HagedornBrown -> Δ "
        "(HB − BB, psi):",
    ]
    for _q, _bb, _hb, _d in zip(qs_bb, ps_bb, ps_hb, deltas):
        out.append(f"  q = {_q:g}  ->  BB = {_bb:.1f}  HB = {_hb:.1f}  "
                   f"Δ = {_d:+.2f}")
    out.append("")
    out.append(f"Maximum |Δ| over the sweep: {max_delta:.1f} psi")
    out.append("")
    out.append("NOTE: Differences come entirely from the two independent")
    out.append("correlation formulations (no shared equations). Inputs")
    out.append("outside a correlation's published envelope are reported in")
    out.append("that correlation's limitations; results are still computed.")
    out.append("These are model-generated values, not measured data.")

    png = None
    if bool(kwargs.get("plot")):
        png = generate_pvt_plot(
            "vlp_compare_plot", qs_bb,
            [ps_bb, ps_hb], None,
            "VLP Comparison — Beggs-Brill vs Hagedorn-Brown",
            labels=["Beggs-Brill (1973)", "Hagedorn-Brown (1965)"],
        )
        if png is None:
            out.append("")
            out.append("NOTE: could not generate the comparison plot.")
        else:
            out.append("")
            out.append("Comparison plot attached (rate on X, required BHP on Y).")
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


# ═══════════════════════════════════════════════════════════════════════
#  /calc sensitivity & /calc optimize  —  Phase 4 Sensitivity &
#  Constrained Candidate Optimization (deterministic layer over the
#  verified IPR + VLP + Nodal engines; zero equation duplication).
#
#  Syntax (both commands):
#    /calc sensitivity type=<var> [var=value1,value2,...]
#        [var_min=X var_max=Y n_points=N] [base_var=X]
#        <IPR inputs...> <VLP inputs...> [plot=1]
#    /calc optimize type=<var> var=value1,value2 objective=<obj>
#        [min_pwf=X max_drawdown=X max_liquid_rate=X max_water_cut=X
#         min_thp=X max_thp=X max_gor=X]
#        <IPR inputs...> <VLP inputs...> [plot=1]
#
#  <var>: thp | id (tubing_id) | wc (water_cut) | gor
#  <obj>: max_oil_rate
# ═══════════════════════════════════════════════════════════════════════

_SENSITIVITY_USAGE = (
    "Usage: /calc sensitivity type=<var> var=<values> "
    "[var_min=X var_max=Y n_points=N] [base_var=X] [plot=1] "
    "<IPR inputs> <VLP inputs>\n\n"
    "Supported variables:\n"
    "  type=thp        THP sensitivity  (thp=100,200,300  or  "
    "thp_min=100 thp_max=400 n_points=4)\n"
    "  type=id         Tubing-ID sensitivity  (id=1.995,2.5,3.0)\n"
    "  type=wc         Water-cut sensitivity  (wc=0,0.25,0.5,0.75,1  — "
    "0<=wc<=1)\n"
    "  type=gor        Produced-GOR sensitivity  (gor=400,800,1600)\n\n"
    "Base case: the first supplied candidate value (or var_min for a "
    "range). Every scenario reports Delta-q, Delta-q% and Delta-Pwf "
    "versus the base case.\n\n"
    "Required in addition: one valid IPR input set (see /calc nodal) and "
    "all VLP inputs (thp tvd id gor api gamma_g mu_l bo rs t_wh "
    "geothermal).\n\n"
    "Examples:\n"
    "  /calc sensitivity type=thp thp=100,200,300 model=linear pr=3000 "
    "j=1.5 tvd=8000 id=1.995 gor=1000 rs=600 api=35 gamma_g=0.65 "
    "mu_l=1 bo=1.4 t_wh=120 geothermal=1.5 plot=1\n"
    "  /calc sensitivity type=wc wc=0,0.5,1 thp_min=100 thp_max=400 "
    "n_points=3 model=linear pr=3000 j=1.5 tvd=8000 id=1.995 gor=1000 "
    "rs=600 api=35 gamma_g=0.65 mu_l=1 bo=1.4 t_wh=120 geothermal=1.5"
)

_OPTIMIZE_USAGE = (
    "Usage: /calc optimize type=<var> var=<values> objective=<obj> "
    "[constraints...] [plot=1] <IPR inputs> <VLP inputs>\n\n"
    "Supported variables: type=thp | id (tubing) | wc (water cut) | gor\n"
    "Objective: objective=max_oil_rate (only deterministic objective "
    "implemented in this phase)\n\n"
    "Supported constraints (explicit limits only):\n"
    "  min_pwf=<psi>  max_drawdown=<psi>  max_liquid_rate=<STB/d>  "
    "max_water_cut=<frac>\n"
    "  min_thp=<psi>  max_thp=<psi>  max_gor=<scf/STB>\n\n"
    "At least two candidates required. Every candidate is classified as "
    "FEASIBLE / INFEASIBLE / NO_OPERATING_POINT / MULTIPLE_OPERATING_POINTS "
    "/ NUMERICAL_NON_CONVERGENCE / PHYSICALLY_INVALID.\n\n"
    "Example:\n"
    "  /calc optimize type=id id=1.995,2.5,3.0 objective=max_oil_rate "
    "min_pwf=500 model=linear pr=3000 j=1.5 tvd=8000 gor=1000 rs=600 "
    "api=35 gamma_g=0.65 mu_l=1 bo=1.4 t_wh=120 geothermal=1.5 plot=1"
)

# Telegram names -> optimizer variable names and display labels
SENSVARIABLE_LABELS = {
    "thp": "THP", "tubing_id": "Tubing ID",
    "water_cut": "Water cut", "gor": "GOR",
}
# Explicit per-parameter unit metadata — never a generic pressure formatter.
SENSUNIT_MAP = {
    "thp": "psia",
    "tubing_id": "in",
    "water_cut": "",
    "gor": "scf/STB",
}
SENSVAR_KEYS = {"thp": "thp", "id": "tubing_id",
                "wc": "water_cut", "gor": "gor"}


def _parse_number_list(token_value: str) -> Tuple[List[float], Optional[str]]:
    """Parse '1.995,2.5,3.0' style values; return (list, error_text)."""
    try:
        values = [float(_v) for _v in token_value.split(",")
                  if _v.strip()]
        return values, None
    except ValueError:
        return [], "Error: values must be numbers separated by commas " \
                   "(e.g. 1.995,2.5,3.0)."


def _common_string_keys(args_str: str, extra: Tuple[str, ...]
                        ) -> Dict[str, Any]:
    """Parse string keys that parse_kv_args silently drops (same caution
    as the IPR/VLP/nodal handlers).

    Comma-separated numeric lists are kept here verbatim for the
    sensitivity/optimization keys (e.g. thp=100,200,300) because the
    generic numeric parser cannot consume lists."""
    _LIST_KEYS = ("thp", "id", "wc", "gor",
                  "thp_min", "id_min", "wc_min", "gor_min",
                  "thp_max", "id_max", "wc_max", "gor_max")
    kwargs: Dict[str, Any] = {}
    for _part in (args_str.split() if args_str else []):
        if "=" not in _part:
            continue
        _key, _, _val = _part.partition("=")
        _key, _val = _key.strip().lower(), _val.strip()
        if _key in ("model", "plot", "vlp_model", "type", "objective",
                    "base_thp",
                    "base_id", "base_wc", "base_gor",
                    "n_points") + extra + _LIST_KEYS:
            # Duplicate-key conflict: when the same key appears twice
            # (e.g. type=id and a later id=1.995 VLP token, or the sweep
            # key given as both a comma list and a base value), prefer
            # the comma-separated list if any occurrence carries one;
            # otherwise the LAST occurrence wins (usual kv semantics).
            if _key in kwargs and "," in _val:
                # a comma list must always beat a plain single value
                kwargs[_key] = _val
            elif _key in kwargs and "," in kwargs[_key]:
                pass  # existing comma list survives a plain single value
            else:
                kwargs[_key] = _val
    return kwargs


def _ipr_kwargs_for_optimizer(kwargs: Dict[str, Any],
                              model_req: str,
                              ) -> Dict[str, Optional[float]]:
    """Build the IPR kwargs block (same keys NodalEngine.solve expects),
    reusing the nodal handler's required-input policy. Returns
    (ipr_kwargs, error_text)."""
    pr = kwargs.get("pr"); pb = kwargs.get("pb")
    j = kwargs.get("j"); qmax = kwargs.get("qmax")
    q_test = kwargs.get("q_test"); pwf_test = kwargs.get("pwf_test")
    j_star = kwargs.get("j_star")
    required: List[str] = []
    if pr is None:
        required.append("pr")
    if model_req == "auto":
        if q_test is None or pwf_test is None:
            if j is None and qmax is None:
                required += ["j", "qmax", "q_test", "pwf_test"]
            elif pb is None and qmax is None:
                required.append("qmax")
    elif model_req == "linear":
        if j is None:
            required += ["j", "q_test", "pwf_test"] if \
                (q_test is None or pwf_test is None) else []
    elif model_req == "vogel":
        if qmax is None:
            required += ["qmax", "q_test", "pwf_test"] if \
                (q_test is None or pwf_test is None) else []
    else:  # composite
        for _k in ("pb", "q_test", "pwf_test"):
            if kwargs.get(_k) is None:
                required.append(_k)
    if required:
        return {}, _nodal_missing_message(required)
    return {"ipr_model": model_req, "pr": pr, "pb": pb, "j": j,
            "j_star": j_star, "qmax": qmax, "q_test": q_test,
            "pwf_test": pwf_test}, None


def _vlp_kwargs_for_optimizer(kwargs: Dict[str, Any]
                              ) -> Tuple[Dict[str, float], Optional[str]]:
    """Build the VLP kwargs block for the optimizer (canonical names)."""
    vlp_required = ["thp", "tvd", "id", "gor", "api", "gamma_g", "mu_l",
                    "bo", "rs", "t_wh", "geothermal"]
    missing = [k for k in vlp_required if kwargs.get(k) is None]
    if missing:
        return {}, _nodal_missing_message(missing)
    return {"thp": kwargs["thp"], "tvd": kwargs["tvd"],
            "tubing_id_in": kwargs["id"], "gor": kwargs["gor"],
            "rs": kwargs["rs"], "api": kwargs["api"],
            "gamma_g": kwargs["gamma_g"], "mu_l": kwargs["mu_l"],
            "bo": kwargs["bo"], "t_wh": kwargs["t_wh"],
            "geothermal": kwargs.get("geothermal", 1.5),
            "wc": kwargs.get("wc") if kwargs.get("wc") is not None else 0.0,
            "gamma_w": kwargs.get("gamma_w", 1.07),
            "bw": kwargs.get("bw", 1.01),
            "z_factor": kwargs.get("z", 0.9),
            "sigma": kwargs.get("sigma", 30.0),
            "n_segments": int(kwargs.get("segments", 80))
            if kwargs.get("segments") is not None else 80}, None


def _fmt_wc_display(value: float) -> str:
    """Water cut as both fraction and percentage."""
    return f"{value:.2f} ({value*100:.0f}%)"


def _variable_label(variable: str, value: float) -> str:
    lbl = SENSVARIABLE_LABELS.get(variable, variable)
    # Units come from explicit parameter metadata in SENSUNIT_MAP, never a
    # generic pressure-unit formatter.
    unit = SENSUNIT_MAP.get(variable, "psia")
    if variable == "water_cut":
        return f"{_fmt_wc_display(value)}"
    if variable == "gor":
        return f"{value:g} scf/STB"
    if variable == "tubing_id":
        return f"{value:g} {unit}"
    return f"{value:g} {unit}"


def _point_line(label: str, point: "SensitivityPoint") -> str:
    if point.classification == FEASIBLE:
        return f"  {label}: q = {point.q_op:.2f} STB/day, " \
               f"Pwf = {point.pwf_op:.2f} psia " \
               f"(residual {point.residual:.4f} psi)"
    if point.classification == MULTIPLE_OPERATING_POINTS:
        return f"  {label}: MULTIPLE_OPERATING_POINTS " \
               f"({point.n_roots} intersections) — " \
               f"requires engineering review"
    if point.classification == NO_OPERATING_POINT:
        return (f"  {label}: NO_OPERATING_POINT "
                + (f"({point.nodal.reason})" if point.nodal and
                   point.nodal.reason else ""))
    if point.classification == PHYSICALLY_INVALID:
        return f"  {label}: PHYSICALLY_INVALID"
    return f"  {label}: {point.classification}"


def _delta_line(delta: "SensitivityDelta", base_q: Optional[float]
                ) -> str:
    dq = delta.dq
    pct = delta.dq_pct
    dpwf = delta.dpwf
    dq_txt = f"{dq:+.1f} STB/day ({pct:+.1f}%)" if \
        (dq is not None and base_q) else "n/c"
    dpwf_txt = f"{dpwf:+.2f} psi" if dpwf is not None else "n/c"
    return f"    Δq = {dq_txt}   ΔPwf = {dpwf_txt}"


@registry.register("sensitivity")
def handle_calc_sensitivity(message: Dict[str, Any], tg
                            ) -> Tuple[str, Optional[bytes], Optional[str]]:
    """Handle /calc sensitivity type=<var> ... — deterministic
    one-variable sensitivity over the verified Nodal engine."""
    text = message.get("text", "")
    first_space = text.find(" ")
    args_str = text[first_space + 1:] if first_space >= 0 else ""

    kwargs = _common_string_keys(args_str, ())
    _numeric = parse_kv_args(args_str)
    _numeric.update(kwargs)
    kwargs = _numeric

    # --- Variable selection ---
    var_key = (kwargs.get("type") or "").lower()
    if var_key not in SENSVAR_KEYS:
        return "Error: type must be one of thp, id, wc, gor.\n\n" \
               + _SENSITIVITY_USAGE, None, None
    variable = SENSVAR_KEYS[var_key]
    skey = var_key  # Telegram key (thp/id/wc/gor)

    # --- Duplicate-key conflict: already resolved at parse time by
    # _common_string_keys (a comma list always beats a plain single
    # value for the same key). The numeric parser may still have added
    # a plain numeric occurrence of the sweep key; if so, demote it and
    # restore the comma list when present.
    if isinstance(kwargs.get(skey), (int, float)) and "_list" in dir():
        pass
    _str_list = [(_k, _v) for _k, _v in kwargs.items()
                 if _k == skey and isinstance(_v, str) and "," in _v]
    if _str_list:
        kwargs[skey] = _str_list[0][1]

    # --- Candidate list or bounded range ---
    token = kwargs.get(skey)
    explicit_values: List[float] = []
    err = None
    if token is not None:
        if isinstance(token, str) and "," in token:
            explicit_values, err = _parse_number_list(token)
            if err:
                return err + "\n\n" + _SENSITIVITY_USAGE, None, None
        else:
            try:
                explicit_values = [float(token)]
            except (TypeError, ValueError):
                return "Error: values must be numeric.\n\n" \
                       + _SENSITIVITY_USAGE, None, None
    lo = kwargs.get(skey + "_min"); hi = kwargs.get(skey + "_max")
    n_points = kwargs.get("n_points")
    if not explicit_values and (lo is None or hi is None):
        return "Error: provide candidate values " \
               f"({skey}=<a>,<b>,<c>) or a bounded range " \
               f"({skey}_min= / {skey}_max=).\n\n" + _SENSITIVITY_USAGE, \
            None, None
    # Range bounds may also be comma-kept strings
    if isinstance(lo, str):
        try:
            lo = float(lo)
        except (TypeError, ValueError):
            return "Error: range bounds must be numeric.\n\n" \
                   + _SENSITIVITY_USAGE, None, None
    if isinstance(hi, str):
        try:
            hi = float(hi)
        except (TypeError, ValueError):
            return "Error: range bounds must be numeric.\n\n" \
                   + _SENSITIVITY_USAGE, None, None
    if isinstance(n_points, str):
        try:
            n_points = float(n_points)
        except (TypeError, ValueError):
            return "Error: n_points must be numeric.\n\n" \
                   + _SENSITIVITY_USAGE, None, None

    # --- IPR + VLP inputs ---
    model_req = (kwargs.get("model") or "auto").lower()
    if model_req not in ("auto", "linear", "vogel", "composite"):
        return "Error: model must be one of auto, linear, vogel, " \
               "composite.\n\n" + _SENSITIVITY_USAGE, None, None
    ipr_kwargs, ipr_err = _ipr_kwargs_for_optimizer(kwargs, model_req)
    if ipr_err:
        return ipr_err, None, None
    vlp_kwargs, vlp_err = _vlp_kwargs_for_optimizer(kwargs)
    if vlp_err:
        return vlp_err, None, None
    # VLP correlation selector (same normalize/validation as /calc vlp).
    _vm = str(kwargs.get("vlp_model", "beggs_brill")).strip().lower()
    try:
        vlp_kwargs["vlp_model"] = vlp_engine._resolve_model(_vm)
    except ValueError:
        return ("Error: unknown vlp_model. Use 'beggs_brill' (default) or "
                "'hagedorn_brown'."), None, None
    # --- Numeric conversion for the VLP block: the optimizer and VLP
    # engine expect float values; string tokens (other than the sweep
    # comma list, which the optimizer substitutes per scenario) must be
    # coerced here or arithmetic silently degrades.
    _STRING_SKIP = ("vlp_model",)
    for _k in tuple(vlp_kwargs):
        if _k in _STRING_SKIP:
            continue  # kept as-is and passed through to nodal.solve
        _v = vlp_kwargs[_k]
        if isinstance(_v, str):
            if "," in _v:
                continue  # sweep token (e.g. id list mapped to
                          # tubing_id_in) — substituted per scenario
            try:
                vlp_kwargs[_k] = float(_v)
            except (TypeError, ValueError):
                return f"Error: value for {_k} must be numeric.\n\n" \
                       + _SENSITIVITY_USAGE, None, None

    base_key = "base_" + skey
    base_value = kwargs.get(base_key)
    if base_value is not None:
        try:
            base_value = float(base_value)
        except (TypeError, ValueError):
            return "Error: base value must be numeric.\n\n" \
                   + _SENSITIVITY_USAGE, None, None

    opt = production_optimizer.ProductionOptimizer()
    try:
        result = opt.sensitivity(
            variable, explicit_values=explicit_values or None,
            lo=float(lo) if lo is not None else None,
            hi=float(hi) if hi is not None else None,
            n_points=int(n_points) if n_points is not None else None,
            base_value=base_value, base_kwargs=vlp_kwargs,
            ipr_kwargs=ipr_kwargs)
    except production_optimizer.OptimizationError as _e:
        if _e.kind == "PHYSICALLY_INVALID":
            return ("Engineering Guardrail — inputs rejected as physically "
                    "invalid.\n" + _e.message), None, None
        if _e.kind == "MISSING_DATA":
            return ("Error: " + _e.message + "\n\n" + _SENSITIVITY_USAGE), \
                None, None
        return ("Engineering Guardrail — " + _e.message + "\n\n"
                + _SENSITIVITY_USAGE), None, None
    except Exception as _e:
        return f"Sensitivity analysis error: {_e}.", None, None

    # --- Response lines ---
    var_display = SENSVARIABLE_LABELS.get(variable, variable)
    lines = [f"{var_display} Sensitivity Result (CALCULATED — "
             "deterministic layer over the verified IPR/VLP/Nodal "
             "engines)", "=" * 60]
    lines.append(f"Variable: {var_display}")
    bp = result.base_point
    lines.append("")
    lines.append("BASE CASE")
    if bp is not None and bp.nodal is not None:
        lines.append("  " + skey + " = " + _variable_label(variable, result.base_value))
        lines.append(f"  VLP model: {bp.nodal.vlp_model}")
        lines.append(f"  Nodal status: {bp.nodal.status}")
        if bp.q_op is not None:
            lines.append(f"  q_op = {bp.q_op:.2f} STB/day")
            lines.append(f"  Pwf_op = {bp.pwf_op:.2f} psia")
            lines.append(f"  Residual = {bp.residual:.4f} psi")
        else:
            lines.append(f"  Classification: {bp.classification}"
                         + (f" ({bp.nodal.reason})" if bp.nodal and
                            bp.nodal.reason else ""))
    lines.append("")
    lines.append("SCENARIOS")
    for p, d in zip(result.points, result.deltas):
        lines.append(_point_line(_variable_label(variable,
                                                 p.parameter_value), p))
        if p.classification == FEASIBLE and bp.q_op is not None:
            lines.append(_delta_line(d, bp.q_op))
    for w in result.warnings:
        lines.append(f"NOTE: {w}")
    lines.append("")
    lines.append("Interpretation (engine layer): this is a calculated "
                 "model sensitivity — field implementation requires "
                 "confirmation of separator pressure, choke limits, "
                 "tubing integrity, facility capacity and sand/erosion "
                 "constraints.")
    lines.append("")
    lines.append("NOTE: Results are CALCULATED MODEL RESULTS — NOT "
                 "measured field data.")
    text_out = "\n".join(lines)

    # --- Plot: operating rate vs parameter (+ optional Pwf) ---
    png = None
    if bool(kwargs.get("plot")):
        xs = [p.parameter_value for p in result.points]
        ys_q = [p.q_op for p in result.points]
        ys_p = [p.pwf_op for p in result.points]
        x_labels = [format(_variable_label(variable, v), ) for v in xs] \
            if variable in ("thp", "tubing_id", "water_cut", "gor") else None
        well = f"Calculated {var_display} Sensitivity"
        if any(_q is not None for _q in ys_q):
            pairs = [(x, y) for x, y in zip(xs, ys_q) if y is not None]
            if len(pairs) >= 2:
                png = generate_pvt_plot(
                    "sensitivity_plot",
                    [_p[0] for _p in pairs],
                    [[_p[1] for _p in pairs]], None, well,
                    labels=[f"Operating rate (base {_fmt_base(result)})"],
                )
        if png is None:
            text_out += ("\n\nNOTE: could not generate the sensitivity "
                         "plot (insufficient feasible points).")
        else:
            text_out += ("\n\nCalculated sensitivity plot attached: "
                         "operating rate vs " + var_display
                         + ". CALCULATED MODEL RESULTS — NOT measured "
                         "field data.")
    return text_out, png, None


def _fmt_base(result: "SensitivityResult") -> str:
    v = result.base_value
    # Units come from explicit parameter metadata in SENSUNIT_MAP, never a
    # generic pressure-unit formatter.
    unit = SENSUNIT_MAP.get(result.variable, "psia")
    if result.variable == "water_cut":
        return _fmt_wc_display(v)
    if result.variable == "gor":
        return f"{v:g} scf/STB"
    return f"{v:g} {unit}"


@registry.register("optimize")
def handle_calc_optimize(message: Dict[str, Any], tg
                         ) -> Tuple[str, Optional[bytes], Optional[str]]:
    """Handle /calc optimize type=<var> var=<vals> objective=... —
    deterministic constrained candidate comparison over the verified
    Nodal engine."""
    text = message.get("text", "")
    first_space = text.find(" ")
    args_str = text[first_space + 1:] if first_space >= 0 else ""

    kwargs = _common_string_keys(args_str, ())
    _numeric = parse_kv_args(args_str)
    _numeric.update(kwargs)
    kwargs = _numeric

    # --- Variable ---
    var_key = (kwargs.get("type") or "").lower()
    if var_key not in SENSVAR_KEYS:
        return "Error: type must be one of thp, id, wc, gor.\n\n" \
               + _OPTIMIZE_USAGE, None, None
    variable = SENSVAR_KEYS[var_key]
    skey = var_key  # Telegram key (thp/id/wc/gor)

    # --- Duplicate-key conflict: same parse-time resolution as the
    # sensitivity handler — restore the comma list if the numeric parser
    # overwrote it with a plain numeric value.
    _str_list = [(_k, _v) for _k, _v in kwargs.items()
                 if _k == skey and isinstance(_v, str) and "," in _v]
    if _str_list:
        kwargs[skey] = _str_list[0][1]

    # --- Candidate list (required) ---
    token = kwargs.get(skey)
    values: List[float] = []
    if token is not None and isinstance(token, str) and "," in token:
        values, err = _parse_number_list(token)
        if err:
            return err + "\n\n" + _OPTIMIZE_USAGE, None, None
    if len(values) < 2:
        return "Error: candidate optimization requires at least two " \
               f"values for {skey} (comma-separated, " \
               f"e.g. {skey}=1.995,2.5,3.0).\n\n" + _OPTIMIZE_USAGE, \
            None, None

    # --- Objective ---
    objective = (kwargs.get("objective") or "").lower()
    if not objective:
        return "Error: objective= is required (objective=max_oil_rate).\n\n" \
               + _OPTIMIZE_USAGE, None, None

    # --- IPR + VLP inputs ---
    model_req = (kwargs.get("model") or "auto").lower()
    if model_req not in ("auto", "linear", "vogel", "composite"):
        return "Error: model must be one of auto, linear, vogel, " \
               "composite.\n\n" + _OPTIMIZE_USAGE, None, None
    ipr_kwargs, ipr_err = _ipr_kwargs_for_optimizer(kwargs, model_req)
    if ipr_err:
        return ipr_err, None, None
    vlp_kwargs, vlp_err = _vlp_kwargs_for_optimizer(kwargs)
    if vlp_err:
        return vlp_err, None, None
    # VLP correlation selector (same normalize/validation as /calc vlp).
    _vm = str(kwargs.get("vlp_model", "beggs_brill")).strip().lower()
    try:
        vlp_kwargs["vlp_model"] = vlp_engine._resolve_model(_vm)
    except ValueError:
        return ("Error: unknown vlp_model. Use 'beggs_brill' (default) or "
                "'hagedorn_brown'."), None, None
    # --- Numeric conversion for the VLP block (same rule as the
    # sensitivity handler — skip the candidate key itself, whose list
    # the optimizer substitutes per candidate).
    _STRING_SKIP = ("vlp_model",)
    for _k in tuple(vlp_kwargs):
        if _k in _STRING_SKIP:
            continue  # kept as-is and passed through to nodal.solve
        _v = vlp_kwargs[_k]
        if isinstance(_v, str):
            if "," in _v:
                continue  # sweep token — substituted per candidate
            try:
                vlp_kwargs[_k] = float(_v)
            except (TypeError, ValueError):
                return f"Error: value for {_k} must be numeric.\n\n" \
                       + _OPTIMIZE_USAGE, None, None

    # --- Constraints ---
    constraints: Dict[str, Any] = {}
    for _cname in ("min_pwf", "max_drawdown", "max_liquid_rate",
                   "max_water_cut", "min_thp", "max_thp", "max_gor"):
        _v = kwargs.get(_cname)
        if _v is not None:
            try:
                constraints[_cname] = float(_v)
            except (TypeError, ValueError):
                return f"Error: {_cname} must be numeric.", None, None

    opt = production_optimizer.ProductionOptimizer()
    try:
        result = opt.optimize(
            variable, values=values, objective=objective,
            constraints=constraints or None,
            base_kwargs=vlp_kwargs, ipr_kwargs=ipr_kwargs)
    except production_optimizer.OptimizationError as _e:
        if _e.kind == "PHYSICALLY_INVALID":
            return ("Engineering Guardrail — inputs rejected as physically "
                    "invalid.\n" + _e.message), None, None
        if _e.kind in ("MISSING_DATA", "UNSUPPORTED_OBJECTIVE",
                       "UNSUPPORTED_CONSTRAINT", "UNSUPPORTED_VARIABLE"):
            return ("Error: " + _e.message + "\n\n" + _OPTIMIZE_USAGE), \
                None, None
        return ("Engineering Guardrail — " + _e.message + "\n\n"
                + _OPTIMIZE_USAGE), None, None
    except Exception as _e:
        return f"Optimization error: {_e}.", None, None

    # --- Response lines ---
    var_display = SENSVARIABLE_LABELS.get(variable, variable)
    lines = ["Production Optimization Result (CALCULATED — deterministic "
             "layer over the verified IPR/VLP/Nodal engines)", "=" * 60]
    lines.append(f"Objective: {result.objective}")
    lines.append(f"Variable optimized: {var_display}")
    lines.append("")
    bc = result.base_candidate
    if bc is not None:
        lines.append("BASE CASE")
        lines.append("  " + skey + " = " + _variable_label(variable, bc.parameter_value))
        if bc.point.q_op is not None:
            lines.append(f"  q_op = {bc.point.q_op:.2f} STB/day")
            lines.append(f"  Pwf_op = {bc.point.pwf_op:.2f} psia")
        else:
            lines.append(f"  Status: {bc.classification}")
    lines.append("")
    lines.append("CANDIDATES")
    for c in result.candidates:
        lines.append("  " + skey + " = " + _variable_label(
            variable, c.parameter_value)
                     + ": " + c.classification)
        if c.point.q_op is not None:
            lines.append(f"    q_op = {c.point.q_op:.2f} STB/day, "
                         f"Pwf_op = {c.point.pwf_op:.2f} psia, "
                         f"residual {c.point.residual:.4f} psi")
            lines.append(f"    VLP model: {c.point.nodal.vlp_model}")
        if c.review_required:
            lines.append("    REVIEW REQUIRED (multiple operating points "
                         "or non-convergence — no root selected "
                         "automatically).")
        for cv in c.constraint_violations:
            lines.append(f"    Constraint violated: {cv.constraint} "
                         f"limit={cv.limit:g}, actual={cv.actual:g}")
    lines.append("")
    best = result.best
    if best is not None:
        lines.append("BEST FEASIBLE CANDIDATE")
        lines.append("  " + skey + " = " + _variable_label(variable, best.parameter_value))
        lines.append(f"  q_op = {best.point.q_op:.2f} STB/day")
        lines.append(f"  Pwf_op = {best.point.pwf_op:.2f} psia")
        if bc is not None and bc.point.q_op is not None \
                and best.point.q_op is not None:
            dq = best.point.q_op - bc.point.q_op
            pct = 100.0 * dq / bc.point.q_op if bc.point.q_op else None
            dpwf = (best.point.pwf_op - bc.point.pwf_op
                    if best.point.pwf_op is not None
                    and bc.point.pwf_op is not None else None)
            lines.append(f"  Δq = {dq:+.1f} STB/day "
                         + (f"({pct:+.1f}%)" if pct is not None else ""))
            if dpwf is not None:
                lines.append(f"  ΔPwf = {dpwf:+.2f} psi")
        lines.append(f"  Residual: {best.point.residual:.4f} psi")
        lines.append("  (Best feasible candidate within the supplied "
                     "model and constraints — not a real-world "
                     "operating condition.)")
    elif result.all_infeasible:
        lines.append("RESULT: ALL CANDIDATES INFEASIBLE under the "
                     "supplied constraints — no feasible optimum exists "
                     "in the candidate set.")
    else:
        lines.append("RESULT: no feasible candidate achieved the "
                     "objective (candidates either failed to converge, "
                     "had no operating point, or needed engineering "
                     "review).")
    for w in result.warnings:
        lines.append(f"NOTE: {w}")
    lines.append("")
    lines.append("Interpretation (engine layer): model sensitivity is "
                 "not a field instruction. Field implementation requires "
                 "confirmation of separator pressure, choke limits, "
                 "tubing integrity, facility capacity and sand/erosion "
                 "constraints.")
    lines.append("")
    lines.append("NOTE: Results are CALCULATED MODEL RESULTS — NOT "
                 "measured field data.")
    text_out = "\n".join(lines)

    # --- Plot: comparison of candidates ---
    png = None
    if bool(kwargs.get("plot")):
        pairs = [(c.parameter_value, c.point.q_op)
                 for c in result.candidates if c.point.q_op is not None]
        if len(pairs) >= 2:
            png = generate_pvt_plot(
                "optimization_plot",
                [_p[0] for _p in pairs],
                [[_p[1] for _p in pairs]], None,
                f"Calculated {var_display} Candidate Comparison",
                labels=["Operating rate"],
            )
        if png is None:
            text_out += ("\n\nNOTE: could not generate the comparison "
                         "plot (fewer than two feasible candidates).")
        else:
            text_out += ("\n\nCalculated comparison plot attached: "
                         "operating rate per candidate. CALCULATED MODEL "
                         "RESULTS — NOT measured field data.")
    return text_out, png, None
