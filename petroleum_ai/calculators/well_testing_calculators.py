"""
Well Testing Engineering Calculators: Skin factor, Radius of investigation, Horner buildup, Transmissibility.
"""

from __future__ import annotations
import math

def calculate_skin_factor(delta_p_skin_psi: float, m_psi_cycle: float) -> float:
    """
    Calculate skin factor s from pressure drop due to skin and semi-log slope m:
    s = 1.151 * ((delta_p_skin / m) - log10(k / (phi * mu * c_t * r_w^2)) + 3.23)
    Simplified standard form: s = 0.869 * (delta_p_skin / m) -- or direct calculation.
    """
    if m_psi_cycle <= 0:
        raise ValueError("Semi-log slope m must be greater than zero.")
    s = 1.151 * (delta_p_skin_psi / m_psi_cycle)
    return round(s, 2)

def calculate_radius_of_investigation(t_hrs: float, k_md: float, phi: float, mu_cp: float, c_t_psi_1: float) -> float:
    """
    Calculate Radius of Investigation (r_i) in feet:
    r_i = 0.029 * sqrt((k * t) / (phi * mu * c_t))
    Reference: Lee, Well Testing.
    """
    if phi <= 0 or mu_cp <= 0 or c_t_psi_1 <= 0 or t_hrs < 0 or k_md < 0:
        raise ValueError("Invalid physical parameters for radius of investigation calculation.")
    r_i = 0.029 * math.sqrt((k_md * t_hrs) / (phi * mu_cp * c_t_psi_1))
    return round(r_i, 2)

def calculate_transmissibility(k_md: float, h_ft: float, mu_cp: float) -> float:
    """
    Calculate Formation Transmissibility (kh / mu) in md-ft/cp.
    """
    if mu_cp <= 0:
        raise ValueError("Viscosity must be greater than zero.")
    t_val = (k_md * h_ft) / mu_cp
    return round(t_val, 2)
