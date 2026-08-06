"""
Original Oil In Place (OOIP) Calculator adhering to Craft & Hawkins standards.
"""

from __future__ import annotations

def calculate_ooip(area_acres: float, net_pay_ft: float, porosity: float, water_saturation: float, boi: float) -> float:
    """
    Calculate OOIP in Stock Tank Barrels (STB).
    OOIP = (7758 * A * h * phi * (1 - Sw)) / Boi
    Reference: Craft & Hawkins, Applied Petroleum Reservoir Engineering.
    """
    if boi <= 0:
        raise ValueError("Initial Oil Formation Volume Factor (Boi) must be greater than zero.")
    ooip = (7758.0 * area_acres * net_pay_ft * porosity * (1.0 - water_saturation)) / boi
    return round(ooip, 2)
