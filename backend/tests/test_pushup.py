"""Push-up mode: counting, gates and form-risk flags on synthetic side-view skeletons.

There is no recorded push-up clip yet, so every sequence here is built from
geometry: a fixed wrist and ankle, the elbow angle drives the shoulder height,
and the hip sits on (or off) the shoulder-ankle line.
"""
import math

import numpy as np
import pytest

from app.video_analysis.live import LiveSquatFeed
from app.video_analysis.movements import RECOGNIZER_LABELS, RecognizerGate, counter_class
from app.video_analysis.pushup import LivePushupCounter, PushupConfig, pushup_metrics

ASPECT = 16 / 9
UPPER, FORE = 0.15, 0.15
WRIST = (1.25, 0.85)   # frame-height units (x will be divided by ASPECT)
ANKLE = (0.35, 0.82)


def skeleton(elbow_deg, hip_offset=0.0, wrist=WRIST, ankle=ANKLE, side="left", upright=False, vis=0.95):
    d = math.sqrt(UPPER**2 + FORE**2 - 2 * UPPER * FORE * math.cos(math.radians(elbow_deg)))
    shoulder = (wrist[0], wrist[1] - d)
    # Elbow: intersection of circles around shoulder and wrist, on the feet side.
    mx, my = (shoulder[0] + wrist[0]) / 2, (shoulder[1] + wrist[1]) / 2
    h = math.sqrt(max(UPPER**2 - (d / 2) ** 2, 0.0))
    elbow = (mx - h, my)
    if upright:  # standing arm curl: body vertical, same arm motion
        ankle = (shoulder[0] - 0.02, shoulder[1] + 0.6)
    hip = ((shoulder[0] + ankle[0]) / 2, (shoulder[1] + ankle[1]) / 2 + hip_offset)
    pts = {"shoulder": shoulder, "elbow": elbow, "wrist": wrist, "hip": hip, "ankle": ankle}
    out = {f"{side}_{k}": (x / ASPECT, y, vis) for k, (x, y) in pts.items()}
    other = "right" if side == "left" else "left"
    out.update({f"{other}_{k}": (x / ASPECT, y, 0.2) for k, (x, y) in pts.items()})
    return out


def pushups(reps=5, bottom=80.0, down=15, up=15, top_hold=10, bottoms=None, **kw):
    frames = []
    for i in range(reps):
        b = bottoms[i] if bottoms else bottom
        trace = [170.0] * top_hold + list(np.linspace(170, b, down)) + list(np.linspace(b, 170, up))
        frames += [skeleton(a, **kw) for a in trace]
    return frames + [skeleton(170.0, **kw)] * top_hold


def run(frames, fps=25.0, **overrides):
    counter = LivePushupCounter(fps=fps, aspect=ASPECT, config=PushupConfig(**overrides))
    counts = [counter.update(f)["rep_count"] for f in frames]
    return counter, counts


def flags(counter):
    return [r["form_flags"] for r in counter.machine.reps]


# --- Measurements --------------------------------------------------------------------

def test_metrics_measure_elbow_body_line_and_hip_side():
    straight = pushup_metrics(skeleton(90.0), 0.55, ASPECT)
    assert straight["side"] == "left"
    assert straight["elbow_angle"] == pytest.approx(90.0, abs=0.5)
    assert straight["body_line"] == pytest.approx(180.0, abs=0.5)
    assert straight["body_tilt"] < 20
    sag = pushup_metrics(skeleton(90.0, hip_offset=0.08), 0.55, ASPECT)
    pike = pushup_metrics(skeleton(90.0, hip_offset=-0.08), 0.55, ASPECT)
    assert sag["hip_offset"] > 0 > pike["hip_offset"]
    assert sag["body_line"] < 165 and pike["body_line"] < 165


def test_hip_side_is_the_same_facing_either_way():
    def mirrored(offset):
        pts = skeleton(90.0, hip_offset=offset)
        return {k: (1 - x, y, v) for k, (x, y, v) in pts.items()}
    assert pushup_metrics(mirrored(0.08), 0.55, ASPECT)["hip_offset"] > 0
    assert pushup_metrics(mirrored(-0.08), 0.55, ASPECT)["hip_offset"] < 0


def test_metrics_use_the_visible_side_and_skip_hidden_bodies():
    right = pushup_metrics(skeleton(90.0, side="right"), 0.55, ASPECT)
    assert right["side"] == "right"
    assert pushup_metrics(skeleton(90.0, vis=0.3), 0.55, ASPECT) is None


# --- Counting and gates --------------------------------------------------------------

def test_clean_pushups_count_with_no_flags():
    counter, counts = run(pushups(reps=6))
    assert counter.rep_count == 6
    assert counts == sorted(counts)
    assert flags(counter) == [[]] * 6
    status = counter.status()
    assert status["movement"] == "pushup" and status["exercise"] == "Push-up"
    assert status["calibration_mode"] == "CALIBRATED"


def test_standing_arm_bends_are_not_pushups():
    counter, _ = run(pushups(reps=6, upright=True))
    assert counter.rep_count == 0
    assert counter.machine.log["rejected_not_plank"] >= 5


def test_hands_moving_is_not_a_pushup():
    frames = []
    for i, f in enumerate(pushups(reps=6)):
        shift = 0.12 if (i % 40) in range(18, 32) else 0.0  # hands slide mid-rep
        frames.append({k: ((x + shift) if k.endswith("wrist") else x, y, v) for k, (x, y, v) in f.items()})
    counter, _ = run(frames)
    assert counter.rep_count == 0
    assert counter.machine.log["rejected_hands_moved"] >= 5


def test_no_motion_counts_zero():
    counter, counts = run([skeleton(168 + (i % 3)) for i in range(200)])
    assert max(counts) == 0
    assert counter.status()["calibration_mode"] == "NO_SQUAT_MOTION"
    assert "elbow angle" in counter.thresholds["reason"]


# --- Flags ---------------------------------------------------------------------------

def test_shallow_pushups_are_flagged():
    counter, _ = run(pushups(reps=5, bottom=120.0))
    assert counter.rep_count == 5
    assert all("SHALLOW_PUSHUP" in f for f in flags(counter))


def test_sagging_and_piking_hips_are_flagged():
    sag, _ = run(pushups(reps=5, hip_offset=0.12))
    pike, _ = run(pushups(reps=5, hip_offset=-0.12))
    assert sag.rep_count == 5 and all("HIPS_SAGGING" in f and "HIPS_PIKING" not in f for f in flags(sag))
    assert pike.rep_count == 5 and all("HIPS_PIKING" in f and "HIPS_SAGGING" not in f for f in flags(pike))
    assert all(r["min_body_line_deg"] < 160 for r in sag.machine.reps)


def test_small_hip_offsets_are_not_flagged():
    counter, _ = run(pushups(reps=5, hip_offset=0.02))
    assert counter.rep_count == 5
    assert not any({"HIPS_SAGGING", "HIPS_PIKING"} & set(f) for f in flags(counter))


def test_depth_drift_flags_only_the_drifted_rep():
    counter, _ = run(pushups(reps=5, bottoms=[75, 76, 74, 75, 100]))
    assert counter.rep_count == 5
    assert [("DEPTH_INCONSISTENT" in f) for f in flags(counter)] == [False] * 4 + [True]


def test_fast_descent_is_flagged_and_controlled_is_not():
    fast, _ = run(pushups(reps=5, down=4, up=20))
    slow, _ = run(pushups(reps=5, down=25, up=20))
    assert fast.rep_count == 5 and all("FAST_DESCENT" in f for f in flags(fast))
    assert slow.rep_count == 5 and not any("FAST_DESCENT" in f for f in flags(slow))


# --- Mode registry and recognizer hook -----------------------------------------------

def test_feed_runs_pushup_mode_and_switches_cleanly():
    class Landmark:
        def __init__(self, x, y, v):
            self.x, self.y, self.visibility = x, y, v

    from app.video_analysis.analyzer import POSE_LANDMARK_NAMES

    def as_list(points):
        return [Landmark(*points.get(n, (0.0, 0.0, 0.0))) for n in POSE_LANDMARK_NAMES]

    feed = LiveSquatFeed(fps=25.0, mode="pushup")
    assert feed.warming_status("pushup")["exercise"] == "Detecting push-up..."
    for f in pushups(reps=4):
        status = feed.update(as_list(f), aspect=ASPECT)
    assert status["movement"] == "pushup" and status["rep_count"] == 4
    assert feed.set_mode("squat") is True
    assert feed.update(None)["movement"] == "squat"
    assert feed.set_mode("squat") is False
    with pytest.raises(ValueError):
        feed.set_mode("lunge")


def test_counter_registry_and_recognizer_labels():
    assert counter_class("pushup") is LivePushupCounter
    assert RECOGNIZER_LABELS["pushups"] == "pushup" and RECOGNIZER_LABELS["squats"] == "squat"
    assert RECOGNIZER_LABELS["lunges"] is None  # no mode yet: the recognizer cannot switch to it


def test_recognizer_gate_needs_a_confident_steady_label_and_no_rep_in_progress():
    gate = RecognizerGate(current="squat")
    assert gate.observe("pushups", 0.95, 0.0) is None
    assert gate.observe("pushups", 0.95, 1.0) is None          # not held long enough
    assert gate.observe("pushups", 0.95, 2.5, mid_rep=True) is None
    assert gate.observe("pushups", 0.95, 3.0) == "pushup"
    assert gate.current == "pushup"
    # Low confidence or unsupported labels reset the candidate and change nothing.
    assert gate.observe("squats", 0.5, 4.0) is None
    assert gate.observe("lunges", 0.99, 5.0) is None
    assert gate.observe("squats", 0.9, 6.0) is None
    assert gate.observe("lunges", 0.99, 7.0) is None           # breaks the squat run
    assert gate.observe("squats", 0.9, 8.5) is None
    assert gate.current == "pushup"
