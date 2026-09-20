from __future__ import annotations
from pydantic import BaseModel


class SessionDefaults(BaseModel):
    camera_id: int
    voice_enabled: bool
    arduino_enabled: bool
    model_complexity: int
    process_every_n: int
    use_temporal: bool


class SessionDefaultsPatch(BaseModel):
    """All fields optional — PATCH only changes what's provided."""
    camera_id: int | None = None
    voice_enabled: bool | None = None
    arduino_enabled: bool | None = None
    model_complexity: int | None = None
    process_every_n: int | None = None
    use_temporal: bool | None = None
