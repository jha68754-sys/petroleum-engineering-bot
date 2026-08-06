"""
Engineering Validator: Validates input parameters and ranges against petroleum engineering standards.
"""

from __future__ import annotations
from typing import Dict, Any, List

class EngineeringValidator:
    def __init__(self):
        pass

    def validate_inputs(self, inputs: Dict[str, Any]) -> List[str]:
        errors = []
        if "porosity" in inputs and not (0.0 < inputs["porosity"] < 0.45):
            errors.append("Porosity out of physical range (0 - 0.45).")
        if "water_saturation" in inputs and not (0.0 <= inputs["water_saturation"] <= 1.0):
            errors.append("Water saturation out of physical range (0 - 1).")
        return errors
