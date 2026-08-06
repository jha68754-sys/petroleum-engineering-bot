"""
Engineering Feedback: Collects and processes user and expert feedback on recommendations.
"""

from __future__ import annotations
from typing import List, Dict, Any

class EngineeringFeedback:
    def __init__(self):
        self.feedbacks: List[Dict[str, Any]] = []

    def submit_feedback(self, feedback: Dict[str, Any]) -> None:
        self.feedbacks.append(feedback)

    def get_feedbacks(self) -> List[Dict[str, Any]]:
        return self.feedbacks
