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


class UserRegisterRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=80)
    # base64-encoded JPEG frames captured from the browser webcam, with or
    # without the "data:image/jpeg;base64," prefix — same face samples the
    # original _enroll_new_user() captured from a live cv2.VideoCapture loop,
    # just sourced from the browser instead of a physical camera the backend
    # process owns.
    images: list[str] = Field(min_length=1)


class UserRegisterResponse(BaseModel):
    user_id: int
    display_name: str
    samples_used: int
    frames_received: int
    status: str = "registered"
