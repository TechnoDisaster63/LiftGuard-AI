"""
Analytics endpoints for charting.

NOTE on scope: right now these read straight from the in-memory
SessionManager (engine._session_iri_history / _session_spine_history), the
same arrays the original app accumulated during a run. That gives you
live/just-finished session charts today. Cross-session history (e.g. "my
IRI trend over the last 30 days") needs sessions persisted to a database —
that's a natural next stage once you want the Analytics/Reports pages to
show more than the current session, not something this stage fakes.
"""
from fastapi import APIRouter

from .routes_sessions import get_session_manager

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/{session_id}/iri-timeline")
def iri_timeline(session_id: str):
    manager = get_session_manager(session_id)
    return {"values": manager.engine._session_iri_history}


@router.get("/{session_id}/spine-timeline")
def spine_timeline(session_id: str):
    manager = get_session_manager(session_id)
    return {"values": manager.engine._session_spine_history}


@router.get("/{session_id}/summary")
def summary(session_id: str):
    manager = get_session_manager(session_id)
    return manager.get_session_report()


@router.get("/{session_id}/uncertainty")
def uncertainty_summary(session_id: str):
    """JSON version of the original [U] keyboard shortcut
    (show_uncertainty_summary()), which only printed to a console."""
    manager = get_session_manager(session_id)
    return manager.get_uncertainty_summary()
