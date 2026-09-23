"""Recorded-clip check for a movement mode.

  # 1. Video -> landmark fixture (landmarks only, no pixels):
  python clip_check.py extract push.mp4 --out tests/fixtures/clips/pushup_side.json.gz \
      --description "Side-view push-ups, Techno, 12 reps" [--start 3 --end 60]

  # 2. Check it against what was done (exit code 0 = pass):
  python clip_check.py check tests/fixtures/clips/pushup_side.json.gz --mode pushup --reps 12 \
      [--fault 11:HIPS_SAGGING --fault 12:SHALLOW_PUSHUP] [--save-expected] [--json out.json]

A video path also works for check (it is extracted in memory first).
--save-expected writes the expected result into the fixture so the test suite
re-checks it on every pull request.
"""
import argparse
import json
import sys
from pathlib import Path

from app.video_analysis.clip_check import (check_clip, extract_fixture, format_report, load_fixture, run_clip,
                                           save_fixture)
from app.video_analysis.movements import MOVEMENT_MODES


def parse_faults(values):
    faults = {}
    for value in values or []:
        rep, _, flag = value.partition(":")
        if not rep.isdigit() or not flag:
            raise SystemExit(f"--fault takes REP:FLAG, got {value!r}")
        faults.setdefault(int(rep), []).append(flag.strip())
    return faults


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    ex = sub.add_parser("extract", help="video -> landmark fixture")
    ex.add_argument("video")
    ex.add_argument("--out", required=True)
    ex.add_argument("--description", required=True)
    ex.add_argument("--start", type=float)
    ex.add_argument("--end", type=float)
    ck = sub.add_parser("check", help="run a fixture or video through a mode and compare")
    ck.add_argument("clip")
    ck.add_argument("--mode", required=True, choices=sorted(MOVEMENT_MODES))
    ck.add_argument("--reps", type=int, required=True, help="reps actually done")
    ck.add_argument("--fault", action="append", help="REP:FLAG a rep that should raise FLAG (repeatable)")
    ck.add_argument("--save-expected", action="store_true")
    ck.add_argument("--json", help="write the full result here")
    args = parser.parse_args(argv)

    if args.command == "extract":
        fixture = extract_fixture(args.video, args.description, args.start, args.end)
        path = save_fixture(fixture, args.out)
        posed = sum(f is not None for f in fixture["frames"])
        print(f"Wrote {path}: {len(fixture['frames'])} frames at {fixture['fps']} fps, pose in {posed}")
        return 0

    clip = Path(args.clip)
    fixture = load_fixture(clip) if clip.name.endswith(".json.gz") else extract_fixture(clip, clip.name)
    faults = parse_faults(args.fault)
    result = run_clip(args.mode, fixture)
    verdict = check_clip(result, args.reps, faults)
    print(format_report(result, verdict))
    if args.json:
        Path(args.json).write_text(json.dumps({"result": result, "verdict": verdict}, indent=2))
    if args.save_expected:
        if not clip.name.endswith(".json.gz"):
            raise SystemExit("--save-expected needs a fixture path, not a video")
        fixture["expected"] = {"mode": args.mode, "reps": args.reps, "faults": {str(k): v for k, v in faults.items()}}
        save_fixture(fixture, clip)
        print(f"Saved expected result into {clip}")
    return 0 if verdict["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
