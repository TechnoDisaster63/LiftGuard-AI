from fastapi import APIRouter, HTTPException

from ..core.settings_store import session_defaults
from ..schemas.settings import SessionDefaults, SessionDefaultsPatch
from ..video_analysis.movements import is_selectable, modes_for_api

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", response_model=SessionDefaults)
def get_settings():
    return session_defaults.get()


@router.patch("", response_model=SessionDefaults)
def update_settings(patch: SessionDefaultsPatch):
    fields = patch.model_dump(exclude_unset=True)
    mode = fields.get("movement_mode")
    if mode is not None and not is_selectable(mode):
        raise HTTPException(status_code=422, detail=f"Movement mode {mode!r} can't be picked yet.")
    return session_defaults.update(fields)


@router.get("/movement-modes")
def movement_modes():
    """Every movement mode with whether it can be picked today."""
    return {"modes": modes_for_api()}
