"""Auto-detect: lets the recognizer switch the live feed's movement mode.

Off by default. It runs only when both are set on the backend:

  LIFTGUARD_AUTO_DETECT=1
  LIFTGUARD_RECOGNIZER_MODEL=/path/to/recognizer_rf.npz   (local file, never in git)

How a switch happens (design in docs/MOVEMENT_MODES.md):

1. Frames are sampled at about 10 fps of stream time (the counter's own
   frame rate, so a video file behaves the same at any playback speed).
2. Every 0.5 s the last 2 s window of landmarks goes to the recognizer, which
   returns (label, confidence). No pose -> ('other', 0.0).
3. A label whose mode cannot be picked yet (``validated`` False and not
   unlocked with LIFTGUARD_PREVIEW_MODES) is treated as 'other'. So today,
   with only squat validated, auto-detect can never leave squat for users.
4. ``RecognizerGate`` switches only when the same supported label holds at
   >= 0.8 for 2 s, and never while the current counter is mid-rep.
5. ``feed.set_mode`` starts a fresh counter. Counting and every cue stay with
   the mode's landmark rules; the recognizer only names the movement.

Any recognizer error turns auto-detect off for the session and the feed keeps
counting in its current mode.
"""
from __future__ import annotations

import logging
import math
import os
from collections import deque

import numpy as np

from .movements import RECOGNIZER_LABELS, RecognizerGate, is_selectable

log = logging.getLogger(__name__)

SAMPLE_FPS = 10.0
WINDOW_SECONDS = 2.0
HOP_SECONDS = 0.5


def landmark_array(landmarks) -> np.ndarray:
    """MediaPipe landmark list -> (33, 3) array of x, y, visibility; None -> NaNs."""
    if landmarks is None:
        return np.full((33, 3), np.nan, dtype=np.float32)
    return np.array([(lm.x, lm.y, lm.visibility) for lm in landmarks], dtype=np.float32)


class AutoModeSwitcher:
    def __init__(self, recognizer, mode: str = "squat", min_confidence: float = 0.8,
                 hold_seconds: float = 2.0) -> None:
        self.recognizer = recognizer
        self.min_confidence = min_confidence
        self.hold_seconds = hold_seconds
        self.enabled = True
        self.error: str | None = None
        self.switches: list[dict] = []
        self.frames = 0                             # stream frames seen; never reset
        self.reset(mode)

    def reset(self, mode: str) -> None:
        """New session or manual mode change: forget the window and any candidate."""
        self.gate = RecognizerGate(current=mode, min_confidence=self.min_confidence,
                                   hold_seconds=self.hold_seconds)
        self.samples: deque = deque(maxlen=int(round(WINDOW_SECONDS * SAMPLE_FPS)))
        self.last_slot = -1
        self.last_predict_slot = None
        self.last: dict | None = None

    def observe(self, landmarks, aspect: float | None, feed) -> str | None:
        """Call once per processed frame, after ``feed.update``. Returns the new mode on a switch."""
        if not self.enabled:
            return None
        if feed.mode != self.gate.current:          # mode changed elsewhere (settings)
            self.reset(feed.mode)
        fps = feed.fps or getattr(feed, "fixed_fps", None)
        index = self.frames
        self.frames += 1
        if not fps:
            return None                             # frame rate not measured yet
        now = index / fps
        slot = math.floor(now * SAMPLE_FPS + 1e-9)
        if slot == self.last_slot:
            return None
        self.last_slot = slot
        self.samples.append(landmark_array(landmarks))
        hop = int(round(HOP_SECONDS * SAMPLE_FPS))
        if len(self.samples) < self.samples.maxlen:
            return None
        if self.last_predict_slot is not None and slot - self.last_predict_slot < hop:
            return None
        self.last_predict_slot = slot
        try:
            label, confidence = self.recognizer.predict(np.stack(self.samples), aspect or 16 / 9, 1.0)
        except Exception as exc:  # never let the recognizer break the frame loop
            self.enabled, self.error = False, f"{type(exc).__name__}: {exc}"
            log.warning("Auto-detect turned off after a recognizer error: %s", self.error)
            return None
        mode = RECOGNIZER_LABELS.get(label)
        gate_label = label if (mode and is_selectable(mode)) else "other"
        # Every mode's rep machine is in state "bottom" from the start of a rep until it finishes.
        machine = getattr(getattr(feed, "counter", None), "machine", None)
        mid_rep = getattr(machine, "state", None) == "bottom"
        new_mode = self.gate.observe(gate_label, confidence, now, mid_rep=mid_rep)
        self.last = {"label": label, "confidence": round(float(confidence), 3), "t": round(now, 2),
                     "counts": gate_label != "other"}
        if new_mode is None:
            return None
        previous = feed.mode
        feed.set_mode(new_mode)
        self.switches.append({"from": previous, "to": new_mode, "t": round(now, 2)})
        self.reset(new_mode)
        return new_mode

    def status(self) -> dict:
        return {"enabled": self.enabled, "last": self.last, "switches": list(self.switches),
                "error": self.error}


def auto_detect_requested() -> bool:
    return os.environ.get("LIFTGUARD_AUTO_DETECT", "").strip().lower() in {"1", "true", "yes", "on"}


def model_path() -> str:
    return os.environ.get("LIFTGUARD_RECOGNIZER_MODEL", "").strip()


def availability() -> dict:
    """For the settings screen: can auto-detect run on this backend?"""
    path = model_path()
    if not path:
        return {"available": False, "reason": "No recognizer model on this machine (LIFTGUARD_RECOGNIZER_MODEL is not set)."}
    if not os.path.isfile(path):
        return {"available": False, "reason": "The recognizer model file set in LIFTGUARD_RECOGNIZER_MODEL was not found."}
    return {"available": True, "reason": None}


def switcher_from_env(mode: str = "squat", requested: bool | None = None) -> AutoModeSwitcher | None:
    """None (auto-detect off) unless turned on with a usable model.

    ``requested`` is the session's settings toggle; None falls back to the
    LIFTGUARD_AUTO_DETECT environment flag (the engine's default at start-up).
    """
    if not (auto_detect_requested() if requested is None else requested):
        return None
    path = model_path()
    if not path or not os.path.isfile(path):
        log.warning("LIFTGUARD_AUTO_DETECT is on but LIFTGUARD_RECOGNIZER_MODEL=%r is not a file; "
                    "auto-detect stays off.", path)
        return None
    from .recognizer import load_recognizer
    try:
        recognizer = load_recognizer(path)
    except Exception as exc:
        log.warning("Could not load the recognizer model %r (%s); auto-detect stays off.", path, exc)
        return None
    return AutoModeSwitcher(recognizer, mode=mode)
