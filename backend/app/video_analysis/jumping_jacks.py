"""Jumping-jacks mode: rep counting and form-risk flags from pose landmarks.

Same approach as the other modes: one angle drives a hysteresis rep counter
with thresholds calibrated from the session itself, gates reject movements
that only look like the rep, and every flag comes from a landmark
measurement. Built for a front view with the whole body in frame.

- Rep signal: arm abduction (hip-shoulder-wrist angle, both arms averaged).
  The counter runs on 180 minus that angle so the shared calibration sees
  "arms down" as the high end, like standing in a squat.
- Gates: both arms go up together, and the feet actually jump apart (arm
  raises alone are not jumping jacks).
- Flags: ARMS_NOT_OVERHEAD, FEET_NOT_APART, TEMPO_DRIFT. No depth rules.
  Thresholds are coaching choices, not validated cut-offs.

Outputs are rep counts and form-risk flags only - not a diagnosis.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np

from .analyzer import AnalysisConfig, Point, angle, calibrate_thresholds

KEYS = ("shoulder", "wrist", "hip", "ankle")

KNOWN_LIMITS = [
    "Jumping-jacks mode is built for a front view with the whole body in frame; side views are not validated.",
    "Jumping-jacks thresholds were tested on synthetic landmark sequences only; no recorded clip has been checked yet.",
    "Arm angles and foot spacing are 2D image-plane values.",
]


@dataclass(frozen=True)
class JacksConfig:
    min_visibility: float = 0.5
    smoothing_seconds: float = 0.12
    min_rep_seconds: float = 0.15      # arms-open phase
    max_rep_seconds: float = 4.0
    calibration_min_samples: int = 15
    min_motion_deg: float = 60.0
    bottom_limits_deg: tuple[float, float] = (10.0, 90.0)    # 180 - arm angle, arms up
    top_limits_deg: tuple[float, float] = (100.0, 175.0)     # arms down
    # Gates.
    max_arm_mismatch_deg: float = 45.0
    min_feet_open_hip_widths: float = 0.4   # ankle gap must grow by this much
    reference_seconds: float = 0.2
    # Flags.
    overhead_arm_deg: float = 150.0
    feet_apart_hip_widths: float = 1.8
    tempo_drift_ratio: float = 1.5
    tempo_reference_reps: int = 3

    def calibration(self) -> AnalysisConfig:
        return AnalysisConfig(
            calibration_min_samples=self.calibration_min_samples,
            min_squat_rom_deg=self.min_motion_deg,
            bottom_limits_deg=self.bottom_limits_deg,
            standing_limits_deg=self.top_limits_deg,
            bottom_knee_deg=60.0,
            standing_knee_deg=140.0,
        )


def jacks_metrics(points: Mapping[str, Point], config: JacksConfig, aspect: float = 1.0) -> dict | None:
    """Per-frame measurements, or None unless both sides' shoulder, wrist, hip and ankle are visible."""
    names = [f"{side}_{key}" for side in ("left", "right") for key in KEYS]
    if not all(n in points and points[n][2] >= config.min_visibility for n in names):
        return None

    def p(name: str) -> tuple[float, float]:
        x, y, _ = points[name]
        return (x * aspect, y)

    arms = {s: angle(p(f"{s}_hip"), p(f"{s}_shoulder"), p(f"{s}_wrist")) for s in ("left", "right")}
    hip_width = math.dist(p("left_hip"), p("right_hip")) or 1e-6
    arm = (arms["left"] + arms["right"]) / 2
    return {
        "arm_angle": round(arm, 2),
        "arm_signal": round(180.0 - arm, 2),
        "left_arm": round(arms["left"], 2),
        "right_arm": round(arms["right"], 2),
        "ankle_gap": round(abs(p("left_ankle")[0] - p("right_ankle")[0]) / hip_width, 4),
    }


class JacksStateMachine:
    """Arms down -> arms up -> arms down hysteresis on the smoothed arm signal."""

    def __init__(self, fps: float, config: JacksConfig, history_limit: int | None = None) -> None:
        self.fps, self.config = fps, config
        self.history_limit = history_limit
        self.reference_frames = max(1, int(fps * config.reference_seconds))
        self.log = {"rejected_arms_uneven": 0, "rejected_feet_did_not_open": 0, "rejected_rom_or_duration": 0}
        self.reps: list[dict] = []
        self.last_end: int | None = None
        self.reset_phase()

    def reset_phase(self) -> None:
        self.state, self.start_frame = "top", 0
        self.current: list[dict] = []
        self.since_top: list[dict] = []

    def push(self, frame_index: int, metrics: dict, signal: float, thresholds: dict) -> dict | None:
        top_deg, bottom_deg = thresholds["standing_knee_deg"], thresholds["bottom_knee_deg"]
        self.current.append(metrics)
        if self.state == "top":
            self.since_top.append(metrics)
            if self.history_limit and len(self.since_top) > self.history_limit:
                del self.since_top[: len(self.since_top) - self.history_limit]
            if signal <= bottom_deg:
                self.state, self.start_frame, self.current = "bottom", frame_index, [metrics]
            return None
        if signal < top_deg:
            return None
        rep = self._finish(frame_index, thresholds)
        self.state, self.current, self.since_top = "top", [], [metrics]
        return rep

    def _finish(self, frame_index: int, thresholds: dict) -> dict | None:
        config, current = self.config, self.current
        duration = (frame_index - self.start_frame) / self.fps
        signals = [m["arm_signal"] for m in current]
        rom = max(signals) - min(signals)
        before = [m for m in self.since_top if m["arm_signal"] >= thresholds["standing_knee_deg"]]
        before = before[-self.reference_frames:] or self.since_top[: self.reference_frames]
        peak = max(current, key=lambda m: m["arm_angle"])
        rest_gap = float(np.median([m["ankle_gap"] for m in before]))
        max_gap = max(m["ankle_gap"] for m in current)
        evidence = {
            "arm_mismatch_deg": round(abs(peak["left_arm"] - peak["right_arm"]), 1),
            "feet_open_hip_widths": round(max_gap - rest_gap, 3),
        }
        reason = None
        if not (config.min_rep_seconds <= duration <= config.max_rep_seconds and rom >= thresholds["min_rep_rom_deg"]):
            reason = "rom_or_duration"
        elif evidence["arm_mismatch_deg"] > config.max_arm_mismatch_deg:
            reason = "arms_uneven"
        elif evidence["feet_open_hip_widths"] < config.min_feet_open_hip_widths:
            reason = "feet_did_not_open"
        if reason:
            self.log[f"rejected_{reason}"] += 1
            return None
        cycle = (frame_index - self.last_end) / self.fps if self.last_end is not None else None
        self.last_end = frame_index
        flags, coaching = jacks_flags(peak["arm_angle"], max_gap, cycle, self.reps, config)
        rep = {
            "rep": len(self.reps) + 1,
            "movement": "jumping_jacks",
            "start_seconds": round(self.start_frame / self.fps, 3),
            "end_seconds": round(frame_index / self.fps, 3),
            "duration_seconds": round(duration, 3),
            "cycle_seconds": round(cycle, 3) if cycle is not None else None,
            "max_arm_angle": round(peak["arm_angle"], 1),
            "max_ankle_gap_hip_widths": round(max_gap, 2),
            "rom_degrees": round(rom, 1),
            "form_flags": flags,
            **evidence,
            **coaching,
        }
        self.reps.append(rep)
        return rep


def jacks_flags(max_arm: float, max_gap: float, cycle: float | None, earlier_reps: Sequence[dict],
                config: JacksConfig) -> tuple[list[str], dict]:
    """Form-risk flags for one counted jumping jack. Returns (flags, evidence).

    - ARMS_NOT_OVERHEAD: the arms never open past ``overhead_arm_deg`` (hip-shoulder-wrist).
    - FEET_NOT_APART: the feet never get more than ``feet_apart_hip_widths`` hip widths apart.
    - TEMPO_DRIFT: this rep's cycle is ``tempo_drift_ratio`` times the median of the
      earlier reps' cycles (after ``tempo_reference_reps``).
    """
    flags: list[str] = []
    if max_arm < config.overhead_arm_deg:
        flags.append("ARMS_NOT_OVERHEAD")
    if max_gap < config.feet_apart_hip_widths:
        flags.append("FEET_NOT_APART")
    evidence = {"tempo_vs_usual": None}
    cycles = [r["cycle_seconds"] for r in earlier_reps if r.get("cycle_seconds")]
    if cycle is not None and len(cycles) >= config.tempo_reference_reps:
        ratio = cycle / float(np.median(cycles))
        evidence["tempo_vs_usual"] = round(ratio, 2)
        if ratio > config.tempo_drift_ratio:
            flags.append("TEMPO_DRIFT")
    return flags, evidence


def calibrate_jacks(signals: Sequence[float], config: JacksConfig) -> dict:
    result = calibrate_thresholds(signals, config.calibration())
    if result.get("reason"):
        result["reason"] = result["reason"].replace("knee angle", "arm angle").replace("squat minimum", "jumping-jack minimum")
    return result
class LiveJacksCounter:
    """Streaming jumping-jacks counter with the same shape as ``LiveSquatCounter``.

    Trailing-median smoothing, rolling-window calibration refreshed about once a
    second, and a replay of buffered frames when motion first becomes countable.
    """

    movement = "jumping_jacks"
    label = "Jumping jacks"

    def __init__(self, fps: float = 25.0, config: JacksConfig | None = None, aspect: float = 16 / 9,
                 window_seconds: float = 30.0, recalibrate_seconds: float = 1.0) -> None:
        from collections import deque

        self.fps, self.aspect = fps, aspect
        self.config = config or JacksConfig()
        self.window: deque = deque(maxlen=max(1, int(window_seconds * fps)))
        self.recent: deque = deque(maxlen=max(1, int(fps * self.config.smoothing_seconds) | 1))
        self.recalibrate_every = max(1, int(recalibrate_seconds * fps))
        self.machine = JacksStateMachine(fps, self.config, history_limit=int(10 * fps))
        self.thresholds: dict = {"mode": "WARMING_UP"}
        self.frame_index = self.valid_frames = 0
        self.calibrated_once = False
        self.last_metrics: dict | None = None
        self.last_pushed = -1

    def update(self, points: Mapping[str, Point] | None) -> dict:
        index = self.frame_index
        self.frame_index += 1
        metrics = jacks_metrics(points, self.config, self.aspect) if points else None
        self.last_metrics = metrics
        if metrics is None:
            return self.status()
        self.valid_frames += 1
        self.recent.append(metrics["arm_signal"])
        signal = float(np.median(self.recent))
        self.window.append((index, metrics, signal))
        if self.valid_frames % self.recalibrate_every == 0:
            self._recalibrate()
        if self.thresholds.get("mode") == "CALIBRATED":
            self._push(index, metrics, signal)
        return self.status()

    def _recalibrate(self) -> None:
        thresholds = calibrate_jacks([m["arm_signal"] for _, m, _ in self.window], self.config)
        was_counting = self.thresholds.get("mode") == "CALIBRATED"
        if thresholds["mode"] != "CALIBRATED":
            if self.machine.state == "bottom":
                return
            self.thresholds = ({**self.thresholds, "mode": "PAUSED", "reason": thresholds["reason"]}
                               if self.calibrated_once else thresholds)
            return
        self.thresholds, self.calibrated_once = thresholds, True
        if not was_counting:
            self.machine.reset_phase()
            for index, m, signal in list(self.window)[:-1]:
                if index > self.last_pushed:
                    self._push(index, m, signal)

    def _push(self, index: int, metrics: dict, signal: float) -> None:
        self.machine.push(index, metrics, signal, self.thresholds)
        self.last_pushed = index

    @property
    def rep_count(self) -> int:
        return len(self.machine.reps)

    def status(self) -> dict:
        mode = self.thresholds.get("mode", "WARMING_UP")
        counting = mode == "CALIBRATED"
        phase = "down" if self.machine.state == "bottom" else "up"
        last = self.machine.reps[-1] if self.machine.reps else None
        return {
            "movement": self.movement,
            "exercise": self.label if self.machine.reps else "Detecting jumping jacks...",
            "rep_count": self.rep_count,
            "phase": phase if counting else "idle",
            "phase_display": ("\u2193" if phase == "down" else "\u2191") if counting else "",
            "calibration_mode": mode,
            "arms_up_signal_deg": self.thresholds.get("bottom_knee_deg"),
            "arms_down_signal_deg": self.thresholds.get("standing_knee_deg"),
            "arm_angle": self.last_metrics["arm_angle"] if self.last_metrics else None,
            "last_rep": dict(last) if last else None,
            "rep_gates": dict(self.machine.log),
            "source": "calibrated_jacks_counter",
        }
