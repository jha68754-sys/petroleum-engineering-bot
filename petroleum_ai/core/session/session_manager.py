"""
1. Engineering Session Manager: Remembers well, reservoir, project, previous calculations,
assumptions, decisions, preferences, and engineering context within a session.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
import time

@dataclass
class EngineeringSession:
    session_id: str
    current_well: Optional[str] = None
    current_reservoir: Optional[str] = None
    current_project: Optional[str] = None
    calculations_history: List[Dict[str, Any]] = field(default_factory=list)
    assumptions_history: List[str] = field(default_factory=list)
    decisions_history: List[str] = field(default_factory=list)
    user_preferences: Dict[str, Any] = field(default_factory=lambda: {"unit_system": "field", "language": "ar"})
    context_data: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)

class SessionManager:
    """Manages active engineering sessions across multiple users and wells."""
    _sessions: Dict[str, EngineeringSession] = {}

    @classmethod
    def get_or_create_session(cls, session_id: str) -> EngineeringSession:
        if session_id not in cls._sessions:
            cls._sessions[session_id] = EngineeringSession(session_id=session_id)
        session = cls._sessions[session_id]
        session.last_accessed = time.time()
        return session

    @classmethod
    def update_session_context(cls, session_id: str, **kwargs: Any) -> EngineeringSession:
        session = cls.get_or_create_session(session_id)
        for k, v in kwargs.items():
            if hasattr(session, k):
                setattr(session, k, v)
        return session

    @classmethod
    def log_calculation(cls, session_id: str, calc_record: Dict[str, Any]) -> None:
        session = cls.get_or_create_session(session_id)
        session.calculations_history.append(calc_record)

    @classmethod
    def log_assumption(cls, session_id: str, assumption: str) -> None:
        session = cls.get_or_create_session(session_id)
        if assumption not in session.assumptions_history:
            session.assumptions_history.append(assumption)

    @classmethod
    def log_decision(cls, session_id: str, decision: str) -> None:
        session = cls.get_or_create_session(session_id)
        session.decisions_history.append(decision)
