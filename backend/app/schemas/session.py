from __future__ import annotations
from typing import Any, Optional
from pydantic import BaseModel


class SessionStartRequest(BaseModel):
    """All fields optional — anything omitted falls back to the current
    values in /api/settings (session_defaults), not a hardcoded default."""
    camera_id: Optional[int] = None
    voice_enabled: Optional[bool] = None
    arduino_enabled: Optional[bool] = None
    model_complexity: Optional[int] = None
    process_every_n: Optional[int] = None
    use_temporal: Optional[bool] = None


class SessionStartResponse(BaseModel):
    session_id: str
    status: str = "started"


class SessionReport(BaseModel):
    user: Optional[dict[str, Any]] = None
    exercise: dict[str, Any] = {}
    fatigue: dict[str, Any] = {}
    peak_risk: int = 0
    iri_history: list[float] = []
    spine_history: list[float] = []
    using_temporal: bool = False
    using_iri_v2: bool = False
    camera_id: int = 0
    iri: Optional[dict[str, Any]] = None
    uncertainty: Optional[dict[str, Any]] = None
