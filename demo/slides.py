"""Render the demo video's title, explainer and terminal cards (1280x720 PNG)."""
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

W, H = 1280, 720
F = "/usr/share/fonts/truetype/noto/"
def font(name, size): return ImageFont.truetype(F + name, size)
BG, ACC, FG, DIM, OK, WARN = (14, 17, 23), (0, 200, 150), (235, 238, 242), (150, 158, 170), (80, 220, 120), (255, 190, 70)
out = Path(sys.argv[1] if len(sys.argv) > 1 else "slides"); out.mkdir(parents=True, exist_ok=True)


def base(step=None):
    im = Image.new("RGB", (W, H), BG); d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, 6], fill=ACC)
    d.text((40, 676), "LiftGuard-AI  ·  Team Zyronith", font=font("NotoSans-SemiBold.ttf", 20), fill=DIM)
    if step: d.text((W - 40, 676), step, font=font("NotoSans-SemiBold.ttf", 20), fill=ACC, anchor="ra")
    return im, d


def card(name, title, lines, step=None, sub=None):
    im, d = base(step)
    d.text((80, 80), title, font=font("NotoSans-Bold.ttf", 54), fill=FG)
    y = 165
    if sub: d.text((80, y), sub, font=font("NotoSans-Regular.ttf", 28), fill=ACC); y += 60
    for ln in lines:
        color = FG
        if isinstance(ln, tuple): ln, color = ln
        d.text((100, y), ln, font=font("NotoSans-Regular.ttf", 30), fill=color); y += 52
    im.save(out / f"{name}.png")


def term(name, title, lines, step=None):
    im, d = base(step)
    d.text((80, 50), title, font=font("NotoSans-Bold.ttf", 40), fill=FG)
    d.rounded_rectangle([60, 120, W - 60, 650], 14, fill=(6, 8, 12), outline=(50, 56, 66), width=2)
    for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]): d.ellipse([80 + i * 26, 136, 96 + i * 26, 152], fill=c)
    y = 172
    for ln in lines:
        color = OK if ln.startswith("$") or ln.startswith(">") else FG
        if ln.startswith("#"): color = DIM
        d.text((90, y), ln, font=font("NotoSansMono-Regular.ttf", 22), fill=color); y += 31
    im.save(out / f"{name}.png")


im, d = base()
d.text((W // 2, 250), "LiftGuard-AI", font=font("NotoSans-Bold.ttf", 96), fill=FG, anchor="mm")
d.text((W // 2, 340), "AI squat analysis from any recorded workout video", font=font("NotoSans-Regular.ttf", 36), fill=ACC, anchor="mm")
d.text((W // 2, 420), "End-to-end demo: setup, analysis, skeleton tracking, rep counting, dashboard", font=font("NotoSans-Regular.ttf", 28), fill=DIM, anchor="mm")
d.text((W // 2, 500), "Sabari T  ·  Team Zyronith  ·  SFIC Theme 3", font=font("NotoSans-SemiBold.ttf", 28), fill=FG, anchor="mm")
im.save(out / "00_title.png")

im, d = base("1 / 8  How it works")
d.text((80, 70), "How LiftGuard works", font=font("NotoSans-Bold.ttf", 54), fill=FG)
steps = ["Recorded\nvideo", "MediaPipe\npose\n33 points", "Knee +\ntrunk\nangles", "Calibrate\nthresholds\nper session", "Count reps\n+ form flags\n+ fatigue", "Annotated MP4\nreport.json\nreps.csv\nDashboard"]
bw, gap, x0, y0 = 170, 26, 55, 220
for i, s in enumerate(steps):
    x = x0 + i * (bw + gap)
    d.rounded_rectangle([x, y0, x + bw, y0 + 190], 16, fill=(24, 30, 40), outline=ACC, width=3)
    d.multiline_text((x + bw // 2, y0 + 95), s, font=font("NotoSans-SemiBold.ttf", 20), fill=FG, anchor="mm", align="center", spacing=6)
    if i < len(steps) - 1:
        ax, ay = x + bw + 4, y0 + 95
        d.polygon([(ax, ay - 10), (ax + 18, ay), (ax, ay + 10)], fill=ACC)
for j, ln in enumerate(["Runs offline on a laptop. Free tools only (Python, OpenCV, MediaPipe, Streamlit).",
                        "Explainable rules, not a black box: every number traces back to a joint angle.",
                        "Refuses to guess when the body is not visible enough to measure."]):
    d.text((80, 470 + j * 50), "•  " + ln, font=font("NotoSans-Regular.ttf", 27), fill=FG)
im.save(out / "01_pipeline.png")

term("02_setup", "Step 2 · Setup (Windows 11 / Python 3.11)", [
    "$ git clone https://github.com/TechnoDisaster63/LiftGuard-AI",
    "$ cd LiftGuard-AI\\backend",
    "$ py -3.11 -m venv .venv && .\\.venv\\Scripts\\Activate.ps1",
    "$ pip install mediapipe==0.10.5 opencv-contrib-python==4.8.0.74 numpy==1.24.3",
    "# dashboard extras",
    "$ pip install -r ..\\dashboard\\requirements.txt",
    "",
    "# run analysis from the command line ...",
    "$ python analyze_video.py squats.mp4 --output outputs\\demo",
    "# ... or open the dashboard",
    "$ streamlit run ..\\dashboard\\app.py",
], "2 / 8  Setup")

import json
R = json.load(open(sys.argv[2])) if len(sys.argv) > 2 else None
if R:
    s, c, inp = R["summary"], R["calibration"], R["input"]
    term("03_cli", "Step 3 · Analyze a real workout clip (45 s, front view)", [
        "$ python analyze_video.py lg-clip-squat.mp4 --output outputs/demo",
        "{",
        f'  "message": null,',
        f'  "reps": {s["reps"]},',
        f'  "flagged_reps": {s["flagged_reps"]},',
        f'  "fatigue_indicator": {{ "status": "{s["fatigue_indicator"]["status"]}", "score": {s["fatigue_indicator"]["score"]} }}',
        "}",
        f"# {inp['frames']} frames @ {inp['fps']:.0f} fps, pose found in {inp['pose_coverage']:.0%} of frames",
        "# writes: outputs/demo/annotated.mp4  report.json  reps.csv",
    ], "3 / 8  Command line")
    card("05_calibration", "Step 5 · Per-session calibration", [
        f"Upright level (90th pct knee angle):   {c['standing_reference_deg']} deg",
        f"Deep level (5th pct knee angle):          {c['bottom_reference_deg']} deg",
        f"Observed range:                                    {c['observed_rom_deg']} deg",
        (f"Rep = knee below {c['bottom_knee_deg']} deg, then back above {c['standing_knee_deg']} deg,", ACC),
        (f"      covering at least {c['min_rep_rom_deg']} deg of motion", ACC),
        (f"Result: {s['reps']} reps counted on this {inp['frames'] // int(inp['fps'])} s clip", OK),
        ("Range under 35 deg = no squat. It never loosens rules to force a count.", DIM),
    ], "5 / 8  Calibration", sub="Front-view cameras make squats look shallow, so fixed 105/155 deg rules undercount.")

card("07_honesty", "Step 7 · Honest by design", [
    "Mobility / stretching clip:  0 reps  (correct - no squat to count)",
    "Pose visible in under 50% of frames:  refused, no report",
    "Gym edit with tight crops + equipment in the way:  refused",
    ("Caught + fixed: a one-leg knee-lift hold once counted as a squat.", WARN),
    ("A rep now needs both knees bent, hips dropping, feet planted.", WARN),
    ("Coaching indicators only - not medical advice.", DIM),
], "7 / 8  Honesty")

term("08_tests", "Automated tests (CI on every pull request)", [
    "$ cd backend && pytest -q tests/test_video_analysis.py",
    "..................                                       [100%]",
    "18 passed",
    "",
    "# covers: joint-angle math, deterministic rep counting,",
    "#         calibration, output files, low-pose refusal,",
    "#         full-skeleton overlay, knee-lift + broad-jump",
    "#         regressions (both-knees / hip-drop / feet-planted gates)",
], "8 / 8  Tests")

card("09_roadmap", "What's shipped, what's next", [
    ("Shipped:  squat analysis on recorded video + dashboard", OK),
    "Next:  side-view clean / sloppy / tired squat validation",
    "Done:  both-knees + hip-drop + feet-planted rep gates",
    "Roadmap:  lunges, step-ups, push-ups... (exercise catalog from",
    "                real workout footage, each needs its own rules + tests)",
    "Experiment:  small ML exercise classifier on pose landmarks",
], None)

im, d = base()
d.text((W // 2, 280), "LiftGuard-AI", font=font("NotoSans-Bold.ttf", 84), fill=FG, anchor="mm")
d.text((W // 2, 370), "github.com/TechnoDisaster63/LiftGuard-AI", font=font("NotoSansMono-Regular.ttf", 32), fill=ACC, anchor="mm")
d.text((W // 2, 440), "Sabari T  ·  Team Zyronith", font=font("NotoSans-SemiBold.ttf", 30), fill=DIM, anchor="mm")
im.save(out / "10_end.png")
