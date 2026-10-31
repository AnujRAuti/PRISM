You are implementing **BE-001** for the Proof-of-Action backend.

Repository:
`AnujRAuti/Proof-Of-Action-Final`

Branch:
`Backend`

## Objective

Create the real PostgreSQL/PostGIS/pgvector database foundation for PoA.

The current repository contains a FastAPI scaffold, SQLAlchemy/Alembic scaffolding, and placeholder analysis engines. Do NOT jump ahead into analysis features.

## Required work

1. Replace the SQLite development default with PostgreSQL.
2. Configure development infrastructure for:
   - PostgreSQL
   - PostGIS
   - pgvector
3. Clean and correct `.env.example`.
4. Implement proper SQLAlchemy models for:
   - User
   - Project
   - Activity
   - Claim
   - Evidence
   - EvidenceMetadata
   - AnalysisJob
   - AnalysisResult
   - Anomaly
   - DuplicateMatch
   - ReviewDecision
   - AuditEvent
5. Implement correct:
   - primary keys
   - foreign keys
   - nullability
   - uniqueness
   - timestamps
   - indexes
   - useful relationships
6. Add location fields using PostGIS-compatible types.
7. Add an embedding vector field appropriate for future pgvector use.
8. Configure Alembic to detect the real metadata.
9. Replace the empty initial migration with a real migration.
10. Ensure `alembic upgrade head` creates the complete schema successfully.
11. Update the readiness endpoint so it verifies an actual database connection.
12. Add integration tests covering migration + basic CRUD.
13. Ensure the application can start cleanly with Docker Compose.
14. Run the complete test suite and fix all failures.

## Important architectural constraints

- PostgreSQL is the database.
- Do NOT use SQLite anywhere in the active backend configuration.
- Do NOT implement fake analysis.
- Do NOT create placeholder analysis results.
- Do NOT implement embeddings generation yet.
- Do NOT implement object storage yet.
- Do NOT implement evidence uploads yet.
- Do NOT implement authentication yet.
- Do NOT implement vision yet.
- Do NOT implement fusion yet.
- Do NOT implement frontend work.
- Do NOT refactor unrelated modules.
- Preserve the existing API version structure.
- Keep database models, configuration, and infrastructure production-oriented.

## Definition of done

The task is complete only when all of the following are true:

- Docker starts PostgreSQL successfully.
- PostGIS is available.
- pgvector is available.
- FastAPI connects to PostgreSQL.
- Alembic migration runs successfully.
- All required tables exist.
- Foreign keys and indexes exist.
- The readiness endpoint confirms the DB is reachable.
- Integration tests pass.
- No migration contains `pass`.
- No SQLite configuration remains active.
- No unrelated functionality is added.

At the end, provide:
1. files changed
2. database schema summary
3. commands to run locally
4. tests executed
5. any remaining known issues

Do not stop at explaining the changes. Implement them.