"""Focused contract tests for Engineering Q&A / Reasoning Layer V1."""

from services.petroleum_qa import EngineeringQALayer, answer_engineering_question


def test_definition_is_composed_from_verified_knowledge_with_source_basis():
    response = answer_engineering_question("What is Bo?")
    assert response is not None
    assert "Bo — Oil Formation Volume Factor" in response
    assert "معامل حجم تكوين النفط" in response
    assert "Verification status: VERIFIED" in response
    assert "Source basis:" in response
    assert "http" in response
    assert "{" not in response and "}" not in response


def test_engineering_meaning_intent_is_distinct_from_definition():
    response = answer_engineering_question("شن معناها هندسيًا Rs؟")
    assert response is not None
    assert "Engineering meaning:" in response
    assert "المعنى" not in response or "Engineering meaning" in response
    assert "Source basis:" in response


def test_definition_and_unit_are_composed_together():
    response = answer_engineering_question("Give me the definition and unit of Bo.")
    assert response is not None
    assert "Definition:" in response
    assert "Engineering meaning:" in response
    assert "Common unit: rb/STB" in response
    assert "SI unit where applicable: m³/m³" in response
    assert "Source basis:" in response


def test_unit_intent_understands_informal_arabic_request():
    response = answer_engineering_question("نبي وحدة Rs")
    assert response is not None
    assert "Common unit: scf/STB" in response
    assert "SI unit where applicable: m³/m³" in response
    assert "Definition:" not in response


def test_rs_pb_relationship_uses_verified_state_relationship():
    response = answer_engineering_question("شن العلاقة بين Rs و Pb؟")
    assert response is not None
    assert "Rs and Pb are linked through the oil PVT phase boundary." in response
    assert "علاقة Rs:" in response
    assert "No numerical value is inferred" in response
    assert "Source basis:" in response


def test_related_concepts_are_listed_for_arabic_related_request():
    response = answer_engineering_question("شن المصطلحات المرتبطة بـ PVT؟")
    assert response is not None
    assert "Related to PVT:" in response
    assert "Source basis:" in response
    assert "Bo" in response or "Pb" in response


def test_three_term_comparison_is_not_reduced_to_two_terms():
    response = answer_engineering_question("شن الفرق بين Bo و Bg و Bw؟")
    assert response is not None
    assert "Bo vs Bg vs Bw" in response
    assert "Oil Formation Volume Factor" in response
    assert "Gas Formation Volume Factor" in response
    assert "Water Formation Volume Factor" in response
    assert "not interchangeable" in response


def test_comparison_with_usage_is_one_coherent_answer():
    response = answer_engineering_question("شن الفرق بين Rs و GOR ووين نستخدم كل واحد؟")
    assert response is not None
    assert "Rs vs GOR" in response
    assert "Usage of each term:" in response
    assert "Rs:" in response and "GOR:" in response
    assert "not interchangeable" in response


def test_context_question_connects_rs_to_pb_without_calculating():
    response = answer_engineering_question("شن يصير لـ Rs لما الضغط ينزل تحت Pb؟")
    assert response is not None
    assert "Pressure condition: below Pb" in response
    assert "Rs response:" in response
    assert "below Pb it declines as gas evolves" in response
    assert "استجابة Rs: عند انخفاض الضغط تحت Pb، تنخفض Rs" in response
    assert "استجابة Rs: Above Pb" not in response
    assert "ليست حسابًا عدديًا" in response


def test_explanation_intent_builds_simple_engineering_explanation():
    response = answer_engineering_question("اشرحلي PVT بطريقة بسيطة لكن هندسية.")
    assert response is not None
    assert "Simple engineering explanation:" in response
    assert "Pressure-Volume-Temperature" in response
    assert "Why it matters:" in response
    assert "Source basis:" in response


def test_calculation_request_bridges_to_released_path_only():
    response = answer_engineering_question("عندي قيمة ضغط، احسبلي Bo")
    assert response is not None
    assert "Calculation bridge for Bo" in response
    assert "/calc vlp" in response
    assert "does not create a second calculator" in response
    assert "No numerical answer" not in response


def test_ambiguous_symbols_are_clarified_without_random_resolution():
    for query, expected in [
        ("What is P?", "Pwf"),
        ("ما معنى T؟", "reservoir temperature"),
        ("What is B?", "Bo"),
        ("What is GOR?", "solution GOR (Rs)"),
        ("What is pressure?", "Pwf"),
        ("ما معنى درجة الحرارة؟", "reservoir temperature"),
    ]:
        response = answer_engineering_question(query)
        assert response is not None, query
        assert expected in response, query
        assert "no numerical value was inferred" in response


def test_batch_keeps_known_and_unknown_questions_in_one_safe_response():
    batch = "\n".join(["What is Bo?", "What is an unsupported rock magic term?"])
    response = answer_engineering_question(batch)
    assert response is not None
    assert response.count("Question ") == 2
    assert "Oil Formation Volume Factor" in response
    assert "UNVERIFIED / NOT CURRENTLY COVERED" in response
    assert "will not invent" in response
    assert "Source basis:" in response


def test_general_text_remains_available_to_the_existing_ai_fallback():
    assert answer_engineering_question("Please summarize my uploaded report") is None
    assert answer_engineering_question("hello there") is None


def test_main_dispatches_natural_qa_before_ai_fallback():
    import main

    class FakeTelegram:
        def __init__(self):
            self.messages = []

        def send_message(self, chat_id, text, **kwargs):
            self.messages.append((chat_id, text))

    class FailIfCalledAI:
        def ask_text(self, *args, **kwargs):
            raise AssertionError("AI must not handle a verified Knowledge question")

    telegram = FakeTelegram()
    main.process_message(
        {"chat": {"id": 7}, "message_id": 11, "text": "شن معنى Rs؟"},
        telegram,
        FailIfCalledAI(),
    )
    assert len(telegram.messages) == 1
    assert "Solution Gas-Oil Ratio" in telegram.messages[0][1]
    assert "Source basis:" in telegram.messages[0][1]


def test_define_command_uses_the_same_qa_composer():
    from handlers import text_handlers

    response, png, filename = text_handlers.handle_define({"text": "/define Rs"}, None)
    assert png is None
    assert filename is None
    assert response is not None
    assert "Solution Gas-Oil Ratio" in response
    assert "Source basis:" in response


def test_layer_can_be_injected_with_the_existing_knowledge_source():
    layer = EngineeringQALayer()
    assert layer.knowledge.dataset_status == "VERIFIED_CORE_TERMS"
    assert len(layer.knowledge.records) == 60
