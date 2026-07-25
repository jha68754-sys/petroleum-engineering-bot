"""
File upload handlers for the Petroleum Engineering Bot.

Handles document (PDF, DOCX, Excel, CSV) and photo (PNG, JPG, WebP)
uploads from Telegram. Downloads files, extracts content, and stores
context for subsequent AI analysis.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional, Tuple

from services.file_processing import (
    detect_file_type,
    extract_file_content,
    save_uploaded_file,
    segment_pdf_text,
    format_segmented_context,
)
from logging_config import get_logger

logger = get_logger(__name__)


def handle_document_upload(
    message: Dict[str, Any],
    tg: Any,
    file_context: Dict[int, str],
) -> Tuple[str, Optional[str]]:
    """
    Handle a document upload (PDF, DOCX, Excel, CSV).

    Downloads the file, extracts text content, segments if necessary,
    and stores the context for AI analysis.

    Args:
        message: The Telegram message dict containing document info.
        tg: The TelegramService instance.
        file_context: Global dict mapping chat_id to file context.

    Returns:
        Tuple of (status_message, error_message_or_none).
    """
    chat_id = message.get("chat", {}).get("id", 0)
    doc = message.get("document", {})

    if not doc:
        return "No document found in message.", "No document"

    file_id = doc.get("file_id", "")
    filename = doc.get("file_name", "unknown")
    file_size = doc.get("file_size", 0)

    # Validate file size
    from config import MAX_UPLOAD_SIZE
    if file_size > MAX_UPLOAD_SIZE:
        return (
            f"File too large: {file_size / 1024 / 1024:.1f} MB "
            f"(max {MAX_UPLOAD_SIZE / 1024 / 1024:.0f} MB)"
        ), "File too large"

    # Detect file type
    file_type = detect_file_type(filename)
    if file_type == "unknown":
        ext = os.path.splitext(filename)[1]
        return (
            f"Unsupported file type: {ext}\n"
            f"Supported: PDF, DOCX, XLSX, XLS, CSV"
        ), "Unsupported file type"

    # Download file
    file_path = tg.get_file_path(file_id)
    if not file_path:
        return "Failed to get file download path.", "Download failed"

    file_bytes = tg.download_file(file_path)
    if not file_bytes:
        return "Failed to download file.", "Download failed"

    # Save to temp file
    tmp_path = save_uploaded_file(file_bytes, filename)
    if not tmp_path:
        return "Failed to save file.", "Save failed"

    # Extract content
    content = extract_file_content(tmp_path, file_type)

    # Clean up temp file
    try:
        os.unlink(tmp_path)
    except OSError:
        logger.warning("Failed to clean up temp file: %s", tmp_path)

    if not content:
        return (
            f"No text extracted from {filename}.\n"
            f"This may be a scanned PDF or image-based document.\n"
            f"Try uploading a text-based PDF or DOCX file."
        ), "No content extracted"

    # Store context
    file_context[chat_id] = content
    char_count = len(content)

    return (
        f"File received: {filename} ({file_type.upper()})\n"
        f"Extracted: {char_count} characters\n"
        f"Ready for /analyze or direct questions."
    ), None


def handle_photo_upload(
    message: Dict[str, Any],
    tg: Any,
    image_context: Dict[int, str],
) -> Tuple[str, Optional[str]]:
    """
    Handle a photo upload (PNG, JPG, WebP).

    Downloads the highest-quality photo variant and stores the path
    for subsequent AI vision analysis.

    Args:
        message: The Telegram message dict containing photo info.
        tg: The TelegramService instance.
        image_context: Global dict mapping chat_id to image file path.

    Returns:
        Tuple of (status_message, error_message_or_none).
    """
    chat_id = message.get("chat", {}).get("id", 0)
    photos = message.get("photo", [])

    if not photos:
        return "No photo found in message.", "No photo"

    # Use the largest photo (last in array)
    best_photo = photos[-1]
    file_id = best_photo.get("file_id", "")
    file_size = best_photo.get("file_size", 0)

    # Validate file size (same cap as document uploads)
    from config import MAX_UPLOAD_SIZE
    if file_size > MAX_UPLOAD_SIZE:
        return (
            f"Photo too large: {file_size / 1024 / 1024:.1f} MB "
            f"(max {MAX_UPLOAD_SIZE / 1024 / 1024:.0f} MB)"
        ), "File too large"

    # Get file path
    file_path = tg.get_file_path(file_id)
    if not file_path:
        return "Failed to get photo download path.", "Download failed"

    # Download
    photo_bytes = tg.download_file(file_path)
    if not photo_bytes:
        return "Failed to download photo.", "Download failed"

    # Determine format
    file_ext = ".png"
    content_type = "image/png"
    if file_path.endswith((".jpg", ".jpeg")):
        file_ext = ".jpg"
        content_type = "image/jpeg"
    elif file_path.endswith(".webp"):
        file_ext = ".webp"
        content_type = "image/webp"

    # Save to temp file
    tmp_path = save_uploaded_file(photo_bytes, f"photo_upload{file_ext}")
    if not tmp_path:
        return "Failed to save photo.", "Save failed"

    # Store context
    image_context[chat_id] = tmp_path

    return (
        f"Photo received: {file_size / 1024:.1f} KB\n"
        f"Ask your question about this chart and I'll analyze it."
    ), None
