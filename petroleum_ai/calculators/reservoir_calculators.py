"""
Reservoir Engineering Calculators: OOIP, OGIP, Total Compressibility, Porosity.
"""

from __future__ import annotations

def calculate_ooip(area_acres: float, net_pay_ft: float, porosity: float, water_saturation: float, boi: float) -> float:
    """
    Calculate Original Oil in Place (OOIP) in STB:
    OOIP = (7758 * A * h * phi * (1 - Sw)) / Boi
    Reference: Craft & Hawkins.
    """
    if area_acres <= 0 or net_pay_ft <= 0 or porosity <= 0 or water_saturation < 0 or water_saturation >= 1 or boi <= 0:
        raise ValueError("Invalid reservoir parameters for OOIP calculation.")
    ooip = (7758.0 * area_acres * net_pay_ft * porosity * (1.0 - water_saturation)) / boi
    return round(ooip, 2)

def calculate_ogip(area_acres: float, net_pay_ft: float, porosity: float, water_saturation: float, bgi: float) -> float:
    """
    Calculate Original Gas in Place (OGIP) in scf:
    OGIP = (43560 * A * h * phi * (1 - Sw)) / Bgi
    Reference: Craft & Hawkins.
    """
    if area_acres <= 0 or net_pay_ft <= 0 or porosity <= 0 or water_saturation < 0 or water_saturation >= 1 or bgi <= 0:
        raise ValueError("Invalid reservoir parameters for OGIP calculation.")
    ogip = (43560.0 * area_acres * net_pay_ft * porosity * (1.0 - water_saturation)) / bgi
    return round(ogip, 2)

def calculate_total_compressibility(c_f: float, c_o: float, c_w: float, sw: float) -> float:
    """
    Calculate Total System Compressibility ct (psi^-1) for undersaturated oil reservoir:
    ct = cf + co * (1 - sw) + cw * sw
    """
    so = 1.0 - sw
    ct = c_f + (c_o * so) + (c_w * sw)
    return round(ct, 7)
