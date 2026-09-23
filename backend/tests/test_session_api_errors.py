"""Session start/stop edge cases through the HTTP API."""
import pytest
from fastapi.testclient import TestClient

from app.api import routes_sessions
from app.main import app


class FakeManager:
    viewer = True

    def __init__(self, fail_start=None, **_):
        self.fail_start = fail_start
        self.stopped = False
        self.engine = None

    def start(self, camera_id=0):
        if self.fail_start:
            raise self.fail_start

    def has_viewer(self):
        return self.viewer

    def stop(self):
        self.stopped = True

    def stop_quietly(self):
        self.stopped = True

    def get_session_report(self):
        raise ValueError("boom")


@pytest.fixture
def client(monkeypatch):
    routes_sessions._sessions.clear()
    with TestClient(app) as c:  # runs startup, which creates the tables
        yield c
    routes_sessions._sessions.clear()


def test_camera_error_detail_reaches_the_client(client, monkeypatch):
    from app.core.session_manager import CameraError

    monkeypatch.setattr(routes_sessions, "SessionManager",
                        lambda **k: FakeManager(fail_start=CameraError("Couldn't open camera 0. Check it")))
    r = client.post("/api/sessions/start", json={"camera_id": 0})
    assert r.status_code == 400
    assert r.json()["detail"].startswith("Couldn't open camera 0")
    assert routes_sessions._sessions == {}


def test_second_session_is_refused_while_one_runs(client, monkeypatch):
    monkeypatch.setattr(routes_sessions, "SessionManager", lambda **k: FakeManager())
    assert client.post("/api/sessions/start", json={}).status_code in (200, 201)
    r = client.post("/api/sessions/start", json={})
    assert r.status_code == 409 and "already running" in r.json()["detail"]


def test_unwatched_session_is_saved_and_replaced(client, monkeypatch):
    """Closed tab / refreshed page / finished video must not lock the camera."""
    managers = []

    def make(**k):
        managers.append(FakeManager())
        managers[-1].viewer = False
        return managers[-1]

    monkeypatch.setattr(routes_sessions, "SessionManager", make)
    first = client.post("/api/sessions/start", json={}).json()["session_id"]
    routes_sessions._sessions[first].started_monotonic -= 60  # past the grace period
    second = client.post("/api/sessions/start", json={})
    assert second.status_code in (200, 201)
    assert managers[0].stopped and first not in routes_sessions._sessions
    history = client.get(f"/api/sessions/history/{first}")
    assert history.status_code == 200  # only returned once ended_at is set


def test_stop_frees_the_session_even_if_the_report_fails(client, monkeypatch):
    monkeypatch.setattr(routes_sessions, "SessionManager", lambda **k: FakeManager())
    sid = client.post("/api/sessions/start", json={}).json()["session_id"]
    client.post(f"/api/sessions/{sid}/stop")
    assert routes_sessions._sessions == {}
    assert client.post("/api/sessions/start", json={}).status_code in (200, 201)
