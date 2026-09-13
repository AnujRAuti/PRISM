import subprocess
import sys
import time
from sqlalchemy.orm import Session
from backend.core.config import settings
from backend.db.session import get_engine, get_session
from backend.db import models


def test_alembic_upgrade_head():
    # Run alembic upgrade head (assumes DB is reachable)
    subprocess.check_call([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=".")


def test_basic_crud():
    engine = get_engine()
    session = get_session()

    # create a user and project
    u = models.User(username="testuser", email="test@example.com")
    session.add(u)
    session.commit()

    p = models.Project(name="testproj", owner_id=u.id)
    session.add(p)
    session.commit()

    e = models.Evidence(project_id=p.id, filename="foo.jpg")
    session.add(e)
    session.commit()

    # read back
    got = session.query(models.Evidence).filter_by(id=e.id).one()
    assert got.filename == "foo.jpg"
