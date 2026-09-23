"""Live-path squat counting: the streaming counter must agree with the offline analyzer."""
import gzip
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.video_analysis.analyzer import POSE_LANDMARK_NAMES
from app.video_analysis.live import LiveSquatCounter, LiveSquatFeed

from .test_video_analysis import count_fixture

FIXTURES = Path(__file__).parent / "fixtures"


def fixture_points(name):
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
        frames.append(points)
    return data["fps"], data.get("aspect", 1.0), frames


def stream(name):
    fps, aspect, frames = fixture_points(name)
    counter = LiveSquatCounter(fps=fps, aspect=aspect)
    counts = [counter.update(points)["rep_count"] for points in frames]
    return counter, counts


def test_front_view_squats_are_counted_live():
    counter, counts = stream("front_view_squats.json.gz")
    assert counter.rep_count == 15
    assert counts == sorted(counts)  # the live count never goes backwards
    status = counter.status()
    assert status["exercise"] == "Squat"
    assert status["calibration_mode"] == "CALIBRATED"


def test_live_reps_line_up_with_offline_reps():
    counter, _ = stream("front_view_squats.json.gz")
    offline, _ = count_fixture("front_view_squats.json.gz")
    assert len(offline) == len(counter.machine.reps)
    for live, ref in zip(counter.machine.reps, offline):
        assert abs(live["start_seconds"] - ref["start_seconds"]) <= 0.5
        assert abs(live["end_seconds"] - ref["end_seconds"]) <= 0.5


@pytest.mark.parametrize("name", ["a_position_hold.json.gz", "broad_jumps.json.gz"])
def test_non_squats_stay_at_zero_live(name):
    counter, counts = stream(name)
    assert max(counts) == 0
    assert counter.status()["exercise"] == "Detecting squat..."
    assert counter.machine.log["rejected_feet_moved"] >= 1


def test_no_pose_frames_do_not_crash_or_count():
    counter = LiveSquatCounter(fps=25)
    for _ in range(100):
        status = counter.update(None)
    assert status["rep_count"] == 0
    assert status["calibration_mode"] == "WARMING_UP"
    assert status["phase"] == "idle"


def fixture_landmarks(frames):
    """Fixture frames as MediaPipe-style landmark lists (the fixture stores a landmark subset)."""
    names = tuple(k for k in next(p for p in frames if p) if k.startswith(("left_", "right_")))
    lists = [[SimpleNamespace(x=p[n][0], y=p[n][1], visibility=p[n][2]) for n in names] if p else None
             for p in frames]
    return names, lists


def test_feed_with_file_fps_matches_counter():
    fps, aspect, frames = fixture_points("front_view_squats.json.gz")
    names, lists = fixture_landmarks(frames)
    feed = LiveSquatFeed(fps=fps, landmark_names=names)
    for lms in lists:
        status = feed.update(lms, aspect)
    assert feed.fps == fps
    assert status["rep_count"] == 15


def test_feed_measures_webcam_rate_and_replays_probe_frames():
    fps, aspect, frames = fixture_points("front_view_squats.json.gz")
    names, lists = fixture_landmarks(frames)
    tick = iter(i / fps for i in range(len(frames) + 1))
    feed = LiveSquatFeed(fps=None, clock=lambda: next(tick), landmark_names=names)
    statuses = [feed.update(lms, aspect) for lms in lists]
    assert statuses[0]["calibration_mode"] == "WARMING_UP"
    assert feed.fps == pytest.approx(fps, rel=0.01)
    assert statuses[-1]["rep_count"] == 15


def test_default_names_are_mediapipe_order():
    assert LiveSquatFeed().names == POSE_LANDMARK_NAMES
