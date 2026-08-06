"""
Artificial Lift Engine under petroleum_ai/engines/
"""

from __future__ import annotations
from typing import Dict, Any, Optional
from artificial_lift_kb import ARTIFICIAL_LIFT_KNOWLEDGE_BASE

class ArtificialLiftEngine:
    @staticmethod
    def get_details(system_id: str) -> Optional[Dict[str, Any]]:
        return ARTIFICIAL_LIFT_KNOWLEDGE_BASE.get(system_id.lower())
