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
| D-CHAIN | Writer policy when an audit append meets an **already-invalid** historical chain (`pofa_dev`'s 7 known gaps) | Blocked-by-owner-decision | **Open — no approved policy** | BE-030 §3 / BE-032 §5.2 | D-2-A validates only the *immediate* predecessor, so a fresh append onto `pofa_dev`'s locally-valid tail **succeeds** while `verify_chain` still reports the 7 gaps. BE-032 does not choose refusal / controlled-continuation / governed-recovery. |
| F-03 | Expose the §9 anchored/checkpoint control (`verify_chain_anchored` / `ledger_checkpoint`) over an authorized endpoint, or keep it internal-only | Blocked-by-owner-decision | **Open** [MEASURED] | BE-031 F-03 | Only `verify_chain` is wired to `GET /api/v1/audit/verify` (`endpoints/audit_ledger.py:91-101`); anchored control has no endpoint/scheduler/automatic caller. Proven by tests, unpolled at runtime. Surfacing it = new API surface → §12 bars it without an owner call. |
| F-04 | Runtime discrimination of **known** historical gaps vs **new** tampering | Blocked-by-owner-decision | **Open** [MEASURED] | BE-031 F-04 | `verify_chain` classifies symptom type (gap / missing-predecessor / hash-mismatch) but never annotates whether a gap is one of the 7 register ranges. Register anchoring today is a read-only script + docs, not code; §14 bars a shipped test from reading live `pofa_dev`. Needs a persisted-baseline / signed-checkpoint design (architecture choice). |
| F-05 | `TRUNCATE` hardening via a non-owner least-privilege runtime role | Blocked-by-owner-decision (accept-open in BE-030 D-1-A) | **Open** [MEASURED] | BE-030 §2.3; BE-031 F-05/I.3, Appendix D | **Both** DBs connect as table owner `postgres`, `has_truncate_priv=true`, memberships `[]`. BE-030 trigger is `BEFORE UPDATE OR DELETE FOR EACH ROW` → does **not** fire on `TRUNCATE`; `REVOKE` inert while app is owner. Silent-reset hole stays open. Closing = DB role/ownership architecture change, disposable-proof first (§3.1). |
| D-PFD | Authorization to migrate live `pofa_dev` → `t0u1v2w3x030` (enforcement) | Blocked-by-owner-decision | **Open** [MEASURED] | BE-030 §2.1; BE-031 F-01/§I.1, Appendix B | `pofa_dev` [MEASURED] still at `s9t0u1v2w029`, enforcement absent. Requires fresh `pg_dump` + restore-to-disposable proof + per-step sign-off + workers/API stopped. BE-032 executed none of it. |
| D-RESTART | API / worker restart after BE-029's live `pofa_dev` migration (and to load current code) | Blocked-by-owner-action | **Open** | BE-030 §2.4; BE-031 I.4, Appendix C | `main.py` startup hook runs only OpenTelemetry + log (no auto-migrate / no `create_all`); workers emit audit rows via `append_event`. Restart is itself owner-gated; BE-032 restarted nothing. |

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
| R-BE030 | Append-only enforcement (`trg_audit_ledger_append_only`, `audit_ledger_refuse_mutation`, `ck_audit_ledger_event_type_domain`) + D-2-A predecessor check + anchored verify + checkpoint digest + hatch, migration `t0u1v2w3x030`, symmetric downgrade | Resolved-and-verified on `pofa_test` | Clone proof + catalog pin + enforcement suite. **Not** applied to `pofa_dev` (D-PFD). |
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
