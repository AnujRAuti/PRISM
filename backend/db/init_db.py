"""Create database tables for local development."""
from backend.db.session import get_engine
from backend.db.models import Base


def init_db():
    engine = get_engine()
    Base.metadata.create_all(engine)


if __name__ == "__main__":
    init_db()
    print("Database initialized")
