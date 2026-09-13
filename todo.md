BE-001 Progress Report

Files changed:
- backend/core/config.py
- backend/db/session.py
- backend/db/models.py
- backend/api/v1/endpoints/health.py
- alembic/versions/bb4bf0dd8fb7_initial_migration.py
- docker-compose.yml
- docker/pg-init/init.sql
- requirements.txt
- tests/integration/test_migration_and_crud.py

Next steps performed:
- Replaced SQLite default with PostgreSQL URL.
- Added PostGIS + pgvector init SQL and Docker Compose.
- Implemented production-oriented models with UUID PKs, JSONB, PostGIS geometry, and embedding placeholder.
- Replaced empty Alembic migration with a full schema and extension creation.
- Updated readiness endpoint to run a simple query.
- Added integration tests that run migrations and basic CRUD.

Remaining tasks / known issues:
- Ensure Docker is started (`docker compose up -d`) so Postgres is available for tests.
- `geoalchemy2` and `pgvector` must be installed in the virtualenv: `pip install -r requirements.txt`.
- Running tests will fail until the Postgres container is up and reachable at the connection URL in `.env` or `backend/core/config.py`.
- The `embedding` column is an ARRAY(Float) placeholder pending pgvector SQLAlchemy adapter.
