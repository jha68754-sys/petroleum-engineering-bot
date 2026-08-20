"""Quality-surface regression tests for truthful Telegram UX.

These tests do not call Telegram or an external AI service. They protect the
boundary between deterministic handlers and explanatory/free-text surfaces.
"""

from pathlib import Path

import main
from constants import HELP_MESSAGE
from handlers.command_registry import registry
from handlers.text_handlers import handle_analyze, handle_report


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_removed_commands_are_not_registered():
    """Dead /glossary and /graph surfaces must not be dispatchable."""
    assert registry.dispatch("/glossary") is None
    assert registry.dispatch("/graph") is None


def test_help_does_not_promise_removed_or_unbounded_surfaces():
    """Help must describe supported paths rather than dead feature promises."""
    assert "/glossary" not in HELP_MESSAGE
    assert "/graph" not in HELP_MESSAGE
    assert "/case report" in HELP_MESSAGE
    assert "/case replay" in HELP_MESSAGE
    assert "/report" in HELP_MESSAGE


def test_report_without_context_is_typed_and_non_fabricating(monkeypatch):
    """PVT report refuses to invent laboratory data when no file exists."""
    chat_id = "quality-report-no-context"
    monkeypatch.delitem(main.FILE_CONTEXT, chat_id, raising=False)

    result, png_bytes, doc_filename = handle_report(
        {"chat": {"id": chat_id}, "text": "/report"}, None
    )

    assert png_bytes is None
    assert doc_filename is None
    assert result.startswith("Engineering Data Requirement")
    assert "No uploaded document" in result
    assert "will not fabricate" in result


def test_analyze_without_context_explains_required_next_step(monkeypatch):
    """Document analysis must not silently fall through to an AI call."""
    chat_id = "quality-analyze-no-context"
    monkeypatch.delitem(main.FILE_CONTEXT, chat_id, raising=False)

    result, png_bytes, doc_filename = handle_analyze(
        {"chat": {"id": chat_id}, "text": "/analyze"}, None
    )

    assert result == "No document uploaded. Upload a PDF, DOCX, Excel, or CSV file first."
    assert png_bytes is None
    assert doc_filename is None


def test_ai_prompt_contains_deterministic_boundary():
    """The free-text model is explicitly forbidden from fabricating calculations."""
    prompt = (REPO_ROOT / "prompts" / "system_prompt.txt").read_text(encoding="utf-8")
    assert "DETERMINISTIC CALCULATION BOUNDARY" in prompt
    assert "do not guess, interpolate, or invent a value" in prompt
    assert "Never claim that a report, plot, file, calculation, replay" in prompt
    assert "Do not silently change a result" in prompt


def test_help_contains_truthful_calculation_disclaimer():
    """The public help text must distinguish deterministic calculations from AI."""
    lowered = HELP_MESSAGE.lower()
    assert "deterministic" in lowered
    assert "ai" in lowered or "الذكاء" in lowered
    assert "hallucination" in lowered or "اختلاق" in lowered or "fabricat" in lowered
