"""
Configuration module for the Petroleum Engineering Telegram Bot.

All environment variables, API URLs, model names, timeouts, and
operational constants are defined here. This module is the single
source of truth for runtime configuration.
"""

from __future__ import annotations

import os
import tempfile
import logging
from pathlib import Path

from dotenv import load_dotenv

# Load .env file if present (useful for local development)
load_dotenv()

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────
#  TELEGRAM
# ─────────────────────────────────────────────────────────────────────

TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
if not TELEGRAM_BOT_TOKEN:
    raise ValueError(
        "Missing required environment variable: TELEGRAM_BOT_TOKEN. "
        "Set it in your Railway environment or .env file."
    )

TELEGRAM_API_BASE: str = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
TELEGRAM_FILE_BASE: str = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}"

# Long-polling configuration
POLLING_TIMEOUT: int = int(os.getenv("POLLING_TIMEOUT", "30"))
POLLING_OFFSET_SLEEP: float = 0.35  # seconds between message sends (Telegram rate limit)
POLLING_LOOP_SLEEP: float = 1.0     # seconds between getUpdates calls

# Message chunking
MAX_MESSAGE_LENGTH: int = 4096  # Telegram limit is 4096
CHUNK_SPLIT_THRESHOLD: int = 3800  # split before reaching the hard limit

# ─────────────────────────────────────────────────────────────────────
#  AI / LLM  (Groq-compatible OpenAI API)
# ─────────────────────────────────────────────────────────────────────

GROQ_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
if not GROQ_API_KEY:
    raise ValueError(
        "Missing required environment variable: OPENAI_API_KEY (used for Groq API). "
        "Set it in your Railway environment or .env file."
    )

GROQ_API_BASE: str = os.getenv(
    "GROQ_API_BASE", "https://api.groq.com/openai/v1/chat/completions"
)

# Model configuration
TEXT_MODEL: str = os.getenv("GROQ_TEXT_MODEL", "llama-3.3-70b-versatile")
VISION_MODEL: str = os.getenv(
    "GROQ_VISION_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct"
)

# AI call parameters
AI_TEMPERATURE: float = 0.08
AI_MAX_TOKENS_TEXT: int = 3000
AI_MAX_TOKENS_VISION: int = 2200
AI_REQUEST_TIMEOUT: int = 90  # seconds
AI_MAX_RETRIES: int = 3
AI_MAX_VISION_RETRIES: int = 3
AI_RATE_LIMIT_BACKOFF_BASE: int = 2  # exponential backoff base (seconds)

# Context truncation
MAX_CONTEXT_CHARS: int = 20000
MAX_FILE_CONTEXT_CHARS: int = 20000

# ─────────────────────────────────────────────────────────────────────
#  FILE PROCESSING
# ─────────────────────────────────────────────────────────────────────

# Maximum upload file size (10 MB)
MAX_UPLOAD_SIZE: int = 10 * 1024 * 1024

# Supported upload MIME types
SUPPORTED_MIME_TYPES: set[str] = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
    "text/csv",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
    "image/png",
    "image/jpeg",
    "image/webp",
}

# File extensions mapped to handlers
FILE_EXT_HANDLERS: dict[str, str] = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".doc": "docx",
    ".csv": "csv",
    ".xlsx": "excel",
    ".xls": "excel",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".webp": "image",
}

# Temp directory for downloaded files
TEMP_DIR: Path = Path(os.getenv("TEMP_DIR", tempfile.mkdtemp(prefix="pvt_bot_")))

# ─────────────────────────────────────────────────────────────────────
#  STATE PERSISTENCE
# ─────────────────────────────────────────────────────────────────────

# Path for persistent offset storage (survives Railway restarts)
OFFSET_STATE_FILE: Path = Path(os.getenv("OFFSET_STATE_FILE", "offset_state.json"))

# SQLite path for the Engineering Case Registry. Set this to a mounted
# persistent-volume path in Railway for survival across redeployments.
ENGINEERING_CASE_DB_PATH: Path = Path(
    os.getenv("ENGINEERING_CASE_DB_PATH", "engineering_cases.sqlite3")
)

# ─────────────────────────────────────────────────────────────────────
#  VISUALIZATION
# ─────────────────────────────────────────────────────────────────────

PLOT_DEFAULT_DPI: int = 150
PLOT_HIGH_DPI: int = 300
PLOT_FIGURE_WIDTH: float = 10.0
PLOT_FIGURE_HEIGHT: float = 6.0

# Dark theme colors
PLOT_BG_COLOR: str = "#0D1117"
PLOT_AXES_BG_COLOR: str = "#161B22"
PLOT_AXES_EDGE_COLOR: str = "#30363D"
PLOT_TEXT_COLOR: str = "#C9D1D9"
PLOT_TITLE_COLOR: str = "#F0F6FC"
PLOT_TICK_COLOR: str = "#8B949E"
PLOT_GRID_COLOR: str = "#21262D"
PLOT_SATURATION_COLOR: str = "#F39C12"
PLOT_MAX_ANNOTATION_COLOR: str = "#58A6FF"
PLOT_MIN_ANNOTATION_COLOR: str = "#FF7B72"
PLOT_WATERMARK_COLOR: str = "#30363D"

# ─────────────────────────────────────────────────────────────────────
#  LOGGING
# ─────────────────────────────────────────────────────────────────────

LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_FORMAT: str = (
    "%(asctime)s [%(levelname)s] %(name)s.%(funcName)s (line %(lineno)d): %(message)s"
)
LOG_DATE_FORMAT: str = "%Y-%m-%d %H:%M:%S"
