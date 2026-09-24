# ML results (research track)

Text summary of the experiments behind the movement recognizer and the form-scoring baseline. No model files, landmarks or video are in this repo. The recognizer model is trained partly on Penn Action, so it stays local for the pilot and would be retrained on licence-clean data before any distribution (see [MOVEMENT_MODES.md](MOVEMENT_MODES.md)).

The app does not depend on any of this: counting and every form flag come from the landmark rules. The recognizer only names the movement, is off by default, and today cannot switch a user out of squat.

## 1. Movement recognizer on Penn Action (Sep 24, 2026)

Test set: Penn Action's official test half, never trained on. Clip accuracy / share of 2 s windows at confidence >= 0.8.

| Movement | MM-Fit only | + Penn train half |
|---|---|---|
| Squats, side view | 28% / 1% | 57% / 25% |
| Squats, front/back view | 80% / 11% | 84% / 40% |
| Push-ups, side view | 92% / 78% | 92% / 82% |
| Push-ups, front view | 76% / 21% | 81% / 26% |
| Jumping jacks | 98% / 80% | 98% / 85% |

False switches: 0 of 442 Penn test clips of other actions (bench press, sit-ups, pull-ups, clean and jerk, jump rope, bowling, tennis serve) held one label at >= 0.8 for 2 s.

Caveats:
- The Penn split is by clip. Penn has no person IDs, so the same person could appear in both halves. Treat these numbers as optimistic.
- Trade-off: on MM-Fit session w19 (fully held out, filmed close to side-on), squats fell from 48% to 14% after adding Penn (lunges 78% -> 82%, push-ups 80% -> 74%). Squat stays manual-select.

## 2. False switches, earlier model (MM-Fit only)

1015 Penn clips of non-target actions: 2 clips would have tripped the 2 s gate, both bench press read as push-ups. Other actions: 0.

## 3. Form scoring on UI-PRMD, 2D camera-style features (Sep 24, 2026)

Correct vs non-optimal rep, leave-one-subject-out (10 subjects, 200 reps per movement, balanced).

| Movement | 3D Kinect angles | 2D front | 2D side |
|---|---|---|---|
| Deep squat | 87.5% | 84.0% | 82.0% |
| Hurdle step | 93.0% | 82.5% | 85.0% |
| Inline lunge | 84.0% | 77.5% | 84.5% |
| Side lunge | 81.5% | 77.5% | 82.0% |
| Sit to stand | 93.0% | 92.5% | 87.0% |

Method: UI-PRMD Kinect skeletons rebuilt to global 3D, projected to a front and a side 2D view, mapped to the 13 joints MediaPipe gives, and passed through the same feature code the app's landmark stream would use (10 fps).

Caveat: these are clean lab skeletons projected to 2D, not MediaPipe on phone video. Proven on 2D camera-style features; real-phone validation is next.

## 4. Lab baseline and camera angle (Sep 23, 2026)

- MM-Fit, session-held-out (21 sessions, 31,710 windows, 10 exercises plus rest): 95.6% accuracy, 95.1% balanced accuracy. Lab data; the drop on new camera angles is the real story.
- Held-out session w19 through MediaPipe: 74.7% of exercise windows with all features (squats 1%); 84.2% after removing left-right coordinates (squats 48%, lunges 78%).

## Datasets and citations

- MM-Fit: Strömbäck, Huang, Radu. "MM-Fit: Multimodal Deep Learning for Automatic Exercise Logging across Sensing Devices." IMWUT 4(4), 2020. https://doi.org/10.1145/3432701 (CC BY 4.0)
- UI-PRMD: Vakanski, Jun, Paul, Baker. "A Data Set of Human Body Movements for Physical Rehabilitation Exercises." Data 3(1):2, 2018. https://doi.org/10.3390/data3010002 (PDDL 1.0, public domain)
- Penn Action: Zhang, Zhu, Derpanis. "From Actemes to Action: A Strongly-supervised Representation for Detailed Action Understanding." ICCV 2013. No licence; used for non-commercial research with citation.
