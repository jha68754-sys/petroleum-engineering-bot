"""
AI / LLM service module.

Handles all communication with the Groq API (text and vision).
Implements retry with exponential backoff, response caching,
system prompt loading, and structured error handling.

v4.1 -- Enhanced with engineering knowledge base injection for
context-aware AI responses grounded in project knowledge.
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
from constants import (
    SYSTEM_PROMPT_FILE,
    KNOWLEDGE_BASE,
    PVT_PLOT_RULES,
    EXACT_FORMULAS,
    CORRELATIONS,
    FLUID_CLASSIFICATION_TABLE,
)
from logging_config import get_logger
from models.pvt_models import AIResponse

logger = get_logger(__name__)


class AIService:
    """
    AI/LLM client for Groq API.

    Handles both text and vision (image) requests with retry logic,
    caching, and system prompt management.

    v4.1: Now injects project engineering knowledge base into the
    message stack to ground AI responses in validated project data.
    """

    MAX_CACHE_SIZE = 128

    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
        })
        self.system_prompt: str = self._load_system_prompt()
        self.engineering_context: str = self._build_engineering_context()
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
                "You are a Senior Petroleum Engineer with 25+ years of experience. "
                "Never invent equations, correlations, or engineering facts. "
                "Prioritize project knowledge over general AI memory. "
                "Clearly distinguish verified knowledge from assumptions."
            )

    @staticmethod
    def _build_engineering_context() -> str:
        """
        Build a structured engineering knowledge context string
        from project constants to ground AI responses.

        This is injected as a system-level assistant message before
        the user's first message, ensuring the AI reasons from
        validated project data rather than hallucinating.

        Returns:
            Formatted engineering context string.
        """
        context_parts: List[str] = []

        context_parts.append("=== PROJECT ENGINEERING KNOWLEDGE BASE ===")
        context_parts.append(
            "The following is validated petroleum engineering knowledge from the project. "
            "Always ground your answers in this data. Never contradict it."
        )

        # --- Knowledge Base Entries ---
        context_parts.append("\n--- KNOWLEDGE BASE ---")
        for entry in KNOWLEDGE_BASE:
            en_name = entry.get("en", "")
            ar_name = entry.get("ar", "")
            category = entry.get("category", "")
            unit = entry.get("unit", "")
            def_ar = entry.get("def_ar", "")
            trend = entry.get("trend", "")
            rel_key = entry.get("relationship_key", "")
            typical_range = entry.get("typical_range", "")

            context_parts.append(f"\n[{category}] {en_name} ({ar_name})")
            context_parts.append(f"  Unit: {unit}")
            context_parts.append(f"  Definition (AR): {def_ar}")
            context_parts.append(f"  PVT Trend: {trend}")
            if typical_range:
                context_parts.append(f"  Typical Range: {typical_range}")
            if rel_key:
                context_parts.append(f"  Plot Key: {rel_key}")

        # --- Fluid Classification ---
        context_parts.append("\n--- FLUID CLASSIFICATION ---")
        context_parts.append(
            "Classification by GOR (scf/STB) and API Gravity (deg API):"
        )
        for fc in FLUID_CLASSIFICATION_TABLE:
            context_parts.append(
                f"  {fc['type_en']} ({fc['type_ar']}): "
                f"GOR {fc['gor_min']}-{fc['gor_max']}, API {fc['api_min']}-{fc['api_max']}"
            )

        # --- PVT Plot Rules (Deterministic Truth) ---
        context_parts.append("\n--- DETERMINISTIC PVT TRENDS (GROUND TRUTH) ---")
        context_parts.append(
            "These physical trends are ABSOLUTE. Never contradict them."
        )
        for key, rule in PVT_PLOT_RULES.items():
            context_parts.append(f"\n  [{key}] {rule['title_en']} ({rule['title_ar']})")
            if "shape" in rule:
                context_parts.append(f"    Shape: {rule['shape']}")
            if rule.get("pivot"):
                context_parts.append(f"    Pivot: {rule['pivot']}")
            context_parts.append(f"    Above Sat: {rule.get('above_saturation', 'n/a')}")
            context_parts.append(f"    At Sat: {rule.get('at_saturation', 'n/a')}")
            context_parts.append(f"    Below Sat: {rule.get('below_saturation', 'n/a')}")
            mistakes = rule.get("common_ai_mistakes", [])
            if mistakes:
                context_parts.append(f"    NEVER do: {'; '.join(mistakes)}")

        # --- Exact Formulas ---
        context_parts.append("\n--- EXACT FORMULAS (DETERMINISTIC) ---")
        context_parts.append(
            "Use these formulas for calculations. Never invent alternative equations."
        )
        for key, formula in EXACT_FORMULAS.items():
            context_parts.append(
                f"  /calc {key}: {formula['name_en']} ({formula['name_ar']})"
            )
            context_parts.append(f"    Formula: {formula['formula_str']}")
            context_parts.append(f"    Inputs: {', '.join(formula['inputs'])}")
            context_parts.append(f"    Output: {formula['output_unit']}")

        # --- Correlations ---
        context_parts.append("\n--- CORRELATIONS ---")
        context_parts.append(
            "These are correlation estimates, NOT lab-measured values. "
            "Always label them as estimates."
        )
        for key, corr in CORRELATIONS.items():
            context_parts.append(
                f"  /estimate {key}: {corr['name_en']}"
            )
            context_parts.append(f"    Formula: {corr['formula_str']}")
            context_parts.append(f"    Inputs: {', '.join(corr['inputs'])}")
            applicability = corr.get("applicability", {})
            if applicability:
                ranges = "; ".join(
                    f"{k}=[{lo},{hi}]" for k, (lo, hi) in applicability.items()
                )
                context_parts.append(f"    Validity: {ranges}")

        context_parts.append(
            "\n=== END ENGINEERING KNOWLEDGE BASE ==="
        )

        context = "\n".join(context_parts)
        logger.info(
            "Engineering context built (%d chars, %d KB entries, %d plot rules, %d formulas, %d correlations)",
            len(context),
            len(KNOWLEDGE_BASE),
            len(PVT_PLOT_RULES),
            len(EXACT_FORMULAS),
            len(CORRELATIONS),
        )
        return context

    def ask_text(
        self,
        user_message: str,
        system_prompt: Optional[str] = None,
        chat_history: Optional[List[Dict[str, str]]] = None,
        file_context: Optional[str] = None,
    ) -> AIResponse:
        """
        Send a text message to the AI and get a response.

        Message stack order:
        1. System prompt (engineering identity + rules)
        2. Engineering knowledge context (project-grounded data)
        3. Chat history (last 10 messages)
        4. User message (with optional file context)

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

        # Inject engineering knowledge context as assistant grounding.
        # Performance/cost fix: the full knowledge base is large and fixed --
        # only send it in full on the FIRST turn of a conversation (no prior
        # chat_history). On follow-up turns, the model already has it earlier
        # in this same conversation's context, so send a short reminder
        # instead of re-transmitting thousands of tokens on every call.
        if not chat_history:
            messages.append({"role": "assistant", "content": self.engineering_context})
        else:
            messages.append({
                "role": "assistant",
                "content": (
                    "(Reminder: continue grounding answers in the PROJECT ENGINEERING "
                    "KNOWLEDGE BASE, fluid classification table, deterministic PVT trends, "
                    "exact formulas, and correlations provided earlier in this conversation. "
                    "Never contradict them.)"
                ),
            })

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

        # Check cache. Key on the user-relevant tail only (history + this turn's
        # message/file context), NOT a truncated prefix of the full serialized
        # message list -- the system prompt + engineering_context are large and
        # fixed, so a naive prefix-truncated key could collide across unrelated
        # user questions and return a cached answer for the wrong question.
        import hashlib
        cache_key = hashlib.sha256(
            json.dumps(
                {
                    "history": chat_history[-10:] if chat_history else [],
                    "user_message": user_message,
                    "file_context": file_context,
                },
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
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

        # Inject engineering context for vision too
        messages.append({"role": "assistant", "content": self.engineering_context})

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
