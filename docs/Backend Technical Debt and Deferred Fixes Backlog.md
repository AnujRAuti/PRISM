# Backend Technical Debt and Deferred Fixes Backlog (Canonical)

**Purpose.** The single reconciliation register for backend work left deliberately open across BE-023 →
BE-032. This file is **canonical** for the path named in the BE-032 spec §5. Before BE-032 no file
existed here; the authoritative registers lived inside three milestone reports. This backlog
*consolidates and re-verifies* them against current code/database state and does **not** duplicate
them or silently close any decision-dependent item. Each item points at the milestone report that
proves it.

Convention: **[MEASURED]** = re-observed against the live target during BE-032 (2026-10-11);
**[PRIOR]** = reproduced from a milestone report, not re-run; **[DOC]** = read from a spec/register.
These tags describe the **BE-032 assessment** snapshot. **BE-032R (2026-10-11)** then *implemented and
disposable-verified* several of the §1 items; its per-item outcomes (new status, code/test/migration
references, remaining live authorization) are recorded in **§4** and do **not** overwrite the register
below, which is preserved as the assessment-time history.

Classification vocabulary (BE-032 §5): Resolved-and-verified · Implemented-not-fully-verified ·
Partially-resolved · Deferred · Blocked-by-owner-decision · Superseded · Unresolved.

---

## 1. Owner-gated decisions (open — cannot be closed by an engineer)

These require a product / security / deployment owner call. None was fabricated by BE-032. Full
options/evidence/implications for each live in the **BE-032 Final Acceptance Report §11 Owner Decision
Register**.

| ID | Decision | Class | Status | Where it came from | Evidence pointer |
| --- | --- | --- | --- | --- | --- |
| OQ-3 | `users.external_subject` policy: keep nullable-and-inert, backfill+NOT NULL, NULLS-NOT-DISTINCT on the populated subset, or retire the column | Blocked-by-owner-decision | **Open** [MEASURED] | BE-029 OQ-3; carried BE-030 §2.4, BE-031 §I.2 | `backend/db/models.py:50-60`; write-only path `services/authorization.py:340`; no read consumer (grep `backend/**` → only write path + model). `pofa_dev` 1,004/1,054 NULL, `pofa_test` 2,710/2,710 NULL; `identity_provider` distinct `{local}`; constraint `uq_user_identity_subject` inert for NULL (NULLS DISTINCT) |
| D-CHAIN | Writer policy when an audit append meets an **already-invalid** historical chain (`pofa_dev`'s 7 known gaps) | Resolved-and-verified (**owner-ACCEPTED 2026-10-11**) | **Closed** — policy `controlled_continuation` implemented + tested; owner accepted in BE-033 §6 | BE-030 §3 / BE-032 §5.2; BE-032R §5; BE-033 §6 | D-2-A validates only the *immediate* predecessor; a fresh append onto `pofa_dev`'s locally-valid tail succeeds while `verify_chain` reports the 7 gaps. Implemented `LEDGER_WRITER_POLICY="controlled_continuation"` in `services/audit_ledger.py`. See §6. |
| F-03 | Expose the §9 anchored/checkpoint control (`verify_chain_anchored` / `ledger_checkpoint`) over an authorized endpoint, or keep it internal-only | Blocked-by-owner-decision | **Open** [MEASURED] | BE-031 F-03 | Only `verify_chain` is wired to `GET /api/v1/audit/verify` (`endpoints/audit_ledger.py:91-101`); anchored control has no endpoint/scheduler/automatic caller. Proven by tests, unpolled at runtime. Surfacing it = new API surface → §12 bars it without an owner call. |
| F-04 | Runtime discrimination of **known** historical gaps vs **new** tampering | Resolved-and-verified (**owner-ACCEPTED 2026-10-11**) | **Closed** — versioned baseline registry implemented + tested; owner accepted the 7-gap register in BE-033 §6 | BE-031 F-04; BE-032R §5; BE-033 §6 | `services/audit_integrity_baseline.py` (`POFA_DEV_HISTORICAL_BASELINE` v1, default-deny `EMPTY_BASELINE`, hash-mismatch/missing-predecessor never blessable). Live `pofa_dev` re-verified `known_historical_only` 7/0/0. See §6. |
| F-05 | `TRUNCATE` hardening via a non-owner least-privilege runtime role | **Applied-to-live-dev + verified against a running service** (production still pending) | BE-034 proved it on a faithful clone; **BE-035 cut the actual development `DATABASE_URL` over to `poa_runtime` and restarted the real API against live `pofa_dev`** | BE-030 §2.3; BE-031 F-05; BE-032R §5; BE-033 §3; BE-034 §3–§6; **BE-035 §1–§7** | `scripts/provision_runtime_roles.sql` applied to live `pofa_dev`: `poa_runtime` is non-owner (owner=`postgres`), SELECT+INSERT only on the ledger. **BE-035:** `.env` `DATABASE_URL` repointed owner→`poa_runtime`; `uvicorn` started; `pg_stat_activity` shows the app connection as `poa_runtime` (only the operator `psql` probe is `postgres`) — no fallback; `/ready` reports postgresql+redis+storage healthy; live anchored endpoint stays `known_historical_only` 7/0/0; app-path append works while UPDATE/DELETE/**TRUNCATE**/`SET ROLE postgres` denied (denied on the clone). **Pending:** production runtime identity + a real JWT secret store (external actions). **BE-036** closed the BE-035-D1 note: `webhook_worker` now imports and starts, and its `get_session()` opens a `poa_runtime` session (startup-verified; see §9). See §8. |
| D-PFD | Authorization to migrate live `pofa_dev` → `t0u1v2w3x030` (enforcement) | **Applied-to-live-`pofa_dev`** | **Closed (migration done)** | BE-030 §2.1; BE-031 F-01; BE-032R §5; BE-033 §4 | Owner-authorized 2026-10-11 after fresh backup + restore-to-clone gate. Live `pofa_dev` `s9t0u1v2w029` → `t0u1v2w3x030`; 6023 rows intact; trigger+function+CHECK present; UPDATE refused even as owner without hatch. See §6. |
| D-RESTART | API / worker restart after BE-029's live `pofa_dev` migration (and to load current code) | **Development DONE; production pending** | **API restart on live `pofa_dev` as `poa_runtime` completed (BE-035); webhook worker unblocked and startup-verified (BE-036 closed BE-035-D1); production restart pending** | BE-030 §2.4; BE-031 I.4; BE-033 §7/§11; BE-034 §5; **BE-035 §5–§7**; **BE-036 §3–§6** | BE-035 repointed the real dev `.env` to `poa_runtime` and started the actual `uvicorn` against live `pofa_dev`: `/api/v1/health`·`/api/v1/ready`·`/health`·`/ready`·`/healthz`·`/metrics` all 200; `/ready` reports postgresql+redis+storage healthy; `pg_stat_activity` confirms the running app connection is `poa_runtime`. `analysis`/`notification`/`retention` workers import and share that engine; **BE-036 fixed the `webhook_worker` `ImportError`, so it now imports and its `get_session()` opens a `poa_runtime` session** (startup + full delivery lifecycle verified with mocked egress; a live daemon pass against `pofa_dev` was intentionally not run to avoid real outbound delivery). **Pending:** production restart + runtime identity (external). See §8. |
| BE-035-D1 | `webhook_worker.py` imports a non-existent `SessionLocal` and cannot start | **CLOSED — fix implemented + verified through actual worker startup (BE-036)** | **Closed** [MEASURED — `ImportError` reproduced, then fixed and startup-verified] | BE-035 §7.1 (found/deferred); **BE-036 §3–§6** | **Root cause:** `backend/workers/webhook_worker.py:20,269,294` imported/called a bare `SessionLocal`, but `backend/db/session.py` exports only `get_session` (the `sessionmaker` is the private `_SessionLocal`). Import-time → `ImportError: cannot import name 'SessionLocal'`; the other three workers already use `get_session()`. **Fix (smallest correct):** `from backend.db.session import get_session`; `db = get_session()` at both call sites (`run_worker_once` and `__main__`). No interface/behaviour change. **Verified:** module imports (`IMPORT_OK backend.db.session`); `python -m backend.workers.webhook_worker --help` runs; `get_session()` opens a `poa_runtime` session + clean close (BE-036 §5); full delivery lifecycle tested with mocked `urlopen` — success→DELIVERED, connection/5xx→RETRYING, 4xx/exhausted/SSRF→FAILED, disabled→DISABLED, auto-disable after 10, fanout idempotent, no re-processing of completed, every outcome appends one `WEBHOOK_DELIVERY_*` ledger row via `append_event`, zero real egress. `tests/integration/test_be036_webhook_worker.py` (10 tests). Full suite **831 passed / 1 skipped / 0 failed** on `pofa_test`. See §9. |
| BE-036-D1 (new finding) | `webhook_worker._attempt_delivery` delivers via `urllib.request.urlopen`, whose default opener **follows HTTP 3xx redirects**, contradicting the "never follow redirects" SSRF guarantee asserted in `webhook_worker.py` and `services/webhook.py::validate_webhook_url` | Found-and-reported; **deferred (out of BE-036 scope — not caused by the import defect)** | **Open** [MEASURED — code path read] | BE-036 §9 | `webhook_worker.py` `_attempt_delivery` builds `urllib.request.Request(...)` and calls `urllib.request.urlopen(req, timeout=10)`. Python's default opener installs `HTTPRedirectHandler`, so a 301/302 from the endpoint is followed to a new URL that `validate_webhook_url` never inspected — a redirect to a private/metadata address is the exact SSRF vector the guard exists to block. Security-relevant, pre-existing, independent of BE-035-D1, and its fix (a no-redirect opener / explicit 3xx handling + tests) is a reliability milestone in its own right, so it is **not** folded into BE-036. Recommend a narrow follow-up. The `timeout=10` bound and no-retry-on-SSRF path are correct today; only redirect-following diverges from the documented contract. |

## 2. Deferred / unresolved technical debt (approval-free but not done this milestone)

| ID | Item | Class | Status | Evidence pointer |
| --- | --- | --- | --- | --- |
| D-LEGACY | Legacy `audit_events` table + model `AuditEvent` still shipped but unused | Partially-resolved / Deferred | **Open** [MEASURED] | `db/models.py:262-263`. Table physically exists in **both** DBs, **0 rows**; live ledger is `audit_ledger_events` (`pofa_test` 44,747 / `pofa_dev` 6,023). No code reads/writes `audit_events` (grep → only the model def). Dropping it = a migration against protected DBs → barred by §3.1; removal deferred to an owner-approved migration. |
| D-MIGDOC | `tests/unit/test_migrations.py` module docstring names a stale head (`o5p6q7r8s025`) in prose while `EXPECTED_HEAD` correctly = `t0u1v2w3x030` | Deferred (cosmetic) | **Open** | BE-030 §2.5. Non-load-bearing narrative; the constant is authoritative and the revision-graph tests pass. Left rather than silently rewritten; a doc-only fix is safe but out of BE-032's evidence-gated scope. |
| D-DRIFT | Alembic `compare_metadata` blind spots: cannot reflect triggers or CHECK constraints; mishandles `NULLS NOT DISTINCT` on `uq_user_role_scoped` | Implemented-not-fully-verified (mitigated) | **Contained** [MEASURED] | `backend/db/schema_drift_policy.py` named filter suppresses the `uq_user_role_scoped` artifact (logged reason + pointer); `alembic check` on `pofa_test` = `No new upgrade operations detected.` Enforcement objects stay invisible to autogenerate by design → catalog-pin tests (`test_enforcement_objects_are_present_in_the_catalog`) + custom `test_schema_drift_gate.py` are the real guards. |
| D-GIST | Expression / GiST index reflection limits | Deferred | **Open [PRIOR]** | BE-028/BE-030 feasibility; autogenerate does not round-trip some expression/GiST indexes. Contained the same way as D-DRIFT (catalog pins, not autogenerate). |
| D-BACKUP | Backup/recovery has **no true PITR** (`archive_mode=off`, `wal_level=replica`, zero archived WAL); `pg_dump`/`psql` exist only inside container `pofa_db` | Unresolved (environment) | **Open [PRIOR]** | `project-be029-g3-backup`. A dump is one transactionally-consistent snapshot; post-dump writes cannot be replayed. No verified current restore point exists for `pofa_dev` (the BE-029 G3 dump predates BE-030). |
| D-RESTART-FIX2 | Hard-killing `analysis_worker` can strand a job in `running` | Deferred | **Open [PRIOR]** | BE-031 Appendix C step 3 references the separate FIX-002 in the cleanup backlog; recovery path not implemented. |

## 3. Resolved and verified (recorded so they are not re-opened)

| ID | Item | Class | Verification |
| --- | --- | --- | --- |
| R-BE027 | CORS + request-ID middleware | Resolved-and-verified | `app/main.py:31,40`; BE-027 tests green. |
| R-BE028 | Schema-drift containment gate (B-3) + three declared-but-unmigrated indexes | Resolved-and-verified | `q7r8s9t0u027`; `test_schema_drift_gate.py` passes. |
| R-BE029-id | Username/email DB uniqueness (`s9t0u1v2w029`), synthetic-fixture retirement | Resolved-and-verified | BE-029 OQ-1/2/4 shipped; identity contract tests green. |
| R-BE029-conflict | `POST /auth/users` 409 only for the three identity objects; other IntegrityError → 500; rollback then re-use | Resolved-and-verified | `endpoints/auth.py:166-173`, `services/authorization.py:317-322`; `test_be029_identity_conflict_api.py`. |
| R-BE030 | Append-only enforcement (`trg_audit_ledger_append_only`, `audit_ledger_refuse_mutation`, `ck_audit_ledger_event_type_domain`) + D-2-A predecessor check + anchored verify + checkpoint digest + hatch, migration `t0u1v2w3x030`, symmetric downgrade | Resolved-and-verified on `pofa_test` **and now applied to live `pofa_dev`** | Clone proof + catalog pin + enforcement suite. **Applied to live `pofa_dev`** at `t0u1v2w3x030` in BE-033 §4 (D-PFD closed). |
| R-OQ5 | Application-level IntegrityError handling | Resolved-and-verified | BE-029 follow-up; see R-BE029-conflict. |
| R-OQ6 | BE-029 commit | Superseded/Resolved | Committed `22ce7497`, HEAD `07cb59a4` [MEASURED]; not pushed (unpushed state not re-fetched this milestone). |

---

## 4. Reconciliation rule

An item may move to §3 (resolved) only with (a) fresh or reproduced evidence and (b) no outstanding
owner decision. Every §1 item is therefore reported by BE-032 as a **blocker**, not closed. A prepared
plan (Appendix B migration, Appendix D role split) is **not** an executed action and does **not** clear
the gate. See the BE-032 report §12 Release Gate Matrix for the per-gate disposition.

---

## 5. BE-032R remediation reconciliation (2026-10-11)

BE-032R took the seven §1 owner-gated blockers and did all *safe, in-scope* engineering: it
implemented fixes where the contract was grounded, tested them on **named disposable databases**
(`poa_b032r_roles`, `poa_b032r_devclone` — a `pg_restore` clone of the real `pofa_dev`), and where an
action is inherently a **live operation** it produced a proven, executable procedure plus the exact
authorization required. No protected database (`pofa_dev`/`pofa_test`) was mutated by BE-032R beyond
the ordinary pytest target (`pofa_test`), and `pofa_dev` was only ever read. The §1 history above is
preserved; the deltas are below. See
`docs/BE-032R Post-Acceptance Remediation and Release-Gate Closure Report.md` and
`docs/BE-032R Operational Runbook - Runtime Roles, Ledger Migration, Restart & Recovery.md`.

| ID | BE-032R status | Implementation / refs | Decision & rationale | Disposable evidence | Remaining live requirement | Exact authorization needed |
| --- | --- | --- | --- | --- | --- | --- |
| **D-CHAIN** | **Resolved-and-verified (policy explicit + tested)** | `services/audit_ledger.py` `LEDGER_WRITER_POLICY="controlled_continuation"`, `writer_policy_statement()`, `verify_chain_classified()`; `services/audit_integrity_baseline.py`; `tests/unit/test_audit_integrity_baseline.py` | Chose **controlled continuation**: D-2-A still refuses appends onto a cryptographically *damaged* tail, and a gapped-but-intact ledger stays writable. No automatic repair/reinsert/renumber (§15). | Classifier + policy unit tests pass; endpoint degrades correctly on a rolled-back mid-chain tamper (`test_be032r_anchored_verification.py`). | None (code + policy are complete). | None — policy is a documented engineering decision; owner only needs to accept it. |
| **F-03** | **Resolved-and-verified** | `GET /api/v1/audit/verify/anchored` (`endpoints/audit_ledger.py`), gated `audit.read`, read-only, optional validated `baseline` param; schemas in `schemas/audit_ledger.py` | Anchor exposed as an authorized read endpoint reusing `require_global("audit.read")` + the existing verify pattern; unknown baseline → 422 (honest, no silent default). | 8 integration tests on `pofa_test` at head green (success shape, degraded-on-tamper, baseline accept/reject, read-only 405). | None. | None. |
| **F-04** | **Resolved-and-verified** | `services/audit_integrity_baseline.py` (`HistoricalGapBaseline`, `classify_findings`, `resolve_baseline`, `EMPTY_BASELINE`, `POFA_DEV_HISTORICAL_BASELINE`); wired into `verify_chain_classified` | Explicit, versioned, **reviewed** baseline registry; default-deny (no baseline ⇒ every gap is *new*); hash mismatch / missing-predecessor never blessable; gap match requires both boundary numbers. | Unit tests cover unchanged-known, new, shifted, hash-mismatch, mixed, baseline-missing; classifier run on the real `pofa_dev` clone data → `known_historical_only`, 7/0/0. | None in code. The `pofa_dev` register values are pinned from BE-030 §6; **re-verify against `pofa_dev` and bump the baseline version** if that register ever changes — a deliberate, traceable act, not automatic. | Owner sign-off that the 7-gap register is the approved historical set (already measured unchanged). |
| **F-05** | **Implemented-not-deployed (proven on disposable)** | `scripts/provision_runtime_roles.sql` (idempotent, password passed out-of-band); runbook §2 | Move app to a **non-owner** `poa_runtime` (SELECT+INSERT only on ledger), separate from `poa_migrator`. A trigger cannot stop `TRUNCATE`; only non-ownership can. | On `poa_b032r_roles` and the `pofa_dev` clone: `insert=t/update=f/delete=f/truncate=f`; append succeeds; UPDATE/DELETE/**TRUNCATE** permission-denied; `SET ROLE postgres` denied; no DDL from runtime. Script re-runs idempotently. | **Live role/ownership change on `pofa_dev`** (and any prod): create roles, reassign ownership, split runtime vs migration `DATABASE_URL`. | Explicit authorization to alter roles/ownership/grants on a live cluster (§2 forbids it on protected DBs in-task). |
| **D-PFD** | **Proven-ready, NOT applied** | runbook §3; migration `t0u1v2w3x030` unchanged | Re-verified the current `pofa_dev` state, restored a fresh `pg_dump` into a disposable clone, applied the real path. Migration re-measures the out-of-domain precondition and aborts with no DDL; refuses double-install. | Clone at `s9t0u1v2w029` (6023 rows/7 gaps) → `upgrade head` → `t0u1v2w3x030`, rows **unchanged**, trigger+function+CHECK present, `known_historical_only` 7/0/0, append onto gap works, `downgrade`→rows kept→`upgrade`→enforcement back. | **Apply to live `pofa_dev`**: fresh backup first, then `alembic upgrade head` under sign-off, then restart (§4). | Explicit authorization to run the migration against `pofa_dev`. |
| **OQ-3** | **Contract grounded — no unsafe change made; product policy remains open** | No code change (intentional). Facts: `models.py:50-60` (`external_subject` nullable, `uq_user_identity_subject` = `(identity_provider, external_subject)`, NULLS DISTINCT); write-only at `services/authorization.py:340`; no read consumer (grep). | Provider-scoped uniqueness + nullability is already safe. Changing `create_user:340` (which assigns a synthetic UUID subject to local users) would break the pinned BE-029 invariant `test_be029_identity_contract.py:266` — **not done**. No `NOT NULL`/unique invention, no backfill (§8/§15). | BE-029 identity-contract tests green on `pofa_test` (provider-scoped, null-permitted, collision, normalization). | Product decision only: adopt (recommended) keep-nullable-and-inert + document that no provider consumes it yet; retire-column/backfill are separate owner-gated migrations. | Owner decision on the eventual external-provider semantics (proposal in BE-032R report §Decision register). |
| **D-RESTART** | **Prepared (procedure), not executed** | runbook §4 | Documented prerequisite checklist, API restart + `/health`·`/ready`·`/healthz`·`/metrics` (readiness builds a *guarded* engine, so the armed-context guard applies), per-worker startup + safe-workload check, JWT secret injection/rotation. Distinguishes disposable vs operational restart. | Health/worker code traced in `app/main.py`, `observability/health.py`, `workers/*.py`; endpoints exercised by suite. | **Operational restart** of live services to load current code + (after D-PFD) enforcement. | Explicit authorization to restart real services (not done in BE-032R). |
| **JWT secret** | **Resolved-and-verified (config-level)** | `backend/core/config.py` `model_validator` (`UNSAFE_JWT_SECRETS`, `MIN_JWT_SECRET_LENGTH=32`); `tests/unit/test_configuration_and_logging.py` | Production/prod mode refuses to construct `Settings` on the `"changeme"`/blank/short secret; dev/staging keep the permissive default; the secret value is never echoed. | Unit tests pass (rejects changeme/empty/short, accepts ≥32-char, dev/staging unaffected, no secret echoed). | Deployment must actually set a distinct `JWT_SECRET` in prod. | Owner/deployment: inject the secret via the deployment store (not committed `.env`). |

**Net for BE-032R:** D-CHAIN, F-03, F-04, JWT are **closed in code and verified**. F-05 and D-PFD are
**fully built and disposable-proven**, awaiting only a separately-approved **live** operation. OQ-3 is
a genuine product-policy decision that must not be manufactured — safe today, no code change. D-RESTART
is an executable procedure awaiting an authorized operational restart. No blocker was relabelled as done
without evidence, and no protected database was mutated beyond `pofa_test`'s normal pytest use.

**Final verification (re-measured 2026-10-11, after the guard fix):** full suite on `pofa_test` =
`821 passed, 1 skipped, 0 failed` (775s, EXIT=0); focused BE-032R + adjacent suites = `81 passed`
(94s). The two prior audit-guard failures were resolved by adding the new sanctioned-tamper test to
`tests/audit_guard.py`'s UPDATE allowlist (DELETE/TRUNCATE stay unconditional). A read-only
`verify_chain_classified` run against the **live** `pofa_dev` returns `known_historical_only`, 7 known / 0
new / 0 hard anomalies (degraded=False). One unrelated latent flake
(`test_evidence_request.py::test_full_lifecycle_to_fulfilled`, random `id` tiebreak in `open_slots[0]`)
passed the final run and is tracked in BE-033 §6.1/§12 — it is not a BE-032R regression (no evidence-request
file was touched). Disposable DBs (`poa_b032r_roles`, `poa_b032r_devclone`) and the `poa_runtime` role were
dropped after verification.

---

## 6. BE-033 live execution reconciliation (2026-10-11)

BE-033 *executed* the two operations BE-032R left gated, against the **live** `pofa_dev`, after
obtaining explicit, scoped owner authorization (the spec §1 premise that F-05 was "already
authorized" was false against the committed record, so genuine authorization was captured first
via a direct decision). Verdict: **REMEDIATION COMPLETE — DEPLOYMENT ACTIONS PENDING**. Full
evidence: `docs/BE-033 Live Enforcement Rollout and Production Readiness Report.md`.

**State vocabulary applied separately (never conflated):**
*Implemented-and-tested-in-code* · *Proven-on-disposable-clone* · *Applied-to-protected-live-DB* ·
*Operationally-verified-against-a-running-service* · *Approved-but-not-executed* ·
*Blocked-by-missing-approval-or-external-deployment-access*.

| ID | Code | Clone | Live `pofa_dev` | Live-app / ops | Remaining action | Owner state |
| --- | --- | --- | --- | --- | --- | --- |
| **D-PFD** | ✓ | ✓ | **✓ applied** (`s9t0u1v2w029`→`t0u1v2w3x030`, 6023 rows intact, enforcement present, UPDATE refused w/o hatch) | app not restarted | none for the migration itself | **AUTHORIZED + DONE** |
| **F-05** | ✓ | ✓ | **✓ role provisioned + privileges verified** (`poa_runtime` non-owner, SELECT+INSERT ledger, UPDATE/DELETE/TRUNCATE/`SET ROLE` denied) | **✗** app `DATABASE_URL` still `postgres` | switch app identity to `poa_runtime` + restart, then live verify | **AUTHORIZED for role; identity-switch HELD** |
| **D-CHAIN** | ✓ | ✓ (via clone tamper) | policy is DB-independent | n/a | none | **ACCEPTED** |
| **F-04** | ✓ | ✓ | register re-verified live `known_historical_only` 7/0/0 | n/a | bump baseline if register ever changes | **ACCEPTED** (7-gap register approved) |
| **F-03** | ✓ | ✓ | endpoint implemented | not polled live | scheduler/poller if desired | implemented (unchanged) |
| **JWT** | ✓ (prod-mode validator) | — | dev keeps permissive non-prod default (correct) | **✗** prod secret not injected | inject distinct ≥32-char secret into the real deployment store | **no prod store here** (external, not executable) |
| **D-RESTART** | procedure ready | — | — | **✗ not performed** | controlled restart + `/health`·`/ready`·`/healthz`·`/metrics`·worker append smoke | **HELD** (dev stays non-production) |
| **OQ-3** | no unsafe change | — | unchanged | — | product decision only | **Open** |

**Integrity before == after (read-only, live `pofa_dev`):** 6023 rows, `status=known_historical_only`,
`degraded=false`, 7 known gaps / 0 new / 0 hard, checkpoint 6023. No event deleted, renumbered,
reconstructed, or fabricated; the 7 gaps stay documented rather than concealed.

**Backup/restore:** fresh pre-change `pg_dump -Fc` → `D:/CODING/Scratch/be033/be033_pofa_dev.dump`
(sha256 `64318c217d523bdf532da9d50f18a81f5e88dd1ad022188d3d618b2b77cf9182`), restored with
`--no-owner` into disposable `poa_b033_clone` (revision + rows matched) and used as the live gate.
Container `archive_mode=off` → recovery is to the snapshot, no true PITR (D-BACKUP unchanged).

**Regression:** focused `81 passed`; full suite `821 passed, 1 skipped, 0 failed` (EXIT=0) on
`pofa_test`. No source file changed by the live ops; the evidence-request ordering flake did not
reproduce and stays a separate deferred item (spec §10 — not expanded here).

**Production NOT cleared** because three deployment actions remain: (1) runtime-identity cutover +
service restart and live health/worker verification, (2) a production deployment-store JWT secret
(no such store exists in this environment), and (3) — optional/non-blocking — the deterministic
ordering fix. Recommended next milestone: **BE-034 Runtime Identity Cutover & Live Service
Verification**.

---

## 7. BE-034 runtime-identity cutover reconciliation (2026-10-11)

BE-034 is the BE-033 §13 follow-up (no dedicated task file; scope owner-confirmed). Per the
owner's chosen execution mode it ran **entirely against a disposable clone** of the *current*
live `pofa_dev` — the real dev stack was **not** repointed and **no** protected database was
modified. Full evidence: `docs/BE-034 Runtime Identity Cutover and Live Service Verification Report.md`.

| Item | BE-034 reached state |
| --- | --- |
| **F-05 runtime identity** | Implemented ✓ · Proven-on-clone ✓ · Applied-to-live-role ✓ (BE-033) · **Operationally-verified-against-a-running-service ✓** on a faithful current clone: fresh `pg_dump -Fc` of live `pofa_dev` (`t0u1v2w3x030`, 6023 rows) → `poa_b034_clone` → `provision_runtime_roles.sql` (`insert=t/update=f/delete=f/truncate=f`) → **uvicorn started as `poa_runtime`** with `/ready` reporting `postgresql` healthy; app-path `append_event` (`ANALYSIS_COMPLETED`, worker `WEBHOOK_DELIVERY_SUCCEEDED`) grew the ledger and classification stayed `known_historical_only` **7/0/0**; direct UPDATE/DELETE/**TRUNCATE**/**SET ROLE postgres** all refused. |
| **F-03 / F-04 anchored endpoint** | Exercised **over HTTP** on the running app: `/api/v1/audit/verify` and `/verify/anchored?baseline=pofa-dev-pre-be030-test-cleanup` → 200 `known_historical_only`, checkpoint present; unknown baseline → **422**. |
| **JWT** | **Config-level only**: production-mode validator **6 passed**; the run used a local non-committed strong secret. **No production deployment store exists here** → no real prod secret injected or claimed. |
| **D-RESTART (live)** | **Not performed on the real stack** — clone-backed process only. Owner kept dev non-production. |

**Six-state classification for F-05 after BE-034:** the runtime-role protection is now
**operationally verified against a running service and worker on a faithful clone of the current
live database**, upgraded from BE-033's "role provisioned but not exercised". It is **not** yet
"the production process cannot TRUNCATE" until the **real** `DATABASE_URL` is repointed to
`poa_runtime` and the live API/workers are restarted — a deployment action, not engineering.

**Safety:** `poa_b034_clone` dropped; container `/tmp` cleared; live `pofa_dev` confirmed still
`rev=t0u1v2w3x030`, `ledger=6023` (probe appends landed only on the clone). Fresh dump retained
outside the repo (`D:/CODING/Scratch/be034/be034_pofa_dev_current.dump`, sha256
`ff8255a9b5d88084953799fe518018c7919adec9015b4efa988ffb13cf2e48d3`). Runtime password passed
out-of-band, never echoed. Focused regression `84 passed`, EXIT 0; no source file changed, so the
BE-033 full-suite `821/1/0` baseline carries.

**Net:** BE-034 verdict = **RUNTIME-IDENTITY PATH OPERATIONALLY VERIFIED — LIVE CUTOVER &
PRODUCTION DEPLOYMENT STILL PENDING**. Production is **not** cleared. Recommended next: a
maintenance-window **live** identity cutover + restart with re-verification against the real
target, paired with a real production JWT secret store.

## 8. BE-035 live development runtime-identity cutover reconciliation (2026-10-11)

BE-035 executed the live cutover BE-034 held: it repointed the **actual** development application
(`.env`, git-ignored) from the owner `postgres` to the non-owner `poa_runtime` and restarted the real
API against live `pofa_dev`. Authorized by the BE-035 task file §1/§2 for the development target only,
after the preflight (A) / role (B) / fresh-backup+restore (C) gates all passed. Full evidence:
`docs/BE-035 Live Runtime-Identity Cutover and Production Deployment Readiness Report.md`.

| Item | BE-035 reached state (six distinct statuses kept apart) |
| --- | --- |
| **F-05 runtime identity** | Implemented ✓ · Proven-on-clone ✓ (BE-034) · **Applied-to-live-dev ✓** (`.env` DATABASE_URL → `poa_runtime`; app connection verified as `poa_runtime` by `pg_stat_activity`, no owner fallback) · **Verified-against-a-running-service ✓** (real uvicorn on live `pofa_dev`; `/ready` postgresql+redis+storage healthy; live anchored endpoint `known_historical_only` 7/0/0) · Configured-in-production ✗ · **PENDING: production.** |
| **Append-only enforcement** | On the faithful disposable clone as `poa_runtime`: app-path `append_event` OK (seq 6060/6061); `UPDATE`/`DELETE`/`TRUNCATE`/`SET ROLE postgres` **DENIED** (permission layer); ordinary-table write **PERMITTED**. Live `pofa_dev` re-read after milestone: `rev=t0u1v2w3x030`, **ledger=6023 unchanged** (clone writes never touched it). |
| **F-03 / F-04** | `GET /api/v1/audit/verify/anchored` exercised over the **live** `poa_runtime` API: known baseline → `known_historical_only` (7 gaps reported, not concealed); no baseline → default-deny still reports the 7. No new API surface added. |
| **JWT** | **Config-level only**: production validator rejects `changeme`/empty/`<32`, accepts valid, canary secret **not** leaked in the error; dev/staging permissive. **No production deployment target or secret store exists here** → no real prod secret injected or claimed. |
| **D-RESTART** | **Development performed + verified** (real API restarted as `poa_runtime`, 6 endpoints 200). `analysis`/`notification`/`retention` workers import and share the `poa_runtime` engine. **webhook worker not runnable** — see BE-035-D1. **Production restart + runtime identity pending (external).** |
| **BE-035-D1 (new finding)** | `webhook_worker.py` `ImportError` on a non-existent `SessionLocal`; pre-existing, independent of the cutover. Reported, **not fixed** (out of operational-cutover scope) → owner decision. |

**Recovery:** original owner config preserved outside the repo
(`D:/CODING/Scratch/be035/env.owner.backup`); recovery = restore `.env` and restart. Fresh recovery
point `D:/CODING/Scratch/be035/be035_pofa_dev_current.dump` (1,778,724 B, sha256
`f9583a51d199ec06a24f7c69036ca7a615c7d38d3fac7f3fcef5224abd26aeae`, distinct from BE-034's
`ff8255a9…` → genuinely fresh), restore-verified into `poa_b035_restore` (rev/ledger/trigger/function/
CHECK/users all matched), then dropped. `archive_mode=off` → dump is a consistent snapshot, **not** PITR.
Runtime password passed out-of-band, never echoed. Regression on `pofa_test`: **168 passed, 0 failed**.

**Net:** BE-035 verdict = **DEVELOPMENT RUNTIME CUTOVER VERIFIED — PRODUCTION DEPLOYMENT PENDING**.
Production is **not** cleared. Remaining external actions: identify a production target, stand up a
production JWT secret store (distinct ≥32-char secret), configure the production runtime identity as
`poa_runtime` with runtime/migration `DATABASE_URL` secrets split, and run production health + integrity
checks. Separately, **BE-035-D1** (webhook-worker startup defect) — owner **DEFERRED** the fix (documented,
not applied in BE-035) pending a narrow follow-up milestone.

---

## 9. BE-036 webhook-worker reliability reconciliation (2026-10-11)

BE-036 is the narrow follow-up the §8 BE-035 snapshot anticipated ("deferred to a narrow follow-up
milestone"). It is **reliability only** — no production deployment, no repo-wide refactor, no change to
the BE-035 report above (its rows are the historical BE-035 disposition and are left intact).

**BE-035-D1 is CLOSED.** The six-state status was advanced honestly, not collapsed into "done":

| Gate | State after BE-036 |
| --- | --- |
| Root cause | **Confirmed** — `webhook_worker.py` imported/called a bare `SessionLocal` that `backend/db/session.py` does not export (only `get_session`, with a private `_SessionLocal`). Reproduced as `ImportError: cannot import name 'SessionLocal'`. The other three workers already used `get_session()`; a repo grep confirmed `SessionLocal` (bare) appeared **only** in this worker. |
| Fix | **Implemented** — swap to `from backend.db.session import get_session`; `db = get_session()` at both call sites (`run_worker_once`, `__main__`). No public-interface, auth, transaction, retry, timeout, audit or append-only behavior changed. No new dependency. |
| Unit-tested / integration-tested | **Yes** — `tests/integration/test_be036_webhook_worker.py` (10 tests) drives the real sweeps/`_attempt_delivery`/`_fanout_event` with `urlopen` mocked and `getaddrinfo` stubbed (deterministic, DNS-free). |
| Verified through actual worker startup | **Yes** — module imports; `python -m backend.workers.webhook_worker --help` runs; `get_session()` opens a **`poa_runtime`** session and closes cleanly. The entry-point fix itself is pinned by `test_run_worker_once_uses_fixed_session_and_closes_cleanly`. |
| Delivery correctness (no real egress) | **Yes** — success→DELIVERED (failure counter reset), connection-error/5xx→RETRYING (future `next_attempt_at`), 4xx & exhausted-attempts & SSRF→FAILED (no retry), disabled-subscription→DISABLED, auto-disable after 10 consecutive failures, fanout idempotent, a completed delivery is never re-processed, every outcome appends exactly one `WEBHOOK_DELIVERY_*` ledger row via the real `append_event`. SSRF and disabled-subscription cases assert **zero** `urlopen` calls; no real webhook was sent. |
| Regression | **Yes** — full backend suite **831 passed / 1 skipped / 0 failed** on `pofa_test` (EXIT 0), up from the BE-033 `821/1/0` baseline by exactly the 10 new tests; no security assertion weakened; protected DBs untouched (all writes confined to `pofa_test`). |

**A deliberate verification boundary:** the worker was **not** run as a live daemon performing real outbound
delivery against `pofa_dev` (§2 external-side-effect rule — "never invoke a real outbound webhook merely to
prove that a worker starts"). Startup, `poa_runtime` session acquisition, clean shutdown, and the full
delivery/retry/audit lifecycle were verified through the launch path plus mocked-egress integration tests.

**New finding deferred to a follow-up milestone — BE-036-D1** (see §1): `urllib.request.urlopen` follows
HTTP 3xx redirects, contradicting the "never follow redirects" SSRF guarantee. Pre-existing, not caused by
the import defect, and its fix needs a redirect-free opener + tests, so it is documented rather than folded
into BE-036.

**Net:** BE-036 verdict = **BE-035-D1 CLOSED — WORKER VERIFIED**. Production deployment remains **outside
this milestone** and **NOT CLEARED** (see §8: no production target/secret store yet).
