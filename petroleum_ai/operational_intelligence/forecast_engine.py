"""
Forecast Engine: Production, pressure, and reservoir forecasting for 30d, 90d, 6m, 1y, and 5y horizons.
"""

from __future__ import annotations
from typing import Dict, List, Any

class ForecastEngine:
    """Generates multi-horizon production and pressure forecasts."""

    @staticmethod
    def generate_forecasts(initial_rate: float, decline_rate_annual: float = 0.15) -> Dict[str, Any]:
        horizons = {
            "30_days": initial_rate * (1 - decline_rate_annual * (30 / 365)),
            "90_days": initial_rate * (1 - decline_rate_annual * (90 / 365)),
            "6_months": initial_rate * (1 - decline_rate_annual * (180 / 365)),
            "1_year": initial_rate * (1 - decline_rate_annual),
            "5_years": initial_rate * ((1 - decline_rate_annual) ** 5)
        }
        return horizons
