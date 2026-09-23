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
        return {
            name: (points[idx].x, points[idx].y, points[idx].visibility)
            for name, idx in self._indices.items()
        }

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


def _draw(frame: np.ndarray, points: Landmarks | None, metrics: dict | None, rep_count: int) -> None:
    height, width = frame.shape[:2]
    if points:
        for left, right in CONNECTIONS:
            if left in points and right in points:
                a, b = points[left], points[right]
                cv2.line(frame, (int(a[0]*width), int(a[1]*height)), (int(b[0]*width), int(b[1]*height)), (0, 220, 255), 3)
        for point in points.values():
            cv2.circle(frame, (int(point[0]*width), int(point[1]*height)), 5, (0, 255, 120), -1)
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
