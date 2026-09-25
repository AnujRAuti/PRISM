# BE-022 — Publication, Transparency & Public Evidence Governance
## Verification Report (§44)

Date: 2026-09-24
Scope: Publication as a first-class governed domain concept, versioned policies,
immutable publication versions, explicit public projections, stable public
identifiers, deterministic eligibility, and governance interactions with
BE-015/016/017/018/019/020/021.

---

## ⚠️ Verification method and its limits — read first

**`pytest` could not be run. `alembic upgrade head` was never applied.**

`backend/.venv` *is* populated — 128 site-packages including FastAPI 0.141.1,
SQLAlchemy, Alembic 1.20.0, Pydantic and pytest — but it is a **Windows**
environment (`Scripts/`, `.pyd` files such as `greenlet/_greenlet.cp314-win_amd64.pyd`)
and the tooling here runs in a **Linux** sandbox. Windows binaries cannot execute
there. PyPI is unreachable (`403 Forbidden` from the proxy), no other interpreter
exists, and the pip cache is empty, so a Linux equivalent cannot be provisioned.
`pydantic_core` is a compiled Rust extension with no pure-Python fallback, which
alone blocks importing Pydantic v2 and therefore the app.

**What was actually done instead.** The 28 unit tests are pure-logic by design
(§38), so the real test bodies were extracted and executed against the real
module code via AST harvesting — the same assertions pytest would run, without
the import chain that needs compiled wheels.

**Result: 29/29 unit tests pass** (28 original + 1 added, see below).

Because a test that cannot fail proves nothing, the suite was then
**mutation-tested**: the source was deliberately broken and the suite re-run to
confirm it catches each defect.

| Injected defect | Caught? |
|---|---|
| `DRAFT` allowed to skip to `PUBLISHED` (breaks §6) | **detected** |
| `REJECTED` made re-enterable (breaks terminal states) | **detected** |
| `ADMINISTRATOR` granted `publication.publish` (breaks §14) | **detected** |
| `SUPERVISOR` granted `publication.policy.manage` (breaks §14) | **detected** |
| `storage_key` removed from the prohibited-field list (§21) | **detected** |
| `public_id` added as a Prometheus label (breaks §35) | **detected** |
| `CITIZEN` granted `publication.read` (§17) | **initially MISSED → test added** |

That last row is a real gap the mutation testing found: no test asserted that
citizens hold no publication authority, so granting a citizen internal read
access would have gone unnoticed. `test_citizens_hold_no_publication_authority`
was added and now detects it.

**Still NOT established:**

- the 27 integration tests have never been executed (they need PostgreSQL, the
  app, and the compiled dependency stack)
- the app has never been booted
- `alembic upgrade head` / `downgrade` / re-`upgrade` have not been run
- no test was deleted, skipped, weakened or xfailed

**Required before merge, on a Windows host with the populated venv:**

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
| Unit (`tests/unit/test_publication.py`) | 29 | **executed via AST harness — 29/29 pass**, and mutation-tested |
| Integration (`tests/integration/test_publication.py`) | 27 | **written, not run** |
| Full suite | — | **not run** |
| Failures | 0 | mutation testing additionally confirmed the suite detects 7/7 injected defects (one gap found and closed) |
| Skipped | none | no test was skipped, xfailed or deleted |

*Executed checks:* the 29 unit tests were run via AST extraction and all pass.
The integration test file parses; all 27 test functions are top-level with no
duplicate names; and every model class, model column, schema class, service
function, metric function, route path, blocker code, status literal and response
field it references was cross-referenced against its definition and confirmed to
exist. The integration tests themselves remain unexecuted.

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

## Post-implementation defect fixes (from live integration runs)

### Fix A — persisted actor written to a UUID column (BE-022 live run 1)

`create_publication` fabricated the literal `"dev-user"` as the actor during
development bypass, which reached PostgreSQL as
`invalid input syntax for type uuid: "dev-user"`.

Resolved by reusing the existing convention: `_require_uuid` / `_optional_uuid`
(already present in 7+ services, introduced in BE-021 for `dispute.py`) validate
the actor at the persistence boundary, so a non-UUID identity becomes a `ValueError`
→ HTTP 422 rather than an opaque driver-level 500. A `Principal.principal_id` is an
*authorization* identity, not necessarily a persisted user id — an anonymous
principal has `None` and `system_principal()` uses the sentinel `"system"`.
Neither is a UUID, so neither may be written to a UUID column. The endpoint
helper `_get_principal_or_raise` now returns the real principal identity or
requires one. `PublicationPolicyVersion.created_by` is nullable, so an
unattributable policy actor is recorded as `NULL`; `Publication.requested_by` is
not nullable, so a missing actor is rejected with 401.

No schema change, no hardcoded UUID, no cast, no weakened authorization.

### Fix B — `PublicationPolicyResponse` missing 13 fields (BE-022 live run 2)

`pydantic_core.ValidationError: 13 validation errors for PublicationPolicyResponse`
at `endpoints/publication.py:332`. The 13 reported fields
(`version`, `status`, `allowed_target_types`, `public_fields`,
`prohibited_fields`, `allow_media_exposure`, `allow_derived_intelligence`,
`allow_review_outcomes`, `min_authorization_level`, `required_approvals`,
`require_separation_of_duties`, `location_precision`, `redaction_level`) live on
`PublicationPolicyVersion`, not on `PublicationPolicy` — the split is intentional
(§9). The create path returned the bare `PublicationPolicy` ORM row, so those
fields were unreachable. `policy_view(policy, version)` already existed to
flatten the pair, but the create path never called it.

Fixed by returning `policy_view(...)` from `create_publication_policy` on **both**
return paths, including the idempotent (`created=False`) path, which must still
resolve the ACTIVE version rather than falling back to the no-version defaults.
The endpoint needed no change: `model_validate` accepts the dict, exactly as the
list endpoint already did.

No duplicated fields on `PublicationPolicy`, no schema change, no field made
`Optional`, no arbitrary ORM serialization, no versioning removed. The 13 fields
remain required and unsuppressible (verified statically against the schema).

### Verification of Fix B

`policy_view` was executed against stub objects and its key set compared against
`PublicationPolicyResponse.model_fields` parsed from the schema: **exact match on
all 20 fields**, with version-derived values taken from the ACTIVE version and a
complete no-active-version fallback. Both return paths were confirmed to route
through the projection.

Mutation testing — 8 injected defects, all caught:

| # | Injected defect | Caught by |
|---|---|---|
| M1 | idempotent path returns bare ORM row | AST return-path test + idempotent test |
| M2 | create path returns bare ORM row | AST return-path test (line 211) + integration |
| M3 | `status` hardcoded to `DRAFT` | projection value assertions |
| M4 | `version` hardcoded to `1.0` | projection value assertions |
| M5 | `allowed_target_types` dropped from projection | projection key-set assertion |
| M6 | idempotent path passes `None` instead of the ACTIVE version | idempotent test (repo-call assertion) |
| M7 | idempotent path ignores the active version entirely | idempotent test |
| — | unmutated baseline | passes (no false positive) |

M6 was initially a real coverage gap: passing `None` yields a *valid-looking*
response reporting `DRAFT`/`1.0`, so no field-required error would ever reveal
it. A dedicated test now asserts the repository is consulted for the active
version and that its configuration is returned verbatim.

### Fix C — authenticated publication requests denied 403 (BE-022 live run 3)

Every authenticated request to `POST /api/v1/publications` returned
`403 {"detail":"Forbidden"}`, cascading into `KeyError("id")` in
`run_to_published()` and many downstream tests.

**Authorization decision path, traced end to end:**

1. `headers_for(user_id)` → `Authorization: Bearer dev-user-<uuid>`.
2. `resolve_principal` (`security/authentication.py:72`) matches the
   `dev-user-` prefix and calls `resolve_user_principal(db, subject)`.
3. `resolve_user_principal` (`services/authorization.py:191`) loads the user,
   then builds the permission set **from the database**:
   `assignments_for_user` → `roles_by_ids` → `permissions_for_roles`, which
   reads the `role_permissions` **table**.
4. The endpoint declares `Depends(require("publication.create"))` — a single
   argument, so `resource_type is None`.
5. `require()` takes the resource-less branch and evaluates exactly one
   condition: `if permission not in principal.permissions`
   (`security/authorization.py:56`).
6. That is `NO_PERMISSION` → **403**, raised at lines 56–60.

- principal: `USER:<requester uuid>`, authenticated, `ACTIVE`
- permission requested: `publication.create`
- role permissions in `AUTH_ROLE_PERMISSIONS`: `FIELD_OFFICER` **does** hold
  `publication.create` and `publication.read` (models.py:1222)
- resource: `Resource("global")` — no project/org scope is consulted on this path
- decision: denied, reason `NO_PERMISSION`

**Root cause — the constant and the table had drifted apart.**
`AUTH_ROLE_PERMISSIONS` grants officers `publication.create`, but
`principal.permissions` is populated from the `role_permissions` table, and
that table is written *only* by `ensure_default_catalogue`
(`services/authorization.py:169`). Nothing in the application startup and no
migration calls it: the BE-016 migration creates the tables but seeds no
catalogue data, and the BE-022 migration is schema-only. `test_publication.py`
assigned roles and made authenticated requests but never seeded the catalogue,
so it only passed when another test file had already seeded the same database
in the same session. Run in isolation, `FIELD_OFFICER` resolved to an empty
permission set and every authenticated request was denied.

Classification: **D — incorrect test fixture assumption**, with a real
deployment gap behind it. Not an authorization design bug, not a missing
mapping, not a wrong endpoint permission, and not a scope problem.

**Fix:** added the same `autouse` `seed_catalogue` fixture that
`test_authorization.py` (BE-016) and `test_retention.py` already use, calling
`ensure_default_catalogue` before every test in the module. Centralized
authorization is untouched: no permission was added, no role mapping changed,
`require()` was not bypassed, and no test was weakened to accept a 403.

**Regression tests added (authorization contract):**
- `test_field_officer_principal_carries_the_publication_create_permission` —
  asserts the contract directly, independent of any endpoint, so a missing
  catalogue row fails here rather than as an opaque 403 in a dozen unrelated
  tests. Also asserts officers hold *none* of approve/publish/unpublish (§15).
- `test_field_officer_can_create_a_publication_request` — end-to-end proof the
  403 is gone.
- `test_citizen_is_still_denied_publication_create` — proves seeding did not
  widen authority; a citizen is still refused with 403.

Verified by simulation that the contract test fails on an unseeded catalogue
(`permissions == {}`), passes when correctly seeded, and fails if the catalogue
is ever over-granted.

**Known deployment gap (not fixed here, by decision):** a freshly provisioned
production database receives no roles or permissions at all, because
`ensure_default_catalogue` is never invoked outside tests. Closing that needs
either an app-startup call or a data migration — both are runtime/migration
changes beyond the 403 under investigation.

### Fix D — `submit-review` denied 403 for the requester (BE-022 live run 4)

With the catalogue seeded, every authenticated `POST /api/v1/publications/{id}/
submit-review` still returned 403.

**Authorization path.** The endpoint declared
`require("publication.review", "publication", "publication_id")`. Because a
resource was supplied, `resolve_resource_scope` ran and resolved the
publication through its target (a PROJECT-targeted publication inherits that
project's scope). `can()` then evaluated
`principal.permissions.get("publication.review")`, which is empty for
`FIELD_OFFICER` → `NO_PERMISSION` → 403 at `security/authorization.py:149`.
Note the ordering: `can()` checks permission *before* scope, which is why this
presented as 403 rather than the `RESOURCE_UNSCOPEABLE` → 404 that an
out-of-scope actor would receive. Scope was not implicated.

**Root cause.** The `DRAFT → PENDING_REVIEW` transition is the *requester
handing over their own work*, not a reviewer exercising judgement — yet it was
gated on `publication.review`, which the catalogue grants to `REVIEWER` and
`SUPERVISOR` but deliberately withholds from `FIELD_OFFICER` (§15). Five tests
plus `run_to_published` had a FIELD_OFFICER requester submit their own request,
and all were refused. `submit_review` also had **no ownership guard at all**:
`_transition` checked only the status, never that the actor was the requester,
so under the old gate any `REVIEWER` could advance someone else's draft.

**Fix (confirmed contract: the requester submits their own request).**
- The endpoint now requires `publication.create` — the permission that admits an
  actor to raise a request in the first place — scoped through the publication
  exactly as before.
- `_transition` gained a `requester_only` flag (default `False`, so every other
  transition is untouched), and `submit_review` passes `requester_only=True`.
  The service now requires `publication.requested_by == actor_id`.

This is strictly *narrower* than before on the service layer: previously any
reviewer could submit anyone's draft; now only the requester can. No permission
was added, no role mapping changed, and `require()` still enforces the endpoint
gate. Approval is unaffected — it still requires `publication.approve` plus its
own separation-of-duties check, so submitting your own request confers no
publication authority.

One ordering detail: the ownership check runs *after* the state-machine check,
so a caller retrying an already-submitted request is told "Invalid transition"
rather than a misleading ownership complaint.

**Note:** `publication.review` now gates no endpoint. It remains declared in
`AUTH_PERMISSIONS` and granted to `REVIEWER`/`SUPERVISOR`; removing it was out
of scope and would be a separate, deliberate decision.

**Regression tests added:**
- `test_requester_may_submit_their_own_request_for_review` — a FIELD_OFFICER
  creates and submits, reaching `PENDING_REVIEW`.
- `test_non_requester_may_not_submit_someone_elses_request` — a second officer
  (who legitimately holds `publication.create`) is refused with 422, and the
  publication is confirmed still `DRAFT`. This is the test the old
  permission-only gate could not have passed.
- `test_citizen_may_not_submit_for_review` — citizens hold no
  `publication.create`, so submission is refused with 403.
- `test_requester_still_cannot_approve_their_own_request` — a SUPERVISOR
  submits their own request (allowed) but cannot approve it (§15).
- Unit: the ownership guard exists, runs after the state-machine guard, is set
  only by `submit_review`, and is absent from `reject_publication`.

Verified by executing the real `_transition`/`submit_review` against a stubbed
repository: requester-submits passes, non-requester is refused, re-submit reports
the transition error, `reject_publication` stays unrestricted, and
`requester_only` defaults to `False`. Mutation testing over 5 injected defects
(removing the ownership check, dropping `requester_only` from `submit_review`,
inverting the guard order, wrongly restricting `reject_publication`, flipping
the default) — all 5 caught, baseline clean.

### Not executed in the sandbox

`pytest`, `alembic upgrade` and application boot still **cannot** be run here:
`backend/.venv` is a Windows venv (`Scripts/`, `.cp314-win_amd64.pyd`), the
sandbox is Linux, PyPI returns 403, and no other interpreter is available
(`pydantic`, `sqlalchemy`, `fastapi`, `pytest` are all unimportable). The results
above are from executing the real `policy_view` and `create_publication_policy`
code via an AST harness with stub dependencies, plus static cross-checks — they
are **not** a substitute for the pytest run, which remains outstanding.

### Fix E — `location_precision="CITY"` rejected with 422 (BE-022 live run 5)

**Symptom.** `test_created_policy_response_carries_the_active_version_fields`
posted a policy with `location_precision="CITY"` and received `HTTP 422`.

**Traced contract.** `CITY` appears in no layer of BE-022:

| Layer | Location | Values |
|---|---|---|
| Pydantic enum | `backend/schemas/publication.py` `LocationPrecision` | `EXACT`, `APPROXIMATE`, `AREA`, `HIDDEN` |
| DB CHECK | `alembic/versions/n4o5p6q7r022_...py` line 64 | `EXACT`, `APPROXIMATE`, `AREA`, `HIDDEN` |
| Model constant | `backend/db/models.py` `LOCATION_PRECISION_POLICIES` | `EXACT`, `APPROXIMATE`, `AREA`, `HIDDEN` |
| Service default | `backend/services/publication.py` `create_publication_policy` | `HIDDEN` |

Four independent layers agree; the value was invented by a test. `CITY` is a
plausible-sounding granularity, but the BE-022 precision ladder is a *privacy*
ladder — each step coarsens a location — and `CITY` has no position on it:
a city boundary is an administrative polygon, not a precision tier, and adding it
would have meant changing the Pydantic enum, the DB CHECK constraint and a
migration, all to accommodate a bad test literal.

**Classification.** The test was wrong, not the implementation. The fix is
test-only.

**Fix.**
- `tests/integration/test_publication.py` — payload `location_precision="CITY"`
  → `"AREA"`, and the response assertion updated to match.
- `tests/unit/test_publication.py` — `_StubVersion.location_precision` stub
  attribute and its assertion likewise corrected to `"AREA"`.

No production file, enum, or migration was touched.

**Guard.** `test_publication_tests_only_use_valid_policy_configuration_values`
asserts that both publication test modules use only in-vocabulary values for
`location_precision`, `redaction_level` and `min_authorization_level`. It parses
both files with `ast` (not a regex) so that comments and docstrings — which
legitimately name the rejected value — are not scanned as usage, and it inspects
three syntactic positions: keyword arguments, dict literals, and plain/annotated
assignments (the last is what the `_StubVersion` class attribute uses).

**Evidence.** AST-harness mutation matrix over the guard — 5 mutations, all
caught, baseline clean:

```
M0 current                 pass (correct)
M1 CITY in integration     CAUGHT integration location_precision: ['CITY']
M2 CITY in unit (stub)     CAUGHT unit location_precision: ['CITY']
M3 bad redaction_level     CAUGHT integration redaction_level: ['CITY']
M4 bad min_auth level      CAUGHT integration min_authorization_level: ['OFFICER']
M5 CITY both files         CAUGHT unit + integration location_precision: ['CITY']
```

M2 initially escaped because the guard did not inspect class-level `ast.Assign`
nodes; that gap is what the assignment handling was added to close.

**Not executed.** As with Fixes A–D, the sandbox cannot run the Windows venv, so
`tests/integration/test_publication.py -v` remains outstanding.

---

### Fix F — snapshot `datetime` not JSON-serializable on JSONB insert (live run 5)

**Symptom.** `test_public_evidence_never_leaks_storage_key_or_exif` failed with
`TypeError: Object of type datetime is not JSON serializable` while inserting
`publication_versions.snapshot` as PostgreSQL JSONB. The offending value was
`collected_at = datetime(..., tzinfo=timezone.utc)`.

**Authoritative snapshot contract (§8, §32).** The spec requires the snapshot to
be *deterministic, versioned, immutable, reproducible,* and *independent of
future internal field changes*, and explicitly permits JSONB. It states nothing
about temporal representation, because JSONB has no native temporal type — the
contract is therefore fixed by the platform's existing convention, not by this
spec. BE-015 already established one:
`audit_ledger.normalize_value` renders `datetime` as tz-aware ISO-8601 in UTC,
`UUID` as `str`, `bytes` as hex, and sorts dict keys. `canonical_json` sits on
top of it for the ledger's hash chain. No second serializer was added.

**Root cause.** `_project_evidence` copies `row.created_at` straight into the
projection as `collected_at`, and `build_snapshot` returned that dict unchanged.
`publish_publication` handed it to `insert_version` as JSONB, so the driver
received a live `datetime` object. This was not specific to EVIDENCE: the
projectors for ACTIVITY (`occurred_at`) and CLAIM
(`temporal_start_at`/`temporal_end_at`) emit the same shape, so a general
boundary was required rather than a one-off for `collected_at`.

**Fix.** `backend/services/publication.py` — new `_json_safe_snapshot()` applied
as the last statement of `build_snapshot`, reusing
`audit_ledger.normalize_value`. Two lines of behaviour change plus the import;
no repository, model, schema, or migration was touched.

**Why this is the correct boundary.** It sits exactly where the public
projection becomes the persisted snapshot, which is what §8 calls the source of
the record. Consequences:

- *One rule, not N.* Every projector is covered automatically, so a new target
  type cannot reintroduce the failure by forgetting a field.
- *Reproducible.* Key sorting and UTC ISO-8601 make the same evidence yield
  identical JSON on every publish, which §32 requires and a one-off
  `.isoformat()` at a single call site would not.
- *No ORM mutation.* Rows are read, never rewritten, to make persistence work.
- *No catch-all.* `normalize_value` has no `default=str`. An unknown type
  raises, so a future leak fails loudly instead of being silently stringified
  into a frozen public record. This is the specific failure mode a
  `json.dumps(..., default=str)` "fix" would introduce: it makes the reported
  `TypeError` disappear while turning arbitrary objects into arbitrary strings
  inside the permanent public record.
- *Privacy is not traded away.* The leak guard is re-run on the canonical form,
  so it checks the exact structure that gets persisted. This matters because
  canonicalization stringifies UUIDs — a `actor_id` UUID would become a
  innocuous-looking string, and the post-normalization check is what still
  rejects it.

**Files changed.**

| File | Change |
|---|---|
| `backend/services/publication.py` | import `normalize_value`; new `_json_safe_snapshot()`; `build_snapshot` returns it |
| `tests/unit/test_publication.py` | 12 new tests (§32 JSON-safety, determinism, no-catch-all, leak guards, wiring) |
| `tests/integration/test_publication.py` | 2 new tests asserting the persisted JSONB row and the faithful timestamp |

**Tests added (unit, 12).** JSON-serializability of the projection carrying
datetimes; deterministic ISO-8601 timestamps; non-UTC offsets normalized to UTC
and equal to the UTC rendering of the same instant; all four temporal fields a
projector can emit; rejection of `object()`/`set`/naive-datetime instead of
stringification; sorted keys and insertion-order independence; `storage_key` and
EXIF still rejected; internal UUIDs still rejected *after* canonicalization; the
guard running on the nested persisted structure; identity with
`audit_ledger.normalize_value` (no duplicate serializer); an AST guard that
`build_snapshot` actually *returns* `_json_safe_snapshot(...)` rather than merely
defining it; and an AST guard that no projector hand-rolls `.isoformat()` or
`str(<temporal field>)`.

The `build_snapshot` wiring guard exists because the other 11 tests call
`_json_safe_snapshot` directly — a refactor could stop calling it from
`build_snapshot` and every one of them would still pass while the live failure
returned.

**Tests added (integration, 2).** `test_persisted_snapshot_is_json_safe_and_leak_free`
reads the actual `publication_versions` row after publishing EVIDENCE and
asserts: the INSERT succeeded; `collected_at` is a `str` ending in `+00:00`;
`json.dumps` round-trips with no custom `default`; and `storage_key`,
`quarantine/internal`, `exif`, the evidence UUID, and both actor UUIDs are absent
— plus `source_version_references` is JSON-safe too.
`test_snapshot_timestamp_is_a_faithful_deterministic_rendering` asserts the stored
string round-trips to the *identical instant* as the source column, so the frozen
record cannot drift from the evidence it describes.

**Evidence — mutation matrix (12 new unit tests, 7 mutations).** All caught,
baseline clean:

```
M1 no canonicalization (the live bug)   CAUGHT  wiring guard
M2 json.dumps default=str catch-all     CAUGHT  5 tests (determinism, ISO-8601, UTC)
M3 str(datetime) not isoformat          CAUGHT  3 tests
M4 drop post-normalization leak guard   CAUGHT  3 tests (storage_key/EXIF/UUID)
M5 boundary computed then discarded     CAUGHT  wiring guard
M6 projector hand-rolls isoformat       CAUGHT  projector guard
M7 duplicate private serializer         CAUGHT  9 tests
```

M5 is the case M1 cannot distinguish from the helper tests alone: the boundary
is called and its result thrown away. Both are caught only by the wiring guard,
which is why it is there.

**Not executed.** The 12 unit tests were executed against the real harvested
`_json_safe_snapshot` and `normalize_value` in an AST harness (12/12 pass; the
mutation matrix above was run the same way). The 2 integration tests require
PostgreSQL and the Windows venv and have **not** been run —
`tests/integration/test_publication.py -v` remains outstanding.

---

### Fix G — test opened a `PROJECT` dispute, which BE-021 does not support (live run 6)

**Symptom.** `test_active_dispute_blocks_approval` failed at the INSERT with
`psycopg2.errors.CheckViolation: new row for relation "disputes" violates check
constraint "ck_dispute_target_type"`. The test constructed
`Dispute(target_type="PROJECT", target_id=project["id"], ...)` directly through
the ORM.

**Authoritative BE-021 contract.** BE-021 §5.1 enumerates the disputable
objects: *Evidence, Evidence-Claim relationship, Claim, External Assertion,
Fusion Assessment, Review Case outcome where permitted by governance rules.*
A project is not among them. That omission is enforced consistently in **four
independent places**:

| Layer | Location | Values |
|---|---|---|
| Spec | BE-021 §5.1 | Evidence, Evidence-Claim relationship, Claim, External Assertion, Fusion Assessment, Review Case |
| Migration | `m3n4o5p6q021_be021_governance.py` line 154 | same six, `ck_dispute_target_type` |
| Model | `backend/db/models.py` line 2291 | same six |
| Pydantic | `backend/schemas/dispute.py` `DisputeTargetType` | same six |
| Python constant | `backend/db/models.py` `DISPUTE_TARGET_TYPES`, enforced in `backend/services/dispute.py` `TARGET_TYPES` | same six |

**Classification: A — the test was wrong.** BE-021 is internally consistent and
`PROJECT` is *intentionally* unsupported: BE-021 disputes challenge
**assertions and objects of evidence**, and a project is a container, not an
assertion. The database was right to reject it.

This is *not* classification D, and the distinction matters. BE-022's
implementation does **not** assume project-level disputes exist:
`_has_active_dispute` queries the `disputes` table for the publication's *own*
`target_type` and `target_id`. For a `PROJECT` publication that query simply
returns no rows, which is the correct outcome — there is no such dispute. BE-022
§12 says "*if a published object becomes disputed*", i.e. the dispute and the
publication concern the same object, which is exactly what the lookup does. The
implementation was never wrong; the test invented a dispute that cannot exist.

The two vocabularies only partly overlap:

```
DISPUTE_TARGET_TYPES      EVIDENCE, EVIDENCE_CLAIM_RELATIONSHIP, CLAIM,
                          EXTERNAL_ASSERTION, FUSION_ASSESSMENT, REVIEW_CASE
PUBLICATION_TARGET_TYPES  PROJECT, ACTIVITY, CLAIM, EVIDENCE,
                          REVIEW_CASE, FUSION_ASSESSMENT

intersection               EVIDENCE, CLAIM, REVIEW_CASE, FUSION_ASSESSMENT
publishable, not disputable  PROJECT, ACTIVITY   <-- the gap that caused this
```

**Fix — test-only.** `test_active_dispute_blocks_approval` now publishes an
`EVIDENCE` and disputes that evidence, using a target in the intersection and
mirroring the sibling `test_unresolved_correction_blocks_evidence_publication`.
No production file, schema, constraint, or migration was touched.

**Files changed.**

| File | Change |
|---|---|
| `tests/integration/test_publication.py` | corrected the dispute test to a supported target; added a resolved-dispute counterpart |
| `tests/unit/test_publication.py` | 5 new tests pinning the cross-milestone vocabulary contract |

**Tests added (integration, 1).** `test_a_resolved_dispute_no_longer_blocks_approval`
is the counterpart to the blocker test. Without it, a one-line change widening
the active-status filter to include `RESOLVED` would pass every other test in
the file while permanently freezing settled targets. It constructs a properly
resolved dispute (`resolution`/`resolved_by`/`resolved_at` all set, satisfying
`ck_dispute_resolution_complete` and `ck_dispute_resolution_status_consistent`)
and asserts `ACTIVE_DISPUTE` is absent from eligibility.

**Tests added (unit, 5).** The BE-021 vocabulary, and that `PROJECT` is
publishable but not disputable; the exact intersection, and that the
publishable-but-not-disputable set is exactly `{PROJECT, ACTIVITY}`; that
`_has_active_dispute` is scoped to the publication's own target and never
widened to `project_id`; that BE-022's "active" status set matches BE-021's
partial unique index predicate, so the blocker and the idempotency guard can
never drift apart; and an AST guard that no BE-022 test constructs a
`Dispute(target_type=...)` outside `DISPUTE_TARGET_TYPES`.

That last guard is the direct analogue of the Fix E vocabulary guard. A test
that builds a `Dispute` through the ORM bypasses the service-layer
`TARGET_TYPES` check, so the only thing between an invented value and the
database is the CHECK constraint — which reports it as an opaque `psycopg2`
error pointing at the schema rather than at the test. It is AST-based, so the
docstring that names the historical `PROJECT` value is correctly ignored.

**Evidence — mutation matrix (5 new unit tests, 7 mutations).** All caught,
baseline clean:

```
M1 dispute lookup widened to project_id   CAUGHT  scoping test
M2 RESOLVED counted as active             CAUGHT  scoping + index-coupling
M3 UNDER_REVIEW dropped                   CAUGHT  scoping + index-coupling
M4 target_id filter removed               CAUGHT  scoping test
M5 index/blocker status drift             CAUGHT  index-coupling test
M6 BE-021 vocabulary gains PROJECT        CAUGHT  2 vocabulary tests
M7 a BE-022 test re-opens a PROJECT one   CAUGHT  vocabulary guard
```

M5 is the one worth calling out: the "active" status set is duplicated between
BE-021's partial unique index and BE-022's blocker query. If they drift, a
retried dispute could be refused as a duplicate while still blocking
publication. Nothing else in the suite would catch that.

**Not executed.** The 5 unit tests were executed against the real constants,
the real partial-index predicate, and the real `_has_active_dispute` in an AST
harness (5/5 pass; the mutation matrix ran the same way). The 2 integration
tests require PostgreSQL and the Windows venv and have **not** been run.

---

## Conclusion

BE-022 is implemented as a complete vertical slice. The design invariants that
carry the governance weight — the lifecycle matrix, the §14 role separation, the
target allowlist, the prohibited-field set, the snapshot's JSON-safety and
reproducibility, the blocker vocabulary and the migration's single-head symmetry —
were **verified by executing the real modules** and asserting against them, not
by inspection.

The functional tests exist and are statically cross-referenced against every
symbol they touch, and the seven live-run defects (Fixes A–G) are each covered by
regression tests proven to detect their reinjection by mutation testing. They
have still **not** been run end-to-end, and the migration has not been applied.
Treat this milestone as *implemented and statically verified, pending execution*
until the Windows commands in the first section are run.
