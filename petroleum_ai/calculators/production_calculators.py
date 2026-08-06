"""
Production Engineering Calculators: Vogel IPR, Productivity Index, Arps Decline Curve Analysis.
"""

from __future__ import annotations
import math

def calculate_productivity_index(q_stb_day: float, pr_psi: float, pwf_psi: float) -> float:
    """
    Calculate Productivity Index (PI) J in STB/day/psi:
    J = q / (Pr - Pwf)
    """
    drawdown = pr_psi - pwf_psi
    if drawdown <= 0:
        raise ValueError("Reservoir pressure Pr must be greater than flowing bottom-hole pressure Pwf.")
    j = q_stb_day / drawdown
    return round(j, 3)

def calculate_vogel_q_max(q_current: float, pwf: float, pr: float) -> float:
    """
    Calculate maximum flow rate q_max using Vogel's IPR equation:
    q / q_max = 1.0 - 0.2*(Pwf/Pr) - 0.8*(Pwf/Pr)^2
    """
    if pr <= 0 or pwf < 0 or pwf > pr:
        raise ValueError("Invalid pressure inputs for Vogel IPR calculation.")
    ratio = pwf / pr
    denominator = 1.0 - 0.2 * ratio - 0.8 * (ratio ** 2)
    if denominator <= 0:
        raise ValueError("Denominator approaches zero or negative in Vogel equation.")
    q_max = q_current / denominator
    return round(q_max, 2)

def calculate_arps_decline(q_i: float, b: float, d_i: float, t_years: float) -> float:
    """
    Calculate future production rate q(t) using Arps decline equation:
    Exponential (b=0): q = q_i * exp(-d_i * t)
    Hyperbolic (0 < b < 1): q = q_i / (1 + b * d_i * t)^(1/b)
    Harmonic (b=1): q = q_i / (1 + d_i * t)
    """
    if q_i < 0 or d_i < 0 or t_years < 0:
        raise ValueError("Invalid inputs for Arps decline calculation.")
    
    if b == 0.0:
        q_t = q_i * math.exp(-d_i * t_years)
    elif abs(b - 1.0) < 1e-5:
        q_t = q_i / (1.0 + d_i * t_years)
    else:
        q_t = q_i / ((1.0 + b * d_i * t_years) ** (1.0 / b))
    return round(q_t, 2)
