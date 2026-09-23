"""Recorded-clip check pipeline: fixture round trip, run, verdict, CLI, and every committed clip fixture."""
from pathlib import Path

import numpy as np
import pytest

import clip_check as cli
from app.video_analysis.clip_check import (FIXTURE_KEYS, check_clip, extract_fixture, format_report, load_fixture,
                                           run_clip, save_fixture)

from . import test_jumping_jacks as jj
from . import test_lunge as lg
from . import test_pushup as pu

FIXTURES = Path(__file__).parent / "fixtures"
CLIPS = sorted((FIXTURES / "clips").glob("*.json.gz"))


def as_fixture(frames, aspect, fps=25.0):
    rows = []
    for points in frames:
        row = []
        for key in FIXTURE_KEYS:
            row += list(points.get(key, (0.0, 0.0, 0.0)))
        rows.append(row)
    return {"description": "synthetic", "fps": fps, "aspect": aspect, "keys": list(FIXTURE_KEYS), "frames": rows}


# --- Committed clip fixtures (each carries its expected result) -------------------

@pytest.mark.parametrize("path", CLIPS, ids=[p.name for p in CLIPS])
def test_committed_clip_fixture_passes(path):
    fixture = load_fixture(path)
    expected = fixture["expected"]
    result = run_clip(expected["mode"], fixture)
    verdict = check_clip(result, expected["reps"], expected.get("faults"))
    assert verdict["passed"], format_report(result, verdict)


def test_real_front_view_squat_clip_through_the_pipeline():
    """The one real clip we have. Squat mode is built for a side view; from the front the knee
    angle is foreshortened, so LIMITED_DEPTH fires on most of these normal reps. The pipeline
    must report that as a failure, while the count and the four coaching flags stay right."""
    fixture = load_fixture(FIXTURES / "front_view_squats.json.gz")
    result = run_clip("squat", fixture)
    assert result["rep_count"] == 15 and result["pose_coverage"] > 0.9
    coaching = {"KNEES_CAVING", "HEELS_LIFTING", "DEPTH_INCONSISTENT", "FAST_DESCENT"}
    assert not any(coaching & set(r["form_flags"]) for r in result["reps"])
    verdict = check_clip(result, 15)
    limited = [r["rep"] for r in result["reps"] if "LIMITED_DEPTH" in r["form_flags"]]
    assert limited and not verdict["passed"]
    assert verdict["problems"] == [f"rep {n}: flags not expected ['LIMITED_DEPTH']" for n in limited]


# --- New modes, synthetic stand-ins until the real clips arrive -------------------

@pytest.mark.parametrize("mode, frames, aspect, faults", [
    ("pushup", pu.pushups(reps=4) + pu.pushups(reps=1, hip_offset=0.12), pu.ASPECT, {5: ["HIPS_SAGGING"]}),
    ("lunge", lg.lunges(reps=5, bottoms=[0.66, 0.665, 0.66, 0.655, 0.60]), lg.ASPECT, {5: ["DEPTH_INCONSISTENT"]}),
    ("jumping_jacks", jj.jacks(reps=6), jj.ASPECT, {}),
])
def test_synthetic_clips_pass_with_their_faults(tmp_path, mode, frames, aspect, faults):
    path = save_fixture(as_fixture(frames, aspect), tmp_path / f"{mode}.json.gz")
    result = run_clip(mode, load_fixture(path))
    verdict = check_clip(result, 5 if mode != "jumping_jacks" else 6, faults)
    assert verdict["passed"], format_report(result, verdict)


def test_wrong_count_false_flags_and_missed_flags_all_fail():
    result = run_clip("pushup", as_fixture(pu.pushups(reps=5, bottom=120.0), pu.ASPECT))
    assert all("SHALLOW_PUSHUP" in r["form_flags"] for r in result["reps"])
    verdict = check_clip(result, 6, {1: ["HIPS_SAGGING"]})
    assert not verdict["passed"]
    text = " ".join(verdict["problems"])
    assert "counted 5 reps, expected 6" in text
    assert "flags not expected ['SHALLOW_PUSHUP']" in text
    assert "expected flags missing ['HIPS_SAGGING']" in text
    assert "RESULT: FAIL" in format_report(result, verdict)


def test_low_pose_coverage_fails():
    fixture = as_fixture(pu.pushups(reps=5), pu.ASPECT)
    fixture["frames"] = [row if i % 3 == 0 else None for i, row in enumerate(fixture["frames"])]
    verdict = check_clip(run_clip("pushup", fixture), 5)
    assert not verdict["passed"] and any("pose found in only" in p for p in verdict["problems"])


# --- Video extraction and CLI -----------------------------------------------------

def test_extract_reads_a_video_and_keeps_only_landmarks(tmp_path):
    import cv2

    video = tmp_path / "clip.avi"
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"MJPG"), 20.0, (64, 36))
    for _ in range(40):
        writer.write(np.zeros((36, 64, 3), dtype=np.uint8))
    writer.release()
    calls = []

    def detector(frame):
        calls.append(frame.shape)
        return None if len(calls) % 4 == 0 else {"left_hip": (0.5, 0.6, 0.9)}

    fixture = extract_fixture(video, "test", start=0.5, detector=detector)
    assert fixture["fps"] == pytest.approx(20.0) and fixture["aspect"] == pytest.approx(64 / 36, abs=1e-3)
    assert len(fixture["frames"]) == 30 == len(calls)
    assert sum(f is None for f in fixture["frames"]) == 7
    row = next(f for f in fixture["frames"] if f)
    assert len(row) == 3 * len(FIXTURE_KEYS)
    i = FIXTURE_KEYS.index("left_hip") * 3
    assert row[i:i + 3] == [0.5, 0.6, 0.9]


def test_cli_check_exit_codes_and_save_expected(tmp_path, capsys):
    path = save_fixture(as_fixture(jj.jacks(reps=6), jj.ASPECT), tmp_path / "jacks.json.gz")
    assert cli.main(["check", str(path), "--mode", "jumping_jacks", "--reps", "7"]) == 1
    assert "RESULT: FAIL" in capsys.readouterr().out
    assert cli.main(["check", str(path), "--mode", "jumping_jacks", "--reps", "6", "--save-expected",
                     "--json", str(tmp_path / "out.json")]) == 0
    assert "RESULT: PASS" in capsys.readouterr().out
    assert load_fixture(path)["expected"] == {"mode": "jumping_jacks", "reps": 6, "faults": {}}
    assert (tmp_path / "out.json").exists()
    with pytest.raises(SystemExit):
        cli.parse_faults(["x:FLAG"])
    assert cli.parse_faults(["3:HIPS_SAGGING", "3:FAST_DESCENT"]) == {3: ["HIPS_SAGGING", "FAST_DESCENT"]}
