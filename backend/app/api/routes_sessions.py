from __future__ import annotations
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session as DBSession
from starlette.concurrency import run_in_threadpool

from ..core.session_manager import SessionManager
from ..core.settings_store import session_defaults
from ..db.database import get_db
from ..db.models import SessionRecord
from ..schemas.session import SessionStartRequest, SessionStartResponse, SessionReport

router = APIRouter(prefix="/api/sessions", tags=["sessions"])

# In-memory registry of ACTIVE sessions only. One process = one or a few
# camera rigs in practice, so this is intentionally simple (swap for Redis
# if you need multi-worker deployment). Completed sessions are persisted to
# the `sessions` table (see app/db/models.py) and no longer need to live here.
_sessions: dict[str, SessionManager] = {}


@router.post("/start", response_model=SessionStartResponse)
async def start_session(req: SessionStartRequest, db: DBSession = Depends(get_db)):
    # Anything the caller didn't specify falls back to the current
    # /api/settings values, not a hardcoded default.
    defaults = session_defaults.get()
    provided = req.model_dump(exclude_unset=True)
    merged = {**defaults, **{k: v for k, v in provided.items() if v is not None}}

    manager = SessionManager(
        voice_enabled=merged["voice_enabled"],
        arduino_enabled=merged["arduino_enabled"],
        model_complexity=merged["model_complexity"],
        process_every_n=merged["process_every_n"],
        use_temporal=merged["use_temporal"],
    )
    try:
        # manager.start() blocks on face-ID (up to 25s) — run it in a
        # threadpool so it doesn't stall the event loop for every other
        # client (other sessions' WebSocket frames, health checks, etc.)
        # while one person is enrolling.
        await run_in_threadpool(manager.start, camera_id=merged["camera_id"])
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    session_id = str(uuid.uuid4())
    _sessions[session_id] = manager

    user = getattr(manager.engine, "current_user", None)
    db.add(SessionRecord(
        session_id=session_id,
        user_id=getattr(user, "user_id", None) if user else None,
        display_name=getattr(user, "display_name", "Guest") if user else "Guest",
        is_guest=getattr(user, "is_guest", True) if user else True,
        camera_id=merged["camera_id"],
        using_temporal=merged["use_temporal"],
        started_at=datetime.now(timezone.utc),
    ))
    db.commit()

    return SessionStartResponse(session_id=session_id)


@router.post("/{session_id}/stop")
async def stop_session(session_id: str, db: DBSession = Depends(get_db)):
    manager = _sessions.get(session_id)
    if manager is None:
        raise HTTPException(status_code=404, detail="Session not found")

    report = manager.get_session_report()
    # stop() blocks briefly on cap.release() and Arduino serial I/O — worth
    # keeping off the event loop for the same reason as start().
    await run_in_threadpool(manager.stop)
    del _sessions[session_id]

    record = db.query(SessionRecord).filter_by(session_id=session_id).first()
    if record is not None:
        record.ended_at = datetime.now(timezone.utc)
        record.peak_risk = report.get("peak_risk", 0)
        record.iri_history = report.get("iri_history", [])
        record.spine_history = report.get("spine_history", [])
        record.exercise_summary = report.get("exercise", {})
        record.fatigue_summary = report.get("fatigue", {})
        record.iri_summary = report.get("iri")
        record.uncertainty_summary = report.get("uncertainty")
        record.using_iri_v2 = report.get("using_iri_v2", False)
        if report.get("user"):
            record.display_name = report["user"].get("display_name", record.display_name)
            record.is_guest = report["user"].get("is_guest", record.is_guest)
        db.commit()

    return {"status": "stopped"}


@router.get("/{session_id}/report", response_model=SessionReport)
def get_report(session_id: str):
    """Live report for an ACTIVE session. For a finished session, use
    /api/sessions/history/{session_id} instead."""
    manager = _sessions.get(session_id)
    if manager is None:
        raise HTTPException(status_code=404, detail="Session not found or already stopped")
    return manager.get_session_report()


@router.get("")
def list_sessions():
    return {"active_sessions": list(_sessions.keys())}


@router.get("/history")
def list_history(limit: int = 20, user_id: int | None = None, db: DBSession = Depends(get_db)):
    """Completed sessions, most recent first. Powers the Sessions/Analytics
    'past sessions' views on the frontend."""
    query = db.query(SessionRecord).filter(SessionRecord.ended_at.isnot(None))
    if user_id is not None:
        query = query.filter(SessionRecord.user_id == user_id)
    records = query.order_by(SessionRecord.ended_at.desc()).limit(limit).all()
    return {
        "sessions": [
            {
                "session_id": r.session_id,
                "display_name": r.display_name,
                "is_guest": r.is_guest,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "ended_at": r.ended_at.isoformat() if r.ended_at else None,
                "peak_risk": r.peak_risk,
            }
            for r in records
        ]
    }


@router.get("/history/{session_id}", response_model=SessionReport)
def get_history_report(session_id: str, db: DBSession = Depends(get_db)):
    record = db.query(SessionRecord).filter_by(session_id=session_id).first()
    if record is None or record.ended_at is None:
        raise HTTPException(status_code=404, detail="No completed session with that id")
    return record.to_report_dict()


def get_session_manager(session_id: str) -> SessionManager:
    """Used by ws_live.py to fetch the manager for a given session id."""
    manager = _sessions.get(session_id)
    if manager is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return manager
