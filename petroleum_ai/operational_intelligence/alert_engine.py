"""
Alert Engine: Issues prioritized operational alerts (Critical, Warning, Info).
"""

from __future__ import annotations
from typing import Dict, List, Any

class AlertEngine:
    """Generates and prioritizes operational alerts."""

    @staticmethod
    def generate_alerts(anomalies: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        alerts = []
        for anom in anomalies:
            severity = anom.get("severity", "Info")
            alerts.append({
                "priority": 1 if severity == "Critical" else (2 if severity == "Warning" else 3),
                "severity": severity,
                "message": anom.get("anomaly"),
                "indicator": anom.get("indicator")
            })
        return sorted(alerts, key=lambda x: x["priority"])
