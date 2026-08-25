import json
from pathlib import Path
from unittest.mock import Mock

import constants
from config import MAX_UPLOAD_SIZE
from handlers.file_handlers import handle_document_upload, handle_photo_upload
from services.ai_service import AIService


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
