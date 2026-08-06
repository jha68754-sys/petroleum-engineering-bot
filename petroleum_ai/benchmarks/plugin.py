"""
Benchmarks Plugin for automatic registration in the Enterprise Core Platform.
"""

from __future__ import annotations
from petroleum_ai.core.plugins.plugin_system import PluginManager

class BenchmarksPlugin:
    plugin_name = "BenchmarksPlugin"
    discipline = "Benchmarks"

    def initialize(self) -> None:
        pass

# Automatically register plugin
PluginManager.register_plugin(BenchmarksPlugin())
