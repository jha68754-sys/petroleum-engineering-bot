"""
Enterprise Application Layer Plugin for automatic registration in the Enterprise Core Platform.
"""

from __future__ import annotations
from petroleum_ai.core.plugins.plugin_system import PluginManager

class EnterpriseAppsPlugin:
    plugin_name = "EnterpriseAppsPlugin"
    discipline = "EnterpriseApplicationLayer"

    def initialize(self) -> None:
        pass

# Automatically register plugin
PluginManager.register_plugin(EnterpriseAppsPlugin())
