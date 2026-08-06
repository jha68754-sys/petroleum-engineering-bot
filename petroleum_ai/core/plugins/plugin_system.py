"""
5. Engineering Plugin System: Automatic module/plugin registration.
"""

from __future__ import annotations
from typing import Any, Dict, Protocol

class EngineeringPlugin(Protocol):
    plugin_name: str
    discipline: str

    def initialize(self) -> None:
        ...

class PluginManager:
    """Manages automatic registration of engineering discipline plugins."""
    _plugins: Dict[str, Any] = {}

    @classmethod
    def register_plugin(cls, plugin: Any) -> None:
        name = getattr(plugin, "plugin_name", plugin.__class__.__name__)
        cls._plugins[name] = plugin
        if hasattr(plugin, "initialize"):
            plugin.initialize()

    @classmethod
    def get_plugin(cls, name: str) -> Any:
        return cls._plugins.get(name)

    @classmethod
    def list_plugins(cls) -> list[str]:
        return list(cls._plugins.keys())
