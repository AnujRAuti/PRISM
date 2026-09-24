# BE-021 — Dispute, Correction & Intelligence Invalidation Governance
## Final Verification Report (per spec §42)

**Date:** 2026-09-24
**Milestone:** BE-021 — Dispute, Correction & Intelligence Invalidation Governance
**Branch:** `Backend`

---

## Verification Environment Note (read first)

This report was produced in an agent sandbox that has **no PostgreSQL, Redis,
MinIO, or installable Python dependencies**. Everything that can be verified
without live infrastructure was verified **statically and structurally**, and
every such check is listed below with its result. Checks that require the live
stack (pytest execution, `alembic upgrade/downgrade/upgrade` against live
PostgreSQL, latency measurements) are explicitly marked
**"PENDING LOCAL RUN"** together with the exact command to run on the
development machine. No test result in this report is fabricated.

Static checks performed in this environment (all passed):

| # | Check | Result |
|---|-------|--------|
| 1 | `ast.parse` on all 24 BE-021-touched Python files | PASS |
| 2 | Alembic revision graph walk over all 18 migration files: exactly one head `m3n4o5p6q021`, parent `l2g3h4i5j019`, no children of the new head, unbroken chain to the initial migration | PASS |
| 3 | Migration ↔ ORM consistency: tables, columns, types, CHECK constraints, indexes, partial unique indexes, RESTRICT FKs in `m3n4o5p6q021_be021_governance.py` match `backend/db/models.py` | PASS |
| 4 | Endpoint imports vs. schema/service/authorization module exports | PASS |
| 5 | Endpoint service-call kwargs vs. service function signatures | PASS |
| 6 | All 23 governance routes registered in `backend/api/v1/router.py` under `/api/v1` | PASS |
| 7 | Unit test file: every referenced service attribute/constant exists; every audit/notification type is a registered vocabulary member | PASS |
| 8 | Integration test file: all 29 model imports exist in `models.py`; all model constructor kwargs match model attributes; all service call kwargs match signatures; every URL used matches a registered route (119 routes checked); fixture model constructors match columns | PASS |
| 9 | Anti-shortcut sweep (§40): no truth/fraud/authenticity vocabulary used as resolution values; no ML/LLM decision paths; no Python locks for concurrency; no second audit ledger/graph/notification/worker | PASS |
| 10 | Metric label sweep: no identity labels (`user_id`, `project_id`, `evidence_id`, `claim_id`, `dispute_id`, `correction_id`) as Prometheus labels | PASS |

---

## 1. Implementation

### Files created (17)

| File | Purpose |
|------|---------|
| `alembic/versions/m3n4o5p6q021_be021_governance.py` | Migration: 6 governance tables + staleness columns + indexes/constraints |
| `backend/schemas/dispute.py` | Pydantic v2 dispute schemas incl. controlled lifecycle/resolution enums |
| `backend/schemas/correction.py` | Correction schemas incl. category-validated requests |
| `backend/schemas/governance.py` | Dependency graph, invalidation, reprocessing schemas |
| `backend/repositories/dispute.py` | Dispute + append-only event data access (row-locked transitions) |
| `backend/repositories/correction.py` | Correction request + append-only event data access |
| `backend/repositories/governance.py` | Target resolution, dependency traversal queries, invalidation records |
| `backend/services/dispute.py` | Dispute lifecycle: create (idempotent), review, assign, escalate, resolve (human-governed), reject, withdraw; audit + notification twins |
| `backend/services/correction.py` | Correction workflow: request, review, approve, reject, apply (distinct states), cancel; immutable-evidence protection; version lineage; staleness invalidation |
| `backend/services/governance.py` | Bounded BFS dependency traversal (§16), staleness policy (§14), `invalidate_target` propagation (§13), reprocessing delegation (§17) |
| `backend/api/v1/endpoints/dispute.py` | 10 dispute routes, server-side scope enforcement |
| `backend/api/v1/endpoints/correction.py` | 9 correction routes, server-side scope enforcement |
| `backend/api/v1/endpoints/governance.py` | 4 governance routes (dependencies/invalidate/invalidation get/reprocess) |
| `backend/observability/governance_metrics.py` | BE-020 telemetry: closed-vocabulary counters + operation timer |
| `tests/unit/test_governance.py` | Unit tests (§35) — pure logic, no DB |
| `tests/integration/test_governance.py` | Integration tests (§36) — live stack, 13 end-to-end tests |
| `docs/Production Task Files/BE-021 — Dispute, Correction & Intelligence Invalidation Governance.md` | Spec (tracked for the milestone) |

Plus this report: `BE-021_VERIFICATION_REPORT.md`.

### Files modified (content changes only)

| File | Change |
|------|--------|
| `backend/db/models.py` | +475 lines: 6 new models (`Dispute`, `DisputeEvent`, `CorrectionRequest`, `CorrectionEvent`, `IntelligenceInvalidation`, `ReprocessingRequest`), `staleness` columns + CHECKs + indexes on `AnalysisJob`/`FusionRun`/`ExplanationRun`, 19 new `AUDIT_EVENT_TYPES`, 9 new `NOTIFICATION_TYPES`, 10 new permissions in `AUTH_ROLE_PERMISSIONS` |
| `backend/api/v1/router.py` | +8: register dispute/correction/governance routers |
| `backend/services/authorization.py` | +121: public `governance_target_resource()` mapping; target-scope fallback in `resolve_resource_scope` for project-less governance rows (dispute/correction/reprocessing/invalidation resolve scope through their target) |
| `backend/services/evidence_graph.py` | +3: lineage edge `("EVIDENCE", "DERIVED_FROM", "EVIDENCE")` in the BE-010 compatibility vocabulary (§9) — no second graph |
| `backend/workers/analysis_worker.py` | +18: `_complete_reprocessing_hook` — when a delegated job completes, BE-021 marks the reprocessing request COMPLETED (idempotent, failure-isolated; no duplicated worker logic) |
| `requirements.txt` | +4: `structlog`, `prometheus-client` (BE-020 deps that were missing from the file — regression-fix prerequisite, see below) |
| `backend/app/main.py`, `backend/observability/health.py`, `backend/observability/logging.py`, `backend/observability/redaction.py`, `tests/unit/observability/test_logging.py` | BE-020 regression fixes made before BE-021 work began (app boot, `/api/v1` health route contracts, logging/redaction fixes) — prerequisite for the full regression suite to run; committed ahead of the BE-021 commits with their own message |

Approximately 73 further tracked files show as modified with **line-ending (LF→CRLF) changes only** (`git diff --ignore-all-space` is empty for them). They are left untouched in the working tree — nothing was discarded and no historical migration was modified content-wise.

### Files deleted

None.

### Migration revision

`m3n4o5p6q021` (parent `l2g3h4i5j019`, the BE-020 head). Creates:
`disputes`, `dispute_events`, `correction_requests`, `correction_events`,
`intelligence_invalidations`, `reprocessing_requests`; adds
`staleness` (with CHECK + index) to `analysis_jobs`, `fusion_runs`,
`explanation_runs`. All tables: UUID PKs, timezone-aware timestamps, FKs,
CHECK constraints (11 total), operational indexes, and RESTRICT FKs where
historical rows must be preserved. Idempotency enforced at the DB level by
partial unique indexes: `uq_disputes_active_target_initiator`
(active disputes per target+initiator),
`uq_correction_active_target_category_requester` (active corrections per
target+category+requester), `uq_reprocessing_pending_evidence` (one PENDING
reprocessing per evidence item). Symmetric `downgrade()` implemented.
No historical migration was modified.

### API endpoints (23, all under `/api/v1`)

Disputes — `POST /disputes` (create, idempotent per active target+initiator: 201 created / 200 existing), `GET /disputes/{dispute_id}`, `GET /disputes` (filtered listing, scope-filtered), `GET /disputes/{dispute_id}/history` (append-only), `POST /disputes/{dispute_id}/start-review`, `POST .../assign`, `POST .../escalate`, `POST .../resolve`, `POST .../reject`, `POST .../withdraw`.

Corrections — `POST /corrections` (idempotent per active target+category+requester), `GET /corrections/{correction_id}`, `GET /corrections`, `GET /corrections/{correction_id}/history`, `POST /corrections/{correction_id}/start-review`, `POST .../approve`, `POST .../reject`, `POST .../apply`, `POST .../cancel`.

Governance — `GET /governance/{target_type}/{target_id}/dependencies` (bounded), `POST /governance/{target_type}/{target_id}/invalidate`, `GET /governance/invalidations/{invalidation_id}`, `POST /governance/{target_type}/{target_id}/reprocess` (EVIDENCE targets only).

Creation endpoints resolve the challenged target's scope server-side;
workflow endpoints resolve the governance row's own project, falling back to
the target's scope when the row is project-less (external assertions, fusion
assessments). Out-of-scope resources are indistinguishable from absent (404).

### Permissions (10, BE-016 integration only — no second permission system)

`dispute.create`, `dispute.read`, `dispute.review`, `dispute.resolve`,
`correction.create`, `correction.read`, `correction.approve`,
`correction.apply`, `intelligence.invalidate`, `intelligence.reprocess`.

Role grants in `AUTH_ROLE_PERMISSIONS`: CITIZEN — dispute.create/read,
correction.create/read; FIELD_OFFICER — adds intelligence.reprocess;
REVIEWER — adds dispute.review; SUPERVISOR — full set incl. dispute.resolve,
correction.approve/apply, intelligence.invalidate, intelligence.reprocess;
ADMINISTRATOR — read-only (§12: administrators are never substantive
decision-makers). Substantive role separation (§12) additionally enforced in
services: a requester cannot approve/apply their own correction, and a
dispute initiator cannot resolve their own dispute.

### Audit events (19, emitted through the existing BE-015 ledger — no second store)

`DISPUTE_CREATED`, `DISPUTE_REVIEW_STARTED`, `DISPUTE_ASSIGNED`,
`DISPUTE_ESCALATED`, `DISPUTE_RESOLVED`, `DISPUTE_REJECTED`,
`DISPUTE_WITHDRAWN`, `CORRECTION_REQUESTED`, `CORRECTION_REVIEW_STARTED`,
`CORRECTION_APPROVED`, `CORRECTION_REJECTED`, `CORRECTION_APPLIED`,
`CORRECTION_CANCELLED`, `INTELLIGENCE_INVALIDATED`,
`GRAPH_RELATIONSHIP_INVALIDATED`, `INTELLIGENCE_REPROCESS_REQUESTED`,
`INTELLIGENCE_REPROCESS_COMPLETED`, `INTELLIGENCE_REPROCESS_FAILED`,
`DEPENDENT_INTELLIGENCE_CHANGED`.

Payloads carry reference metadata only (bounded ID lists capped by
`_capped`, counts, statuses) and are subject to existing audit scrubbing.

### Notification events (9, through the existing BE-018 outbox — no new delivery logic)

`DISPUTE_CREATED`, `DISPUTE_ASSIGNED`, `DISPUTE_ESCALATED`,
`DISPUTE_RESOLVED`, `CORRECTION_APPROVED`, `CORRECTION_REJECTED`,
`CORRECTION_APPLIED`, `INTELLIGENCE_INVALIDATED`, `REPROCESSING_COMPLETED`.
Payloads carry IDs only — never evidence content (§24).

---

## 2. Tests

**Unit** — `tests/unit/test_governance.py` (§35): dispute lifecycle matrix
(valid + all invalid pairs, terminal states, ESCALATED-only-to-review),
resolution vocabulary is exactly the specified 4-value set and never
FRAUD/AUTHENTIC/FAKE/TRUE/FALSE/VALID/GENUINE/DEBUNKED, dispute creation
validation (unknown target type, bad UUIDs, blank/oversized reason),
correction lifecycle matrix (approval/application distinct), change
validation for all six categories (location bounds, filename exactness,
metadata non-empty, association keys, EVIDENCE_FILE self-reference),
staleness policy deterministic per cause and within vocabulary, traversal
bounds (constants 10/1000, validation before DB access, capped payloads),
invalidation/reprocessing input validation, target-type → scoped-resource
mapping (fail-closed for unknown), audit/notification vocabulary membership
(19 audit + 9 notification types registered), closed metric vocabularies
with bounded fallback and no identity labels.

**Integration** — `tests/integration/test_governance.py` (§36), 13 tests
against live PostgreSQL + storage, covering every §36 bullet: dispute
lifecycle with append-only history and single-decision preservation;
UPHELD dispute invalidating the full downstream chain (analysis jobs, graph
relationships, fusion runs, explanations, integrity assessments) with the
review case preserved (DEPENDENT_INTELLIGENCE_CHANGED, never auto-resolved)
and reprocessing delegated to a new analysis job exactly once; correction
workflow with original evidence bytes/checksums/filename unchanged,
location update via PostGIS ST_Y/ST_X, staleness STALE propagation,
self-approval 422, event sequence REQUESTED→APPROVED→APPLIED; EVIDENCE_FILE
correction superseding the old version with a DERIVED_FROM lineage edge and
SUPERSEDED old job (no reprocessing); bounded dependency reporting with
truncation flag; reprocessing idempotency (201/200), non-evidence 422,
completion via the worker hook exactly once (single audit + single
notification); concurrent resolution yielding a single outcome (200 + 422,
one DISPUTE_RESOLVED audit, ≤1 invalidation); concurrent correction
application single-invalidation/single-reprocessing; role separation via
authenticated requests (citizen 403s, supervisor resolution, initiator-only
withdrawal, requester self-approval 422 at both permission and §12 layers);
cross-project authorization isolation (404s out-of-scope, list filtering,
admin read-only 403s on resolution/invalidation); retention hold surviving
invalidation; external-assertion dispute recorded locally without mutating
the source payload, and FUSION_ASSESSMENT dispute marking the assessment
INVALIDATED; response-content scan proving no evidence bytes/sha256/storage
keys/reasons leak through governance responses or notification payloads;
telemetry counters recorded via Prometheus registry samples.

**Full suite** — **PENDING LOCAL RUN.** Run with the stack up
(`docker-compose up -d`), then:

```bash
pytest tests/ -q
```

**Failures:** **PENDING LOCAL RUN** — none expected; if any existing test
fails, §37 requires stopping to investigate rather than weakening the test.
**Skipped:** **PENDING LOCAL RUN** — the telemetry test skips itself only if
Prometheus collectors are unavailable (`REGISTRY.get_sample_value` returns
None), by design.

No existing test was deleted, weakened, skipped, or rewritten. The pre-existing
BE-020 regressions that blocked the suite (app boot, `/api/v1` health route
contracts, missing `requirements.txt` entries) were fixed as prerequisite
work before BE-021 started, in the files listed above.

---

## 3. Database

- **Alembic head:** exactly one — `m3n4o5p6q021` (verified statically across
  all 18 revision files; parent `l2g3h4i5j019`; no revision has
  `m3n4o5p6q021` as parent).
- **Upgrade / Downgrade / Re-upgrade:** **PENDING LOCAL RUN** against live
  PostgreSQL:

  ```bash
  alembic heads        # must show exactly m3n4o5p6q021
  alembic upgrade head
  alembic downgrade -1
  alembic upgrade head
  ```

- **Orphan check:** 0 orphaned governance rows by construction — every
  governance table carries FKs (dispute/correction events → their aggregate
  with `ondelete=RESTRICT`; invalidations → optional dispute/correction FKs
  RESTRICT; reprocessing → evidence RESTRICT, invalidation RESTRICT,
  analysis_job RESTRICT). Integration cleanup walks the same FK order.
  Runtime confirmation: **PENDING LOCAL RUN** (the integration suite plus
  the existing `tests/integration/test_migration_and_crud.py`).
- **Constraint check:** 11 CHECK constraints verified in both migration and
  ORM — dispute target-type/status/resolution vocabularies, resolution
  completeness and status-consistency; correction target-type/category/
  status and application-consistency; invalidation target-type/cause;
  reprocessing status; staleness vocabulary on all three derived tables.
  Partial unique indexes enforce idempotency (§28) at the DB level.

---

## 4. Governance Verification

- **Dispute lifecycle:** explicitly validated state machine —
  OPEN→{UNDER_REVIEW, RESOLVED, REJECTED, ESCALATED, WITHDRAWN},
  UNDER_REVIEW→{RESOLVED, REJECTED, ESCALATED, WITHDRAWN},
  ESCALATED→UNDER_REVIEW only; terminals have no exits. Unit-tested matrix +
  DB CHECK constraints + integration history assertions.
- **Correction lifecycle:** REQUESTED→{UNDER_REVIEW, APPROVED, REJECTED,
  CANCELLED}, UNDER_REVIEW→{APPROVED, REJECTED, CANCELLED},
  APPROVED→{APPLIED, CANCELLED}; approval and application are distinct
  states (unit-tested; DB application-consistency CHECK).
- **Evidence immutability:** correction paths never write evidence bytes,
  `sha256`, or `storage_key`; only authorized contextual fields
  (project/claim association, location, metadata, filename) change, and
  EVIDENCE_FILE corrections create a *new* evidence item through the normal
  ingestion pipeline. Integration test asserts checksums + storage keys +
  original filename unchanged.
- **Version lineage:** new→old `DERIVED_FROM` edge via the existing BE-010
  graph service with `provenance.correction_id`; `("EVIDENCE", "DERIVED_FROM",
  "EVIDENCE")` added to the compatibility vocabulary (no second graph).
  Integration test asserts the edge and its provenance.
- **Dependency propagation:** bounded BFS over the evidence graph children
  (EVIDENCE→analysis jobs/fusion runs/graph relationships/review cases;
  ANALYSIS_JOB→results; ANALYSIS_RESULT→relationships;
  FUSION_RUN→explanations/assessments/review cases), visited-set duplicate
  protection, depth ≤ 10, nodes ≤ 1000, truncation reported. Per-cause
  staleness: DISPUTE→INVALIDATED; CORRECTION+EVIDENCE_FILE→SUPERSEDED;
  CORRECTION(context)/DIRECT→STALE; relationships/assessments always
  INVALIDATED. EXTERNAL_ASSERTION is record-only (§22/§25).
- **Fusion invalidation:** fusion runs marked via `staleness`, integrity
  assessments via their existing `assessment_status` lifecycle
  (INVALIDATED); fusion algorithm untouched (§18). Historical runs remain
  queryable.
- **Explanation preservation:** explanation runs marked via `staleness` only —
  content never mutated; historical explanations remain retrievable (§19).
- **Review-case preservation:** review cases are never auto-resolved or
  auto-reopened; open cases record a `DEPENDENT_INTELLIGENCE_CHANGED` audit
  event and stay OPEN; resolved decisions are preserved (§20).
- **Human-decision preservation:** resolutions/rationales live on the row
  once (guarded by lifecycle + CHECK constraints); workflow history is
  append-only events; re-resolution attempts are rejected (422) and retries
  return the existing decision (§21).
- **Reprocessing:** requests delegate to BE-005's `create_analysis_job`
  (new run; no historical run modified); the worker marks the request
  COMPLETED through an idempotent, failure-isolated hook emitting
  `INTELLIGENCE_REPROCESS_COMPLETED` + `REPROCESSING_COMPLETED` exactly once.

---

## 5. Security

- **Authorization:** all 23 routes behind `require(...)` with narrowly scoped
  permissions; scope resolution server-side (never client-supplied); 403
  (no permission), 404 (out of scope / unscopeable), 401 (unauthenticated)
  distinction preserved from BE-016.
- **Cross-project isolation:** project-scoped roles see only their project's
  governance rows; out-of-scope targets 404. Integration-tested across two
  projects for create/read/list/resolve/invalidate/traversal.
- **Retention interaction:** invalidation and disputes never delete evidence
  or bypass retention; a retention hold placed on disputed evidence remains
  authoritative (integration-tested).
- **Sensitive-data exposure:** governance responses and notification/audit
  payloads carry IDs and statuses only — integration test recursively scans
  every response key set for `sha256`/`storage_key`/`content`/`bytes`/file
  data and scans notification payloads against a whitelist. Metric labels
  are closed vocabularies (§33) — verified by source scan.
- **Audit integrity:** all governance actions emit BE-015 ledger events
  through the existing service; payloads scrubbed by the existing redaction
  path; dispute/correction events append-only with RESTRICT FKs.

---

## 6. Performance

- **Dispute creation / Correction creation:** single-transaction inserts with
  operational indexes on (target_type, target_id), status, project, initiator/
  requester, created_at; idempotent dedupe via partial unique index lookup.
  **Latency: PENDING LOCAL RUN.**
- **Dependency traversal:** bounded BFS — MAX_TRAVERSAL_DEPTH=10,
  MAX_TRAVERSAL_NODES=1000 (unit-enforced); boundary truncation reported;
  visited set prevents duplicate processing and cycles. No unbounded
  recursion exists in the implementation.
- **Invalidation propagation:** set-based UPDATEs per dependency kind inside
  one transaction per phase; counts capped for audit payloads. **Latency:
  PENDING LOCAL RUN.**
- **Concurrent mutation:** PostgreSQL row-level locks (`WITH FOR UPDATE`) on
  the governance row serialize competing transitions; losers observe a
  terminal/invalid state and receive 422; partial unique indexes make
  duplicate active disputes/corrections and duplicate pending reprocessing
  impossible at the DB level. No Python locks anywhere (§29).

---

## 7. Git

- **Implementation commit:** `BE-021: implement dispute and correction governance`
- **Completion commit:** `BE-021 Complete` (this report)
- **Pushed to:** `origin/Backend` (plain push; **no** force push, reset,
  rebase, branch deletion, history rewriting, or discarding of unrelated
  changes; unrelated line-ending-only modifications were left untouched in
  the working tree)

---

## 8. Anti-Shortcut Compliance (§40)

No evidence is ever marked fake/authentic, deleted, or overwritten; no
historical analysis, fusion, explanation, or human decision is overwritten;
no LLM/ML anywhere in dispute decisions; no truth/fraud probabilities;
authorization and retention are never bypassed; no second audit ledger,
graph, notification delivery, worker, or external-integration logic; no
Python locks; no unlimited traversal; no sensitive evidence through
governance APIs; no high-cardinality Prometheus labels; no historical
migrations modified; no existing tests weakened; no BE-022+ scope. Resolution
vocabulary is strictly UPHELD / REJECTED / INCONCLUSIVE /
INSUFFICIENT_EVIDENCE.

---

## 9. Local Runbook (completes the PENDING items)

```bash
# with the stack running (docker-compose up -d)
alembic heads                                  # exactly one head: m3n4o5p6q021
alembic upgrade head                           # upgrade
alembic downgrade -1                           # downgrade
alembic upgrade head                           # re-upgrade
pytest tests/unit/test_governance.py -q        # BE-021 unit tests
pytest tests/integration/test_governance.py -q # BE-021 integration tests
pytest tests/ -q                               # full regression suite (§37)
```

Expected: ALL TESTS PASS, 0 REGRESSIONS. If any pre-existing test fails,
§37 requires investigating the conflict rather than changing the test.
