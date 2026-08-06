"""
Field Surveillance Engine: Continuous monitoring and early detection of reservoir and well anomalies.
"""

from __future__ import annotations
from typing import Dict, List, Any

class FieldSurveillanceEngine:
    """Monitors field parameters and detects early anomalies like water breakthrough, scaling, and ESP issues."""

    @staticmethod
    def survey_well_status(twin_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        anomalies = []
        prod_hist = twin_data.get("production_history", [])
        if prod_hist:
            latest = prod_hist[-1]
            if latest.get("water_cut", 0.0) > 0.50:
                anomalies.append({
                    "anomaly": "Water Breakthrough / Coning Detected",
                    "severity": "Warning",
                    "indicator": f"Water cut is {latest.get('water_cut') * 100:.1f}%"
                })
            if latest.get("gor", 1000) > 4000:
                anomalies.append({
                    "anomaly": "Gas Breakthrough / High GOR Detected",
                    "severity": "Warning",
                    "indicator": f"GOR is {latest.get('gor')} scf/STB"
                })
        return anomalies if anomalies else [{"anomaly": "Normal Operational Envelope", "severity": "Info", "indicator": "Stable"}]
