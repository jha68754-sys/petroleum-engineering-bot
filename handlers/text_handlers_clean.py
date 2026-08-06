"""
Clean text handlers.
"""
from __future__ import annotations
from typing import Any, Dict, Optional, Tuple
from handlers.command_registry import registry

def handle_graph(message: Dict[str, Any], tg) -> Tuple[str, Optional[bytes], Optional[str]]:
    """Handle /graph command."""
    return "Graph handled", None, None

def handle_analyze(message: Dict[str, Any], tg) -> Tuple[str, Optional[bytes], Optional[str]]:
    """Handle /analyze command."""
    return "Analyze handled", None, None
