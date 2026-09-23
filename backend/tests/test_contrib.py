"""Opt-in data contributions: consent gate, landmarks only, list/label/delete."""
import json
import uuid
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.api import routes_contrib, routes_sessions
from app.contrib.hub import HubUploader
from app.contrib.store import BODY_POINTS, ContribError, ContributionStore, LandmarkRecorder
from app.main import app

ANON = str(uuid.uuid4())


def pose(value=0.5):
    return [SimpleNamespace(x=value + i / 100, y=value, z=0.0, visibility=0.9) for i in range(33)]


def recorder_with_frames(anon=ANON, n=5):
    rec = LandmarkRecorder(anon, "phone", "environment", "browser")
    for i in range(n):
        rec.add(pose() if i % 2 == 0 else None, 640, 480, mirror=False, now=i / 15)
    return rec


class FakeApi:
    def __init__(self, fail=0):
        self.calls, self.fail = [], fail

    def _maybe_fail(self):
        if self.fail:
            self.fail -= 1
            raise ConnectionError("offline")

    def upload_folder(self, **kw):
        self._maybe_fail()
        self.calls.append(("upload", kw["path_in_repo"], sorted(p.name for p in __import__("pathlib").Path(kw["folder_path"]).iterdir())))

    def delete_folder(self, **kw):
        self._maybe_fail()
        self.calls.append(("delete", kw["path_in_repo"]))

    def super_squash_history(self, **kw):
        self.calls.append(("squash", kw["repo_id"]))


@pytest.fixture
def store(tmp_path):
    api = FakeApi()
    s = ContributionStore(tmp_path, uploader=HubUploader("me/data", "t", api=api, start_worker=False))
    s.api = api
    routes_contrib.set_store(s)
    yield s
    routes_contrib.set_store(None)


@pytest.fixture
def client(store):
    routes_sessions._sessions.clear()
    with TestClient(app) as c:
        yield c
    routes_sessions._sessions.clear()


def H(anon=ANON):
    return {"X-Contributor-Id": anon}


# ── Store ────────────────────────────────────────────────────
def test_nothing_is_saved_without_consent(store, tmp_path):
    assert store.save(recorder_with_frames(), []) is None
    assert not any(tmp_path.rglob("*.npz"))


def test_consent_requires_an_adult(store):
    with pytest.raises(ContribError):
        store.give_consent(ANON, adult=False)
    assert store.consent(ANON) is None


def test_saved_set_holds_body_landmarks_only(store):
    store.give_consent(ANON, adult=True)
    reps = [{"rep": 1, "form_flags": ["shallow"], "_end_frame": 40, "min_knee_angle": float("nan")}]
    summary = store.save(recorder_with_frames(), reps, app_version="abc123")
    folder = store.root / ANON / summary["set_id"]
    assert sorted(p.name for p in folder.iterdir()) == ["landmarks.npz", "meta.json"]
    data = np.load(folder / "landmarks.npz")
    assert set(data.files) == {"landmarks", "t_ms"}
    assert data["landmarks"].shape == (5, BODY_POINTS, 4) == (5, 22, 4)
    assert data["landmarks"].dtype == np.float16
    # Point 11 (left shoulder) is the first kept point: face points 0-10 are gone.
    assert float(data["landmarks"][0, 0, 0]) == pytest.approx(0.61, abs=1e-3)
    assert np.isnan(data["landmarks"][1]).all()  # frame without a pose
    meta = json.loads((folder / "meta.json").read_text())
    assert meta["movement_mode"] == "squat" and meta["anon_id"] == ANON
    assert meta["landmark_points"][0] == 11 and len(meta["landmark_points"]) == 22
    assert meta["frames"] == 5 and meta["frames_with_pose"] == 3
    assert meta["device_class"] == "phone" and meta["camera_facing"] == "environment"
    assert meta["engine_label"]["total_reps"] == 1 and meta["engine_label"]["flagged_reps"] == 1
    rep = meta["engine_label"]["reps"][0]
    assert "_end_frame" not in rep and rep["min_knee_angle"] is None
    def keys(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                yield k.lower()
                yield from keys(v)
        elif isinstance(obj, list):
            for v in obj:
                yield from keys(v)
    for key in keys(meta):
        for banned in ("name", "user_id", "face", "image", "frame_jpeg", "ip", "agent", "email"):
            assert banned not in key.split("_") and banned != key


def test_a_set_without_any_pose_is_not_kept(store):
    store.give_consent(ANON, adult=True)
    rec = LandmarkRecorder(ANON)
    rec.add(None, 640, 480)
    assert store.save(rec, []) is None


def test_bad_ids_are_rejected(store):
    for bad in ("../etc", "not-a-uuid", ""):
        with pytest.raises(ContribError):
            store.list(bad)
    store.give_consent(ANON, adult=True)
    with pytest.raises(ContribError):
        store.delete(ANON, "../../x")


def test_upload_and_delete_reach_the_hub_with_history_squash(store):
    store.give_consent(ANON, adult=True)
    summary = store.save(recorder_with_frames(), [])
    store.uploader.run_pending()
    path = f"{ANON}/{summary['set_id']}"
    assert store.api.calls == [("upload", path, ["landmarks.npz", "meta.json"])]
    store.delete(ANON, summary["set_id"])
    store.uploader.run_pending()
    assert store.api.calls[1:] == [("delete", path), ("squash", "me/data")]


def test_failed_upload_is_retried(tmp_path):
    api = FakeApi(fail=1)
    up = HubUploader("me/data", "t", api=api, start_worker=False)
    s = ContributionStore(tmp_path, uploader=up)
    s.give_consent(ANON, adult=True)
    s.save(recorder_with_frames(), [])
    up.run_pending()
    assert api.calls == [] and len(up.failed) == 1
    assert up.retry_failed() == 1
    up.run_pending()
    assert api.calls and api.calls[0][0] == "upload" and up.failed == []


# ── API ──────────────────────────────────────────────────────
def test_consent_api_and_withdraw(client, store):
    assert client.get("/api/contrib/consent", headers=H()).json()["consented"] is False
    assert client.post("/api/contrib/consent", json={"adult": False}, headers=H()).status_code == 400
    assert client.post("/api/contrib/consent", json={"adult": True}, headers=H()).json()["consented"]
    store.save(recorder_with_frames(), [])
    assert len(client.get("/api/contrib", headers=H()).json()["sets"]) == 1
    out = client.delete("/api/contrib", headers=H()).json()
    assert out == {"deleted_sets": 1, "consented": False}
    assert client.get("/api/contrib/consent", headers=H()).json()["consented"] is False


def test_missing_or_bad_contributor_id_is_400(client):
    assert client.get("/api/contrib").status_code == 400
    assert client.get("/api/contrib", headers=H("nope")).status_code == 400


def test_label_and_delete_one_set(client, store):
    store.give_consent(ANON, adult=True)
    set_id = store.save(recorder_with_frames(), [])["set_id"]
    r = client.patch(f"/api/contrib/{set_id}/label", json={"feel": "hurt", "counting_right": False}, headers=H())
    assert r.status_code == 200 and r.json()["self_label"]["feel"] == "hurt"
    assert client.patch(f"/api/contrib/{set_id}/label", json={"feel": "great"}, headers=H()).status_code == 422
    other = str(uuid.uuid4())
    assert client.delete(f"/api/contrib/{set_id}", headers=H(other)).status_code == 404
    assert client.delete(f"/api/contrib/{set_id}", headers=H()).json() == {"deleted": set_id}
    assert client.get("/api/contrib", headers=H()).json()["sets"] == []


# ── Session wiring ───────────────────────────────────────────
class FakeManager:
    def __init__(self, **_):
        self.engine = SimpleNamespace(live_squat=SimpleNamespace(
            counter=SimpleNamespace(machine=SimpleNamespace(reps=[{"rep": 1, "form_flags": []}]))))

    def start(self, camera_id=0):
        pass

    def has_viewer(self):
        return True

    def get_session_report(self):
        return {}

    def stop(self):
        pass


def start(client, monkeypatch, **body):
    monkeypatch.setattr(routes_sessions, "SessionManager", FakeManager)
    out = client.post("/api/sessions/start", json={"camera_id": "browser", **body}).json()
    manager = routes_sessions._sessions[out["session_id"]]
    assert out["contributing"] is (manager.contrib_recorder is not None)
    return out["session_id"], manager


def test_session_without_consent_does_not_record(client, monkeypatch):
    sid, manager = start(client, monkeypatch, contributor_id=ANON)
    assert manager.contrib_recorder is None
    assert client.post(f"/api/sessions/{sid}/stop").json() == {"status": "stopped", "contribution": None}


def test_consented_session_saves_a_set_on_stop(client, store, monkeypatch):
    store.give_consent(ANON, adult=True)
    sid, manager = start(client, monkeypatch, contributor_id=ANON, device_class="phone", camera_facing="environment")
    rec = manager.contrib_recorder
    assert rec is not None and rec.camera_source == "browser"
    for i in range(3):
        rec.add(pose(), 640, 480, now=i / 15)
    out = client.post(f"/api/sessions/{sid}/stop").json()
    assert out["contribution"]["total_reps"] == 1
    assert [s["set_id"] for s in store.list(ANON)] == [out["contribution"]["set_id"]]
