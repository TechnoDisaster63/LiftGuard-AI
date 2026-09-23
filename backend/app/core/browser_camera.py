"""A camera source fed by the viewer's browser.

The live page captures the device camera with getUserMedia and sends JPEG
frames over the existing /ws/live socket. This class looks like the parts
of cv2.VideoCapture that SessionManager uses (read / isOpened / get / set /
release), so the analysis loop runs unchanged whether the frames come from
a local webcam, a video file, or a browser anywhere on the internet.

Only the newest frame is kept. If analysis is slower than the browser, old
frames are dropped instead of queuing up, so the overlay stays close to live.
"""
from __future__ import annotations

import threading

BROWSER_SOURCE = "browser"
# A 640x360 JPEG is ~30-60 KB. Anything far bigger is not a camera frame.
MAX_FRAME_BYTES = 2 * 1024 * 1024


def is_browser_source(source) -> bool:
    return isinstance(source, str) and source == BROWSER_SOURCE


class BrowserFrameSource:
    def __init__(self, wait_seconds: float = 0.5, decode=None):
        self._cond = threading.Condition()
        self._jpeg: bytes | None = None
        self._seq = 0
        self._read_seq = 0
        self._closed = False
        self.wait_seconds = wait_seconds
        self._decode = decode or _decode_jpeg
        self.frames_received = 0

    def push(self, jpeg: bytes) -> bool:
        """Store the newest frame from the browser. Returns False if rejected."""
        if not jpeg or len(jpeg) > MAX_FRAME_BYTES:
            return False
        with self._cond:
            if self._closed:
                return False
            self._jpeg = jpeg
            self._seq += 1
            self.frames_received += 1
            self._cond.notify_all()
        return True

    def read(self):
        """(ok, frame) like VideoCapture.read(). Waits briefly for a frame
        newer than the last one returned; never returns the same frame twice."""
        with self._cond:
            if not self._closed and self._seq == self._read_seq:
                self._cond.wait(self.wait_seconds)
            if self._closed or self._seq == self._read_seq or self._jpeg is None:
                return False, None
            jpeg, self._read_seq = self._jpeg, self._seq
        frame = self._decode(jpeg)  # outside the lock: decoding takes a few ms
        if frame is None or not getattr(frame, "size", 0):
            return False, None
        return True, frame

    def isOpened(self) -> bool:  # noqa: N802 - VideoCapture API
        return not self._closed

    def get(self, _prop) -> float:
        return 0.0

    def set(self, _prop, _value) -> bool:
        return False

    def release(self) -> None:
        with self._cond:
            self._closed = True
            self._jpeg = None
            self._cond.notify_all()


def _decode_jpeg(jpeg: bytes):
    import cv2  # lazy: see the note in session_manager.SessionManager.__init__
    import numpy as np

    return cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
