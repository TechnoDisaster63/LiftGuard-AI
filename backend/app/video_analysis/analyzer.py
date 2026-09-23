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
    }
    other = ("right_hip", "right_knee", "right_ankle")
    if all(name in points and points[name][2] >= min_visibility for name in other):
        metrics["other_knee_angle"] = round(angle(points["right_hip"], points["right_knee"], points["right_ankle"]), 2)
    return metrics


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
    b_trunk = mean([r["max_trunk_lean"] for r in base])
    r_duration = mean([r["duration_seconds"] for r in recent])
    r_rom = mean([r["rom_degrees"] for r in recent])
    r_trunk = mean([r["max_trunk_lean"] for r in recent])
    duration_drift = max(0.0, (r_duration - b_duration) / max(b_duration, 0.01))
    rom_loss = max(0.0, (b_rom - r_rom) / max(b_rom, 1.0))
    trunk_drift = max(0.0, (r_trunk - b_trunk) / 20.0)
    score = round(min(100.0, 100 * (0.4 * duration_drift + 0.35 * rom_loss + 0.25 * trunk_drift)), 1)
    status = "ELEVATED" if score >= 35 else "WATCH" if score >= 15 else "STABLE"
    return {
        "status": status,
        "score": score,
        "signals": {
            "rep_duration_drift_pct": round(duration_drift * 100, 1),
            "range_of_motion_loss_pct": round(rom_loss * 100, 1),
            "trunk_lean_drift_degrees": round(max(0.0, r_trunk - b_trunk), 1),
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


def _leg_gate(since_standing: Sequence[dict], current: Sequence[dict], thresholds: dict,
              leg_ref: float | None, config: AnalysisConfig) -> tuple[str | None, dict]:
    """Check that a candidate rep looks like a squat, not a knee lift.

    Knee angle on one leg cannot tell a squat from lifting that leg (for example
    a sprint A-position hold). A squat also (1) bends the other knee and
    (2) lowers the hips. Returns (rejection reason or None, evidence).
    """
    evidence: dict = {}
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


def count_reps(frames: Sequence[dict | None], fps: float, config: AnalysisConfig, thresholds: dict,
               gate_log: dict | None = None) -> list[dict]:
    """Hysteresis state machine over smoothed knee angles; raw values feed per-rep metrics."""
    valid = [(i, m) for i, m in enumerate(frames) if m]
    if not valid:
        return []
    extents = [m["leg_extent"] for _, m in valid if m.get("leg_extent")]
    # Standing leg length reference: upright frames dominate the upper percentiles.
    leg_ref = float(np.percentile(extents, 90)) if extents and config.leg_gates else None
    if leg_ref is not None and leg_ref <= 0:
        leg_ref = None
    log = gate_log if gate_log is not None else {}
    log.update({"enabled": config.leg_gates, "leg_reference": round(leg_ref, 4) if leg_ref else None,
                "rejected_hip_drop": 0, "rejected_other_knee": 0, "rejected_rom_or_duration": 0})
    since_standing: list[dict] = []
    # Median window of ~smoothing_seconds, odd length; off in FIXED mode to keep legacy behavior.
    window = (int(fps * config.smoothing_seconds) | 1) if config.calibrate else 1
    smoothed = smooth([m["knee_angle"] for _, m in valid], window)
    bottom, standing = thresholds["bottom_knee_deg"], thresholds["standing_knee_deg"]
    state, start_frame = "standing", 0
    current: list[dict] = []
    reps: list[dict] = []
    for (frame_index, metrics), knee in zip(valid, smoothed):
        current.append(metrics)
        if state == "standing":
            since_standing.append(metrics)
        if state == "standing" and knee <= bottom:
            state, start_frame, current = "bottom", frame_index, [metrics]
        elif state == "bottom" and knee >= standing:
            duration = (frame_index - start_frame) / fps
            min_knee = min(m["knee_angle"] for m in current)
            max_knee = max(m["knee_angle"] for m in current)
            max_trunk = max(m["trunk_lean"] for m in current)
            rom = max_knee - min_knee
            reason, evidence = (None, {})
            if not (config.min_rep_seconds <= duration <= config.max_rep_seconds and rom >= thresholds["min_rep_rom_deg"]):
                reason = "rom_or_duration"
            elif config.leg_gates:
                reason, evidence = _leg_gate(since_standing, current, thresholds, leg_ref, config)
            if reason:
                log[f"rejected_{reason}"] += 1
            else:
                reps.append({
                    "rep": len(reps) + 1,
                    "start_seconds": round(start_frame / fps, 3),
                    "end_seconds": round(frame_index / fps, 3),
                    "duration_seconds": round(duration, 3),
                    "min_knee_angle": round(min_knee, 1),
                    "max_trunk_lean": round(max_trunk, 1),
                    "rom_degrees": round(rom, 1),
                    "form_flags": _form_flags(min_knee, max_trunk, rom),
                    "hip_drop_ratio": evidence.get("hip_drop_ratio"),
                    "other_min_knee_angle": evidence.get("other_min_knee_angle"),
                    "_end_frame": frame_index,
                })
            state, current, since_standing = "standing", [], [metrics]
    return reps


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
    reps = [] if thresholds["mode"] == "NO_SQUAT_MOTION" else count_reps(all_metrics, fps, config, thresholds, gate_log)
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
        "summary": {"message": message, "reps": len(reps), "flagged_reps": sum(bool(r["form_flags"]) for r in reps), "fatigue_indicator": _fatigue(reps, config.baseline_reps)},
        "reps": reps,
        "artifacts": {"annotated_video": annotated.name, "csv": "reps.csv"},
    }
    (out / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    with (out / "reps.csv").open("w", newline="", encoding="utf-8") as handle:
        fields = ["rep", "start_seconds", "end_seconds", "duration_seconds", "min_knee_angle", "max_trunk_lean", "rom_degrees", "hip_drop_ratio", "other_min_knee_angle", "form_flags"]
        writer_csv = csv.DictWriter(handle, fieldnames=fields)
        writer_csv.writeheader()
        for rep in reps:
            row = dict(rep); row["form_flags"] = "|".join(row["form_flags"])
            writer_csv.writerow(row)
    return report
