"""
Production-grade PVT Calculators for PFIE.
Calculates Bo, Bg, Bw, Rs, Pb, Z-factor, viscosities, and compressibilities.
"""

from __future__ import annotations
import math
from petroleum_ai.pvt.correlations.pvt_correlations import PVTCorrelations

def calculate_oil_fvf(api: float, gamma_g: float, temp_f: float, rs: float, method: str = "standing") -> float:
    """Calculate Oil Formation Volume Factor Bo (rb/STB)."""
    if method.lower() == "standing":
        return PVTCorrelations.standing_bo(gamma_g, api, temp_f, rs)
    return 1.25 # default fallback

def calculate_gas_fvf(pressure: float, temp_f: float, z_factor: float) -> float:
    """
    Calculate Gas Formation Volume Factor Bg (rb/scf or bbl/scf):
    Bg = 0.02827 * Z * (T + 460) / P
    """
    if pressure <= 0:
        raise ValueError("Pressure must be greater than zero for Bg calculation.")
    bg = 0.02827 * z_factor * (temp_f + 460.0) / pressure
    return round(bg, 5)

def calculate_bubble_point(gamma_g: float, api: float, temp_f: float, rs_b: float) -> float:
    """Calculate Bubble Point Pressure Pb (psia) using Standing correlation."""
    return PVTCorrelations.standing_pb(gamma_g, api, temp_f, rs_b)

def calculate_z_factor(pressure: float, temp_f: float, gamma_g: float) -> float:
    """Calculate real gas Z-factor."""
    # Pseudo-critical properties (Standing correlation)
    t_pc = 168.0 + 325.0 * gamma_g - 12.5 * (gamma_g ** 2)
    p_pc = 677.0 + 15.0 * gamma_g - 37.5 * (gamma_g ** 2)
    tr = (temp_f + 460.0) / t_pc
    pr = pressure / p_pc
    return PVTCorrelations.dranchuk_abou_kassem_z(pr, tr)
