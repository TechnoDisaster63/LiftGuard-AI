"""On-device face ID: matching, storage, locality guard and privacy.

The model-free tests use a fake embedder (color of the frame -> vector), so
they run in CI without the YuNet/SFace files. test_real_models_* run only when
the model files are present (python fetch_face_models.py).
"""
import base64
import logging
import sqlite3
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.identity import face_id
from app.identity.locality import is_local_request

cv2 = pytest.importorskip("cv2")


# ── matching ────────────────────────────────────────────────
def _unit(seed, dim=face_id.EMBED_DIM):
    return face_id.normalize(np.random.default_rng(seed).normal(size=dim))


def _near(v, noise, seed):
    return face_id.normalize(v + noise * np.random.default_rng(seed).normal(size=v.size))


def test_best_match_needs_threshold_and_margin():
    a, b = _unit(1), _unit(2)
    gallery = {1: a, 2: b}
    assert face_id.best_match(_near(a, 0.02, 9), gallery)[0] == 1
    assert face_id.best_match(_unit(3), gallery)[0] is None          # stranger
    # halfway between two enrolled users: no guess
    assert face_id.best_match(face_id.normalize(a + b), gallery)[0] is None
    assert face_id.best_match(a, {})[0] is None


def test_enrollment_rejects_too_few_or_mixed_faces():
    a, b = _unit(1), _unit(2)
    mean, err = face_id.enrollment_embedding([a] * 3 + [None] * 5)
    assert mean is None and "3" in err
    mean, err = face_id.enrollment_embedding([_near(a, 0.05, i) for i in range(4)] + [b, b])
    assert mean is None and "same face" in err
    mean, err = face_id.enrollment_embedding([_near(a, 0.05, i) for i in range(6)])
    assert err is None and face_id.cosine(mean, a) > 0.95


def test_identifier_needs_consecutive_frames():
    a = _unit(1)
    ident = face_id.Identifier({7: a}, confirm_frames=3)
    assert ident.observe(a) is None
    assert ident.observe(None) is None      # face lost: start over
    assert ident.observe(a) is None
    assert ident.observe(a) is None
    assert ident.observe(a) == 7


# ── storage ─────────────────────────────────────────────────
def test_gallery_roundtrip_and_forget(tmp_path):
    g = face_id.FaceGallery(tmp_path / "u.db")
    a = _unit(1)
    g.save(5, a, samples=8)
    loaded = g.load()
    assert set(loaded) == {5} and np.allclose(loaded[5], a, atol=1e-6)
    assert g.forget(5) and g.load() == {}


def test_upgrade_deletes_old_face_images(tmp_path):
    from app.identity.user_manager_lite import DB_SCHEMA

    db = tmp_path / "u.db"
    conn = sqlite3.connect(db)
    conn.executescript(DB_SCHEMA)
    marker = b"OLD-FACE-PIXELS-" * 64
    conn.execute("INSERT INTO users (username, display_name, created_at, face_features, profile_photo)"
                 " VALUES ('a','A','now',?,?)", (marker, b"\xff\xd8\xff" + marker))
    conn.commit()
    conn.close()
    assert face_id.purge_stored_face_images(db) == 1
    row = sqlite3.connect(db).execute("SELECT username, face_features, profile_photo FROM users").fetchone()
    assert row == ("a", None, None)                     # account kept, images gone
    assert marker not in Path(db).read_bytes()          # and not left in free pages
    assert face_id.purge_stored_face_images(db) == 0


# ── locality guard ──────────────────────────────────────────
class _Req:
    def __init__(self, host, headers=None):
        self.client = type("C", (), {"host": host})() if host else None
        self.headers = {k.lower(): v for k, v in (headers or {}).items()}


@pytest.mark.parametrize("host,headers,ok", [
    ("127.0.0.1", {"Origin": "http://localhost:3000"}, True),
    ("::1", {}, True),
    # start.sh proxy mode: Next on the same machine forwards to the backend
    ("127.0.0.1", {"X-Forwarded-For": "127.0.0.1", "X-Forwarded-Host": "localhost:3000",
                   "Origin": "http://localhost:3000"}, True),
    ("192.168.1.20", {"Origin": "http://192.168.1.5:3000"}, False),      # phone on the Wi-Fi
    ("127.0.0.1", {"X-Forwarded-For": "203.0.113.9"}, False),            # tunnel / proxy
    ("127.0.0.1", {"Forwarded": "for=203.0.113.9;proto=https"}, False),
    ("127.0.0.1", {"X-Forwarded-Host": "turbo-guide-3000.app.github.dev"}, False),  # Codespace
    ("127.0.0.1", {"Origin": "https://abc.trycloudflare.com"}, False),
    ("127.0.0.1", {"Referer": "https://abc.trycloudflare.com/register"}, False),
    ("testclient", {}, False),
    (None, {}, False),
])
def test_is_local_request(host, headers, ok):
    assert is_local_request(_Req(host, headers)) is ok


# ── API with a fake embedder ────────────────────────────────
class FakeEmbedder:
    """Frame color -> embedding. Black frames have no face."""

    def embed(self, frame):
        mean = frame.reshape(-1, 3).mean(axis=0)
        if mean.sum() < 10:
            return face_id.EmbedResult(None, "no_face")
        seed = int(mean[2] // 40) * 100 + int(mean[1] // 40) * 10 + int(mean[0] // 40)
        return face_id.EmbedResult(_near(_unit(seed), 0.03, int(mean.sum())), None, (10, 10, 80, 80))


def _jpeg(bgr):
    img = np.zeros((96, 96, 3), np.uint8)
    img[:] = bgr
    img[0, 0] = (bgr[0] + 1) % 256    # vary bytes slightly
    ok, buf = cv2.imencode(".jpg", img)
    return "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode()


RED, BLUE, BLACK = (20, 20, 220), (220, 20, 20), (0, 0, 0)


@pytest.fixture()
def api(tmp_path, monkeypatch):
    from app.api import routes_users
    from app.identity.locality import require_local
    from app.identity.user_manager_lite import UserManager
    from app.main import app

    db = tmp_path / "users.db"
    manager = UserManager(db_path=str(db))
    manager._embedder = FakeEmbedder()
    monkeypatch.setattr(routes_users, "_user_manager", manager)
    local = {"on": True}

    def fake_require_local():
        if not local["on"]:
            from fastapi import HTTPException
            raise HTTPException(status_code=403, detail="not local")

    app.dependency_overrides[require_local] = fake_require_local
    monkeypatch.setattr(routes_users, "is_local_request", lambda request: local["on"])
    yield TestClient(app), manager, db, local
    app.dependency_overrides.pop(require_local, None)


def test_register_identify_forget(api, caplog, capsys):
    client, manager, db, _ = api
    caplog.set_level(logging.DEBUG)
    r = client.post("/api/users/register", json={"display_name": "Techno", "images": [_jpeg(RED)] * 8})
    assert r.status_code == 200, r.text
    uid = r.json()["user_id"]
    assert r.json()["samples_used"] == 8
    users = client.get("/api/users").json()
    assert users[0]["face_enrolled"] is True

    r = client.post("/api/users/identify", json={"images": [_jpeg(RED)] * 4})
    assert r.json()["matched"] is True and r.json()["user"]["user_id"] == uid
    r = client.post("/api/users/identify", json={"images": [_jpeg(BLUE)] * 4})
    assert r.json() == {"matched": False, "user": None, "reason": "no_match", "frames_with_face": 4}
    r = client.post("/api/users/identify", json={"images": [_jpeg(BLACK)] * 4})
    assert r.json()["reason"] == "no_face"

    # nothing but the embedding is stored; no image bytes anywhere in the DB
    raw = Path(db).read_bytes()
    assert b"\xff\xd8\xff" not in raw and b"JFIF" not in raw
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT face_features, profile_photo FROM users").fetchall() == [(None, None)]
    (dim, blob), = conn.execute("SELECT dim, vector FROM face_embeddings").fetchall()
    assert dim == 128 and len(blob) == 128 * 4

    # no embedding values or image data in logs or console output
    out = capsys.readouterr()
    emb = manager.gallery.load()[uid]
    text = caplog.text + out.out + out.err
    assert f"{emb[0]:.4f}" not in text and "base64" not in text

    r = client.delete(f"/api/users/{uid}/face")
    assert r.json()["face_enrolled"] is False
    assert client.post("/api/users/identify", json={"images": [_jpeg(RED)] * 4}).json()["matched"] is False
    assert client.get(f"/api/users/{uid}").json()["display_name"] == "Techno"   # account kept


def test_reenroll_existing_user(api):
    client, manager, _, _ = api
    profile = manager.register_user("old", "Old User")               # e.g. after the upgrade purge
    assert client.get("/api/users").json()[0]["face_enrolled"] is False
    r = client.post(f"/api/users/{profile.user_id}/face", json={"images": [_jpeg(BLUE)] * 6})
    assert r.status_code == 200 and r.json()["face_enrolled"] is True


def test_register_rejects_too_few_faces_without_creating_user(api):
    client, _, _, _ = api
    r = client.post("/api/users/register",
                    json={"display_name": "X", "images": [_jpeg(RED)] * 2 + [_jpeg(BLACK)] * 6})
    assert r.status_code == 400 and "2 of 8" in r.json()["detail"]
    assert client.get("/api/users").json() == []


def test_two_users_are_told_apart(api):
    client, _, _, _ = api
    a = client.post("/api/users/register", json={"display_name": "A", "images": [_jpeg(RED)] * 6}).json()
    b = client.post("/api/users/register", json={"display_name": "B", "images": [_jpeg(BLUE)] * 6}).json()
    assert client.post("/api/users/identify", json={"images": [_jpeg(BLUE)] * 3}).json()["user"]["user_id"] == b["user_id"]
    assert client.post("/api/users/identify", json={"images": [_jpeg(RED)] * 3}).json()["user"]["user_id"] == a["user_id"]


def test_remote_browser_refused(api):
    client, _, _, local = api
    local["on"] = False
    for path, body in [("/api/users/register", {"display_name": "X", "images": [_jpeg(RED)]}),
                       ("/api/users/identify", {"images": [_jpeg(RED)]}),
                       ("/api/users/1/face", {"images": [_jpeg(RED)]})]:
        assert client.post(path, json=body).status_code == 403, path
    s = client.get("/api/users/face-id/status").json()
    assert s["local"] is False


def test_real_guard_refuses_testclient():
    """Without the override, TestClient (not a loopback peer) is refused."""
    from app.main import app

    r = TestClient(app).post("/api/users/identify", json={"images": [_jpeg(RED)]})
    assert r.status_code == 403 and "never leaves" in r.json()["detail"]


def test_status_when_models_missing(tmp_path, monkeypatch):
    from app.identity.user_manager_lite import UserManager

    monkeypatch.setenv("LIFTGUARD_FACE_MODEL_DIR", str(tmp_path / "none"))
    m = UserManager(db_path=str(tmp_path / "u.db"))
    s = m.face_id_status()
    assert s["available"] is False and s["reason"] == "models_missing"
    assert m.identify_from_frame(np.zeros((64, 64, 3), np.uint8))[0] is None


def test_contributions_never_touch_face_data():
    """Contribution code has no path to embeddings or the user DB's face table."""
    root = Path(__file__).resolve().parents[1] / "app"
    for f in list((root / "contrib").rglob("*.py")) + [root / "api" / "routes_contrib.py"]:
        if f.exists():
            src = f.read_text()
            for word in ("face_id", "face_embeddings", "FaceGallery", "embed_bgr"):
                assert word not in src, f"{f.name} mentions {word}"


# ── real models (local only) ────────────────────────────────
real = pytest.mark.skipif(not face_id.models_present(), reason="face models not downloaded")


@real
def test_real_models_load_and_find_no_face_in_blank():
    e = face_id.SFaceEmbedder()
    r = e.embed(np.zeros((480, 640, 3), np.uint8))
    assert r.embedding is None and r.reason == "no_face"
