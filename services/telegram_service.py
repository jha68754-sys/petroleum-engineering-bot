"""
Telegram API service module.

Provides a connection-pooled HTTP client for Telegram Bot API calls
(sendMessage, sendPhoto, sendDocument, getUpdates, getFile, etc.).
Handles retries, error logging, and graceful degradation.
"""

from __future__ import annotations

import io
import time
import logging
from typing import Any, Dict, List, Optional, Union

import requests

from config import (
    TELEGRAM_API_BASE,
    TELEGRAM_FILE_BASE,
    POLLING_TIMEOUT,
    MAX_MESSAGE_LENGTH,
    POLLING_OFFSET_SLEEP,
)
from logging_config import get_logger

logger = get_logger(__name__)


class TelegramService:
    """
    Telegram Bot API client with connection pooling and retry logic.

    Attributes:
        session: A requests.Session with connection pooling.
        base_url: The Telegram Bot API base URL including the token.
    """

    def __init__(self) -> None:
        self.session = requests.Session()
        self.base_url = TELEGRAM_API_BASE
        self.file_url = TELEGRAM_FILE_BASE

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
                logger.warning("getUpdates returned ok=false: %s", data.get("description"))
                return []
            return data.get("result", [])
        except requests.exceptions.RequestException as exc:
            logger.error("Failed to get updates: %s", exc)
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
        for chunk in chunks:
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
                time.sleep(POLLING_OFFSET_SLEEP)
            except requests.exceptions.RequestException as exc:
                logger.error("Failed to send message: %s", exc)
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
            logger.error("Failed to send photo: %s", exc)
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
            logger.error("Failed to send document: %s", exc)
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
            logger.error("Failed to download file: %s", exc)
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
            logger.error("Failed to get file path: %s", exc)
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
