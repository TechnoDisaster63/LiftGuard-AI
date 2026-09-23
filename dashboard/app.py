"""LiftGuard-AI demo dashboard (Streamlit).

Wraps the shipped offline squat analyzer (backend/app/video_analysis) without
changing it: upload a recorded squat video, run the real pipeline, and review
the annotated skeleton video, calibrated rep count, per-rep form flags,
fatigue indicator and knee-angle timeline.

Run from the repo root:
    pip install -r dashboard/requirements.txt
    streamlit run dashboard/app.py
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd
import streamlit as st

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))

from app.video_analysis.analyzer import (  # noqa: E402
    AnalysisConfig,
    MediaPipePoseDetector,
    _metrics,
    analyze_video,
)

RUNS = Path(__file__).resolve().parent / "runs"
FLAG_TEXT = {
    "LIMITED_DEPTH": "Limited depth (knee never went below 110 deg)",
    "EXCESSIVE_TRUNK_LEAN": "Excessive trunk lean (over 45 deg from vertical)",
    "LOW_RANGE_OF_MOTION": "Low range of motion (under 45 deg)",
}

st.set_page_config(page_title="LiftGuard-AI Dashboard", page_icon="🏋️", layout="wide")


class RecordingDetector:
    """Pass-through around the real MediaPipe detector that keeps per-frame metrics for the timeline chart."""

    def __init__(self, config: AnalysisConfig) -> None:
        self.inner = MediaPipePoseDetector()
        self.config = config
        self.knee: list[float | None] = []

    def __call__(self, frame):
        points = self.inner(frame)
        metrics = _metrics(points, self.config.min_visibility) if points else None
        self.knee.append(metrics["knee_angle"] if metrics else None)
        return points

    def close(self) -> None:
        self.inner.close()


def to_browser_mp4(src: Path) -> Path:
    """The analyzer writes mp4v; browsers need H.264. Transcode with ffmpeg when available."""
    dst = src.with_name("annotated_h264.mp4")
    if dst.exists():
        return dst
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return src
    subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", str(src), "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(dst)], check=True)
    return dst


def run_analysis(video: Path, name: str) -> Path:
    out = RUNS / f"{time.strftime('%Y%m%d-%H%M%S')}-{Path(name).stem}"
    out.mkdir(parents=True, exist_ok=True)
    config = AnalysisConfig()
    detector = RecordingDetector(config)
    try:
        analyze_video(video, out, detector=detector, config=config)
    except ValueError as exc:
        (out / "refusal.json").write_text(json.dumps({"input": name, "error": str(exc)}), encoding="utf-8")
    finally:
        detector.close()
    (out / "timeline.json").write_text(json.dumps({"knee_angle": detector.knee}), encoding="utf-8")
    return out


def past_runs() -> list[Path]:
    if not RUNS.exists():
        return []
    done = (p for p in RUNS.iterdir() if (p / "report.json").exists() or (p / "refusal.json").exists())
    return sorted(done, reverse=True)


# ---------------- Sidebar ----------------
st.sidebar.title("🏋️ LiftGuard-AI")
st.sidebar.caption("Offline squat analysis · MediaPipe pose · explainable rules")
uploaded = st.sidebar.file_uploader("Upload a squat video (20-60 s, full body visible)", type=["mp4", "mov", "avi", "m4v"])
if uploaded and st.sidebar.button("▶ Analyze video", type="primary", use_container_width=True) \
        and st.session_state.get("analyzed_upload") != uploaded.file_id:
    st.session_state["analyzed_upload"] = uploaded.file_id
    tmp = RUNS.parent / ".uploads"
    tmp.mkdir(parents=True, exist_ok=True)
    src = tmp / uploaded.name
    src.write_bytes(uploaded.getbuffer())
    with st.spinner("Tracking 33 body landmarks per frame, calibrating thresholds, counting reps..."):
        st.session_state["run"] = str(run_analysis(src, uploaded.name))

runs = past_runs()
if runs:
    labels = [p.name for p in runs]
    current = Path(st.session_state.get("run", runs[0]))
    idx = labels.index(current.name) if current.name in labels else 0
    choice = st.sidebar.selectbox("Session history", labels, index=idx)
    st.session_state["run"] = str(RUNS / choice)

st.sidebar.divider()
st.sidebar.markdown(
    "**Shipped:** squat (recorded video)\n\n"
    "**Roadmap:** see `docs/EXERCISE_CATALOG.md`\n\n"
    "_Coaching indicators only - not medical advice or injury probability._"
)

# ---------------- Main ----------------
st.title("LiftGuard-AI · Squat Session Dashboard")
if "run" not in st.session_state:
    st.info("Upload a recorded squat video in the sidebar and press **Analyze video**.")
    st.markdown(
        "**Pipeline:** video → MediaPipe pose (33 landmarks/frame) → knee & trunk angles → "
        "per-session threshold calibration → rep state machine → form flags + fatigue indicator → "
        "annotated MP4, `report.json`, `reps.csv`."
    )
    st.stop()

run = Path(st.session_state["run"])
refusal = run / "refusal.json"
if refusal.exists():
    info = json.loads(refusal.read_text())
    st.error(f"**Analysis refused - no report produced.**\n\n{info['error']}")
    st.caption("LiftGuard refuses instead of guessing when the body is not visible enough to measure.")
    st.stop()

report = json.loads((run / "report.json").read_text())
summary, cal, reps = report["summary"], report["calibration"], report["reps"]
fatigue = summary["fatigue_indicator"]
st.caption(f"Session: `{report['input']['filename']}` · {report['input']['frames']} frames @ {report['input']['fps']:.0f} fps · scope: {report['scope']}")

if summary.get("message"):
    st.warning(summary["message"])

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Reps counted", summary["reps"])
c2.metric("Flagged reps", summary["flagged_reps"])
FATIGUE_LABEL = {"INSUFFICIENT_REPS": "Need 4+ reps", "STABLE": "Stable", "WATCH": "Watch", "ELEVATED": "Elevated"}
MODE_LABEL = {"CALIBRATED": "Calibrated", "NO_SQUAT_MOTION": "No squat", "FIXED": "Fixed rule"}
c3.metric("Fatigue indicator", FATIGUE_LABEL.get(fatigue["status"], fatigue["status"]), f"score {fatigue['score']}", delta_color="off")
c4.metric("Pose coverage", f"{report['input']['pose_coverage']:.0%}")
c5.metric("Calibration", MODE_LABEL.get(cal["mode"], cal["mode"]))

left, right = st.columns([3, 2])
with left:
    st.subheader("Annotated video - full skeleton + live rep counter")
    st.video(str(to_browser_mp4(run / "annotated.mp4")))
with right:
    st.subheader("Per-session calibration")
    cal_rows = {
        "Upright level (P90 knee)": cal.get("standing_reference_deg"),
        "Deep level (P5 knee)": cal.get("bottom_reference_deg"),
        "Observed range": cal.get("observed_rom_deg"),
        "Bottom threshold": cal["bottom_knee_deg"],
        "Standing threshold": cal["standing_knee_deg"],
        "Min range per rep": cal["min_rep_rom_deg"],
    }
    if cal["mode"] == "NO_SQUAT_MOTION":
        cal_rows = {k: v for k, v in cal_rows.items() if "threshold" not in k and "per rep" not in k}
    st.table(pd.DataFrame({"degrees": {k: f"{v:.1f}" for k, v in cal_rows.items() if v is not None}}))
    st.caption(f"Reason: {cal['reason']}")
    if fatigue["signals"]:
        st.subheader("Fatigue signals (vs first 3 reps)")
        s = fatigue["signals"]
        st.write(f"- Rep duration drift: **{s['rep_duration_drift_pct']}%**\n"
                 f"- Range-of-motion loss: **{s['range_of_motion_loss_pct']}%**\n"
                 f"- Trunk-lean drift: **{s['trunk_lean_drift_degrees']} deg**")

timeline = run / "timeline.json"
if timeline.exists():
    knee = json.loads(timeline.read_text())["knee_angle"]
    fps = report["input"]["fps"]
    df = pd.DataFrame({"seconds": [i / fps for i in range(len(knee))], "knee angle": knee})
    if cal["mode"] != "NO_SQUAT_MOTION":
        df["bottom threshold"] = cal["bottom_knee_deg"]
        df["standing threshold"] = cal["standing_knee_deg"]
    st.subheader("Knee angle over time (raw pose, per frame)")
    st.line_chart(df.set_index("seconds"), height=260)

if reps:
    st.subheader("Per-rep breakdown")
    table = pd.DataFrame(reps)
    table["form_flags"] = table["form_flags"].apply(lambda f: ", ".join(f) if f else "OK")
    st.dataframe(table, hide_index=True, use_container_width=True)
    b1, b2 = st.columns(2)
    b1.caption("Deepest knee angle per rep (lower = deeper)")
    b1.bar_chart(table.set_index("rep")["min_knee_angle"], height=220)
    b2.caption("Rep duration (s)")
    b2.bar_chart(table.set_index("rep")["duration_seconds"], height=220)
    flagged = [r for r in reps if r["form_flags"]]
    if flagged:
        st.subheader("Form feedback")
        for r in flagged:
            st.write(f"Rep {r['rep']}: " + "; ".join(FLAG_TEXT.get(f, f) for f in r["form_flags"]))
    else:
        st.success("No form flags on any counted rep.")

d1, d2 = st.columns(2)
d1.download_button("Download report.json", (run / "report.json").read_bytes(), "report.json", "application/json")
d2.download_button("Download reps.csv", (run / "reps.csv").read_bytes(), "reps.csv", "text/csv")
st.caption(report["disclaimer"])
