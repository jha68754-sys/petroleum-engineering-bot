"""
Calculation engine for exact petroleum engineering formulas.

Wraps the formula registry with a unified interface for the handler layer.
Handles input parsing, validation, and formatted output.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from services.pvt_engine import run_exact_calculation, run_correlation, run_unit_conversion

logger = logging.getLogger("pvt_bot.services.calculation_engine")


def execute_calculation(
    formula_key: str,
    kwargs: Dict[str, float],
) -> str:
    """
    Execute an exact petroleum engineering calculation.

    This is a thin wrapper around pvt_engine.run_exact_calculation
    that provides additional error context for the handler layer.

    Args:
        formula_key: The formula identifier (e.g., "ooip", "darcy").
        kwargs: Input parameters as float values.

    Returns:
        Formatted calculation result string.
    """
    try:
        return run_exact_calculation(formula_key, kwargs)
    except Exception as exc:
        logger.exception("Calculation error for formula=%s", formula_key)
        return f"Calculation error: {exc}. Please check your inputs."


def execute_correlation(
    correlation_key: str,
    kwargs: Dict[str, float],
) -> str:
    """
    Execute a PVT correlation estimate.

    Args:
        correlation_key: The correlation identifier.
        kwargs: Input parameters as float values.

    Returns:
        Formatted correlation result string.
    """
    try:
        return run_correlation(correlation_key, kwargs)
    except Exception as exc:
        logger.exception("Correlation error for key=%s", correlation_key)
        return f"Correlation error: {exc}. Please check your inputs."


def execute_conversion(
    value: float,
    from_unit: str,
    to_unit: str,
) -> str:
    """
    Execute a unit conversion.

    Args:
        value: Numeric value to convert.
        from_unit: Source unit name.
        to_unit: Target unit name.

    Returns:
        Formatted conversion result string.
    """
    try:
        result = run_unit_conversion(value, from_unit, to_unit)
        return result if result else f"Unknown conversion: {from_unit} -> {to_unit}"
    except Exception as exc:
        logger.exception("Conversion error: %s -> %s", from_unit, to_unit)
        return f"Conversion error: {exc}"


def _parse_numeric_list(val_str: str):
    """
    Parse a value that may be a single number or a comma-separated numeric
    list (e.g. cf=-1000000,300000,350000,400000).

    Returns:
        A float for a single value, or a list of floats for a
        comma-separated sequence. Returns None if the value is not valid
        numeric data (with the caller expected to raise/report).
    """
    val_str = val_str.strip()
    if "," in val_str:
        values = []
        for tok in val_str.split(","):
            tok = tok.strip()
            if not tok:
                return None  # malformed: trailing/leading/double comma
            try:
                v = float(tok)
            except ValueError:
                return None  # malformed: non-numeric token in the list
            if not (v == v) or v in (float("inf"), float("-inf")):  # non-finite
                return None
            values.append(v)
        if len(values) < 2:
            return None  # malformed: e.g. "500," yielded fewer than 2 values
        return values
    # Scalar value: skip non-numeric strings instead of raising ValueError,
    # so that string keys (e.g. model=vogel) are silently dropped rather
    # than crashing the whole command parser.
    try:
        v = float(val_str)
    except ValueError:
        return None
    if not (v == v) or v in (float("inf"), float("-inf")):
        return None
    return v


def parse_kv_args(args_str: str) -> Dict[str, Any]:
    """
    Parse key=value arguments from a command string.

    Supports formats like:
        area=500 h=50 phi=0.2 sw=0.3 bo=1.3
        cf=-1000000,300000,350000,400000   (comma-separated numeric list)

    Args:
        args_str: Space-separated key=value pairs.

    Returns:
        Dictionary mapping string keys to float values, or to lists of
        floats when the value is a comma-separated numeric sequence.
        Comma-separated lists are only accepted for fully valid finite
        numeric sequences; malformed lists cause the key to be rejected
        with a warning so the engine can report a specific error.
    """
    result: Dict[str, Any] = {}
    if not args_str or not args_str.strip():
        return result

    parts = args_str.split()
    for part in parts:
        if "=" not in part:
            logger.warning("Skipping malformed argument: %s", part)
            continue
        key, _, val_str = part.partition("=")
        parsed = _parse_numeric_list(val_str)
        if parsed is None:
            logger.warning(
                "Cannot parse valid numeric data from: %s (key=%s) -- "
                "malformed or non-finite numeric sequence",
                val_str, key,
            )
            continue
        result[key.strip().lower()] = parsed

    return result
