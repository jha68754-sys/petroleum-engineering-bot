"""
Petroleum Engineering Telegram Bot -- Main Entry Point.

Professional refactor of the original monolithic bot.py.
Implements modular architecture with:
- Clean command dispatch via registry
- Per-chat state management
- Persistent offset for Railway restarts
- Graceful shutdown on SIGTERM
- Structured logging with token redaction
- Deterministic + AI-assisted modes
- Startup delay to prevent deploy overlap 409
- Instance identity logging (PID, hostname, commit SHA)

Deployment: Railway (long-polling Telegram Bot API)
"""

from __future__ import annotations

import hashlib
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
import logging
import re
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
from services.petroleum_knowledge import answer_knowledge_question
# Glossary service removed
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

from state import (
    FILE_CONTEXT,
    IMAGE_CONTEXT,
    CONVERSATION_HISTORY,
    _LAST_AI_CALL_TIME,
    _delete_temp_image
)

# Per-chat AI-call rate limiting (basic abuse/cost protection)
AI_CALL_MIN_INTERVAL_SECONDS = float(os.environ.get("AI_CALL_MIN_INTERVAL_SECONDS", "2.0"))

# ═══════════════════════════════════════════════════════════════════════
#  TOKEN REDACTION
# ═══════════════════════════════════════════════════════════════════════

_TOKEN_PATTERN = re.compile(r"bot\d{8,12}:[A-Za-z0-9_\-]{20,60}")


def redact_token(text: str) -> str:
    """Replace bot token in text with [REDACTED]."""
    return _TOKEN_PATTERN.sub("bot[REDACTED]", text)


def token_fingerprint() -> str:
    """Return a safe fingerprint of the token (SHA-256 first 8 chars)."""
    return hashlib.sha256(TELEGRAM_BOT_TOKEN.encode()).hexdigest()[:8]


# ═══════════════════════════════════════════════════════════════════════
#  INSTANCE IDENTITY
# ═══════════════════════════════════════════════════════════════════════

def get_instance_identity() -> Dict[str, str]:
    """
    Collect instance identity information for log traceability.

    Returns a dict with environment details, never including secrets.
    """
    identity: Dict[str, str] = {
        "pid": str(os.getpid()),
        "hostname": socket.gethostname(),
        "python": sys.version.split()[0],
    }

    # Railway environment variables (safe to log)
    for env_var in [
        "RAILWAY_DEPLOYMENT_ID",
        "RAILWAY_SERVICE_NAME",
        "RAILWAY_ENVIRONMENT_NAME",
        "RAILWAY_REPLICA_ID",
        "RAILWAY_GIT_COMMIT_SHA",
        "RAILWAY_GIT_BRANCH",
        "RAILWAY_PROJECT_NAME",
    ]:
        value = os.environ.get(env_var, "")
        if value:
            identity[env_var.replace("RAILWAY_", "").lower()] = value

    # Local git info (fallback)
    if "commit_sha" not in identity or "branch" not in identity:
        try:
            repo_root = Path(__file__).parent
            sha = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True, text=True, cwd=repo_root, timeout=5,
            )
            if sha.returncode == 0:
                identity.setdefault("commit_sha", sha.stdout.strip())
            branch = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True, text=True, cwd=repo_root, timeout=5,
            )
            if branch.returncode == 0:
                identity.setdefault("branch", branch.stdout.strip())
        except Exception:
            pass

    return identity


def log_instance_identity(identity: Dict[str, str]) -> None:
    """Log instance identity details (secrets excluded)."""
    logger.info("=" * 60)
    logger.info("Petroleum Engineering Bot - Instance Identity")
    logger.info("=" * 60)
    for key, value in identity.items():
        logger.info("  %s = %s", key.upper(), value)
    logger.info("  TOKEN_FINGERPRINT = sha256:%s", token_fingerprint())
    logger.info("=" * 60)


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

# Vietnamese-specific diacritic characters. A word containing any of these in
# an Arabic/English response is a language-consistency glitch (observed live,
# e.g. the AI outputting "nên" mid-sentence) rather than legitimate content --
# this is a narrow, defense-in-depth backstop on top of the system prompt's
# "Arabic or English only" rule, deliberately NOT touching Greek/scientific
# symbols (gamma, mu, etc.) that legitimately appear in engineering text.
_STRAY_WORD_RE = re.compile(
    r"\S*[^\x00-\x7F\u0370-\u03FF"  # ASCII (plain English/digits/punctuation), Greek (gamma, mu, etc.)
    r"\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF"  # Arabic (all blocks)
    r"\u2000-\u206F\u2200-\u22FF\u00B0\u00B2\u00B3\u00B5\u00B7\u00D7\s]\S*"  # units, punctuation, math operators
)


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
    # Defense-in-depth: strip stray foreign-script words (a language-
    # consistency glitch, not legitimate content in an Arabic/English reply).
    # Uses a whitelist of Arabic/Greek/Latin/punctuation ranges, so it
    # catches ANY stray script (Vietnamese, Cyrillic, CJK, etc.) generically.
    text = _STRAY_WORD_RE.sub("", text)
    text = re.sub(r" {2,}", " ", text)
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

# ═══════════════════════════════════════════════════════════════════════
#  DYNAMIC PLOT CAPTIONS (Telegram photo captions per plot type)
# ═══════════════════════════════════════════════════════════════════════

# Professional caption per plot type (from rule key to Telegram caption).
# Falls back to the rule's English title when the key is not listed here,
# so new plot types are captioned automatically.
_PLOT_CAPTIONS: Dict[str, str] = {
    "bo_vs_p": "Oil Formation Volume Factor (Bo) Plot",
    "rs_vs_p": "Solution Gas-Oil Ratio (Rs) Plot",
    "bg_vs_p": "Gas Formation Volume Factor (Bg) Plot",
    "z_vs_p": "Gas Compressibility Factor (Z) Plot",
    "mu_o_vs_p": "Oil Viscosity Plot",
    "mu_g_vs_p": "Gas Viscosity Plot",
    "dropout_vs_p": "Liquid Dropout Plot",
    "cgr_vs_p": "Condensate-Gas Ratio (CGR) Plot",
    "density_vs_p": "Density vs Pressure Plot",
    "vrel_vs_p": "Relative Volume Plot",
    "gor_vs_p": "Gas-Oil Ratio (GOR) Plot",
    "wor_vs_p": "Water-Oil Ratio (WOR) Plot",
    "wc_vs_p": "Water Cut Plot",
    "p_vs_t": "Pressure Plot",
    "q_vs_t": "Production Performance Plot",
    "kr_vs_sw": "Relative Permeability Plot",
    "ipr_plot": "Inflow Performance Relationship (IPR) Plot",
    "vlp_plot": "Vertical Lift Performance (VLP) Plot",
    "nodal_plot": "Nodal Analysis (IPR vs VLP)",
}


def _plot_caption_for(command_text: str) -> str:
    """
    Return a dynamic Telegram photo caption based on the plot type requested
    in the command text (e.g. "/plot Bo p=... v=..."). Falls back to "PVT
    Plot" only when no plot type could be resolved.
    """
    try:
        from services.pvt_engine import PLOT_ALIASES
        from constants import PVT_PLOT_RULES
    except ImportError:
        return "PVT Plot"

    parts = command_text.strip().split()
    if len(parts) < 2 or not parts[0].startswith("/"):
        return "PVT Plot"

    rel_key = resolve_relationship_key(parts[1])
    if rel_key:
        caption = _PLOT_CAPTIONS.get(rel_key, "")
        if caption:
            return caption
        title_en = PVT_PLOT_RULES.get(rel_key, {}).get("title_en", "")
        if title_en:
            return f"{title_en} Plot"
    return "PVT Plot"


def process_message(
    message: Dict[str, Any],
    tg: TelegramService,
    ai: AIService,
) -> None:
    """
    Process a single Telegram message.

    Routes to the appropriate handler based on message type:
    - Document upload -> file handler -> optional AI analysis
    - Photo upload -> stored for automatic vision analysis on next message
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
            # Priority 1: Handle /start directly to bypass any registry issues
            if text.split()[0].lower() == "/start":
                from constants import START_MESSAGE
                tg.send_message(chat_id, START_MESSAGE, reply_to_message_id=message_id)
                return

            # Priority 2: Dispatch other commands via registry
            handler = registry.dispatch(text)
            if handler:
                result_text, png_bytes, doc_filename = handler(message, tg)

                # Sentinel (None, None, None) means the command handler validated
                # that context exists (file already uploaded) and wants the
                # AI to actually produce the analysis (used by /analyze).
                if result_text is None and png_bytes is None and doc_filename is None:
                    ai_prompt = (
                        "Analyze the uploaded engineering document/report in the FILE CONTEXT below. "
                        "Summarize key PVT/reservoir data, flag any inconsistencies, and follow BLOCK 5 "
                        "ground truth rules and BLOCK 13 formatting (no markdown, clear headings)."
                    )
                    _handle_free_text(message, ai_prompt, tg, ai)
                    return

                if result_text:
                    # Don't clean_text for /start as it might remove Markdown
                    msg_to_send = result_text if text.split()[0].lower() == "/start" else clean_text(result_text)
                    tg.send_message(chat_id, msg_to_send, reply_to_message_id=message_id)

                if png_bytes:
                    caption = _plot_caption_for(text)
                    tg.send_photo_bytes(chat_id, png_bytes, caption=caption, reply_to_message_id=message_id)
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

        # --- Free text: deterministic Petroleum Knowledge Layer first ---
        # Recognized terminology questions are answered from the reviewed,
        # version-controlled knowledge dataset. Other free text keeps the
        # existing AI-assisted path unchanged.
        knowledge_answer = answer_knowledge_question(text)
        if knowledge_answer is not None:
            tg.send_message(
                chat_id,
                clean_text(knowledge_answer),
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

    # Lightweight per-chat rate limit: bound how often a single chat can trigger
    # a (costly) AI call, to reduce abuse/runaway-cost risk from message spam.
    now = time.monotonic()
    last_call = _LAST_AI_CALL_TIME.get(chat_id)
    if last_call is not None and (now - last_call) < AI_CALL_MIN_INTERVAL_SECONDS:
        wait_left = AI_CALL_MIN_INTERVAL_SECONDS - (now - last_call)
        tg.send_message(
            chat_id,
            f"Please wait {wait_left:.0f}s before your next AI question "
            f"(deterministic commands like /calc, /estimate, /plot are not rate-limited).",
            reply_to_message_id=message_id,
        )
        return
    _LAST_AI_CALL_TIME[chat_id] = now

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
#  MAIN LOOP
# ═══════════════════════════════════════════════════════════════════════

# Startup delay to prevent deploy overlap (old + new container running simultaneously).
# Must exceed the worst-case time the PREVIOUS instance can still be blocked inside a
# long-poll get_updates() call after receiving SIGTERM (POLLING_TIMEOUT + request overhead,
# ~40s with default settings) -- see AUDIT_REPORT.md Section B1. Default raised from 8s to 45s.
STARTUP_DELAY_SECONDS = int(os.environ.get("STARTUP_DELAY", "45"))


def run() -> None:
    """
    Main entry point. Initializes services and runs the polling loop.

    Handles graceful shutdown on SIGTERM (Railway).
    Prevents 409 Conflict via:
    - delete_webhook on startup (with retry)
    - Startup delay to avoid deploy overlap
    - Token redaction in all logs
    - Instance identity logging
    """
    # Setup logging (with token redaction)
    setup_logging()

    # Log instance identity for traceability
    identity = get_instance_identity()
    log_instance_identity(identity)

    # Startup delay: wait to allow old container to shut down during rolling deploy
    if STARTUP_DELAY_SECONDS > 0:
        logger.info(
            "Startup delay: waiting %ds to prevent deploy overlap...",
            STARTUP_DELAY_SECONDS,
        )
        time.sleep(STARTUP_DELAY_SECONDS)

    # Initialize services
    try:
        tg = TelegramService()
        ai = AIService()
    except ValueError as exc:
        logger.error("Configuration Error: %s", exc)
        logger.info("Bot stopping due to missing configuration.")
        return

    # Delete webhook to prevent 409 Conflict (with retry + drop_pending)
    logger.info("Ensuring webhook is deleted (required for long-polling)...")
    webhook_deleted = tg.delete_webhook(drop_pending=True)

    # Check webhook status
    webhook_info = tg.get_webhook_info()
    if webhook_info:
        webhook_url = webhook_info.get("url", "none")
        logger.info(
            "Webhook status after deletion: url=%s, pending_count=%d",
            webhook_url if webhook_url else "(none)",
            webhook_info.get("pending_update_count", 0),
        )
        if webhook_url:
            logger.warning(
                "WARNING: Webhook URL still set! "
                "This will cause 409 Conflict with getUpdates. "
                "Verify no external service is setting the webhook."
            )

    # Load persisted offset
    offset = load_offset()
    logger.info("Telegram bot polling starting (PID: %s)", identity["pid"])

    # Graceful shutdown handler
    running = True

    def shutdown_handler(signum, frame):
        nonlocal running
        logger.info(
            "Received signal %d (SIGTERM). Shutting down gracefully... "
            "Bot will delete webhook on exit.",
            signum,
        )
        running = False

    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)

    logger.info(
        "Bot ready. Polling with offset=%d, timeout=%ds",
        offset, POLLING_TIMEOUT,
    )

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
                    # No sleep here: fetch the next batch immediately instead of
                    # adding a flat latency penalty after every message batch.
                else:
                    time.sleep(POLLING_LOOP_SLEEP)

            except Exception as exc:
                # Redact token from exception if present
                error_msg = redact_token(str(exc))
                logger.error("Polling loop error: %s", error_msg)
                time.sleep(5)  # Wait before retrying

    finally:
        logger.info("Graceful shutdown initiated (PID: %s)...", identity["pid"])

        # Delete webhook on shutdown to prevent stale webhook issues
        logger.info("Deleting webhook on shutdown...")
        tg.delete_webhook(drop_pending=True)

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
