# BE-032 — Final Backend Acceptance, Integrity Verification & Release Readiness — Report

**Overall status: `CONDITIONALLY ACCEPTED` — the engineering assessment is complete and every
approval-free gate is verified with fresh evidence, but mandatory owner decisions and the gated
live `pofa_dev` enforcement migration remain open.**
**Production recommendation: `NOT CLEARED FOR PRODUCTION`.**

Per §16, this milestone optimises for *proving what is correct, exposing what remains uncertain, and
preventing release on unverified assumptions* — not for declaring completion. Nothing here authorises
deployment: "engineering assessment completion does not itself authorize deployment" (§14).

Convention: **[MEASURED]** = re-observed live during BE-032 on 2026-10-11 against a named target,
output quoted; **[PRIOR]** = reproduced from a milestone report, not re-run here; **[DOC]** = read
from a spec/register; **[INFERENCE]** = reasoned from measured facts.

---

## 1. Overall status

`CONDITIONALLY ACCEPTED`. See the header. This is **not** `ACCEPTED`: §14 states BE-032 can be fully
accepted only when *all mandatory decisions for the intended release are resolved*, and seven are not
(§11). It is **not** `ACCEPTANCE BLOCKED`: no verified gate was defeated — the codebase is integrity-
sound on `pofa_test`, the migration graph is clean, identity/authorization behaves correctly, and the
fresh suite is at parity. The blockers are *outstanding owner decisions*, not unproven defects.

## 2. Production recommendation

`NOT CLEARED FOR PRODUCTION`. Release-gating gaps that would be unresolved in a real deployment:
the enforcement migration has never been applied to `pofa_dev` (let alone a prod/staging analogue),
the `TRUNCATE` silent-reset hole is still open under the current owner-role, no true PITR exists, and
three runtime policy questions (invalid-chain writer behaviour, known-vs-new gap discrimination,
anchored-control exposure) are undecided. Each is documented and gated, none is silently assumed done.

## 3. Repository baseline (initial and final)

| Item | Value | Source |
| --- | --- | --- |
| Repository root | `D:/CODING/Projects/Proof-Of-Action-Final` | [MEASURED] |
| Branch | `Backend` (tracks `origin/Backend`; local-vs-remote not re-fetched) | [MEASURED] `git status -sb` |
| HEAD, initial **and** final | `07cb59a44cdf43b459ed00915fcad5c263e789b6` — "BE-30 Complete" | [MEASURED] `git rev-parse HEAD` |
| Initial working tree | `M docs/BE-029 … Results.md`; `?? BE-031 … Results.md`; `?? BE-031/BE-032 Production Task Files` | [MEASURED] `git status --short --branch` |
| Final working tree | Same as initial, **plus** the two new docs from this milestone (`BE-032 … Report.md`, `Backend Technical Debt and Deferred Fixes Backlog.md`) | [MEASURED] |
| Python / FastAPI / SQLAlchemy / Alembic | `3.12.0` / `0.141.1` / `2.0.52` / `1.11.2` | [MEASURED] interpreter probe (`.venv312_repro`) |
| DB server | PostgreSQL `15.13 (Debian 15.13-1.pgdg120+1)` in container `pofa_db` | [MEASURED] `server_version` in read-only session |
| Containers | `pofa_db`, `pofa_redis`, `pofa_minio` all `Up` | [MEASURED] `docker ps` |
| Alembic script graph | Single linear head `t0u1v2w3x030`; 25 revision files | [MEASURED] `alembic heads` / `history` |

**Pre-existing / unrelated changes preserved, not touched:** the modified BE-029 results doc and the
untracked BE-031 doc + both Production Task files all predate BE-032. Nothing from another process was
present. No excluded path (`backend/.venv312_clean/`, `backend/.venv312_repro/`, `BE-023_Status.txt`,
`BE-023_Summary.txt`) was staged or modified.

## 4. Verified findings (evidence-based)

- **[MEASURED]** `pofa_test` @ `t0u1v2w3x030`: all three BE-030 enforcement objects present
  (`trg_audit_ledger_append_only`, `audit_ledger_refuse_mutation`, `ck_audit_ledger_event_type_domain`
  each count 1); service `verify_chain` = **valid**, 45,155 events, `failure_count = 0`, contiguous
  (min 1 / max 45,155); `verify_chain_anchored` = **valid=true** over all 45,155; checkpoint tail hash
  `6d80dd95a1ff…`. Event count grew honestly from ordinary test appends during the fresh full suite.
- **[MEASURED]** `pofa_dev` @ `s9t0u1v2w029`: enforcement objects all count 0 (absent); service
  `verify_chain` = **valid=false**, 6,023 events (1..6,059), **`failure_count = 7`, all
  `sequence gap before N` (5350/5380/5385/5392/5397/5677/5682) with ZERO `event_hash mismatch`**.
  This is the **first BE-032 full service-level hash walk of `pofa_dev` since BE-030** and it proves the
  surviving rows' hashes are intact: the only damage is the 7 known historical gaps, no tampering.
  `verify_chain_anchored` reports the same 7 failures. The gap set is byte-consistent with the
  BE-030/BE-031 register (no new damage — §3.2 preservation holds).
- **[MEASURED]** Privilege posture: on **both** DBs `current_user = postgres = table_owner(audit_ledger_events)`,
  `has_truncate_priv = true`, memberships `[]`. The `BEFORE … FOR EACH ROW` trigger does not fire on
  `TRUNCATE` and `REVOKE` is inert for the owner → **`TRUNCATE` is not mitigated** (F-05 / D-CHAIN).
- **[MEASURED]** Legacy `audit_events` table exists in both DBs with **0 rows**; live ledger is
  `audit_ledger_events` (`pofa_test` 45,155 / `pofa_dev` 6,023). No code reads/writes `audit_events`
  (grep over `backend/**` → only `db/models.py:262-263`). Deferred cleanup (a migration is barred here).
- **[MEASURED]** `alembic check` on `pofa_test` = **`No new upgrade operations detected.`** — the
  `uq_user_role_scoped` `nulls_not_distinct` reflection artifact is detected then suppressed by the
  reviewed named filter in `backend/db/schema_drift_policy.py` (reason + measurement pointer logged).
- **[MEASURED]** `external_subject` is a **write-only key with no read consumer** (BE-029 OQ-3, re-confirmed):
  only the create-user path writes it (`services/authorization.py:340` defaults a missing value to
  `uuid4()` → `repositories/authorization.py`; `endpoints/auth.py:160`); auth resolves on `User.id`.
- **[MEASURED]** Identity/authorization behavior is shipped and correct: email normalized
  (`strip().lower()`, `services/authorization.py:335`); provider+subject UNIQUE constraint
  (`models.py:60`); conflict classification keyed on constraint name against `IDENTITY_UNIQUE_OBJECTS`
  (`services/authorization.py:317-322`); `POST /auth/users` → **409 only for the three identity
  objects, all other IntegrityError re-raised → 500** after `db.rollback()` (`endpoints/auth.py:166-173`).
- **[MEASURED]** Operational surface: liveness (`/health`) is dependency-agnostic (application check
  only); readiness (`/ready`, `/healthz`) requires PostgreSQL + Redis + Storage and returns 503 when a
  required dependency is non-healthy; error detail is redacted unless `environment == "development"`
  (`observability/health.py:225-286`); the PG readiness probe builds a fresh engine through
  `build_guarded_engine` so the armed-context guard applies and disposes only its own engine. Startup
  hook (`main.py`) runs only OpenTelemetry + a log line — it does **not** auto-migrate or `create_all`.
- **[MEASURED]** Config defaults are dev-safe but not prod-safe: `jwt_secret` default `"changeme"`,
  `s3_secret_key` default `""`, `environment` default `"development"`,
  `observability_redact_sensitive` default `True`. A default `changeme` JWT secret in a production
  deployment is a release-blocking configuration risk (**[INFERENCE]**; not a code defect to fix here).

## 5. Fresh tests (exact commands, environment, counts)

Run **sequentially, never concurrently**, on `pofa_test`, interpreter `.venv312_repro`, target verified
(`target_database_name=pofa_test`) before execution.

| Run | Command | Result | Duration |
| --- | --- | --- | --- |
| Full suite | `pytest -p no:cacheprovider -q -rs` (via `TEST_DATABASE_URL` republished by `tests/conftest.py`) | **792 passed, 1 skipped, 0 failed, 9 warnings** | 743.33 s (12:23) |
| Targeted acceptance matrix (15 files) | `pytest -p no:cacheprovider -q -rs <files>` | **176 passed, 0 failed, 6 warnings** | 98.37 s (1:38) |

**Baseline parity:** 792/1/0 reproduces BE-030's and BE-031's full-suite counts exactly → BE-032
introduced **no regression**. This run was slower (743 s vs BE-031's 523 s) — environmental, not a
result change. The targeted matrix is broader than BE-031's (176 vs 123) because BE-032 added the DB-
safety/target and observability health/redaction files: `unit/test_database_safety.py`,
`unit/test_test_target.py`, `unit/observability/test_health.py`, `unit/observability/test_redaction.py`,
on top of BE-031's 11 audit/identity/drift/revision-graph files.

**Skip (both runs):** exactly **1** — `tests/unit/test_preflight.py:117`
`test_ml_missing_never_becomes_available_without_importer`, reason *"ML stack genuinely installed in
this environment"*. Deterministic environmental skip, identical to BE-030/BE-031 — not a regression.

**Warnings:** 9 (full) / 6 (targeted) — pre-existing Starlette/FastAPI/Pydantic deprecations (`on_event`
at `main.py:121,135`, `HTTP_422_UNPROCESSABLE_ENTITY`, class-based config). Non-fatal, not suppressed,
not new.

**Disposables / enforcement behavior:** enforcement UPDATE/DELETE/INSERT/CHECK/anchored/D-2-A behaviors
were exercised only through the sanctioned pytest armed context on `pofa_test` (permitted test-database
writes) and are green. No disposable clone was rebuilt this session (the clone proof is **[PRIOR]**
BE-030 §3). `pofa_dev` historical records were **not** rewritten (§3.2).

## 6. Migration / schema acceptance (per environment)

- **Script graph [MEASURED]:** single head `t0u1v2w3x030`, linear (`s9t0u1v2w029 → t0u1v2w3x030 → head`),
  25 files, no merge/orphan. `tests/unit/test_migrations.py` pins the invariants (exactly one head,
  single root, no merges, full reachability) — green.
- **`pofa_test` [MEASURED]:** `alembic_version = t0u1v2w3x030`; `alembic check` = **CLEAN** (only the
  reviewed `uq_user_role_scoped` artifact suppressed). Enforcement objects present. Schema acceptance:
  **PASS**.
- **`pofa_dev` [MEASURED]:** `alembic_version = s9t0u1v2w029` — **one revision behind**. Enforcement is
  absent because the BE-030 migration has not been applied, not because of drift. `alembic check` was
  **not** run against `pofa_dev` (kept strictly read-only; §3.1). Schema acceptance: **DEFERRED on the
  gated `pofa_dev` migration (D-PFD)**. A clean `pofa_test` comparison does **not** transfer to `pofa_dev`.

## 7. Audit-ledger acceptance (per environment)

| Environment | Enforcement | `verify_chain` | `verify_chain_anchored` | Interpretation |
| --- | --- | --- | --- | --- |
| `pofa_test` | trigger+fn+CHECK present [MEASURED] | **valid**, 45,155 / 0 failures | valid=true over 45,155 | Append-only enforced, chain intact, tail hash `6d80dd95…`. **PASS** (write-behavior proven by the 176-test matrix on this DB only). |
| `pofa_dev` | absent [MEASURED] | **invalid**, 6,023 / **7 gap-only failures, 0 hash mismatch** | same 7 failures | No enforcement (pre-BE-030). Damage is purely the 7 preserved historical gaps; survivors hash-intact. **BLOCKED** pending D-PFD + D-CHAIN. |

- **Append-only / UPDATE / DELETE / out-of-domain INSERT / hatch / D-2-A predecessor refusal / rollback
  consistency / concurrent-writer safety:** shipped-tested on `pofa_test`, green [MEASURED this session].
- **`TRUNCATE`:** **NOT protected on either DB** (F-05). Reported honestly, not suppressed.
- **Anchored/checkpoint control:** implemented and proven, **unpolled at runtime** (F-03) — only
  `verify_chain` reaches `GET /api/v1/audit/verify`.
- **Known-vs-new gap discrimination:** **absent in runtime code** (F-04) — `verify_chain` names the
  symptom but never tags a gap as one of the 7 register ranges.
- **Writer-on-invalid-chain policy:** **unresolved** (D-CHAIN). D-2-A validates only the immediate
  predecessor, so a `pofa_dev` append onto its locally-valid tail would succeed despite the 7 gaps
  **[INFERENCE from the shipped D-2-A contract]**; no approved policy dictates refusal/continuation.
- Diagnostic checks used read-only sessions (both protected DBs); enforcement-write tests used the armed
  `pofa_test` context only. No test generated ledger events on `pofa_dev`.

## 8. Identity / authorization acceptance

**PASS (all [MEASURED] against current code + the 176-test matrix on `pofa_test`).**
Username & email DB uniqueness live (`s9t0u1v2w029`); email normalized on write; provider+subject UNIQUE
constraint unchanged (`test_identity_key_constraint_definition_is_unchanged`); identity conflicts
classified by constraint name (not exception type) → 409; non-identity IntegrityError → 500 after
rollback; NULL `external_subject` rows permitted and non-colliding (NULLS DISTINCT); scoped-role
behavior, pagination exactly-once, and the database-safety guard pinned by their named tests, all green.
Retired BE-028/BE-029 synthetic fixtures were **not** reintroduced (§3.3). `external_subject`'s nullability
policy is **not** an identity-behavior defect; it is decision OQ-3 (§11).

## 9. Operational acceptance (implemented vs proposed)

**Implemented & verified:** liveness vs readiness separation; PG/Redis/Storage required-readiness with
environment-gated error redaction; `RequestIDMiddleware`; CORS; `/metrics`; secret-redaction default on.

**Implemented but under-adopted (not a defect):** the durable anchored/checkpoint control is not wired
to any caller (F-03).

**Proposed only — NOT executed, NOT claimed tested:** API/worker restart (no service restarted —
prerequisites in BE-031 Appendix C), live `pofa_dev` migration (Appendix B plan), non-owner role split
(Appendix D), backup restoreability for a *current* `pofa_dev` state (no valid current restore point
exists; the BE-029 G3 dump predates BE-030 and **must not** be presented as a restore point for a BE-030
upgrade). **No backup is claimed recoverable for the current `pofa_dev`; no alerting is claimed active.**

## 10. Environment differences (`pofa_test` vs `pofa_dev`)

| Dimension | `pofa_test` | `pofa_dev` |
| --- | --- | --- |
| Revision | `t0u1v2w3x030` (head) | `s9t0u1v2w029` (behind 1) |
| Enforcement objects | present (3/3) | absent (0/3) |
| Ledger | 45,155 rows, contiguous | 6,023 rows, 36 missing in 7 ranges |
| `verify_chain` | valid | invalid (7 gaps, 0 hash mismatch) |
| `alembic check` | CLEAN (reviewed artifact) | not run (read-only preserved) |
| `external_subject` NULL | 2,710 / 2,710 [PRIOR BE-031] | 1,004 / 1,054 [PRIOR BE-031] |
| Table owner = role | `postgres` owner, TRUNCATE allowed | same |

The `pofa_test` environment is the **test** DB (armed context, honest appends expected). `pofa_dev` is a
**long-lived dev** DB, touched by this milestone **read-only only**.

## 11. Owner Decision Register (deliverable D)

For each: the decision, options, implications, evidence, and what remains blocked. **No approval was
fabricated.** These seven are the reason status is `CONDITIONALLY ACCEPTED`, not `ACCEPTED`.

### 11.1 OQ-3 — `external_subject` policy
- **Decision:** give the column real meaning or retire it.
- **Options:** A keep nullable+inert (zero migration, latent trap if a federated flow later assumes
  uniqueness); B backfill+NOT NULL (needs an approved subject-derivation mapping there is no IdP to
  source; blocked on policy not code); C NULLS-NOT-DISTINCT / functional-unique on the populated subset
  (smallest real effect, still an identity-policy + drift-visible ALTER); D retire the column (forecloses
  the reserved federated anchor).
- **Implications:** B/C/D are Alembic revisions → they interact with the open D-PFD migration. C is
  drift-gate-visible; B is not.
- **Evidence:** §4, §8; full brief BE-031 Appendix A.
- **Blocked:** a product/security call. **Recommendation (evidence-supported, not approval):** Option A
  with an explicit "declared, not enforced, no consumer" marker is the cheapest honest state if no
  federated login is planned near-term.

### 11.2 D-CHAIN — invalid-chain writer policy
- **Decision:** what a writer should do when an append meets an already-invalid *historical* chain.
- **Options:** refuse (max integrity, breaks `pofa_dev` writes today); controlled-continuation with an
  alert (current de-facto behavior — D-2-A only checks the immediate predecessor); governed recovery.
- **Implications:** none of the three has an approved policy; today's behavior is emergent, not chosen.
- **Evidence:** §7 (`pofa_dev` valid=false; D-2-A immediate-predecessor contract).
- **Blocked:** governance decision + acceptance tests. Per §3.2 BE-032 **does not** choose or repair.

### 11.3 F-03 — anchored / checkpoint control exposure
- **Decision:** expose `verify_chain_anchored`/`ledger_checkpoint` over an authorized endpoint, a
  scheduler, or keep internal-only.
- **Options:** admin-only authenticated endpoint; periodic scheduled poll; leave as log-only/manual.
- **Implications:** any HTTP exposure = new API surface + authz/scope design (§12 bars closing a
  checklist by exposing it); the digest is log-only today because `TRUNCATE` would erase an in-DB digest.
- **Evidence:** `endpoints/audit_ledger.py:91-101` wires only `verify_chain`.
- **Blocked:** a product/architecture decision (consumer, authorization, semantics, safety).

### 11.4 F-04 — known-vs-new gap discrimination
- **Decision:** how to tell one of the 7 register gaps from fresh tampering at runtime.
- **Options:** persisted signed baseline the runtime consults; periodic checkpoint comparison; keep the
  register procedural (docs/script only).
- **Implications:** §14 bars a shipped test from reading live `pofa_dev`, so a naive baseline-in-test is
  disallowed; a real solution needs a persisted-baseline/signed-checkpoint design. Must **not** suppress
  an integrity error because "a similar gap was seen before" (§3.2 / §5.4).
- **Evidence:** `verify_chain` reports symptom type only.
- **Blocked:** architecture + policy decision.

### 11.5 D-PFD — authorize the live `pofa_dev` enforcement migration
- **Decision:** apply `t0u1v2w3x030` to `pofa_dev`.
- **Options:** (a) leave `pofa_dev` unenforced (dev-only) and ship enforcement to staging/prod first —
  BE-030 §2.1 names this safest; (b) migrate after a fresh verified backup.
- **Implications:** changes runtime behavior of every audited write on `pofa_dev` (D-1 refusal, D-2-A);
  requires fresh `pg_dump` + restore-to-disposable proof + per-step sign-off + workers/API stopped. No
  valid current restore point exists today.
- **Evidence:** §3, §6, §10 (all [MEASURED]).
- **Blocked:** explicit owner authorization. Plan prepared (BE-031 Appendix B), **not executed**.

### 11.6 F-05 — non-owner role + TRUNCATE hardening
- **Decision:** adopt a least-privilege `poa_runtime` (DML, no TRUNCATE/DROP) with a separate
  `poa_migrate`/owner for DDL.
- **Options:** full role split; or keep accept-open under D-1-A and rely on append-onto-rebuilt-chain
  detection (currently unpolled — see F-03).
- **Implications:** a `TRUNCATE` guard is meaningful **only** once the app is not the table owner;
  changes DB roles/ownership → §3.1 gate + disposable-environment proof first.
- **Evidence:** §4, §7 (both DBs owner, `has_truncate_priv`, row trigger doesn't fire on TRUNCATE).
- **Blocked:** owner + deployment work. Follow-up proposed (BE-031 Appendix D), **not started**.

### 11.7 D-RESTART — API / worker restart
- **Decision:** restart services to load current code / after D-PFD.
- **Implications:** startup does not auto-migrate; workers emit audit rows via `append_event`; hard
  kill can strand an `analysis_worker` job in `running`. Restart is itself owner-gated; behavior
  differs pre/post D-PFD (UPDATE/DELETE newly refused after).
- **Evidence:** `main.py` startup hook (no auto-migrate); BE-031 Appendix C.
- **Blocked:** owner action. BE-032 restarted nothing (started Docker Desktop only to restore the
  `pofa_db` *dependency* after an unrelated outage — no API/worker process launched).

## 12. Release Gate Matrix (deliverable B)

| # | Gate | Evidence | Status | Owner | Closure criteria | Disposition |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Repo / test integrity | 792/1/0 + 176/0 fresh; reviewed tree | **Verified** | Eng | parity maintained | PASS |
| 2 | Migration consistency | single head `t0u1v2w3x030`; graph tests; `alembic check` CLEAN | **Verified** | Eng | unchanged | PASS |
| 3 | `pofa_test` enforcement | catalog 3/3; `verify_chain` valid 45,155/0 | **Verified** | Eng | unchanged | PASS |
| 4 | `pofa_dev` enforcement migration | plan prepared; not run | **Blocked** | Owner | fresh backup+restore proof+sign-off+stopped services | do not execute |
| 5 | `external_subject` (OQ-3) | write-only, no consumer | **Open** | Product/Sec | recorded decision | decision needed |
| 6 | Invalid-chain writer policy | D-2-A immediate-pred only; `pofa_dev` invalid | **Open** | Governance | approved policy + tests | decision needed |
| 7 | TRUNCATE hardening (F-05) | owner-role on both DBs | **Open** | Owner/Deploy | non-owner role proven disposable-first | prepare; do not apply live |
| 8 | Anchored/checkpoint exposure (F-03) | only `verify_chain` wired | **Open** | Product/Arch | consumer+authz+semantics+poll | decision needed |
| 9 | Gap discrimination (F-04) | runtime lacks known-vs-new tagging | **Open** | Arch | approved policy + semantics | decision needed |
| 10 | API/worker restart | startup no auto-migrate; workers append audit | **Do not execute** | Owner | checklist + explicit auth | checklist only |
| 11 | Production deployment | — | **Do not execute** | Owner | approved release plan | not cleared |
| 12 | Backup / recovery | no valid current restore point; no PITR | **Reported gap** | Owner | restore proof or accepted limit | limitation reported |
| 13 | Git delivery | HEAD `07cb59a4`; my docs only | **No commit/push** | User | reviewed changes + authorization | intentionally none |

A prepared plan ≠ an executed action; a `pofa_test` pass ≠ a `pofa_dev` state; a gate with a runbook is
not "resolved" until an owner acts.

## 13. Remaining backlog (severity / dependencies / closure)

Canonical register: **`docs/Backend Technical Debt and Deferred Fixes Backlog.md`** (created/adopted
this milestone at the §5 path — none existed). Summary:

- **High / release-blocking (owner):** D-PFD (pofa_dev enforcement, blocks prod parity), F-05 (TRUNCATE),
  D-CHAIN (writer policy).
- **Medium:** OQ-3 (external_subject drift risk), F-03 (unpolled durable control), F-04 (gap
  discrimination), D-BACKUP (no PITR / no current restore point), `jwt_secret` default in prod **[INFERENCE]**.
- **Low / deferred:** D-LEGACY (`audit_events` 0-row vestigial table + model), D-MIGDOC (stale docstring
  head name), D-DRIFT/D-GIST (mitigated by catalog pins + custom gate), D-RESTART-FIX2 (stranded job).
- Dependency chain: several OQ-3 options (B/C/D) and F-05 are Alembic/role changes that should be ordered
  relative to D-PFD.

## 14. Files changed (paths + rationale)

Created (documentation only — no code/schema/DB change):
- `docs/BE-032 Final Backend Acceptance and Release Readiness Report.md` — this report (deliverables A, B, D).
- `docs/Backend Technical Debt and Deferred Fixes Backlog.md` — canonical backlog (deliverable C).

Read-only inspection / new scratch diagnostics (outside version control, no secrets):
- `D:/CODING/Scratch/be032_chain_verify.{py,sh}` — read-only service-level `verify_chain`/anchored/
  checkpoint probe (AUTOCOMMIT + `SET default_transaction_read_only=on`, asserts `current_database()`).
- Reused `D:/CODING/Scratch/be031/run_targeted.sh`, `recon_baseline.py`.

**No application code, migration, model, config, or test was modified.** §12 review found no in-scope,
approval-free, safely-testable defect: every open finding is an owner decision, an accepted design
choice, or protected-DB history. Therefore §12's documented-assessment outcome applies.

## 15. Safety statement

- `pofa_dev`, `pofa_test`: **read-only inspection only** (SELECT/`SET READ ONLY` sessions; the
  sanctioned armed pytest context writes **only** to `pofa_test`, target-verified via
  `current_database()`). No reset, destructive cleanup, live/backfill migration, role/grant change,
  destructive restore, or write-capable probe touched either DB. `pofa_dev` remains `s9t0u1v2w029`.
- **Audit ledger:** no event updated, deleted, renumbered, manufactured, hash-rewritten, or sequence-
  reset; integrity failures were **reported, not suppressed**. The 7 `pofa_dev` gaps remain preserved.
- **Identity/schema:** BE-029 constraints intact; no synthetic fixtures reintroduced; no
  `external_subject` policy decided; extension-owned objects untouched; no migration history rewritten;
  real drift not hidden under the known-artifact filter.
- **No live operation performed:** no migration applied, no API/worker restarted, no deployment, no
  production infrastructure change. The only environment action was starting Docker Desktop to restore
  the `pofa_db` dependency container after an unrelated outage (launched no application process).

## 16. Git status (as reported, not performed)

- HEAD unchanged: `07cb59a4…` ("BE-30 Complete"). **`git add`: none. Commit: none. Push: none.
  `git fetch`: none** → local-vs-`origin/Backend` not re-verified this milestone.
- Final tree: modified BE-029 doc + untracked BE-031 doc + both Production Task files (all pre-BE-032) +
  this report + the canonical backlog file. Excluded paths (`backend/.venv312_clean/`,
  `backend/.venv312_repro/`, `BE-023_Status.txt`, `BE-023_Summary.txt`) not staged/touched.
- Expected-and-achieved: **nothing staged, committed, or pushed.**

## 17. Next action (single highest-priority, evidence-supported)

**Have the owner decide D-PFD (§11.5) and order F-05/D-CHAIN alongside it.** The codebase's integrity is
proven on the test environment; the dominant un-closed risk to any real release is that enforcement has
never reached the long-lived environments, and the writer policy on the still-invalid `pofa_dev` chain is
unchosen. The safe, owner-free interim is BE-030 §2.1 option (a): leave `pofa_dev` unenforced and treat
enforcement rollout to a *non-protected* staging target as the next planned, backup-gated action. Nothing
further can be safely executed by an engineer without an explicit, operation-specific owner authorization.

---

### Appendix — §14 Acceptance-criteria checklist

- [x] Initial Git baseline recorded (§3) — [x] Existing changes preserved (§3, §16)
- [x] Canonical backlog reconciled (§13; file created at §5 path) — [x] Alembic revision graph verified (§6)
- [x] Schema-drift behavior documented accurately (§4, §6) — [x] Audit enforcement assessed per env (§7)
- [x] Historical ledger gaps preserved and reported (§7) — [x] No historical events rewritten/deleted (§15)
- [x] Identity/authorization constraints verified (§8) — [x] Database safety protections verified (§15)
- [x] Fresh regression results recorded (§5) — [x] Skips and blockers explained (§5)
- [x] Operational documentation checked against implementation (§9)
- [~] Backup/recovery claims supported by evidence — **reported as a limitation** (no current restore point; §9/§13)
- [x] Environment differences recorded (§10) — [x] Owner decisions registered (§11)
- [x] Live migration/restart prerequisites documented (§11.5, §11.7) — [x] No unauthorized DB mutation or live op (§15)
- [x] Final diff reviewed (§14) — [x] No commit or push performed (§16)

Because mandatory release decisions (gates 4–9) remain open, full acceptance is withheld and production
is **NOT CLEARED**.
