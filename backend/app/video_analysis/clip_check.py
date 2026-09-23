"""Recorded-clip check for movement modes (the release gate's step 1).

Turns a recorded video into a landmark fixture (landmarks only, no pixels),
streams it through the mode's live counter exactly as the app would, and
compares the result with what the person actually did: how many reps, and
which reps had which fault. A mode flips to ``validated=True`` only after its
clip passes here.

Fixtures are gzipped JSON: ``{description, fps, aspect, keys, frames,
expected?}``. Each frame is a flat list of x, y, visibility per key, or null
when no pose was found. ``expected`` holds ``{mode, reps, faults}``, where
``faults`` maps a rep number (as a string) to the flags that rep should
raise; every other rep should raise none.
"""
from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Callable, Mapping, Sequence

from .movements import MOVEMENT_MODES, counter_class

# Body points every mode uses; faces and hands are left out of fixtures.
FIXTURE_KEYS = tuple(
    f"{side}_{part}"
    for side in ("left", "right")
    for part in ("shoulder", "elbow", "wrist", "hip", "knee", "ankle", "heel", "foot_index")
)
ALIASES = ("shoulder", "hip", "knee", "ankle")
MIN_POSE_COVERAGE = 0.5


def extract_fixture(video_path: str | Path, description: str, start: float | None = None, end: float | None = None,
                    detector: Callable | None = None) -> dict:
    """Run pose detection over a video and return a landmark fixture (no pixels kept)."""
    import cv2

    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise ValueError(f"Could not open video {video_path}")
    fps = capture.get(cv2.CAP_PROP_FPS) or 25.0
    width = capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 16.0
    height = capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 9.0
    if detector is None:
        from .analyzer import MediaPipePoseDetector
        detector = MediaPipePoseDetector()
    frames: list[list[float] | None] = []
    index = 0
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            t = index / fps
            index += 1
            if start is not None and t < start:
                continue
            if end is not None and t > end:
                break
            points = detector(frame)
            if not points:
                frames.append(None)
                continue
            row: list[float] = []
            for key in FIXTURE_KEYS:
                x, y, v = points.get(key, (0.0, 0.0, 0.0))
                row += [round(float(x), 4), round(float(y), 4), round(float(v), 3)]
            frames.append(row)
    finally:
        capture.release()
        close = getattr(detector, "close", None)
        if close:
            close()
    return {"description": description, "fps": round(float(fps), 3), "aspect": round(width / height, 4),
            "keys": list(FIXTURE_KEYS), "frames": frames}


def save_fixture(fixture: dict, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt") as handle:
        json.dump(fixture, handle, separators=(",", ":"))
    return path


def load_fixture(path: str | Path) -> dict:
    with gzip.open(path, "rt") as handle:
        return json.load(handle)


def fixture_frames(fixture: Mapping) -> list[dict | None]:
    """Named points per frame, with the left-side aliases the squat engine reads."""
    keys = fixture["keys"]
    frames: list[dict | None] = []
    for row in fixture["frames"]:
        if row is None:
            frames.append(None)
            continue
        points = {key: tuple(row[i * 3:i * 3 + 3]) for i, key in enumerate(keys)}
        for alias in ALIASES:
            if f"left_{alias}" in points:
                points[alias] = points[f"left_{alias}"]
        frames.append(points)
    return frames


def run_clip(mode: str, fixture: Mapping) -> dict:
    """Stream a fixture through the mode's live counter and collect what it reported."""
    counter = counter_class(mode)(fps=float(fixture["fps"]), aspect=float(fixture.get("aspect", 16 / 9)))
    frames = fixture_frames(fixture)
    status: dict = {}
    for points in frames:
        status = counter.update(points)
    posed = sum(p is not None for p in frames)
    reps = [
        {"rep": r["rep"], "start_seconds": r["start_seconds"], "end_seconds": r["end_seconds"],
         "form_flags": list(r.get("form_flags", []))}
        for r in counter.machine.reps
    ]
    return {
        "mode": mode,
        "view": MOVEMENT_MODES[mode]["view"],
        "frames": len(frames),
        "pose_coverage": round(posed / len(frames), 3) if frames else 0.0,
        "calibration_mode": status.get("calibration_mode"),
        "thresholds": {k: v for k, v in getattr(counter, "thresholds", {}).items() if k != "mode"},
        "rep_count": len(reps),
        "reps": reps,
        "rep_details": [dict(r) for r in counter.machine.reps],
        "rejected": dict(getattr(counter.machine, "log", {})),
    }


def check_clip(result: Mapping, expected_reps: int, faults: Mapping[int, Sequence[str]] | None = None) -> dict:
    """Compare a run with what was actually done. Every rep not in ``faults`` should raise no flags."""
    faults = {int(k): set(v) for k, v in (faults or {}).items()}
    problems: list[str] = []
    if result["pose_coverage"] < MIN_POSE_COVERAGE:
        problems.append(f"pose found in only {result['pose_coverage']:.0%} of frames (need {MIN_POSE_COVERAGE:.0%})")
    if result["rep_count"] != expected_reps:
        problems.append(f"counted {result['rep_count']} reps, expected {expected_reps}")
    flag_rows = []
    for rep in result["reps"]:
        want = faults.get(rep["rep"], set())
        got = set(rep["form_flags"])
        row = {"rep": rep["rep"], "expected": sorted(want), "got": sorted(got),
               "false_flags": sorted(got - want), "missed_flags": sorted(want - got)}
        flag_rows.append(row)
        if row["false_flags"]:
            problems.append(f"rep {rep['rep']}: flags not expected {row['false_flags']}")
        if row["missed_flags"]:
            problems.append(f"rep {rep['rep']}: expected flags missing {row['missed_flags']}")
    for number in sorted(faults):
        if number > result["rep_count"]:
            problems.append(f"rep {number} (expected {sorted(faults[number])}) was not counted")
    return {"passed": not problems, "problems": problems, "flags": flag_rows}


def format_report(result: Mapping, verdict: Mapping) -> str:
    lines = [
        f"Mode: {result['mode']} (built for a {result['view']} view)",
        f"Frames: {result['frames']}, pose found in {result['pose_coverage']:.0%}",
        f"Calibration: {result['calibration_mode']}",
        f"Reps counted: {result['rep_count']}",
        f"Rejected look-alikes: {result['rejected']}",
    ]
    for row, rep in zip(verdict["flags"], result["reps"]):
        mark = "ok" if not (row["false_flags"] or row["missed_flags"]) else "MISMATCH"
        lines.append(f"  rep {rep['rep']:>2}  {rep['start_seconds']:7.2f}-{rep['end_seconds']:7.2f}s  "
                     f"flags {row['got'] or '-'}  expected {row['expected'] or '-'}  {mark}")
    lines.append("RESULT: PASS" if verdict["passed"] else "RESULT: FAIL")
    lines += [f"  - {p}" for p in verdict["problems"]]
    return "\n".join(lines)
