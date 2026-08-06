"""
Original Gas In Place (OGIP) Calculator adhering to Craft & Hawkins standards.
"""

from __future__ import annotations

def calculate_ogip(area_acres: float, net_pay_ft: float, porosity: float, water_saturation: float, bgi: float) -> float:
    """
    Calculate OGIP in standard cubic feet (scf).
    OGIP = (43560 * A * h * phi * (1 - Sw)) / Bgi
    Reference: Craft & Hawkins, Applied Petroleum Reservoir Engineering.
    """
    if bgi <= 0:
        raise ValueError("Initial Gas Formation Volume Factor (Bgi) must be greater than zero.")
    ogip = (43560.0 * area_acres * net_pay_ft * porosity * (1.0 - water_saturation)) / bgi
    return round(ogip, 2)
