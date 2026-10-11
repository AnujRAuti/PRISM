# BE-036 — Webhook Worker Reliability and ImportError Remediation Report

**Date:** 2026-10-11
**Branch:** `Backend` · **HEAD at start:** `d5685abf` ("BE-032 Complete") — unchanged; nothing committed or pushed.
**Verdict:** **BE-035-D1 CLOSED — WORKER VERIFIED**
**Production:** **NOT CLEARED** — production deployment remains entirely outside this milestone.

This milestone investigated, fixed, and verified the single reported defect carried out of BE-035:
the `webhook_worker` `ImportError` (finding **BE-035-D1**). It is a reliability milestone. No production
target, secret store, or deployment action was attempted, and the BE-035 report was not rewritten to
imply the finding had already been resolved there.

---

## 1. Original error and reproduction conditions

**Reported (BE-035 §7.1 / backlog BE-035-D1):** `backend.workers.webhook_worker` fails to import with an
`ImportError`, so the worker cannot start under the current runtime configuration.

**Reproduced** with the repo's reproducible interpreter (`backend/.venv312_repro`, Python 3.12), from the
repository root, before any change:

```
$ backend/.venv312_repro/Scripts/python.exe -c "import backend.workers.webhook_worker"
ImportError: cannot import name 'SessionLocal' from 'backend.db.session' (backend\db\session.py)
```

Reproduction was exact and deterministic. The failure is at **import time** (module-level statement),
which is why it also blocked the `python -m backend.workers.webhook_worker` entry point: Python executes
the module's top-level imports before `__main__` runs. No credentials or connection strings appear in the
error; it names only the missing symbol and its source module.

## 2. Root cause

`backend/workers/webhook_worker.py` line 20 read:

```python
from backend.db.session import SessionLocal
```

and called `db = SessionLocal()` in two places — `run_worker_once` (line 269) and the `__main__`
`else` branch (line 294).

But `backend/db/session.py` **does not export** `SessionLocal`. Its public/available names are
`get_session`, `get_engine`, `get_db`, `build_guarded_engine`, plus a **module-private** sessionmaker
`_SessionLocal` (`backend/db/session.py:22,60-63`). `get_session()` is the documented, correct idiom —
it returns `_SessionLocal()` after lazily configuring the engine from `settings.database_url`.

This is a **stale/incorrect import path**, i.e. a genuinely broken reference — not a circular import, not a
missing third-party dependency, not a working-directory problem, and not environment-specific. Confirmed
by inspection:

* The other three workers (`analysis`, `notification`, `retention`) already use `get_session()` —
  `webhook_worker` was the lone outlier, so this was a per-file defect, not a systemic one.
* A repository-wide grep for the bare identifier `SessionLocal` under `backend/` returned **only**
  `webhook_worker.py` (before the fix) and the private `_SessionLocal` definition in `session.py`
  (after the fix). No sibling worker shared the latent bug.

The defect is **pre-existing and independent of the BE-035 runtime-identity cutover** — the import never
resolved, whether the configured user was `postgres` or `poa_runtime`.

## 3. Exact code changes

One file changed: `backend/workers/webhook_worker.py`. The fix is the smallest correct one and follows the
convention already used by the other workers. No interface, authorization, transaction, retry, timeout,
audit, or append-only behavior was altered, and no dependency was added.

```diff
- from backend.db.session import SessionLocal
+ from backend.db.session import get_session
```

```diff
  def run_worker_once(limit: int = 50) -> None:
      """Run one full pass: fanout events, then attempt deliveries."""
-     db = SessionLocal()
+     db = get_session()
      try:
          ...
      finally:
          db.close()
```

```diff
      else:
-         db = SessionLocal()
+         db = get_session()
          try:
              ...
          finally:
              db.close()
```

Three lines total (one import + two call sites). `get_session()` returns a fresh session per call, matching
the previous (intended) `SessionLocal()` semantics, so `run_worker_once`'s `try/finally db.close()` still
owns and releases exactly the session it opened — no session leak introduced.

## 4. Worker import and startup verification

Against the **actual** launch configuration (`settings.database_url` from the dev `.env`, which BE-035
repointed to `poa_runtime`):

```
$ backend/.venv312_repro/Scripts/python.exe -c "import backend.workers.webhook_worker as w; print('IMPORT_OK', w.get_session.__module__)"
IMPORT_OK backend.db.session

$ backend/.venv312_repro/Scripts/python.exe -m backend.workers.webhook_worker --help
usage: webhook_worker.py [-h] [--sweep-events] [--sweep-retries] [--once] [--limit LIMIT]
BE-019 webhook worker
```

The original `ImportError` is gone; the entry point parses arguments and exits cleanly **without**
performing any delivery. The `--help` path does not touch the network or the database.

The startup/entry-point wiring that the fix touched is additionally pinned by
`tests/integration/test_be036_webhook_worker.py::test_run_worker_once_uses_fixed_session_and_closes_cleanly`,
which asserts `run_worker_once` acquires its session through `get_session` and closes it in `finally`.

## 5. Runtime identity evidence

Read-only probe through the worker's own session factory (no delivery, no writes, no credentials echoed):

```
$ backend/.venv312_repro/Scripts/python.exe -c "... get_session(); SELECT current_user, session_user, current_database()"
WORKER_SESSION_IDENTITY user=poa_runtime session_user=poa_runtime db=pofa_dev
SHUTDOWN_CLEAN
```

The worker acquires its session as the non-owner, least-privilege `poa_runtime` identity against the
development database, consistent with the rest of the runtime (BE-035). The session closed cleanly. This
satisfies the F-05/D-RESTART note that previously read "webhook worker running identity is unverified."

**Deliberate verification boundary:** the worker was **not** run as a live daemon performing real outbound
delivery against `pofa_dev`. BE-036 §2 forbids invoking a real outbound webhook merely to prove the worker
starts, and forbids using the worker as a pretext for broad writes against protected data. Startup,
identity, shutdown, and the full delivery lifecycle were verified through the launch path plus
mocked-egress integration tests on `pofa_test`.

## 6. Webhook processing tests and external-side-effect controls

New file: `tests/integration/test_be036_webhook_worker.py` — **10 tests**, marked `integration`, run
against the explicit test database via `tests/conftest.py` (which refuses to fall back to `pofa_dev`).

Each test drives the **real** worker functions (`sweep_pending_deliveries`, `sweep_retries`,
`_attempt_delivery`, `_fanout_event`, `run_worker_once`) end to end:

| Test | §7 gate covered |
| --- | --- |
| `test_pending_delivery_delivers_and_audits` | A PENDING delivery is selected & processed once; success → `DELIVERED`, `delivered_at` set, failure counter reset, exactly one `WEBHOOK_DELIVERY_SUCCEEDED` audit row. |
| `test_connection_error_enters_retrying` | Connection error → `RETRYING` with a **future** `next_attempt_at`, attempt counter incremented, one `WEBHOOK_DELIVERY_FAILED` audit. |
| `test_retryable_status_retries_nonretryable_fails` | 5xx → `RETRYING`; 4xx → `FAILED` with no next attempt. |
| `test_exhausted_attempts_terminate_failed` | Once `MAX_DELIVERY_ATTEMPTS` is spent the failure is terminal (`FAILED`, `next_attempt_at` NULL). |
| `test_ssrf_blocked_fails_permanently_without_egress` | Unsafe endpoint fails **closed** and reaches **zero** `urlopen` calls; a later retry sweep does not re-send. |
| `test_disabled_subscription_short_circuits` | A `DISABLED` subscription marks the delivery `DISABLED` with no send. |
| `test_consecutive_failures_auto_disable` | The 10th consecutive failure disables the subscription and the delivery. |
| `test_completed_delivery_is_not_reprocessed` | A `DELIVERED` row is not selected by a later sweep; no duplicate audit. |
| `test_fanout_creates_one_delivery_per_subscription` | Fanout creates one delivery and is idempotent on re-run. |
| `test_run_worker_once_uses_fixed_session_and_closes_cleanly` | The fixed entry point acquires the session via `get_session` and closes it cleanly. |

**Side-effect controls:**
* `urllib.request.urlopen` is monkeypatched, so **no outbound request ever left the process**. The
  success/SSRF/disabled tests assert the exact call count (including `calls == []` where no send is
  expected). The fake also asserts the worker still passes `timeout=10`.
* `socket.getaddrinfo` (used by `validate_webhook_url`) is stubbed with a deterministic resolver — numeric
  hosts resolve to themselves so the private/metadata blocks still fire, and named hosts resolve to one
  public address so a well-formed endpoint is permitted. The **real** SSRF logic runs without any DNS call.
* Audit events are written through the established `append_event` path, so the append-only ledger
  (BE-030 enforcement) is exercised, not bypassed. Every delivery outcome produces exactly one ledger row.

**Result:** `11 passed` for the file on the first clean run (the 11th being the delete-guard check run
alongside it), then focused re-runs confirmed **all 10 tests green**.

## 7. Regression commands and results

Interpreter: `backend/.venv312_repro/Scripts/python.exe` (Python 3.12).
Database target: `pofa_test` (published as `DATABASE_URL` from `TEST_DATABASE_URL` by `tests/conftest.py`;
the suite refuses `pofa_dev`). Alembic revision on `pofa_test`: `t0u1v2w3x030`.

**Import / startup (no DB, no egress):**
```
IMPORT_OK backend.db.session
webhook_worker --help → usage printed, EXIT 0
```

**Focused worker + affected tracks:**
```
TEST_DATABASE_URL=.../pofa_test python -m pytest tests/integration/test_be036_webhook_worker.py
  → 11 passed
TEST_DATABASE_URL=.../pofa_test python -m pytest tests/unit/test_integration.py \
      tests/integration/test_be030_ledger_enforcement.py tests/integration/test_audit_ledger.py \
      tests/integration/test_be029_database_safety_guard.py
  → 52 passed, 0 failed
```

**Full backend suite:**
```
TEST_DATABASE_URL=.../pofa_test python -m pytest tests/
  → 831 passed, 1 skipped, 0 failed  (EXIT 0)
```
The single skip is `tests/unit/test_preflight.py` ("ML stack genuinely installed" → the unavailable-ML
branch is skipped); it is pre-existing and unrelated.

**Comparison points (not claims about this run):**
* BE-035 reported a **168 passed / 0 failed** focused subset — a comparison, consistent with the affected
  tracks re-run here.
* The prior **full-suite** baseline was BE-033's `821 passed / 1 skipped / 0 failed`. This run is
  `831 / 1 / 0` — exactly **+10**, i.e. the ten new BE-036 tests, with **no regression**.

One transient failure during development, `test_no_test_deletes_audit_ledger_rows`, is described in §9.

## 8. Files changed

* `backend/workers/webhook_worker.py` — the fix (3 lines: import + two call sites).
* `tests/integration/test_be036_webhook_worker.py` — new, 10 integration tests (the delivery/retry/audit
  verification, mocked egress).
* `docs/Backend Technical Debt and Deferred Fixes Backlog.md` — BE-035-D1 → **Closed**; F-05/D-RESTART
  "webhook worker cannot start" notes corrected; new §9 BE-036 reconciliation; new deferred finding
  **BE-036-D1** (§1 table).
* `docs/BE-036 Webhook Worker Reliability and ImportError Remediation Report.md` — this document.

No production configuration, `.env` contents, secrets, or the BE-035 report were modified. Nothing was
committed or pushed. The working tree shows the `webhook_worker.py` source change, the new test file, the
backlog edit, and this report.

## 9. Related findings intentionally deferred

**BE-036-D1 — `urlopen` follows HTTP redirects (SSRF guarantee mismatch).** Deferred, not fixed.
`_attempt_delivery` sends via `urllib.request.urlopen(req, timeout=10)`. Python's default opener installs
`HTTPRedirectHandler`, so a 301/302 from the endpoint is followed to a new URL that `validate_webhook_url`
never re-inspected — precisely the redirect-to-internal-address vector the SSRF guard exists to prevent.
The code comment ("never follow redirects") and `validate_webhook_url`'s docstring both assert a guarantee
the implementation does not currently hold. This is **pre-existing, security-relevant, and not caused by
the import defect**; its correct fix (a redirect-free opener or explicit 3xx handling, plus tests) is its
own reliability milestone. Per BE-036 §9 it is documented as a backlog item rather than folded into this
scope. Full detail: backlog §1, row **BE-036-D1**.

Minor, noted and left as-is (pre-existing, in-scope-neutral, not caused by the fix):
* A delivery set to `PROCESSING` before the network call has no reaper; a crash mid-send would strand it in
  `PROCESSING`, which neither sweep selects (they pick `PENDING`/`RETRYING`). Single-pass/periodic use is
  unaffected; worth a reaper in a future worker-hardening pass.
* The sweeps `SELECT` without row-level locking (`FOR UPDATE ... SKIP LOCKED`), so two concurrent worker
  processes could double-deliver the same `PENDING` delivery. The worker's documented model is one-shot /
  periodic single process; this only matters if it is ever parallelized.

**The `test_no_test_deletes_audit_ledger_rows` guard** initially flagged this milestone's own draft test,
which had embedded a literal `UPDATE audit_ledger_events …` to re-demonstrate refusal. That is the guard
working as designed (it is a conservative textual rule; BE-029/BE-030 history shows why DELETE/UPDATE
against the ledger is barred). The redundant UPDATE probe was **removed** rather than special-cased into the
allowlist or reworded to slip past the guard — the append-only refusal is already a shipped BE-030
responsibility, and BE-036 proves the worker only ever goes through `append_event`. No security assertion
was weakened.

## 10. BE-035-D1 disposition

**CLOSED — verified through actual worker startup**, not merely by a unit test. The root cause was fixed,
the module imports, the real entry point runs, `get_session()` opens a `poa_runtime` session and closes
cleanly, and the full delivery/retry/audit lifecycle is integration-verified with zero real egress. The
backlog six-state row was advanced honestly and the F-05/D-RESTART "worker cannot start" notes corrected.

## 11. Production deployment status

**Outside this milestone. Production remains NOT CLEARED.** BE-036 is reliability work only. There is still
no production target, no production JWT secret store, and no production runtime-identity configuration;
those are the separate **Option B — Production Deployment Planning** workstream that follows BE-036 and must
identify the real target and secret-management mechanism before any production deployment or credential
cutover is attempted. The next workstream after this milestone is Option B; nothing here advances it.
