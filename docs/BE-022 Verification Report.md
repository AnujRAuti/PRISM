# BE-022 — Publication, Transparency & Public Evidence Governance
## Verification Report (§44)

Date: 2026-09-24
Scope: Publication as a first-class governed domain concept, versioned policies,
immutable publication versions, explicit public projections, stable public
identifiers, deterministic eligibility, and governance interactions with
BE-015/016/017/018/019/020/021.

---

## ⚠️ Verification method and its limits — read first

**No test in this report has been executed, and no migration has been run.**

The project virtualenv (`backend/.venv`) *is* populated — 128 site-packages
including FastAPI 0.141.1, SQLAlchemy, Alembic 1.20.0, Pydantic, pytest and
GeoAlchemy2. However it is a **Windows** environment (`Scripts/`, `.pyd`
extensions such as `_cffi_backend.cp314-win_amd64.pyd`) and the tooling used for
this work runs in a **Linux** sandbox. Windows-compiled extensions cannot be
imported there, and no network/PyPI access is available to provision a Linux
equivalent.

Consequently the following are **NOT** established by this report:

- the unit suite does not demonstrably pass — it has been *written* and
  statically validated, not run
- the integration suite has never been executed
- `alembic upgrade head` has not been run
- the application has not been booted
- no test was deleted, skipped, weakened or xfailed

What *was* done is described honestly below under each heading. Every claim is
labelled as either **executed** (real code run and invariants asserted) or
**static** (parsed / cross-referenced, not executed).

**Required before merge on a Windows host with the populated venv:**

```
backend\.venv\Scripts\python.exe -m pytest tests/unit/test_publication.py -v
backend\.venv\Scripts\python.exe -m pytest tests/integration/test_publication.py -v
backend\.venv\Scripts\python.exe -m pytest -q
backend\.venv\Scripts\python.exe -m alembic upgrade head
backend\.venv\Scripts\python.exe -m alembic downgrade -1
backend\.venv\Scripts\python.exe -m alembic upgrade head
```

---

## Implementation

**Files created**

| File | Purpose |
|---|---|
| `backend/schemas/publication.py` | Request models + explicit public projection schemas |
| `backend/repositories/publication.py` | Persistence only; no policy decisions |
| `backend/services/publication.py` | Lifecycle, eligibility, snapshot projection, public reads |
| `backend/observability/publication_metrics.py` | 8 bounded-label Prometheus collectors |
| `backend/api/v1/endpoints/publication.py` | Internal, BE-016-authorized workflow endpoints |
| `backend/api/v1/endpoints/public.py` | Public read-only endpoints (no internal auth, §17) |
| `alembic/versions/n4o5p6q7r022_be022_publication_transparency.py` | 7 tables + indexes |
| `tests/unit/test_publication.py` | 28 tests |
| `tests/integration/test_publication.py` | 27 tests |

**Files modified**

- `backend/db/models.py` — 6 models, 8 vocabularies, 7 permissions, role mapping,
  10 audit events, 6 notification types
- `backend/services/authorization.py` — 7 action→permission entries,
  `publication_target_resource()`, scope resolution
- `backend/api/v1/router.py` — registers both routers

**Files deleted**

- `alembic/versions/n4o5p6q7r022_be022_publication_transparency.md` — this was
  *not* a runnable migration. It was real Alembic code stored with a `.md`
  extension and could never execute, and it contained a check constraint
  referencing a non-existent `publication_versions.unpublished_at` column.
  Replaced by the `.py` file with that constraint removed.

**Migration** — `n4o5p6q7r022`, `down_revision = m3n4o5p6q021`.
Creates `publication_policies`, `publication_policy_versions`,
`public_identifiers`, `publications`, `publication_versions`,
`publication_events`, `public_media_derivatives`. *Executed check:* upgrade and
downgrade create/drop the identical 7-table set, and each has a matching
`__tablename__` model.

**API endpoints**

Internal (`/api/v1/publications`, BE-016 enforced): create, get, list,
submit-review, approve, reject, publish, unpublish, eligibility;
`/policies` create/get/list.

Public (`/api/v1/public`, **no** internal authentication per §17): list/get
project, activities, claims, evidence list, evidence detail, publication by
public id. All listings are mandatory-paginated (`DEFAULT_PAGE_SIZE=50`,
`MAX_PAGE_SIZE=100`, `limit` constrained by `Query(ge=1, le=100)`).

**Permissions** — `publication.create`, `.read`, `.review`, `.approve`,
`.publish`, `.unpublish`, `.policy.manage` (7).

**Publication policies** — created via `create_publication_policy()`, idempotent
on name, each with a first `ACTIVE` `PublicationPolicyVersion` carrying the
allowlist, public fields, prohibited fields, media/derived-intelligence/review
outcome switches, min authorization level, required approvals, separation-of-
duties flag, location precision, redaction level and retention duration.

**Audit events** (10) — `PUBLICATION_CREATED`, `PUBLICATION_REVIEW_STARTED`,
`PUBLICATION_APPROVED`, `PUBLICATION_REJECTED`, `PUBLICATION_PUBLISHED`,
`PUBLICATION_UNPUBLISHED`, `PUBLICATION_POLICY_CREATED`,
`PUBLICATION_ELIGIBILITY_FAILED`, `PUBLIC_PUBLICATION_VERSION_CREATED`,
`PUBLICATION_DISPUTE_INTERACTION` — written through the existing BE-015 ledger,
no second audit system.

**Notification events** (6) — `PUBLICATION_SUBMITTED`, `PUBLICATION_APPROVED`,
`PUBLICATION_REJECTED`, `PUBLICATION_PUBLISHED`, `PUBLICATION_UNPUBLISHED`,
`PUBLICATION_REQUIRES_REVIEW` — reference IDs only, routed through the existing
outbox, no direct delivery.

---

## Tests

| Suite | Count | Status |
|---|---|---|
| Unit (`tests/unit/test_publication.py`) | 28 | **written, not run** |
| Integration (`tests/integration/test_publication.py`) | 27 | **written, not run** |
| Full suite | — | **not run** |
| Failures | unknown | — |
| Skipped | none | no test was skipped, xfailed or deleted |

*Executed checks on the test files:* both parse under `ast`; every one of the 28
+ 27 test functions is top-level with no duplicate names. Every model class,
model column, schema class, service function, metric function, route path,
blocker code, status literal and response field referenced by the integration
tests was cross-referenced against its definition and confirmed to exist.

---

## Database

| Check | Result |
|---|---|
| Alembic head | **`n4o5p6q7r022`** — single head, no branches, 19 revisions, no dangling `down_revision` (*executed* graph analysis) |
| Upgrade | not run |
| Downgrade | not run (code present; table set verified symmetric) |
| Re-upgrade | not run |
| Orphan check | all 19 revisions resolve to the one chain (*executed*) |
| Constraint check | partial unique index on `public_id`; unique target constraint backing request idempotency; **fixed** a constraint that referenced a non-existent column |

Chain: `bb4bf0dd8fb7 → c6e8a9d4b001 → d7f3b2a1c004 → e8a4c6d2b005 → f9b5d7e3c006
→ a1b2c3d4e008 → b2c3d4e5f009 → c3d4e5f6a010 → d4e5f6a7b011 → e5f6a7b8c012
→ f6a7b8c9d013 → g7b8c9d0e014 → h8c9d0e1f015 → i9d0e1f2g016 → j0e1f2g3h017
→ k1f2g3h4i018 → l2g3h4i5j019 → m3n4o5p6q021 → n4o5p6q7r022`

---

## Publication Verification

**Policy versioning** — `PublicationPolicyVersion` rows are immutable and
status-bearing; `get_active_policy_version()` resolves the ACTIVE version.
A publication pins `policy_version_id`, so a later policy change cannot
retroactively alter an already-published version.

**Eligibility** — `check_eligibility()` is deterministic and returns
**structured** blockers (code + detail), never a single opaque `NOT_ALLOWED`.
11 blocker codes. It deliberately does **not** treat low integrity or high
review priority as a blocker — publication governs visibility, not truth
(§11, "publication is not truth"). It uses no ML and no LLM.

*Executed:* the 6 statuses / 11 blockers / 6 target types were extracted from
the real modules and asserted; the target allowlist and the authorization
resource map agree on all 6 types.

**Publication lifecycle** — *executed.* The transition matrix was extracted from
`publication.py` and driven exhaustively: **6 accepted / 36 rejected** across
all state pairs, every outcome matching the declared matrix. Verified:
`DRAFT → PUBLISHED` is impossible; `PUBLISHED` leaves only to `UNPUBLISHED`;
`REJECTED` and `UNPUBLISHED` are sinks with no outgoing edges and are never
re-entered; every `PUBLICATION_STATUS` has a matrix entry. `validate_transition()`
is called on the real transition path, so tests and runtime cannot drift.

**Public visibility** — every public read routes through
`_published_snapshot()` → `get_published_version_for_public_id()`, which joins
Publication and requires `status == "PUBLISHED"`. A `DRAFT`, `PENDING_REVIEW`,
`APPROVED`, `REJECTED` or `UNPUBLISHED` publication is therefore simply not
found. Publication state — not caller identity — is the gate.

**Unpublication** — `unpublish_publication()` sets `UNPUBLISHED` and preserves
history: the `PublicationVersion` rows are retained, so the public record of
what was once published is not erased.

**Versioning** — publishing freezes a new immutable `PublicationVersion` at
`current_version_number + 1`; republishing a material change creates the *next*
version rather than mutating the old one. `get_current_version()` resolves via
`current_version_number`, not "latest row".

**Snapshot immutability** — the snapshot is a frozen JSONB allowlist projection
built at publish time; it does not track later mutations of the source record.
Covered by an integration test (not executed).

**Public identifier stability** — `ensure_public_identifier()` mints once per
target and reuses it for every later version; `PublicIdentifier.public_id` is
unique. IDs are sequential `POA-<PREFIX>-<6 digits>`, **not** derived from the
internal UUID or any secret.

---

## Privacy

All enforced by an allowlist projection plus `_assert_no_prohibited_fields()`,
a recursive defence-in-depth check (walks dicts, nested dicts and lists) that
**raises** rather than letting a leak ship. 20 prohibited field names, verified
*executed* to include `storage_key`, `exif`, `user_id`, `actor_id`,
`reviewer_id`, `priority_score`, `fusion_signals`, `token`, `secret`,
`internal_notes`, `reviewer_notes`, `internal_graph`.

- **Citizen data protection** — no citizen identity in any public projection.
- **GPS protection** — exact coordinates are emitted **only** when policy
  `location_precision == "EXACT"`; otherwise a precision label/coarse area.
- **EXIF protection** — EXIF is never read into a snapshot; covered by test.
- **Storage-key protection** — `storage_key` is prohibited and never projected.
- **Internal-ID protection** — public responses carry only `public_id`; the
  internal UUID is never serialized. Covered by an integration test.
- **Reviewer-data protection** — `reviewer_id`/`actor_id` prohibited; the
  activity projector omits actor identity outright.
- **Fusion-data protection** — `fusion_signals`/`priority_score` prohibited; a
  `FUSION_ASSESSMENT` is labelled `source_category = "AUTOMATED_SIGNAL"` and is
  never presented as a final government determination.

No internal ORM object is ever serialized directly — every public route builds
its response through an explicit projection schema.

---

## Governance

- **BE-021 dispute interaction** — an active dispute (`OPEN`, `UNDER_REVIEW`,
  `ESCALATED`) yields an `ACTIVE_DISPUTE` blocker; approval fails with the
  structured reason rather than silently publishing contested material.
- **BE-021 correction interaction** — an unresolved correction
  (`REQUESTED`, `UNDER_REVIEW`, `APPROVED`) on evidence yields
  `UNRESOLVED_CORRECTION`.
- **BE-017 retention interaction** — a legal hold yields `LEGAL_HOLD`; a
  retention state of `ELIGIBLE_FOR_DELETION` / `DELETION_PENDING` / `DELETED`
  yields `RETENTION_RESTRICTION`. Publication never bypasses BE-017. The
  retention lookup degrades safely if those tables are unavailable.
- **BE-016 authorization** — every internal route uses
  `Depends(require(action, resource_type, id_param))`. A publication's scope is
  resolved *through its target*, so cross-project authorization works
  automatically. Policies resolve to a bare resource, so only `GLOBAL` scope can
  manage them.
- **§14 separation of duties** — *executed.* `ADMINISTRATOR` holds
  `publication.policy.manage` + `publication.read` and **zero** substantive
  powers; `SUPERVISOR` holds approve/publish/unpublish but not
  `policy.manage`; `CITIZEN` holds none. This structurally prevents the
  widen-the-policy-then-self-approve attack: no single role can both change the
  rules and exercise them. Enforced again at runtime in `approve_publication()`.
- **BE-015 audit** — 10 event types, written to the existing ledger.
- **BE-018 notifications** — 6 types, reference IDs only, existing outbox.
- **BE-019 integrations** — none added.
- **BE-020 telemetry** — 8 collectors; `_bounded()` coerces any unexpected
  value to a fallback so high-cardinality data can never become a label. No
  `user_id`, `project_id`, `evidence_id`, `claim_id`, `publication_id` or
  `public_id` is used as a label.

---

## Performance

**Not measured.** No benchmark was run; the sandbox cannot execute the
application. Qualitative notes only: reads are bounded by construction
(mandatory pagination, indexed public-id lookup); eligibility performs a fixed
number of indexed point queries with no N+1 over target collections;
concurrency is handled by `with_for_update()` row locks plus a unique
constraint, so the intended behaviour is that concurrent publish attempts
serialize and the loser raises rather than double-publishing — but this is
**design intent, not a measured result**.

---

## Defects found and fixed during implementation

1. Migration written as a `.md` file — unrunnable; also contained a check
   constraint on a non-existent column.
2. `publication.requester` AttributeError — column is `requested_by`.
3. `publication.policy.read` used but never defined — mapped to the existing
   `publication.read`.
4. Unpublish required `publication.publish` — corrected to
   `publication.unpublish`.
5. Create endpoint passed caller-supplied `public_id`/`version_number`,
   violating the `extra="forbid"` schema — removed; the service mints them.
6. `create_publication_policy` called with kwargs but defined to take a dict.
7. `public.py` used `Principal` without importing it, contained no-op
   `if/pass` auth blocks, and bound a path param named `public_id` to a
   `publication_id` argument — file rewritten to match §17.
8. Garbage constraint expression I wrote in `models.py` — removed.

---

## Conclusion

BE-022 is implemented as a complete vertical slice. The design invariants that
carry the governance weight — the lifecycle matrix, the §14 role separation, the
target allowlist, the prohibited-field set, the blocker vocabulary and the
migration's single-head symmetry — were **verified by executing the real
modules** and asserting against them, not by inspection.

The functional tests exist and are statically cross-referenced against every
symbol they touch, but **they have not been run**, and the migration has not
been applied. Treat this milestone as *implemented and statically verified,
pending execution* until the Windows commands in the first section are run.
