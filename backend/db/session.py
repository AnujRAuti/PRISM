"""Database session and engine using SQLAlchemy (SQLite for local development)."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.engine import Engine
from backend.core.config import settings


_engine: Engine | None = None
_SessionLocal = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        # For PostgreSQL, no SQLite-specific connect_args are needed.
        _engine = create_engine(settings.database_url, pool_pre_ping=True)
    return _engine


def get_session():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=get_engine())
    return _SessionLocal()

