"""Database engine and session, with the armed-context write guard (BE-029).

``get_engine()`` is the only place the application builds an engine, which is
what makes it the enforcement point for ``backend.db.safety``: a test or
verification run that has declared its context cannot silently end up writing
to a different database than the one it was authorised for.

When no context is armed this is the same engine factory it always was —
normal application, worker and Alembic startup see no extra checks and no
behaviour change.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.engine import Engine

from backend.core.config import settings
from backend.db import safety


_engine: Engine | None = None
_SessionLocal = None


def build_guarded_engine(database_url: str) -> Engine:
    """Build an engine for ``database_url`` through the armed-context guard.

    This is the only place an engine is constructed, so no caller can reach a
    database the current run was not authorised to touch — including callers
    that must honour a DSN read at call time rather than the cached engine.

    When no context is armed the guard is inert and this is a plain
    ``create_engine``: normal application, worker and Alembic startup see no
    extra checks and no behaviour change.
    """
    context = safety.current_context()
    # A declared context means writes are only allowed against the database
    # that context named. Confirm it against the server before handing out an
    # engine anyone could commit through.
    if context:
        safety.guard_url(database_url, context)
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        if context:
            safety.confirm_server_database(engine, context)
    except Exception:
        engine.dispose()
        raise
    return engine


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = build_guarded_engine(settings.database_url)
    return _engine


def get_session():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=get_engine())
    return _SessionLocal()


def get_db():
    session = get_session()
    try:
        yield session
    finally:
        session.close()
