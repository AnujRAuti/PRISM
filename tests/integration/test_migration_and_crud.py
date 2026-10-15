import subprocess
import sys
from uuid import uuid4
from backend.db.session import get_session
from backend.db import models


def test_alembic_upgrade_head():
    # Run alembic upgrade head (assumes DB is reachable)
    subprocess.check_call([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=".")


def test_basic_crud():
    """The three core entities round-trip through the migrated schema.

    Every identifier is per-run and every row is deleted again. The test used
    to insert a fixed ``testuser`` / ``test@example.com`` pair, which kept
    "succeeding" only because the database does not enforce the uniqueness the
    ORM declares -- and left another duplicate behind on every run.
    """
    suffix = uuid4().hex
    session = get_session()
    user = project = evidence = None
    try:
        user = models.User(username=f"testuser-{suffix}",
                           email=f"test-{suffix}@example.com")
        session.add(user)
        session.commit()

        project = models.Project(name=f"testproj-{suffix}", owner_id=user.id)
        session.add(project)
        session.commit()

        evidence = models.Evidence(project_id=project.id, filename="foo.jpg")
        session.add(evidence)
        session.commit()

        # read back
        got = session.query(models.Evidence).filter_by(id=evidence.id).one()
        assert got.filename == "foo.jpg"
        assert got.project_id == project.id
        assert session.query(models.Project).filter_by(id=project.id).one().owner_id == user.id
        assert session.query(models.User).filter_by(id=user.id).one().email.endswith(
            f"{suffix}@example.com"
        )
    finally:
        if evidence is not None:
            session.query(models.Evidence).filter_by(id=evidence.id).delete()
        if project is not None:
            session.query(models.Project).filter_by(id=project.id).delete()
        if user is not None:
            session.query(models.User).filter_by(id=user.id).delete()
        session.commit()
        session.close()
