"""Lunge mode: rep counting and form-risk flags from pose landmarks.

Same approach as the squat and push-up engines: one joint angle drives a
hysteresis rep counter with thresholds calibrated from the session itself,
gates reject movements that only look like the rep, and every flag comes from
a landmark measurement. Built for a side view of a stationary lunge (split
squat): the feet stay where they are and the hips go down and up.

- Rep signal: front knee angle (hip-knee-ankle). The front leg is the one with
  the more upright shin, which holds at the top and the bottom of a lunge.
- Gates: the feet are split front to back (a squat has them side by side), both
  feet stay put during the rep, and the hips actually drop.
- Flags: SHALLOW_LUNGE, FORWARD_LEAN, KNEE_PAST_TOES, DEPTH_INCONSISTENT,
  FAST_DESCENT. Thresholds are coaching choices, not validated cut-offs.
  KNEE_PAST_TOES reports a measured distance only; a knee in front of the
  toes is not treated as unsafe.

Outputs are rep counts and form-risk flags only - not a diagnosis.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np

from .analyzer import AnalysisConfig, Point, angle, calibrate_thresholds

LEG_KEYS = ("hip", "knee", "ankle")

KNOWN_LIMITS = [
    "Lunge mode is built for a side view of a stationary lunge (split squat); stepping or walking lunges are not counted yet.",
    "Lunge thresholds were tested on synthetic landmark sequences only; no recorded lunge clip has been checked yet.",
    "Knee, trunk and knee-to-toe measurements are 2D image-plane values, not 3D joint angles.",
]


@dataclass(frozen=True)
class LungeConfig:
    min_visibility: float = 0.55       # near-side shoulder and hip
    leg_min_visibility: float = 0.3    # both legs; the far leg is partly hidden in a side view
    smoothing_seconds: float = 0.2
    min_rep_seconds: float = 0.4
    max_rep_seconds: float = 8.0
    # Calibration (reuses the squat engine's percentile calibration on front-knee angles).
    calibration_min_samples: int = 15
    min_motion_deg: float = 35.0
    bottom_limits_deg: tuple[float, float] = (60.0, 130.0)
    top_limits_deg: tuple[float, float] = (135.0, 175.0)
    # Gates (distances are fractions of the front leg length, hip-knee + knee-ankle).
    min_split_fraction: float = 0.3
    max_foot_shift_fraction: float = 0.25
    min_hip_drop_fraction: float = 0.12
    reference_seconds: float = 0.3
    # Flags.
    shallow_knee_deg: float = 110.0
    forward_lean_deg: float = 30.0     # shoulder-hip line vs vertical
    knee_past_toes_fraction: float = 0.1
    depth_drift_deg: float = 15.0
    depth_reference_reps: int = 3
    fast_descent_seconds: float = 0.2

    def calibration(self) -> AnalysisConfig:
        """The squat calibration's fields, pointed at front-knee ranges."""
        return AnalysisConfig(
            calibration_min_samples=self.calibration_min_samples,
            min_squat_rom_deg=self.min_motion_deg,
            bottom_limits_deg=self.bottom_limits_deg,
            standing_limits_deg=self.top_limits_deg,
            bottom_knee_deg=95.0,
            standing_knee_deg=155.0,
        )


def _visible(points: Mapping[str, Point], name: str, threshold: float) -> bool:
    return name in points and points[name][2] >= threshold


def lunge_metrics(points: Mapping[str, Point], config: LungeConfig, aspect: float = 1.0) -> dict | None:
    """Per-frame lunge measurements, or None when the legs or trunk are not visible.

    ``aspect`` (width / height) turns normalized x into frame-height units so
    distances and angles are not squashed by a wide frame.
    """
    legs = [f"{side}_{key}" for side in ("left", "right") for key in LEG_KEYS]
    if not all(_visible(points, name, config.leg_min_visibility) for name in legs):
        return None
    trunk_sides = [s for s in ("left", "right")
                   if _visible(points, f"{s}_shoulder", config.min_visibility)
                   and _visible(points, f"{s}_hip", config.min_visibility)]
    if not trunk_sides:
        return None

    def p(name: str) -> tuple[float, float]:
        x, y, _ = points[name]
        return (x * aspect, y)

    def shin_tilt(side: str) -> float:
        kx, ky = p(f"{side}_knee")
        ax, ay = p(f"{side}_ankle")
        return math.degrees(math.atan2(abs(kx - ax), abs(ay - ky) or 1e-6))

    front = min(("left", "right"), key=shin_tilt)
    back = "right" if front == "left" else "left"
    hip, knee, ankle = (p(f"{front}_{k}") for k in LEG_KEYS)
    back_hip, back_knee, back_ankle = (p(f"{back}_{k}") for k in LEG_KEYS)
    leg = math.dist(hip, knee) + math.dist(knee, ankle) or 1e-6
    facing = 1.0 if ankle[0] >= back_ankle[0] else -1.0
    toe_name = f"{front}_foot_index"
    toe = p(toe_name) if _visible(points, toe_name, config.leg_min_visibility) else ankle
    sh = np.mean([p(f"{s}_shoulder") for s in trunk_sides], axis=0)
    hp = np.mean([p(f"{s}_hip") for s in trunk_sides], axis=0)
    return {
        "front_side": front,
        "knee_angle": round(angle(hip, knee, ankle), 2),
        "back_knee_angle": round(angle(back_hip, back_knee, back_ankle), 2),
        "split_ratio": round(abs(ankle[0] - back_ankle[0]) / leg, 4),
        "knee_ahead_ratio": round((knee[0] - toe[0]) * facing / leg, 4),
        "trunk_lean": round(math.degrees(math.atan2(abs(sh[0] - hp[0]), abs(hp[1] - sh[1]) or 1e-6)), 2),
        "hip_y": round((hip[1] + back_hip[1]) / 2, 5),
        "leg_length": round(leg, 5),
        "front_ankle_xy": (round(ankle[0], 5), round(ankle[1], 5)),
        "back_ankle_xy": (round(back_ankle[0], 5), round(back_ankle[1], 5)),
    }


class LungeStateMachine:
    """Top -> bottom -> top hysteresis on the smoothed front-knee angle."""

    def __init__(self, fps: float, config: LungeConfig, history_limit: int | None = None) -> None:
        self.fps, self.config = fps, config
        self.history_limit = history_limit
        self.reference_frames = max(1, int(fps * config.reference_seconds))
        self.log = {"rejected_no_split_stance": 0, "rejected_feet_moved": 0, "rejected_no_hip_drop": 0,
                    "rejected_rom_or_duration": 0}
        self.reps: list[dict] = []
        self.reset_phase()

    def reset_phase(self) -> None:
        self.state, self.start_frame = "top", 0
        self.current: list[dict] = []
        self.since_top: list[dict] = []
        self.descent_seconds: float | None = None

    def push(self, frame_index: int, metrics: dict, knee: float, thresholds: dict) -> dict | None:
        top_deg, bottom_deg = thresholds["standing_knee_deg"], thresholds["bottom_knee_deg"]
        self.current.append(metrics)
        if self.state == "top":
            self.since_top.append(metrics)
            if self.history_limit and len(self.since_top) > self.history_limit:
                del self.since_top[: len(self.since_top) - self.history_limit]
            if knee <= bottom_deg:
                self.descent_seconds = self._descent_seconds(top_deg)
                self.state, self.start_frame, self.current = "bottom", frame_index, [metrics]
            return None
        if knee < top_deg:
            return None
        rep = self._finish(frame_index, thresholds)
        self.state, self.current, self.since_top = "top", [], [metrics]
        return rep

    def _descent_seconds(self, top_deg: float) -> float | None:
        for back, m in enumerate(reversed(self.since_top[:-1]), start=1):
            if m["knee_angle"] >= top_deg:
                return back / self.fps
        return None

    def _finish(self, frame_index: int, thresholds: dict) -> dict | None:
        config, current = self.config, self.current
        duration = (frame_index - self.start_frame) / self.fps
        knees = [m["knee_angle"] for m in current]
        min_knee, max_knee = min(knees), max(knees)
        rom = max_knee - min_knee
        before = [m for m in self.since_top if m["knee_angle"] >= thresholds["standing_knee_deg"]]
        before = before[-self.reference_frames:] or self.since_top[: self.reference_frames]
        leg = float(np.median([m["leg_length"] for m in (*before, *current)])) or 1e-6

        def shift(key: str) -> float:
            rx = float(np.median([m[key][0] for m in before]))
            ry = float(np.median([m[key][1] for m in before]))
            # Over the whole rep, from leaving the top: a foot can slide on the way down.
            return max(math.hypot(m[key][0] - rx, m[key][1] - ry) for m in (*self.since_top, *current)) / leg

        top_hip = float(np.median([m["hip_y"] for m in before]))
        evidence = {
            "split_ratio": round(float(np.median([m["split_ratio"] for m in current])), 3),
            "foot_shift_ratio": round(max(shift("front_ankle_xy"), shift("back_ankle_xy")), 3),
            "hip_drop_ratio": round((max(m["hip_y"] for m in current) - top_hip) / leg, 3),
        }
        reason = None
        if not (config.min_rep_seconds <= duration <= config.max_rep_seconds and rom >= thresholds["min_rep_rom_deg"]):
            reason = "rom_or_duration"
        elif evidence["split_ratio"] < config.min_split_fraction:
            reason = "no_split_stance"
        elif evidence["foot_shift_ratio"] > config.max_foot_shift_fraction:
            reason = "feet_moved"
        elif evidence["hip_drop_ratio"] < config.min_hip_drop_fraction:
            reason = "no_hip_drop"
        if reason:
            self.log[f"rejected_{reason}"] += 1
            return None
        flags, coaching = lunge_flags(current, min_knee, self.reps, self.descent_seconds, config)
        rep = {
            "rep": len(self.reps) + 1,
            "movement": "lunge",
            "front_leg": max(("left", "right"), key=[m["front_side"] for m in current].count),
            "start_seconds": round(self.start_frame / self.fps, 3),
            "end_seconds": round(frame_index / self.fps, 3),
            "duration_seconds": round(duration, 3),
            "min_knee_angle": round(min_knee, 1),
            "rom_degrees": round(rom, 1),
            "form_flags": flags,
            **evidence,
            **coaching,
        }
        self.reps.append(rep)
        return rep


def lunge_flags(current: Sequence[dict], min_knee: float, earlier_reps: Sequence[dict],
                descent_seconds: float | None, config: LungeConfig) -> tuple[list[str], dict]:
    """Form-risk flags for one counted lunge. Returns (flags, evidence).

    - SHALLOW_LUNGE: the front knee never bends past ``shallow_knee_deg``.
    - FORWARD_LEAN: the shoulder-hip line leans more than ``forward_lean_deg``
      from vertical for at least a quarter of the rep.
    - KNEE_PAST_TOES: at its furthest the front knee is more than
      ``knee_past_toes_fraction`` of leg length in front of the toes (the
      ankle when the toes are not visible). A measured distance, not a safety limit.
    - DEPTH_INCONSISTENT: > ``depth_drift_deg`` shallower than the median of
      the earlier reps (after ``depth_reference_reps``); skipped when already
      SHALLOW_LUNGE.
    - FAST_DESCENT: top to bottom threshold in under ``fast_descent_seconds``.
    """
    flags: list[str] = []
    if min_knee > config.shallow_knee_deg:
        flags.append("SHALLOW_LUNGE")
    leans = np.array([m["trunk_lean"] for m in current])
    if float(np.mean(leans > config.forward_lean_deg)) >= 0.25:
        flags.append("FORWARD_LEAN")
    knee_ahead = max(m["knee_ahead_ratio"] for m in current)
    if knee_ahead > config.knee_past_toes_fraction:
        flags.append("KNEE_PAST_TOES")
    evidence = {"max_trunk_lean_deg": round(float(leans.max()), 1),
                "knee_ahead_of_toes_ratio": round(knee_ahead, 3),
                "descent_seconds": None, "depth_vs_usual_deg": None}
    depths = [r["min_knee_angle"] for r in earlier_reps]
    if len(depths) >= config.depth_reference_reps:
        drift = min_knee - float(np.median(depths))
        evidence["depth_vs_usual_deg"] = round(drift, 1)
        if drift > config.depth_drift_deg and "SHALLOW_LUNGE" not in flags:
            flags.append("DEPTH_INCONSISTENT")
    if descent_seconds is not None:
        evidence["descent_seconds"] = round(descent_seconds, 3)
        if descent_seconds < config.fast_descent_seconds:
            flags.append("FAST_DESCENT")
    return flags, evidence


def calibrate_lunge(knee_angles: Sequence[float], config: LungeConfig) -> dict:
    result = calibrate_thresholds(knee_angles, config.calibration())
    if result.get("reason"):
        result["reason"] = result["reason"].replace("knee angle", "front knee angle").replace("squat minimum", "lunge minimum")
    return result


class LiveLungeCounter:
    """Streaming lunge counter with the same shape as ``LiveSquatCounter``.

    Trailing-median smoothing, rolling-window calibration refreshed about once a
    second, and a replay of buffered frames when motion first becomes countable.
    """

    movement = "lunge"
    label = "Lunge"

    def __init__(self, fps: float = 25.0, config: LungeConfig | None = None, aspect: float = 16 / 9,
                 window_seconds: float = 30.0, recalibrate_seconds: float = 1.0) -> None:
        from collections import deque

        self.fps, self.aspect = fps, aspect
        self.config = config or LungeConfig()
        self.window: deque = deque(maxlen=max(1, int(window_seconds * fps)))
        self.recent: deque = deque(maxlen=max(1, int(fps * self.config.smoothing_seconds) | 1))
        self.recalibrate_every = max(1, int(recalibrate_seconds * fps))
        self.machine = LungeStateMachine(fps, self.config, history_limit=int(10 * fps))
        self.thresholds: dict = {"mode": "WARMING_UP"}
        self.frame_index = self.valid_frames = 0
        self.calibrated_once = False
        self.last_metrics: dict | None = None
        self.last_pushed = -1

    def update(self, points: Mapping[str, Point] | None) -> dict:
        index = self.frame_index
        self.frame_index += 1
        metrics = lunge_metrics(points, self.config, self.aspect) if points else None
        self.last_metrics = metrics
        if metrics is None:
            return self.status()
        self.valid_frames += 1
        self.recent.append(metrics["knee_angle"])
        knee = float(np.median(self.recent))
        self.window.append((index, metrics, knee))
        if self.valid_frames % self.recalibrate_every == 0:
            self._recalibrate()
        if self.thresholds.get("mode") == "CALIBRATED":
            self._push(index, metrics, knee)
        return self.status()

    def _recalibrate(self) -> None:
        thresholds = calibrate_lunge([m["knee_angle"] for _, m, _ in self.window], self.config)
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
            for index, m, knee in list(self.window)[:-1]:
                if index > self.last_pushed:
                    self._push(index, m, knee)

    def _push(self, index: int, metrics: dict, knee: float) -> None:
        self.machine.push(index, metrics, knee, self.thresholds)
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
            "exercise": self.label if self.machine.reps else "Detecting lunge...",
            "rep_count": self.rep_count,
            "phase": phase if counting else "idle",
            "phase_display": ("\u2193" if phase == "down" else "\u2191") if counting else "",
            "calibration_mode": mode,
            "bottom_knee_deg": self.thresholds.get("bottom_knee_deg"),
            "standing_knee_deg": self.thresholds.get("standing_knee_deg"),
            "knee_angle": self.last_metrics["knee_angle"] if self.last_metrics else None,
            "last_rep": dict(last) if last else None,
            "rep_gates": dict(self.machine.log),
            "source": "calibrated_lunge_counter",
        }
