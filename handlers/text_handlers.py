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
from services.visualization import format_plot_response
from logging_config import get_logger

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
    kwargs = parse_kv_args(args_str)

    result = run_exact_calculation(formula_key, kwargs)
    return result, None, None


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
