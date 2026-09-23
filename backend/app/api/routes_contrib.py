"""Opt-in training-data contributions: consent, list, label, delete.

The contributor id travels in the X-Contributor-Id header, not the URL,
so it does not land in access logs. It is a random UUID the browser
made; holding it is what lets someone see and delete its sets.
"""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from ..contrib.hub import uploader_from_env
from ..contrib.store import CONSENT_VERSION, ContribError, ContributionStore, valid_anon_id
from ..core.config import settings

router = APIRouter(prefix="/api/contrib", tags=["contributions"])

_store: ContributionStore | None = None


def get_store() -> ContributionStore:
    global _store
    if _store is None:
        _store = ContributionStore(settings.CONTRIB_DIR, uploader=uploader_from_env())
    return _store


def set_store(store: ContributionStore | None) -> None:
    """Tests swap in a temporary store."""
    global _store
    _store = store


def _anon(value: Optional[str]) -> str:
    try:
        return valid_anon_id(value)
    except ContribError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class ConsentRequest(BaseModel):
    adult: bool = False


class LabelRequest(BaseModel):
    feel: Optional[Literal["easy", "ok", "hard", "hurt"]] = None
    counting_right: Optional[bool] = None


@router.get("/consent")
def get_consent(x_contributor_id: Optional[str] = Header(None)):
    record = get_store().consent(_anon(x_contributor_id))
    return {"consented": record is not None, "consent_version": CONSENT_VERSION, "record": record}


@router.post("/consent")
def give_consent(req: ConsentRequest, x_contributor_id: Optional[str] = Header(None)):
    try:
        record = get_store().give_consent(_anon(x_contributor_id), req.adult)
    except ContribError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"consented": True, "record": record}


@router.get("")
def list_sets(x_contributor_id: Optional[str] = Header(None)):
    return {"sets": get_store().list(_anon(x_contributor_id))}


@router.patch("/{set_id}/label")
def label_set(set_id: str, req: LabelRequest, x_contributor_id: Optional[str] = Header(None)):
    try:
        return get_store().label(_anon(x_contributor_id), set_id, req.feel, req.counting_right)
    except ContribError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Set not found") from exc


@router.delete("/{set_id}")
async def delete_set(set_id: str, x_contributor_id: Optional[str] = Header(None)):
    anon = _anon(x_contributor_id)
    try:
        deleted = await run_in_threadpool(get_store().delete, anon, set_id)
    except ContribError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Set not found")
    return {"deleted": set_id}


@router.delete("")
async def withdraw(x_contributor_id: Optional[str] = Header(None)):
    """Stop contributing: delete every set and the consent record."""
    removed = await run_in_threadpool(get_store().withdraw, _anon(x_contributor_id))
    return {"deleted_sets": removed, "consented": False}
