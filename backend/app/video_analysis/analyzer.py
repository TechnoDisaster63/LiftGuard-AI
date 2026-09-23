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
    return {"knee_angle": round(knee, 2), "trunk_lean": round(trunk, 2)}


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


def _draw(frame: np.ndarray, points: Landmarks | None, metrics: dict | None, rep_count: int) -> None:
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
    annotated = out / "annotated.mp4"
    writer = cv2.VideoWriter(str(annotated), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    if not writer.isOpened():
        capture.release()
        raise RuntimeError("Cannot create annotated MP4")

    state, start_frame = "standing", 0
    current: list[dict] = []
    reps: list[dict] = []
    valid_frames = frame_index = 0
    try:
        while frame_index < config.max_frames:
            ok, frame = capture.read()
            if not ok:
                break
            points = detector(frame)
            metrics = _metrics(points, config.min_visibility) if points else None
            if metrics:
                valid_frames += 1
                current.append(metrics)
                knee = metrics["knee_angle"]
                if state == "standing" and knee <= config.bottom_knee_deg:
                    state, start_frame = "bottom", frame_index
                    current = [metrics]
                elif state == "bottom" and knee >= config.standing_knee_deg:
                    duration = (frame_index - start_frame) / fps
                    if config.min_rep_seconds <= duration <= config.max_rep_seconds:
                        min_knee = min(m["knee_angle"] for m in current)
                        max_knee = max(m["knee_angle"] for m in current)
                        max_trunk = max(m["trunk_lean"] for m in current)
                        rom = max_knee - min_knee
                        reps.append({
                            "rep": len(reps)+1,
                            "start_seconds": round(start_frame/fps, 3),
                            "end_seconds": round(frame_index/fps, 3),
                            "duration_seconds": round(duration, 3),
                            "min_knee_angle": round(min_knee, 1),
                            "max_trunk_lean": round(max_trunk, 1),
                            "rom_degrees": round(rom, 1),
                            "form_flags": _form_flags(min_knee, max_trunk, rom),
                        })
                    state, current = "standing", []
            _draw(frame, points, metrics, len(reps))
            writer.write(frame)
            frame_index += 1
    finally:
        capture.release()
        writer.release()
        if owns_detector and hasattr(detector, "close"):
            detector.close()  # type: ignore[attr-defined]

    coverage = valid_frames / max(frame_index, 1)
    if frame_index == 0:
        raise ValueError("Video contains no readable frames")
    if coverage < 0.5:
        annotated.unlink(missing_ok=True)
        raise ValueError(f"Pose visible in only {coverage:.0%} of frames; record one person in full side view")
    report = {
        "schema_version": "1.0",
        "scope": "recorded side-view squat prototype",
        "disclaimer": "Form-risk flags and fatigue indicator only; not medical advice or injury probability.",
        "input": {"filename": source.name, "fps": round(fps, 3), "frames": frame_index, "pose_coverage": round(coverage, 3)},
        "config": asdict(config),
        "summary": {"reps": len(reps), "flagged_reps": sum(bool(r["form_flags"]) for r in reps), "fatigue_indicator": _fatigue(reps, config.baseline_reps)},
        "reps": reps,
        "artifacts": {"annotated_video": annotated.name, "csv": "reps.csv"},
    }
    (out / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    with (out / "reps.csv").open("w", newline="", encoding="utf-8") as handle:
        fields = ["rep", "start_seconds", "end_seconds", "duration_seconds", "min_knee_angle", "max_trunk_lean", "rom_degrees", "form_flags"]
        writer_csv = csv.DictWriter(handle, fieldnames=fields)
        writer_csv.writeheader()
        for rep in reps:
            row = dict(rep); row["form_flags"] = "|".join(row["form_flags"])
            writer_csv.writerow(row)
    return report
