"""Enrollment upload limits - these fire before any CV code runs, so they
need no opencv/mediapipe install."""
import base64

from fastapi.testclient import TestClient

from app.main import app
from app.api.routes_users import _estimate_decoded_size
from app.identity.locality import require_local

client = TestClient(app)


def setup_module(_):
    # Face frames are only accepted from the backend's own machine; these
    # tests exercise the upload limits behind that check.
    app.dependency_overrides[require_local] = lambda: None


def teardown_module(_):
    app.dependency_overrides.pop(require_local, None)

_TINY_JPEG_B64 = base64.b64encode(b"\xff\xd8\xff" + b"\x00" * 64).decode()


def test_estimate_decoded_size_plain_and_data_url():
    raw = b"\x01" * 300
    b64 = base64.b64encode(raw).decode()
    assert abs(_estimate_decoded_size(b64) - 300) <= 3
    assert abs(_estimate_decoded_size(f"data:image/jpeg;base64,{b64}") - 300) <= 3


def test_too_many_images_rejected():
    resp = client.post(
        "/api/users/register",
        json={"display_name": "Test", "images": [_TINY_JPEG_B64] * 31},
    )
    assert resp.status_code == 413


def test_oversized_image_rejected():
    big = base64.b64encode(b"\x00" * (6 * 1024 * 1024)).decode()
    resp = client.post(
        "/api/users/register",
        json={"display_name": "Test", "images": [big]},
    )
    assert resp.status_code == 413


def test_empty_display_name_rejected():
    resp = client.post(
        "/api/users/register",
        json={"display_name": "", "images": [_TINY_JPEG_B64]},
    )
    assert resp.status_code == 422
