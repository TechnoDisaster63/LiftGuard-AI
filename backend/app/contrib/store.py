"""Opt-in training-data contributions from pilot users.

What is saved, per consented set (one live session):
  landmarks.npz   landmarks [T, 22, 4] float16 (x, y, z, visibility) for
                  MediaPipe pose points 11-32 (shoulders to feet), NaN rows
                  for frames without a usable pose; t_ms [T] float32.
  meta.json       movement mode, schema/consent versions, device class,
                  camera facing/source, measured fps, frame size, mirror,
                  the engine's per-rep results ("engine_label", the rule's
                  output, not ground truth) and the optional self-label.

Never saved: frames, video, audio, face landmarks (MediaPipe points 0-10
are nose, eyes, ears and mouth, and are dropped before anything is kept),
names, face-ID user records, IP addresses, user-agent strings, free text.

Identity is an anonymous id (a random UUID the browser generates). It is
the only key: whoever holds it can list and delete its sets.
"""
from __future__ import annotations

import json
import math
import os
import re
import shutil
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

SCHEMA_VERSION = 1
CONSENT_VERSION = 1
MOVEMENT_MODE = "squat"
FIRST_BODY_POINT = 11  # MediaPipe: 0-10 are face points
NUM_POINTS = 33
BODY_POINTS = NUM_POINTS - FIRST_BODY_POINT  # 22
MAX_FRAMES = 15 * 60 * 20  # 20 minutes at 15 fps: a hard cap per set
DEVICE_CLASSES = {"phone", "tablet", "desktop", "unknown"}
FACINGS = {"environment", "user", "unknown"}
FEELS = {"easy", "ok", "hard", "hurt"}

_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
_SET_RE = re.compile(r"^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}$")


class ContribError(ValueError):
    """A bad anonymous id, set id or label. Safe to show to the user."""


def valid_anon_id(anon_id: Any) -> str:
    if not isinstance(anon_id, str) or not _UUID_RE.match(anon_id):
        raise ContribError("Not a valid contributor id.")
    return anon_id


def valid_set_id(set_id: Any) -> str:
    if not isinstance(set_id, str) or not _SET_RE.match(set_id):
        raise ContribError("Not a valid set id.")
    return set_id


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _json_safe(value):
    if isinstance(value, float):
        return round(value, 4) if math.isfinite(value) else None
    if isinstance(value, (int, str, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items() if not str(k).startswith("_")}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    try:  # numpy scalars
        return _json_safe(value.item())
    except Exception:
        return str(value)


class LandmarkRecorder:
    """Collects body landmarks for one session, in memory, until saved.

    ``add`` takes MediaPipe's 33 landmarks (objects with x, y, z,
    visibility) or None for a frame without a usable pose. Face points are
    dropped here, so they never reach memory beyond this call.
    """

    def __init__(self, anon_id: str, device_class: str = "unknown", camera_facing: str = "unknown",
                 camera_source: str = "unknown"):
        self.anon_id = valid_anon_id(anon_id)
        self.device_class = device_class if device_class in DEVICE_CLASSES else "unknown"
        self.camera_facing = camera_facing if camera_facing in FACINGS else "unknown"
        self.camera_source = camera_source
        self.rows: list[list[tuple[float, float, float, float]] | None] = []
        self.t_ms: list[float] = []
        self.frame_size: tuple[int, int] | None = None
        self.mirror_seen: set[bool] = set()
        self._t0: float | None = None
        self.truncated = False

    def add(self, landmarks: Optional[Iterable], width: int, height: int, mirror: bool = False,
            now: Optional[float] = None) -> None:
        if len(self.rows) >= MAX_FRAMES:
            self.truncated = True
            return
        now = time.monotonic() if now is None else now
        if self._t0 is None:
            self._t0 = now
        self.frame_size = (int(width), int(height))
        self.mirror_seen.add(bool(mirror))
        row = None
        if landmarks is not None:
            pts = list(landmarks)
            if len(pts) == NUM_POINTS:
                row = [(float(p.x), float(p.y), float(p.z), float(p.visibility))
                       for p in pts[FIRST_BODY_POINT:]]
        self.rows.append(row)
        self.t_ms.append((now - self._t0) * 1000.0)

    @property
    def frames(self) -> int:
        return len(self.rows)

    def measured_fps(self) -> float | None:
        if len(self.t_ms) < 2 or self.t_ms[-1] <= 0:
            return None
        return round((len(self.t_ms) - 1) / (self.t_ms[-1] / 1000.0), 2)

    def arrays(self):
        import numpy as np

        data = np.full((len(self.rows), BODY_POINTS, 4), np.nan, dtype=np.float16)
        for i, row in enumerate(self.rows):
            if row is not None:
                data[i] = np.asarray(row, dtype=np.float16)
        return data, np.asarray(self.t_ms, dtype=np.float32)


class ContributionStore:
    """Consent records and saved sets on local disk, mirrored to an
    optional uploader (a private Hugging Face dataset repo)."""

    def __init__(self, root: os.PathLike | str, uploader=None):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.uploader = uploader
        self._lock = threading.Lock()

    # ── Consent ─────────────────────────────────────────────
    def _dir(self, anon_id: str) -> Path:
        return self.root / valid_anon_id(anon_id)

    def give_consent(self, anon_id: str, adult: bool) -> dict:
        if adult is not True:
            raise ContribError("You need to be 18 or older to contribute.")
        d = self._dir(anon_id)
        d.mkdir(parents=True, exist_ok=True)
        record = {"anon_id": anon_id, "consent_version": CONSENT_VERSION, "adult_confirmed": True,
                  "given_at": _now_iso()}
        (d / "consent.json").write_text(json.dumps(record, indent=2))
        return record

    def consent(self, anon_id: str) -> dict | None:
        p = self._dir(anon_id) / "consent.json"
        if not p.exists():
            return None
        try:
            record = json.loads(p.read_text())
        except (OSError, ValueError):
            return None
        return record if record.get("consent_version") == CONSENT_VERSION else None

    def withdraw(self, anon_id: str) -> int:
        """Stop contributing and delete everything under this id."""
        removed = self.delete_all(anon_id)
        shutil.rmtree(self._dir(anon_id), ignore_errors=True)
        return removed

    # ── Sets ────────────────────────────────────────────────
    def save(self, recorder: LandmarkRecorder, reps: list[dict], app_version: str = "") -> dict | None:
        """Write one set. Returns its summary, or None when nothing is worth
        keeping (no consent any more, or no frame had a pose)."""
        import numpy as np

        anon_id = recorder.anon_id
        consent = self.consent(anon_id)
        if consent is None:
            return None
        if not any(r is not None for r in recorder.rows):
            return None
        set_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
        d = self._dir(anon_id) / set_id
        d.mkdir(parents=True, exist_ok=False)
        landmarks, t_ms = recorder.arrays()
        np.savez_compressed(d / "landmarks.npz", landmarks=landmarks, t_ms=t_ms)
        engine_reps = [_json_safe(r) for r in reps]
        meta = {
            "schema_version": SCHEMA_VERSION,
            "set_id": set_id,
            "anon_id": anon_id,
            "movement_mode": getattr(recorder, "movement_mode", MOVEMENT_MODE),
            "created_at": _now_iso(),
            "app_version": app_version,
            "consent_version": consent["consent_version"],
            "landmark_points": list(range(FIRST_BODY_POINT, NUM_POINTS)),
            "landmark_fields": ["x", "y", "z", "visibility"],
            "coords": "MediaPipe normalized image coordinates (0-1), after any mirror flip",
            "frames": recorder.frames,
            "frames_with_pose": sum(r is not None for r in recorder.rows),
            "truncated": recorder.truncated,
            "measured_fps": recorder.measured_fps(),
            "frame_width": recorder.frame_size[0] if recorder.frame_size else None,
            "frame_height": recorder.frame_size[1] if recorder.frame_size else None,
            "mirror": sorted(recorder.mirror_seen),
            "device_class": recorder.device_class,
            "camera_facing": recorder.camera_facing,
            "camera_source": recorder.camera_source,
            "engine_label": {
                "note": "Output of the rule engine at recording time, not ground truth.",
                "reps": engine_reps,
                "total_reps": len(engine_reps),
                "flagged_reps": sum(bool(r.get("form_flags")) for r in engine_reps),
            },
            "self_label": None,
        }
        (d / "meta.json").write_text(json.dumps(meta, indent=2))
        self._upload(anon_id, set_id)
        return self.summary(meta)

    @staticmethod
    def summary(meta: dict) -> dict:
        eng = meta.get("engine_label") or {}
        return {
            "set_id": meta["set_id"],
            "created_at": meta["created_at"],
            "movement_mode": meta["movement_mode"],
            "total_reps": eng.get("total_reps", 0),
            "flagged_reps": eng.get("flagged_reps", 0),
            "frames": meta.get("frames", 0),
            "seconds": round((meta.get("frames") or 0) / meta["measured_fps"], 1) if meta.get("measured_fps") else None,
            "self_label": meta.get("self_label"),
        }

    def _meta_path(self, anon_id: str, set_id: str) -> Path:
        return self._dir(anon_id) / valid_set_id(set_id) / "meta.json"

    def list(self, anon_id: str) -> list[dict]:
        d = self._dir(anon_id)
        out = []
        if d.exists():
            for sub in sorted(d.iterdir(), reverse=True):
                if sub.is_dir() and _SET_RE.match(sub.name) and (sub / "meta.json").exists():
                    try:
                        out.append(self.summary(json.loads((sub / "meta.json").read_text())))
                    except (OSError, ValueError, KeyError):
                        continue
        return out

    def label(self, anon_id: str, set_id: str, feel: Optional[str], counting_right: Optional[bool]) -> dict:
        if feel is not None and feel not in FEELS:
            raise ContribError("Unknown rating.")
        if counting_right is not None and not isinstance(counting_right, bool):
            raise ContribError("Unknown answer.")
        p = self._meta_path(anon_id, set_id)
        with self._lock:
            if not p.exists():
                raise KeyError(set_id)
            meta = json.loads(p.read_text())
            meta["self_label"] = {"feel": feel, "counting_right": counting_right, "labeled_at": _now_iso()}
            p.write_text(json.dumps(meta, indent=2))
        self._upload(anon_id, set_id)
        return self.summary(meta)

    def delete(self, anon_id: str, set_id: str) -> bool:
        d = self._dir(anon_id) / valid_set_id(set_id)
        if not d.exists():
            return False
        shutil.rmtree(d)
        if self.uploader is not None:
            self.uploader.delete_paths([f"{anon_id}/{set_id}"])
        return True

    def delete_all(self, anon_id: str) -> int:
        sets = [s["set_id"] for s in self.list(anon_id)]
        for set_id in sets:
            shutil.rmtree(self._dir(anon_id) / set_id, ignore_errors=True)
        if self.uploader is not None and sets:
            self.uploader.delete_paths([anon_id])
        return len(sets)

    def _upload(self, anon_id: str, set_id: str) -> None:
        if self.uploader is not None:
            self.uploader.upload_set(self._dir(anon_id) / set_id, f"{anon_id}/{set_id}")
