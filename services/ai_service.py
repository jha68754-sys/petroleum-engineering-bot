"""
AI / LLM service module.

Handles all communication with the Groq API (text and vision).
Implements retry with exponential backoff, response caching,
system prompt loading, and structured error handling.
"""

from __future__ import annotations

import json
import os
import time
from typing import Dict, List, Optional, Tuple

import requests

from config import (
    GROQ_API_KEY,
    GROQ_API_BASE,
    TEXT_MODEL,
    VISION_MODEL,
    AI_TEMPERATURE,
    AI_MAX_TOKENS_TEXT,
    AI_MAX_TOKENS_VISION,
    AI_REQUEST_TIMEOUT,
    AI_MAX_RETRIES,
    AI_MAX_VISION_RETRIES,
    AI_RATE_LIMIT_BACKOFF_BASE,
    MAX_CONTEXT_CHARS,
)
from constants import SYSTEM_PROMPT_FILE
from logging_config import get_logger
from models.pvt_models import AIResponse

logger = get_logger(__name__)


class AIService:
    """
    AI/LLM client for Groq API.

    Handles both text and vision (image) requests with retry logic,
    caching, and system prompt management.

    Attributes:
        session: Connection-pooled HTTP session.
        system_prompt: The loaded system prompt text.
        response_cache: Simple in-memory LRU cache for text responses.
    """

    MAX_CACHE_SIZE = 128

    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
        })
        self.system_prompt: str = self._load_system_prompt()
        self.response_cache: Dict[str, AIResponse] = {}

    @staticmethod
    def _load_system_prompt() -> str:
        """
        Load the system prompt from the templates file.

        Returns:
            The system prompt text, or a minimal fallback if the file is missing.
        """
        try:
            with open(SYSTEM_PROMPT_FILE, "r", encoding="utf-8") as f:
                prompt = f.read()
            logger.info("System prompt loaded from %s (%d chars)", SYSTEM_PROMPT_FILE, len(prompt))
            return prompt
        except FileNotFoundError:
            logger.error(
                "System prompt file not found: %s. Using minimal fallback.",
                SYSTEM_PROMPT_FILE,
            )
            return (
                "You are a Petroleum Engineering assistant. "
                "Answer questions about PVT, reservoir engineering, "
                "drilling, production, and economics. Be precise and professional."
            )

    def ask_text(
        self,
        user_message: str,
        system_prompt: Optional[str] = None,
        chat_history: Optional[List[Dict[str, str]]] = None,
        file_context: Optional[str] = None,
    ) -> AIResponse:
        """
        Send a text message to the AI and get a response.

        Args:
            user_message: The user's message text.
            system_prompt: Override system prompt (default: loaded from file).
            chat_history: Optional conversation history.
            file_context: Optional extracted file context to append.

        Returns:
            AIResponse with content, model name, and metadata.

        Raises:
            RuntimeError: If all retries fail.
        """
        prompt = system_prompt or self.system_prompt

        # Build the message payload
        messages: List[Dict[str, str]] = [{"role": "system", "content": prompt}]

        if chat_history:
            # Truncate history to fit within context limits
            for msg in chat_history[-10:]:  # keep last 10 messages
                messages.append({"role": msg["role"], "content": msg["content"]})

        if file_context:
            user_msg = user_message
            if len(file_context) > MAX_CONTEXT_CHARS:
                file_context = file_context[:MAX_CONTEXT_CHARS] + "\n...[truncated]"
            full_content = f"{user_msg}\n\n--- FILE CONTEXT ---\n{file_context}"
            messages.append({"role": "user", "content": full_content})
        else:
            messages.append({"role": "user", "content": user_message})

        # Check cache
        cache_key = json.dumps(messages, sort_keys=True)[:2000]
        if cache_key in self.response_cache:
            cached = self.response_cache[cache_key]
            logger.info("AI response served from cache (cached=%s)", cached.content[:50])
            return cached

        payload = {
            "model": TEXT_MODEL,
            "messages": messages,
            "temperature": AI_TEMPERATURE,
            "max_tokens": AI_MAX_TOKENS_TEXT,
        }

        for attempt in range(AI_MAX_RETRIES):
            try:
                resp = self.session.post(
                    GROQ_API_BASE,
                    json=payload,
                    timeout=AI_REQUEST_TIMEOUT,
                )

                if resp.status_code == 429:
                    # Rate limit -- exponential backoff
                    backoff = AI_RATE_LIMIT_BACKOFF_BASE ** (attempt + 1)
                    logger.warning(
                        "Rate limited by Groq. Retrying in %ds (attempt %d/%d)",
                        backoff, attempt + 1, AI_MAX_RETRIES,
                    )
                    time.sleep(backoff)
                    continue

                resp.raise_for_status()
                data = resp.json()

                content = (
                    data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                )
                usage = data.get("usage", {})
                total_tokens = usage.get("total_tokens")

                result = AIResponse(
                    content=content,
                    model=data.get("model", TEXT_MODEL),
                    tokens_used=total_tokens,
                    cached=False,
                )

                # Cache the response
                if len(self.response_cache) < self.MAX_CACHE_SIZE:
                    self.response_cache[cache_key] = result

                logger.info(
                    "AI response received (model=%s, tokens=%s, chars=%d)",
                    result.model, str(total_tokens), len(content),
                )
                return result

            except requests.exceptions.RequestException as exc:
                logger.warning(
                    "AI request failed (attempt %d/%d): %s",
                    attempt + 1, AI_MAX_RETRIES, exc,
                )
                if attempt < AI_MAX_RETRIES - 1:
                    time.sleep(AI_RATE_LIMIT_BACKOFF_BASE * (attempt + 1))
                else:
                    raise RuntimeError(f"AI request failed after {AI_MAX_RETRIES} attempts: {exc}") from exc

        raise RuntimeError("AI request failed: max retries exceeded")

    def ask_vision(
        self,
        image_bytes: bytes,
        image_type: str = "image/png",
        user_message: str = "Describe this petroleum engineering chart",
        system_prompt: Optional[str] = None,
    ) -> AIResponse:
        """
        Send an image to the vision AI and get a description.

        Args:
            image_bytes: Raw image bytes (PNG or JPEG).
            image_type: MIME type of the image.
            user_message: The user's question about the image.
            system_prompt: Override system prompt.

        Returns:
            AIResponse with the vision analysis.

        Raises:
            RuntimeError: If all retries fail.
        """
        prompt = system_prompt or self.system_prompt

        # Encode image to base64
        import base64
        b64_data = base64.b64encode(image_bytes).decode("utf-8")

        messages: List[Dict[str, object]] = [{"role": "system", "content": prompt}]

        messages.append({
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{image_type};base64,{b64_data}",
                    },
                },
                {
                    "type": "text",
                    "text": user_message,
                },
            ],
        })

        payload = {
            "model": VISION_MODEL,
            "messages": messages,
            "temperature": AI_TEMPERATURE,
            "max_tokens": AI_MAX_TOKENS_VISION,
        }

        for attempt in range(AI_MAX_VISION_RETRIES):
            try:
                resp = self.session.post(
                    GROQ_API_BASE,
                    json=payload,
                    timeout=AI_REQUEST_TIMEOUT,
                )

                if resp.status_code == 429:
                    backoff = AI_RATE_LIMIT_BACKOFF_BASE ** (attempt + 1)
                    logger.warning(
                        "Vision API rate limited. Retrying in %ds (attempt %d/%d)",
                        backoff, attempt + 1, AI_MAX_VISION_RETRIES,
                    )
                    time.sleep(backoff)
                    continue

                resp.raise_for_status()
                data = resp.json()

                content = (
                    data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                )

                return AIResponse(
                    content=content,
                    model=data.get("model", VISION_MODEL),
                    cached=False,
                )

            except requests.exceptions.RequestException as exc:
                logger.warning(
                    "Vision request failed (attempt %d/%d): %s",
                    attempt + 1, AI_MAX_VISION_RETRIES, exc,
                )
                if attempt < AI_MAX_VISION_RETRIES - 1:
                    time.sleep(AI_RATE_LIMIT_BACKOFF_BASE * (attempt + 1))
                else:
                    raise RuntimeError(
                        f"Vision request failed after {AI_MAX_VISION_RETRIES} attempts: {exc}"
                    ) from exc

        raise RuntimeError("Vision request failed: max retries exceeded")

    def clear_cache(self) -> None:
        """Clear the response cache."""
        self.response_cache.clear()
        logger.info("AI response cache cleared")

    def close(self) -> None:
        """Close the HTTP session."""
        self.session.close()
        logger.info("AIService session closed")
