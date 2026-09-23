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

    return {
        "exercise": "Squat" if reps else "No squat reps counted",
        "total_reps": len(reps),
        "reps_with_form_flags": sum(bool(r.get("form_flags")) for r in reps),
        "avg_rep_seconds": avg("duration_seconds"),
        "avg_deepest_knee_angle_deg": avg("min_knee_angle"),
        "avg_range_of_motion_deg": avg("rom_degrees"),
        "rejected_candidates": sum(int(v or 0) for v in gates.values()),
        "calibration_mode": status.get("calibration_mode"),
        "counter": "calibrated_squat_counter",
    }


def live_fatigue_summary(engine) -> dict:
    indicator = live_fatigue_indicator(engine)
    return {
        "indicator": "rep-based fatigue indicator (0-100, higher = more drift)",
        "status": indicator["status"],
        "score": indicator["score"] if indicator["status"] != "INSUFFICIENT_REPS" else None,
        **indicator["signals"],
    }


class SessionManager:
    """One SessionManager instance = one live camera session."""

    validated_claims_only = True

    def __init__(self, voice_enabled=True, arduino_enabled=True,
                 model_complexity=0, process_every_n=1, use_temporal=True):
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
        self.cap = None
        self.active = False
        self.camera_id = 0
        # A VideoCapture and its mutable ML pipeline cannot be advanced by
        # two WebSocket loops at once. Only one live stream may drive a
        # session; extra dashboards receive a clear close code instead of
        # racing camera reads and model state.
        import threading
        self._stream_lock = threading.Lock()

    def acquire_stream(self) -> bool:
        return self._stream_lock.acquire(blocking=False)

    def release_stream(self) -> None:
        if self._stream_lock.locked():
            self._stream_lock.release()

    # ── Lifecycle ────────────────────────────────────────────
    def start(self, camera_id: int = 0):
        """Mirrors the camera-open portion of LiftGuardAI.run() (minus the
        cv2.imshow loop itself, which the WebSocket route drives instead)."""
        import cv2  # lazy: see note in __init__

        self.camera_id = camera_id
        self.cap = cv2.VideoCapture(camera_id)
        if not self.cap.isOpened():
            raise RuntimeError(f"Cannot open camera {camera_id}")

        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        # Squat counter timing: a video file has a real fps; a webcam's
        # nominal fps is not the processing rate, so let the engine measure it.
        source_fps = None
        if isinstance(camera_id, str) and not camera_id.isdigit():
            source_fps = float(self.cap.get(cv2.CAP_PROP_FPS) or 0) or None
        self.engine.configure_live_squat(source_fps)

        # Same face-ID call as the desktop run(). Blocking is acceptable -
        # start() runs once, off the per-frame loop.
        if hasattr(self.engine, "user_manager"):
            # Headless: a web request has no console for input() and no
            # desktop for cv2.imshow. Enrolled users are matched; otherwise
            # the session starts as Guest. A video file source skips face ID
            # so no frames of the clip are consumed before analysis.
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

        self.engine.session_active = True
        self.active = True

    def stop(self):
        self.active = False
        if self.engine.session_active:
            self.engine._end_session()
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        if self.engine.arduino_connected:
            self.engine.arduino.laser_off()
            self.engine.arduino.disconnect()

    # ── Per-frame step (called in a loop by the WS route) ─────
    def step(self):
        """Reads one frame, runs it through the UNCHANGED process_frame()
        pipeline, and returns (jpeg_bytes, telemetry_dict)."""
        import cv2  # lazy: see note in __init__

        if not self.active or self.cap is None:
            return None, None

        ret, frame = self.cap.read()
        if not ret:
            return None, None

        if self.engine.mirror_mode:
            frame = cv2.flip(frame, 1)

        output = self.engine.process_frame(frame)  # same call the desktop app makes

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
            e.export_data()
            return "Session data exported"
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
            self.cap = e.connect_ip_camera(self.cap)
            return "IP camera connect attempted - check the video feed"
        elif action.startswith("switch_camera:"):
            cam_id = int(action.split(":", 1)[1])
            self.cap = e.switch_camera(self.cap, cam_id)
            return f"Switched to camera {cam_id}"
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
