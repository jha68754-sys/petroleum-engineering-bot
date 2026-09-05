from services.problem_extraction import extract_engineering_fields, format_problem_extraction


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


def test_does_not_invent_values_from_problem_text():
    result = format_problem_extraction("أشعر أن البئر يعاني من انخفاض في الإنتاج")
    assert "لم أجد قيمة هندسية رقمية واضحة" in result
    assert "لم أستنتج سبب المشكلة" in result
