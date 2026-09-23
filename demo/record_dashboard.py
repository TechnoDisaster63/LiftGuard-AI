"""Record a scripted walkthrough of the Streamlit dashboard with Playwright.

    python demo/record_dashboard.py SQUAT.mp4 NON_SQUAT.mp4 --out demo/recording
Starts the dashboard, uploads each clip, runs the real analysis, scrolls the
results, and saves WebM screen recordings (one per clip) to --out.
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parent.parent
ap = argparse.ArgumentParser()
ap.add_argument("clips", nargs="+")
ap.add_argument("--out", default=str(REPO / "demo" / "recording"))
ap.add_argument("--port", default="8599")
args = ap.parse_args()
out = Path(args.out); out.mkdir(parents=True, exist_ok=True)

server = subprocess.Popen([sys.executable, "-m", "streamlit", "run", str(REPO / "dashboard" / "app.py"),
                           "--server.headless", "true", "--server.port", args.port,
                           "--browser.gatherUsageStats", "false", "--theme.base", "dark", "--client.toolbarMode", "viewer"],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
url = f"http://localhost:{args.port}"


SCROLLER = """(dy) => {
  const els = [...document.querySelectorAll('section, div')].filter(e => e.scrollHeight > e.clientHeight + 20 && getComputedStyle(e).overflowY.match(/auto|scroll/) && e.clientWidth > 700);
  (els[0] || document.scrollingElement).scrollBy(0, dy);
}"""


def smooth_scroll(page, total, steps=40, pause=0.05):
    for _ in range(steps):
        page.evaluate(SCROLLER, total / steps)
        time.sleep(pause)


try:
    time.sleep(6)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for n, clip in enumerate(args.clips):
            ctx = browser.new_context(viewport={"width": 1280, "height": 720}, record_video_dir=str(out / f"clip{n}"),
                                      record_video_size={"width": 1280, "height": 720})
            page = ctx.new_page()
            page.goto(url); page.wait_for_selector("text=LiftGuard-AI", timeout=60000)
            time.sleep(3)
            page.set_input_files("input[type=file]", clip)
            time.sleep(2.5)
            page.get_by_role("button", name="Analyze video").click()
            page.wait_for_selector("text=Session history", timeout=240000)
            page.wait_for_function("() => !document.body.innerText.includes('Tracking 33 body landmarks')", timeout=240000)
            time.sleep(4)
            vid = page.query_selector("video")
            if vid:
                page.evaluate("v => { v.muted = true; v.play(); }", vid)
                time.sleep(9)
            for _ in range(7):
                smooth_scroll(page, 380); time.sleep(3.5)
            smooth_scroll(page, -3000, steps=30); time.sleep(2)
            ctx.close()
        browser.close()
finally:
    server.terminate()
