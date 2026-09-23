"""Jumping-jacks mode: counting, gates and form-risk flags on synthetic front-view skeletons.

There is no recorded jumping-jacks clip yet, so every sequence here is built
from geometry: one phase value (0 = arms down, feet together; 1 = arms up,
feet apart) sets both arm angles and the ankle spacing.
"""
import math

import numpy as np
import pytest

from app.video_analysis.jumping_jacks import JacksConfig, LiveJacksCounter, jacks_metrics
from app.video_analysis.live import LiveSquatFeed
from app.video_analysis.movements import MOVEMENT_MODES, RECOGNIZER_LABELS, RecognizerGate, counter_class, is_selectable

ASPECT = 16 / 9
CX = 0.9           # body centre, frame-height units
ARM = 0.25


def skeleton(t, peak_arm=170.0, feet_open=0.11, one_arm=False, vis=0.95):
    arm = 15.0 + t * (peak_arm - 15.0)
    half = 0.04 + t * (feet_open - 0.04)
    pts = {}
    for side, sign in (("left", 1), ("right", -1)):
        a = 15.0 if (one_arm and side == "right") else arm
        sx, sy = CX + sign * 0.07, 0.35
        pts[f"{side}_shoulder"] = (sx, sy)
        pts[f"{side}_wrist"] = (sx + sign * ARM * math.sin(math.radians(a)), sy + ARM * math.cos(math.radians(a)))
        pts[f"{side}_hip"] = (CX + sign * 0.04, 0.60)
        pts[f"{side}_ankle"] = (CX + sign * half, 0.90)
    return {k: (x / ASPECT, y, vis) for k, (x, y) in pts.items()}


def jacks(reps=8, up=6, down=6, rest=4, cycles=None, **kw):
    frames = [skeleton(0.0, **kw)] * 10
    for i in range(reps):
        u = cycles[i] if cycles else up
        frames += [skeleton(t, **kw) for t in np.linspace(0, 1, u)]
        frames += [skeleton(t, **kw) for t in np.linspace(1, 0, down)]
        frames += [skeleton(0.0, **kw)] * rest
    return frames + [skeleton(0.0, **kw)] * 10


def run(frames, fps=25.0, **overrides):
    counter = LiveJacksCounter(fps=fps, aspect=ASPECT, config=JacksConfig(**overrides))
    counts = [counter.update(f)["rep_count"] for f in frames]
    return counter, counts


def flags(counter):
    return [r["form_flags"] for r in counter.machine.reps]


def test_metrics_measure_both_arms_and_foot_spacing():
    down = jacks_metrics(skeleton(0.0), JacksConfig(), ASPECT)
    up = jacks_metrics(skeleton(1.0), JacksConfig(), ASPECT)
    assert down["arm_angle"] < 30 and up["arm_angle"] > 150
    assert up["left_arm"] == pytest.approx(up["right_arm"], abs=1)
    assert down["ankle_gap"] == pytest.approx(1.0, abs=0.05) and up["ankle_gap"] > 2.5
    assert jacks_metrics(skeleton(0.5, vis=0.2), JacksConfig(), ASPECT) is None


def test_clean_jumping_jacks_count_with_no_flags():
    counter, counts = run(jacks(reps=8))
    assert counter.rep_count == 8
    assert counts == sorted(counts)
    assert flags(counter) == [[]] * 8
    status = counter.status()
    assert status["movement"] == "jumping_jacks" and status["exercise"] == "Jumping jacks"


def test_arm_raises_without_a_jump_are_not_counted():
    counter, _ = run(jacks(reps=8, feet_open=0.04))
    assert counter.rep_count == 0
    assert counter.machine.log["rejected_feet_did_not_open"] >= 6


def test_one_arm_is_not_a_jumping_jack():
    counter, _ = run(jacks(reps=8, one_arm=True, peak_arm=175.0))
    assert counter.rep_count == 0
    assert counter.machine.log["rejected_arms_uneven"] >= 6


def test_standing_still_counts_zero():
    counter, counts = run([skeleton(0.02 * (i % 3)) for i in range(200)])
    assert max(counts) == 0
    assert "arm angle" in counter.thresholds["reason"]


def test_arms_short_of_overhead_are_flagged():
    counter, _ = run(jacks(reps=6, peak_arm=120.0))
    assert counter.rep_count == 6
    assert all("ARMS_NOT_OVERHEAD" in f for f in flags(counter))


def test_narrow_feet_are_flagged():
    counter, _ = run(jacks(reps=6, feet_open=0.065))
    assert counter.rep_count == 6
    assert all("FEET_NOT_APART" in f and "ARMS_NOT_OVERHEAD" not in f for f in flags(counter))


def test_tempo_drift_flags_the_slow_rep():
    counter, _ = run(jacks(reps=6, cycles=[6, 6, 6, 6, 6, 20]))
    assert counter.rep_count == 6
    assert [("TEMPO_DRIFT" in f) for f in flags(counter)] == [False] * 5 + [True]


def test_feed_runs_jumping_jacks_mode():
    class Landmark:
        def __init__(self, x, y, v):
            self.x, self.y, self.visibility = x, y, v

    from app.video_analysis.analyzer import POSE_LANDMARK_NAMES

    feed = LiveSquatFeed(fps=25.0, mode="jumping_jacks")
    assert feed.warming_status("jumping_jacks")["exercise"] == "Detecting jumping jack..."
    for f in jacks(reps=5):
        status = feed.update([Landmark(*f.get(n, (0.0, 0.0, 0.0))) for n in POSE_LANDMARK_NAMES], aspect=ASPECT)
    assert status["movement"] == "jumping_jacks" and status["rep_count"] == 5


def test_registered_front_view_not_selectable_and_recognizer_can_name_it():
    assert counter_class("jumping_jacks") is LiveJacksCounter
    assert MOVEMENT_MODES["jumping_jacks"]["view"] == "front"
    assert MOVEMENT_MODES["jumping_jacks"]["validated"] is False and not is_selectable("jumping_jacks")
    assert RECOGNIZER_LABELS["jumping_jacks"] == "jumping_jacks"
    gate = RecognizerGate(current="squat")
    assert gate.observe("jumping_jacks", 0.9, 0.0) is None
    assert gate.observe("jumping_jacks", 0.9, 2.5) == "jumping_jacks"
