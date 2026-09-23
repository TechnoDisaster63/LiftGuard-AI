# Movement modes

A movement mode owns three things: the joint metrics it measures, a rep definition with gates that reject look-alike movements, and form-risk flags that each come from a landmark measurement. The live feed runs one mode at a time. Registry: `backend/app/video_analysis/movements.py`.

| Mode | State | Rep signal | Gates | Flags (cue) |
|---|---|---|---|---|
| `squat` | Live in the app | Knee angle | Feet planted, hips drop, both knees bend | LIMITED_DEPTH (Go deeper), EXCESSIVE_TRUNK_LEAN (Chest up), LOW_RANGE_OF_MOTION (Full range), KNEES_CAVING (Knees out), HEELS_LIFTING (Heels down), DEPTH_INCONSISTENT (Match your depth), FAST_DESCENT (Slow down) |
| `pushup` | Engine done, synthetic tests only, not selectable yet | Elbow angle, side facing the camera | Body within 40° of horizontal, shoulders drop ≥ 12% of arm length, hands move < 35% of arm length | SHALLOW_PUSHUP (Chest lower, elbow never below 110°), HIPS_SAGGING / HIPS_PIKING (Hips up / Hips down, shoulder-hip-ankle line under 160° for a quarter of the rep, side from the hip's position against the line), DEPTH_INCONSISTENT, FAST_DESCENT |
| `lunge` | Engine done, synthetic tests only, not selectable yet | Front knee angle (the leg with the more upright shin), side view, stationary lunge | Feet split front-back by ≥ 30% of leg length (rejects side-by-side squats), both feet move < 25% of leg length during the whole rep, hips drop ≥ 12% of leg length | SHALLOW_LUNGE (Drop lower, front knee never below 110°), FORWARD_LEAN (Chest up, shoulder-hip line past 30° from vertical for a quarter of the rep), KNEE_PAST_TOES (Longer stance, front knee more than 10% of leg length past the toes; a measured distance, not a safety limit), DEPTH_INCONSISTENT, FAST_DESCENT |
| `jumping_jacks` | Planned | Arm abduction angle plus ankle gap (front view) | Both arms and both feet open and close together | Arms not overhead, feet not apart, tempo drift. No depth rules. |

## Rollout

1. **Push-up (this step).** Engine, gates, flags and tests on synthetic skeletons. Next: record one side-view push-up clip (Techno, not trainer footage for anything public), turn its landmarks into a fixture like `front_view_squats.json.gz`, check counts and flags against it, then tune thresholds.
2. **Mode selection in the app (done).** `movement_mode` is a session default (squat by default). Session start passes it to the live feed, and the report summary, fatigue indicator and saved contributions follow it. Settings and the Live Ready screen have a mode picker, and the top bar shows the current mode. `GET /api/settings/movement-modes` lists every mode with `validated` and `selectable`. A mode can be picked only once `validated` is True in `movements.py`. Push-up is False until step 1 passes, so the app lists it as "Coming". For development, `LIFTGUARD_PREVIEW_MODES=pushup` on the backend unlocks it.
3. **Lunge (engine done).** Same steps as push-up: engine, gates, flags and tests on synthetic skeletons are in; `validated` is False until a recorded side-view lunge clip passes. Only stationary lunges (split squats) are counted; stepping and walking lunges are rejected by the feet-stay-put gate for now. `LIFTGUARD_PREVIEW_MODES=lunge` unlocks it for development. **Jumping jacks** next, same steps.
4. **Auto-detection** (below), turned on after at least two modes pass on real clips.

## Release gate for a new mode

A mode flips to `validated = True` in `movements.py` only when all of these are done:

1. **Recorded clip check.** One side-view clip of Techno doing the movement (not trainer footage), turned into a landmark fixture. Counts match the reps done, and each flag fires only on the reps that show the fault.
2. **Live help panel copy.** The Live screen's help panel says "Learning your depth: do 3 slow squats" during calibration. Each mode needs its own line before release, for example "do 3 slow push-ups" or "do 3 slow lunges", plus the camera view it needs.
3. **Flip `validated` to True** in the same PR as the fixture test, so the app never offers a mode that has not passed 1 and 2.

Push-up is waiting on step 1 (a side-view push-up clip). Lunge is waiting on step 1 as well.

## Recognizer hook

The exercise recognizer (MM-Fit, 10 classes) only names the movement. Counting and every flag stay with the mode's own landmark rules, so a wrong or unsupported label cannot create a flag.

Interface for the recognizer:
- Input: the same MediaPipe landmark stream the counter gets (33 points, x, y, visibility), in windows of about 2 s.
- Output per window: `(label, confidence)` using MM-Fit label names (`squats`, `pushups`, `lunges`, `jumping_jacks`, ...).
- `RecognizerGate.observe(label, confidence, now, mid_rep)` returns a new mode only when the same supported label has held at ≥ 0.8 confidence for 2 s, and never mid-rep. Labels without a mode (`RECOGNIZER_LABELS[...] is None`) change nothing.
- The engine then calls `feed.set_mode(mode)`. That starts a fresh counter: reps and calibration do not carry across movements.

Not wired into the engine yet: the gate and `set_mode` are in place and tested; calling them from the frame loop waits for the recognizer model.
