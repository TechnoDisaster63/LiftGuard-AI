"""Session start must never block on console input or open OpenCV windows."""
import builtins
from types import SimpleNamespace

import pytest

cv2 = pytest.importorskip("cv2")
import numpy as np  # noqa: E402

from app.identity import user_manager_lite as um  # noqa: E402


@pytest.fixture
def no_ui(monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("interactive UI called during a headless session start")

    monkeypatch.setattr(builtins, "input", forbidden)
    monkeypatch.setattr(cv2, "imshow", forbidden)
    monkeypatch.setattr(cv2, "waitKey", forbidden)


def bare_manager(users, trained=True):
    manager = um.UserManager.__new__(um.UserManager)
    manager.get_all_users = lambda: users
    manager.matcher = SimpleNamespace(is_trained=trained)
    manager.current_user = um.UserProfile.guest()
    manager.CONFIRM_FRAMES = 20
    return manager


class FakeCap:
    def __init__(self, frames=5):
        self.frames = frames

    def read(self):
        if self.frames <= 0:
            return False, None
        self.frames -= 1
        return True, np.zeros((48, 64, 3), np.uint8)


def test_no_enrolled_users_starts_as_guest_without_input(no_ui):
    manager = bare_manager(users=[])
    profile = manager.identify_from_camera(FakeCap(), timeout=1.0, allow_new_user=True, interactive=False)
    assert profile.is_guest


def test_unrecognized_face_starts_as_guest_and_never_enrolls(no_ui, monkeypatch):
    manager = bare_manager(users=[object()])
    monkeypatch.setattr(um, "FACE_DETECTOR_OK", True)
    manager.identify_from_frame = lambda frame: (None, [], 1.0)
    manager._enroll_new_user = lambda *a, **k: pytest.fail("enrollment attempted headless")
    profile = manager.identify_from_camera(FakeCap(frames=30), timeout=5.0, interactive=False)
    assert profile.is_guest


def test_enrolled_user_is_recognized_headless(no_ui, monkeypatch):
    athlete = um.UserProfile(7, "techno", "Techno")
    manager = bare_manager(users=[athlete])
    monkeypatch.setattr(um, "FACE_DETECTOR_OK", True)
    calls = iter([None, None, athlete])
    manager.identify_from_frame = lambda frame: (next(calls), [], 0.3)
    profile = manager.identify_from_camera(FakeCap(frames=10), timeout=5.0, interactive=False)
    assert profile is athlete and manager.current_user is athlete


def test_session_manager_start_is_headless(monkeypatch):
    from app.core.session_manager import SessionManager

    calls = {}

    class FakeUserManager:
        def identify_from_camera(self, cap, **kwargs):
            calls.update(kwargs)
            return um.UserProfile.guest()

    class OpenCap:
        def isOpened(self):
            return True

        def set(self, *_):
            return True

        def get(self, *_):
            return 25.0

        def read(self):
            return True, np.zeros((48, 64, 3), np.uint8)

        def release(self):
            pass

    monkeypatch.setattr(cv2, "VideoCapture", lambda *_: OpenCap())
    manager = SessionManager.__new__(SessionManager)
    manager.engine = SimpleNamespace(user_manager=FakeUserManager(), session_active=False,
                                     configure_live_squat=lambda fps, mode="squat": None)
    manager.start(camera_id=0)
    assert calls["interactive"] is False
    assert calls["allow_new_user"] is False
    assert manager.engine.current_user.is_guest and manager.active

    manager.start(camera_id="clip.mp4")
    assert calls["timeout"] == 0.0  # a video file skips face ID instead of eating clip frames
