"""
Structured logging configuration for the Petroleum Engineering Bot.

Provides a centralized logging setup with:
- Token redaction (replaces bot<TOKEN> with bot[REDACTED])
- Appropriate formatters, handlers, and log levels
- Production-safe exception logging
"""

from __future__ import annotations

import logging
import re
import sys
from typing import Optional

from config import LOG_LEVEL, LOG_FORMAT, LOG_DATE_FORMAT


# ═══════════════════════════════════════════════════════════════════════
#  TOKEN REDACTION FILTER
# ═══════════════════════════════════════════════════════════════════════

# Matches: bot<digits_and_letters>  (Telegram bot token pattern)
_TOKEN_RE = re.compile(r"bot\d{8,12}:[A-Za-z0-9_\-]{20,60}")

# Matches Groq/OpenAI-style bearer API keys (e.g. "gsk_...", "sk-...") if they
# ever appear in a log line (e.g. from a raised request exception echoing headers).
_APIKEY_RE = re.compile(r"\b(gsk|sk)-[A-Za-z0-9_\-]{16,}\b")


class TokenRedactionFilter(logging.Filter):
    """
    Logging filter that redacts Telegram bot tokens from log records.

    Replaces patterns like 'bot123456789:ABCDEFGHIJKLMN...'
    with 'bot[REDACTED]' to prevent token leakage in logs.

    Also redacts full Telegram API URLs that contain the token.
    """

    @staticmethod
    def _redact(text: str) -> str:
        text = _TOKEN_RE.sub("bot[REDACTED]", text)
        text = _APIKEY_RE.sub("[REDACTED_API_KEY]", text)
        return text

    def filter(self, record: logging.LogRecord) -> bool:
        # Redact from the message
        if isinstance(record.msg, str):
            record.msg = self._redact(record.msg)

        # Redact from exception info
        if record.exc_info and record.exc_info[1]:
            try:
                record.exc_info = (
                    record.exc_info[0],
                    _TokenExceptionWrapper(record.exc_info[1], _TOKEN_RE, _APIKEY_RE),
                    record.exc_info[2],
                )
            except Exception:
                pass  # Don't break logging on redaction errors

        # Redact from args
        if record.args:
            try:
                if isinstance(record.args, tuple):
                    record.args = tuple(self._redact(str(a)) for a in record.args)
                elif isinstance(record.args, dict):
                    record.args = {k: self._redact(str(v)) for k, v in record.args.items()}
            except Exception:
                pass

        return True


class _TokenExceptionWrapper:
    """Wraps an exception to redact tokens/API keys from its string representation."""

    def __init__(self, exc: BaseException, token_re: re.Pattern, apikey_re: Optional[re.Pattern] = None):
        self._exc = exc
        self._re = token_re
        self._apikey_re = apikey_re

    def _redact(self, text: str) -> str:
        text = self._re.sub("bot[REDACTED]", text)
        if self._apikey_re:
            text = self._apikey_re.sub("[REDACTED_API_KEY]", text)
        return text

    def __str__(self):
        return self._redact(str(self._exc))

    def __repr__(self):
        return self._redact(repr(self._exc))


# ═══════════════════════════════════════════════════════════════════════
#  LOGGING SETUP
# ═══════════════════════════════════════════════════════════════════════

def setup_logging() -> logging.Logger:
    """
    Configure and return the root application logger.

    Includes token redaction filter on all handlers.
    Logs go to stdout for Railway log capture.

    Returns:
        logging.Logger: The configured root logger.
    """
    level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }
    level = level_map.get(LOG_LEVEL, logging.INFO)

    # Root logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove existing handlers to avoid duplicate logs
    root_logger.handlers.clear()

    # Stream handler (stdout — works with Railway log capture)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)

    formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)
    handler.setFormatter(formatter)

    # Add token redaction filter
    redaction_filter = TokenRedactionFilter()
    handler.addFilter(redaction_filter)

    root_logger.addHandler(handler)

    # Apply filter to root logger level too (catches propagate)
    root_logger.addFilter(redaction_filter)

    # Suppress noisy third-party loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("matplotlib").setLevel(logging.WARNING)
    logging.getLogger("PIL").setLevel(logging.WARNING)

    logger = logging.getLogger("pvt_bot")
    logger.info(
        "Logging configured: level=%s, format=structured, redaction=active",
        LOG_LEVEL,
    )
    return logger


def get_logger(name: str) -> logging.Logger:
    """
    Get a child logger under the 'pvt_bot' namespace.

    Args:
        name: Module name (e.g., 'services.telegram_service').

    Returns:
        logging.Logger: A child logger with proper hierarchy.
    """
    return logging.getLogger(f"pvt_bot.{name}")
