"""
Telegram API service module.

Provides a connection-pooled HTTP client for Telegram Bot API calls
(sendMessage, sendPhoto, sendDocument, getUpdates, getFile, etc.).
Handles retries, error logging, and graceful degradation.

Security: All error messages redact bot tokens from URLs.
"""

from __future__ import annotations

import io
import re
import time
import logging
from typing import Any, Dict, List, Optional, Union

import requests

from config import (
    TELEGRAM_API_BASE,
    TELEGRAM_FILE_BASE,
    TELEGRAM_BOT_TOKEN,
    POLLING_TIMEOUT,
    MAX_MESSAGE_LENGTH,
    POLLING_OFFSET_SLEEP,
)
from logging_config import get_logger

logger = get_logger(__name__)

# Token fingerprint for safe identification (last 4 chars)
TOKEN_FINGERPRINT = TELEGRAM_BOT_TOKEN[-4:] if len(TELEGRAM_BOT_TOKEN) > 4 else "****"

# Pattern to redact tokens from URLs in error messages
_TOKEN_IN_URL = re.compile(r"bot\d{8,12}:[A-Za-z0-9_\-]{20,60}")


def _redact_token(text: str) -> str:
    """Replace bot token in text with [REDACTED]."""
    return _TOKEN_IN_URL.sub("bot[REDACTED]", text)


class TelegramService:
    """
    Telegram Bot API client with connection pooling and retry logic.

    Attributes:
        session: A requests.Session with connection pooling.
        base_url: The Telegram Bot API base URL including the token.
        token_fingerprint: Last 4 chars of the token (for safe logging).
    """

    def __init__(self) -> None:
        self.session = requests.Session()
        self.base_url = TELEGRAM_API_BASE
        self.file_url = TELEGRAM_FILE_BASE
        self.token_fingerprint = TOKEN_FINGERPRINT
        logger.info(
            "TelegramService initialized (token fingerprint: ...%s)",
            self.token_fingerprint,
        )

    def delete_webhook(self, drop_pending: bool = False) -> bool:
        """
        Delete any active webhook to allow long-polling (fixes 409 Conflict).

        Retries up to 3 times with backoff. Optionally drops pending updates
        to clear any backlog from a previous webhook instance.

        Args:
            drop_pending: If True, drops all pending updates from Telegram.
                         Use with caution during startup.

        Returns:
            True if webhook was successfully deleted.
        """
        max_retries = 3
        backoff = 2.0

        for attempt in range(1, max_retries + 1):
            try:
                logger.info(
                    "Deleting webhook (attempt %d/%d, drop_pending=%s)...",
                    attempt, max_retries, drop_pending,
                )
                params: Dict[str, Any] = {}
                if drop_pending:
                    params["drop_pending_updates"] = True

                resp = self.session.post(
                    f"{self.base_url}/deleteWebhook",
                    params=params,
                    timeout=15,
                )
                resp.raise_for_status()
                data = resp.json()

                if data.get("ok"):
                    logger.info("Webhook deleted successfully.")
                    return True

                logger.warning(
                    "Failed to delete webhook: %s",
                    data.get("description", "Unknown error"),
                )

            except requests.exceptions.RequestException as exc:
                # Redact token from error message
                error_msg = _redact_token(str(exc))
                logger.warning(
                    "Error deleting webhook (attempt %d): %s",
                    attempt, error_msg,
                )

            if attempt < max_retries:
                time.sleep(backoff)
                backoff *= 1.5

        logger.error(
            "Webhook deletion failed after %d attempts. "
            "Bot may encounter 409 Conflict.",
            max_retries,
        )
        return False

    def get_webhook_info(self) -> Optional[Dict[str, Any]]:
        """
        Get current webhook status from Telegram API.

        Returns:
            Webhook info dict or None on error.
        """
        try:
            resp = self.session.get(
                f"{self.base_url}/getWebhookInfo",
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("ok"):
                return data.get("result")
            return None
        except requests.exceptions.RequestException as exc:
            logger.warning("Failed to get webhook info: %s", _redact_token(str(exc)))
            return None

    def get_updates(
        self,
        offset: int = 0,
        timeout: int = POLLING_TIMEOUT,
    ) -> List[Dict[str, Any]]:
        """
        Fetch pending updates from Telegram.

        Args:
            offset: The offset of the first update to return.
            timeout: Long-polling timeout in seconds.

        Returns:
            A list of update dictionaries, or an empty list on error.
        """
        try:
            resp = self.session.get(
                f"{self.base_url}/getUpdates",
                params={"offset": offset, "timeout": timeout},
                timeout=timeout + 10,
            )
            resp.raise_for_status()
            data = resp.json()
            if not data.get("ok"):
                description = data.get("description", "No description")
                if "conflict" in description.lower():
                    logger.error(
                        "CONFLICT ERROR (409): Another bot instance is running "
                        "with the same token (fingerprint: ...%s). "
                        "Check for duplicate deployments or stale webhook.",
                        self.token_fingerprint,
                    )
                else:
                    logger.warning("getUpdates returned ok=false: %s", description)
                return []
            return data.get("result", [])
        except requests.exceptions.RequestException as exc:
            # Redact token from URL in error
            error_msg = _redact_token(str(exc))
            logger.error("Failed to get updates: %s", error_msg)
            return []

    def send_message(
        self,
        chat_id: Union[int, str],
        text: str,
        reply_to_message_id: Optional[int] = None,
        parse_mode: Optional[str] = None,
    ) -> bool:
        """
        Send a text message, automatically chunking if it exceeds the limit.

        Args:
            chat_id: The target chat ID.
            text: The message text.
            reply_to_message_id: Optional message ID to reply to.
            parse_mode: Optional parse mode (Markdown, HTML, etc.).

        Returns:
            True if all chunks sent successfully, False otherwise.
        """
        if not text or not text.strip():
            return False

        chunks = self._split_message(text)
        for i, chunk in enumerate(chunks):
            try:
                params: Dict[str, Any] = {
                    "chat_id": chat_id,
                    "text": chunk,
                    "disable_web_page_preview": True,
                }
                if reply_to_message_id:
                    params["reply_to_message_id"] = reply_to_message_id
                if parse_mode:
                    params["parse_mode"] = parse_mode

                resp = self.session.post(
                    f"{self.base_url}/sendMessage",
                    json=params,
                    timeout=30,
                )
                resp.raise_for_status()
                result = resp.json()
                if not result.get("ok"):
                    logger.warning(
                        "sendMessage failed: %s", result.get("description")
                    )
                    return False
                # Only pace ourselves BETWEEN chunks of a multi-part message
                # (Telegram rate-limit courtesy) -- no need to delay after the
                # last (or only) chunk since nothing else is being sent.
                if i < len(chunks) - 1:
                    time.sleep(POLLING_OFFSET_SLEEP)
            except requests.exceptions.RequestException as exc:
                error_msg = _redact_token(str(exc))
                logger.error("Failed to send message: %s", error_msg)
                return False
        return True

    def send_photo_bytes(
        self,
        chat_id: Union[int, str],
        photo_bytes: bytes,
        filename: str = "plot.png",
        caption: Optional[str] = None,
        reply_to_message_id: Optional[int] = None,
    ) -> bool:
        """
        Send a photo (PNG bytes) to a chat.

        Args:
            chat_id: The target chat ID.
            photo_bytes: Raw PNG image bytes.
            filename: Suggested filename.
            caption: Optional caption (max 1024 chars).
            reply_to_message_id: Optional message ID to reply to.

        Returns:
            True if sent successfully, False otherwise.
        """
        try:
            files = {"photo": (filename, io.BytesIO(photo_bytes), "image/png")}
            params: Dict[str, Any] = {"chat_id": chat_id}
            if caption:
                params["caption"] = caption[:1024]
            if reply_to_message_id:
                params["reply_to_message_id"] = reply_to_message_id

            resp = self.session.post(
                f"{self.base_url}/sendPhoto",
                data=params,
                files=files,
                timeout=60,
            )
            resp.raise_for_status()
            return True
        except requests.exceptions.RequestException as exc:
            error_msg = _redact_token(str(exc))
            logger.error("Failed to send photo: %s", error_msg)
            return False

    def send_document(
        self,
        chat_id: Union[int, str],
        content: bytes,
        filename: str,
        caption: Optional[str] = None,
        reply_to_message_id: Optional[int] = None,
    ) -> bool:
        """
        Send a document file to a chat.

        Args:
            chat_id: The target chat ID.
            content: Raw file bytes.
            filename: The filename to send.
            caption: Optional caption.
            reply_to_message_id: Optional message ID to reply to.

        Returns:
            True if sent successfully, False otherwise.
        """
        try:
            files = {"document": (filename, io.BytesIO(content))}
            params: Dict[str, Any] = {"chat_id": chat_id}
            if caption:
                params["caption"] = caption[:1024]
            if reply_to_message_id:
                params["reply_to_message_id"] = reply_to_message_id

            resp = self.session.post(
                f"{self.base_url}/sendDocument",
                data=params,
                files=files,
                timeout=60,
            )
            resp.raise_for_status()
            return True
        except requests.exceptions.RequestException as exc:
            error_msg = _redact_token(str(exc))
            logger.error("Failed to send document: %s", error_msg)
            return False

    def download_file(self, file_path: str) -> Optional[bytes]:
        """
        Download a file from Telegram's file server.

        Args:
            file_path: The file_path from getFile API response.

        Returns:
            Raw file bytes, or None on error.
        """
        try:
            url = f"{self.file_url}/{file_path}"
            resp = self.session.get(url, timeout=60)
            resp.raise_for_status()
            return resp.content
        except requests.exceptions.RequestException as exc:
            error_msg = _redact_token(str(exc))
            logger.error("Failed to download file: %s", error_msg)
            return None

    def get_file_path(self, file_id: str) -> Optional[str]:
        """
        Get the download path for a file.

        Args:
            file_id: The file_id from the message.

        Returns:
            The file_path string, or None on error.
        """
        try:
            resp = self.session.get(
                f"{self.base_url}/getFile",
                params={"file_id": file_id},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("ok"):
                return data.get("result", {}).get("file_path")
            logger.warning("getFile failed: %s", data.get("description"))
            return None
        except requests.exceptions.RequestException as exc:
            error_msg = _redact_token(str(exc))
            logger.error("Failed to get file path: %s", error_msg)
            return None

    @staticmethod
    def _split_message(text: str) -> List[str]:
        """
        Split a long message into chunks that fit within Telegram's limit.

        Splits on paragraph boundaries (double newline) first,
        then on single newlines, then on spaces, then hard-cuts.

        Args:
            text: The full message text.

        Returns:
            A list of message chunks.
        """
        if len(text) <= MAX_MESSAGE_LENGTH:
            return [text]

        chunks: List[str] = []
        remaining = text

        while remaining:
            if len(remaining) <= MAX_MESSAGE_LENGTH:
                chunks.append(remaining)
                break

            # Try splitting on double newline (paragraph)
            split_pos = remaining[:MAX_MESSAGE_LENGTH].rfind("\n\n")
            if split_pos == -1:
                split_pos = remaining[:MAX_MESSAGE_LENGTH].rfind("\n")
            if split_pos == -1:
                split_pos = remaining[:MAX_MESSAGE_LENGTH].rfind(" ")
            if split_pos == -1:
                split_pos = MAX_MESSAGE_LENGTH

            chunks.append(remaining[:split_pos].rstrip())
            remaining = remaining[split_pos:].lstrip()

        return chunks

    def close(self) -> None:
        """Close the HTTP session and release connections."""
        self.session.close()
        logger.info("TelegramService session closed")
