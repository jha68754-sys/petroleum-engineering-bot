"""Engineering Assistant Core V2 contract tests."""

from __future__ import annotations

from dataclasses import replace

import pytest

from handlers import text_handlers as th
from services.choke_engine import ChokeEngine, ChokeInput
from services.engineering_case import build_choke_case
from services.engineering_case_registry import EngineeringCaseRegistry, SessionIntegrityError
from services.engineering_context import (
    ContextResolutionError,
    EngineeringDataModel,
    EngineeringSessionContext,
    EngineeringValue,
    EngineeringValueOrigin,
    SessionContextError,
    data_model_from_case,
    session_key_for_chat,
)
from state import ENGINEERING_SESSION_CONTEXT


CHAT = "core-v2-test-chat"


def _choke_case(upstream: float, size: float = 16.0):
    inputs = ChokeInput(
        upstream_pressure_psia=upstream,
        downstream_pressure_psia=200.0,
        choke_size_64th_in=size,
        gor_scf_stb=1000.0,
        liquid_rate_bpd=1000.0,
        choke_model="gilbert_1954",
    )
    result = ChokeEngine().calculate(inputs)
    return build_choke_case(
        inputs,
        result,
        request={
            "calculation": "choke",
            "arguments": {
                "p_up": upstream,
                "p_down": 200,
                "choke": size,
                "gor": 1000,
                "q_liquid": 1000,
            },
        },
    )


def test_data_model_round_trip_and_explicit_origins():
    model = EngineeringDataModel().with_value(
        "well", "tvd_ft", 8000, unit="ft", origin=EngineeringValueOrigin.USER_PROVIDED
    ).with_value(
        "measurements", "operating_rate_bpd", 711.2, unit="STB/day", origin=EngineeringValueOrigin.CALCULATED
    )
    assert model.get("well", "tvd_ft").origin is EngineeringValueOrigin.USER_PROVIDED
    assert model.get("measurements", "operating_rate_bpd").origin is EngineeringValueOrigin.CALCULATED
    assert model.get("flow", "missing").origin is EngineeringValueOrigin.UNKNOWN
    assert model.get("flow", "missing").value is None
    assert EngineeringDataModel.from_json(model.to_json()).to_json() == model.to_json()


def test_unknown_value_cannot_carry_inferred_value():
    with pytest.raises(SessionContextError, match="UNKNOWN"):
        EngineeringValue(value=200, origin=EngineeringValueOrigin.UNKNOWN)


def test_data_model_from_case_marks_explicit_defaulted_and_calculated_values():
    case = _choke_case(1000.0)
    model = data_model_from_case(case)
    assert model.get("equipment", "upstream_pressure_psia").origin is EngineeringValueOrigin.USER_PROVIDED
    assert model.get("equipment", "choke_size_64th_in").origin is EngineeringValueOrigin.USER_PROVIDED
    # ChokeInput carries an omitted optional value; omission stays UNKNOWN.
    assert model.get("reservoir_fluid", "oil_api").origin is EngineeringValueOrigin.UNKNOWN
    assert model.get("measurements", "calculated_rate_bpd").origin is EngineeringValueOrigin.CALCULATED
    assert model.traceability["case_id"] == case.case_id


def test_session_tracks_current_and_ordered_previous_cases():
    first = _choke_case(1000.0)
    second = _choke_case(1200.0)
    context = EngineeringSessionContext().with_case(first).with_case(second)
    assert context.current_case_id == second.case_id
    assert context.resolve_case_id("current") == second.case_id
    assert context.resolve_case_id("previous") == first.case_id
    assert context.resolve_case_id("first") == first.case_id
    assert context.to_json() == EngineeringSessionContext.from_json(context.to_json()).to_json()


def test_session_reference_errors_are_typed_and_never_guess():
    empty = EngineeringSessionContext()
    with pytest.raises(ContextResolutionError) as no_current:
        empty.resolve_case_id("current")
    assert no_current.value.code == "NO_CURRENT_CASE"
    with pytest.raises(ContextResolutionError) as unknown:
        empty.resolve_case_id("maybe the case")
    assert unknown.value.code == "AMBIGUOUS_REFERENCE"
    with pytest.raises(ContextResolutionError) as no_previous:
        EngineeringSessionContext(current_case_id="a" * 64).resolve_case_id("previous")
    assert no_previous.value.code == "NO_PREVIOUS_CASE"


def test_session_persistence_survives_registry_close_and_memory_clear(tmp_path):
    path = tmp_path / "core-v2.sqlite3"
    registry = EngineeringCaseRegistry(path)
    case = _choke_case(1000.0)
    registry.save_case(case)
    context = EngineeringSessionContext().with_case(case)
    key = session_key_for_chat(CHAT)
    registry.save_session(key, context)
    registry.close()

    reloaded_registry = EngineeringCaseRegistry(path)
    reloaded = reloaded_registry.get_session(key)
    assert reloaded.current_case_id == case.case_id
    assert reloaded.current_profile.traceability["case_id"] == case.case_id
    reloaded_registry.close()


def test_session_tamper_is_rejected_with_typed_integrity_error(tmp_path):
    path = tmp_path / "tamper.sqlite3"
    registry = EngineeringCaseRegistry(path)
    case = _choke_case(1000.0)
    key = session_key_for_chat(CHAT)
    registry.save_session(key, EngineeringSessionContext().with_case(case))
    registry._connection.execute(
        "UPDATE engineering_sessions SET session_json = ? WHERE session_key = ?",
        ('{"schema_version":"engineering_session_context_v2"}', key),
    )
    registry._connection.commit()
    with pytest.raises(SessionIntegrityError):
        registry.get_session(key)
    registry.close()


def test_natural_report_previous_replay_and_comparison_are_deterministic(tmp_path, monkeypatch):
    registry = EngineeringCaseRegistry(tmp_path / "context-routing.sqlite3")
    monkeypatch.setattr(th, "_CASE_REGISTRY", registry)
    th._ENGINEERING_CASES.clear()
    th._COMPARISONS.clear()
    ENGINEERING_SESSION_CONTEXT.clear()
    first = _choke_case(1000.0)
    second = _choke_case(1200.0)
    message = {"chat": {"id": CHAT}}
    th._remember_engineering_case(first, message)
    th._remember_engineering_case(second, message)

    previous_report = th.handle_engineering_context_message(
        {**message, "text": "اعطني التقرير للحالة السابقة"}
    )
    assert previous_report is not None
    assert first.case_id in previous_report

    replay = th.handle_engineering_context_message({**message, "text": "اعمل replay"})
    assert replay is not None and "Replay comparison: MATCH" in replay

    comparison = th.handle_engineering_context_message({**message, "text": "قارنها بالحالة السابقة"})
    assert comparison is not None and "Scenario Comparison V1" in comparison
    assert "previous" in comparison and "current" in comparison
    registry.close()


def test_context_route_does_not_invoke_ai(monkeypatch):
    case = _choke_case(1000.0)
    th._ENGINEERING_CASES.clear()
    ENGINEERING_SESSION_CONTEXT.clear()
    th._remember_engineering_case(case, {"chat": {"id": CHAT}})

    class ExplodingAI:
        def ask_text(self, *args, **kwargs):
            raise AssertionError("AI must not be called for deterministic context routes")

        def ask_vision(self, *args, **kwargs):
            raise AssertionError("AI must not be called for deterministic context routes")

    class FakeTelegram:
        def __init__(self):
            self.messages = []

        def send_message(self, chat_id, text, **kwargs):
            self.messages.append((chat_id, text))

        def send_photo_bytes(self, *args, **kwargs):
            raise AssertionError("photo path is not expected")

    import main

    telegram = FakeTelegram()
    main.process_message({"chat": {"id": CHAT}, "text": "اعطني التقرير"}, telegram, ExplodingAI())
    assert telegram.messages
    assert "Engineering Case Report" in telegram.messages[0][1]


def test_calc_system_updates_chat_context_and_explicit_thp_override_recalculates(tmp_path, monkeypatch):
    registry = EngineeringCaseRegistry(tmp_path / "system-context.sqlite3")
    monkeypatch.setattr(th, "_CASE_REGISTRY", registry)
    th._ENGINEERING_CASES.clear()
    ENGINEERING_SESSION_CONTEXT.clear()
    command = (
        "/calc system model=linear pr=3000 j=1.5 tvd=8000 id=1.995 "
        "gor=1000 rs=600 api=35 gamma_g=0.65 mu_l=1 bo=1.4 "
        "t_wh=120 geothermal=1.5 choke=16 p_down=200 case=1"
    )
    response, _, error = th.handle_calc({"chat": {"id": CHAT}, "text": command}, None)
    assert error is None and "Engineering Case ID:" in response
    context = th.load_engineering_session(CHAT)
    assert context.current_case_id
    assert context.current_calculation_type == "integrated_system_v1"
    changed = th.handle_engineering_context_message(
        {"chat": {"id": CHAT}, "text": "غير THP فقط إلى 200 psia"}
    )
    assert changed and "Engineering Case ID:" in changed
    assert th.load_engineering_session(CHAT).current_case_id != context.current_case_id
    registry.close()


def test_context_thp_mutation_requires_explicit_psia_and_rejects_non_system_case():
    case = _choke_case(1000.0)
    th._ENGINEERING_CASES.clear()
    ENGINEERING_SESSION_CONTEXT.clear()
    th._remember_engineering_case(case, {"chat": {"id": CHAT}})
    missing_unit = th.handle_engineering_context_message(
        {"chat": {"id": CHAT}, "text": "غير THP إلى 200"}
    )
    assert missing_unit and "MISSING_OVERRIDE" in missing_unit
    unsupported = th.handle_engineering_context_message(
        {"chat": {"id": CHAT}, "text": "غير THP إلى 200 psia"}
    )
    assert unsupported and "UNSUPPORTED_CONTEXT_MUTATION" in unsupported
