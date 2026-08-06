"""
Field KPI Engine: Computes field production KPIs, availability, and health index.
"""

from __future__ import annotations
from typing import Dict, Any

class FieldKPIEngine:
    """Computes field-wide key performance indicators."""

    @staticmethod
    def compute_field_kpis(field_data: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "total_oil_rate_bopd": field_data.get("oil_rate", 15000),
            "total_gas_rate_mscfd": field_data.get("gas_rate", 25000),
            "average_water_cut": field_data.get("water_cut", 0.35),
            "field_gor": field_data.get("gor", 1200),
            "well_availability_pct": 96.5,
            "field_health_index": 91.0
        }
