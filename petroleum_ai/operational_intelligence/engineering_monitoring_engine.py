"""
Engineering Monitoring Engine: Detects trends, performance drift, and time-series anomalies.
"""

from __future__ import annotations
from typing import Dict, List, Any

class EngineeringMonitoringEngine:
    """Monitors time-series operational variables for performance drift and reservoir changes."""

    @staticmethod
    def detect_trends(time_series_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not time_series_data:
            return {"trend": "Insufficient Data", "drift_detected": False}
        
        rates = [d.get("oil_rate", 0) for d in time_series_data]
        if len(rates) > 1 and rates[-1] < rates[0] * 0.90:
            return {"trend": "Declining Production Drift", "drift_detected": True}
        return {"trend": "Stable Production Trend", "drift_detected": False}
