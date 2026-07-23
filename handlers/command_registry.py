"""
Command registry module.

Provides a decorator-based command registration system
that replaces the long if/elif chain in the original bot.py.
Each command is registered with a name, aliases, and handler function.
"""

from __future__ import annotations

import logging
from typing import Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("pvt_bot.handlers.command_registry")


class CommandRegistry:
    """
    Registry for bot command handlers.

    Commands are registered with a primary name and optional aliases.
    The dispatch method matches incoming messages against registered
    commands and invokes the appropriate handler.

    Usage:
        registry = CommandRegistry()

        @registry.register("classify", aliases=["classify_fluid"])
        def handle_classify(msg, args):
            ...

        handler = registry.dispatch("/classify gor=500 api=35")
    """

    def __init__(self) -> None:
        self._commands: Dict[str, Callable] = {}
        self._aliases: Dict[str, str] = {}

    def register(
        self,
        name: str,
        aliases: Optional[List[str]] = None,
    ) -> Callable:
        """
        Decorator to register a command handler.

        Args:
            name: The primary command name (without leading /).
            aliases: Optional list of alternative names.

        Returns:
            Decorator function.
        """
        def decorator(func: Callable) -> Callable:
            self._commands[name] = func
            for alias in (aliases or []):
                self._aliases[alias] = name
            logger.info("Registered command: /%s (aliases: %s)", name, aliases or [])
            return func
        return decorator

    def dispatch(self, message: str) -> Optional[Callable]:
        """
        Find and return the handler for a given message.

        Checks for command patterns like /classify, /calc, etc.

        Args:
            message: The user's message text.

        Returns:
            The handler function, or None if no match.
        """
        text = message.strip()

        # Check if message starts with /
        if not text.startswith("/"):
            return None

        # Extract command name (everything between / and first space)
        parts = text[1:].split(None, 1)
        cmd_name = parts[0].lower() if parts else ""

        if not cmd_name:
            return None

        # Resolve aliases
        resolved = self._aliases.get(cmd_name, cmd_name)

        return self._commands.get(resolved)

    def get_command_list(self) -> str:
        """
        Get a formatted list of all registered commands.

        Returns:
            Formatted command list string.
        """
        lines = ["Available commands:"]
        for name in sorted(self._commands.keys()):
            aliases = [a for a, c in self._aliases.items() if c == name]
            alias_str = f" (also: {', '.join(aliases)})" if aliases else ""
            lines.append(f"  /{name}{alias_str}")
        return "\n".join(lines)


# Global registry instance
registry = CommandRegistry()
