"""
Engineering Timeline: Chronological timeline of engineering workflows and events.
"""

from __future__ import annotations
from typing import List, Dict, Any
import time

class EngineeringTimeline:
    def __init__(self):
        self.timeline: List[Dict[str, Any]] = []

    def add_event(self, event_name: str, details: Dict[str, Any]) -> None:
        self.timeline.append({
            "timestamp": time.time(),
            "event": event_name,
            "details": details
        })

    def get_timeline(self) -> List[Dict[str, Any]]:
        return self.timeline
