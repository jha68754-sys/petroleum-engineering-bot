"""
Error handling utilities for the Petroleum Engineering Bot.

Provides structured error handling, user-facing error messages,
and graceful degradation for all failure modes.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class BotError(Exception):
    """Base exception for bot-level errors with user-facing messages."""
    def __init__(self, message: str, user_message: Optional[str] = None):
        super().__init__(message)
        self.user_message = user_message or message


class APIError(BotError):
    """API call failure (Telegram or Groq)."""
    pass


class ValidationError(BotError):
    """Input validation failure."""
    pass


class FileError(BotError):
    """File processing failure."""
    pass


class AIAvailabilityError(BotError):
    """AI service unavailable -- provide deterministic fallback."""
    pass


def get_user_safe_error(exc: Exception) -> str:
    """
    Convert an exception into a user-safe error message.

    Internal error details are logged but NOT shown to the user.
    Only safe, actionable messages are returned.

    Args:
        exc: The caught exception.

    Returns:
        A user-friendly error message string.
    """
    if isinstance(exc, BotError):
        return exc.user_message

    if isinstance(exc, ValueError):
        return "Invalid input. Please check your values and try again."

    if isinstance(exc, (KeyError, IndexError)):
        return "Data format error. Please check the input format."

    if isinstance(exc, (FileNotFoundError, OSError)):
        return "File processing failed. Please try uploading the file again."

    if isinstance(exc, RuntimeError):
        return "Service temporarily unavailable. Please try again in a moment."

    # Generic -- never expose internal details
    logger.error("Unexpected error: %s", exc, exc_info=True)
    return "An unexpected error occurred. Please try again or contact support."


def format_error_for_user(error_msg: str) -> str:
    """
    Format an error message for Telegram display.

    Args:
        error_msg: The raw error message.

    Returns:
        Formatted error string.
    """
    return f"Error: {error_msg}"
