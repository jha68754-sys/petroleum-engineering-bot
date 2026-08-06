"""
Engineering Calculator Center: Central interface for all certified calculators categorized by discipline.
"""

from __future__ import annotations
from typing import Dict, List, Any

class CalculatorCenter:
    """Categorized hub for reservoir, production, PVT, well testing, artificial lift, and economics calculators."""

    @staticmethod
    def list_calculators() -> Dict[str, List[str]]:
        return {
            "Reservoir": ["OOIP", "OGIP", "Compressibility"],
            "Production": ["Vogel IPR", "Productivity Index", "Arps Decline"],
            "PVT": ["Standing", "Vasquez-Beggs", "Z-Factor"],
            "Well Testing": ["Skin Factor", "Radius of Investigation", "Horner Build-up"],
            "Artificial Lift": ["ESP TDH", "Gas Lift Design", "Pump HHP"],
            "Economics": ["NPV", "IRR", "Payback"]
        }
