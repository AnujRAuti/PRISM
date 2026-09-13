"""Database session and engine using SQLAlchemy (SQLite for local development)."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.core.config import settings


_engine = None
_SessionLocal = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})
    return _engine


def get_session():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=get_engine())
    return _SessionLocal()

