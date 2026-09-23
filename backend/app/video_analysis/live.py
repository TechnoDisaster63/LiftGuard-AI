"""Realtime squat counting for the live camera path.

Uses the same per-frame metrics, calibration, rep state machine and leg gates
as the offline analyzer (``analyzer.py``), adapted to a stream:

- Knee angles are smoothed with a trailing median (the offline pass can look
  ahead; a live stream cannot). This adds about 0.1 s of lag.
- Thresholds are calibrated from a rolling window of recent frames and
  refreshed about once a second, so they follow the lifter.
- Until the window shows real squat motion, nothing is counted. When
  calibration first succeeds, the buffered frames are replayed so a rep done
  during warm-up is not lost.
- A rolling window can drift: if the lifter pauses long enough that the window
  holds no squat motion, counting pauses until motion returns. Counts never go
  backwards.

Outputs are rep counts and form-risk flags only - not a diagnosis.
"""
from __future__ import annotations

from collections import deque
from typing import Mapping

import numpy as np

from .analyzer import (
    AnalysisConfig,
    Point,
    RepStateMachine,
    _metrics,
    calibrate_thresholds,
    leg_reference,
)

MEASUREMENT_ALIASES = ("shoulder", "hip", "knee", "ankle")


def named_landmarks(landmarks, names: tuple[str, ...]) -> dict[str, Point]:
    """Convert a MediaPipe landmark list into the analyzer's named mapping."""
    points = {name: (lm.x, lm.y, lm.visibility) for name, lm in zip(names, landmarks)}
    for alias in MEASUREMENT_ALIASES:
        key = f"left_{alias}"
        if key in points:
            points[alias] = points[key]
    return points


class LiveSquatCounter:
    def __init__(self, fps: float = 25.0, config: AnalysisConfig | None = None, aspect: float = 16 / 9,
                 window_seconds: float = 30.0, recalibrate_seconds: float = 1.0) -> None:
        self.fps = fps
        self.config = config or AnalysisConfig()
        self.window = deque(maxlen=max(1, int(window_seconds * fps)))
        self.recent_knees: deque[float] = deque(maxlen=max(1, int(fps * self.config.smoothing_seconds) | 1))
        self.recalibrate_every = max(1, int(recalibrate_seconds * fps))
        self.machine = RepStateMachine(fps, self.config, aspect, history_limit=int(10 * fps))
        self.thresholds: dict = {"mode": "WARMING_UP"}
        self.leg_ref: float | None = None
        self.frame_index = 0
        self.valid_frames = 0
        self.calibrated_once = False
        self.last_metrics: dict | None = None
        self.last_pushed = -1

    # ── feeding ──────────────────────────────────────────────
    def update(self, points: Mapping[str, Point] | None) -> dict:
        """Feed one frame's named landmarks (normalized x, y, visibility) or None."""
        index = self.frame_index
        self.frame_index += 1
        metrics = _metrics(points, self.config.min_visibility) if points else None
        self.last_metrics = metrics
        if metrics is None:
            return self.status()
        self.valid_frames += 1
        self.recent_knees.append(metrics["knee_angle"])
        knee = float(np.median(self.recent_knees))
        self.window.append((index, metrics, knee))
        if self.valid_frames % self.recalibrate_every == 0:
            self._recalibrate()
        if self.thresholds.get("mode") == "CALIBRATED":
            self._push(index, metrics, knee)
        return self.status()

    def _recalibrate(self) -> None:
        metrics = [m for _, m, _ in self.window]
        thresholds = calibrate_thresholds([m["knee_angle"] for m in metrics], self.config)
        was_counting = self.thresholds.get("mode") == "CALIBRATED"
        if thresholds["mode"] != "CALIBRATED":
            # Keep the last good thresholds while a rep is in progress.
            if self.machine.state == "bottom":
                return
            if self.calibrated_once:
                self.thresholds = {**self.thresholds, "mode": "PAUSED", "reason": thresholds["reason"]}
            else:
                self.thresholds = thresholds
            return
        self.thresholds, self.leg_ref = thresholds, leg_reference(metrics, self.config)
        self.calibrated_once = True
        if not was_counting:
            # Motion just became countable: replay frames the counter has not seen
            # yet so a rep started during warm-up or a pause is not lost.
            self.machine.reset_phase()
            for index, m, knee in list(self.window)[:-1]:
                if index > self.last_pushed:
                    self._push(index, m, knee)

    def _push(self, index: int, metrics: dict, knee: float) -> None:
        self.machine.push(index, metrics, knee, self.thresholds, self.leg_ref)
        self.last_pushed = index

    # ── output ───────────────────────────────────────────────
    @property
    def rep_count(self) -> int:
        return len(self.machine.reps)

    def status(self) -> dict:
        mode = self.thresholds.get("mode", "WARMING_UP")
        counting = mode == "CALIBRATED"
        phase = "down" if self.machine.state == "bottom" else "up"
        last = self.machine.reps[-1] if self.machine.reps else None
        return {
            "exercise": "Squat" if self.machine.reps else "Detecting squat...",
            "rep_count": self.rep_count,
            "phase": phase if counting else "idle",
            "phase_display": ("\u2193" if phase == "down" else "\u2191") if counting else "",
            "calibration_mode": mode,
            "bottom_knee_deg": self.thresholds.get("bottom_knee_deg"),
            "standing_knee_deg": self.thresholds.get("standing_knee_deg"),
            "knee_angle": self.last_metrics["knee_angle"] if self.last_metrics else None,
            "last_rep": {k: v for k, v in last.items() if not k.startswith("_")} if last else None,
            "rep_gates": {k: v for k, v in self.machine.log.items() if k.startswith("rejected_")},
            "source": "calibrated_squat_counter",
        }


class LiveSquatFeed:
    """Engine-facing wrapper: picks the frame rate, then drives LiveSquatCounter.

    The counter's timing rules (rep duration, smoothing, standing reference)
    are in seconds, so it needs the rate at which frames actually arrive.
    For a video file that is the file's fps (playback speed does not matter).
    For a webcam it is the measured processing rate, estimated from the first
    ``fps_probe_frames`` frames and then fixed.
    """

    def __init__(self, fps: float | None = None, fps_probe_frames: int = 30,
                 clock=None, landmark_names: tuple[str, ...] | None = None) -> None:
        import time

        from .analyzer import POSE_LANDMARK_NAMES

        self.clock = clock or time.monotonic
        self.names = landmark_names or POSE_LANDMARK_NAMES
        self.fixed_fps = fps
        self.fps_probe_frames = max(2, fps_probe_frames)
        self.pending: list[tuple[float, dict | None]] = []
        self.counter: LiveSquatCounter | None = None
        self.aspect = 16 / 9

    def update(self, landmarks, aspect: float | None = None) -> dict:
        """``landmarks``: MediaPipe landmark list, or None when there is no usable pose."""
        if aspect:
            self.aspect = aspect
        points = named_landmarks(landmarks, self.names) if landmarks is not None else None
        if self.counter is not None:
            return self.counter.update(points)
        self.pending.append((self.clock(), points))
        fps = self.fixed_fps
        if fps is None and len(self.pending) >= self.fps_probe_frames:
            elapsed = self.pending[-1][0] - self.pending[0][0]
            fps = (len(self.pending) - 1) / elapsed if elapsed > 0 else 25.0
        if fps is None:
            return self.warming_status()
        self.counter = LiveSquatCounter(fps=float(np.clip(fps, 5.0, 120.0)), aspect=self.aspect)
        status = self.warming_status()
        for _, buffered in self.pending:
            status = self.counter.update(buffered)
        self.pending = []
        return status

    def reset(self) -> None:
        self.counter = None
        self.pending = []

    @property
    def fps(self) -> float | None:
        return self.counter.fps if self.counter else None

    @staticmethod
    def warming_status() -> dict:
        return {"exercise": "Detecting squat...", "rep_count": 0, "phase": "idle", "phase_display": "",
                "calibration_mode": "WARMING_UP", "source": "calibrated_squat_counter"}
