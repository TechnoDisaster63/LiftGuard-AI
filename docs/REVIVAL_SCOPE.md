# LiftGuard-AI revival scope (Sep 23 - Oct 7, 2026)

## Frozen Track A demo

One offline flow: a **20-60 second, side-view squat video** becomes an annotated MP4, a per-rep CSV, and a JSON report. The report contains joint-angle measurements, transparent form-risk flags, and a fatigue indicator based on drift from the first three valid reps.

These outputs are coaching indicators. They are **not medical advice, a diagnosis, biomechanical validation, or an injury probability**.

## Acceptance gate

- A fresh Windows 11 / Python 3.11 setup completes using free local tooling.
- The same input produces the same rep count and report twice.
- Three consented clips (clean, intentional form breakdown, late-set degradation) finish without crashing.
- Poor visibility fails clearly instead of returning misleading zeros.
- Every successful run writes `annotated.mp4`, `report.json`, and `reps.csv`.
- CI covers angle calculations, deterministic rep analysis, output creation, and low-pose failure.

## Rep counting: per-session threshold calibration

People squat to different depths, and camera angle changes how deep a knee angle looks. A fixed rule ("bottom at 105 deg or less, standing at 155 deg or more") undercounted honest reps on a front-view clip, where bottoms showed as 110-125 deg.

Each video now sets its own thresholds from its knee-angle distribution (`calibrate_thresholds` in `backend/app/video_analysis/analyzer.py`):

- Upright level = 90th percentile knee angle. Deep level = 5th percentile. Observed range = upright - deep.
- If the observed range is under 35 deg, the video has no squat motion: **0 reps**, with the message "No squat movement detected ...". Thresholds are never shrunk until something counts.
- Bottom threshold = deep level + 35% of range, clamped to 70-140 deg. Standing threshold = upright level - 25% of range, clamped to 140-175 deg. They are kept at least 25 deg apart (hysteresis).
- Each counted rep must itself cover at least half the observed range (30 deg minimum), so partial pulses and bobbing are not counted as squats.
- A ~0.2 s running median removes single-frame pose glitches before counting; per-rep depth and range use the raw angles.
- The chosen thresholds and reason are written to `report.json` under `calibration` and shown on the annotated video.

This is calibration to the lifter, not loosening to force a count. Pose coverage under 50% still refuses to produce a report. `AnalysisConfig(calibrate=False)` restores the fixed rule; the golden fixture gives the same summary either way.

## Explicitly out of scope for this challenge demo

Arduino/laser feedback, face recognition, live multi-user streaming, clinical claims, injury probabilities, TCN/MC-dropout claims, multiple exercises, cloud deployment, and mobile apps. Existing modules remain experimental and are not evidence for this demo.

## Windows 11 / Python 3.11 setup

The old `mediapipe==0.10.3` pin is unavailable from the current package index. `0.10.5` is the minimum tested replacement and publishes a CPython 3.11 Windows x64 wheel.

```powershell
cd LiftGuard-AI\backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install mediapipe==0.10.5 opencv-contrib-python==4.8.0.74 numpy==1.24.3
python analyze_video.py C:\path\to\side-view-squats.mp4 --output outputs\demo
```

Recording: one person, full body visible, fixed side-view camera, stable light, no mirrors or bystanders, 20-60 seconds. Use bodyweight or a safe light load with supervision; do not deliberately perform unsafe loaded form for a demo.
