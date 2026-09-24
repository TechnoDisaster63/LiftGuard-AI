# LiftGuard-AI exercise catalog and expansion roadmap

**Status: cataloged from footage, not validated for analysis.** This list records the exercises seen in internal development videos. Apart from the squat, none of them has analysis logic, thresholds, tests, or validation. Listing an exercise here is not a claim that LiftGuard can analyze it.

The development videos are third-party trainer content used only for internal testing. They are not demo material and are not committed to this repo.

## Shipped

| Exercise | Status | What exists |
|---|---|---|
| Squat (bodyweight, recorded video) | Shipped, prototype | Knee angle and trunk lean, per-session calibrated rep thresholds, form-risk flags, fatigue indicator, tests. Built for side-view recordings; side-view validation with consented clips still to come. See `docs/REVIVAL_SCOPE.md`. |

## How a new exercise gets added

Each exercise is its own piece of work. None reuses the squat logic by default.

1. Define the joint angles and camera view that matter for it.
2. Define the rep or hold logic and its thresholds, with a documented reason for each.
3. Write tests: synthetic fixtures, a "not this exercise" refusal case, and low-visibility failure.
4. Validate on consented, owner-recorded clips before claiming it works.
5. Update this catalog with the validation result.

Until those steps are done, the exercise stays "cataloged".

## Cataloged from development footage

### Video 1: 28-minute home workout (real trainer, front view, on-screen overlays)

| Exercise | Status |
|---|---|
| Squats | Squat analysis applies (front view is not the supported view) |
| Squat Pulses | Cataloged |
| Crunches + Squat Pulses | Cataloged |
| Push-Ups | Cataloged |
| Push Up + Child's Pose | Cataloged |
| Leg Lift + Push Up (left / right) | Cataloged |
| Plank Side Steps | Cataloged |
| Plank Toe Tap | Cataloged |
| Plank Front-Back Walk | Cataloged |
| Low Plank Leg Raises | Cataloged |
| Shoulder Taps | Cataloged |
| Slow Climbers | Cataloged |
| Superman | Cataloged |
| 1-Leg Glute Bridge (left / right) | Cataloged |
| Deep Lunge | Cataloged |
| Reach + Knee Hug | Cataloged |
| Lean-Back Body Twists | Cataloged |

Pipeline notes: the 45 s squat segment counts 15 reps with calibrated thresholds (the fixed 105/155 deg rule counted 2). A 40 s Superman segment stops with low pose coverage (32%), as it should.

### Video 2: full-body athlete mobility routine (real person, front/back view)

Unlabeled stretch flow with no countable reps. Kept as a reference "not a squat" test asset.

Pipeline notes: 92% pose coverage; 0 reps with "No squat movement detected" (knee range 11 deg).

### Video 3: Roberta's Gym (animated trainer)

| Exercise | Status |
|---|---|
| Walk Downs | Cataloged |
| Arm Circles | Cataloged |
| Lateral Arm Circles | Cataloged |
| Snow Angels | Cataloged |
| Lateral Step Reach | Cataloged |
| Knee Tuck Crunch | Cataloged |
| Super Mans | Cataloged |
| Forward Jump | Cataloged |
| Swing Backs | Cataloged |
| Step Back Jacks | Cataloged |
| Prayer Pushes | Cataloged |
| Side Leg Raise (left / right) | Cataloged |
| Body Extensions | Cataloged |

Pipeline notes: MediaPipe tracks the animated body (100% pose coverage on a 40 s Side Leg Raise segment); 0 reps with "No squat movement detected" (knee range 2 deg). Tracking a cartoon body is not a sign the input is suitable; the no-squat gate is what refuses it.

### Video 4: sprint mechanics drills (outdoor, 82 s)

| Exercise | Status |
|---|---|
| A Skips | Cataloged |
| A Pops | Cataloged (on-screen label) |
| High Knees | Cataloged (on-screen label) |
| Single-Leg High Knees | Cataloged (on-screen label) |
| Dribble Bleeds | Cataloged (on-screen label) |
| Crossover Sprints | Cataloged (on-screen label) |

Pipeline notes: the full 82 s file is refused by the 60 s input limit. Split into 0-55 s and 54-82 s, pose coverage was 99.6% and 63%. The first part counted 0 reps. The second part counted 1 false squat rep on a held "thighs parallel" running pose: the measured knee was the lifted leg, not a squatting leg. Knee angle on one leg cannot tell a squat from a knee lift. Follow-up needed: require both knees to bend and the hips to drop before a rep counts.

### Video 5: gym athletic-training edit (strength vs power, real people, mostly front view)

Gym / weighted and plyometric category.

| Exercise | Status |
|---|---|
| Dumbbell Lunges | Cataloged |
| Box Step-Ups | Cataloged |
| Plyometric (vertical) Jumps | Cataloged |
| Lateral Bounds / Skater Jumps | Cataloged |
| Pogos | Cataloged |
| Broad Jumps | Cataloged |
| Box Jumps | Cataloged |

Pipeline notes: a 40 s segment is refused (pose visible in 25% of frames). MediaPipe found a body in 88% of frames, but the full shoulder-hip-knee-ankle chain was usable in only 25%: tight crops cut off the legs or head, equipment blocks joints, and cutaways show an interview and talking-to-camera shots. Once it also drew a skeleton on a seated interviewee. The coverage gate refused the clip correctly, and no squat reps were reported.

Jump sections (45 s each, cut from the same video): see the PR that adds leg gates for current pipeline behavior.
