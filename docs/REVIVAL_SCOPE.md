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
