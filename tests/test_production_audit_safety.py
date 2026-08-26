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
