"""Application settings. Values can be overridden via environment variables."""
import os
from pathlib import Path

# backend/ - the directory this file's package (app/core/) lives two levels under.
# Used so file paths below are correct regardless of the working directory
# uvicorn was launched from (a very easy thing to get wrong, and it silently
# breaks anything touching USER_DB_PATH - see the mkdir below).
BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings:
    APP_NAME: str = "LiftGuard AI"
    API_PREFIX: str = "/api"

    # CORS - set to your deployed frontend origin(s) in production.
    # Includes both localhost and 127.0.0.1 by default: browsers treat these
    # as DIFFERENT origins for CORS purposes even though they're the same
    # machine, and `next dev` / a browser bookmark can land on either one.
    # A mismatch here silently blocks every API call from the frontend
    # (registration, session start, everything) with no obvious error unless
    # you check the browser console's Network tab.
    _default_origins = (
        "http://localhost:3000,http://127.0.0.1:3000,"
        "http://localhost:3001,http://127.0.0.1:3001"
    )
    CORS_ORIGINS: list[str] = os.getenv(
        "LIFTGUARD_CORS_ORIGINS", _default_origins
    ).split(",")

    # Default camera / engine settings (mirrors the original main.py constants)
    DEFAULT_CAMERA_ID: int = int(os.getenv("LIFTGUARD_CAMERA_ID", "0"))
    VOICE_ENABLED: bool = os.getenv("LIFTGUARD_VOICE_ENABLED", "true").lower() == "true"
    ARDUINO_ENABLED: bool = os.getenv("LIFTGUARD_ARDUINO_ENABLED", "true").lower() == "true"
    MODEL_COMPLEXITY: int = int(os.getenv("LIFTGUARD_MODEL_COMPLEXITY", "0"))
    PROCESS_EVERY_N: int = int(os.getenv("LIFTGUARD_PROCESS_EVERY_N", "1"))
    USE_TEMPORAL: bool = os.getenv("LIFTGUARD_USE_TEMPORAL", "true").lower() == "true"

    # SQLite database used by user_manager_lite.py (unchanged schema/path
    # convention). Resolved to an absolute path under backend/ instead of a
    # bare relative one - sqlite3 does NOT create missing directories, so a
    # relative "data/..." silently pointed at the wrong place (and crashed
    # UserManager() at import time) if uvicorn was launched from anywhere
    # other than backend/ itself.
    USER_DB_PATH: str = os.getenv(
        "LIFTGUARD_USER_DB", str(BACKEND_ROOT / "data" / "liftguard_users.db")
    )

    # WebSocket target frame rate (the engine itself decides real throughput;
    # this just paces the read loop so we don't spin a CPU core at 100%)
    WS_TARGET_FPS: int = int(os.getenv("LIFTGUARD_WS_FPS", "30"))

    # ── Security ───────────────────────────────────────────
    # Optional API key. When set, every REST route and the live WebSocket
    # require it: REST via `Authorization: Bearer <key>`, the WebSocket via
    # `?token=<key>` (browsers cannot set headers on WS handshakes).
    # Empty = open development mode, intended for localhost only. Set this
    # before exposing the backend to any network you do not fully control -
    # without it, anyone who can reach the port can read users/sessions,
    # change settings, enroll face data, and control the laser.
    API_KEY: str = os.getenv("LIFTGUARD_API_KEY", "")

    # Optional comma-separated allowlist of ESP32 hosts (IPs or mDNS
    # hostnames) that /api/hardware/{id}/connect is permitted to reach.
    # Empty = any private/loopback/link-local IP or local (.local /
    # single-label) hostname; public addresses are always rejected. See
    # app/core/security.py for why the backend must not proxy requests to
    # arbitrary hosts.
    ESP32_ALLOWED_HOSTS: list[str] = [
        h.strip()
        for h in os.getenv("LIFTGUARD_ESP32_ALLOWED_HOSTS", "").split(",")
        if h.strip()
    ]

    # Browser face-enrollment upload limits. Frames arrive as base64 in a
    # single JSON body, so bound both the count and the per-image size.
    MAX_REGISTER_IMAGES: int = int(os.getenv("LIFTGUARD_MAX_REGISTER_IMAGES", "30"))
    MAX_IMAGE_BYTES: int = int(os.getenv("LIFTGUARD_MAX_IMAGE_BYTES", str(5 * 1024 * 1024)))


settings = Settings()

# Guarantee the directory exists before anything (UserManager, the
# SQLAlchemy engine) tries to open a file inside it.
Path(settings.USER_DB_PATH).parent.mkdir(parents=True, exist_ok=True)
