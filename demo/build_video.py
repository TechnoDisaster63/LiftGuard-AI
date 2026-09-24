"""Assemble the end-to-end demo MP4 (H.264 + AAC) from slides, clips and dashboard recordings.

    python demo/build_video.py --slides SLIDES_DIR --raw SQUAT.mp4 --annotated ANNOTATED.mp4 \
        --dash-squat REC0.mp4 --dash-refusal REC1.mp4 --out liftguard_demo.mp4
Recording timings (spinner start/end) are passed as flags because they vary per machine.
"""
import argparse, subprocess, tempfile
from pathlib import Path

ap = argparse.ArgumentParser()
for a in ("slides", "raw", "annotated", "dash_squat", "dash_refusal", "out"): ap.add_argument("--" + a.replace("_", "-"), required=True)
ap.add_argument("--spin-start", type=float, default=6); ap.add_argument("--spin-end", type=float, default=58)
ap.add_argument("--refusal-start", type=float, default=57)
a = ap.parse_args()
S = Path(a.slides); tmp = Path(tempfile.mkdtemp()); parts = []
FONT = "/usr/share/fonts/truetype/noto/NotoSans-SemiBold.ttf"
V = "fps=25,format=yuv420p"


def cap(text):
    t = text.replace(":", "\\:").replace("'", "\u2019")
    return (f",drawbox=y=ih-78:w=iw:h=78:color=black@0.72:t=fill,"
            f"drawtext=fontfile={FONT}:text='{t}':x=(w-tw)/2:y=h-56:fontsize=30:fontcolor=white:expansion=none")


def run(args): subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


def seg(name, inputs, vf):
    out = tmp / f"{len(parts):02d}_{name}.mp4"
    run([*inputs, "-vf", vf + "," + V, "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "21", str(out)])
    parts.append(out)


def slide(png, secs, caption=None):
    seg(png, ["-loop", "1", "-t", str(secs), "-i", str(S / f"{png}.png")],
        "scale=1280:720,fade=t=in:d=0.4" + (cap(caption) if caption else ""))


def clip(src, start, dur, caption, speed=1.0):
    fit = "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=0x0e1117"
    pts = f",setpts=(PTS-STARTPTS)/{speed}" if speed != 1 else ",setpts=PTS-STARTPTS"
    seg(Path(src).stem, ["-ss", str(start), "-t", str(dur * speed), "-i", src], fit + pts + cap(caption))


slide("00_title", 5)
slide("01_pipeline", 9)
slide("02_setup", 9)
slide("03_cli", 8)
clip(a.raw, 2, 5, "Step 4 · Input: real workout footage, front view, no labels")
clip(a.annotated, 0, 18, "Full 33-point skeleton, measured leg chain highlighted, live rep counter")
slide("05_calibration", 10)
clip(a.dash_squat, 0, a.spin_start, "Step 6 · Dashboard: upload a clip, press Analyze")
clip(a.dash_squat, a.spin_start, (a.spin_end - a.spin_start) / 8, "Analyzing every frame (sped up 8x)", speed=8)
d0 = a.spin_end
clip(a.dash_squat, d0, 12, "15 reps · 11 flagged for depth · fatigue stable · 100% pose coverage")
clip(a.dash_squat, d0 + 12, 12, "Knee angle per frame with this session's thresholds")
clip(a.dash_squat, d0 + 24, 12, "Per-rep breakdown: depth, duration, trunk lean, range of motion")
clip(a.dash_squat, d0 + 36, 13, "Plain-language form feedback + report.json / reps.csv download")
slide("07_honesty", 9)
clip(a.dash_refusal, a.refusal_start, 7, "Mobility clip in the dashboard: no squat motion, 0 reps")
slide("08_tests", 7)
slide("09_roadmap", 9)
slide("10_end", 5)

lst = tmp / "list.txt"; lst.write_text("".join(f"file '{p}'\n" for p in parts))
run(["-f", "concat", "-safe", "0", "-i", str(lst), "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
     "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "96k", "-shortest",
     "-movflags", "+faststart", a.out])
print(a.out)
