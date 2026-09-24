from typing import Any, Optional
from pydantic import BaseModel, Field


class UserOut(BaseModel):
    user_id: int
    username: str
    display_name: str
    baseline: dict[str, Any] = {}
    settings: dict[str, Any] = {}
    total_sessions: int = 0
    last_seen: Optional[str] = None
    is_guest: bool = False
    # True when this user has a face embedding on this machine.
    face_enrolled: bool = False


class UserRegisterRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=80)
    # base64 JPEG frames from the browser camera (with or without the
    # "data:image/jpeg;base64," prefix). Only accepted from a browser on the
    # backend's own machine; decoded in memory, embedded, never stored.
    images: list[str] = Field(min_length=1)


class UserRegisterResponse(BaseModel):
    user_id: int
    display_name: str
    samples_used: int
    frames_received: int
    status: str = "registered"


class FaceEnrollRequest(BaseModel):
    images: list[str] = Field(min_length=1)


class FaceIdentifyRequest(BaseModel):
    images: list[str] = Field(min_length=1)


class FaceIdentifyResponse(BaseModel):
    matched: bool
    user: Optional[UserOut] = None
    # no_face | no_match | ambiguous when matched is False
    reason: Optional[str] = None
    frames_with_face: int = 0


class FaceStatus(BaseModel):
    available: bool
    # models_missing, or an OpenCV error name, when not available
    reason: Optional[str] = None
    # True when this request came from a browser on the backend's machine
    local: bool
    enrolled_count: int = 0
