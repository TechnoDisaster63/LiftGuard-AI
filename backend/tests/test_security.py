import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.security import require_api_key, validate_esp32_host


class TestValidateEsp32Host:
    def test_private_ips_allowed(self, monkeypatch):
        monkeypatch.setattr(settings, "ESP32_ALLOWED_HOSTS", [])
        for host in ["192.168.1.42", "10.0.0.5", "172.16.0.10", "127.0.0.1"]:
            assert validate_esp32_host(host) == host

    def test_local_hostnames_allowed(self, monkeypatch):
        monkeypatch.setattr(settings, "ESP32_ALLOWED_HOSTS", [])
        assert validate_esp32_host("liftguard-laser.local") == "liftguard-laser.local"
        assert validate_esp32_host("esp32") == "esp32"

    def test_scheme_and_trailing_slash_stripped(self, monkeypatch):
        monkeypatch.setattr(settings, "ESP32_ALLOWED_HOSTS", [])
        assert validate_esp32_host("http://192.168.1.42/") == "192.168.1.42"

    def test_public_ip_rejected(self, monkeypatch):
        monkeypatch.setattr(settings, "ESP32_ALLOWED_HOSTS", [])
        with pytest.raises(ValueError):
            validate_esp32_host("8.8.8.8")

    def test_public_hostname_rejected(self, monkeypatch):
        monkeypatch.setattr(settings, "ESP32_ALLOWED_HOSTS", [])
        for host in ["example.com", "169.254.169.254.nip.io", "a.b.c"]:
            with pytest.raises(ValueError):
                validate_esp32_host(host)

    def test_credentials_and_port_rejected(self, monkeypatch):
        monkeypatch.setattr(settings, "ESP32_ALLOWED_HOSTS", [])
        with pytest.raises(ValueError):
            validate_esp32_host("user:pass@192.168.1.42")
        with pytest.raises(ValueError):
            validate_esp32_host("192.168.1.42:8080")

    def test_allowlist_overrides_private_rule(self, monkeypatch):
        monkeypatch.setattr(settings, "ESP32_ALLOWED_HOSTS", ["192.168.1.42"])
        assert validate_esp32_host("192.168.1.42") == "192.168.1.42"
        with pytest.raises(ValueError):
            validate_esp32_host("192.168.1.43")

    def test_empty_rejected(self, monkeypatch):
        monkeypatch.setattr(settings, "ESP32_ALLOWED_HOSTS", [])
        with pytest.raises(ValueError):
            validate_esp32_host("   ")


class TestRequireApiKey:
    def _app(self):
        app = FastAPI()

        @app.get("/protected", dependencies=[Depends(require_api_key)])
        def protected():
            return {"ok": True}

        return TestClient(app)

    def test_open_when_no_key(self, monkeypatch):
        monkeypatch.setattr(settings, "API_KEY", "")
        assert self._app().get("/protected").status_code == 200

    def test_rejects_missing_or_wrong_key(self, monkeypatch):
        monkeypatch.setattr(settings, "API_KEY", "test-key")
        client = self._app()
        assert client.get("/protected").status_code == 401
        assert client.get(
            "/protected", headers={"Authorization": "Bearer wrong"}
        ).status_code == 401

    def test_accepts_correct_key(self, monkeypatch):
        monkeypatch.setattr(settings, "API_KEY", "test-key")
        client = self._app()
        resp = client.get("/protected", headers={"Authorization": "Bearer test-key"})
        assert resp.status_code == 200
