"""
Editable session defaults — the settings a person can actually change from
the dashboard (camera id, voice, Arduino, model complexity, TCN on/off).

Distinct from core/config.py's Settings, which is process-level
infrastructure config (CORS origins, DB path, WS frame rate) meant to be set
once via environment variables at deploy time, not toggled from a UI.

Persisted to a small JSON file rather than a DB table — this is a single
settings object, not a collection that needs querying/joining, so a table
would be overkill. Loaded once at startup with env-var fallback for the
very first run, then the file (once it exists) is the source of truth.
"""
import json
import threading
from pathlib import Path

from .config import settings as env_settings

_DEFAULTS_PATH = Path(env_settings.USER_DB_PATH).parent / "session_defaults.json"

_FIELDS = (
    "camera_id",
    "voice_enabled",
    "arduino_enabled",
    "model_complexity",
    "process_every_n",
    "use_temporal",
)


class SessionDefaultsStore:
    def __init__(self, path: Path):
        self._path = path
        self._lock = threading.Lock()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if self._path.exists():
            self._data = json.loads(self._path.read_text())
        else:
            self._data = {
                "camera_id": env_settings.DEFAULT_CAMERA_ID,
                "voice_enabled": env_settings.VOICE_ENABLED,
                "arduino_enabled": env_settings.ARDUINO_ENABLED,
                "model_complexity": env_settings.MODEL_COMPLEXITY,
                "process_every_n": env_settings.PROCESS_EVERY_N,
                "use_temporal": env_settings.USE_TEMPORAL,
            }
            self._save()

    def get(self) -> dict:
        with self._lock:
            return dict(self._data)

    def update(self, patch: dict) -> dict:
        with self._lock:
            for key, value in patch.items():
                if key in _FIELDS and value is not None:
                    self._data[key] = value
            self._save()
            return dict(self._data)

    def _save(self):
        self._path.write_text(json.dumps(self._data, indent=2))


session_defaults = SessionDefaultsStore(_DEFAULTS_PATH)
