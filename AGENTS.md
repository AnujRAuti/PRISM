# Repository guidance

## Local skills

This repository includes 150 reusable skills under `skills/`, grouped by domain. When a task materially matches one of them, read its `SKILL.md` and apply the relevant workflow. The library is reference material; it does not load automatically into every session. Prefer the narrowest relevant skill and follow repository-specific instructions when they differ.

## Project context

PRISM (Proof-of-Action) is an evidence integrity and review platform for public infrastructure and government scheme field submissions. The intended product workflow is to preserve evidence provenance, compute explainable integrity and risk signals, and support human review. Automated risk signals are not final findings.

The current checkout contains a React 19/Vite PWA in `frontend/` and a checked-in OpenAPI document at `openapi.json`. It does not currently contain a `backend/` source directory, Python project metadata, migrations, or deployment manifests. Backend implementation and production operation described in the README and `docs/Production Task Files/` must be treated as documented or historically reported context, not as code or independently verified live state in this checkout.

Frontend entry points are `frontend/src/App.jsx`, `frontend/src/context/`, `frontend/src/lib/api/`, and `frontend/src/pages/`. `frontend/src/data/mockDataset.ts` contains frontend-side domain/demo data. API calls are centralized in `frontend/src/lib/api/client.js`; the base URL comes from `VITE_API_BASE_URL` (default `http://localhost:8000`). `openapi.json` describes 155 API paths under `/api/v1`.

The major UI areas include dashboard, projects, evidence ingestion and inspection, reviewer queues, evidence comparison, geospatial map, evidence graph, search, citizen and field experiences, audit, analytics, and administration. Frontend package scripts are in `frontend/package.json`.

## Domain guardrails

- Preserve the distinction between evidence integrity, authenticity, fraud risk, compliance, and human decisions.
- Missing or uncertain evidence is not automatically negative evidence or proof of fraud.
- Keep automated signals explainable and traceable to their inputs and methods.
- Protect role-scoped data and avoid treating UI controls as authorization boundaries.
