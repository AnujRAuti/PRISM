# BE-033 — Live Enforcement Rollout, Operational Verification & Production Readiness

**Date:** 2026-10-11
**Milestone:** BE-033 (execution milestone; follows BE-032R, whose disposition was
REMEDIATION COMPLETE — OPERATIONAL GATES PENDING)
**Branch / HEAD at start:** `Backend` / `d5685abf`
**Verdict:** **REMEDIATION COMPLETE — DEPLOYMENT ACTIONS PENDING**
**Production clearance:** **NOT granted** (deployment-store secret, application-identity
switch to the runtime role, and a live service restart remain outstanding — see §9).

This milestone *executes* the two operations BE-032R built and disposable-proved but left
gated (F-05 runtime role, D-PFD enforcement migration), against the **live** `pofa_dev`, and
verifies them independently. It is not an assessment-only document.

---

## 1. Scope reconciliation against BE-032R

BE-032R's premise, carried into the BE-033 spec §1, was "the F-05 runtime-role and ownership
change is authorized." Re-checked against the committed record (backlog §1, BE-032R report,
decision register), **no such authorization existed** — F-05 and D-PFD were both still marked
`Blocked-by-owner-decision` / "Explicit authorization needed". The spec's own §1/§3 forbid
inferring live authority from the general goal of finishing BE-033.

Therefore, before any live write, explicit owner authorization was obtained (project owner:
AnujRAuti) via a direct decision:

| Decision | Owner disposition | Date |
| --- | --- | --- |
| F-05 live role/privilege provisioning on `pofa_dev` | **AUTHORIZED** (create `poa_runtime`, grant-scoped, live) | 2026-10-11 |
| D-PFD live enforcement migration `pofa_dev → t0u1v2w3x030` | **AUTHORIZED** (after backup + restore-to-clone gate) | 2026-10-11 |
| D-CHAIN `controlled_continuation` writer policy | **ACCEPTED** | 2026-10-11 |
| F-04 seven-gap historical register (`pofa-dev-pre-be030-test-cleanup` v1) | **ACCEPTED** as the approved baseline | 2026-10-11 |
| D-RESTART — start/restart real services + switch app `DATABASE_URL` to `poa_runtime` | **HELD** — dev stays non-production; do not start services | 2026-10-11 |
| JWT production secret injection into a deployment store | **HELD** — no production deployment store exists in this environment | 2026-10-11 |

The F-05 / D-PFD authorizations and the D-CHAIN / F-04 acceptances are genuine, scoped,
recorded owner calls — not inferred. The two HELD items are the sole reason production is not
cleared; both require an environment/deployment action the owner explicitly declined to take
this milestone.

---

## 2. Execution timeline (all live actions)

All timestamps 2026-10-11. Protected-DB rule: only `pofa_dev` was written; `pofa_test` was used
solely as the pytest target; every destructive experiment ran on a **named disposable**
database (`poa_b033_clone`).

1. **Preflight / revalidation** (read-only `pofa_dev`): rev=`s9t0u1v2w029`→ confirmed prior
   reported pre-migration state; ledger=6023 rows; both DBs connect as owner `postgres`.
   Containers `pofa_db`/`pofa_redis` up.
2. **Backup** `pofa_dev` (pre-change) via in-container `pg_dump -Fc` → host
   `D:/CODING/Scratch/be033/be033_pofa_dev.dump`.
   SHA-256 `64318c217d523bdf532da9d50f18a81f5e88dd1ad022188d3d618b2b77cf9182`.
3. **Restore-to-disposable proof**: `pg_restore --no-owner` of that exact dump into
   `poa_b033_clone`; row count and revision confirmed to match the live pre-change state.
4. **Clone migration + role proof**: `alembic upgrade head` on the clone →
   `t0u1v2w3x030`; `provision_runtime_roles.sql` applied to the clone; `poa_runtime` append
   verified (ledger grows), UPDATE/DELETE/**TRUNCATE**/**SET ROLE postgres** denied, ledger
   CHECK refused an out-of-domain `USER_LOGIN` append (defense-in-depth evidence).
5. **D-PFD live migration**: with the gate satisfied, `alembic upgrade head` on **live
   `pofa_dev`** → `s9t0u1v2w029` → `t0u1v2w3x030` (~2s). No downgrade used as rollback.
6. **F-05 live provisioning**: `provision_runtime_roles.sql` applied to **live `pofa_dev`** as
   owner `postgres`, runtime password supplied out-of-band (never echoed; stored in scratch
   outside the repo). Self-check returned `insert=t | update=f | delete=f | truncate=f`.
7. **Post-change verification** (live `pofa_dev`, read-only): revision, enforcement objects,
   privileges, denials, and `verify_chain_classified` (see §4/§5).
8. **Regression**: focused suites (81 passed) + full suite (821 passed / 1 skipped / 0 failed)
   — run against `pofa_test`, with **no** source or `pofa_test` schema change caused by the
   live ops.
9. **Cleanup**: dropped `poa_b033_clone`, cleared container `/tmp`. Dump + runtime password
   retained outside the repo.

---

## 3. F-05 — live runtime-role / privilege outcome (APPLIED TO PROTECTED LIVE `pofa_dev`)

`scripts/provision_runtime_roles.sql` was reviewed before use: it is idempotent, takes the
password only via the `:runtime_password` psql variable (refuses to create an open role if
unset), grants `poa_runtime` `USAGE` on the schema, full DML on ordinary tables,
**SELECT+INSERT only** on `audit_ledger_events`, and `USAGE/SELECT` on sequences. It does not
grant ownership and does not create `poa_migrator` (the current deployment keeps `postgres` as
the single owner/migration identity; the runtime/migration *separation* is the privilege model,
not a second role file).

**Measured on live `pofa_dev` after applying (re-verified at report time):**

| Probe | Result | Meaning |
| --- | --- | --- |
| `poa_runtime` exists, `rolsuper` | `true` / `false` | non-superuser login role |
| `pg_get_userbyid(audit_ledger_events.relowner)` | `postgres` | runtime role is **NOT** the table owner |
| `has_table_privilege(... 'INSERT')` | `true` | authorized appends permitted |
| `has_table_privilege(... 'UPDATE')` | `false` | historical mutation denied at permission layer |
| `has_table_privilege(... 'delete')` | `false` | deletion denied |
| `has_table_privilege(... 'TRUNCATE')` | `false` | **the F-05 silent-reset hole is closed** for this identity |
| `SET ROLE postgres` as `poa_runtime` | `permission denied to set role` (clone-proven) | cannot escalate to owner |
| `TRUNCATE audit_ledger_events` as `poa_runtime` | `permission denied` (clone-proven) | ownership requirement enforced |

**Why this closes the trigger gap:** BE-030's `trg_audit_ledger_append_only` is a
`FOR EACH ROW` trigger and does **not** fire on `TRUNCATE`. Only removing table ownership from
the runtime connection makes `TRUNCATE` fail (it requires ownership). `poa_runtime` lacks
ownership, so the ledger cannot be silently wiped and re-baselined by the application identity.

**Honest caveat (the pending action):** the live application `.env` `DATABASE_URL` still points
at the owner identity (`postgres`), **not** `poa_runtime`. The role and its protections now
exist and are verified on `pofa_dev`, but they only guard the running application once its
connection is switched to `poa_runtime` and the service is restarted. That switch was **HELD**
by the owner this milestone (§1). F-05 is therefore **APPLIED-TO-LIVE / role-proven**, not yet
**operationally wired into the app**.

---

## 4. D-PFD — live enforcement migration outcome (APPLIED TO PROTECTED LIVE `pofa_dev`)

`alembic upgrade head` was run against **live `pofa_dev` only** using the owner/migration
identity.

**Measured (re-verified at report time):**

| Check | Value |
| --- | --- |
| `alembic_version.version_num` | `t0u1v2w3x030` (was `s9t0u1v2w029`) |
| `audit_ledger_events` row count | `6023` — unchanged across the migration |
| `trg_audit_ledger_append_only` present | `1` |
| `audit_ledger_refuse_mutation` present | `1` |
| `ck_audit_ledger_event_type_domain` present | `1` |
| `UPDATE ... SET payload='{}'` on the ledger (as owner, **no** hatch GUC) | `ERROR: append-only enforcement refuses UPDATE on the audit ledger` |

The migration reached the intended head, existing events are intact, and enforcement behaves as
designed on the live database. No live downgrade was used.

---

## 5. Ledger integrity before and after (no fabrication, read-only)

`verify_chain_classified(db, "pofa-dev-pre-be030-test-cleanup")` on **live `pofa_dev`**,
read-only, re-verified at report time:

| Field | Before (pre-migration, read-only) | After (post-migration + role) |
| --- | --- | --- |
| row count | 6023 | 6023 |
| `status` | `known_historical_only` | `known_historical_only` |
| `valid` | `false` (chain has historical gaps) | `false` |
| `degraded` | `false` | `false` |
| known historical gaps | 7 | 7 |
| new gaps | 0 | 0 |
| hard anomalies (hash mismatch / missing predecessor) | 0 | 0 |
| checkpoint rows | 6023 | 6023 |

The seven historical gap ranges remain present, preserved, and correctly classified as
**known_historical**; no event was deleted, renumbered, reconstructed, or edited to make the
chain look clean; no new unexplained anomaly was introduced. `valid=false` is the honest,
expected result for this register (a gapped-but-intact tail) and is exactly what the accepted
D-CHAIN `controlled_continuation` policy is designed to coexist with.

---

## 6. D-CHAIN and F-04 decision status

- **D-CHAIN:** `LEDGER_WRITER_POLICY="controlled_continuation"` (`services/audit_ledger.py`).
  Owner **ACCEPTED** 2026-10-11. D-2-A still refuses appends onto a cryptographically *damaged*
  tail; a gapped-but-intact ledger stays writable; no automatic repair/renumber.
- **F-04:** `services/audit_integrity_baseline.py`, registry baseline
  `POFA_DEV_HISTORICAL_BASELINE` (name `pofa-dev-pre-be030-test-cleanup`, v1, 7 gaps), default
  deny (`EMPTY_BASELINE` blesses nothing; unknown baseline → HTTP 422). Owner **ACCEPTED** the
  7-gap register as the approved historical set 2026-10-11. This resolves the BE-032R report's
  internal inconsistency (accepted in one section, "open" in another): it is now **accepted**.

Both corrections are reflected in the backlog §1 (see §8).

---

## 7. API, workers, health, JWT — deployment-pending state

Per the owner **HELD** decision ("dev stays non-production; do not start services"), **no real
service was started or restarted**, and the application `DATABASE_URL` was **not** switched to
`poa_runtime`. Consequently:

- `/health`, `/ready`, `/healthz`, `/metrics` were **not** exercised against a live running
  service this milestone. They are implemented (`observability/health.py`, `app/main.py`) and
  covered by the suite, but BE-033 does not claim a live operational check that did not occur.
- Workers were **not** started; no live append-through-the-app smoke test was performed. No
  production business event was fabricated for demonstration (§ spec §7).
- **JWT:** the production-mode validator (`core/config.py`: rejects `"changeme"`/blank/short
  (<32) secrets, never echoing the value) is code-verified and tested. A **distinct production
  secret has NOT been injected into a deployment store** — no production deployment store exists
  in this environment, and dev `pofa_dev` intentionally keeps the permissive non-production
  default. This is stated precisely, not glossed: application-side validation ≠ deployment
  secret configured.

These three — runtime-identity switch + restart, live health/worker verification, and the
production secret — are the outstanding deployment actions behind the verdict.

---

## 8. Exact test commands and results

Interpreter: `backend/.venv312_repro/Scripts/python.exe`. Test DB target: `pofa_test`
(via `TEST_DATABASE_URL`; never `pofa_dev`). No source change and no live-ops-induced
`pofa_test` schema change.

```
# Focused: DB safety, role/ledger enforcement, chain classification, anchored endpoint,
# audit guard, config/JWT
backend/.venv312_repro/Scripts/python.exe -m pytest \
  tests/unit/test_audit_integrity_baseline.py \
  tests/integration/test_be032r_anchored_verification.py \
  tests/integration/test_be030_enforcement.py \
  tests/test_audit_guard.py \
  tests/unit/test_configuration_and_logging.py \
  tests/unit/test_migrations.py
# => 81 passed

# Full suite
backend/.venv312_repro/Scripts/python.exe -m pytest
# => 821 passed, 1 skipped, 0 failed in 782.6s (EXIT=0)
```

Matches the BE-032R baseline (821/1/0). The single skip is the pre-existing ML-stack preflight
skip. The BE-032R evidence-request ordering flake was **not** reproduced in this run; it
remains a separate, non-release-critical carry-over (see §9).

---

## 9. Backlog / report state classification (the six distinct states)

| ID | State reached this milestone |
| --- | --- |
| **F-05** | Implemented-and-tested-in-code ✓ · Proven-on-disposable-clone ✓ · **Applied-to-protected-live-DB ✓** · Operationally-wired-into-app ✗ (HELD) — pending identity switch + restart |
| **D-PFD** | Implemented-and-tested-in-code ✓ · Proven-on-disposable-clone ✓ · **Applied-to-protected-live-DB ✓** · Operationally-verified-via-live-app ✗ (HELD) |
| **D-CHAIN** | **Owner-ACCEPTED** policy; implemented + tested |
| **F-04** | **Owner-ACCEPTED** 7-gap register; implemented + tested |
| **F-03** | Implemented + tested (unchanged from BE-032R) |
| **JWT validation** | Implemented + tested · **deployment secret injection: Approved-but-not-executable here (no prod store)** — precise remaining action stated |
| **D-RESTART / runtime-identity switch** | Procedure ready · **Approved-HELD by owner, not executed** |
| **OQ-3** | Unchanged: contract-safe today, product policy still open (no unsafe change) |
| **evidence-request flake** | Not reproduced; **deferred** as a separate deterministic-ordering task (not expanded here per spec §10) |

---

## 10. Backup and restore evidence

- Dump: `D:/CODING/Scratch/be033/be033_pofa_dev.dump` (custom-format `pg_dump`, pre-change
  `pofa_dev`, 1,755,944 bytes).
- SHA-256: `64318c217d523bdf532da9d50f18a81f5e88dd1ad022188d3d618b2b77cf9182`.
- Restore proof: `pg_restore --no-owner` into disposable `poa_b033_clone`; revision and
  ledger row count matched the live pre-change state; the clone then passed the migration and
  role verification used as the live gate. The **actual current** pre-change state was dumped
  (not a historical BE-029 dump).
- Recovery path: restore the dump into a fresh disposable to roll forward, or, if a live revert
  were ever required, restore into a new database and repoint `DATABASE_URL` — **not** a live
  downgrade of the protected DB. Container `pofa_db` runs `archive_mode=off` (no true PITR);
  recovery is to the dump snapshot (unchanged fact from BE-029 G3 / D-BACKUP).

---

## 11. Actions NOT executed and why

1. **Switch app `DATABASE_URL` to `poa_runtime` + restart services** — HELD by owner (dev stays
   non-production; do not start services). Role exists and is verified but not yet the running
   app identity.
2. **Live `/health`·`/ready`·`/healthz`·`/metrics` and worker append smoke** — depends on (1);
   not claimed.
3. **Inject a distinct production JWT secret into a deployment store** — no production
   deployment store exists in this environment; only config-level validation is verifiable here.
4. **Live downgrade / reset of `pofa_dev`** — intentionally not performed (barred).
5. **evidence-request deterministic-ordering fix** — deferred (separate task; not a release
   blocker; not reproduced this run).

---

## 12. Final gates (§14 disposition)

### Live database
- [x] Runtime role is non-owner and correctly restricted (`postgres` owns ledger; `poa_runtime`
      is non-super, SELECT+INSERT only).
- [x] `TRUNCATE` and unauthorized historical mutation are **denied** to the runtime identity
      (privilege check + clone-proven denials).
- [x] The intended enforcement migration (`t0u1v2w3x030`) **applied to live `pofa_dev`**.
- [x] Schema is at the expected revision.
- [x] The seven historical gaps remain preserved and honestly classified (`known_historical_only`
      7/0/0, `degraded=false`).
- [x] No unexplained new integrity anomalies.
- [x] Backup and restore evidence valid for the actual pre-change DB state.

### Operational readiness
- [ ] API healthy/ready **live** — services not started (owner HELD).
- [ ] Workers running **live** — not started (HELD).
- [~] Runtime vs migration credentials separated **at the role layer** (done); the running app
      still uses the owner identity (identity switch HELD) → not yet operationally separated.
- [ ] Production secret verified in a deployment store — no store here; only config-level
      validation passes.
- [ ] Operational/recovery procedures reflect a running deployed config — restart procedure is
      written but unexercised live.

### Application quality
- [x] Focused tests pass (81).
- [x] Full suite passes (821/1/0).
- [x] No new schema or authorization regression.
- [x] Backlog and this report accurately represent the evidence.

### Verdict

**REMEDIATION COMPLETE — DEPLOYMENT ACTIONS PENDING.**

Code and test work is complete; F-05 and D-PFD are now *applied to the live protected
`pofa_dev`* and independently verified with historical integrity preserved. Production is **not**
cleared because the runtime-identity switch + service restart, live health/worker verification,
and a production deployment-store JWT secret are outstanding — the first two by explicit owner
hold, the last because no production deployment store exists in this environment.

---

## 13. Next milestone recommendation

BE-033 has genuinely executed the previously-gated live operations. A follow-up
(**BE-034 — Runtime Identity Cutover & Live Service Verification**, recommended) should:

1. Switch the running application's `DATABASE_URL` to `poa_runtime`, restart API + workers in a
   controlled window, and verify `/health`·`/ready`·`/healthz`·`/metrics` and a real
   append-then-read-back through the app under the runtime identity (closing the F-05 →
   operationally-wired gap).
2. Provide/verify the production JWT secret mechanism for whatever the real deployment store is,
   and confirm no weak fallback.
3. (Optional, non-blocking) Land the evidence-request deterministic-ordering fix as its own
   small, isolated change.

Not recommended: re-running BE-032R/BE-033 verification (already evidenced) or expanding into
unrelated refactoring.
