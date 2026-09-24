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


def test_movement_modes_list_squat_selectable_and_pushup_pending():
    modes = {m["id"]: m for m in client.get("/api/settings/movement-modes").json()["modes"]}
    assert modes["squat"]["selectable"] is True and modes["squat"]["validated"] is True
    assert modes["pushup"]["validated"] is False
    assert modes["pushup"]["selectable"] is False
    assert "recorded" in modes["pushup"]["note"]


def test_default_movement_mode_is_squat_and_pushup_cannot_be_picked_yet():
    assert client.get("/api/settings").json()["movement_mode"] == "squat"
    resp = client.patch("/api/settings", json={"movement_mode": "pushup"})
    assert resp.status_code == 422
    assert client.patch("/api/settings", json={"movement_mode": "lunge"}).status_code == 422
    assert client.get("/api/settings").json()["movement_mode"] == "squat"


def test_preview_env_unlocks_pushup_for_development(monkeypatch):
    monkeypatch.setenv("LIFTGUARD_PREVIEW_MODES", "pushup")
    modes = {m["id"]: m for m in client.get("/api/settings/movement-modes").json()["modes"]}
    assert modes["pushup"]["selectable"] is True
    resp = client.patch("/api/settings", json={"movement_mode": "pushup"})
    assert resp.status_code == 200 and resp.json()["movement_mode"] == "pushup"
    assert client.patch("/api/settings", json={"movement_mode": "squat"}).json()["movement_mode"] == "squat"


def test_session_start_rejects_a_mode_that_cannot_be_picked():
    resp = client.post("/api/sessions/start", json={"movement_mode": "pushup"})
    assert resp.status_code == 400
    assert "can't be picked" in resp.json()["detail"]


def test_session_summary_and_fatigue_follow_the_movement_mode():
    from types import SimpleNamespace

    from app.core.session_manager import live_exercise_summary, live_fatigue_indicator

    reps = [{"duration_seconds": 1.0, "rom_degrees": 90.0, "min_elbow_angle": 80.0, "form_flags": []}] * 3
    reps += [{"duration_seconds": 1.5, "rom_degrees": 60.0, "min_elbow_angle": 100.0, "form_flags": ["SHALLOW_PUSHUP"]}] * 3
    feed = SimpleNamespace(mode="pushup", counter=SimpleNamespace(machine=SimpleNamespace(reps=reps)))
    engine = SimpleNamespace(live_squat=feed, current_exercise_status={"rep_gates": {"rejected_not_plank": 2}})
    summary = live_exercise_summary(engine)
    assert summary["exercise"] == "Push-up" and summary["movement_mode"] == "pushup"
    assert summary["avg_deepest_elbow_angle_deg"] == 90.0 and "avg_deepest_knee_angle_deg" not in summary
    assert summary["reps_with_form_flags"] == 3 and summary["rejected_candidates"] == 2
    fatigue = live_fatigue_indicator(engine)
    assert fatigue["status"] in {"WATCH", "ELEVATED"}
    assert fatigue["signals"]["trunk_lean_drift_degrees"] is None


def test_auto_detect_is_off_by_default_and_can_be_toggled():
    assert client.get("/api/settings").json()["auto_detect"] is False
    on = client.patch("/api/settings", json={"auto_detect": True})
    assert on.status_code == 200 and on.json()["auto_detect"] is True
    off = client.patch("/api/settings", json={"auto_detect": False})
    assert off.json()["auto_detect"] is False


def test_auto_detect_availability_follows_the_local_model_file(monkeypatch, tmp_path):
    monkeypatch.delenv("LIFTGUARD_RECOGNIZER_MODEL", raising=False)
    info = client.get("/api/settings/auto-detect").json()
    assert info["available"] is False and "not set" in info["reason"]
    monkeypatch.setenv("LIFTGUARD_RECOGNIZER_MODEL", str(tmp_path / "missing.npz"))
    assert client.get("/api/settings/auto-detect").json()["available"] is False
    model = tmp_path / "m.npz"
    model.write_bytes(b"x")
    monkeypatch.setenv("LIFTGUARD_RECOGNIZER_MODEL", str(model))
    assert client.get("/api/settings/auto-detect").json() == {"available": True, "reason": None}
