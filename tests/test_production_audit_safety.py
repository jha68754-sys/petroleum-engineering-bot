import json
from pathlib import Path
from unittest.mock import Mock

import constants
from config import MAX_UPLOAD_SIZE
from handlers.file_handlers import handle_document_upload, handle_photo_upload
from services.ai_service import AIService
from services.engineering_case import build_case
from services.engineering_context import EngineeringValueOrigin, input_origins_for_case
from services.engineering_report import generate_report_arabic_v1, generate_report_v1


DATASET = Path(__file__).resolve().parents[1] / "data" / "petroleum_knowledge_v1.json"


def test_ai_and_legacy_prompt_adapter_use_the_same_knowledge_v1_records():
    records = json.loads(DATASET.read_text(encoding="utf-8"))["records"]
    assert len(constants.KNOWLEDGE_BASE) == len(records)
    assert [entry["en"] for entry in constants.KNOWLEDGE_BASE] == [
        f"{record['canonical_english_name']} ({record['symbol']})" for record in records
    ]
    context = AIService._build_engineering_context()
    assert "Flowing Bottomhole Pressure (Pwf)" in context
    assert "ضغط قاع البئر أثناء الجريان" in context


class _FakeTelegram:
    def __init__(self, payload: bytes, path: str = "file.bin"):
        self.payload = payload
        self.path = path

    def get_file_path(self, file_id):
        return self.path

    def download_file(self, path):
        return self.payload


def test_document_downloaded_bytes_are_capped_even_if_metadata_is_small():
    payload = b"x" * (MAX_UPLOAD_SIZE + 1)
    message = {
        "chat": {"id": 1},
        "document": {
            "file_id": "file-id",
            "file_name": "input.csv",
            "file_size": 1,
        },
    }
    status, error = handle_document_upload(message, _FakeTelegram(payload), {})
    assert error == "File too large"
    assert "Downloaded file too large" in status


def test_photo_downloaded_bytes_are_capped_even_if_metadata_is_small():
    payload = b"x" * (MAX_UPLOAD_SIZE + 1)
    message = {
        "chat": {"id": 1},
        "photo": [{"file_id": "photo-id", "file_size": 1}],
    }
    status, error = handle_photo_upload(message, _FakeTelegram(payload, "photo.png"), {})
    assert error == "File too large"
    assert "Downloaded photo too large" in status


def test_save_offset_writes_atomically_and_leaves_no_temp_file(tmp_path, monkeypatch):
    import main

    offset_path = tmp_path / "nested" / "offset_state.json"
    monkeypatch.setattr(main, "OFFSET_STATE_FILE", offset_path)
    main.save_offset(42)
    assert main.load_offset() == 42
    assert list(offset_path.parent.glob(".offset_state.json.*.tmp")) == []
    assert list(offset_path.parent.glob("*.tmp")) == []


def test_load_offset_returns_zero_for_invalid_payload(tmp_path, monkeypatch):
    import main

    offset_path = tmp_path / "offset_state.json"
    monkeypatch.setattr(main, "OFFSET_STATE_FILE", offset_path)
    offset_path.write_text("{invalid", encoding="utf-8")
    assert main.load_offset() == 0
    offset_path.write_text('{"current_offset": -1}', encoding="utf-8")
    assert main.load_offset() == 0
    offset_path.write_text('{"current_offset": "42"}', encoding="utf-8")
    assert main.load_offset() == 0


def test_save_offset_rejects_invalid_value_without_overwriting_valid_state(tmp_path, monkeypatch):
    import main

    offset_path = tmp_path / "offset_state.json"
    monkeypatch.setattr(main, "OFFSET_STATE_FILE", offset_path)
    main.save_offset(42)
    main.save_offset(-1)
    main.save_offset("43")
    assert main.load_offset() == 42


def test_case_input_origins_are_deterministic_and_visible_in_reports():
    case = build_case(
        calculation_type="integrated_system_v1",
        request={
            "calculation": "system",
            "arguments": {"pr": "3000", "model": "linear", "j": "1.5"},
        },
        inputs={
            "pr": 3000.0,
            "thp": 100.0,
            "ipr_model": "linear",
            "vlp_model": "beggs_brill",
            "j": 1.5,
            "custom_value": 7.0,
        },
        units={"pressure": "psia"},
    )
    origins = input_origins_for_case(case)
    assert origins["pr"] is EngineeringValueOrigin.USER_PROVIDED
    assert origins["thp"] is EngineeringValueOrigin.DEFAULTED
    assert origins["ipr_model"] is EngineeringValueOrigin.USER_PROVIDED
    assert origins["vlp_model"] is EngineeringValueOrigin.DEFAULTED
    assert origins["custom_value"] is EngineeringValueOrigin.UNKNOWN

    english = generate_report_v1(case)
    arabic = generate_report_arabic_v1(case)
    assert "Input origin labels:" in english
    assert "Reservoir pressure: 3,000 psia [origin: USER_PROVIDED]" in english
    assert "Tubing-head pressure (THP): 100 psia [origin: DEFAULTED]" in english
    assert "مصدر المدخلات:" in arabic
    assert "ضغط المكمن (Pr): 3,000 psia [origin: USER_PROVIDED]" in arabic
    assert "ضغط رأس البئر (THP): 100 psia [origin: DEFAULTED]" in arabic


def test_context_override_marks_inherited_inputs_as_derived_in_reports():
    case = build_case(
        calculation_type="integrated_system_v1",
        request={
            "calculation": "system",
            "arguments": {"thp": 200},
            "context_override": "thp",
        },
        inputs={"pr": 3000.0, "thp": 200.0, "choke_size_64th_in": 32.0},
        units={"pressure": "psia"},
    )
    origins = input_origins_for_case(case)
    assert origins["thp"] is EngineeringValueOrigin.USER_PROVIDED
    assert origins["pr"] is EngineeringValueOrigin.DERIVED
    report = generate_report_arabic_v1(case)
    assert "ضغط المكمن (Pr): 3,000 psia [origin: DERIVED]" in report
    assert "ضغط رأس البئر (THP): 200 psia [origin: USER_PROVIDED]" in report


def test_replacing_photo_removes_the_previous_temp_file(tmp_path, monkeypatch):
    previous = tmp_path / "previous.png"
    previous.write_bytes(b"old")
    current = tmp_path / "current.png"
    current.write_bytes(b"new")
    image_context = {7: str(previous)}
    monkeypatch.setattr(
        "handlers.file_handlers.save_uploaded_file",
        lambda payload, filename: str(current),
    )
    message = {
        "chat": {"id": 7},
        "photo": [{"file_id": "photo-id", "file_size": 3}],
    }
    status, error = handle_photo_upload(message, _FakeTelegram(b"new", "photo.png"), image_context)
    assert error is None
    assert "Photo received" in status
    assert image_context[7] == str(current)
    assert not previous.exists()
    assert current.exists()



def _portable_case():
    return build_case(
        calculation_type="integrated_system_v1",
        request={
            "calculation": "system",
            "arguments": {"pr": "3000", "thp": "100", "j": "1.5"},
            "telegram_chat_id": "12345",
            "bot_token": "bot1234567890:SECRET",
        },
        inputs={
            "pr": 3000.0,
            "thp": 100.0,
            "ipr_model": "linear",
            "j": 1.5,
            "choke_size_64th_in": 16.0,
        },
        units={"pr": "psia", "thp": "psia", "j": "STB/day/psi"},
        model={"engine": "IntegratedSystemEngine"},
        selectors={"ipr_model": "linear", "vlp_model": "beggs_brill"},
        pvt={"mode": "conventional", "provider": "released inputs"},
        result={"operating_rate_bpd": 711.22, "pwf_psia": 2525.83},
    )


def test_quality_gate_rejects_obvious_system_input_before_engine():
    from handlers import text_handlers as th

    command = (
        "/calc system model=linear pr=-1 j=1.5 tvd=8000 id=1.995 "
        "gor=1000 rs=600 api=35 gamma_g=0.65 mu_l=1 bo=1.4 "
        "t_wh=120 geothermal=1.5 choke=16 p_down=200"
    )
    text, png, filename = th.handle_calc({"text": command}, None)
    assert png is None
    assert filename is None
    assert "Engineering Data Quality Gate" in text
    assert "Reservoir pressure" in text
    assert "q_op" not in text


def test_quality_gate_preserves_valid_system_engine_path():
    from handlers import text_handlers as th

    command = (
        "/calc system model=linear pr=3000 j=1.5 tvd=8000 id=1.995 "
        "gor=1000 rs=600 api=35 gamma_g=0.65 mu_l=1 bo=1.4 "
        "t_wh=120 geothermal=1.5 choke=16 p_down=200"
    )
    text, png, filename = th.handle_calc({"text": command}, None)
    assert png is None
    assert filename is None
    assert "Status: OK" in text
    assert "q_op =" in text


def test_guided_workflow_requests_explicit_thp_without_inference():
    from handlers.text_handlers import handle_engineering_workflow_message

    arabic = handle_engineering_workflow_message(
        {"chat": {"id": 991001}, "text": "احسب الإنتاج"}
    )
    english = handle_engineering_workflow_message(
        {"chat": {"id": 991002}, "text": "calculate production"}
    )
    assert arabic is not None
    assert "THP" in arabic
    assert "THP=200 psia" in arabic
    assert "لم أستخدم قيمة افتراضية" in arabic
    assert english is not None
    assert "THP=200 psia" in english
    assert "No default or inferred value" in english


def test_portable_snapshot_is_secret_free_and_contains_traceability():
    from services.case_snapshot import build_case_snapshot

    snapshot = build_case_snapshot(_portable_case()).decode("utf-8")
    assert "Portable Engineering Case Snapshot V1" in snapshot
    assert _portable_case().case_id in snapshot
    assert "integrated_system_v1" in snapshot
    assert "USER_PROVIDED" in snapshot
    assert "Engineering Case Report V1" in snapshot
    assert "bot1234567890:SECRET" not in snapshot
    assert "telegram_chat_id" not in snapshot
    assert "ghp_" not in snapshot


def test_case_snapshot_handler_returns_markdown_document():
    from handlers import text_handlers as th

    case = _portable_case()
    th._ENGINEERING_CASES[case.case_id] = case
    text, content, filename = th.handle_case_command(
        {"chat": {"id": 991003}, "text": f"/case snapshot {case.case_id}"},
        None,
    )
    assert "Portable Case Snapshot V1" in text
    assert content is not None and content.startswith(b"# Portable Engineering Case Snapshot V1")
    assert filename == f"engineering_case_{case.case_id[:16]}_snapshot.md"


def test_process_message_sends_snapshot_as_document_not_photo(monkeypatch):
    import main
    from handlers import text_handlers as th

    case = _portable_case()
    th._ENGINEERING_CASES[case.case_id] = case

    class FakeTelegram:
        def __init__(self):
            self.messages = []
            self.documents = []
            self.photos = []

        def send_message(self, chat_id, text, reply_to_message_id=None):
            self.messages.append((chat_id, text, reply_to_message_id))

        def send_document(self, chat_id, content, filename, caption=None, reply_to_message_id=None):
            self.documents.append((chat_id, content, filename, caption, reply_to_message_id))

        def send_photo_bytes(self, *args, **kwargs):
            self.photos.append((args, kwargs))
            raise AssertionError("Portable snapshot must not be sent as a photo")

    telegram = FakeTelegram()
    main.process_message(
        {
            "chat": {"id": 991004},
            "message_id": 44,
            "text": f"/case snapshot {case.case_id}",
        },
        telegram,
        object(),
    )
    assert len(telegram.documents) == 1
    assert telegram.documents[0][2].endswith("_snapshot.md")
    assert telegram.documents[0][1].startswith(b"# Portable Engineering Case Snapshot V1")
    assert not telegram.photos
