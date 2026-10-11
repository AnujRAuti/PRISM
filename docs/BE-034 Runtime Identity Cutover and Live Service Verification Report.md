# BE-034 — Runtime Identity Cutover & Live Service Verification

**Date:** 2026-10-11
**Follows:** BE-033 (verdict REMEDIATION COMPLETE — DEPLOYMENT ACTIONS PENDING)
**Branch / HEAD at start:** `Backend` / `d5685abf`
**Verdict:** **RUNTIME-IDENTITY PATH OPERATIONALLY VERIFIED — LIVE CUTOVER & PRODUCTION DEPLOYMENT STILL PENDING**
**Production clearance:** **NOT granted** (no production deployment store exists in this
environment; the live dev stack has not been switched off the owner identity).

## 0. Scope origin and authorization

There is **no BE-034 task file** in `docs/Production Task Files/`; this milestone is the
follow-up BE-033 §13 recommended. Its scope was confirmed with the project owner before any
live write. The owner chose the conservative execution mode:

| Question | Owner decision (2026-10-11) |
| --- | --- |
| Cutover target | **Disposable clone** — restore a *fresh* dump of the current live `pofa_dev`, provision `poa_runtime`, run the API + a worker against it. **No changes to live `pofa_dev`; the host dev stack was not switched or restarted.** |
| JWT | **Config-level only** — re-prove the production-mode validator; state plainly that no production deployment store exists here. Do not claim a prod secret was injected. |
| Ledger append smoke | **App-driven append via the application's own code path** (`append_event`, the function every endpoint/worker calls) — never a hand-fabricated SQL `INSERT`. |

This lifts the BE-033 "do not start services" hold **only for a disposable clone**, not for the
protected `pofa_dev`.

## 1. Environment discovery (recon)

- `docker-compose.yml` provisions **infrastructure only** (`pofa_db`, `pofa_minio`, `pofa_redis`).
  The API (`backend/app/main.py`, uvicorn) and the four workers (`backend/workers/*.py`) run on
  the **host**. "Restart" therefore means host process lifecycle, not containers.
- App startup (`@app.on_event("startup")`) runs **only** OpenTelemetry init + a log line — no
  `create_all`, no auto-migrate — so pointing the app at a database cannot alter schema.
- `get_engine()` → `build_guarded_engine(settings.database_url)`. The armed-context guard is
  **inert** for a normal (non-`pytest`) process, so a runtime-identity app connects without the
  test guard interfering.
- Health surface: `/api/v1/health` (static), `/api/v1/ready` (`SELECT 1`), observability
  `/health` (liveness), `/ready` (readiness: postgresql+redis+storage via a **guarded** engine),
  `/healthz` (combined), `/metrics` (Prometheus).

## 2. Disposable clone build (current-state faithful)

The BE-033 backup predated the enforcement migration (`s9t0u1v2w029`, **0** enforcement objects),
so it was **not** suitable for testing the *current* deployed protection. A fresh dump was taken
from the **live** `pofa_dev` (read-only `pg_dump -Fc`) and restored into `poa_b034_clone`:

| Artifact | Value |
| --- | --- |
| Dump | `D:/CODING/Scratch/be034/be034_pofa_dev_current.dump` (1,778,724 bytes) |
| SHA-256 | `ff8255a9b5d88084953799fe518018c7919adec9015b4efa988ffb13cf2e48d3` |
| Restore | `pg_restore -U postgres --no-owner --exit-on-error` → `RESTORE_EXIT=0` |
| Clone verified state | `rev=t0u1v2w3x030`, `ledger=6023`, append trigger=1, refuse fn=1, event-type CHECK=1, ledger owner=`postgres` |

`provision_runtime_roles.sql` was applied to the clone (table grants are per-database).
Self-check: `insert_ok=t | update_ok=f | delete_ok=f | truncate_ok=f`.

## 3. Runtime-identity privilege verification (as `poa_runtime`, on the clone)

| Probe | Result |
| --- | --- |
| `has_table_privilege('poa_runtime','audit_ledger_events', …)` | `ins=true upd=false del=false trunc=false` |
| `SELECT current_user` / read ledger | `poa_runtime` / 6023 rows readable |
| `UPDATE audit_ledger_events …` | **`permission denied for table audit_ledger_events`** |
| `DELETE …` | **`permission denied`** |
| `TRUNCATE audit_ledger_events` | **`permission denied`** |
| `SET ROLE postgres` | **`permission denied to set role "postgres"`** |

This is the F-05 guarantee held against the **live, running** application path (§5), not a
static grant check.

## 4. JWT — config-level proof

`tests/unit/test_configuration_and_logging.py` (production-mode validator): **6 passed**.
`Settings` construction with `environment=production/prod` refuses `""`, `"changeme"`, and any
secret `< 32` chars; the secret value is never echoed; dev/staging keep the permissive default.
For the verification run the server was started with a locally-set, non-committed strong secret
to confirm a compliant secret lets the service start. **No production deployment store exists in
this environment**, so no real prod secret injection was performed or claimed.

## 5. Live running service as `poa_runtime` — health + endpoint evidence

`uvicorn backend.app.main:app` was started with `DATABASE_URL=…poa_runtime@…/poa_b034_clone`
(`ENVIRONMENT=development`, `AUTH_MODE=development`). It booted cleanly (no schema change, no
errors). Probes:

| Endpoint | HTTP | Meaning |
| --- | --- | --- |
| `/api/v1/health` | 200 | static ok |
| `/api/v1/ready` | 200 `{"status":"ok"}` | `SELECT 1` succeeds as `poa_runtime` |
| `/health` (obs liveness) | 200 `healthy` | process alive |
| `/ready` (obs readiness) | 200 | **postgresql healthy, redis healthy, storage healthy** — the live app connected to the clone **as `poa_runtime`** and passed required-dep checks |
| `/healthz` | 200 `healthy` | combined snapshot healthy |
| `/metrics` | 200 | Prometheus exposition present |
| `/api/v1/audit/verify` | 200 | `valid=false`, **6025** events, last seq 6061, exactly the **7 known historical gaps**, 0 hash mismatches |
| `/api/v1/audit/verify/anchored?baseline=pofa-dev-pre-be030-test-cleanup` | 200 | `classification.status=known_historical_only`, `degraded=false`, checkpoint rows 6025 |
| `/api/v1/audit/verify/anchored?baseline=BOGUS` | 422 | unknown baseline honestly rejected (registered: `none`, `pofa-dev-pre-be030-test-cleanup`) |

## 6. App-driven append through the runtime identity (`append_event`)

A scratch probe invoked the application's own `services.audit_ledger.append_event` (the shared
path every endpoint/worker uses) with a process bound to the clone as `poa_runtime`:

- `ANALYSIS_COMPLETED` → seq **6060**, `6023 → 6024`; re-run → seq **6061**, `→ 6025`.
- `WEBHOOK_DELIVERY_SUCCEEDED` (the worker's audit type) → seq **6062**, `→ 6026`; the worker's
  delivery-status table `webhook_deliveries` is writable by `poa_runtime` (`insert=true update=true`).
- Read-back of the appended rows succeeded; `verify_chain_classified` returned
  **`known_historical_only`, degraded=false, 7 known / 0 new / 0 hard** after every append — i.e.
  a legitimate append under the restricted identity chains onto the valid tail and introduces **no
  new integrity anomaly** (D-CHAIN `controlled_continuation` behaves exactly as documented).
- A direct `UPDATE audit_ledger_events …` through the same runtime session → **refused
  (`psycopg2.errors.InsufficientPrivilege: permission denied`)**.

No production business event was fabricated: the appends are on a **disposable clone** and use the
application's real append code path, and the events are marked as BE-034 probes in their payload.

## 7. Regression

No source file was modified this milestone (docs + disposable DB operations only). Focused
enforcement/anchored/integrity/guard/config/migration suites on `pofa_test` (via
`TEST_DATABASE_URL`): **84 passed**, EXIT 0. The BE-033 full-suite baseline (821/1/0) therefore
carries unchanged.

## 8. State classification (six-state discipline)

| Item | Reached state |
| --- | --- |
| F-05 runtime-identity model | Implemented ✓ · Proven-on-clone ✓ · Applied-to-live-`pofa_dev`-role ✓ (BE-033) · **Operationally-verified-against-a-running-service ✓ (on a faithful current clone)** — but the **live dev/production stack is not yet pointed at `poa_runtime`** |
| D-CHAIN controlled continuation | Verified live-through-app on clone (append onto gapped tail works, classifier holds 7/0/0) |
| F-03 / F-04 anchored endpoint | Verified over HTTP on the running app (200 classified; 422 on unknown baseline) |
| JWT | Config-level validator verified; **production store injection: not executable here (external/absent)** |
| Live cutover of the real `pofa_dev` app + worker restart | **Not performed** (owner chose clone-only) |

## 9. What remains (the pending deployment actions)

1. **Real cutover:** set the running application's `DATABASE_URL` to `poa_runtime` for the actual
   dev/production deployment and restart API + workers in a maintenance window, then re-run §5/§6
   against the live target. This is the one step that converts "proven on a faithful clone" into
   "the production process cannot `TRUNCATE` the ledger."
2. **Production JWT secret:** inject a distinct ≥32-char secret into the real deployment store
   (none exists in this environment). Config validation is complete.
3. (Non-blocking) evidence-request deterministic-ordering fix — still deferred; not reproduced.

## 10. Safety report

- **Write target:** `poa_b034_clone` (disposable) only. **Live `pofa_dev` untouched** — confirmed
  after all operations at `rev=t0u1v2w3x030`, `ledger=6023` (the probe appends went to the clone,
  not `pofa_dev`). `pofa_test` used solely as the pytest target.
- **Protected DB modified?** No. `pofa_dev` and `pofa_test` schema/ledger unchanged.
- **Migration applied to a protected DB?** No new migration (BE-033 already applied it).
- **Services restarted?** Only a **clone-backed** uvicorn process, started and stopped locally for
  verification. The host dev stack and any production service were **not** started or restarted.
- **Secrets:** runtime password read from `D:/CODING/Scratch/be033/poa_runtime_password.txt`
  out-of-band and passed via env; never echoed. The JWT secret used for the run was local-only and
  not committed. No connection string with a password appears in logs or this report.
- **Cleanup:** `poa_b034_clone` dropped; container `/tmp` cleared. The fresh dump + probe scripts
  retained outside the repo in `D:/CODING/Scratch/be034/`.

## 11. Files changed

Docs only: `docs/BE-034 Runtime Identity Cutover and Live Service Verification Report.md`
(this file); backlog §6/§7 and project memory updated. No application source, migration, or test
file was edited. Nothing committed; nothing pushed.

## 12. Git status

Branch `Backend`, HEAD `d5685abf`. Untracked/modified = the BE-033 docs (from the prior
milestone) plus the new BE-034 report and backlog edits. No `git add -A`/`clean`/`reset` used; no
commit or push performed.

## 13. Next milestone recommendation

BE-034 has converted F-05 from "role provisioned but not exercised" into "**operationally verified
end-to-end against a running service and worker on a faithful clone of the current live
database**." The remaining work is genuinely operational/deployment, not engineering:

- **BE-035 (or an ops change-window task): execute the live runtime-identity cutover** — repoint
  the real deployment's `DATABASE_URL` to `poa_runtime`, restart API + workers, and re-run the §5/§6
  evidence against the live target; then pair with a real production JWT secret store. Production
  clearance should be re-evaluated only after that live cutover is verified.
