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


def test_batch_of_newline_separated_questions_is_answered_independently():
    batch = "\n".join([
        "What is Bo?",
        "شن وحدة Rs؟",
        "الفرق بين Bo و Bg؟",
        "عرفلي Pwf و Pwh",
        "What is the unit of permeability?",
        "Calculate Bo",
    ])
    response = answer_knowledge_question(batch)
    assert response is not None
    assert response.count("Question ") == 6
    assert "Oil Formation Volume Factor" in response
    assert "Common unit: scf/STB" in response
    assert "Bo vs Bg" in response
    assert "Flowing Bottomhole Pressure" in response
    assert "Wellhead Pressure" in response
    assert "Calculation bridge for Bo" in response


def test_flattened_question_batch_is_split_at_question_boundaries():
    batch = "What is Bo? What is Bg? شن وحدة Rs؟ What is Pwf?"
    response = answer_knowledge_question(batch)
    assert response is not None
    assert response.count("Question ") == 4
    assert "Oil Formation Volume Factor" in response
    assert "Gas Formation Volume Factor" in response
    assert "Flowing Bottomhole Pressure" in response


def test_mixed_general_text_is_not_forced_into_batch_knowledge_response():
    batch = "What is Bo? Please summarize my uploaded report."
    assert answer_knowledge_question(batch) is None


def test_si_units_survive_telegram_text_cleaning():
    from main import clean_text

    text = "SI unit: m³/m³; permeability: m²; viscosity: Pa·s; pressure: MPa(a)"
    cleaned = clean_text(text)
    assert "m³/m³" in cleaned
    assert "m²" in cleaned
    assert "Pa·s" in cleaned
    assert "MPa(a)" in cleaned


def test_comparison_wording_is_readable_for_bo_and_bg():
    response = answer_knowledge_question("What is the difference between Bo and Bg?")
    assert response is not None
    assert "Bo is defined as:" in response
    assert "Bg is defined as:" in response
    assert "describes bo" not in response.lower()


def test_bhp_and_pwf_comparison_states_condition_boundary():
    response = answer_knowledge_question("شن الفرق بين BHP و Pwf؟")
    assert response is not None
    assert "BHP is a broader bottomhole-pressure term" in response
    assert "يجب تحديد حالته" in response


@pytest.mark.parametrize("query, expected", [
    ("R_s", "rs"),
    ("solution gas oil ratio", "rs"),
    ("B_o", "bo"),
    ("Oil FVF", "bo"),
    ("FVF", "formation_volume_factor"),
    ("PVT", "pvt"),
    ("pressure-volume-temperature", "pvt"),
    ("viscosity", "viscosity"),
    ("اللزوجة", "viscosity"),
])
def test_prompt_aliases_resolve_to_single_canonical_entity(query, expected):
    resolution = resolve_knowledge_term(query)
    assert resolution.record is not None
    assert resolution.record.canonical_id == expected


def test_pvt_definition_is_source_backed_and_does_not_claim_a_numerical_solver():
    response = answer_knowledge_question("What is PVT?")
    assert response is not None
    assert "Pressure-Volume-Temperature" in response
    assert "الضغط والحجم ودرجة الحرارة" in response
    assert "fluid-property evaluation" in response
    assert "laboratory report" in response
    assert "No numerical" not in response


def test_generic_viscosity_definition_is_concise_and_state_aware():
    response = answer_knowledge_question("ما معنى اللزوجة؟")
    assert response is not None
    assert "Viscosity" in response
    assert "Pa·s" in response
    assert "shear rate" in response
    assert "temperature" in response.lower()


def test_rs_and_gor_comparison_distinguishes_solution_and_produced_gas():
    response = answer_knowledge_question("شن الفرق بين Rs وGOR؟")
    assert response is not None
    assert "Rs vs GOR" in response
    assert "الغاز المذاب" in response
    assert "produced gas" in response.lower()
    assert "not interchangeable" in response


def test_formula_request_without_formula_is_explicitly_limited():
    response = answer_knowledge_question("What is the formula for Pb?")
    assert response is not None
    assert "No single formula" in response
    assert "state, model, or process dependent" in response
    assert "Traceback" not in response


def test_generic_pressure_and_temperature_are_registered_as_gaps_not_fake_entities():
    layer = PetroleumKnowledgeLayer()
    gaps = {item["term"]: item for item in layer.coverage_gaps}
    assert gaps["P"]["status"] == "GAP"
    assert gaps["T"]["status"] == "GAP"
    assert layer.resolve("P").record is None
    assert layer.resolve("T").record is None


def test_malformed_or_empty_questions_are_safe():
    assert answer_knowledge_question("") is None
    response = answer_knowledge_question("What is ???")
    assert response is not None
    assert "will not invent" in response
    assert "Traceback" not in response
    assert "File \"" not in response


def test_arabic_and_english_intents_remain_explicit_and_distinct():
    assert "Common unit:" in answer_knowledge_question("ما وحدة Bo؟")
    assert "Definition:" in answer_knowledge_question("Rs definition")
    assert "Common relationship:" in answer_knowledge_question("شن صيغة Rs؟")
    assert "Related to Rs:" in answer_knowledge_question("ما المرتبط بـ Rs؟")


def test_all_verified_records_have_nonempty_source_and_verification_basis():
    layer = PetroleumKnowledgeLayer()
    for record in layer.records:
        assert record.verification_status == "VERIFIED"
        assert record.source
        assert all(str(source).strip() for source in record.source)


def test_no_duplicate_alias_points_to_multiple_entities_after_v1_extension():
    layer = PetroleumKnowledgeLayer()
    seen = {}
    for record in layer.records:
        values = [record.canonical_id, record.symbol, record.canonical_english_name, record.canonical_arabic_name, *record.aliases, *record.arabic_aliases, *record.english_aliases]
        for value in values:
            key = normalize_term(value)
            if not key:
                continue
            previous = seen.setdefault(key, record.canonical_id)
            assert previous == record.canonical_id, (key, previous, record.canonical_id)
