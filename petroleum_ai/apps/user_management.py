"""
User Management: Role-based access control (Administrator, Field Engineer, Reservoir Engineer, Production Engineer, Manager, Viewer).
"""

from __future__ import annotations
from typing import Dict, List, Any

class UserManagement:
    """Manages roles and permissions across enterprise users."""

    ROLES = ["Administrator", "Field Engineer", "Reservoir Engineer", "Production Engineer", "Manager", "Viewer"]

    @staticmethod
    def authorize_user(username: str, role: str) -> Dict[str, Any]:
        is_valid = role in UserManagement.ROLES
        return {
            "username": username,
            "role": role,
            "authorized": is_valid,
            "permissions": ["read", "write", "execute"] if is_valid else []
        }
