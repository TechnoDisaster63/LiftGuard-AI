"""
SessionManager - drives the LiftGuardAI engine for the web dashboard.

This wraps the EXACT SAME per-frame pipeline the original desktop app used
(LiftGuardAI.process_frame), just swapping the cv2.imshow()/waitKey() sink
for WebSocket-ready output. No AI logic is touched here - this is glue code
that mirrors LiftGuardAI.run() step by step, see the original in
liftguard_engine.py for the reference implementation this is built from.
"""


# Live-screen fields backed by models that are not validated for this demo
# (TCN / risk classifier confidence and uncertainty, injury risk index).
# docs/REVIVAL_SCOPE.md puts TCN claims and injury probabilities out of scope,
# so the live telemetry sends None for them unless validated_claims_only is
# turned off for development.
UNVALIDATED_TELEMETRY_OFF = {
    "risk_label": None,
    "risk_level": None,
    "confidence": None,
    "uncertainty": None,
    "uncertainty_category": None,
    "risk_mode": None,
    "injury_risk": None,
    "injury_acute": None,
    "injury_cumulative": None,
    "injury_category": None,
    "injury_ci_text": None,
    "using_iri_v2": False,
    "using_temporal": False,
}


def _live_reps(engine) -> list:
    feed = getattr(engine, "live_squat", None)
    counter = getattr(feed, "counter", None)
    return list(counter.machine.reps) if counter is not None else []


def live_fatigue_indicator(engine) -> dict:
    from ..video_analysis.analyzer import AnalysisConfig, _fatigue

    return _fatigue(_live_reps(engine), AnalysisConfig().baseline_reps)


def live_exercise_summary(engine) -> dict:
    """Session exercise summary from the calibrated squat counter.

    Flat scalars so the report page's key/value list renders them directly.
    """
    reps = _live_reps(engine)
    status = getattr(engine, "current_exercise_status", None) or {}
    gates = status.get("rep_gates") or {}

    def avg(key):
        return round(sum(r[key] for r in reps) / len(reps), 2) if reps else None

    from ..video_analysis.movements import MOVEMENT_MODES

    feed = getattr(engine, "live_squat", None)
    mode = getattr(feed, "mode", "squat")
    info = MOVEMENT_MODES.get(mode, MOVEMENT_MODES["squat"])
    summary = {
        "exercise": info["label"] if reps else f"No {info['noun']} reps counted",
        "movement_mode": mode,
        "total_reps": len(reps),
        "reps_with_form_flags": sum(bool(r.get("form_flags")) for r in reps),
        "avg_rep_seconds": avg("duration_seconds"),
    }
    if mode == "pushup":
        summary["avg_deepest_elbow_angle_deg"] = avg("min_elbow_angle")
    else:
        summary["avg_deepest_knee_angle_deg"] = avg("min_knee_angle")
    summary.update({
        "avg_range_of_motion_deg": avg("rom_degrees"),
        "rejected_candidates": sum(int(v or 0) for v in gates.values()),
        "calibration_mode": status.get("calibration_mode"),
        "counter": info["source"],
    })
    return summary


def live_fatigue_summary(engine) -> dict:
    indicator = live_fatigue_indicator(engine)
    return {
        "indicator": "rep-based fatigue indicator (0-100, higher = more drift)",
        "status": indicator["status"],
        "score": indicator["score"] if indicator["status"] != "INSUFFICIENT_REPS" else None,
        **indicator["signals"],
    }


class CameraError(RuntimeError):
    """A camera problem with a message meant for the person at the laptop."""


CAMERA_HELP = (
    "Check that the camera is connected and not in use by another app "
    "(Zoom, Teams, the Windows Camera app, or a browser tab on the Register "
    "page). On Windows, also check Settings > Privacy & security > Camera: "
    "'Camera access' and 'Let desktop apps access your camera' must be on."
)


from .browser_camera import BrowserFrameSource, is_browser_source


def camera_source(camera_id):
    """LIFTGUARD_CAMERA_SOURCE (a video file path or stream URL) overrides the
    numeric camera id. Used for testing with a recorded clip and for IP cameras."""
    import os

    # The viewer chose their own device camera: a server-side clip or IP
    # camera override must not replace it.
    if is_browser_source(camera_id):
        return camera_id
    override = os.getenv("LIFTGUARD_CAMERA_SOURCE", "").strip()
    return override or camera_id


def open_camera(source, warmup_seconds: float = 3.0):
    """Open a camera or video source and make sure it actually delivers frames.

    Returns (cap, first_frame). Raises CameraError with a readable message.
    On Windows, numeric cameras try DirectShow first: the default Media
    Foundation backend can take many seconds to open or hang on some webcams.
    """
    import sys
    import time

    import cv2

    label = f"camera {source}" if isinstance(source, int) else f"video source {source}"
    attempts = []
    if isinstance(source, int) and sys.platform == "win32":
        attempts.append(cv2.CAP_DSHOW)
    attempts.append(None)

    for backend in attempts:
        cap = cv2.VideoCapture(source) if backend is None else cv2.VideoCapture(source, backend)
        if not cap.isOpened():
            cap.release()
            continue
        if isinstance(source, int):
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        deadline = time.monotonic() + warmup_seconds
        while time.monotonic() < deadline:
            ok, frame = cap.read()
            if ok and frame is not None and frame.size:
                return cap, frame
            time.sleep(0.05)
        cap.release()
        raise CameraError(
            f"Opened {label} but it isn't sending any video. It is probably in use by "
            f"another app or blocked by privacy settings. {CAMERA_HELP}"
        )
    raise CameraError(f"Couldn't open {label}. {CAMERA_HELP}")


class SessionManager:
    """One SessionManager instance = one live camera session."""

    validated_claims_only = True

    def __init__(self, voice_enabled=True, arduino_enabled=True,
                 model_complexity=0, process_every_n=1, use_temporal=True, movement_mode="squat"):
        # Imported here (not at module load) so the FastAPI app and its
        # test suite can start without the heavy CV/ML stack (opencv,
        # mediapipe, torch) installed. See requirements-dev.txt.
        from .liftguard_engine import LiftGuardAI

        self.engine = LiftGuardAI(
            voice_enabled=voice_enabled,
            arduino_enabled=arduino_enabled,
            model_complexity=model_complexity,
            process_every_n=process_every_n,
            use_temporal=use_temporal,
        )
        # Tells process_frame() to use _draw_web_frame() (skeleton only) at
        # its tail instead of _draw_full_ui() (full OpenCV HUD baked into
        # pixels). See liftguard_engine.py's process_frame for the branch -
        # unset, this attribute defaults to "desktop", so run_standalone.py
        # is completely unaffected by this.
        self.engine.render_mode = "web"
        self.movement_mode = movement_mode
        self.cap = None
        self.active = False
        self.camera_id = 0
        # A VideoCapture and its mutable ML pipeline cannot be advanced by
        # two WebSocket loops at once. Only one live stream may drive a
        # session; extra dashboards receive a clear close code instead of
        # racing camera reads and model state.
        import threading
        self._stream_lock = threading.Lock()
        # Guards cap.read() (WebSocket thread) against cap.release() /
        # camera switches (stop and control requests on other threads).
        self._cap_lock = threading.Lock()

    def _camera_lock(self):
        import threading

        lock = getattr(self, "_cap_lock", None)
        if lock is None:  # instances built with __new__ in tests
            lock = self._cap_lock = threading.Lock()
        return lock

    def acquire_stream(self) -> bool:
        return self._stream_lock.acquire(blocking=False)

    def has_viewer(self) -> bool:
        return self._stream_lock.locked()

    def release_stream(self) -> None:
        if self._stream_lock.locked():
            self._stream_lock.release()

    # ── Lifecycle ────────────────────────────────────────────
    def start(self, camera_id: int = 0):
        """Mirrors the camera-open portion of LiftGuardAI.run() (minus the
        cv2.imshow loop itself, which the WebSocket route drives instead)."""
        import cv2  # lazy: see note in __init__

        source = camera_source(camera_id)
        self.camera_id = source
        if is_browser_source(source):
            # Frames arrive later over the WebSocket (push_browser_frame);
            # there is nothing to open or warm up here.
            self.cap = BrowserFrameSource()
        else:
            self.cap, _ = open_camera(source)
        camera_id = source

        # Squat counter timing: a video file has a real fps; a webcam's
        # nominal fps is not the processing rate, so let the engine measure it.
        # The same goes for a browser camera.
        source_fps = None
        if isinstance(camera_id, str) and not camera_id.isdigit() and not is_browser_source(camera_id):
            source_fps = float(self.cap.get(cv2.CAP_PROP_FPS) or 0) or None
            # open_camera consumed one frame; rewind a file so no clip frame is lost.
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        self.engine.configure_live_squat(source_fps, mode=getattr(self, "movement_mode", "squat"))

        # Same face-ID call as the desktop run(). Blocking is acceptable -
        # start() runs once, off the per-frame loop.
        try:
            self._identify_user(camera_id)
        except Exception:
            self.cap.release()
            self.cap = None
            raise
        if hasattr(self.engine, "current_camera_id"):
            self.engine.current_camera_id = camera_id

        self.engine.session_active = True
        self.active = True

    def _identify_user(self, camera_id):
        if hasattr(self.engine, "user_manager"):
            # Headless: a web request has no console for input() and no
            # desktop for cv2.imshow. Enrolled users are matched; otherwise
            # the session starts as Guest. A video file source skips face ID
            # so no frames of the clip are consumed before analysis.
            # A browser camera has sent no frames yet at this point, so it
            # starts as Guest too.
            is_file = isinstance(camera_id, str) and not camera_id.isdigit()
            self.engine.current_user = self.engine.user_manager.identify_from_camera(
                self.cap, timeout=0.0 if is_file else 8.0,
                allow_new_user=False, allow_guest=True, interactive=False
            )
            if getattr(self.engine.current_user, "baseline", None):
                self.engine.risk_classifier.calibrate_to_person(
                    self.engine.current_user.baseline
                )
            if not getattr(self.engine.current_user, "is_guest", True):
                self.engine.user_manager.start_session(self.engine.current_user.user_id)

    def push_browser_frame(self, jpeg: bytes) -> bool:
        """Hand one JPEG from the viewer's browser to the analysis loop.
        Ignored (False) unless this session uses the browser camera."""
        cap = self.cap
        if not self.active or not isinstance(cap, BrowserFrameSource):
            return False
        return cap.push(jpeg)

    def uses_browser_camera(self) -> bool:
        return isinstance(self.cap, BrowserFrameSource)

    def stop(self):
        self.active = False
        if self.engine.session_active:
            self.engine._end_session()
        with self._camera_lock():
            if self.cap is not None:
                self.cap.release()
                self.cap = None
        if self.engine.arduino_connected:
            self.engine.arduino.laser_off()
            self.engine.arduino.disconnect()

    def stop_quietly(self):
        """Release the camera without touching the engine; never raises."""
        self.active = False
        try:
            with self._camera_lock():
                if self.cap is not None:
                    self.cap.release()
                    self.cap = None
        except Exception:
            pass

    # ── Per-frame step (called in a loop by the WS route) ─────
    def step(self):
        """Reads one frame, runs it through the UNCHANGED process_frame()
        pipeline, and returns (jpeg_bytes, telemetry_dict)."""
        import cv2  # lazy: see note in __init__

        with self._camera_lock():
            if not self.active or self.cap is None:
                return None, None
            ret, frame = self.cap.read()
        if not ret or frame is None:
            return None, None

        if self.engine.mirror_mode:
            frame = cv2.flip(frame, 1)

        output = self.engine.process_frame(frame)  # same call the desktop app makes

        recorder = getattr(self, "contrib_recorder", None)
        if recorder is not None and self.engine.frame_count % self.engine.process_every_n == 0:
            # Opt-in only (set by the start route after a consent check).
            # Body landmarks of this processed frame, never the frame itself.
            try:
                h, w = frame.shape[:2]
                recorder.add(self.engine.cached_landmarks_raw, w, h, mirror=self.engine.mirror_mode)
            except Exception:
                pass  # recording must never break the live session

        ok, buf = cv2.imencode(".jpg", output, [cv2.IMWRITE_JPEG_QUALITY, 80])
        jpeg_bytes = buf.tobytes() if ok else None

        return jpeg_bytes, self._collect_telemetry()

    def _collect_telemetry(self) -> dict:
        """Mirrors exactly what _draw_full_ui()'s panels used to draw as
        OpenCV pixels - user panel, risk panel, exercise panel, status
        badges, fatigue/IRI panel, FPS - just as JSON instead, so the web
        dashboard can render it as HTML/CSS instead of burned-in text."""
        e = self.engine
        risk = e.current_risk_result or {}
        fatigue = e.current_fatigue_status or {}
        injury = e.current_injury_risk or {}
        features = e.current_features or {}
        user = getattr(e, "current_user", None)

        fatigue_indicator = live_fatigue_indicator(e)

        fps = None
        if e.frame_times:
            import numpy as _np
            fps = round(1.0 / (float(_np.mean(e.frame_times)) + 1e-6), 1)

        telemetry = {
            # Risk panel
            "risk_label": risk.get("risk_label"),
            "risk_level": risk.get("risk_level"),
            "confidence": risk.get("confidence"),
            "uncertainty": risk.get("uncertainty"),
            "uncertainty_category": risk.get("uncertainty_category"),
            "risk_mode": risk.get("mode"),
            # Biomechanical features (bottom of the old risk panel)
            "spine_flexion": features.get("spine_flexion"),
            "hip_hinge_angle": features.get("hip_hinge_angle"),
            "stability_index": features.get("stability_index"),
            # Fatigue / IRI panel
            "fatigue_score": fatigue.get("fatigue_score"),
            "fatigue_alert": fatigue.get("alert_level"),
            "lifts_completed": fatigue.get("lifts_completed"),
            "injury_risk": injury.get("combined_iri", injury.get("probability")),
            "injury_acute": injury.get("acute_risk"),
            "injury_cumulative": injury.get("cumulative_risk"),
            "injury_category": injury.get("category"),
            "injury_ci_text": (injury.get("confidence_interval") or {}).get("text"),
            "using_iri_v2": e.using_iri_v2,
            # Exercise panel
            "exercise_status": e.current_exercise_status,
            # Corrections
            "corrections": e.current_corrections,
            "feedback_message": e.feedback_message,
            # User / identity panel
            "user": {
                "display_name": getattr(user, "display_name", None),
                "user_id": getattr(user, "user_id", None),
                "total_sessions": getattr(user, "total_sessions", None),
                "last_seen": getattr(user, "last_seen", None),
                "is_guest": getattr(user, "is_guest", True),
            } if user else None,
            "id_state": getattr(e, "id_state", "not_started"),
            # Status badges
            "camera_id": e.current_camera_id,
            "voice_enabled": e.voice_enabled,
            "voice_speaking": getattr(e.speaker, "is_speaking", False),
            "arduino_connected": e.arduino_connected,
            "arduino_calibrated": getattr(e.arduino, "is_calibrated", False) if e.arduino_connected else False,
            "mirror_mode": e.mirror_mode,
            "calibration_mode": e.calibration_mode,
            "using_temporal": e.using_temporal,
            "process_every_n": e.process_every_n,
            # Perf
            "fps": fps,
            "frame_count": e.frame_count,
        }
        # Fatigue indicator from the counted reps (same rule as the offline
        # report): 0-100, higher = more drift in rep duration, depth and trunk
        # lean versus the first reps. None until there are enough reps.
        # The legacy fatigue_engine score (100 = fresh) read as "100% fatigue"
        # from the first frame on the dashboard.
        telemetry["fatigue_indicator"] = fatigue_indicator
        telemetry["fatigue_score"] = (
            fatigue_indicator["score"] if fatigue_indicator["status"] != "INSUFFICIENT_REPS" else None
        )
        telemetry["fatigue_alert"] = fatigue_indicator["status"]
        telemetry["lifts_completed"] = e.current_exercise_status.get("rep_count", 0)
        if self.validated_claims_only:
            telemetry.update(UNVALIDATED_TELEMETRY_OFF)
        telemetry["validated_claims_only"] = self.validated_claims_only
        return telemetry

    # ── Controls (mirrors the keyboard shortcuts in run()) ────
    def handle_control(self, action: str) -> str:
        """Runs the same action the original keyboard shortcuts triggered,
        and returns a short status string. The original methods only
        print() to a console the web user never sees - this reads the
        resulting engine state back out so the frontend can show a toast
        instead of a silent no-op."""
        e = self.engine

        if action == "toggle_voice":
            e.toggle_voice()
            return f"Voice feedback {'on' if e.voice_enabled else 'off'}"
        elif action == "toggle_arduino":
            e.toggle_arduino()
            return f"Laser {'connected' if e.arduino_connected else 'disconnected'}"
        elif action == "toggle_temporal":
            e.toggle_temporal()
            return f"Using {'temporal (TCN) model' if e.using_temporal else 'frame-level model'}"
        elif action == "toggle_mirror":
            e.toggle_mirror()
            return f"Mirror {'on' if e.mirror_mode else 'off'}"
        elif action == "save_model":
            e.save_model()
            return "Model saved"
        elif action == "reset_reps":
            e.reset_reps()
            return "Rep counter reset"
        elif action == "export_data":
            import os

            e.export_data()
            # ExerciseTracker writes relative to the backend's working directory.
            return f"Session data exported as CSV to {os.path.abspath('exports')}"
        elif action == "list_users":
            e.list_users()
            return "User list printed to server console"
        elif action == "start_calibration":
            e.start_calibration()
            return "Calibration started - follow the on-screen prompts"
        elif action == "complete_calibration":
            e.complete_calibration()
            return "Calibration complete"
        elif action == "connect_ip_camera":
            return self._switch_camera(e.ip_camera_url)
        elif action.startswith("switch_camera:"):
            try:
                cam_id = int(action.split(":", 1)[1])
            except ValueError as exc:
                raise ValueError("Camera id must be a number") from exc
            return self._switch_camera(cam_id)
        elif action.startswith("connect_wifi_laser:"):
            host = action.split(":", 1)[1]
            ok = e.connect_wifi_laser(host)
            return f"WiFi laser {'connected at ' + host if ok else 'connection failed'}"
        elif action == "connect_usb_laser":
            ok = e.connect_usb_laser()
            return f"USB laser {'connected' if ok else 'not found'}"
        elif action == "speed_up":
            e.adjust_speed(faster=True)
            return f"Processing every {e.process_every_n} frame(s) - faster"
        elif action == "speed_down":
            e.adjust_speed(faster=False)
            return f"Processing every {e.process_every_n} frame(s) - slower"
        else:
            raise ValueError(f"Unknown control action: {action}")

    def _switch_camera(self, source) -> str:
        """Open the new camera first; keep the current one if it fails."""
        try:
            new_cap, _ = open_camera(source)
        except CameraError as exc:
            return f"Kept the current camera. {exc}"
        with self._camera_lock():
            old, self.cap = self.cap, new_cap
            self.camera_id = source
            self.engine.current_camera_id = source
        if old is not None:
            old.release()
        return f"Switched to {'camera ' + str(source) if isinstance(source, int) else 'IP camera'}"

    def get_uncertainty_summary(self) -> dict:
        """JSON equivalent of engine.show_uncertainty_summary(), which only
        prints to console. Empty dict if the uncertainty manager isn't
        active for this session (e.g. not using the temporal model)."""
        e = self.engine
        if getattr(e, "uncertainty_manager", None):
            return e.uncertainty_manager.get_uncertainty_summary()
        return {}

    def get_session_report(self) -> dict:
        """JSON equivalent of engine.show_session_report(), which only
        prints to console - same underlying data, just returned instead."""
        e = self.engine
        report = {
            "user": {
                "display_name": getattr(e.current_user, "display_name", "Guest"),
                "user_id": getattr(e.current_user, "user_id", None),
                "is_guest": getattr(e.current_user, "is_guest", True),
            } if getattr(e, "current_user", None) else None,
            # Built from the calibrated squat counter and the rep-based
            # fatigue indicator (the legacy tracker reported 0 reps).
            "exercise": live_exercise_summary(e),
            "fatigue": live_fatigue_summary(e),
            "peak_risk": e._session_peak_risk,
            "iri_history": e._session_iri_history,
            "spine_history": e._session_spine_history,
            "using_temporal": getattr(e, "using_temporal", False),
            "using_iri_v2": getattr(e, "using_iri_v2", False),
            "camera_id": e.current_camera_id,
        }
        if self.validated_claims_only:
            # Same rule as live telemetry: no unvalidated IRI / TCN output in
            # stored or returned reports. peak_risk stays an int for the DB
            # schema; the UI does not display it.
            report.update({"iri_history": [], "using_temporal": False, "using_iri_v2": False})
            return report
        if hasattr(e.injury_predictor, "get_session_report"):
            report["iri"] = e.injury_predictor.get_session_report()
        if e.uncertainty_manager:
            report["uncertainty"] = e.uncertainty_manager.get_uncertainty_summary()
        return report
