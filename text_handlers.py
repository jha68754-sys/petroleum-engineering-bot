"""
Text command handlers for the Petroleum Engineering Bot.

Handles all text-based commands: /classify, /calc, /estimate, /convert,
/plot, /check, /pvto, /pvdo, /pvtg, /pvdg, /export_sim, /eclipse,
/cmg, /report, /reset, /start, /analyze.

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
    from state import FILE_CONTEXT, IMAGE_CONTEXT, _delete_temp_image
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
    """Handle /plot <type> [p=v1,v2 v=v1,v2] [pb=val] [well=name] command."""
    text = message.get("text", "")
    parts = text.split(None, 1)
    if len(parts) < 2:
        return (
            "Usage: /plot <type> [p=v1,v2,... v=v1,v2,...] [pb=val] [well=name]\n\n"
            "Types: bo, rs, bg, z, viscosity, mu_g, dropout, cgr,\n"
            "  density, vrel, cce, phase_envelope\n\n"
            "Example: /plot bo p=500,1000,1500,2000 v=1.15,1.18,1.20,1.17 pb=1500"
        ), None, None

    # Parse arguments
    args_str = parts[1]
    pressures: Optional[List[float]] = None
    values: Optional[List[float]] = None
    pb: Optional[float] = None
    well_name: Optional[str] = None

    for token in args_str.split():
        if token.startswith("p="):
            pressures = [float(x) for x in token[2:].split(",")]
        elif token.startswith("v="):
            values = [float(x) for x in token[2:].split(",")]
        elif token.startswith("pb="):
            pb = float(token[3:])
        elif token.startswith("well="):
            well_name = token[5:]

    # Resolve relationship key
    rel_key = resolve_relationship_key(parts[1].split()[0] if " " not in args_str else parts[1].split()[0])
    if not rel_key:
        return (
            f"Unknown plot type: {parts[1].split()[0]}\n"
            f"Available: bo, rs, bg, z, viscosity, mu_g, dropout, cgr,\n"
            f"  density, vrel, cce, phase_envelope"
        ), None, None

    text_response, png_bytes = format_plot_response(rel_key, pressures, values, pb, well_name)
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
    """Handle /report command."""
    from pathlib import Path
    template_path = Path("templates/pvt_report.txt")
    if template_path.exists():
        result = template_path.read_text(encoding="utf-8")
    else:
        result = "PVT Report template not found. Using default structure.\n\nUse /analyze after uploading a PVT report for detailed analysis."
    return result, None, None


# Glossary command removed


def handle_graph(message: Dict[str, Any], tg) -> Tuple[str, Optional[bytes], Optional[str]]:
    """Handle /graph command."""
    chat_id = message.get("chat", {}).get("id", "")
    from state import FILE_CONTEXT
    context = FILE_CONTEXT.get(chat_id)
    if not context:
        return "No document uploaded for graphing. Upload a file first.", None, None
    return None, None, None

def handle_graph(message: Dict[str, Any], tg) -> Tuple[str, Optional[bytes], Optional[str]]:
    """Handle /graph command."""
    chat_id = message.get("chat", {}).get("id", "")
    from state import FILE_CONTEXT
    context = FILE_CONTEXT.get(chat_id)
    if not context:
        return "No document uploaded for graphing. Upload a file first.", None, None
    return None, None, None

@registry.register("graph", aliases=["plot"])
def handle_graph_cmd(message: Dict[str, Any], tg) -> Tuple[str, Optional[bytes], Optional[str]]:
    return handle_graph(message, tg)

@registry.register("analyze", aliases=["document", "doc"])
def handle_analyze(message: Dict[str, Any], tg) -> Tuple[str, Optional[bytes], Optional[str]]:
    """Handle /analyze command."""
    chat_id = message.get("chat", {}).get("id", "")
    from state import FILE_CONTEXT
    context = FILE_CONTEXT.get(chat_id)
    if not context:
        return "No document uploaded. Upload a PDF, DOCX, Excel, or CSV file first.", None, None
    return None, None, None  # Signal that AI analysis is needed


@registry.register("surface_separator", aliases=["separator"])
def handle_surface_separator(message: Dict[str, Any], tg) -> Tuple[str, Optional[bytes], Optional[str]]:
    """Handle /surface_separator command."""
    return SURFACE_SEPARATOR_ANSWER, None, None
