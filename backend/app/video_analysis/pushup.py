"""Push-up mode: rep counting and form-risk flags from pose landmarks.

Same approach as the squat engine (``analyzer.py``): one joint angle drives a
hysteresis rep counter with thresholds calibrated from the session itself,
gates reject movements that only look like the rep, and every flag comes from
a landmark measurement. Built for a side view with the whole body in frame.

- Rep signal: elbow angle (shoulder-elbow-wrist) on the side facing the camera.
- Gates: the body is roughly horizontal (a plank, not standing arm curls),
  the shoulders actually lower toward the floor, and the hands stay planted.
- Flags: SHALLOW_PUSHUP, HIPS_SAGGING, HIPS_PIKING, DEPTH_INCONSISTENT,
  FAST_DESCENT. Thresholds are coaching choices, not validated cut-offs.

Outputs are rep counts and form-risk flags only - not a diagnosis.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np

from .analyzer import AnalysisConfig, Point, angle, calibrate_thresholds

SIDE_KEYS = ("shoulder", "elbow", "wrist", "hip", "ankle")

KNOWN_LIMITS = [
    "Push-up mode is built for a side view with the whole body in frame; other views are not validated.",
    "Push-up thresholds were tested on synthetic landmark sequences only; no recorded push-up clip has been checked yet.",
    "Elbow and body-line angles are 2D image-plane angles, not 3D joint angles.",
]


@dataclass(frozen=True)
class PushupConfig:
    min_visibility: float = 0.55
    smoothing_seconds: float = 0.2
    min_rep_seconds: float = 0.4
    max_rep_seconds: float = 8.0
    # Calibration (reuses the squat engine's percentile calibration on elbow angles).
    calibration_min_samples: int = 15
    min_motion_deg: float = 35.0
    bottom_limits_deg: tuple[float, float] = (60.0, 130.0)
    top_limits_deg: tuple[float, float] = (135.0, 175.0)
    # Gates.
    max_body_tilt_deg: float = 40.0        # shoulder-ankle line vs horizontal
    min_shoulder_drop_fraction: float = 0.12  # of arm length
    max_wrist_shift_fraction: float = 0.35    # of arm length
    reference_seconds: float = 0.3
    # Flags.
    shallow_elbow_deg: float = 110.0
    body_line_min_deg: float = 160.0       # shoulder-hip-ankle; 180 is a straight line
    depth_drift_deg: float = 15.0
    depth_reference_reps: int = 3
    fast_descent_seconds: float = 0.2

    def calibration(self) -> AnalysisConfig:
        """The squat calibration's fields, pointed at elbow-angle ranges."""
        return AnalysisConfig(
            calibration_min_samples=self.calibration_min_samples,
            min_squat_rom_deg=self.min_motion_deg,
            bottom_limits_deg=self.bottom_limits_deg,
            standing_limits_deg=self.top_limits_deg,
            bottom_knee_deg=90.0,
            standing_knee_deg=155.0,
        )


def _pick_side(points: Mapping[str, Point], min_visibility: float) -> str | None:
    """The body side facing the camera: all five points visible, best mean visibility."""
    best, best_vis = None, -1.0
    for side in ("left", "right"):
        names = [f"{side}_{key}" for key in SIDE_KEYS]
        if not all(name in points and points[name][2] >= min_visibility for name in names):
            continue
        vis = sum(points[name][2] for name in names) / len(names)
        if vis > best_vis:
            best, best_vis = side, vis
    return best


def pushup_metrics(points: Mapping[str, Point], min_visibility: float, aspect: float = 1.0) -> dict | None:
    """Per-frame push-up measurements, or None when one side is not fully visible.

    ``aspect`` (width / height) turns normalized x into frame-height units so
    tilt and distances are not squashed by a wide frame.
    """
    side = _pick_side(points, min_visibility)
    if side is None:
        return None

    def p(key: str) -> tuple[float, float, float]:
        x, y, v = points[f"{side}_{key}"]
        return (x * aspect, y, v)

    sh, el, wr, hip, an = (p(k) for k in SIDE_KEYS)
    body_line = angle(sh, hip, an)
    # Signed distance of the hip from the shoulder-ankle line; image y grows
    # downward, so positive = hip below the line (sagging), negative = above (piking).
    dx, dy = an[0] - sh[0], an[1] - sh[1]
    length = math.hypot(dx, dy) or 1e-6
    cross = (hip[0] - sh[0]) * dy - (hip[1] - sh[1]) * dx
    # Orient so "below" is positive whichever way the lifter faces.
    offset = -cross / length if dx >= 0 else cross / length
    return {
        "side": side,
        "elbow_angle": round(angle(sh, el, wr), 2),
        "body_line": round(body_line, 2),
        "hip_offset": round(offset / length, 4),
        "body_tilt": round(math.degrees(math.atan2(abs(dy), abs(dx) or 1e-6)), 2),
        "shoulder_y": round(sh[1], 5),
        "arm_length": round(math.dist(sh[:2], el[:2]) + math.dist(el[:2], wr[:2]), 5),
        "wrist_xy": (round(wr[0], 5), round(wr[1], 5)),
    }


class PushupStateMachine:
    """Top -> bottom -> top hysteresis on the smoothed elbow angle."""

    def __init__(self, fps: float, config: PushupConfig, history_limit: int | None = None) -> None:
        self.fps, self.config = fps, config
        self.history_limit = history_limit
        self.reference_frames = max(1, int(fps * config.reference_seconds))
        self.log = {"rejected_not_plank": 0, "rejected_no_shoulder_drop": 0, "rejected_hands_moved": 0,
                    "rejected_rom_or_duration": 0}
        self.reps: list[dict] = []
        self.reset_phase()

    def reset_phase(self) -> None:
        self.state, self.start_frame = "top", 0
        self.current: list[dict] = []
        self.since_top: list[dict] = []
        self.descent_seconds: float | None = None

    def push(self, frame_index: int, metrics: dict, elbow: float, thresholds: dict) -> dict | None:
        top_deg, bottom_deg = thresholds["standing_knee_deg"], thresholds["bottom_knee_deg"]
        self.current.append(metrics)
        if self.state == "top":
            self.since_top.append(metrics)
            if self.history_limit and len(self.since_top) > self.history_limit:
                del self.since_top[: len(self.since_top) - self.history_limit]
            if elbow <= bottom_deg:
                self.descent_seconds = self._descent_seconds(top_deg)
                self.state, self.start_frame, self.current = "bottom", frame_index, [metrics]
            return None
        if elbow < top_deg:
            return None
        rep = self._finish(frame_index, thresholds)
        self.state, self.current, self.since_top = "top", [], [metrics]
        return rep

    def _descent_seconds(self, top_deg: float) -> float | None:
        for back, m in enumerate(reversed(self.since_top[:-1]), start=1):
            if m["elbow_angle"] >= top_deg:
                return back / self.fps
        return None

    def _finish(self, frame_index: int, thresholds: dict) -> dict | None:
        config, current = self.config, self.current
        duration = (frame_index - self.start_frame) / self.fps
        elbows = [m["elbow_angle"] for m in current]
        min_elbow, max_elbow = min(elbows), max(elbows)
        rom = max_elbow - min_elbow
        before = [m for m in self.since_top if m["elbow_angle"] >= thresholds["standing_knee_deg"]]
        before = before[-self.reference_frames:] or self.since_top[: self.reference_frames]
        arm = float(np.median([m["arm_length"] for m in (*before, *current)])) or 1e-6
        evidence = {
            "max_body_tilt_deg": round(max(m["body_tilt"] for m in current), 1),
            "shoulder_drop_ratio": None,
            "wrist_shift_ratio": None,
        }
        top_shoulder = float(np.median([m["shoulder_y"] for m in before]))
        evidence["shoulder_drop_ratio"] = round((max(m["shoulder_y"] for m in current) - top_shoulder) / arm, 3)
        rx = float(np.median([m["wrist_xy"][0] for m in before]))
        ry = float(np.median([m["wrist_xy"][1] for m in before]))
        evidence["wrist_shift_ratio"] = round(
            max(math.hypot(m["wrist_xy"][0] - rx, m["wrist_xy"][1] - ry) for m in current) / arm, 3)
        reason = None
        if not (config.min_rep_seconds <= duration <= config.max_rep_seconds and rom >= thresholds["min_rep_rom_deg"]):
            reason = "rom_or_duration"
        elif float(np.median([m["body_tilt"] for m in current])) > config.max_body_tilt_deg:
            reason = "not_plank"
        elif evidence["wrist_shift_ratio"] > config.max_wrist_shift_fraction:
            reason = "hands_moved"
        elif evidence["shoulder_drop_ratio"] < config.min_shoulder_drop_fraction:
            reason = "no_shoulder_drop"
        if reason:
            self.log[f"rejected_{reason}"] += 1
            return None
        flags, coaching = pushup_flags(current, min_elbow, self.reps, self.descent_seconds, config)
        rep = {
            "rep": len(self.reps) + 1,
            "movement": "pushup",
            "start_seconds": round(self.start_frame / self.fps, 3),
            "end_seconds": round(frame_index / self.fps, 3),
            "duration_seconds": round(duration, 3),
            "min_elbow_angle": round(min_elbow, 1),
            "rom_degrees": round(rom, 1),
            "form_flags": flags,
            **evidence,
            **coaching,
        }
        self.reps.append(rep)
        return rep


def pushup_flags(current: Sequence[dict], min_elbow: float, earlier_reps: Sequence[dict],
                 descent_seconds: float | None, config: PushupConfig) -> tuple[list[str], dict]:
    """Form-risk flags for one counted push-up. Returns (flags, evidence).

    - SHALLOW_PUSHUP: the elbow never bends past ``shallow_elbow_deg``.
    - HIPS_SAGGING / HIPS_PIKING: for at least a quarter of the rep the body
      line (shoulder-hip-ankle) is bent more than 180 - ``body_line_min_deg``
      with the hip below / above the shoulder-ankle line.
    - DEPTH_INCONSISTENT: > ``depth_drift_deg`` shallower than the median of
      the earlier reps (after ``depth_reference_reps``); skipped when already
      SHALLOW_PUSHUP.
    - FAST_DESCENT: top to bottom threshold in under ``fast_descent_seconds``.
    """
    flags: list[str] = []
    if min_elbow > config.shallow_elbow_deg:
        flags.append("SHALLOW_PUSHUP")
    lines = np.array([m["body_line"] for m in current])
    offsets = np.array([m["hip_offset"] for m in current])
    bent = lines < config.body_line_min_deg
    sag_share = float(np.mean(bent & (offsets > 0)))
    pike_share = float(np.mean(bent & (offsets < 0)))
    if sag_share >= 0.25:
        flags.append("HIPS_SAGGING")
    elif pike_share >= 0.25:
        flags.append("HIPS_PIKING")
    evidence = {"min_body_line_deg": round(float(lines.min()), 1), "descent_seconds": None,
                "depth_vs_usual_deg": None}
    depths = [r["min_elbow_angle"] for r in earlier_reps]
    if len(depths) >= config.depth_reference_reps:
        drift = min_elbow - float(np.median(depths))
        evidence["depth_vs_usual_deg"] = round(drift, 1)
        if drift > config.depth_drift_deg and "SHALLOW_PUSHUP" not in flags:
            flags.append("DEPTH_INCONSISTENT")
    if descent_seconds is not None:
        evidence["descent_seconds"] = round(descent_seconds, 3)
        if descent_seconds < config.fast_descent_seconds:
            flags.append("FAST_DESCENT")
    return flags, evidence


def calibrate_pushup(elbow_angles: Sequence[float], config: PushupConfig) -> dict:
    result = calibrate_thresholds(elbow_angles, config.calibration())
    if result.get("reason"):
        result["reason"] = result["reason"].replace("knee angle", "elbow angle").replace("squat minimum", "push-up minimum")
    return result


class LivePushupCounter:
    """Streaming push-up counter with the same shape as ``LiveSquatCounter``.

    Trailing-median smoothing, rolling-window calibration refreshed about once a
    second, and a replay of buffered frames when motion first becomes countable.
    """

    movement = "pushup"
    label = "Push-up"

    def __init__(self, fps: float = 25.0, config: PushupConfig | None = None, aspect: float = 16 / 9,
                 window_seconds: float = 30.0, recalibrate_seconds: float = 1.0) -> None:
        from collections import deque

        self.fps, self.aspect = fps, aspect
        self.config = config or PushupConfig()
        self.window: deque = deque(maxlen=max(1, int(window_seconds * fps)))
        self.recent: deque = deque(maxlen=max(1, int(fps * self.config.smoothing_seconds) | 1))
        self.recalibrate_every = max(1, int(recalibrate_seconds * fps))
        self.machine = PushupStateMachine(fps, self.config, history_limit=int(10 * fps))
        self.thresholds: dict = {"mode": "WARMING_UP"}
        self.frame_index = self.valid_frames = 0
        self.calibrated_once = False
        self.last_metrics: dict | None = None
        self.last_pushed = -1

    def update(self, points: Mapping[str, Point] | None) -> dict:
        index = self.frame_index
        self.frame_index += 1
        metrics = pushup_metrics(points, self.config.min_visibility, self.aspect) if points else None
        self.last_metrics = metrics
        if metrics is None:
            return self.status()
        self.valid_frames += 1
        self.recent.append(metrics["elbow_angle"])
        elbow = float(np.median(self.recent))
        self.window.append((index, metrics, elbow))
        if self.valid_frames % self.recalibrate_every == 0:
            self._recalibrate()
        if self.thresholds.get("mode") == "CALIBRATED":
            self._push(index, metrics, elbow)
        return self.status()

    def _recalibrate(self) -> None:
        thresholds = calibrate_pushup([m["elbow_angle"] for _, m, _ in self.window], self.config)
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
            for index, m, elbow in list(self.window)[:-1]:
                if index > self.last_pushed:
                    self._push(index, m, elbow)

    def _push(self, index: int, metrics: dict, elbow: float) -> None:
        self.machine.push(index, metrics, elbow, self.thresholds)
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
            "exercise": self.label if self.machine.reps else "Detecting push-up...",
            "rep_count": self.rep_count,
            "phase": phase if counting else "idle",
            "phase_display": ("\u2193" if phase == "down" else "\u2191") if counting else "",
            "calibration_mode": mode,
            "bottom_elbow_deg": self.thresholds.get("bottom_knee_deg"),
            "top_elbow_deg": self.thresholds.get("standing_knee_deg"),
            "elbow_angle": self.last_metrics["elbow_angle"] if self.last_metrics else None,
            "last_rep": dict(last) if last else None,
            "rep_gates": dict(self.machine.log),
            "source": "calibrated_pushup_counter",
        }
