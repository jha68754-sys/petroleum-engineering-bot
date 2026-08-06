"""
Session Manager: Manages active enterprise sessions and state scoping.
"""

from __future__ import annotations
from typing import Dict, Any
import uuid

class SessionManager:
    def __init__(self):
        self.sessions: Dict[str, Dict[str, Any]] = {}

    def create_session(self, metadata: Dict[str, Any] = None) -> str:
        session_id = str(uuid.uuid4())
        self.sessions[session_id] = {
            "metadata": metadata or {},
            "active": True
        }
        return session_id

    def get_session(self, session_id: str) -> Dict[str, Any]:
        return self.sessions.get(session_id, {})

    def close_session(self, session_id: str) -> None:
        if session_id in self.sessions:
            self.sessions[session_id]["active"] = False
