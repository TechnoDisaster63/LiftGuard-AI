# Movement modes

A movement mode owns three things: the joint metrics it measures, a rep definition with gates that reject look-alike movements, and form-risk flags that each come from a landmark measurement. The live feed runs one mode at a time. Registry: `backend/app/video_analysis/movements.py`.

| Mode | State | Rep signal | Gates | Flags (cue) |
|---|---|---|---|---|
| `squat` | Live in the app | Knee angle | Feet planted, hips drop, both knees bend | LIMITED_DEPTH (Go deeper), EXCESSIVE_TRUNK_LEAN (Chest up), LOW_RANGE_OF_MOTION (Full range), KNEES_CAVING (Knees out), HEELS_LIFTING (Heels down), DEPTH_INCONSISTENT (Match your depth), FAST_DESCENT (Slow down) |
| `pushup` | Engine done, synthetic tests only, not selectable yet | Elbow angle, side facing the camera | Body within 40° of horizontal, shoulders drop ≥ 12% of arm length, hands move < 35% of arm length | SHALLOW_PUSHUP (Chest lower, elbow never below 110°), HIPS_SAGGING / HIPS_PIKING (Hips up / Hips down, shoulder-hip-ankle line under 160° for a quarter of the rep, side from the hip's position against the line), DEPTH_INCONSISTENT, FAST_DESCENT |
| `lunge` | Planned | Front knee angle | Feet split front-back and stay put during the rep, hips drop | Front knee depth, trunk lean, front knee past toes only as a measured distance (no injury claim), depth drift, fast descent |
| `jumping_jacks` | Planned | Arm abduction angle plus ankle gap (front view) | Both arms and both feet open and close together | Arms not overhead, feet not apart, tempo drift. No depth rules. |

## Rollout

1. **Push-up (this step).** Engine, gates, flags and tests on synthetic skeletons. Next: record one side-view push-up clip (Techno, not trainer footage for anything public), turn its landmarks into a fixture like `front_view_squats.json.gz`, check counts and flags against it, then tune thresholds.
2. **Mode selection in the app.** Add `movement_mode` to session defaults, pass it to `LiveSquatFeed(mode=...)` at session start, add the Push-up button on Settings and the Ready page. Only modes that passed step 1 on a real clip become selectable.
3. **Lunge**, then **jumping jacks**: same steps. Each gets a recorded-clip fixture before it is selectable.
4. **Auto-detection** (below), turned on after at least two modes pass on real clips.

## Recognizer hook

The exercise recognizer (MM-Fit, 10 classes) only names the movement. Counting and every flag stay with the mode's own landmark rules, so a wrong or unsupported label cannot create a flag.

Interface for the recognizer:
- Input: the same MediaPipe landmark stream the counter gets (33 points, x, y, visibility), in windows of about 2 s.
- Output per window: `(label, confidence)` using MM-Fit label names (`squats`, `pushups`, `lunges`, `jumping_jacks`, ...).
- `RecognizerGate.observe(label, confidence, now, mid_rep)` returns a new mode only when the same supported label has held at ≥ 0.8 confidence for 2 s, and never mid-rep. Labels without a mode (`RECOGNIZER_LABELS[...] is None`) change nothing.
- The engine then calls `feed.set_mode(mode)`. That starts a fresh counter: reps and calibration do not carry across movements.

Not wired into the engine yet: the gate and `set_mode` are in place and tested; calling them from the frame loop waits for the recognizer model.
