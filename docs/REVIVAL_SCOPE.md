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

### Leg gates: feet planted, hips lowered, both knees bent

Knee angle on one leg cannot tell a squat from lifting that leg (a held sprint "A-position" counted as a rep), and a deep dip before or after a jump looks like a squat (broad jumps counted 2 reps). After a candidate rep passes the range and duration checks, `_leg_gate` applies three checks. Leg length below means standing hip-to-ankle height (90th percentile over the session).

- **Feet planted:** each visible ankle must stay within 25% of leg length of its spot just before the rep (median of the previous 0.3 s). The x distance is scaled by the frame's width/height so both axes use the same units. On the dev clips, real squats moved the ankles 1-2% of leg length and broad jumps moved them 57-79%.
- **Hip drop:** the hips must drop by at least 15% of leg length between the preceding standing phase and the bottom.
- **Other knee:** when the other leg's hip, knee, and ankle are visible, its deepest knee angle in the rep must be within 20 deg of the bottom threshold. If the other leg is hidden (common in a true side view), this check is skipped.

`report.json` lists rejected candidates by reason under `rep_gates` and writes the limits below under `known_limits`. Each counted rep records `ankle_shift_ratio`, `hip_drop_ratio`, and `other_min_knee_angle`.

**Known limits**

- A camera cut or zoom moves every landmark at once. It can fake a hip drop. The feet check usually rejects a rep that spans a cut (the A-position regression is rejected this way), but it can also reject a real rep that spans one. Recordings should be one continuous shot.
- A squat-like dip done in place, with the feet not moving (for example a vertical jump landing on the same spot), can still pass.
- Angles are 2D image-plane angles, not 3D joint angles.
- Thresholds were checked on third-party dev clips and synthetic tests, not tuned to a target count. Side-view clips from the user are still needed.

## Live path: same squat counter as the offline report

The live session (`/ws/live`, Live page) used to count reps with the legacy `ExerciseTracker`, which never recognized the squat clip (exercise stayed "Unknown", 0 reps). Live reps, phase, and the exercise label now come from `app/video_analysis/live.py`, which runs the same per-frame metrics, rep state machine (`RepStateMachine`), calibration, and leg gates as the offline analyzer. Differences that come from streaming:

- **Smoothing looks back only.** Knee angles use a trailing median (about 0.2 s) instead of a centered one.
- **Rolling calibration.** Thresholds come from the last 30 s of pose frames and refresh about once a second. Nothing counts until that window shows at least the minimum squat range of motion. When counting becomes possible, the frames already in the window are replayed, so a rep done during warm-up still counts. It can show up about a second late.
- **Pauses.** If the lifter stops long enough that the window has no squat motion, the mode shows `PAUSED` and counting waits for motion to return. Counts never go backwards.
- **Frame rate.** Timing rules are in seconds. For a video file the counter uses the file's fps. For a webcam it measures the processing rate over the first 30 frames and keeps it.
- **Label.** The HUD shows "Detecting squat..." until the first rep counts, then "Squat". The counter does not recognize other exercises.

Telemetry `exercise_status` carries `rep_count`, `phase`, `phase_display`, `calibration_mode`, the current thresholds, `last_rep` (with its form-risk flags), and `rep_gates`. The legacy tracker still runs; its output is kept under `exercise_status.legacy_tracker` for comparison only.

Checked on the dev landmark fixtures (`backend/tests/test_live_squat.py`): front-view squats 15 (same reps as offline, within 0.5 s), A-position hold 0, broad jumps 0. Through the full live engine (`LiftGuardAI.process_frame`, MediaPipe 0.10.5) the front-view squat clip gave 15 while the legacy tracker gave 0; the broad-jump and Superman dev clips gave 0. The offline known limits above apply here too.

### Live screen: only defensible claims

- **Fatigue indicator.** `fatigue_score` in live telemetry is now the same indicator as the offline report: 0-100, higher means more drift in rep duration, depth, and trunk lean versus the first reps. It is empty (`INSUFFICIENT_REPS`) until there are enough reps. The legacy `fatigue_engine` score (100 = fresh) showed as "100%" in red from the first frame. Full detail is under `fatigue_indicator`. This is a trend indicator, not a medical measure.
- **Unvalidated model fields are not sent.** With `SessionManager.validated_claims_only` (on by default) the live telemetry sends None for the risk classifier's label/confidence/uncertainty/mode and every injury risk index field, and `using_temporal` false. No TCN weights have been trained or validated for this demo.
- **Lateral lean.** The "Center yourself!" correction used shoulder height difference in raw pixels / 100, so about 30 px at 720p fired it for a centered lifter (every frame of the front-view squat clip). It now uses the shoulder-line angle and fires above 10 deg. In a side view the shoulders overlap, the angle cannot be measured, and the check is skipped. On the front-view squat clip it went from 1125/1125 frames to 0.

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
