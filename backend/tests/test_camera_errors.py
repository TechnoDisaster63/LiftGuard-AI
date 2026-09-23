"""Camera problems must come back as readable messages, not crashes or hangs."""
import pytest

cv2 = pytest.importorskip("cv2")
import numpy as np  # noqa: E402

from app.core import session_manager as sm  # noqa: E402


class Cap:
    def __init__(self, opened=True, frames=True):
        self.opened, self.frames, self.released = opened, frames, False

    def isOpened(self):
        return self.opened

    def set(self, *_):
        return True

    def get(self, *_):
        return 25.0

    def read(self):
        if self.frames:
            return True, np.zeros((8, 8, 3), np.uint8)
        return False, None

    def release(self):
        self.released = True


def test_missing_camera_gives_readable_error(monkeypatch):
    monkeypatch.setattr(cv2, "VideoCapture", lambda *a: Cap(opened=False))
    with pytest.raises(sm.CameraError, match="Couldn't open camera 3"):
        sm.open_camera(3)


def test_busy_camera_is_reported_as_busy(monkeypatch):
    cap = Cap(frames=False)
    monkeypatch.setattr(cv2, "VideoCapture", lambda *a: cap)
    with pytest.raises(sm.CameraError, match="isn't sending any video"):
        sm.open_camera(0, warmup_seconds=0.2)
    assert cap.released


def test_camera_error_is_a_runtime_error_so_the_api_returns_400():
    assert issubclass(sm.CameraError, RuntimeError)


def test_env_override_selects_a_video_source(monkeypatch):
    monkeypatch.setenv("LIFTGUARD_CAMERA_SOURCE", "/tmp/clip.mp4")
    assert sm.camera_source(0) == "/tmp/clip.mp4"
    monkeypatch.delenv("LIFTGUARD_CAMERA_SOURCE")
    assert sm.camera_source(1) == 1


def test_failed_camera_switch_keeps_the_current_camera(monkeypatch):
    from types import SimpleNamespace

    manager = sm.SessionManager.__new__(sm.SessionManager)
    current = Cap()
    manager.cap, manager.camera_id = current, 0
    manager.engine = SimpleNamespace(current_camera_id=0)
    monkeypatch.setattr(cv2, "VideoCapture", lambda *a: Cap(opened=False))
    message = manager._switch_camera(2)
    assert message.startswith("Kept the current camera")
    assert manager.cap is current and not current.released


def test_successful_camera_switch_releases_the_old_one(monkeypatch):
    from types import SimpleNamespace

    manager = sm.SessionManager.__new__(sm.SessionManager)
    old = Cap()
    manager.cap, manager.camera_id = old, 0
    manager.engine = SimpleNamespace(current_camera_id=0)
    new = Cap()
    monkeypatch.setattr(cv2, "VideoCapture", lambda *a: new)
    assert manager._switch_camera(1) == "Switched to camera 1"
    assert manager.cap is new and old.released and manager.engine.current_camera_id == 1
