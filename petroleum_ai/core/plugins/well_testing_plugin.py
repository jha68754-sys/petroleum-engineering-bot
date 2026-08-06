"""
Well Testing Plugin for automatic registration in the Enterprise Core Platform.
"""

from __future__ import annotations
from petroleum_ai.core.plugins.plugin_system import PluginManager
from petroleum_ai.core.calculators.calculator_manager import CalculatorManager
from petroleum_ai.calculators.well_testing_calculators import (
    calculate_skin_factor,
    calculate_radius_of_investigation,
    calculate_transmissibility
)

class WellTestingPlugin:
    plugin_name = "WellTestingPlugin"
    discipline = "Well Testing"

    def initialize(self) -> None:
        # Register calculators into Universal Calculator Manager
        CalculatorManager.register_calculator("skin_factor", calculate_skin_factor)
        CalculatorManager.register_calculator("radius_of_investigation", calculate_radius_of_investigation)
        CalculatorManager.register_calculator("transmissibility", calculate_transmissibility)

# Automatically register plugin
PluginManager.register_plugin(WellTestingPlugin())
