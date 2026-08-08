"""
Handlers package.
"""

from __future__ import annotations

# Intentionally NOT importing the legacy top-level text_handlers.py here:
# it registered a duplicate /graph command with the alias "plot", which
# overwrote the registry alias for /plot and routed direct-data /plot
# requests to a legacy document-upload handler. All command handlers now
# live in handlers/text_handlers.py and are imported explicitly in main.py.
