"""
Lessons Learned: Expert engineering lessons and field warnings from historical well interventions.
"""

from __future__ import annotations
from typing import List

class LessonsLearned:
    """Provides critical field warnings and historical lessons learned."""

    @staticmethod
    def get_lessons() -> List[str]:
        return [
            "Never acidize a carbonate well without checking temperature limits and iron control additives.",
            "Avoid rapid drawdown below bubble point in volatile oil reservoirs to prevent severe relative permeability damage from gas blocking.",
            "Always verify surface choke performance before attributing well deliverability loss to downhole skin."
        ]
