"""
Persisted session history.

user_manager_lite.py still owns its own SQLite connection/tables (raw
sqlite3, schema in DB_SCHEMA at the top of that file) — untouched, per
"preserve every feature." This adds ONE new table, `sessions`, via
SQLAlchemy, in the same .db file, so session records can be joined to
users by user_id.

This is what makes /api/sessions/history and the Analytics/Reports pages'
"past sessions" view real instead of memory-only.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import String, Integer, Boolean, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class SessionRecord(Base):
    # NOTE: named web_sessions, not "sessions" — user_manager_lite.py's raw
    # sqlite3 DB_SCHEMA already creates its OWN "sessions" table (different
    # columns: session_id INTEGER PK, total_reps, mean_iri, exercise_type...)
    # in this same .db file. Reusing that name would have silently collided
    # via "CREATE TABLE IF NOT EXISTS" — whichever ran first would win and
    # the other write path would throw column-mismatch errors at runtime.
    __tablename__ = "web_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String, unique=True, index=True)

    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    display_name: Mapped[str] = mapped_column(String, default="Guest")
    is_guest: Mapped[bool] = mapped_column(Boolean, default=True)

    camera_id: Mapped[int] = mapped_column(Integer, default=0)
    using_temporal: Mapped[bool] = mapped_column(Boolean, default=False)
    using_iri_v2: Mapped[bool] = mapped_column(Boolean, default=False)

    started_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    peak_risk: Mapped[int] = mapped_column(Integer, default=0)

    # JSON blobs — same shape as SessionManager.get_session_report()'s fields
    iri_history: Mapped[list] = mapped_column(JSON, default=list)
    spine_history: Mapped[list] = mapped_column(JSON, default=list)
    exercise_summary: Mapped[dict] = mapped_column(JSON, default=dict)
    fatigue_summary: Mapped[dict] = mapped_column(JSON, default=dict)
    iri_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    uncertainty_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    def to_report_dict(self) -> dict:
        """Same shape as SessionManager.get_session_report(), so the
        frontend's SessionReport type works for both live and historical."""
        return {
            "user": {
                "display_name": self.display_name,
                "user_id": self.user_id,
                "is_guest": self.is_guest,
            },
            "exercise": self.exercise_summary,
            "fatigue": self.fatigue_summary,
            "peak_risk": self.peak_risk,
            "iri_history": self.iri_history,
            "spine_history": self.spine_history,
            "using_temporal": self.using_temporal,
            "using_iri_v2": self.using_iri_v2,
            "camera_id": self.camera_id,
            "iri": self.iri_summary,
            "uncertainty": self.uncertainty_summary,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
        }
