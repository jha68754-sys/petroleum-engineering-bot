"""
Best Practices: Internationally recognized petroleum engineering best practices (SPE, API).
"""

from __future__ import annotations
from typing import List

class BestPractices:
    """Outlines gold-standard engineering best practices."""

    @staticmethod
    def get_best_practices() -> List[str]:
        return [
            "Perform multi-rate well testing (Flow After Flow or Modified Isochronal) to accurately determine deliverability without skin distortion.",
            "Integrate core analysis, wireline logs, and PVT lab reports prior to full-field numerical simulation modeling.",
            "Monitor artificial lift operating efficiency continuously to optimize power consumption and prevent premature equipment failure."
        ]
