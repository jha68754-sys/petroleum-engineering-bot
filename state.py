"""
Global state management for the Petroleum Engineering Bot.
Centralizes shared dictionaries to prevent circular import issues and 
module duplication (e.g., __main__ vs main).
"""

from __future__ import annotations
import os
from collections import OrderedDict
import logging

logger = logging.getLogger("pvt_bot.state")

MAX_TRACKED_CHATS = 500

class _BoundedChatDict(OrderedDict):
    """LRU-bounded dict for per-chat state."""
    def __init__(self, maxsize: int, on_evict=None):
        super().__init__()
        self.maxsize = maxsize
        self.on_evict = on_evict

    def __setitem__(self, key, value):
        if key in self:
            self.move_to_end(key)
        super().__setitem__(key, value)
        while len(self) > self.maxsize:
            oldest_key, oldest_value = self.popitem(last=False)
            if self.on_evict:
                try:
                    self.on_evict(oldest_value)
                except Exception:
                    logger.warning("Cleanup failed while evicting state for chat %s", oldest_key)

    def get(self, key, default=None):
        if key in self:
            self.move_to_end(key)
        return super().get(key, default)

def _delete_temp_image(path: str) -> None:
    """Best-effort deletion of a temp image file."""
    try:
        if path and os.path.exists(path):
            os.unlink(path)
    except OSError:
        pass

# Global state objects
FILE_CONTEXT = _BoundedChatDict(MAX_TRACKED_CHATS)
IMAGE_CONTEXT = _BoundedChatDict(MAX_TRACKED_CHATS, on_evict=_delete_temp_image)
CONVERSATION_HISTORY = _BoundedChatDict(MAX_TRACKED_CHATS)
_LAST_AI_CALL_TIME = _BoundedChatDict(MAX_TRACKED_CHATS)
# Core V2 chat-scoped engineering context. The durable registry is the source
# of truth when configured; this bounded map is only the fast in-process cache.
ENGINEERING_SESSION_CONTEXT = _BoundedChatDict(MAX_TRACKED_CHATS)
