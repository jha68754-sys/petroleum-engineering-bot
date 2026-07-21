"""
Structured logging configuration for the Petroleum Engineering Bot.

Provides a centralized logging setup with appropriate formatters,
handlers, and log levels for both development and production (Railway).
"""

from __future__ import annotations

import logging
import sys

from config import LOG_LEVEL, LOG_FORMAT, LOG_DATE_FORMAT


def setup_logging() -> logging.Logger:
    """
    Configure and return the root application logger.

    In production (Railway), logs go to stdout so the platform
    can capture them. In development, the same handler is used
    but the level can be set lower via the LOG_LEVEL env var.

    Returns:
        logging.Logger: The configured root logger for the application.
    """
    # Map string level names to logging constants
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

    root_logger.addHandler(handler)

    # Suppress noisy third-party loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("matplotlib").setLevel(logging.WARNING)
    logging.getLogger("PIL").setLevel(logging.WARNING)

    logger = logging.getLogger("pvt_bot")
    logger.info(
        "Logging configured: level=%s, format=structured", LOG_LEVEL
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
