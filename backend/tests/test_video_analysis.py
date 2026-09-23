import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from app.video_analysis.analyzer import AnalysisConfig, analyze_video, angle


def point(x, y):
    return (x, y, 0.99)


def landmarks(knee_angle, trunk=12):
    knee = point(0.55, 0.65)
    ankle = point(0.55, 0.90)
    rad = np.deg2rad(knee_angle)
    hip = point(0.55 + 0.25*np.sin(rad), 0.65 + 0.25*np.cos(rad))
    shoulder = point(hip[0] + 0.28*np.sin(np.deg2rad(trunk)), hip[1] - 0.28*np.cos(np.deg2rad(trunk)))
    return {"shoulder": shoulder, "hip": hip, "knee": knee, "ankle": ankle}


class SequenceDetector:
    def __init__(self, sequence):
        self.sequence = iter(sequence)
    def __call__(self, _frame):
        return next(self.sequence)


def make_video(path: Path, frames: int, fps: int = 10):
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (320, 240))
    assert writer.isOpened()
    for i in range(frames):
        frame = np.full((240, 320, 3), (20+i%20, 28, 38), np.uint8)
        writer.write(frame)
    writer.release()


def squat_sequence(reps=5):
    one = [170, 160, 140, 115, 95, 115, 140, 160, 170]
    return [landmarks(a, 12 + (4 if rep >= 3 else 0)) for rep in range(reps) for a in one]


def test_angle_is_deterministic():
    assert angle(point(0, 0), point(0, 1), point(1, 1)) == pytest.approx(90)


def test_fixture_video_writes_repeatable_artifacts(tmp_path):
    video = tmp_path / "squats.mp4"
    sequence = squat_sequence(5)
    make_video(video, len(sequence))
    config = AnalysisConfig(baseline_reps=3, min_rep_seconds=0.2)
    first = analyze_video(video, tmp_path / "a", SequenceDetector(sequence), config)
    second = analyze_video(video, tmp_path / "b", SequenceDetector(squat_sequence(5)), config)
    assert first["summary"] == second["summary"]
    assert first["summary"]["reps"] == 5
    assert first["summary"]["fatigue_indicator"]["status"] in {"STABLE", "WATCH", "ELEVATED"}
    assert (tmp_path / "a" / "annotated.mp4").stat().st_size > 1000
    assert json.loads((tmp_path / "a" / "report.json").read_text())["schema_version"] == "1.0"
    assert (tmp_path / "a" / "reps.csv").read_text().count("\n") == 6


def test_low_pose_coverage_fails_clearly(tmp_path):
    video = tmp_path / "bad.mp4"
    make_video(video, 10)
    with pytest.raises(ValueError, match="Pose visible"):
        analyze_video(video, tmp_path / "out", SequenceDetector([None]*10))
