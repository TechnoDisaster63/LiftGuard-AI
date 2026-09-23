"""Offline, squat-only recorded-video analysis.

Outputs are explainable form-risk flags and a fatigue indicator. They are not a
medical diagnosis or an estimate of injury probability.
"""
from __future__ import annotations

import csv
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Mapping, Sequence

import cv2
import numpy as np

Point = tuple[float, float, float]
Landmarks = Mapping[str, Point]
Detector = Callable[[np.ndarray], Landmarks | None]

CONNECTIONS = (("shoulder", "hip"), ("hip", "knee"), ("knee", "ankle"))
MEASUREMENT_KEYS = ("shoulder", "hip", "knee", "ankle")

# MediaPipe Pose's 33 landmark names and its 35 skeleton connections
# (mirrors mp.solutions.pose.PoseLandmark / POSE_CONNECTIONS in 0.10.x) so the
# overlay can be drawn and tested without importing MediaPipe.
POSE_LANDMARK_NAMES = (
    "nose", "left_eye_inner", "left_eye", "left_eye_outer", "right_eye_inner",
    "right_eye", "right_eye_outer", "left_ear", "right_ear", "mouth_left",
    "mouth_right", "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
    "left_wrist", "right_wrist", "left_pinky", "right_pinky", "left_index",
    "right_index", "left_thumb", "right_thumb", "left_hip", "right_hip",
    "left_knee", "right_knee", "left_ankle", "right_ankle", "left_heel",
    "right_heel", "left_foot_index", "right_foot_index",
)
POSE_CONNECTIONS = (
    (0, 1), (0, 4), (1, 2), (2, 3), (3, 7), (4, 5), (5, 6), (6, 8), (9, 10),
    (11, 12), (11, 13), (11, 23), (12, 14), (12, 24), (13, 15), (14, 16),
    (15, 17), (15, 19), (15, 21), (16, 18), (16, 20), (16, 22), (17, 19),
    (18, 20), (23, 24), (23, 25), (24, 26), (25, 27), (26, 28), (27, 29),
    (27, 31), (28, 30), (28, 32), (29, 31), (30, 32),
)
SKELETON_MIN_VISIBILITY = 0.5

KNOWN_LIMITS = [
    "Built for one person in a recorded side view; other views are not validated.",
    "Camera cuts or zooms move every landmark at once: the hip-drop check can be fooled, "
    "and the feet check may reject a real rep that spans a cut.",
    "A squat-like dip done in place without the feet moving (e.g. a jump that lands in the same spot) "
    "can still pass the rep checks.",
    "Knee angles are 2D image-plane angles, not 3D joint angles.",
    "Coaching flags (knees caving, heels lifting, depth drift, fast descent) use simple thresholds that have "
    "not been validated against a coach's labels. Knees caving needs a front view; heels lifting needs a side "
    "view with the heel and toe visible. When the view or landmarks are missing, the flag is not checked.",
    "Back rounding is not checked: the pose model has no points along the spine, so only overall trunk lean "
    "is measured.",
]


@dataclass(frozen=True)
class AnalysisConfig:
    min_visibility: float = 0.55
    bottom_knee_deg: float = 105.0
    standing_knee_deg: float = 155.0
    min_rep_seconds: float = 0.45
    max_rep_seconds: float = 12.0
    baseline_reps: int = 3
    max_duration_seconds: float = 60.0
    max_frames: int = 3600
    # Per-session threshold calibration (see calibrate_thresholds).
    calibrate: bool = True
    smoothing_seconds: float = 0.2
    calibration_min_samples: int = 15
    min_squat_rom_deg: float = 35.0
    bottom_rom_fraction: float = 0.35
    standing_rom_fraction: float = 0.25
    bottom_limits_deg: tuple[float, float] = (70.0, 140.0)
    standing_limits_deg: tuple[float, float] = (140.0, 175.0)
    min_hysteresis_deg: float = 25.0
    min_rep_rom_fraction: float = 0.5
    # Leg gates (see count_reps): a squat bends both knees and lowers the hips.
    leg_gates: bool = True
    min_hip_drop_fraction: float = 0.15
    other_knee_margin_deg: float = 20.0
    max_ankle_shift_fraction: float = 0.25
    standing_reference_seconds: float = 0.3
    # Coaching flags beyond the core three (see _coaching_flags). Thresholds are
    # coaching choices, not validated cut-offs.
    coaching_flags: bool = True
    front_view_min_hip_width: float = 0.21
    knees_caving_max_ratio: float = 0.9
    heel_rise_fraction: float = 0.04
    depth_drift_deg: float = 15.0
    depth_reference_reps: int = 3
    fast_descent_seconds: float = 0.2


class MediaPipePoseDetector:
    """Lazy MediaPipe adapter so pure calculations remain light to test."""

    def __init__(self) -> None:
        import mediapipe as mp

        self._pose = mp.solutions.pose.Pose(
            static_image_mode=False,
            model_complexity=1,
            enable_segmentation=False,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self._indices = {
            "shoulder": mp.solutions.pose.PoseLandmark.LEFT_SHOULDER.value,
            "hip": mp.solutions.pose.PoseLandmark.LEFT_HIP.value,
            "knee": mp.solutions.pose.PoseLandmark.LEFT_KNEE.value,
            "ankle": mp.solutions.pose.PoseLandmark.LEFT_ANKLE.value,
        }

    def __call__(self, frame: np.ndarray) -> Landmarks | None:
        result = self._pose.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        if not result.pose_landmarks:
            return None
        points = result.pose_landmarks.landmark
        landmarks = {
            name: (points[idx].x, points[idx].y, points[idx].visibility)
            for idx, name in enumerate(POSE_LANDMARK_NAMES)
        }
        # Measurement aliases used by the side-view squat calculations.
        landmarks.update({
            name: (points[idx].x, points[idx].y, points[idx].visibility)
            for name, idx in self._indices.items()
        })
        return landmarks

    def close(self) -> None:
        self._pose.close()


def angle(a: Point, b: Point, c: Point) -> float:
    """Angle ABC in degrees, using image-plane coordinates."""
    ba = np.array(a[:2], dtype=float) - np.array(b[:2], dtype=float)
    bc = np.array(c[:2], dtype=float) - np.array(b[:2], dtype=float)
    denom = float(np.linalg.norm(ba) * np.linalg.norm(bc))
    if denom == 0:
        return 0.0
    cosine = float(np.clip(np.dot(ba, bc) / denom, -1.0, 1.0))
    return math.degrees(math.acos(cosine))


def _metrics(points: Landmarks, min_visibility: float) -> dict | None:
    required = ("shoulder", "hip", "knee", "ankle")
    if any(name not in points or points[name][2] < min_visibility for name in required):
        return None
    knee = angle(points["hip"], points["knee"], points["ankle"])
    trunk = angle((points["hip"][0], points["hip"][1] - 1, 1), points["hip"], points["shoulder"])
    metrics = {
        "knee_angle": round(knee, 2),
        "trunk_lean": round(trunk, 2),
        # Image y grows downward: a larger hip_y means lower hips.
        "hip_y": round(points["hip"][1], 5),
        "leg_extent": round(points["ankle"][1] - points["hip"][1], 5),
        "other_knee_angle": None,
        "ankle_xy": (round(points["ankle"][0], 5), round(points["ankle"][1], 5)),
        "other_ankle_xy": None,
    }
    other = ("right_hip", "right_knee", "right_ankle")
    if all(name in points and points[name][2] >= min_visibility for name in other):
        metrics["other_knee_angle"] = round(angle(points["right_hip"], points["right_knee"], points["right_ankle"]), 2)
        metrics["other_ankle_xy"] = (round(points["right_ankle"][0], 5), round(points["right_ankle"][1], 5))
    metrics.update(_coaching_metrics(points, min_visibility))
    return metrics


def _coaching_metrics(points: Landmarks, min_visibility: float) -> dict:
    """Per-frame inputs for the coaching flags; None when the landmarks are not visible.

    - hip_dx: horizontal gap between the hips (frame-width units). Large in a
      front view, near zero in a side view.
    - knee_width_ratio: knee gap / ankle gap. Front view only; it drops when
      the knees move in toward each other relative to the feet.
    - heel_lift: toe y minus heel y (frame-height units) on the measured leg.
      Near zero with the foot flat; grows when the heel comes up.
    """
    def seen(*names: str) -> bool:
        return all(name in points and points[name][2] >= min_visibility for name in names)

    out: dict = {"hip_dx": None, "knee_width_ratio": None, "heel_lift": None}
    if seen("left_hip", "right_hip"):
        out["hip_dx"] = round(abs(points["left_hip"][0] - points["right_hip"][0]), 5)
    if seen("left_knee", "right_knee", "left_ankle", "right_ankle"):
        ankle_gap = abs(points["left_ankle"][0] - points["right_ankle"][0])
        if ankle_gap >= 0.01:
            out["knee_width_ratio"] = round(abs(points["left_knee"][0] - points["right_knee"][0]) / ankle_gap, 4)
    if seen("left_heel", "left_foot_index"):
        out["heel_lift"] = round(points["left_foot_index"][1] - points["left_heel"][1], 5)
    return out


def _coaching_flags(since_standing: Sequence[dict], current: Sequence[dict], min_knee: float,
                    earlier_reps: Sequence[dict], descent_seconds: float | None, leg_ref: float | None,
                    aspect: float, config: AnalysisConfig, core_flags: Sequence[str],
                    standing_knee_deg: float, reference_frames: int = 8) -> tuple[list[str], dict]:
    """Coaching flags beyond depth, trunk lean and range. Returns (flags, evidence).

    Each flag is checked only when its measurement exists for this rep:
    - KNEES_CAVING: front view, and at the bottom the knees are closer together
      than ``knees_caving_max_ratio`` x their gap while standing (ratio of the
      knee gap to the ankle gap, so a wide or narrow stance does not matter).
    - HEELS_LIFTING: side view, and the heel rises more than
      ``heel_rise_fraction`` of standing leg length above its standing spot for
      at least a quarter of the rep.
    - DEPTH_INCONSISTENT: the rep is more than ``depth_drift_deg`` shallower
      than the median of the earlier reps in this session. Skipped when the rep
      is already LIMITED_DEPTH.
    - FAST_DESCENT: going from the standing threshold to the bottom threshold
      took under ``fast_descent_seconds``.
    """
    flags: list[str] = []
    evidence: dict = {"view": None, "knee_width_ratio_bottom": None, "knee_width_ratio_standing": None,
                      "heel_rise_ratio": None, "descent_seconds": None, "depth_vs_usual_deg": None}
    # Standing reference: the upright frames just before this rep (not the
    # start of the descent, which is also in since_standing).
    upright = [m for m in since_standing if m["knee_angle"] >= standing_knee_deg]
    before = upright[-reference_frames:] or list(since_standing[:reference_frames])
    hip_widths = [m["hip_dx"] for m in current if m.get("hip_dx") is not None]
    if leg_ref and hip_widths:
        front = float(np.median(hip_widths)) * aspect / leg_ref >= config.front_view_min_hip_width
        evidence["view"] = "front" if front else "side"
    if evidence["view"] == "front":
        near_bottom = [m["knee_width_ratio"] for m in current
                       if m.get("knee_width_ratio") is not None and m["knee_angle"] <= min_knee + 10]
        standing = [m["knee_width_ratio"] for m in before if m.get("knee_width_ratio") is not None]
        if near_bottom and standing:
            bottom_ratio = float(np.median(near_bottom))
            standing_ratio = float(np.median(standing))
            evidence["knee_width_ratio_bottom"] = round(bottom_ratio, 3)
            evidence["knee_width_ratio_standing"] = round(standing_ratio, 3)
            if standing_ratio > 0 and bottom_ratio < config.knees_caving_max_ratio * standing_ratio:
                flags.append("KNEES_CAVING")
    if evidence["view"] == "side" and leg_ref:
        standing_heel = [m["heel_lift"] for m in before if m.get("heel_lift") is not None]
        during = [m["heel_lift"] for m in current if m.get("heel_lift") is not None]
        if standing_heel and len(during) >= 3:
            rise = (float(np.percentile(during, 75)) - float(np.median(standing_heel))) / leg_ref
            evidence["heel_rise_ratio"] = round(rise, 3)
            if rise > config.heel_rise_fraction:
                flags.append("HEELS_LIFTING")
    depths = [r["min_knee_angle"] for r in earlier_reps]
    if len(depths) >= config.depth_reference_reps:
        drift = min_knee - float(np.median(depths))
        evidence["depth_vs_usual_deg"] = round(drift, 1)
        if drift > config.depth_drift_deg and "LIMITED_DEPTH" not in core_flags:
            flags.append("DEPTH_INCONSISTENT")
    if descent_seconds is not None:
        evidence["descent_seconds"] = round(descent_seconds, 3)
        if descent_seconds < config.fast_descent_seconds:
            flags.append("FAST_DESCENT")
    return flags, evidence


def _form_flags(min_knee: float, max_trunk: float, rom: float) -> list[str]:
    flags: list[str] = []
    if min_knee > 110:
        flags.append("LIMITED_DEPTH")
    if max_trunk > 45:
        flags.append("EXCESSIVE_TRUNK_LEAN")
    if rom < 45:
        flags.append("LOW_RANGE_OF_MOTION")
    return flags


def _fatigue(reps: Sequence[dict], baseline_reps: int) -> dict:
    if len(reps) <= baseline_reps:
        return {"status": "INSUFFICIENT_REPS", "score": 0, "signals": {}}
    base = reps[:baseline_reps]
    recent = reps[baseline_reps:]
    mean = lambda xs: sum(xs) / len(xs)
    b_duration = mean([r["duration_seconds"] for r in base])
    b_rom = mean([r["rom_degrees"] for r in base])
    r_duration = mean([r["duration_seconds"] for r in recent])
    r_rom = mean([r["rom_degrees"] for r in recent])
    duration_drift = max(0.0, (r_duration - b_duration) / max(b_duration, 0.01))
    rom_loss = max(0.0, (b_rom - r_rom) / max(b_rom, 1.0))
    # Movements without a trunk-lean measurement (e.g. push-ups) score on
    # rep time and range only, re-weighted to the same 0-100 scale.
    has_trunk = all("max_trunk_lean" in r for r in reps)
    if has_trunk:
        b_trunk = mean([r["max_trunk_lean"] for r in base])
        r_trunk = mean([r["max_trunk_lean"] for r in recent])
        trunk_drift = max(0.0, (r_trunk - b_trunk) / 20.0)
        raw = 0.4 * duration_drift + 0.35 * rom_loss + 0.25 * trunk_drift
    else:
        raw = (0.4 * duration_drift + 0.35 * rom_loss) / 0.75
    score = round(min(100.0, 100 * raw), 1)
    status = "ELEVATED" if score >= 35 else "WATCH" if score >= 15 else "STABLE"
    return {
        "status": status,
        "score": score,
        "signals": {
            "rep_duration_drift_pct": round(duration_drift * 100, 1),
            "range_of_motion_loss_pct": round(rom_loss * 100, 1),
            "trunk_lean_drift_degrees": round(max(0.0, r_trunk - b_trunk), 1) if has_trunk else None,
        },
    }


def smooth(values: Sequence[float], window: int) -> list[float]:
    """Centered running median; removes single-frame pose glitches."""
    if window <= 1:
        return list(values)
    half = window // 2
    return [float(np.median(values[max(0, i - half):i + half + 1])) for i in range(len(values))]


def calibrate_thresholds(knee_angles: Sequence[float], config: AnalysisConfig) -> dict:
    """Derive this session's rep thresholds from its own knee-angle distribution.

    People squat to different depths and camera angles foreshorten joints, so a
    fixed 105/155 degree rule undercounts honest reps. The standing reference
    is the 90th percentile knee angle (the upright cluster) and the bottom
    reference is the 5th percentile (the deep cluster). Thresholds sit inside
    that observed range with guardrails (percentiles use raw angles so real
    depth is not flattened; a handful of glitch frames cannot move P5/P90), and each rep must still cover a
    minimum share of the observed range. If the whole session moves less than
    ``min_squat_rom_deg`` there is no squat to count, and the result is zero
    reps rather than thresholds shrunk until something counts.
    """
    fixed = {
        "bottom_knee_deg": config.bottom_knee_deg,
        "standing_knee_deg": config.standing_knee_deg,
        "min_rep_rom_deg": 0.0,
    }
    if not config.calibrate:
        return {"mode": "FIXED", **fixed, "reason": "calibration disabled"}
    if len(knee_angles) < config.calibration_min_samples:
        return {"mode": "FIXED", **fixed, "reason": "too few pose frames to calibrate"}
    values = list(knee_angles)
    standing_ref = float(np.percentile(values, 90))
    bottom_ref = float(np.percentile(values, 5))
    observed_rom = standing_ref - bottom_ref
    base = {
        "standing_reference_deg": round(standing_ref, 1),
        "bottom_reference_deg": round(bottom_ref, 1),
        "observed_rom_deg": round(observed_rom, 1),
    }
    if observed_rom < config.min_squat_rom_deg:
        return {
            "mode": "NO_SQUAT_MOTION", **fixed, **base,
            "reason": f"knee angle range {observed_rom:.0f} deg is below the {config.min_squat_rom_deg:.0f} deg squat minimum",
        }
    bottom = float(np.clip(bottom_ref + config.bottom_rom_fraction * observed_rom, *config.bottom_limits_deg))
    standing = float(np.clip(standing_ref - config.standing_rom_fraction * observed_rom, *config.standing_limits_deg))
    if standing - bottom < config.min_hysteresis_deg:
        bottom = standing - config.min_hysteresis_deg
    return {
        "mode": "CALIBRATED",
        "bottom_knee_deg": round(bottom, 1),
        "standing_knee_deg": round(standing, 1),
        "min_rep_rom_deg": round(max(30.0, config.min_rep_rom_fraction * observed_rom), 1),
        **base,
        "reason": "percentile calibration from this session",
    }


def _ankle_shift(since_standing: Sequence[dict], current: Sequence[dict], key: str,
                 leg_ref: float, aspect: float, reference_frames: int) -> float | None:
    """Largest ankle move during the rep, relative to its spot just before the rep.

    x is scaled by width/height so both axes are in frame-height units, like
    ``leg_ref``. Returns a fraction of standing leg length.
    """
    before = [m[key] for m in since_standing[-reference_frames:] if m.get(key)]
    during = [m[key] for m in current if m.get(key)]
    if not before or not during:
        return None
    ref_x = float(np.median([p[0] for p in before]))
    ref_y = float(np.median([p[1] for p in before]))
    shift = max(math.hypot((x - ref_x) * aspect, y - ref_y) for x, y in during)
    return shift / leg_ref


def _leg_gate(since_standing: Sequence[dict], current: Sequence[dict], thresholds: dict,
              leg_ref: float | None, config: AnalysisConfig, aspect: float = 1.0,
              reference_frames: int = 8) -> tuple[str | None, dict]:
    """Check that a candidate rep looks like a squat, not a knee lift.

    Knee angle on one leg cannot tell a squat from lifting that leg (for example
    a sprint A-position hold). A squat also (1) bends the other knee and
    (2) lowers the hips, and (3) keeps both feet planted - jumps, bounds and
    steps move the ankles. Returns (rejection reason or None, evidence).

    A camera cut or zoom inside a rep moves every landmark at once. The feet
    check usually rejects such a rep (the ankles appear to jump); the hip-drop
    check alone can be fooled by one.
    """
    evidence: dict = {}
    if leg_ref:
        shifts = [
            v for v in (
                _ankle_shift(since_standing, current, key, leg_ref, aspect, reference_frames)
                for key in ("ankle_xy", "other_ankle_xy")
            ) if v is not None
        ]
        if shifts:
            evidence["ankle_shift_ratio"] = round(max(shifts), 3)
            if max(shifts) > config.max_ankle_shift_fraction:
                return "feet_moved", evidence
    hips = [m["hip_y"] for m in (*since_standing, *current) if m.get("hip_y") is not None]
    if leg_ref and hips:
        low = max(m["hip_y"] for m in current if m.get("hip_y") is not None)
        drop = (low - min(hips)) / leg_ref
        evidence["hip_drop_ratio"] = round(drop, 3)
        if drop < config.min_hip_drop_fraction:
            return "hip_drop", evidence
    others = [m["other_knee_angle"] for m in current if m.get("other_knee_angle") is not None]
    if others:
        evidence["other_min_knee_angle"] = round(min(others), 1)
        if min(others) > thresholds["bottom_knee_deg"] + config.other_knee_margin_deg:
            return "other_knee", evidence
    return None, evidence


class RepStateMachine:
    """Hysteresis rep counter shared by the offline analyzer and the live path.

    Feed one pose frame at a time with an already-smoothed knee angle. Offline
    analysis uses a centered median; the live path uses a trailing median.
    """

    def __init__(self, fps: float, config: AnalysisConfig, aspect: float = 1.0,
                 gate_log: dict | None = None, history_limit: int | None = None) -> None:
        self.fps, self.config, self.aspect = fps, config, aspect
        self.history_limit = history_limit
        self.reference_frames = max(1, int(fps * config.standing_reference_seconds))
        self.log = gate_log if gate_log is not None else {}
        self.log.update({"enabled": config.leg_gates, "leg_reference": None, "rejected_feet_moved": 0,
                         "rejected_hip_drop": 0, "rejected_other_knee": 0, "rejected_rom_or_duration": 0})
        self.reps: list[dict] = []
        self.reset_phase()

    def reset_phase(self) -> None:
        self.state, self.start_frame = "standing", 0
        self.descent_seconds: float | None = None
        self.current: list[dict] = []
        self.since_standing: list[dict] = []

    def push(self, frame_index: int, metrics: dict, knee: float, thresholds: dict,
             leg_ref: float | None) -> dict | None:
        """Advance one frame. Returns the new rep when one completes."""
        config = self.config
        self.log["leg_reference"] = round(leg_ref, 4) if leg_ref else None
        self.current.append(metrics)
        if self.state == "standing":
            self.since_standing.append(metrics)
            if self.history_limit and len(self.since_standing) > self.history_limit:
                del self.since_standing[: len(self.since_standing) - self.history_limit]
        if self.state == "standing" and knee <= thresholds["bottom_knee_deg"]:
            self.descent_seconds = self._descent_seconds(thresholds)
            self.state, self.start_frame, self.current = "bottom", frame_index, [metrics]
            return None
        if not (self.state == "bottom" and knee >= thresholds["standing_knee_deg"]):
            return None
        current, fps = self.current, self.fps
        duration = (frame_index - self.start_frame) / fps
        min_knee = min(m["knee_angle"] for m in current)
        max_knee = max(m["knee_angle"] for m in current)
        max_trunk = max(m["trunk_lean"] for m in current)
        rom = max_knee - min_knee
        reason, evidence = (None, {})
        if not (config.min_rep_seconds <= duration <= config.max_rep_seconds and rom >= thresholds["min_rep_rom_deg"]):
            reason = "rom_or_duration"
        elif config.leg_gates:
            reason, evidence = _leg_gate(self.since_standing, current, thresholds, leg_ref, config, self.aspect,
                                         self.reference_frames)
        rep = None
        if reason:
            self.log[f"rejected_{reason}"] += 1
        else:
            core = _form_flags(min_knee, max_trunk, rom)
            extra, coaching = ([], {})
            if config.coaching_flags:
                extra, coaching = _coaching_flags(self.since_standing, current, min_knee, self.reps,
                                                  self.descent_seconds, leg_ref, self.aspect, config, core,
                                                  thresholds["standing_knee_deg"], self.reference_frames)
            rep = {
                "rep": len(self.reps) + 1,
                "start_seconds": round(self.start_frame / fps, 3),
                "end_seconds": round(frame_index / fps, 3),
                "duration_seconds": round(duration, 3),
                "min_knee_angle": round(min_knee, 1),
                "max_trunk_lean": round(max_trunk, 1),
                "rom_degrees": round(rom, 1),
                "form_flags": core + extra,
                "hip_drop_ratio": evidence.get("hip_drop_ratio"),
                "other_min_knee_angle": evidence.get("other_min_knee_angle"),
                "ankle_shift_ratio": evidence.get("ankle_shift_ratio"),
                **coaching,
                "_end_frame": frame_index,
            }
            self.reps.append(rep)
        self.state, self.current, self.since_standing = "standing", [], [metrics]
        return rep

    def _descent_seconds(self, thresholds: dict) -> float | None:
        """Time from the last frame at or above the standing threshold to now.

        Counted in pose frames, so frames with no pose are left out and a gap
        makes the descent look faster. None when the standing point is not in
        the kept history.
        """
        frames = self.since_standing
        for back, m in enumerate(reversed(frames[:-1]), start=1):
            if m["knee_angle"] >= thresholds["standing_knee_deg"]:
                return back / self.fps
        return None


def leg_reference(metrics: Sequence[dict], config: AnalysisConfig) -> float | None:
    """Standing leg length: upright frames dominate the upper percentiles."""
    extents = [m["leg_extent"] for m in metrics if m.get("leg_extent")]
    if not extents or not config.leg_gates:
        return None
    ref = float(np.percentile(extents, 90))
    return ref if ref > 0 else None


def count_reps(frames: Sequence[dict | None], fps: float, config: AnalysisConfig, thresholds: dict,
               gate_log: dict | None = None, aspect: float = 1.0) -> list[dict]:
    """Offline pass: centered-median smoothing, then the shared state machine."""
    valid = [(i, m) for i, m in enumerate(frames) if m]
    machine = RepStateMachine(fps, config, aspect, gate_log)
    if not valid:
        return []
    leg_ref = leg_reference([m for _, m in valid], config)
    # Median window of ~smoothing_seconds, odd length; off in FIXED mode to keep legacy behavior.
    window = (int(fps * config.smoothing_seconds) | 1) if config.calibrate else 1
    smoothed = smooth([m["knee_angle"] for _, m in valid], window)
    for (frame_index, metrics), knee in zip(valid, smoothed):
        machine.push(frame_index, metrics, knee, thresholds, leg_ref)
    return machine.reps


def _pixel(point: Point, width: int, height: int) -> tuple[int, int]:
    return int(point[0] * width), int(point[1] * height)


def _drawable(point: Point | None, min_visibility: float) -> bool:
    return (
        point is not None
        and point[2] >= min_visibility
        and -0.05 <= point[0] <= 1.05
        and -0.05 <= point[1] <= 1.05
    )


def skeleton_segments(points: Landmarks, min_visibility: float = SKELETON_MIN_VISIBILITY) -> list[tuple[str, str]]:
    """Full-body connections whose endpoints are both confidently visible."""
    segments = []
    for a, b in POSE_CONNECTIONS:
        left, right = POSE_LANDMARK_NAMES[a], POSE_LANDMARK_NAMES[b]
        if _drawable(points.get(left), min_visibility) and _drawable(points.get(right), min_visibility):
            segments.append((left, right))
    return segments


def _draw(frame: np.ndarray, points: Landmarks | None, metrics: dict | None, rep_count: int,
          thresholds: dict | None = None) -> None:
    height, width = frame.shape[:2]
    if points:
        # 1) Full MediaPipe skeleton, thin and neutral, visibility-gated so
        #    low-confidence joints never draw ghost limbs.
        for left, right in skeleton_segments(points):
            cv2.line(frame, _pixel(points[left], width, height), _pixel(points[right], width, height),
                     (235, 235, 235), 2, cv2.LINE_AA)
        for name in POSE_LANDMARK_NAMES:
            point = points.get(name)
            if _drawable(point, SKELETON_MIN_VISIBILITY):
                cv2.circle(frame, _pixel(point, width, height), 3, (160, 160, 160), -1, cv2.LINE_AA)
        # 2) Measurement chain (shoulder-hip-knee-ankle) on top, thick and bright:
        #    these are the joints behind every angle, rep and flag.
        for left, right in CONNECTIONS:
            if _drawable(points.get(left), 0.0) and _drawable(points.get(right), 0.0):
                cv2.line(frame, _pixel(points[left], width, height), _pixel(points[right], width, height),
                         (0, 220, 255), 6, cv2.LINE_AA)
        for name in MEASUREMENT_KEYS:
            point = points.get(name)
            if _drawable(point, 0.0):
                cv2.circle(frame, _pixel(point, width, height), 8, (0, 255, 120), -1, cv2.LINE_AA)
                cv2.circle(frame, _pixel(point, width, height), 8, (20, 20, 20), 1, cv2.LINE_AA)
    text = f"Reps {rep_count}"
    if metrics:
        text += f" | knee {metrics['knee_angle']:.0f} | trunk {metrics['trunk_lean']:.0f}"
    cv2.rectangle(frame, (10, 10), (min(width-10, 430), 48), (12, 18, 30), -1)
    cv2.putText(frame, text, (20, 37), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255,255,255), 2)
    if thresholds:
        if thresholds["mode"] == "NO_SQUAT_MOTION":
            note = f"no squat motion (knee range {thresholds['observed_rom_deg']:.0f} deg) - 0 reps"
        else:
            note = f"{thresholds['mode'].lower()}: bottom<={thresholds['bottom_knee_deg']:.0f} stand>={thresholds['standing_knee_deg']:.0f}"
        cv2.rectangle(frame, (10, 50), (min(width-10, 430), 74), (12, 18, 30), -1)
        cv2.putText(frame, note, (20, 67), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 220, 255), 1)


def analyze_video(
    input_path: str | Path,
    output_dir: str | Path,
    detector: Detector | None = None,
    config: AnalysisConfig = AnalysisConfig(),
) -> dict:
    """Analyze a recorded side-view squat video and write MP4, JSON, and CSV."""
    source = Path(input_path)
    out = Path(output_dir)
    if not source.is_file():
        raise FileNotFoundError(f"Input video not found: {source}")
    out.mkdir(parents=True, exist_ok=True)
    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        raise ValueError(f"Cannot decode video: {source}")
    fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if width <= 0 or height <= 0:
        capture.release()
        raise ValueError("Video has invalid dimensions")
    total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if total and (total > config.max_frames or total / fps > config.max_duration_seconds):
        capture.release()
        raise ValueError(f"Video exceeds {config.max_duration_seconds:.0f}s/{config.max_frames} frame limit")
    owns_detector = detector is None
    detector = detector or MediaPipePoseDetector()

    # Pass 1: pose + per-frame metrics. Frames are not kept in memory.
    all_points: list[Landmarks | None] = []
    all_metrics: list[dict | None] = []
    try:
        while len(all_points) < config.max_frames:
            ok, frame = capture.read()
            if not ok:
                break
            points = detector(frame)
            all_points.append(points)
            all_metrics.append(_metrics(points, config.min_visibility) if points else None)
    finally:
        capture.release()
        if owns_detector and hasattr(detector, "close"):
            detector.close()  # type: ignore[attr-defined]

    frame_index = len(all_points)
    if frame_index == 0:
        raise ValueError("Video contains no readable frames")
    knees = [m["knee_angle"] for m in all_metrics if m]
    coverage = len(knees) / frame_index
    if coverage < 0.5:
        raise ValueError(f"Pose visible in only {coverage:.0%} of frames; record one person in full side view")

    thresholds = calibrate_thresholds(knees, config)
    gate_log: dict = {}
    reps = [] if thresholds["mode"] == "NO_SQUAT_MOTION" else count_reps(all_metrics, fps, config, thresholds, gate_log, width / height)
    end_frames = [rep.pop("_end_frame") for rep in reps]
    message = None
    if thresholds["mode"] == "NO_SQUAT_MOTION":
        message = f"No squat movement detected: {thresholds['reason']}. Zero reps counted."
    elif not reps:
        message = "No complete squat reps detected with this session's calibrated thresholds."

    # Pass 2: re-read the source and render the annotated MP4.
    annotated = out / "annotated.mp4"
    capture = cv2.VideoCapture(str(source))
    writer = cv2.VideoWriter(str(annotated), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    if not writer.isOpened():
        capture.release()
        raise RuntimeError("Cannot create annotated MP4")
    try:
        done = 0
        for index in range(frame_index):
            ok, frame = capture.read()
            if not ok:
                break
            while done < len(end_frames) and end_frames[done] <= index:
                done += 1
            _draw(frame, all_points[index], all_metrics[index], done, thresholds)
            writer.write(frame)
    finally:
        capture.release()
        writer.release()

    report = {
        "schema_version": "1.1",
        "scope": "recorded side-view squat prototype",
        "disclaimer": "Form-risk flags and fatigue indicator only; not medical advice or injury probability.",
        "input": {"filename": source.name, "fps": round(fps, 3), "frames": frame_index, "pose_coverage": round(coverage, 3)},
        "config": asdict(config),
        "calibration": thresholds,
        "rep_gates": gate_log,
        "known_limits": KNOWN_LIMITS,
        "summary": {"message": message, "reps": len(reps), "flagged_reps": sum(bool(r["form_flags"]) for r in reps), "fatigue_indicator": _fatigue(reps, config.baseline_reps)},
        "reps": reps,
        "artifacts": {"annotated_video": annotated.name, "csv": "reps.csv"},
    }
    (out / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    with (out / "reps.csv").open("w", newline="", encoding="utf-8") as handle:
        fields = ["rep", "start_seconds", "end_seconds", "duration_seconds", "min_knee_angle", "max_trunk_lean", "rom_degrees", "hip_drop_ratio", "other_min_knee_angle", "ankle_shift_ratio", "view", "knee_width_ratio_bottom", "knee_width_ratio_standing", "heel_rise_ratio", "descent_seconds", "depth_vs_usual_deg", "form_flags"]
        writer_csv = csv.DictWriter(handle, fieldnames=fields)
        writer_csv.writeheader()
        for rep in reps:
            row = dict(rep); row["form_flags"] = "|".join(row["form_flags"])
            writer_csv.writerow(row)
    return report
