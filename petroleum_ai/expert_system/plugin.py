"""
Expert System Plugin for automatic registration in the Enterprise Core Platform.
"""

from __future__ import annotations
from petroleum_ai.core.plugins.plugin_system import PluginManager

class ExpertSystemPlugin:
    plugin_name = "ExpertSystemPlugin"
    discipline = "ExpertSystem"

    def initialize(self) -> None:
        pass

# Automatically register plugin
PluginManager.register_plugin(ExpertSystemPlugin())
