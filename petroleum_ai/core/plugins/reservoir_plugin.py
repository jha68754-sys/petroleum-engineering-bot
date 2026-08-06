"""
Reservoir Plugin for automatic registration in the Enterprise Core Platform.
"""

from __future__ import annotations
from petroleum_ai.core.plugins.plugin_system import PluginManager
from petroleum_ai.core.calculators.calculator_manager import CalculatorManager
from petroleum_ai.calculators.reservoir_calculators import (
    calculate_ooip,
    calculate_ogip,
    calculate_total_compressibility
)

class ReservoirPlugin:
    plugin_name = "ReservoirPlugin"
    discipline = "Reservoir"

    def initialize(self) -> None:
        # Register calculators into Universal Calculator Manager
        CalculatorManager.register_calculator("ooip", calculate_ooip)
        CalculatorManager.register_calculator("ogip", calculate_ogip)
        CalculatorManager.register_calculator("total_compressibility", calculate_total_compressibility)

# Automatically register plugin
PluginManager.register_plugin(ReservoirPlugin())
