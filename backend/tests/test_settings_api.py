from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_get_settings_defaults():
    resp = client.get("/api/settings")
    assert resp.status_code == 200
    body = resp.json()
    assert "voice_enabled" in body
    assert "camera_id" in body


def test_patch_settings_roundtrip():
    original = client.get("/api/settings").json()
    patched = client.patch("/api/settings", json={"voice_enabled": False})
    assert patched.status_code == 200
    assert patched.json()["voice_enabled"] is False
    # restore
    client.patch("/api/settings", json={"voice_enabled": original["voice_enabled"]})
