BE-001 — PostgreSQL + PostGIS + pgvector foundation

Requirements:
- Docker & Docker Compose
- Python 3.11+ (venv)

Quick setup (development):

1. Copy example env:
   cp .env.example .env
2. Start Postgres with PostGIS and pgvector:
   docker compose up -d
3. Install Python deps:
   pip install -r requirements.txt
4. Run Alembic migrations:
   cd backend
   ./.venv/Scripts/python -m alembic upgrade head
5. Run tests:
   pytest tests/integration -q

Notes:
- `.env.example` contains the development DB URL matching Docker Compose (user: `postgres`, db: `pofa_dev`).
- Local SQLite files must not be used; ensure `DATABASE_URL` points to PostgreSQL.
- The `embedding` column uses an `ARRAY(Float)` placeholder for now; migrating to `pgvector` type is a follow-up task in BE-002 when vector operations are required.
