"""
Visualization module for PVT engineering plots.

Generates publication-quality PNG charts using matplotlib with:
- Professional dark theme
- Correct axis labels and units
- Saturation pressure markers
- Trend annotations
- Publication-quality output (configurable DPI)
"""

from __future__ import annotations

import io
import logging
from typing import Dict, List, Optional, Tuple

from config import (
    PLOT_DEFAULT_DPI,
    PLOT_FIGURE_WIDTH,
    PLOT_FIGURE_HEIGHT,
    PLOT_BG_COLOR,
    PLOT_AXES_BG_COLOR,
    PLOT_AXES_EDGE_COLOR,
    PLOT_TEXT_COLOR,
    PLOT_TITLE_COLOR,
    PLOT_TICK_COLOR,
    PLOT_GRID_COLOR,
)
from constants import PVT_PLOT_RULES
from logging_config import get_logger

logger = get_logger(__name__)


def _fix_arabic_text(text: str) -> str:
    """
    Reshape and reorder Arabic text for correct rendering in matplotlib.

    Matplotlib (via its underlying font-rendering engine) draws Arabic
    characters in their isolated forms and in logical storage order, not
    their correct joined/contextual letterforms in right-to-left visual
    order -- which is why Arabic titles previously appeared garbled/reversed
    in generated charts. `arabic_reshaper` joins letters into their correct
    contextual forms; `python-bidi` then reorders the text for correct
    right-to-left visual display. Falls back to the original text (English
    parts of a mixed title are unaffected either way) if the libraries
    aren't installed, so a missing dependency degrades gracefully rather
    than crashing plot generation.
    """
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
    except ImportError:
        logger.warning(
            "arabic_reshaper/python-bidi not installed -- Arabic chart "
            "titles will render without RTL correction. Add "
            "'arabic-reshaper' and 'python-bidi' to requirements.txt."
        )
        return text

    # Reshape+reorder line by line so any English lines in a mixed
    # multi-line title (e.g. "Arabic title\nEnglish title") aren't disturbed.
    fixed_lines = []
    for line in text.split("\n"):
        if any("\u0600" <= ch <= "\u06FF" for ch in line):
            reshaped = arabic_reshaper.reshape(line)
            fixed_lines.append(get_display(reshaped))
        else:
            fixed_lines.append(line)
    return "\n".join(fixed_lines)


def generate_pvt_plot(
    relationship_key: str,
    pressures: List[float],
    values: List[float],
    saturation_pressure: Optional[float] = None,
    well_name: Optional[str] = None,
) -> Optional[bytes]:
    """
    Generate a PVT property vs pressure plot.

    Args:
        relationship_key: The PVT relationship key (e.g., "bo_vs_p").
        pressures: List of pressure values (psia), sorted ascending.
        values: List of corresponding property values.
        saturation_pressure: Optional Pb or Pd value for annotation.
        well_name: Optional well name for the title.

    Returns:
        PNG image bytes, or None on failure.
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
    except ImportError as exc:
        logger.error("matplotlib not available: %s", exc)
        return None

    rule = PVT_PLOT_RULES.get(relationship_key)
    if not rule:
        logger.warning("Unknown plot type: %s", relationship_key)
        return None

    # Sort data by pressure
    sorted_data = sorted(zip(pressures, values))
    sorted_p = [p for p, _ in sorted_data]
    sorted_v = [v for _, v in sorted_data]

    # Create figure
    fig, ax = plt.subplots(
        figsize=(PLOT_FIGURE_WIDTH, PLOT_FIGURE_HEIGHT),
        dpi=PLOT_DEFAULT_DPI,
        facecolor=PLOT_BG_COLOR,
    )
    ax.set_facecolor(PLOT_AXES_BG_COLOR)

    # Plot data
    color = rule.get("plot_color", "#F39C12")
    ax.plot(sorted_p, sorted_v, "o-", color=color, linewidth=2.5, markersize=7, zorder=5)

    # Saturation pressure marker
    if saturation_pressure:
        ax.axvline(
            x=saturation_pressure,
            color="#F39C12",
            linestyle="--",
            linewidth=2,
            alpha=0.8,
            label=f"P{'b' if 'bo' in relationship_key or 'rs' in relationship_key else 'd'} = {saturation_pressure:.0f} psia",
        )
        ax.legend(loc="best", fontsize=10, framealpha=0.7)

    # Axis labels
    ax.set_xlabel(rule["x_axis"], color=PLOT_TEXT_COLOR, fontsize=12, fontweight="bold")
    ax.set_ylabel(rule["y_label"], color=PLOT_TEXT_COLOR, fontsize=12, fontweight="bold")

    # Title
    title = f"{rule['title_ar']}\n{rule['title_en']}"
    if well_name:
        title += f"\nWell: {well_name}"
    ax.set_title(_fix_arabic_text(title), color=PLOT_TITLE_COLOR, fontsize=14, fontweight="bold", pad=15)

    # Style axes
    for spine in ax.spines.values():
        spine.set_color(PLOT_AXES_EDGE_COLOR)
        spine.set_linewidth(1.5)
    ax.tick_params(colors=PLOT_TICK_COLOR, labelsize=10, width=1.5, length=6)
    ax.tick_params(which='minor', width=1, length=4, colors=PLOT_GRID_COLOR)

    # Grid - Major and Minor
    ax.grid(True, which='major', alpha=0.4, color=PLOT_GRID_COLOR, linestyle="-", linewidth=0.8)
    ax.grid(True, which='minor', alpha=0.15, color=PLOT_GRID_COLOR, linestyle="--", linewidth=0.5)
    ax.minorticks_on()

    # Watermark
    ax.text(
        0.98, 0.02,
        "Generated by Petroleum Engineering AI Bot",
        transform=ax.transAxes,
        fontsize=9,
        color=PLOT_TEXT_COLOR,
        ha="right",
        va="bottom",
        alpha=0.3,
        fontstyle='italic'
    )

    # Layout
    plt.tight_layout(pad=1.5)

    # Save to bytes
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=PLOT_DEFAULT_DPI, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)

    png_bytes = buf.read()
    logger.info("Plot generated: %s (%d bytes)", relationship_key, len(png_bytes))
    return png_bytes


def generate_bo_rs_composite_plot(
    pressures: List[float],
    bo_values: List[float],
    rs_values: List[float],
    pb: Optional[float] = None,
    well_name: Optional[str] = None,
) -> Optional[bytes]:
    """
    Generate a composite Bo and Rs plot on dual y-axes.

    Args:
        pressures: Pressure values (psia).
        bo_values: Bo values (rb/STB).
        rs_values: Rs values (scf/STB).
        pb: Bubble point pressure.
        well_name: Optional well name.

    Returns:
        PNG image bytes, or None on failure.
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return None

    sorted_data = sorted(zip(pressures, bo_values, rs_values))
    sorted_p = [d[0] for d in sorted_data]
    sorted_bo = [d[1] for d in sorted_data]
    sorted_rs = [d[2] for d in sorted_data]

    fig, ax1 = plt.subplots(
        figsize=(PLOT_FIGURE_WIDTH, PLOT_FIGURE_HEIGHT),
        dpi=PLOT_DEFAULT_DPI,
        facecolor=PLOT_BG_COLOR,
    )
    ax1.set_facecolor(PLOT_AXES_BG_COLOR)

    # Bo on left axis
    color_bo = "#1A5276"
    ax1.plot(sorted_p, sorted_bo, "o-", color=color_bo, linewidth=2.5, markersize=7, label="Bo (rb/STB)")
    ax1.set_xlabel("Pressure (psia)", color=PLOT_TEXT_COLOR, fontsize=12, fontweight="bold")
    ax1.set_ylabel("Bo (rb/STB)", color=color_bo, fontsize=12, fontweight="bold")
    ax1.tick_params(axis="y", colors=color_bo, labelsize=10)

    # Rs on right axis
    ax2 = ax1.twinx()
    color_rs = "#E67E22"
    ax2.plot(sorted_p, sorted_rs, "s-", color=color_rs, linewidth=2.5, markersize=7, label="Rs (scf/STB)")
    ax2.set_ylabel("Rs (scf/STB)", color=color_rs, fontsize=12, fontweight="bold")
    ax2.tick_params(axis="y", colors=color_rs, labelsize=10)

    # Pb line
    if pb:
        for ax in [ax1, ax2]:
            ax.axvline(x=pb, color="#F39C12", linestyle="--", linewidth=2, alpha=0.8)

    # Title
    title = "Bo & Rs vs Pressure"
    if well_name:
        title += f"\nWell: {well_name}"
    ax1.set_title(title, color=PLOT_TITLE_COLOR, fontsize=14, fontweight="bold", pad=15)

    # Style
    for spine in ax1.spines.values():
        spine.set_color(PLOT_AXES_EDGE_COLOR)
    ax1.grid(True, alpha=0.3, color=PLOT_GRID_COLOR)
    ax1.tick_params(colors=PLOT_TICK_COLOR, labelsize=10)

    # Combined legend
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="best", fontsize=10, framealpha=0.7)

    plt.tight_layout(pad=1.5)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=PLOT_DEFAULT_DPI, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def format_plot_response(
    relationship_key: str,
    pressures: Optional[List[float]] = None,
    values: Optional[List[float]] = None,
    pb: Optional[float] = None,
    well_name: Optional[str] = None,
) -> Tuple[str, Optional[bytes]]:
    """
    Format a complete plot response (text + optional PNG).

    Args:
        relationship_key: The PVT relationship key.
        pressures: Optional pressure data.
        values: Optional property values.
        pb: Optional saturation pressure.
        well_name: Optional well name.

    Returns:
        Tuple of (text_response, png_bytes_or_none).
    """
    rule = PVT_PLOT_RULES.get(relationship_key)
    if not rule:
        return f"Unknown plot type. Available: {', '.join(PVT_PLOT_RULES.keys())}", None

    # Build text response
    lines = [
        f"{rule['title_ar']}",
        f"{rule['title_en']}",
        "=" * 50,
        f"Definition: {rule['definition']}",
        f"X-axis: {rule['x_axis']}",
        f"Y-axis: {rule['y_axis']}",
        "",
        f"Shape: {rule['shape']}",
        f"Pivot: {rule['pivot']}",
        "",
    ]

    if rule.get("above_saturation"):
        lines.append(f"Above saturation: {rule['above_saturation']}")
    if rule.get("at_saturation"):
        lines.append(f"At saturation: {rule['at_saturation']}")
    if rule.get("below_saturation"):
        lines.append(f"Below saturation: {rule['below_saturation']}")

    lines.append("")
    lines.append("Common Mistakes:")
    for mistake in rule.get("common_ai_mistakes", []):
        lines.append(f"  ! {mistake}")

    text_response = "\n".join(lines)

    # Generate PNG if data provided
    png_bytes = None
    if pressures and values:
        png_bytes = generate_pvt_plot(relationship_key, pressures, values, pb, well_name)

    return text_response, png_bytes
