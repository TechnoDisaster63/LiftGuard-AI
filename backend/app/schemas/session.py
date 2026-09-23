from __future__ import annotations
from typing import Any, Literal, Optional, Union
from pydantic import BaseModel


class SessionStartRequest(BaseModel):
    """All fields optional — anything omitted falls back to the current
    values in /api/settings (session_defaults), not a hardcoded default."""
    # A camera index on the backend machine, or "browser": the viewer's own
    # device camera, streamed from the live page over the WebSocket.
    camera_id: Optional[Union[int, Literal["browser"]]] = None
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
    # A camera index, a clip path / stream URL, or "browser".
    camera_id: Union[int, str] = 0
    iri: Optional[dict[str, Any]] = None
    uncertainty: Optional[dict[str, Any]] = None
