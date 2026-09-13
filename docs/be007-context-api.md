# BE-007 Context API

BE-007 adds project, activity, claim, evidence-context, evidence-location, and nearby-evidence contracts under `/api/v1`.

Projects are created with an existing `owner_id`. Activities and claims are project-scoped, and actor/claimant references must point to existing users. Evidence remains uploadable through the existing `POST /api/v1/evidence` contract; context association is performed separately with `PATCH /api/v1/evidence/{evidence_id}/context`.

Evidence locations are stored as PostGIS `POINT` values with SRID 4326. Nearby endpoints use PostgreSQL/PostGIS `ST_DWithin` and `ST_Distance` over geography casts, with radius measured in meters and results ordered by ascending database-computed distance. Claims from another project are rejected with `409 Conflict`.