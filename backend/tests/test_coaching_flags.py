"""Coaching flags beyond depth, trunk lean and range of motion.

Each flag must come from a landmark measurement, and must stay unchecked
(not guessed) when the view or the landmarks it needs are missing.
"""
import gzip
import json
from pathlib import Path

import numpy as np

from app.video_analysis.analyzer import AnalysisConfig, _metrics, angle, calibrate_thresholds, count_reps
from app.video_analysis.live import LiveSquatCounter

from .test_video_analysis import count_fixture, leg_frames

FIXTURES = Path(__file__).parent / "fixtures"
NEW_FLAGS = {"KNEES_CAVING", "HEELS_LIFTING", "DEPTH_INCONSISTENT", "FAST_DESCENT"}


def count(frames, fps=25, aspect=16 / 9, **overrides):
    config = AnalysisConfig(**overrides)
    thresholds = calibrate_thresholds([f["knee_angle"] for f in frames], config)
    return count_reps(frames, fps, config, thresholds, {}, aspect)


def front_view_points(cave=None):
    """Real front-view landmarks. ``cave`` squeezes the knee gap near the bottom."""
    with gzip.open(FIXTURES / "front_view_squats.json.gz", "rt") as handle:
        data = json.load(handle)
    frames = []
    for row in data["frames"]:
        if row is None:
            frames.append(None)
            continue
        p = {key: tuple(row[i * 3:i * 3 + 3]) for i, key in enumerate(data["keys"])}
        for alias in ("shoulder", "hip", "knee", "ankle"):
            p[alias] = p[f"left_{alias}"]
        # The measured knee angle keeps the real left knee ("knee" alias); only the
        # knee gap used by the caving check is squeezed.
        if cave is not None and angle(p["hip"], p["knee"], p["ankle"]) < 140:
            x, y, v = p["left_knee"]
            right_x = p["right_knee"][0]
            p["left_knee"] = (right_x + (x - right_x) * cave, y, v)
        frames.append(p)
    return data["fps"], data["aspect"], frames


def side_frames(heel_rise=0.0, down_frames=15, up_frames=15, reps=4, bottoms=None):
    """Side view (hips overlap) with a flat foot, optionally lifting the heel at the bottom."""
    knee, hip = [], []
    for i in range(reps):
        bottom = bottoms[i] if bottoms else 95.0
        knee += [178.0] * 8 + list(np.linspace(178, bottom, down_frames)) + list(np.linspace(bottom, 178, up_frames))
        hip += [0.40] * 8 + list(np.linspace(0.40, 0.55, down_frames)) + list(np.linspace(0.55, 0.40, up_frames))
    frames = leg_frames(knee, hip, knee)
    for frame in frames:
        frame["hip_dx"] = 0.01
        frame["heel_lift"] = heel_rise if frame["knee_angle"] < 120 else 0.0
    return frames


# --- Real clip: the trainer's normal squats get none of the new flags --------------------

def test_real_front_view_squats_get_no_new_coaching_flags():
    reps, _ = count_fixture("front_view_squats.json.gz")
    assert len(reps) == 15
    assert all(r["view"] == "front" for r in reps)
    # Knees move out at the bottom (ratio goes up), so no caving flag.
    assert all(r["knee_width_ratio_bottom"] >= r["knee_width_ratio_standing"] for r in reps)
    assert not any(NEW_FLAGS & set(r["form_flags"]) for r in reps)
    # Heels are not checked from the front, and this clip has no heel landmarks anyway.
    assert all(r["heel_rise_ratio"] is None for r in reps)
    assert min(r["descent_seconds"] for r in reps) >= 0.2


# --- Knees caving (front view only) ------------------------------------------------------

def test_knees_caving_on_real_landmarks_with_knees_pulled_in():
    fps, aspect, points = front_view_points(cave=0.5)
    frames = [_metrics(p, AnalysisConfig().min_visibility) if p else None for p in points]
    valid = [f for f in frames if f]
    config = AnalysisConfig()
    thresholds = calibrate_thresholds([f["knee_angle"] for f in valid], config)
    reps = count_reps(frames, fps, config, thresholds, {}, aspect)
    assert len(reps) == 15
    assert all("KNEES_CAVING" in r["form_flags"] for r in reps)
    assert all(r["knee_width_ratio_bottom"] < 0.9 * r["knee_width_ratio_standing"] for r in reps)


def test_knees_caving_is_flagged_live_too():
    fps, aspect, points = front_view_points(cave=0.5)
    counter = LiveSquatCounter(fps=fps, aspect=aspect)
    for p in points:
        status = counter.update(p)
    assert counter.rep_count == 15
    assert "KNEES_CAVING" in status["last_rep"]["form_flags"]
    assert status["last_rep"]["view"] == "front"


def test_knees_caving_is_not_checked_from_the_side():
    frames = side_frames()
    for frame in frames:
        frame["knee_width_ratio"] = 0.2  # would be "caving" if this were a front view
    reps = count(frames)
    assert len(reps) == 4
    assert all(r["view"] == "side" and r["knee_width_ratio_bottom"] is None for r in reps)
    assert not any("KNEES_CAVING" in r["form_flags"] for r in reps)


# --- Heels lifting (side view only) ------------------------------------------------------

def test_heels_lifting_is_flagged_when_heel_rises_at_the_bottom():
    reps = count(side_frames(heel_rise=0.05))  # leg length is 0.5, so a 10% rise
    assert len(reps) == 4
    assert all("HEELS_LIFTING" in r["form_flags"] for r in reps)
    assert all(r["heel_rise_ratio"] > 0.04 for r in reps)


def test_flat_heels_and_small_jitter_are_not_flagged():
    for rise in (0.0, 0.01):  # 0.01 = 2% of leg length, below the 4% threshold
        reps = count(side_frames(heel_rise=rise))
        assert len(reps) == 4
        assert not any("HEELS_LIFTING" in r["form_flags"] for r in reps)


def test_heels_unchecked_without_heel_landmarks():
    frames = side_frames(heel_rise=0.05)
    for frame in frames:
        frame["heel_lift"] = None
    reps = count(frames)
    assert all(r["heel_rise_ratio"] is None and "HEELS_LIFTING" not in r["form_flags"] for r in reps)


def test_heel_lift_metric_comes_from_heel_and_toe_landmarks():
    base = {"shoulder": (0.5, 0.2, 0.99), "hip": (0.5, 0.5, 0.99), "knee": (0.55, 0.7, 0.99),
            "ankle": (0.5, 0.9, 0.99)}
    flat = _metrics({**base, "left_heel": (0.48, 0.93, 0.9), "left_foot_index": (0.58, 0.93, 0.9)}, 0.55)
    lifted = _metrics({**base, "left_heel": (0.48, 0.90, 0.9), "left_foot_index": (0.58, 0.93, 0.9)}, 0.55)
    hidden = _metrics({**base, "left_heel": (0.48, 0.90, 0.2), "left_foot_index": (0.58, 0.93, 0.9)}, 0.55)
    assert flat["heel_lift"] == 0.0
    assert lifted["heel_lift"] == 0.03
    assert hidden["heel_lift"] is None


# --- Depth drift across reps -------------------------------------------------------------

def test_depth_inconsistent_flags_only_the_rep_that_drifts():
    steady = count(side_frames(reps=5, bottoms=[85, 86, 84, 85, 90]))
    assert len(steady) == 5
    assert not any("DEPTH_INCONSISTENT" in r["form_flags"] for r in steady)
    # Rep 5 bottoms at 105 deg: passes LIMITED_DEPTH (110) but is 20 deg off the usual 85.
    reps = count(side_frames(reps=5, bottoms=[85, 86, 84, 85, 105]))
    assert len(reps) == 5
    assert [("DEPTH_INCONSISTENT" in r["form_flags"]) for r in reps] == [False] * 4 + [True]
    assert 19.0 <= reps[4]["depth_vs_usual_deg"] <= 21.0
    assert "LIMITED_DEPTH" not in reps[4]["form_flags"]


def test_depth_inconsistent_waits_for_reference_reps_and_defers_to_limited_depth():
    reps = count(side_frames(reps=5, bottoms=[85, 105, 85, 85, 85]))
    assert reps[1]["depth_vs_usual_deg"] is None and "DEPTH_INCONSISTENT" not in reps[1]["form_flags"]
    reps = count(side_frames(reps=5, bottoms=[85, 85, 85, 85, 114]))
    assert "LIMITED_DEPTH" in reps[4]["form_flags"]
    assert "DEPTH_INCONSISTENT" not in reps[4]["form_flags"]


# --- Fast descent ------------------------------------------------------------------------

def test_fast_descent_is_flagged_for_a_drop():
    reps = count(side_frames(down_frames=4, up_frames=20))  # about 0.1 s through the counting band at 25 fps
    assert len(reps) == 4
    assert all("FAST_DESCENT" in r["form_flags"] for r in reps)
    assert all(r["descent_seconds"] < 0.2 for r in reps)


def test_controlled_descent_is_not_flagged():
    reps = count(side_frames(down_frames=25))  # 1 s standing to bottom
    assert len(reps) == 4
    assert not any("FAST_DESCENT" in r["form_flags"] for r in reps)
    assert all(r["descent_seconds"] >= 0.2 for r in reps)


def test_coaching_flags_can_be_turned_off():
    reps = count(side_frames(heel_rise=0.05, down_frames=4, up_frames=20), coaching_flags=False)
    assert len(reps) == 4
    assert not any(NEW_FLAGS & set(r["form_flags"]) for r in reps)
