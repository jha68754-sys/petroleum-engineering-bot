"""
PVT Plugin for automatic registration in the Enterprise Core Platform.
"""

from __future__ import annotations
from petroleum_ai.core.plugins.plugin_system import PluginManager
from petroleum_ai.core.calculators.calculator_manager import CalculatorManager
from petroleum_ai.pvt.calculators.pvt_calculators import (
    calculate_oil_fvf,
    calculate_gas_fvf,
    calculate_bubble_point,
    calculate_z_factor
)

class PVTPlugin:
    plugin_name = "PVTPlugin"
    discipline = "PVT"

    def initialize(self) -> None:
        CalculatorManager.register_calculator("oil_fvf", calculate_oil_fvf)
        CalculatorManager.register_calculator("gas_fvf", calculate_gas_fvf)
        CalculatorManager.register_calculator("bubble_point", calculate_bubble_point)
        CalculatorManager.register_calculator("z_factor", calculate_z_factor)

# Automatically register plugin
PluginManager.register_plugin(PVTPlugin())
