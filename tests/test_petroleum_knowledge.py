import json
from pathlib import Path

import pytest

from services.petroleum_knowledge import (
    PetroleumKnowledgeLayer,
    answer_knowledge_question,
    get_knowledge_record,
    normalize_term,
    resolve_knowledge_term,
)


REQUIRED_IDS = {
    "bo", "bg", "bw", "rs", "gor", "pb", "pdew", "mu_o", "mu_g", "mu_w",
    "api_gravity", "z_factor", "compressibility", "porosity", "permeability",
    "sw", "so", "sg", "swi", "sor", "relative_permeability", "capillary_pressure",
    "reservoir_pressure", "reservoir_temperature", "q", "qo", "qg", "qw", "bhp",
    "pwf", "pwh", "thp", "pi", "ipr", "vlp", "drawdown", "water_cut", "wor",
    "gas_lift", "lift_gas", "gas_injection_rate", "choke", "upstream_pressure",
    "downstream_pressure", "critical_flow", "subcritical_flow", "flow_regime",
}


def test_dataset_is_structured_and_contains_verified_core_terms():
    layer = PetroleumKnowledgeLayer()
    assert REQUIRED_IDS.issubset({record.canonical_id for record in layer.records})
    assert len(layer.records) >= len(REQUIRED_IDS)
    for record in layer.records:
        assert record.verification_status in {"VERIFIED", "UNVERIFIED / REVIEW REQUIRED"}
        assert record.definition
        assert record.definition_ar
        assert record.unit
        assert record.domain
        assert record.source


def test_dataset_is_valid_json_and_versioned():
    path = Path(__file__).parents[1] / "data" / "petroleum_knowledge_v1.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "petroleum_knowledge_v1"
    assert isinstance(payload["records"], list)


@pytest.mark.parametrize("query", ["Bo", "bo", "B_o", "beta o", "BETA O", "oil FVF", "oil formation volume factor", "معامل حجم تكوين النفط", "بيتا او"])
def test_bo_symbol_name_alias_and_arabic_resolution(query):
    resolution = resolve_knowledge_term(query)
    assert resolution.record is not None
    assert resolution.record.canonical_id == "bo"


@pytest.mark.parametrize("query, expected", [
    ("Rs", "rs"),
    ("solution gas-oil ratio", "rs"),
    ("نسبة الغاز المذاب", "rs"),
    ("Bg", "bg"),
    ("bubble point", "pb"),
    ("ضغط نقطة الفقاعة", "pb"),
    ("Pwf", "pwf"),
    ("Pwh", "pwh"),
    ("PI", "pi"),
    ("IPR", "ipr"),
    ("VLP", "vlp"),
    ("API Gravity", "api_gravity"),
    ("Porosity", "porosity"),
    ("المسامية", "porosity"),
    ("Permeability", "permeability"),
    ("النفاذية", "permeability"),
])
def test_core_term_resolution(query, expected):
    resolution = resolve_knowledge_term(query)
    assert resolution.record is not None
    assert resolution.record.canonical_id == expected


def test_normalization_handles_case_spacing_punctuation_and_arabic_variants():
    assert normalize_term(" B_o ") == "b o"
    assert normalize_term("بيتا أو") == normalize_term("بيتا او")
    assert normalize_term("μo") == "muo"


def test_definition_answer_is_engineering_first_and_bilingual():
    response = answer_knowledge_question("What is Bo?")
    assert response is not None
    assert "Bo — Oil Formation Volume Factor" in response
    assert "معامل حجم تكوين النفط" in response
    assert "Definition:" in response
    assert "Unit: rb/STB" in response
    assert "Verification status: VERIFIED" in response
    assert "{" not in response and "}" not in response


def test_arabic_definition_answer():
    response = answer_knowledge_question("شن معنى Rs؟")
    assert response is not None
    assert "Rs — Solution Gas-Oil Ratio" in response
    assert "نسبة الغاز المذاب إلى النفط" in response
    assert "scf/STB" in response


def test_symbol_only_question_is_supported():
    response = answer_knowledge_question("Pwf")
    assert response is not None
    assert "Flowing Bottomhole Pressure" in response
    assert "ضغط قاع البئر أثناء الجريان" in response


def test_unit_lookup_returns_common_and_si_units():
    response = answer_knowledge_question("What is the unit of permeability?")
    assert response is not None
    assert "Common unit: darcy or millidarcy" in response
    assert "SI unit where applicable: m²" in response
    assert "Dimensional meaning" in response


def test_arabic_unit_lookup():
    response = answer_knowledge_question("شن وحدة Rs؟")
    assert response is not None
    assert "Common unit: scf/STB" in response


def test_formula_lookup_explains_variables_without_calculating():
    response = answer_knowledge_question("What is the formula for PI?")
    assert response is not None
    assert "PI = q / (Pr - Pwf)" in response
    assert "productivity index" in response
    assert "source of numerical results" in response


def test_comparison_returns_concise_non_interchangeability_explanation():
    response = answer_knowledge_question("What is the difference between Bo and Bg?")
    assert response is not None
    assert "Bo vs Bg" in response
    assert "معامل حجم تكوين النفط" in response
    assert "معامل حجم تكوين الغاز" in response
    assert "not interchangeable" in response


def test_arabic_comparison_works():
    response = answer_knowledge_question("الفرق بين Bo و Bg؟")
    assert response is not None
    assert "Bo vs Bg" in response
    assert "Units:" in response


def test_related_term_lookup():
    response = answer_knowledge_question("What is related to Rs?")
    assert response is not None
    assert "Related to Rs:" in response
    assert "Bo" in response or "Pb" in response


def test_context_lookup():
    response = answer_knowledge_question("Where is Pwf used?")
    assert response is not None
    assert "Used for:" in response
    assert "IPR" in response


def test_calculation_bridge_does_not_invent_a_new_number():
    response = answer_knowledge_question("Calculate Bo")
    assert response is not None
    assert "Calculation bridge for Bo" in response
    assert "/calc vlp" in response
    assert "does not create a second calculator" in response
    assert "{" not in response and "}" not in response


def test_calculation_bridge_for_ipr_uses_released_command():
    response = answer_knowledge_question("احسب IPR")
    assert response is not None
    assert "/calc ipr" in response
    assert "No numerical answer" not in response


def test_unknown_term_is_safe_and_not_fabricated():
    response = answer_knowledge_question("What is super permeability magic?")
    assert response is not None
    assert "verified Petroleum Engineering record" in response
    assert "will not invent" in response


def test_ambiguous_generic_pressure_question_requests_clarification():
    response = answer_knowledge_question("What is pressure?")
    assert response is not None
    assert "not one unambiguous meaning" in response
    assert "Pwf" in response and "THP" in response


def test_arabic_ambiguous_pressure_question_requests_clarification():
    response = answer_knowledge_question("ما معنى الضغط؟")
    assert response is not None
    assert "لا يوجد معنى واحد" in response


def test_unrelated_free_text_is_left_for_general_ai_path():
    assert answer_knowledge_question("Please summarize my uploaded report") is None
    assert answer_knowledge_question("hello there") is None


def test_public_record_has_no_internal_dataset_fields():
    record = get_knowledge_record("bo")
    assert record is not None
    public = record.to_public_dict()
    assert "canonical_id" not in public
    assert "aliases" not in public
    assert public["symbol"] == "Bo"


def test_define_command_resolves_deterministically():
    from handlers import text_handlers as th

    response, png, filename = th.handle_define({"text": "/define Bo"}, None)
    assert png is None and filename is None
    assert "Oil Formation Volume Factor" in response


def test_define_command_usage_is_human_readable():
    from handlers import text_handlers as th

    response, png, filename = th.handle_define({"text": "/define"}, None)
    assert png is None and filename is None
    assert response.startswith("Usage: /define <term>")


def test_command_registry_registers_define_aliases():
    from handlers.command_registry import registry

    assert registry.dispatch("/define Bo") is not None
    assert registry.dispatch("/meaning Bo") is not None


def test_main_process_message_uses_knowledge_before_ai():
    import main

    class FakeTelegram:
        def __init__(self):
            self.messages = []

        def send_message(self, chat_id, text, reply_to_message_id=None):
            self.messages.append((chat_id, text, reply_to_message_id))

    class FakeAI:
        def __init__(self):
            self.calls = 0

        def ask_text(self, *args, **kwargs):
            self.calls += 1
            raise AssertionError("AI must not be called for a recognized term question")

    tg = FakeTelegram()
    ai = FakeAI()
    main.process_message(
        {"chat": {"id": 42}, "message_id": 7, "text": "ما معنى Bo؟"},
        tg,
        ai,
    )
    assert ai.calls == 0
    assert len(tg.messages) == 1
    assert "Oil Formation Volume Factor" in tg.messages[0][1]


def test_engineering_command_still_dispatches_as_before():
    from handlers.command_registry import registry

    assert registry.dispatch("/calc choke") is not None
    assert registry.dispatch("/calc nodal") is not None


def test_multiple_term_definition_is_not_reported_as_ambiguous():
    response = answer_knowledge_question("Define Pwf and Pwh")
    assert response is not None
    assert "Flowing Bottomhole Pressure" in response
    assert "Wellhead Pressure" in response
    assert "السؤال يطابق أكثر من مفهوم" not in response


def test_relationship_between_rs_and_bo_is_explained():
    response = answer_knowledge_question("What is the relationship between Rs and Bo?")
    assert response is not None
    assert "coupled black-oil PVT properties" in response
    assert "not interchangeable" in response
    assert "الغاز المذاب" in response


def test_numeric_calculation_request_with_extra_inputs_stays_a_bridge():
    response = answer_knowledge_question("Calculate Bo at P=1000 psia")
    assert response is not None
    assert "Calculation bridge for Bo" in response
    assert "1000" not in response
    assert "/calc vlp" in response


def test_required_term_set_has_density_and_residual_gas_records():
    for canonical_id in ("rho_o", "rho_g", "rho_w", "sgr", "rock_compressibility", "reservoir_fluid", "formation_volume_factor"):
        record = get_knowledge_record(canonical_id)
        assert record is not None
        assert record.verification_status == "VERIFIED"


def test_natural_queries_for_required_terms_are_supported():
    queries = [
        "What is Bg?", "What does Pb mean?", "What is Pwf?", "What is Pwh?",
        "Give me the definition of PI", "Explain API gravity", "What is porosity?",
        "What is permeability?", "What is IPR?", "What is VLP?",
    ]
    for query in queries:
        response = answer_knowledge_question(query)
        assert response is not None, query
        assert "I do not have a verified Petroleum Engineering record" not in response, query
