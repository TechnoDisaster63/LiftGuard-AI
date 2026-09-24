"""Run the UNMODIFIED realtime LiftGuard backend with a video file as camera 0.

For machines without a webcam (CI boxes, cloud sandboxes, demo recording).
Every cv2.VideoCapture(<int>) opens the given clip instead, played back at
its native frame rate (a real camera delivers frames in real time, so the
file does too) and looped. Nothing else changes: the same FastAPI app,
SessionManager, liftguard_engine.process_frame(), /ws/live WebSocket and
Next.js dashboard run exactly as they would with a USB camera.

    cd backend
    python ../demo/live_from_file.py /path/to/squats.mp4 --port 8000
    # then in another terminal: cd frontend && npm run dev

Label any recording made this way as "live pipeline, camera fed from a
recorded clip" - it is not a physical-camera validation.
"""
import argparse
import os
import sys
import time
from pathlib import Path

import cv2

ap = argparse.ArgumentParser()
ap.add_argument("video")
ap.add_argument("--host", default="127.0.0.1")
ap.add_argument("--port", type=int, default=8000)
ap.add_argument("--no-loop", action="store_true")
args = ap.parse_args()
VIDEO = str(Path(args.video).resolve())
if not Path(VIDEO).is_file():
    sys.exit(f"Video not found: {VIDEO}")

_RealCapture = cv2.VideoCapture


class FileCamera:
    """Looks like a webcam capture; serves the clip at real-time pace."""

    def __init__(self, index=0, *a, **k):
        self.index = index
        self._cap = _RealCapture(VIDEO)
        self._fps = self._cap.get(cv2.CAP_PROP_FPS) or 25.0
        self._t0 = None
        self._served = 0

    def isOpened(self):
        return self._cap.isOpened()

    def read(self):
        now = time.monotonic()
        if self._t0 is None:
            self._t0 = now
        # Drop frames we are behind on (like a live camera), wait if ahead.
        target = int((now - self._t0) * self._fps)
        if target < self._served:
            time.sleep((self._served - target) / self._fps)
        while self._served < target:
            self._cap.grab(); self._served += 1
        ok, frame = self._cap.read()
        self._served += 1
        if not ok and not args.no_loop:
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            self._t0, self._served = time.monotonic(), 0
            ok, frame = self._cap.read(); self._served = 1
        return ok, frame

    def grab(self):
        return self.read()[0]

    def set(self, prop, value):
        return True  # resolution/buffer hints are meaningless for a file

    def get(self, prop):
        return self._cap.get(prop)

    def release(self):
        self._cap.release()


def patched(source, *a, **k):
    return FileCamera(source) if isinstance(source, int) else _RealCapture(source, *a, **k)


cv2.VideoCapture = patched
print(f"[live_from_file] camera index -> {VIDEO} @ {FileCamera().get(cv2.CAP_PROP_FPS):.0f} fps (realtime pacing)", flush=True)

sys.path.insert(0, os.getcwd())
import uvicorn  # noqa: E402

uvicorn.run("app.main:app", host=args.host, port=args.port, workers=1)
