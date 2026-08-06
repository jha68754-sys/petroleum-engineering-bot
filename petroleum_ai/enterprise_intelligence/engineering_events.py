"""
Engineering Events: Event-driven architecture components for EIF.
"""

from __future__ import annotations
from typing import Callable, List, Dict, Any

class EngineeringEvents:
    def __init__(self):
        self.listeners: Dict[str, List[Callable]] = {}

    def subscribe(self, event_type: str, callback: Callable) -> None:
        if event_type not in self.listeners:
            self.listeners[event_type] = []
        self.listeners[event_type].append(callback)

    def emit(self, event_type: str, data: Dict[str, Any]) -> None:
        if event_type in self.listeners:
            for cb in self.listeners[event_type]:
                cb(data)
