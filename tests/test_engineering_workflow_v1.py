"""Focused contracts for Engineering Workflow Orchestrator V1."""

from __future__ import annotations

import pytest

from handlers import text_handlers as th
from services.engineering_case import build_case
from services.engineering_case_registry import EngineeringCaseRegistry
from services.engineering_workflow import (
    WorkflowError,
    parse_workflow_intent,
    render_result_interpretation,
)
from state import ENGINEERING_SESSION_CONTEXT


CHAT = "workflow-v1-test-chat"


def _system_case(thp: float, choke: float, rate: float, pwf: float, pwh: float):
    return build_case(
        "integrated_system_v1",
        request={
            "calculation": "system",
            "arguments": {"thp": thp, "choke": choke, "case": "1"},
        },
        inputs={
            "pr": 3000.0,
            "thp": thp,
            "tvd": 8000.0,
            "tubing_id_in": 1.995,
            "gor": 1000.0,
            "rs": 600.0,
            "api": 35.0,
            "gamma_g": 0.65,
            "mu_l": 1.0,
            "bo": 1.4,
            "t_wh": 120.0,
            "geothermal": 1.5,
            "choke": choke,
            "p_down": 200.0,
            "j": 1.5,
        },
        units={"rate": "STB/day", "pressure": "psia"},
        selectors={"ipr_model": "linear", "vlp_model": "beggs_brill", "choke_model": "gilbert_1954"},
        model={"engine": "IntegratedSystemEngine V1", "ipr": "linear", "vlp": "beggs_brill", "choke": "gilbert_1954"},
        result={
            "status": "OK",
            "operating_rate_bpd": rate,
            "pwf_psia": pwf,
            "wellhead_pressure_psia": pwh,
            "solver_residual_psi": 0.01,
        },
        status="OK",
    )


def test_parser_recognizes_only_bounded_natural_intents():
    assert parse_workflow_intent("احسب الإنتاج عند THP = 200 psia").kind == "natural_calculation"
    assert parse_workflow_intent("ما الذي تغيّر بين الحالة الحالية والسابقة؟").kind == "interpret"
    assert parse_workflow_intent("hello there") is None


def test_parser_keeps_natural_thp_without_unit_as_bounded_request():
    intent = parse_workflow_intent("احسب الإنتاج عند THP = 200")
    assert intent is not None
    assert intent.kind == "natural_calculation"
    assert intent.thp_psia is None


def test_render_interpretation_uses_stored_inputs_and_results_without_inference():
    previous = _system_case(100.0, 16.0, 711.218, 2525.833, 1654.175)
    current = _system_case(100.0, 32.0, 1779.072, 1813.967, 1121.143)
    text = render_result_interpretation(previous, current)
    assert previous.case_id in text
    assert current.case_id in text
    assert "Choke size" in text
    assert "16" in text and "32" in text
    assert "Operating liquid rate" in text
    assert "Delta:" in text
    assert "deterministic model comparison" in text
    assert "No recommendation" in text


def test_workflow_interpretation_is_deterministic_and_does_not_call_ai(tmp_path, monkeypatch):
    registry = EngineeringCaseRegistry(tmp_path / "workflow.sqlite3")
    monkeypatch.setattr(th, "_CASE_REGISTRY", registry)
    th._ENGINEERING_CASES.clear()
    th._COMPARISONS.clear()
    ENGINEERING_SESSION_CONTEXT.clear()
    th._remember_engineering_case(_system_case(100.0, 16.0, 711.218, 2525.833, 1654.175), {"chat": {"id": CHAT}})
    th._remember_engineering_case(_system_case(100.0, 32.0, 1779.072, 1813.967, 1121.143), {"chat": {"id": CHAT}})

    class ExplodingAI:
        def ask_text(self, *args, **kwargs):
            raise AssertionError("AI must not be called for deterministic result interpretation")

        def ask_vision(self, *args, **kwargs):
            raise AssertionError("AI must not be called for deterministic result interpretation")

    class FakeTelegram:
        def __init__(self):
            self.messages = []

        def send_message(self, chat_id, text, **kwargs):
            self.messages.append(text)

        def send_photo_bytes(self, *args, **kwargs):
            raise AssertionError("unexpected photo")

    import main

    telegram = FakeTelegram()
    main.process_message(
        {"chat": {"id": CHAT}, "text": "ما الذي تغيّر بين الحالة الحالية والسابقة؟"},
        telegram,
        ExplodingAI(),
    )
    assert len(telegram.messages) == 1
    assert "Engineering Result Interpretation" in telegram.messages[0]
    assert "Choke size" in telegram.messages[0]
    registry.close()


def test_natural_calculation_reuses_current_system_case_and_creates_new_case(tmp_path, monkeypatch):
    registry = EngineeringCaseRegistry(tmp_path / "natural-calc.sqlite3")
    monkeypatch.setattr(th, "_CASE_REGISTRY", registry)
    th._ENGINEERING_CASES.clear()
    th._COMPARISONS.clear()
    ENGINEERING_SESSION_CONTEXT.clear()

    original = _system_case(100.0, 16.0, 711.218, 2525.833, 1654.175)
    th._remember_engineering_case(original, {"chat": {"id": CHAT}})
    response = th.handle_engineering_workflow_message(
        {"chat": {"id": CHAT}, "text": "احسب الإنتاج عند THP = 200 psia"}
    )
    assert response is not None
    assert "Engineering Case ID:" in response
    updated = th.load_engineering_session(CHAT)
    assert updated.current_case_id != original.case_id
    assert updated.current_profile.get("well", "thp_psia").value == pytest.approx(200.0)
    registry.close()


def test_natural_calculation_is_safe_when_context_or_data_is_missing(tmp_path, monkeypatch):
    registry = EngineeringCaseRegistry(tmp_path / "natural-missing.sqlite3")
    monkeypatch.setattr(th, "_CASE_REGISTRY", registry)
    th._ENGINEERING_CASES.clear()
    ENGINEERING_SESSION_CONTEXT.clear()

    no_case = th.handle_engineering_workflow_message(
        {"chat": {"id": CHAT}, "text": "احسب الإنتاج عند THP = 200 psia"}
    )
    assert no_case is not None and "NO_CURRENT_CASE" in no_case

    missing_override = th.handle_engineering_workflow_message(
        {"chat": {"id": CHAT}, "text": "احسب الإنتاج"}
    )
    assert missing_override is not None and "MISSING_DATA" in missing_override
    registry.close()
