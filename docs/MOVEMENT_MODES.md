# Movement modes

A movement mode owns three things: the joint metrics it measures, a rep definition with gates that reject look-alike movements, and form-risk flags that each come from a landmark measurement. The live feed runs one mode at a time. Registry: `backend/app/video_analysis/movements.py`.

| Mode | State | Rep signal | Gates | Flags (cue) |
|---|---|---|---|---|
| `squat` | Live in the app | Knee angle | Feet planted, hips drop, both knees bend | LIMITED_DEPTH (Go deeper), EXCESSIVE_TRUNK_LEAN (Chest up), LOW_RANGE_OF_MOTION (Full range), KNEES_CAVING (Knees out), HEELS_LIFTING (Heels down), DEPTH_INCONSISTENT (Match your depth), FAST_DESCENT (Slow down) |
| `pushup` | Engine done, synthetic tests only, not selectable yet | Elbow angle, side facing the camera | Body within 40° of horizontal, shoulders drop ≥ 12% of arm length, hands move < 35% of arm length | SHALLOW_PUSHUP (Chest lower, elbow never below 110°), HIPS_SAGGING / HIPS_PIKING (Hips up / Hips down, shoulder-hip-ankle line under 160° for a quarter of the rep, side from the hip's position against the line), DEPTH_INCONSISTENT, FAST_DESCENT |
| `lunge` | Engine done, synthetic tests only, not selectable yet | Front knee angle (the leg with the more upright shin), side view, stationary lunge | Feet split front-back by ≥ 30% of leg length (rejects side-by-side squats), both feet move < 25% of leg length during the whole rep, hips drop ≥ 12% of leg length | SHALLOW_LUNGE (Drop lower, front knee never below 110°), FORWARD_LEAN (Chest up, shoulder-hip line past 30° from vertical for a quarter of the rep), KNEE_PAST_TOES (Longer stance, front knee more than 10% of leg length past the toes; a measured distance, not a safety limit), DEPTH_INCONSISTENT, FAST_DESCENT |
| `jumping_jacks` | Engine done, synthetic tests only, not selectable yet | Arm abduction (hip-shoulder-wrist, both arms averaged), front view | Both arms within 45° of each other at the top, ankle gap grows by ≥ 0.4 hip widths (arm raises without a jump are rejected) | ARMS_NOT_OVERHEAD (Arms all the way up, arms never past 150°), FEET_NOT_APART (Jump wider, feet under 1.8 hip widths apart), TEMPO_DRIFT (Keep the rhythm, cycle 1.5x the median of earlier reps). No depth rules. |

## Rollout

1. **Push-up (this step).** Engine, gates, flags and tests on synthetic skeletons. Next: record one side-view push-up clip (Techno, not trainer footage for anything public), turn its landmarks into a fixture like `front_view_squats.json.gz`, check counts and flags against it, then tune thresholds.
2. **Mode selection in the app (done).** `movement_mode` is a session default (squat by default). Session start passes it to the live feed, and the report summary, fatigue indicator and saved contributions follow it. Settings and the Live Ready screen have a mode picker, and the top bar shows the current mode. `GET /api/settings/movement-modes` lists every mode with `validated` and `selectable`. A mode can be picked only once `validated` is True in `movements.py`. Push-up is False until step 1 passes, so the app lists it as "Coming". For development, `LIFTGUARD_PREVIEW_MODES=pushup` on the backend unlocks it.
3. **Lunge (engine done).** Same steps as push-up: engine, gates, flags and tests on synthetic skeletons are in; `validated` is False until a recorded side-view lunge clip passes. Only stationary lunges (split squats) are counted; stepping and walking lunges are rejected by the feet-stay-put gate for now. `LIFTGUARD_PREVIEW_MODES=lunge` unlocks it for development. **Jumping jacks (engine done)**, same steps, front view: waits on a recorded front-view clip.
4. **Auto-detection** (below), turned on after at least two modes pass on real clips.

## Release gate for a new mode

A mode flips to `validated = True` in `movements.py` only when all of these are done:

1. **Recorded clip check.** One side-view clip of Techno doing the movement (not trainer footage), turned into a landmark fixture. Counts match the reps done, and each flag fires only on the reps that show the fault.
2. **Live help panel copy.** The Live screen's help panel says "Learning your depth: do 3 slow squats" during calibration. Each mode needs its own line before release, for example "do 3 slow push-ups" or "do 3 slow lunges", plus the camera view it needs.
3. **Flip `validated` to True** in the same PR as the fixture test, so the app never offers a mode that has not passed 1 and 2.

Push-up and lunge are waiting on step 1 (side-view clips). Jumping jacks is waiting on step 1 with a front-view clip.

## Checking a recorded clip

`backend/clip_check.py` runs step 1 of the release gate. It turns a video into a landmark fixture (landmarks only, no pixels), streams it through the mode's live counter the same way the app does, and compares the result with what was actually done.

What to record (Techno's own recordings; trainer footage stays internal):

| Mode | Camera | What to do |
|---|---|---|
| `pushup` | Side view, camera at floor height, whole body from head to feet in frame | 10 normal push-ups, then 1 with hips sagging and 1 shallow one. Say which reps were the faulty ones. |
| `lunge` | Side view, whole body in frame | Stationary lunges (split squat, feet stay put): 10 normal, then 1 shallow and 1 leaning forward. |
| `jumping_jacks` | Front view, facing the camera, whole body in frame | 15 normal jumping jacks, then 2 with arms only to shoulder height and 2 with feet barely apart. |

Then, from `backend/`:

```bash
python clip_check.py extract pushup.mp4 --out tests/fixtures/clips/pushup_side.json.gz \
    --description "Side-view push-ups, Techno, 12 reps"
python clip_check.py check tests/fixtures/clips/pushup_side.json.gz --mode pushup --reps 12 \
    --fault 11:HIPS_SAGGING --fault 12:SHALLOW_PUSHUP --save-expected
```

`check` prints each rep with its flags next to the expected ones and ends with `RESULT: PASS` or `RESULT: FAIL` (exit code 0 or 1). A pass needs the exact rep count, no flag on a normal rep, the expected flag on each faulty rep, and a pose in at least half the frames. `--save-expected` stores the expected result in the fixture; `tests/test_clip_check.py` re-checks every fixture in `tests/fixtures/clips/` on each pull request. If a clip fails, tune the thresholds in the mode's config and re-run; flip `validated` only when it passes.

First run on the one real clip we have (front-view squats, 15 normal reps): the count is right (15) and none of the four coaching flags fire, but `LIMITED_DEPTH` fires on 11 of the 15 reps. Squat mode is built for a side view, and from the front the knee angle looks straighter than it is. This is why the demo stays side-view, and it is the kind of problem the clip check is there to catch.

## Recognizer hook

The exercise recognizer only names the movement. Counting and every flag stay with the mode's own landmark rules, so a wrong or unsupported label cannot create a flag.

Interface:
- Input: the same MediaPipe landmark stream the counter gets (33 points, normalized x, y), as a 2 s window sampled at about 10 fps (20 frames; other lengths are resampled).
- Output per window: `(label, confidence)`, label one of `squats`, `pushups`, `lunges`, `jumping_jacks` or `other`. A window with no pose in most frames returns `('other', 0.0)`.
- `RecognizerGate.observe(label, confidence, now, mid_rep)` returns a new mode only when the same supported label has held at ≥ 0.8 confidence for 2 s, and never mid-rep. Labels without a mode (`RECOGNIZER_LABELS[...] is None`) change nothing.
- The engine then calls `feed.set_mode(mode)`. That starts a fresh counter: reps and calibration do not carry across movements.

### Auto-detect in the engine (wired, off by default)

`backend/app/video_analysis/auto_mode.py` (`AutoModeSwitcher`) connects the recognizer to the live frame loop (`LiftGuardAI._update_live_squat`):

1. After each processed frame goes to the counter, the switcher samples landmarks at 10 fps of stream time (the counter's frame rate, so video files behave the same at any playback speed).
2. Every 0.5 s it sends the last 2 s window to the recognizer.
3. A label whose mode can't be picked yet is treated as `other`. A mode counts only when `validated` is True, or when it is unlocked for development with `LIFTGUARD_PREVIEW_MODES`. **Today only squat is validated, so auto-detect cannot switch a user out of squat.** The switcher gets the same rule as the mode picker.
4. `RecognizerGate` decides (≥ 0.8 for 2 s, never while the rep machine is mid-rep), then `feed.set_mode` starts a fresh counter. The live status gets an `auto_detect` block (last label and confidence, switches, error).
5. A settings change of mode resets the window and the candidate. A recognizer error turns auto-detect off for that session, and counting carries on in the current mode.

Squat stays the default mode and is picked by hand. Auto-detect is off unless both are set on the backend:

```bash
LIFTGUARD_AUTO_DETECT=1
LIFTGUARD_RECOGNIZER_MODEL=C:\Users\you\LiftGuard\recognizer_rf.npz   # local file, never in git
```

No frontend switch exists for it yet, and the dashboard does not show the `auto_detect` block yet.

### How the app gets the model: local file only (free pilot)

The model was trained on MM-Fit plus Penn Action. Penn Action has no licence and is used for non-commercial research with citation (Zhang, Zhu, Derpanis, "From Actemes to Action: A Strongly-supervised Representation for Detailed Action Understanding", ICCV 2013). So the model file, and anything derived from Penn Action, **is never committed to this repo and never shipped** in a build, installer, Docker image or release asset. `.gitignore` blocks `*.joblib` and `*.npz`, and `tests/test_auto_mode.py` fails if a model file shows up in the repo.

For the free pilot the backend reads the model from a local path (`LIFTGUARD_RECOGNIZER_MODEL`) on the machine running it. The file stays in the owner's private Google Drive and is copied by hand to that machine. Why this and not a download at startup:

- A startup download from a private location needs a credential or a public link inside the app. Anyone with the app could then fetch the model, which is redistribution by another route.
- The pilot runs on the owner's own laptop, so a local file costs nothing and needs no server.
- Without the file, auto-detect stays off and everything else works as before.

If LiftGuard is ever distributed, the recognizer has to be retrained on data whose licence allows that (for example MM-Fit alone, once its label licence is checked). A download from a private location doesn't fix the licence problem.

### Model format

The app loads a `.npz` export of the random forest (tree arrays only), not the `.joblib` pickle:

- The pickle was written with scikit-learn 1.7.2 and numpy 2.x. The app pins scikit-learn 1.3.0 and numpy 1.24.3, which can't load it.
- A `.npz` is loaded with `allow_pickle=False`, so a model file can't run code, and reading it needs numpy only.

Make the export where the model was trained (same scikit-learn version):

```bash
cd backend
python export_recognizer.py recognizer_rf.joblib recognizer_rf.npz
```

The script checks itself: exported vs scikit-learn probabilities on random inputs must match (argmax agreement 1.000, max difference 3e-10 on the current model). On 747 synthetic landmark windows the app's reader and the original `recognizer.py` gave the same label every time, with confidences equal to within 1e-9. One `predict` takes about 1 ms (the scikit-learn version took about 8 ms).

### What the tests prove, and what they don't

`tests/test_auto_mode.py` runs synthetic streams (`tests/synthetic_pose.py`: cartoon skeletons of each movement, not recordings) through the real live feed and switcher with scripted recognizers and a tiny hand-built forest. They check: one switch after the label holds 2 s, a fresh counter after the switch, no switch to an unvalidated mode, none below 0.8, none on flickering labels, `other` or no pose, no restart when the label is the current mode, no switch mid-rep, the same timing at 15, 30 and 60 fps, a reset on a manual mode change, and that a recognizer error turns auto-detect off. Engine-level tests run where mediapipe is installed and are skipped in CI.

With the real model (run locally, not in CI) the cartoon streams got the right top label for side-view squats (17 of 28 windows), push-ups, jumping jacks and lunges, but mostly under 0.8, so nothing switched even with every mode unlocked. Front-view cartoon squats read as `other`. That is a limit of the cartoons, not a measure of the model. It shows the pipeline runs end to end and that the gate is strict. Accuracy has to come from real clips.

Recognizer evaluation (ML side, measured on held-out clips):
- Side squats: 57% clip accuracy, 25% of windows ≥ 0.8. Front squats 84%, back squats 40%. Squat stays manual-select.
- Push-ups (side): 92% clip accuracy, 82% of windows ≥ 0.8. Jumping jacks: 98% / 85%.
- False switches: 0 of 442 clips of other actions tripped the 0.8 / 2 s gate.

Before auto-detect is turned on for users: at least two modes pass the recorded-clip check (Rollout step 4), a real recorded session is run with auto-detect on and the switch times checked, and the dashboard shows when the mode changed.
