"""
Engineering State: Manages execution state and parameters across workflows.
"""

from __future__ import annotations
from typing import Dict, Any

class EngineeringState:
    def __init__(self):
        self.state_store: Dict[str, Any] = {}

    def set_state(self, key: str, value: Any) -> None:
        self.state_store[key] = value

    def get_state(self, key: str) -> Any:
        return self.state_store.get(key)

    def dump_state(self) -> Dict[str, Any]:
        return self.state_store.copy()
