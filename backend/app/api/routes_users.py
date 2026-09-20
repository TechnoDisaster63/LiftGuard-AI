from __future__ import annotations

import base64

from fastapi import APIRouter, HTTPException

from ..core.config import settings
from ..schemas.user import UserOut, UserRegisterRequest, UserRegisterResponse

router = APIRouter(prefix="/api/users", tags=["users"])

# Lazily created on first use: UserManager (and the cv2/numpy stack it sits
# on) must not be imported at module load, so the FastAPI app and its tests
# start without the CV dependencies installed. When created, it is the same
# single shared SQLite-backed, LBPH/ORB-based class the desktop app used,
# untouched. Registration below feeds it browser-captured frames through the
# exact same FaceMatcher.detect_faces() / extract_face_region() /
# register_user() calls _enroll_new_user() made from a live cv2.VideoCapture
# loop - only the frame *source* changed.
_user_manager = None

MIN_FACE_SAMPLES = 10  # same floor _enroll_new_user() used


def _get_user_manager():
    global _user_manager
    if _user_manager is None:
        from ..identity.user_manager_lite import UserManager

        _user_manager = UserManager(db_path=settings.USER_DB_PATH)
    return _user_manager


@router.get("", response_model=list[UserOut])
def list_users():
    return [_to_out(u) for u in _get_user_manager().get_all_users()]


@router.get("/{user_id}", response_model=UserOut)
def get_user(user_id: int):
    user = _get_user_manager().get_user_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return _to_out(user)


@router.post("/register", response_model=UserRegisterResponse)
def register_user(req: UserRegisterRequest):
    if len(req.images) > settings.MAX_REGISTER_IMAGES:
        raise HTTPException(
            status_code=413,
            detail=f"Too many images (max {settings.MAX_REGISTER_IMAGES} per request)",
        )
    for img in req.images:
        if _estimate_decoded_size(img) > settings.MAX_IMAGE_BYTES:
            raise HTTPException(
                status_code=413,
                detail=(
                    "An image exceeds the per-image size limit "
                    f"({settings.MAX_IMAGE_BYTES // (1024 * 1024)} MB)"
                ),
            )

    frames = [_decode_base64_image(img) for img in req.images]
    frames = [f for f in frames if f is not None]
    if not frames:
        raise HTTPException(status_code=400, detail="No decodable images received")

    import cv2

    manager = _get_user_manager()
    face_images = []
    profile_photo = None

    for frame in frames:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = manager.matcher.detect_faces(gray)
        if len(faces) == 0:
            continue
        largest = max(faces, key=lambda f: f[2] * f[3])
        face_img = manager.matcher.extract_face_region(gray, largest)
        if face_img is not None:
            face_images.append(face_img)
            if profile_photo is None:
                profile_photo = frame.copy()

    if len(face_images) < MIN_FACE_SAMPLES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Only found a clear face in {len(face_images)} of {len(frames)} frames "
                f"(need at least {MIN_FACE_SAMPLES}). Try better lighting, face the camera "
                "more directly, and make sure only one face is in frame."
            ),
        )

    username = _unique_username(req.display_name)
    profile = manager.register_user(
        username=username,
        display_name=req.display_name,
        face_images=face_images,
        profile_photo=profile_photo,
    )

    return UserRegisterResponse(
        user_id=profile.user_id,
        display_name=profile.display_name,
        samples_used=len(face_images),
        frames_received=len(frames),
    )


def _unique_username(display_name: str) -> str:
    """Same collision-avoidance _enroll_new_user() used: name_1, name_2, ..."""
    base = display_name.lower().strip().replace(" ", "_").replace("'", "")
    username = base
    count = 1
    while _get_user_manager().get_user_by_username(username):
        username = f"{base}_{count}"
        count += 1
    return username


def _estimate_decoded_size(data_url: str) -> int:
    """Approximate decoded byte size of a base64 payload without decoding it."""
    b64 = data_url
    if "," in b64 and b64.strip().startswith("data:"):
        b64 = b64.split(",", 1)[1]
    return (len(b64.strip()) * 3) // 4


def _decode_base64_image(data_url: str):
    import cv2
    import numpy as np

    try:
        if "," in data_url and data_url.strip().startswith("data:"):
            data_url = data_url.split(",", 1)[1]
        raw = base64.b64decode(data_url)
        arr = np.frombuffer(raw, dtype=np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        return frame
    except Exception:
        return None


def _to_out(user) -> UserOut:
    return UserOut(
        user_id=user.user_id,
        username=user.username,
        display_name=user.display_name,
        baseline=user.baseline,
        settings=user.settings,
        total_sessions=user.total_sessions,
        last_seen=user.last_seen,
        is_guest=user.is_guest,
    )
