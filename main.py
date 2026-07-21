"""
Petroleum Engineering Telegram Bot -- Main Entry Point.

Professional refactor of the original monolithic bot.py.
Implements modular architecture with:
- Clean command dispatch via registry
- Per-chat state management
- Persistent offset for Railway restarts
- Graceful shutdown on SIGTERM
- Structured logging
- Deterministic + AI-assisted modes

Deployment: Railway (long-polling Telegram Bot API)
"""

from __future__ import annotations

import json
import os
import signal
import sys
import tempfile
import time
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Ensure project root is on the path
sys.path.insert(0, str(Path(__file__).parent))

from config import (
    TELEGRAM_BOT_TOKEN,
    POLLING_TIMEOUT,
    POLLING_LOOP_SLEEP,
    MAX_CONTEXT_CHARS,
    MAX_FILE_CONTEXT_CHARS,
    TEMP_DIR,
    OFFSET_STATE_FILE,
)
from constants import SYSTEM_PROMPT_FILE, TEXT_FIXES, START_MESSAGE
from logging_config import setup_logging, get_logger
from services.telegram_service import TelegramService
from services.ai_service import AIService
from services.pvt_engine import (
    classify_fluid,
    validate_pvt_trend,
    resolve_relationship_key,
)
from services.calculation_engine import parse_kv_args
from services.visualization import format_plot_response
from services.glossary import generate_glossary_html
from services.file_processing import (
    detect_file_type,
    extract_file_content,
    save_uploaded_file,
    segment_pdf_text,
    format_segmented_context,
)
from handlers.command_registry import registry
from handlers.file_handlers import handle_document_upload, handle_photo_upload
from handlers.error_handlers import get_user_safe_error

# Force import of all handler modules to register commands
import handlers.text_handlers  # noqa: F401

logger = get_logger("main")

# ═══════════════════════════════════════════════════════════════════════
#  GLOBAL STATE (per-chat)
# ═══════════════════════════════════════════════════════════════════════

FILE_CONTEXT: Dict[int, str] = {}      # chat_id -> extracted file text
IMAGE_CONTEXT: Dict[int, str] = {}     # chat_id -> temp image file path
CONVERSATION_HISTORY: Dict[int, List[Dict[str, str]]] = {}  # chat_id -> history

# ═══════════════════════════════════════════════════════════════════════
#  OFFSET PERSISTENCE
# ═══════════════════════════════════════════════════════════════════════

def load_offset() -> int:
    """Load the last processed offset from disk (survives Railway restarts)."""
    try:
        if OFFSET_STATE_FILE.exists():
            data = json.loads(OFFSET_STATE_FILE.read_text())
            offset = data.get("current_offset", 0)
            logger.info("Loaded offset from disk: %d", offset)
            return offset
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to load offset: %s", exc)
    return 0


def save_offset(offset: int) -> None:
    """Persist the current offset to disk."""
    try:
        OFFSET_STATE_FILE.write_text(
            json.dumps({"current_offset": offset, "ts": time.time()}, indent=2)
        )
    except OSError as exc:
        logger.warning("Failed to save offset: %s", exc)


# ═══════════════════════════════════════════════════════════════════════
#  TEXT CLEANER
# ═══════════════════════════════════════════════════════════════════════

def clean_text(text: str) -> str:
    """
    Clean and normalize text by replacing non-standard Arabic terms
    and removing markdown artifacts.

    Args:
        text: Raw text from AI response or file extraction.

    Returns:
        Cleaned text string.
    """
    for old, new in TEXT_FIXES.items():
        text = text.replace(old, new)
    text = text.replace("**", "")
    text = text.replace("###", "")
    text = text.replace("##", "")
    return text.strip()


# ═══════════════════════════════════════════════════════════════════════
#  COMMAND PATTERN MATCHING
# ═══════════════════════════════════════════════════════════════════════

def is_surface_separator(text: str) -> bool:
    """Check if message matches surface separator command patterns."""
    text_lower = text.lower().strip().lstrip("/")
    return text_lower in ("surface_separator", "surface_seperator", "separator_sample")


# ═══════════════════════════════════════════════════════════════════════
#  MESSAGE HANDLING
# ═══════════════════════════════════════════════════════════════════════

def process_message(
    message: Dict[str, Any],
    tg: TelegramService,
    ai: AIService,
) -> None:
    """
    Process a single Telegram message.

    Routes to the appropriate handler based on message type:
    - Document upload -> file handler -> optional AI analysis
    - Photo upload -> store for /graph analysis
    - Text command -> command registry dispatch
    - Free text -> AI-assisted response

    Args:
        message: The Telegram message dict.
        tg: TelegramService instance.
        ai: AIService instance.
    """
    chat_id = message.get("chat", {}).get("id", 0)
    message_id = message.get("message_id")
    text = message.get("text", "").strip()

    try:
        # --- Document upload ---
        if message.get("document"):
            status, error = handle_document_upload(message, tg, FILE_CONTEXT)
            if error:
                tg.send_message(chat_id, f"Error: {error}", reply_to_message_id=message_id)
                return
            tg.send_message(chat_id, status, reply_to_message_id=message_id)
            return

        # --- Photo upload ---
        if message.get("photo"):
            status, error = handle_photo_upload(message, tg, IMAGE_CONTEXT)
            if error:
                tg.send_message(chat_id, f"Error: {error}", reply_to_message_id=message_id)
                return
            tg.send_message(chat_id, status, reply_to_message_id=message_id)
            return

        # --- Text commands ---
        if text.startswith("/"):
            handler = registry.dispatch(text)
            if handler:
                result_text, png_bytes, doc_filename = handler(message, tg)

                if result_text:
                    tg.send_message(chat_id, clean_text(result_text), reply_to_message_id=message_id)

                if png_bytes:
                    tg.send_photo_bytes(chat_id, png_bytes, caption="PVT Plot", reply_to_message_id=message_id)

                if doc_filename and png_bytes is None:
                    # Send HTML glossary as document
                    if doc_filename.endswith(".html"):
                        html_bytes = generate_glossary_html()
                        tg.send_document(chat_id, html_bytes, doc_filename, reply_to_message_id=message_id)
                return

            # Command not found
            tg.send_message(
                chat_id,
                f"Unknown command: {text.split()[0]}\nUse /start to see all commands.",
                reply_to_message_id=message_id,
            )
            return

        # --- Surface separator special case ---
        if is_surface_separator(text):
            tg.send_message(
                chat_id,
                "Engineering Analysis -- Surface Separator Oil + Gas Samples\n\n"
                "These are surface samples, NOT direct reservoir fluid.\n"
                "Oil and gas separated at surface separator conditions.\n"
                "RECOMBINATION is required first before any PVT test or property (Bo, Rs, Pb).\n\n"
                "Data Required Before Proceeding\n"
                "- Separator Pressure and Temperature\n"
                "- Oil Rate [STB/day] and Gas Rate [scf/day]\n"
                "- Producing GOR [scf/STB]\n"
                "- Gas Composition and Stock Tank Oil Composition\n"
                "- API Gravity and Gas Specific Gravity\n"
                "- Water Cut and H2S/CO2 content\n\n"
                "Correct Lab Workflow\n"
                "1. Sample QC\n2. Recombination\n3. Validation\n"
                "4. Compositional Analysis (C1 to C12+)\n"
                "5. CCE/CME\n6. DV (oil) or CVD (gas condensate)\n"
                "7. Separator Test\n8. Viscosity Test\n9. EOS Tuning\n\n"
                "Use /classify after getting GOR and API.\n"
                "Use /pvto or /pvtg for simulation table requirements.",
                reply_to_message_id=message_id,
            )
            return

        # --- Free text: AI-assisted response ---
        _handle_free_text(message, text, tg, ai)

    except Exception as exc:
        logger.exception("Error processing message from chat %d", chat_id)
        error_msg = get_user_safe_error(exc)
        tg.send_message(chat_id, f"Error: {error_msg}", reply_to_message_id=message_id)


def _handle_free_text(
    message: Dict[str, Any],
    text: str,
    tg: TelegramService,
    ai: AIService,
) -> None:
    """
    Handle free-text messages via AI.

    Includes file context if available, and uses conversation history
    for follow-up questions.

    Args:
        message: The Telegram message dict.
        text: The user's text message.
        tg: TelegramService instance.
        ai: AIService instance.
    """
    chat_id = message.get("chat", {}).get("id", 0)
    message_id = message.get("message_id")

    # Update conversation history
    if chat_id not in CONVERSATION_HISTORY:
        CONVERSATION_HISTORY[chat_id] = []
    history = CONVERSATION_HISTORY[chat_id]
    history.append({"role": "user", "content": text})

    # Get file context
    file_context = FILE_CONTEXT.get(chat_id)

    # Determine if image context exists
    image_path = IMAGE_CONTEXT.get(chat_id)

    try:
        if image_path:
            # Vision analysis
            with open(image_path, "rb") as f:
                image_bytes = f.read()
            image_type = "image/png"
            if image_path.endswith((".jpg", ".jpeg")):
                image_type = "image/jpeg"

            # Build graph-specific prompt
            graph_prompt = (
                "Analyze this petroleum engineering plot/image. "
                "Identify axes, match to PVT reference behavior, "
                "confirm or flag discrepancies. "
                "Follow BLOCK 5 ground truth rules."
            )
            response = ai.ask_vision(image_bytes, image_type, graph_prompt)
        else:
            # Text analysis
            response = ai.ask_text(text, chat_history=history, file_context=file_context)

        # Clean and send response
        cleaned = clean_text(response.content)
        tg.send_message(chat_id, cleaned, reply_to_message_id=message_id)

        # Update history with AI response
        history.append({"role": "assistant", "content": cleaned})

        # Trim history to prevent unbounded growth
        if len(history) > 20:
            CONVERSATION_HISTORY[chat_id] = history[-20:]

    except RuntimeError as exc:
        # AI service failure -- provide deterministic fallback
        logger.warning("AI service unavailable: %s", exc)
        fallback = (
            "AI service temporarily unavailable. "
            "Deterministic commands (/calc, /estimate, /plot, /check, /classify) "
            "are still working. Please try again later."
        )
        tg.send_message(chat_id, fallback, reply_to_message_id=message_id)
    except Exception as exc:
        logger.exception("AI processing error")
        error_msg = get_user_safe_error(exc)
        tg.send_message(chat_id, f"Error: {error_msg}", reply_to_message_id=message_id)


# ═══════════════════════════════════════════════════════════════════════
#  GRAPH PROMPT BUILDER
# ═══════════════════════════════════════════════════════════════════════

def build_graph_prompt(
    reference_summary: Optional[str] = None,
) -> str:
    """
    Build the graph analysis prompt for the vision AI.

    Args:
        reference_summary: Optional pre-formatted reference text.

    Returns:
        The complete prompt string.
    """
    if reference_summary:
        return f"""TASK: Analyze the uploaded petroleum engineering plot/image.

REFERENCE SHAPES (BLOCK 5 ground truth):
{reference_summary}

STEPS:
1. Identify X and Y axis labels, units, scale.
2. Match to ONE reference relationship.
3. AGREE or DISAGREE with the reference shape.
4. If AGREE: identify saturation pressure location.
5. If DISAGREE: state discrepancy and suggest causes.
6. Engineering interpretation and recommendation.

Follow BLOCK 13 formatting (no markdown, clear headings)."""

    return (
        "TASK: Analyze the uploaded petroleum engineering plot/image.\n\n"
        "STEPS:\n"
        "1. Identify X and Y axis labels, units, scale.\n"
        "2. Match to PVT reference relationship (BLOCK 5).\n"
        "3. AGREE or DISAGREE with the reference shape.\n"
        "4. If AGREE: identify saturation pressure location.\n"
        "5. If DISAGREE: state discrepancy and suggest causes.\n"
        "6. Engineering interpretation and recommendation.\n\n"
        "Follow BLOCK 13 formatting (no markdown, clear headings)."
    )


# ═══════════════════════════════════════════════════════════════════════
#  MAIN LOOP
# ═══════════════════════════════════════════════════════════════════════

def run() -> None:
    """
    Main entry point. Initializes services and runs the polling loop.

    Handles graceful shutdown on SIGTERM (Railway).
    """
    # Setup logging
    setup_logging()
    logger.info("Petroleum Engineering Bot starting...")
    logger.info("Python %s, PID %d", sys.version.split()[0], os.getpid())

    # Initialize services
    tg = TelegramService()
    ai = AIService()

    # Load persisted offset
    offset = load_offset()

    # Graceful shutdown handler
    running = True

    def shutdown_handler(signum, frame):
        nonlocal running
        logger.info("Received signal %d. Shutting down gracefully...", signum)
        running = False

    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)

    logger.info("Bot ready. Polling with offset=%d, timeout=%ds", offset, POLLING_TIMEOUT)

    try:
        while running:
            try:
                updates = tg.get_updates(offset=offset, timeout=POLLING_TIMEOUT)

                if updates:
                    for update in updates:
                        message = update.get("message")
                        if not message:
                            continue

                        process_message(message, tg, ai)

                        # Update offset
                        update_id = update.get("update_id", 0)
                        offset = update_id + 1

                    # Persist offset
                    save_offset(offset)

                time.sleep(POLLING_LOOP_SLEEP)

            except Exception as exc:
                logger.exception("Polling loop error: %s", exc)
                time.sleep(5)  # Wait before retrying

    finally:
        logger.info("Saving final offset: %d", offset)
        save_offset(offset)
        ai.close()
        tg.close()

        # Cleanup temp files
        for chat_id, path in IMAGE_CONTEXT.items():
            try:
                if os.path.exists(path):
                    os.unlink(path)
            except OSError:
                pass

        logger.info("Bot stopped cleanly.")


if __name__ == "__main__":
    run()
