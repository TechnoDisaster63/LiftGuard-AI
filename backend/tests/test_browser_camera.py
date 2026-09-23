"""The viewer's browser camera as a live analysis source."""
import base64
import threading
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api import routes_sessions, ws_live
from app.core.browser_camera import MAX_FRAME_BYTES, BrowserFrameSource
from app.core.session_manager import SessionManager, camera_source
from app.main import app


def fake_decode(jpeg):
    return SimpleNamespace(size=len(jpeg), payload=jpeg)


def test_read_returns_only_the_newest_frame_once():
    src = BrowserFrameSource(wait_seconds=0.01, decode=fake_decode)
    assert src.read() == (False, None)  # nothing sent yet
    assert src.push(b"one") and src.push(b"two")
    ok, frame = src.read()
    assert ok and frame.payload == b"two"  # stale frame dropped, not queued
    assert src.read() == (False, None)  # the same frame is never analysed twice


def test_read_wakes_as_soon_as_a_frame_arrives():
    src = BrowserFrameSource(wait_seconds=2.0, decode=fake_decode)
    threading.Timer(0.05, src.push, args=(b"late",)).start()
    t0 = time.monotonic()
    ok, frame = src.read()
    assert ok and frame.payload == b"late"
    assert time.monotonic() - t0 < 1.0


def test_oversized_empty_and_post_release_frames_are_rejected():
    src = BrowserFrameSource(wait_seconds=0.01, decode=fake_decode)
    assert not src.push(b"")
    assert not src.push(b"x" * (MAX_FRAME_BYTES + 1))
    src.release()
    assert not src.isOpened()
    assert not src.push(b"after")
    assert src.read() == (False, None)


def test_real_jpeg_decodes_to_a_frame():
    cv2 = pytest.importorskip("cv2")
    import numpy as np

    ok, buf = cv2.imencode(".jpg", np.full((36, 64, 3), 128, np.uint8))
    src = BrowserFrameSource(wait_seconds=0.01)
    src.push(buf.tobytes())
    ok, frame = src.read()
    assert ok and frame.shape == (36, 64, 3)


def test_browser_choice_beats_the_server_clip_override(monkeypatch):
    monkeypatch.setenv("LIFTGUARD_CAMERA_SOURCE", "/tmp/squat.webm")
    assert camera_source("browser") == "browser"
    assert camera_source(0) == "/tmp/squat.webm"  # the clip stays the default


def test_session_start_with_browser_opens_no_device(monkeypatch):
    import app.core.session_manager as sm

    monkeypatch.setattr(sm, "open_camera", lambda *a, **k: pytest.fail("opened a server camera"))
    calls = {}

    class FakeUserManager:
        def identify_from_camera(self, cap, **kwargs):
            calls.update(kwargs)
            return SimpleNamespace(is_guest=True, baseline=None)

    fps = []
    manager = SessionManager.__new__(SessionManager)
    manager.engine = SimpleNamespace(user_manager=FakeUserManager(), session_active=False,
                                     configure_live_squat=lambda f, mode="squat": fps.append(f))
    manager.start(camera_id="browser")
    assert manager.active and manager.uses_browser_camera()
    assert fps == [None]  # the engine measures the real rate
    assert calls["timeout"] == 0.0  # no frames yet: start as Guest without waiting
    assert manager.push_browser_frame(b"jpeg")
    assert manager.cap.frames_received == 1


class FakeLiveManager:
    """Stands in for SessionManager behind /ws/live."""

    def __init__(self):
        self.src = BrowserFrameSource(wait_seconds=0.05, decode=fake_decode)
        self.active = True
        self.camera_id = "browser"
        self.controls = []
        self._lock = threading.Lock()

    def acquire_stream(self):
        return self._lock.acquire(blocking=False)

    def release_stream(self):
        if self._lock.locked():
            self._lock.release()

    def has_viewer(self):
        return self._lock.locked()

    def uses_browser_camera(self):
        return True

    def push_browser_frame(self, jpeg):
        return self.src.push(jpeg)

    def handle_control(self, action):
        self.controls.append(action)
        return "ok"

    def step(self):
        ok, frame = self.src.read()
        if not ok:
            return None, None
        return b"analysed:" + frame.payload, {"camera_id": "browser"}


def test_frames_sent_over_the_socket_are_analysed_and_returned(monkeypatch):
    fake = FakeLiveManager()
    monkeypatch.setattr(ws_live, "get_session_manager", lambda sid: fake)
    with TestClient(app) as client, client.websocket_connect("/ws/live/s1") as ws:
        ws.send_json({"type": "frame", "data": base64.b64encode(b"hello").decode()})
        msg = ws.receive_json()
        assert msg["type"] == "frame"
        assert base64.b64decode(msg["data"]) == b"analysed:hello"
        assert ws.receive_json()["type"] == "telemetry"
        # Controls still work on the same socket, and frames are not controls.
        ws.send_json({"type": "frame", "data": "not base64!!"})
        ws.send_json({"action": "reset_reps"})
        assert ws.receive_json() == {"type": "control_ack", "action": "reset_reps", "message": "ok"}
        fake.active = False
    assert fake.controls == ["reset_reps"]


def test_start_api_accepts_browser_and_records_it(monkeypatch):
    started = {}

    class FakeManager:
        engine = None

        def __init__(self, **_):
            pass

        def start(self, camera_id=0):
            started["camera_id"] = camera_id

        def has_viewer(self):
            return True

        def stop_quietly(self):
            pass

    routes_sessions._sessions.clear()
    monkeypatch.setattr(routes_sessions, "SessionManager", FakeManager)
    with TestClient(app) as client:
        r = client.post("/api/sessions/start", json={"camera_id": "browser"})
        assert r.status_code == 200, r.text
        assert started["camera_id"] == "browser"
        assert client.post("/api/sessions/start", json={"camera_id": "phone"}).status_code == 422
    routes_sessions._sessions.clear()
