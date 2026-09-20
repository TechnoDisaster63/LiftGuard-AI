import json

from app.core.settings_store import SessionDefaultsStore


def test_store_recovers_from_corrupt_json(tmp_path):
    path = tmp_path / "session_defaults.json"
    path.write_text("{not-json", encoding="utf-8")

    store = SessionDefaultsStore(path)

    assert store.get()["camera_id"] == 0
    assert path.with_suffix(".json.corrupt").read_text(encoding="utf-8") == "{not-json"


def test_store_writes_valid_json_without_leaving_temporary_file(tmp_path):
    path = tmp_path / "session_defaults.json"
    store = SessionDefaultsStore(path)

    result = store.update({"camera_id": 2, "unknown": "ignored"})

    assert result["camera_id"] == 2
    assert json.loads(path.read_text(encoding="utf-8"))["camera_id"] == 2
    assert not path.with_suffix(".json.tmp").exists()
