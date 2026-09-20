from fastapi import APIRouter

from ..core.settings_store import session_defaults
from ..schemas.settings import SessionDefaults, SessionDefaultsPatch

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", response_model=SessionDefaults)
def get_settings():
    return session_defaults.get()


@router.patch("", response_model=SessionDefaults)
def update_settings(patch: SessionDefaultsPatch):
    return session_defaults.update(patch.model_dump(exclude_unset=True))
