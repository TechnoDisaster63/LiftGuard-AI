"""Movement modes and the hook for an exercise recognizer.

A movement mode owns its rep counter and form rules. The live feed runs one
mode at a time. The mode comes from the session settings today; a recognizer
(for example the MM-Fit exercise classifier) can switch it through
``LiveSquatFeed.set_mode`` using ``RecognizerGate`` below.

The recognizer only names the movement. Rep counting and every form-risk flag
still come from the mode's own landmark rules, so an unsupported or uncertain
label changes nothing.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _squat():
    from .live import LiveSquatCounter
    return LiveSquatCounter


def _pushup():
    from .pushup import LivePushupCounter
    return LivePushupCounter


def _lunge():
    from .lunge import LiveLungeCounter
    return LiveLungeCounter


MOVEMENT_MODES: dict[str, dict] = {
    "squat": {"label": "Squat", "noun": "squat", "source": "calibrated_squat_counter", "view": "side",
              "counter": _squat, "validated": True,
              "watches": "depth, trunk lean, range of motion, knees, heels, tempo"},
    "pushup": {"label": "Push-up", "noun": "push-up", "source": "calibrated_pushup_counter", "view": "side",
               "counter": _pushup, "validated": False,
               "watches": "depth, hip line, tempo",
               "pending": "Needs a check on a recorded side-view clip before it can be picked."},
    "lunge": {"label": "Lunge", "noun": "lunge", "source": "calibrated_lunge_counter", "view": "side",
              "counter": _lunge, "validated": False,
              "watches": "front knee depth, trunk lean, knee over toes, tempo",
              "pending": "Needs a check on a recorded side-view clip before it can be picked."},
}

DEFAULT_MODE = "squat"


def preview_modes() -> set[str]:
    """Unvalidated modes unlocked for development with LIFTGUARD_PREVIEW_MODES=pushup,..."""
    raw = os.environ.get("LIFTGUARD_PREVIEW_MODES", "")
    return {m.strip() for m in raw.split(",") if m.strip() in MOVEMENT_MODES}


def is_selectable(mode: str) -> bool:
    """A mode can be picked once it has passed a recorded-clip check (or is unlocked for development)."""
    info = MOVEMENT_MODES.get(mode)
    return bool(info) and (info["validated"] or mode in preview_modes())


def modes_for_api() -> list[dict]:
    return [
        {"id": mode, "label": info["label"], "watches": info["watches"], "view": info["view"],
         "validated": info["validated"], "selectable": is_selectable(mode),
         "note": None if info["validated"] else info.get("pending")}
        for mode, info in MOVEMENT_MODES.items()
    ]

# MM-Fit activity labels -> LiftGuard modes. Labels with no mode yet map to None.
RECOGNIZER_LABELS: dict[str, str | None] = {
    "squats": "squat",
    "pushups": "pushup",
    "lunges": "lunge",
    "jumping_jacks": None,
    "situps": None,
    "bicep_curls": None,
    "tricep_extensions": None,
    "dumbbell_rows": None,
    "dumbbell_shoulder_press": None,
    "lateral_shoulder_raises": None,
}


def counter_class(mode: str):
    if mode not in MOVEMENT_MODES:
        raise ValueError(f"Unknown movement mode {mode!r}; available: {', '.join(MOVEMENT_MODES)}")
    return MOVEMENT_MODES[mode]["counter"]()


@dataclass
class RecognizerGate:
    """Turns noisy per-window recognizer output into rare, deliberate mode switches.

    Switch only when the same supported label has been predicted with at least
    ``min_confidence`` for ``hold_seconds`` in a row, and never in the middle
    of a rep (the caller passes ``mid_rep``). Anything else keeps the current mode.
    """

    current: str = "squat"
    min_confidence: float = 0.8
    hold_seconds: float = 2.0
    _candidate: str | None = field(default=None, init=False)
    _since: float | None = field(default=None, init=False)

    def observe(self, label: str, confidence: float, now: float, mid_rep: bool = False) -> str | None:
        """Feed one prediction. Returns the new mode when a switch should happen, else None."""
        mode = RECOGNIZER_LABELS.get(label)
        if mode is None or confidence < self.min_confidence or mode == self.current:
            self._candidate = self._since = None
            return None
        if mode != self._candidate:
            self._candidate, self._since = mode, now
            return None
        if now - self._since < self.hold_seconds or mid_rep:
            return None
        self.current, self._candidate, self._since = mode, None, None
        return mode
