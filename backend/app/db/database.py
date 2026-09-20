"""
SQLAlchemy engine + session factory for persisted session history.

Deliberately points at the SAME SQLite file user_manager_lite.py uses
(settings.USER_DB_PATH) so session records can be joined to users by
user_id without a second connection/file to keep in sync. user_manager_lite.py
still owns its own tables via raw sqlite3 — this just adds a `sessions`
table alongside them through SQLAlchemy's Core/ORM instead of hand-written
SQL, since the query shapes here (filter/paginate by user, order by date)
are exactly what an ORM is for.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from ..core.config import settings

engine = create_engine(
    f"sqlite:///{settings.USER_DB_PATH}",
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency: yields a DB session, closes it after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create tables that don't exist yet. Safe to call on every startup —
    does not touch user_manager_lite.py's own tables."""
    from . import models  # noqa: F401  (ensures models are registered on Base)
    Base.metadata.create_all(bind=engine)
