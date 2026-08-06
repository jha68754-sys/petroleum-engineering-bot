"""
Audit Center: Immutable audit log tracking who, when, what, why, calculation used, reference used, and confidence.
"""

from __future__ import annotations
from typing import Dict, List, Any
from datetime import datetime

class AuditCenter:
    """Logs all operational and engineering decisions with full traceability."""

    log_records: List[Dict[str, Any]] = []

    @classmethod
    def log_action(cls, user: str, action: str, calculation: str, reference: str, confidence: str) -> Dict[str, Any]:
        record = {
            "timestamp": datetime.utcnow().isoformat(),
            "user": user,
            "action": action,
            "calculation_used": calculation,
            "reference_used": reference,
            "confidence": confidence
        }
        cls.log_records.append(record)
        return record
