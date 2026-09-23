from __future__ import annotations
from typing import Any, Optional
from pydantic import BaseModel


class UserTelemetry(BaseModel):
    display_name: Optional[str] = None
    user_id: Optional[int] = None
    total_sessions: Optional[int] = None
    last_seen: Optional[str] = None
    is_guest: bool = True


class TelemetryPayload(BaseModel):
    """One per-frame snapshot of engine state, sent alongside each video
    frame. Mirrors exactly what _draw_full_ui()'s panels used to draw as
    OpenCV pixels in desktop mode — now JSON for the web HUD to render."""
    # Risk panel
    risk_label: Optional[str] = None
    risk_level: Optional[int] = None
    confidence: Optional[float] = None
    uncertainty: Optional[float] = None
    uncertainty_category: Optional[str] = None
    risk_mode: Optional[str] = None
    # Biomechanical features
    spine_flexion: Optional[float] = None
    hip_hinge_angle: Optional[float] = None
    stability_index: Optional[float] = None
    # Fatigue / IRI
    fatigue_score: Optional[float] = None
    fatigue_alert: Optional[str] = None
    fatigue_indicator: dict[str, Any] = {}
    lifts_completed: Optional[int] = None
    injury_risk: Optional[float] = None
    injury_acute: Optional[float] = None
    injury_cumulative: Optional[float] = None
    injury_category: Optional[str] = None
    injury_ci_text: Optional[str] = None
    using_iri_v2: bool = False
    # Exercise
    exercise_status: dict[str, Any] = {}
    # Corrections
    corrections: list[Any] = []
    feedback_message: Optional[str] = None
    # Identity
    user: Optional[UserTelemetry] = None
    id_state: str = "not_started"
    # Status badges
    camera_id: Any = 0
    voice_enabled: bool = True
    voice_speaking: bool = False
    arduino_connected: bool = False
    arduino_calibrated: bool = False
    mirror_mode: bool = False
    calibration_mode: bool = False
    using_temporal: bool = True
    validated_claims_only: bool = True
    # Perf
    fps: Optional[float] = None
    frame_count: int = 0


class ControlMessage(BaseModel):
    """Message the frontend sends over the WebSocket to control the session."""
    action: str  # e.g. "toggle_voice", "switch_camera:1", "reset_reps"
