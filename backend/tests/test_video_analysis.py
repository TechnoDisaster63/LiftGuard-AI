import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from app.video_analysis.analyzer import (
    POSE_CONNECTIONS,
    POSE_LANDMARK_NAMES,
    AnalysisConfig,
    calibrate_thresholds,
    count_reps,
    _draw,
    _metrics,
    analyze_video,
    angle,
    skeleton_segments,
)


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
    assert json.loads((tmp_path / "a" / "report.json").read_text())["schema_version"] == "1.1"
    assert (tmp_path / "a" / "reps.csv").read_text().count("\n") == 6


def test_low_pose_coverage_fails_clearly(tmp_path):
    video = tmp_path / "bad.mp4"
    make_video(video, 10)
    with pytest.raises(ValueError, match="Pose visible"):
        analyze_video(video, tmp_path / "out", SequenceDetector([None]*10))


def full_body(visibility=0.99):
    return {
        name: (0.1 + 0.8 * ((i * 7) % 33) / 33, 0.05 + 0.9 * ((i * 11) % 33) / 33, visibility)
        for i, name in enumerate(POSE_LANDMARK_NAMES)
    }


def test_skeleton_has_33_landmarks_and_35_connections():
    assert len(POSE_LANDMARK_NAMES) == 33
    assert len(POSE_CONNECTIONS) == 35
    assert len(skeleton_segments(full_body())) == 35


def test_skeleton_skips_low_visibility_joints():
    points = full_body()
    points["left_wrist"] = (0.4, 0.4, 0.1)
    segments = skeleton_segments(points)
    assert all("left_wrist" not in seg for seg in segments)
    assert len(segments) == 35 - 4  # left_wrist joins elbow, pinky, index, thumb
    assert skeleton_segments(full_body(visibility=0.2)) == []


def test_draw_renders_full_skeleton_and_measurement_chain():
    frame = np.zeros((240, 320, 3), np.uint8)
    points = full_body()
    points.update(landmarks(90))
    _draw(frame, points, {"knee_angle": 90.0, "trunk_lean": 12.0}, 1)
    neutral = np.all(frame == (235, 235, 235), axis=2).sum()
    chain = np.all(frame == (0, 220, 255), axis=2).sum()
    assert neutral > 50 and chain > 50


# Summary produced by the fixed 105/155 rule before calibration existed.
GOLDEN_SUMMARY = {
    "reps": 5,
    "flagged_reps": 0,
    "fatigue_indicator": {
        "status": "STABLE",
        "score": 5.0,
        "signals": {"rep_duration_drift_pct": 0.0, "range_of_motion_loss_pct": 0.0, "trunk_lean_drift_degrees": 4.0},
    },
}


def run(tmp_path, sequence, name="run", **overrides):
    video = tmp_path / f"{name}.mp4"
    make_video(video, len(sequence))
    config = AnalysisConfig(**{"baseline_reps": 3, "min_rep_seconds": 0.2, **overrides})
    return analyze_video(video, tmp_path / name, SequenceDetector(sequence), config)


def test_golden_fixture_summary_unchanged_by_calibration(tmp_path):
    calibrated = run(tmp_path, squat_sequence(5), "cal")
    fixed = run(tmp_path, squat_sequence(5), "fixed", calibrate=False)
    for report in (calibrated, fixed):
        summary = dict(report["summary"])
        assert summary.pop("message") is None
        assert summary == GOLDEN_SUMMARY
    assert calibrated["calibration"]["mode"] == "CALIBRATED"
    assert fixed["calibration"]["mode"] == "FIXED"
    assert [r["min_knee_angle"] for r in calibrated["reps"]] == [95.0] * 5


def foreshortened_trace(reps=15, fps=25, seed=7):
    """Front-view-like trace: bottoms near 110-125 deg, never reach the fixed 105."""
    rng = np.random.default_rng(seed)
    trace = [178.0] * 25
    for i in range(reps):
        depth = 112 + 12 * rng.random()
        down = np.linspace(178, depth, 20)
        trace += list(down) + list(down[::-1]) + [178.0] * 10
    trace = [a + rng.normal(0, 1.5) for a in trace]
    trace[10:15] = [6.0, 4.0, 4.0, 5.0, 16.0]  # short pose glitch like the real clip
    return trace


def frames_from(trace):
    return [{"knee_angle": a, "trunk_lean": 8.0} for a in trace]


def test_calibration_counts_shallow_view_reps_fixed_rule_misses():
    config = AnalysisConfig()
    trace = foreshortened_trace(15)
    fixed = calibrate_thresholds(trace, AnalysisConfig(calibrate=False))
    calibrated = calibrate_thresholds(trace, config)
    assert calibrated["mode"] == "CALIBRATED"
    assert config.bottom_limits_deg[0] <= calibrated["bottom_knee_deg"] <= config.bottom_limits_deg[1]
    assert calibrated["standing_knee_deg"] - calibrated["bottom_knee_deg"] >= config.min_hysteresis_deg
    assert len(count_reps(frames_from(trace), 25, config, fixed)) == 0
    assert len(count_reps(frames_from(trace), 25, config, calibrated)) == 15


def test_standing_still_counts_zero_with_message(tmp_path):
    rng = np.random.default_rng(1)
    sequence = [landmarks(170 + rng.normal(0, 2)) for _ in range(60)]
    report = run(tmp_path, sequence, "still")
    assert report["summary"]["reps"] == 0
    assert report["calibration"]["mode"] == "NO_SQUAT_MOTION"
    assert report["summary"]["message"].startswith("No squat movement detected")


def test_shallow_bobbing_is_not_a_squat(tmp_path):
    bob = [170, 165, 158, 152, 158, 165]
    report = run(tmp_path, [landmarks(a) for a in bob * 10], "bob")
    assert report["summary"]["reps"] == 0
    assert report["calibration"]["mode"] == "NO_SQUAT_MOTION"


def test_rep_rom_gate_rejects_partial_dips():
    # Full squats plus half-depth pulses: pulses cross no calibrated bottom.
    full = [178] * 5 + list(np.linspace(178, 95, 15)) + list(np.linspace(95, 178, 15))
    pulse = list(np.linspace(178, 150, 8)) + list(np.linspace(150, 178, 8))
    trace = (full + pulse * 2) * 4
    config = AnalysisConfig()
    thresholds = calibrate_thresholds(trace, config)
    assert len(count_reps(frames_from(trace), 25, config, thresholds)) == 4


# --- Leg gates: both knees bent + hip drop -------------------------------------------------

FIXTURES = Path(__file__).parent / "fixtures"


def load_landmark_fixture(name):
    import gzip

    with gzip.open(FIXTURES / name, "rt") as handle:
        data = json.load(handle)
    frames = []
    for row in data["frames"]:
        if row is None:
            frames.append(None)
            continue
        points = {key: tuple(row[i * 3:i * 3 + 3]) for i, key in enumerate(data["keys"])}
        for alias in ("shoulder", "hip", "knee", "ankle"):
            points[alias] = points[f"left_{alias}"]
        frames.append(_metrics(points, AnalysisConfig().min_visibility))
    return data["fps"], frames


def count_fixture(name, **overrides):
    fps, frames = load_landmark_fixture(name)
    config = AnalysisConfig(**overrides)
    thresholds = calibrate_thresholds([m["knee_angle"] for m in frames if m], config)
    log = {}
    return count_reps(frames, fps, config, thresholds, log), log


def test_a_position_hold_is_not_a_squat():
    # Regression: video 4 at 72.1-74.9 s counted 1 squat. The measured knee was the lifted leg.
    reps, log = count_fixture("a_position_hold.json.gz")
    assert reps == []
    assert log["rejected_other_knee"] == 1
    ungated, _ = count_fixture("a_position_hold.json.gz", leg_gates=False)
    assert len(ungated) == 1  # the fixture reproduces the original false rep


def test_front_view_squats_still_count_15():
    reps, log = count_fixture("front_view_squats.json.gz")
    assert len(reps) == 15
    assert log["rejected_hip_drop"] == 0 and log["rejected_other_knee"] == 0
    assert all(r["hip_drop_ratio"] >= AnalysisConfig().min_hip_drop_fraction for r in reps)
    assert 15.0 <= reps[0]["start_seconds"] and reps[-1]["end_seconds"] <= 45.0


def leg_frames(knee_trace, hip_trace, other_trace=None):
    frames = []
    for i, (knee, hip) in enumerate(zip(knee_trace, hip_trace)):
        other = None if other_trace is None else other_trace[i]
        frames.append({"knee_angle": knee, "trunk_lean": 8.0, "hip_y": hip,
                       "leg_extent": 0.9 - hip, "other_knee_angle": other})
    return frames


def squat_like(reps=4, drop=0.15, other_bends=True):
    down = list(np.linspace(178, 95, 15))
    knee = ([178.0] * 5 + down + down[::-1]) * reps
    hip = ([0.40] * 5 + list(np.linspace(0.40, 0.40 + drop, 15)) + list(np.linspace(0.40 + drop, 0.40, 15))) * reps
    other = knee if other_bends else [177.0] * len(knee)
    return knee, hip, other


def test_knee_lift_without_hip_drop_is_rejected():
    knee, _, other = squat_like()
    frames = leg_frames(knee, [0.40] * len(knee), other)
    config = AnalysisConfig()
    thresholds = calibrate_thresholds(knee, config)
    log = {}
    assert count_reps(frames, 25, config, thresholds, log) == []
    assert log["rejected_hip_drop"] == 4


def test_straight_other_leg_is_rejected():
    knee, hip, other = squat_like(other_bends=False)
    config = AnalysisConfig()
    thresholds = calibrate_thresholds(knee, config)
    log = {}
    assert count_reps(leg_frames(knee, hip, other), 25, config, thresholds, log) == []
    assert log["rejected_other_knee"] == 4


def test_real_squat_passes_both_leg_gates():
    knee, hip, other = squat_like()
    config = AnalysisConfig()
    thresholds = calibrate_thresholds(knee, config)
    reps = count_reps(leg_frames(knee, hip, other), 25, config, thresholds)
    assert len(reps) == 4
    assert all(r["hip_drop_ratio"] > 0.15 and r["other_min_knee_angle"] <= 100 for r in reps)
