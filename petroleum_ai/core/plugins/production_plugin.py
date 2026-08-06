"""
Production Plugin for automatic registration in the Enterprise Core Platform.
"""

from __future__ import annotations
from petroleum_ai.core.plugins.plugin_system import PluginManager
from petroleum_ai.core.calculators.calculator_manager import CalculatorManager
from petroleum_ai.calculators.production_calculators import (
    calculate_productivity_index,
    calculate_vogel_q_max,
    calculate_arps_decline
)

class ProductionPlugin:
    plugin_name = "ProductionPlugin"
    discipline = "Production"

    def initialize(self) -> None:
        # Register calculators into Universal Calculator Manager
        CalculatorManager.register_calculator("productivity_index", calculate_productivity_index)
        CalculatorManager.register_calculator("vogel_q_max", calculate_vogel_q_max)
        CalculatorManager.register_calculator("arps_decline", calculate_arps_decline)

# Automatically register plugin
PluginManager.register_plugin(ProductionPlugin())
