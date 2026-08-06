"""
2. Unit Management System: Automatic conversion between Field, SI, and Metric units.
"""

from __future__ import annotations
from typing import Dict, Union

class UnitManager:
    """Handles unit conversions across Field, SI, and Metric systems for petroleum engineering."""

    @staticmethod
    def convert_pressure(val: float, from_system: str, to_system: str) -> float:
        """Convert pressure between psi (Field/Metric) and kPa/MPa (SI)."""
        # Base unit: psi
        psi_val = val
        if from_system.lower() == "si":
            psi_val = val / 6.89475729  # kPa to psi

        if to_system.lower() == "si":
            return round(psi_val * 6.89475729, 3)
        return round(psi_val, 3)

    @staticmethod
    def convert_length(val: float, from_system: str, to_system: str) -> float:
        """Convert length between feet (Field) and meters (SI/Metric)."""
        ft_val = val
        if from_system.lower() in ["si", "metric"]:
            ft_val = val * 3.28084  # meters to feet

        if to_system.lower() in ["si", "metric"]:
            return round(ft_val / 3.28084, 3)
        return round(ft_val, 3)

    @staticmethod
    def convert_rate(val: float, from_system: str, to_system: str) -> float:
        """Convert volumetric rate between STB/day (Field) and m3/day (SI/Metric)."""
        stb_val = val
        if from_system.lower() in ["si", "metric"]:
            stb_val = val * 6.28981  # m3/day to STB/day

        if to_system.lower() in ["si", "metric"]:
            return round(stb_val / 6.28981, 3)
        return round(stb_val, 3)
