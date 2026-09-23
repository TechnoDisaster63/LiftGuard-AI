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

from dataclasses import dataclass, field


def _squat():
    from .live import LiveSquatCounter
    return LiveSquatCounter


def _pushup():
    from .pushup import LivePushupCounter
    return LivePushupCounter


MOVEMENT_MODES: dict[str, dict] = {
    "squat": {"label": "Squat", "noun": "squat", "source": "calibrated_squat_counter", "view": "side",
              "counter": _squat},
    "pushup": {"label": "Push-up", "noun": "push-up", "source": "calibrated_pushup_counter", "view": "side",
               "counter": _pushup},
}

# MM-Fit activity labels -> LiftGuard modes. Labels with no mode yet map to None.
RECOGNIZER_LABELS: dict[str, str | None] = {
    "squats": "squat",
    "pushups": "pushup",
    "lunges": None,
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
