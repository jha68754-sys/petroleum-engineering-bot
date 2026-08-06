"""
Vogel Inflow Performance Relationship (IPR) Calculator for solution-gas drive reservoirs.
"""

from __future__ import annotations

def calculate_vogel_ipr(p_wf: float, p_r: float, q_max: float) -> float:
    """
    Calculate oil flow rate q using Vogel's dimensionless equation:
    q / q_max = 1.0 - 0.2*(Pwf/Pr) - 0.8*(Pwf/Pr)^2
    Reference: Vogel, J.V., JPT (1968).
    """
    if p_r <= 0:
        raise ValueError("Reservoir pressure Pr must be greater than zero.")
    if p_wf > p_r:
        return 0.0
    ratio = p_wf / p_r
    q = q_max * (1.0 - 0.2 * ratio - 0.8 * (ratio ** 2))
    return round(max(0.0, q), 2)
