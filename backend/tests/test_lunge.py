"""Lunge mode: counting, gates and form-risk flags on synthetic side-view skeletons.

There is no recorded lunge clip yet, so every sequence here is built from
geometry: both ankles stay fixed, the hip height drives both knees (two-link
legs), and the shoulder sits above the hip at a chosen trunk lean.
"""
import math

import numpy as np
import pytest

from app.video_analysis.live import LiveSquatFeed
from app.video_analysis.lunge import LiveLungeCounter, LungeConfig, lunge_metrics
from app.video_analysis.movements import RECOGNIZER_LABELS, RecognizerGate, counter_class

ASPECT = 16 / 9
THIGH = SHIN = 0.24
TORSO = 0.30
FRONT_ANKLE = (1.00, 0.90)   # frame-height units (x will be divided by ASPECT)
BACK_ANKLE = (0.62, 0.88)
HIP_X = 0.80
TOP_Y, BOTTOM_Y = 0.465, 0.66


def _knee(hip, ankle, forward):
    """Two-link leg: the knee on the side of the hip-ankle line given by ``forward`` (+1 front of it)."""
    d = min(math.dist(hip, ankle), THIGH + SHIN - 1e-6)
    a = d / 2
    h = math.sqrt(max(THIGH**2 - a**2, 0.0))
    mx, my = hip[0] + (ankle[0] - hip[0]) * a / d, hip[1] + (ankle[1] - hip[1]) * a / d
    ux, uy = (ankle[0] - hip[0]) / d, (ankle[1] - hip[1]) / d
    c1 = (mx - uy * h, my + ux * h)
    c2 = (mx + uy * h, my - ux * h)
    return max(c1, c2) if forward > 0 else min(c1, c2, key=lambda c: c[0])


def skeleton(hip_y, hip_x=HIP_X, lean_deg=10.0, front=FRONT_ANKLE, back=BACK_ANKLE, toe=0.07, vis=0.95,
             mirror=False):
    hip = (hip_x, hip_y)
    fk = _knee(hip, front, +1)
    bk = _knee(hip, back, +1)
    shoulder = (hip_x + TORSO * math.sin(math.radians(lean_deg)), hip_y - TORSO * math.cos(math.radians(lean_deg)))
    pts = {
        "left_hip": hip, "left_knee": fk, "left_ankle": front, "left_foot_index": (front[0] + toe, front[1] + 0.01),
        "left_shoulder": shoulder,
        "right_hip": hip, "right_knee": bk, "right_ankle": back, "right_shoulder": shoulder,
    }
    out = {}
    for k, (x, y) in pts.items():
        v = vis if k.startswith("left") else min(vis, 0.6)
        nx = x / ASPECT
        out[k] = ((1 - nx) if mirror else nx, y, v)
    return out


def lunges(reps=5, bottom=BOTTOM_Y, down=15, up=15, top_hold=10, bottoms=None, **kw):
    frames = []
    for i in range(reps):
        b = bottoms[i] if bottoms else bottom
        trace = [TOP_Y] * top_hold + list(np.linspace(TOP_Y, b, down)) + list(np.linspace(b, TOP_Y, up))
        frames += [skeleton(y, **kw) for y in trace]
    return frames + [skeleton(TOP_Y, **kw)] * top_hold


def run(frames, fps=25.0, **overrides):
    counter = LiveLungeCounter(fps=fps, aspect=ASPECT, config=LungeConfig(**overrides))
    counts = [counter.update(f)["rep_count"] for f in frames]
    return counter, counts


def flags(counter):
    return [r["form_flags"] for r in counter.machine.reps]


# --- Measurements --------------------------------------------------------------------

def test_metrics_find_the_front_leg_and_measure_the_split():
    top = lunge_metrics(skeleton(TOP_Y), LungeConfig(), ASPECT)
    bottom = lunge_metrics(skeleton(BOTTOM_Y), LungeConfig(), ASPECT)
    assert top["front_side"] == bottom["front_side"] == "left"
    assert top["knee_angle"] > 165 and bottom["knee_angle"] < 90
    assert bottom["split_ratio"] > 0.5
    assert bottom["trunk_lean"] == pytest.approx(10.0, abs=0.5)
    assert bottom["knee_ahead_ratio"] < 0  # knee behind the toes in a normal lunge


def test_knee_to_toe_distance_is_the_same_facing_either_way():
    normal = lunge_metrics(skeleton(BOTTOM_Y, hip_x=0.85, toe=0.02), LungeConfig(), ASPECT)
    mirrored = lunge_metrics(skeleton(BOTTOM_Y, hip_x=0.85, toe=0.02, mirror=True), LungeConfig(), ASPECT)
    assert normal["knee_ahead_ratio"] > 0.1
    assert mirrored["knee_ahead_ratio"] == pytest.approx(normal["knee_ahead_ratio"], abs=1e-3)


def test_hidden_legs_or_trunk_give_no_measurement():
    assert lunge_metrics(skeleton(BOTTOM_Y, vis=0.2), LungeConfig(), ASPECT) is None
    no_trunk = {k: v for k, v in skeleton(BOTTOM_Y).items() if "shoulder" not in k}
    assert lunge_metrics(no_trunk, LungeConfig(), ASPECT) is None


# --- Counting and gates --------------------------------------------------------------

def test_clean_lunges_count_with_no_flags():
    counter, counts = run(lunges(reps=6))
    assert counter.rep_count == 6
    assert counts == sorted(counts)
    assert flags(counter) == [[]] * 6
    status = counter.status()
    assert status["movement"] == "lunge" and status["exercise"] == "Lunge"
    assert status["calibration_mode"] == "CALIBRATED"
    rep = counter.machine.reps[0]
    assert rep["front_leg"] == "left" and rep["min_knee_angle"] < 90


def test_squats_with_feet_side_by_side_are_not_lunges():
    counter, _ = run(lunges(reps=6, front=(0.90, 0.90), back=(0.86, 0.90), hip_x=0.72))
    assert counter.rep_count == 0
    assert counter.machine.log["rejected_no_split_stance"] >= 5


def test_a_foot_sliding_during_the_rep_is_not_counted():
    frames = []
    for _ in range(6):  # the front foot slides 0.14 forward on the way down, then steps back
        down = np.linspace(TOP_Y, BOTTOM_Y, 15)
        frames += [skeleton(TOP_Y, front=(0.86, 0.90))] * 10
        frames += [skeleton(y, front=(0.86 + 0.01 * k, 0.90)) for k, y in enumerate(down)]
        frames += [skeleton(y) for y in np.linspace(BOTTOM_Y, TOP_Y, 15)]
    counter, _ = run(frames + [skeleton(TOP_Y)] * 10)
    assert counter.rep_count == 0
    assert counter.machine.log["rejected_feet_moved"] >= 5


def test_no_motion_counts_zero():
    counter, counts = run([skeleton(TOP_Y + 0.004 * (i % 3)) for i in range(200)])
    assert max(counts) == 0
    assert counter.status()["calibration_mode"] == "NO_SQUAT_MOTION"
    assert "front knee angle" in counter.thresholds["reason"]


# --- Flags ---------------------------------------------------------------------------

def test_shallow_lunges_are_flagged():
    counter, _ = run(lunges(reps=5, bottom=0.53))
    assert counter.rep_count == 5
    assert all("SHALLOW_LUNGE" in f for f in flags(counter))


def test_forward_lean_is_flagged_and_upright_is_not():
    lean, _ = run(lunges(reps=5, lean_deg=40.0))
    upright, _ = run(lunges(reps=5, lean_deg=15.0))
    assert lean.rep_count == 5 and all("FORWARD_LEAN" in f for f in flags(lean))
    assert all(r["max_trunk_lean_deg"] > 30 for r in lean.machine.reps)
    assert upright.rep_count == 5 and not any("FORWARD_LEAN" in f for f in flags(upright))


def test_knee_past_toes_reports_the_measured_distance():
    forward, _ = run(lunges(reps=5, hip_x=0.85, toe=0.02))
    assert forward.rep_count == 5 and all("KNEE_PAST_TOES" in f for f in flags(forward))
    assert all(r["knee_ahead_of_toes_ratio"] > 0.1 for r in forward.machine.reps)


def test_depth_drift_flags_only_the_drifted_rep():
    counter, _ = run(lunges(reps=5, bottoms=[0.66, 0.665, 0.66, 0.655, 0.60]))
    assert counter.rep_count == 5
    assert [("DEPTH_INCONSISTENT" in f) for f in flags(counter)] == [False] * 4 + [True]


def test_fast_descent_is_flagged_and_controlled_is_not():
    fast, _ = run(lunges(reps=5, down=4, up=20))
    slow, _ = run(lunges(reps=5, down=25, up=20))
    assert fast.rep_count == 5 and all("FAST_DESCENT" in f for f in flags(fast))
    assert slow.rep_count == 5 and not any("FAST_DESCENT" in f for f in flags(slow))


# --- Mode registry and recognizer hook -----------------------------------------------

def test_feed_runs_lunge_mode():
    class Landmark:
        def __init__(self, x, y, v):
            self.x, self.y, self.visibility = x, y, v

    from app.video_analysis.analyzer import POSE_LANDMARK_NAMES

    def as_list(points):
        return [Landmark(*points.get(n, (0.0, 0.0, 0.0))) for n in POSE_LANDMARK_NAMES]

    feed = LiveSquatFeed(fps=25.0, mode="lunge")
    assert feed.warming_status("lunge")["exercise"] == "Detecting lunge..."
    for f in lunges(reps=4):
        status = feed.update(as_list(f), aspect=ASPECT)
    assert status["movement"] == "lunge" and status["rep_count"] == 4


def test_lunge_is_registered_but_not_selectable_and_the_recognizer_can_name_it():
    from app.video_analysis.movements import MOVEMENT_MODES, is_selectable

    assert counter_class("lunge") is LiveLungeCounter
    assert MOVEMENT_MODES["lunge"]["validated"] is False and not is_selectable("lunge")
    assert RECOGNIZER_LABELS["lunges"] == "lunge"
    gate = RecognizerGate(current="squat")
    assert gate.observe("lunges", 0.9, 0.0) is None
    assert gate.observe("lunges", 0.9, 2.5) == "lunge"
