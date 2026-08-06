"""
Darcy Law Flow Calculator for linear and radial flow regimes.
"""

from __future__ import annotations
import math

def calculate_radial_darcy_flow(k_md: float, h_ft: float, p_r: float, p_wf: float, mu_cp: float, bo: float, re_ft: float, rw_ft: float, s: float = 0.0) -> float:
    """
    Calculate radial steady-state flow rate using Darcy's law:
    q = (7.08 * k * h * (Pr - Pwf)) / (mu * Bo * (ln(re/rw) + S))
    Reference: Tiab & Donaldson, Petrophysics.
    """
    if mu_cp <= 0 or bo <= 0 or rw_ft <= 0 or re_ft <= rw_ft:
        raise ValueError("Invalid fluid or reservoir radii parameters.")
    denominator = mu_cp * bo * (math.log(re_ft / rw_ft) + s)
    if denominator <= 0:
        return 0.0
    q = (7.08 * k_md * h_ft * (p_r - p_wf)) / denominator
    return round(max(0.0, q), 2)
