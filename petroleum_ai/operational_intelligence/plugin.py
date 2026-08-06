"""
Operational Intelligence Plugin for automatic registration in the Enterprise Core Platform.
"""

from __future__ import annotations
from petroleum_ai.core.plugins.plugin_system import PluginManager

class OperationalIntelligencePlugin:
    plugin_name = "OperationalIntelligencePlugin"
    discipline = "OperationalIntelligence"

    def initialize(self) -> None:
        pass

# Automatically register plugin
PluginManager.register_plugin(OperationalIntelligencePlugin())
