"""Thread-safe, crash-tolerant persistence for editable session defaults."""
import json
import os
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
    "movement_mode",
    "auto_detect",
)


def _environment_defaults() -> dict:
    return {
        "camera_id": env_settings.DEFAULT_CAMERA_ID,
        "voice_enabled": env_settings.VOICE_ENABLED,
        "arduino_enabled": env_settings.ARDUINO_ENABLED,
        "model_complexity": env_settings.MODEL_COMPLEXITY,
        "process_every_n": env_settings.PROCESS_EVERY_N,
        "use_temporal": env_settings.USE_TEMPORAL,
        "movement_mode": "squat",
        "auto_detect": False,  # recognizer mode switching: off unless the user turns it on
    }


class SessionDefaultsStore:
    def __init__(self, path: Path):
        self._path = path
        self._lock = threading.Lock()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._data = self._load()
        if not self._path.exists():
            self._save()

    def _load(self) -> dict:
        defaults = _environment_defaults()
        if not self._path.exists():
            return defaults
        try:
            stored = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            # A partial/corrupt settings file must not prevent the API from
            # starting. Preserve it for diagnosis and recover safe defaults.
            corrupt_path = self._path.with_suffix(self._path.suffix + ".corrupt")
            try:
                os.replace(self._path, corrupt_path)
            except OSError:
                pass
            return defaults
        if not isinstance(stored, dict):
            return defaults
        data = {**defaults, **{key: stored[key] for key in _FIELDS if key in stored}}
        from ..video_analysis.movements import DEFAULT_MODE, is_selectable

        if not is_selectable(data.get("movement_mode", "")):
            # A mode that is unknown or no longer unlocked falls back to squat.
            data["movement_mode"] = DEFAULT_MODE
        return data

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

    def _save(self) -> None:
        temporary = self._path.with_suffix(self._path.suffix + ".tmp")
        temporary.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
        os.replace(temporary, self._path)


session_defaults = SessionDefaultsStore(_DEFAULTS_PATH)
