from services.problem_extraction import (
    extract_engineering_fields,
    format_problem_extraction,
    format_extraction_confirmation,
    is_extraction_confirmation,
)


def test_extracts_arabic_and_english_engineering_values():
    text = (
        "لدي بئر ضغط المكمن 3200 psia وTHP يساوي 180 psia، "
        "TVD=7500 ft، Tubing ID=2.441 in، GOR=850 scf/STB، "
        "Rs=500 scf/STB، API=32، gamma_g=0.68، mu_l=1,4 cP، "
        "Bo=1.25 rb/STB، Choke=24/64، downstream pressure=180 psia."
    )
    fields = {field.key: field for field in extract_engineering_fields(text)}
    assert fields["pr"].value == 3200
    assert fields["thp"].value == 180
    assert fields["tvd"].value == 7500
    assert fields["id"].value == 2.441
    assert fields["mu_l"].value == 1.4
    assert fields["choke"].value == 24
    assert fields["p_down"].value == 180


def test_formats_confirmation_before_calculation_and_lists_missing_inputs():
    result = format_problem_extraction("الإنتاج انخفض بعد تغيير Choke إلى 24/64، وPr=3200 psia")
    assert "لم أشغّل أي محرك حسابي بعد" in result
    assert "مقاس Choke" in result
    assert "ضغط المكمن (Pr)" in result
    assert "يلزم اختيار أساس IPR" in result
    assert "اعتمد البيانات المستخرجة" in result


def test_confirmation_is_explicit_and_does_not_start_incomplete_system_case():
    text = "Pr=3200 psia وTHP=180 psia"
    assert is_extraction_confirmation("اعتمد البيانات المستخرجة")
    assert not is_extraction_confirmation("احسب")
    result = format_extraction_confirmation(text)
    assert "تم اعتماد البيانات المستخرجة مبدئيًا" in result
    assert "لا أستطيع تشغيل حساب System بعد" in result
    assert "أساس IPR" in result


def test_complete_confirmation_builds_reviewable_command_only():
    text = (
        "Pr=3200 psia THP=180 psia TVD=7500 ft Tubing ID=2.441 in "
        "GOR=850 Rs=500 API=32 gamma_g=0.68 mu_l=1.4 Bo=1.25 "
        "t_wh=110 geothermal=1.4 Choke=24 p_down=180 J=1.8"
    )
    result = format_extraction_confirmation(text)
    assert "البيانات الأساسية مكتملة" in result
    assert "/calc system model=linear" in result
    assert "j=1.8" in result
    assert "لن أرسل هذا الأمر إلى المحرك" in result


def test_does_not_invent_values_from_problem_text():
    result = format_problem_extraction("أشعر أن البئر يعاني من انخفاض في الإنتاج")
    assert "لم أجد قيمة هندسية رقمية واضحة" in result
    assert "لم أستنتج سبب المشكلة" in result
