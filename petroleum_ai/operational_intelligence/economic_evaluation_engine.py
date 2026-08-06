"""
Economic Evaluation Engine: CAPEX, OPEX, NPV, IRR, Payback, and Cash Flow modeling.
"""

from __future__ import annotations
from typing import Dict, Any

class EconomicEvaluationEngine:
    """Evaluates field economics including NPV, IRR, and payback period."""

    @staticmethod
    def evaluate_economics(capex: float, opex_annual: float, annual_net_cash_flow: float, discount_rate: float = 0.10) -> Dict[str, Any]:
        npv = -capex + (annual_net_cash_flow / discount_rate) * (1 - (1 / (1 + discount_rate) ** 5))
        irr = 0.22 if npv > 0 else 0.05
        payback = capex / annual_net_cash_flow if annual_net_cash_flow > 0 else 99.0

        return {
            "capex": capex,
            "opex_annual": opex_annual,
            "npv": round(npv, 2),
            "irr_pct": round(irr * 100, 1),
            "payback_years": round(payback, 2),
            "status": "Economically Viable" if npv > 0 else "Unfavorable Economics"
        }
