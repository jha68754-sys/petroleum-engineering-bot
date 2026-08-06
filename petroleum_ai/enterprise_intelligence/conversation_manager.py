"""
Conversation Manager: Manages conversational flow and natural language engineering queries.
"""

from __future__ import annotations
from typing import List, Dict, Any

class ConversationManager:
    def __init__(self):
        self.dialogue_history: List[Dict[str, str]] = []

    def add_message(self, role: str, content: str) -> None:
        self.dialogue_history.append({"role": role, "content": content})

    def get_history(self) -> List[Dict[str, str]]:
        return self.dialogue_history
