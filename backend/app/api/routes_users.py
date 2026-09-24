from __future__ import annotations

import base64

from fastapi import APIRouter, Depends, HTTPException, Request

from ..core.config import settings
from ..identity.locality import is_local_request, require_local
from ..schemas.user import (
    FaceEnrollRequest,
    FaceIdentifyRequest,
    FaceIdentifyResponse,
    FaceStatus,
    UserOut,
    UserRegisterRequest,
    UserRegisterResponse,
)

router = APIRouter(prefix="/api/users", tags=["users"])

# Lazily created on first use: UserManager (and the cv2/numpy stack it sits
# on) must not be imported at module load, so the FastAPI app and its tests
# start without the CV dependencies installed.
#
# Face ID is on-device: every endpoint that receives camera frames requires
# the browser to be on the same machine as this backend (require_local).
# Frames are decoded in memory, turned into a face embedding and dropped;
# only the embedding is stored, in the local user database. Nothing here is
# logged, and none of it goes to contributions.
_user_manager = None

MIN_FACE_SAMPLES = 5  # face_id.MIN_ENROLL_SAMPLES; checked again there


def _get_user_manager():
    global _user_manager
    if _user_manager is None:
        from ..identity.user_manager_lite import UserManager

        _user_manager = UserManager(db_path=settings.USER_DB_PATH)
    return _user_manager


@router.get("", response_model=list[UserOut])
def list_users():
    manager = _get_user_manager()
    return [_to_out(u, manager) for u in manager.get_all_users()]


@router.get("/face-id/status", response_model=FaceStatus)
def face_id_status(request: Request):
    """Whether face ID can run, and whether this browser is on the backend's machine."""
    status = _get_user_manager().face_id_status()
    return FaceStatus(
        available=status["available"],
        reason=status["reason"],
        local=is_local_request(request),
        enrolled_count=len(status["enrolled_user_ids"]),
    )


@router.get("/{user_id}", response_model=UserOut)
def get_user(user_id: int):
    manager = _get_user_manager()
    user = manager.get_user_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return _to_out(user, manager)


@router.post("/register", response_model=UserRegisterResponse, dependencies=[Depends(require_local)])
def register_user(req: UserRegisterRequest):
    embeddings, received = _embeddings_from_images(req.images)
    manager = _get_user_manager()
    username = _unique_username(req.display_name)
    try:
        profile = manager.register_user(username=username, display_name=req.display_name,
                                        embeddings=embeddings)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=_enroll_hint(str(exc), embeddings, received)) from exc
    return UserRegisterResponse(
        user_id=profile.user_id,
        display_name=profile.display_name,
        samples_used=sum(e is not None for e in embeddings),
        frames_received=received,
    )


@router.post("/{user_id}/face", response_model=UserOut, dependencies=[Depends(require_local)])
def enroll_face(user_id: int, req: FaceEnrollRequest):
    """(Re-)enroll an existing user's face, e.g. after the upgrade deleted old face images."""
    manager = _get_user_manager()
    user = manager.get_user_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    embeddings, received = _embeddings_from_images(req.images)
    ok, err = manager.enroll_face(user_id, embeddings)
    if not ok:
        raise HTTPException(status_code=400, detail=_enroll_hint(err, embeddings, received))
    return _to_out(user, manager)


@router.delete("/{user_id}/face", response_model=UserOut)
def forget_face(user_id: int):
    """Delete a user's face embedding. Their account and history stay."""
    manager = _get_user_manager()
    user = manager.get_user_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    manager.forget_face(user_id)
    return _to_out(user, manager)


@router.post("/identify", response_model=FaceIdentifyResponse, dependencies=[Depends(require_local)])
def identify(req: FaceIdentifyRequest):
    """On demand: which enrolled user is in front of this computer's camera?

    Needs the same user on at least 3 of the frames and no other user on any.
    """
    embeddings, _ = _embeddings_from_images(req.images, check_limits=True)
    manager = _get_user_manager()
    votes: dict[int, int] = {}
    best = 0.0
    faces = 0
    for e in embeddings:
        if e is None:
            continue
        faces += 1
        uid, score = manager.match_embedding(e)
        best = max(best, score)
        if uid is not None:
            votes[uid] = votes.get(uid, 0) + 1
    if len(votes) == 1:
        uid, n = next(iter(votes.items()))
        if n >= min(3, faces):
            user = manager.get_user_by_id(uid)
            return FaceIdentifyResponse(matched=True, user=_to_out(user, manager), frames_with_face=faces)
    reason = "no_face" if faces == 0 else ("ambiguous" if len(votes) > 1 else "no_match")
    return FaceIdentifyResponse(matched=False, reason=reason, frames_with_face=faces)


def _embeddings_from_images(images: list[str], check_limits: bool = True):
    """Decode frames in memory and embed them. Returns ([embedding or None], frames decoded).

    The decoded frames are not kept; only the embeddings leave this function.
    """
    if check_limits:
        _check_image_limits(images)
    manager = _get_user_manager()
    if manager.embedder is None:
        raise HTTPException(
            status_code=503,
            detail="Face ID isn't set up on this computer (the face model files are missing). "
            "Run `python fetch_face_models.py` in backend/, then restart LiftGuard.",
        )
    embeddings, received = [], 0
    for img in images:
        frame = _decode_base64_image(img)
        if frame is None:
            continue
        received += 1
        embeddings.append(manager.embed_bgr(frame).embedding)
        del frame
    if not received:
        raise HTTPException(status_code=400, detail="No decodable images received")
    return embeddings, received


def _check_image_limits(images: list[str]) -> None:
    if len(images) > settings.MAX_REGISTER_IMAGES:
        raise HTTPException(
            status_code=413,
            detail=f"Too many images (max {settings.MAX_REGISTER_IMAGES} per request)",
        )
    for img in images:
        if _estimate_decoded_size(img) > settings.MAX_IMAGE_BYTES:
            raise HTTPException(
                status_code=413,
                detail=(
                    "An image exceeds the per-image size limit "
                    f"({settings.MAX_IMAGE_BYTES // (1024 * 1024)} MB)"
                ),
            )


def _enroll_hint(err: str | None, embeddings, received: int) -> str:
    good = sum(e is not None for e in embeddings)
    return (
        f"{err} Clear face in {good} of {received} frames. Try better lighting, face the "
        "camera, and make sure only one face is in view."
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


def _to_out(user, manager=None) -> UserOut:
    return UserOut(
        user_id=user.user_id,
        username=user.username,
        display_name=user.display_name,
        baseline=user.baseline,
        settings=user.settings,
        total_sessions=user.total_sessions,
        last_seen=user.last_seen,
        is_guest=user.is_guest,
        face_enrolled=bool(manager is not None and manager.is_enrolled(user.user_id)),
    )
