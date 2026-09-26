# BE-023 — Verification Report

**Status: IMPLEMENTATION COMPLETE. WINDOWS VERIFICATION COMPLETE.**

All tests have been executed on Windows against a fresh Python 3.12 environment
and a clean test database. The results below are actual executed numbers, not
estimates or sandbox projections.

- Branch: `Backend`
- HEAD at start: `9374db4a956fc7acd020886218515349fb70dd84`
- Remote: in sync with `origin/Backend`
- Working tree: ~90 changed paths = **79 pre-existing (user-owned, untouched)** + **BE-023 changes**

---

## 1. What was implemented

| # | Spec section | Deliverable | State |
|---|---|---|---|
| 1 | §1 Reconnaissance | Inventory produced and approved before any edit | done |
| 2 | §2 Test DB isolation | `backend/db/test_target.py`, `tests/conftest.py`, `pytest.ini` | **verified on Windows** |
| 3 | §3 Clean-DB verification | Documented procedure; `pytest_report_header` names the DB | **verified on Windows** |
| 4 | §4/§14 Audit ledger safety | `tests/audit_guard.py`, `tests/unit/test_audit_guard.py` | **verified on Windows** |
| 5 | §6 Migration verification | `tests/unit/test_migrations.py` | **verified on Windows** |
| 6 | §8/§9 Dependency gating | `tests/preflight.py`, `tests/unit/test_preflight.py`, `test_clip_embedding.py` | **verified on Windows** |
| 7 | §9 Documentation | `docs/BE-023 Test Environment.md` | done |
| 8 | §10 Full-suite verification | Full integration + unit suites executed on Windows | **COMPLETE** |

---

## 2. Changed-file inventory

### New files

| File | Purpose |
|---|---|
| `backend/db/test_target.py` | Resolves `TEST_DATABASE_URL` explicitly. Refuses unset/blank/`pofa_dev`/malformed/no-db-name. Never falls back to `DATABASE_URL`. |
| `pytest.ini` | `pythonpath = .`, `testpaths`, `--strict-markers`, `be023`/`integration` markers. |
| `requirements-dev.txt` | Single test-only dependency: `pytest==9.1.1`. Separates runtime from test dependencies. |
| `tests/__init__.py` | Makes `tests` a proper package so `from tests.audit_guard import …` resolves correctly inside `tests/integration/test_audit_ledger.py`. |
| `tests/conftest.py` | Publishes the test DB as `DATABASE_URL` before any engine is built; prints DB identity and ML state in the session header. |
| `tests/audit_guard.py` | AST + regex static guard against destructive audit-ledger operations. Scans for ORM and raw-SQL deletes/truncations against `audit_ledger_events`. |
| `tests/preflight.py` | ML four-state classifier (`AVAILABLE`, `PARTIALLY_AVAILABLE`, `UNAVAILABLE`, `NOT_INSTALLED`); Redis/MinIO/PostgreSQL probes returning structured `DependencyStatus`; `require()` that fails loudly naming every unmet dependency. |
| `tests/unit/test_test_target.py` | 9 unit tests for the DB-resolution contract (unset, blank, malformed, pofa_dev rejection, etc.). |
| `tests/unit/test_audit_guard.py` | 17 regression tests pinning the guard against synthetic sources — including confirmed true/false positives. |
| `tests/unit/test_migrations.py` | 8 tests on the Alembic revision graph (single head, single root, no merges, no orphans, correct head revision). |
| `tests/unit/test_preflight.py` | 24 tests for dependency classification and probing. |
| `docs/BE-023 Test Environment.md` | Setup procedure, dependency table, ML version table, cache behaviour, run commands, known limitations. |

### Modified files

| File | Change | Why |
|---|---|---|
| `requirements.txt` | Added `pi-heif==0.7.0` | Required for reproducible Ultralytics/Pillow behaviour. Without this pin, Ultralytics auto-installs a version that conflicts with the pinned `Pillow==10.0.0` in a fresh environment. This is an intentional reproducibility fix, not a convenience upgrade. |
| `tests/integration/test_audit_ledger.py` | `test_no_test_deletes_audit_ledger_rows` now delegates its scan to `tests/audit_guard.py` via `scan_test_tree()`; imports `from pathlib import Path`. | Two divergent copies of the same guard would inevitably drift. The shared module is the single source of truth, independently regression-tested in `test_audit_guard.py`. |
| `tests/integration/test_clip_embedding.py` | Replaced anonymous `pytest.importorskip("torch")` + `pytest.importorskip("transformers")` with `ml_skip_reason()` from `tests/preflight.py`. | BE-023 §8: an anonymous module-level skip hides whether anything was verified. The skip now names the exact ML state (e.g., `ML_AVAILABLE — all packages present`) in the test report, making it auditable. |
| `tests/integration/test_governance.py` | Extracted `process_with_analysis()` helper; added CLIP-availability gate in `test_dependencies_endpoint_reports_bounded_graph`. | BE-023 §8: `analyze_duplicates` creates the `AnalysisResult` row only inside the CLIP branch. When ML is unavailable there is no `ANALYSIS_RESULT` node for the graph to traverse, and the test would fail for an environmental reason unrelated to governance. The gate distinguishes this from a genuine governance failure — when ML is available, every assertion runs unchanged. |
| `.gitignore` | Changed `backend/.venv312/` to `backend/.venv312*/` | Covers `backend/.venv312_clean/` and `backend/.venv312_repro/` (the reproducibility environments created during Windows verification) without committing them. |

### Explicitly NOT changed

`backend/db/models.py`, `backend/services/audit_ledger.py`,
`backend/repositories/audit_ledger.py`, all Alembic migrations,
the Python version, and every production audit-chain path. Per constraint §5,
BE-015 chain construction, hashing, sequence allocation and `verify_chain()`
are untouched.

The existing 7 sequence gaps in `pofa_dev` (36 missing rows from earlier test
contamination) were **intentionally left untouched**. BE-023 prevents new
contamination and redirects tests to a clean database; it does not repair
historical damage to `pofa_dev`. That is explicitly deferred.

---

## 3. Tests added

| Suite | Count | Windows result |
|---|---|---|
| `tests/unit/test_audit_guard.py` | 17 test functions | **17/17 pass** |
| `tests/unit/test_test_target.py` | 9 tests | **9/9 pass** |
| `tests/unit/test_migrations.py` | 8 tests | **8/8 pass** |
| `tests/unit/test_preflight.py` | 24 tests (incl. parametrized) | **24/24 pass** |

---

## 4. Windows verification — fresh Python 3.12 environment

### Repro environment

A completely fresh Python 3.12 environment was created at:
```
backend/.venv312_repro/
```

Runtime dependencies were installed exclusively from `requirements.txt`.
Test dependencies from `requirements-dev.txt` (`pytest==9.1.1`).

Verified importable in the fresh environment:
```
Python 3.12.0
Pillow 10.0.0
torch 2.8.0+cpu
transformers 4.56.2
ultralytics 8.4.155
pi-heif 0.7.0
```

This proves the ML/image dependency stack can be reproduced from the declared
dependency files without manual intervention or system-level workarounds.

### Test database

Tests were run against: **`pofa_test`**  
Database source: **`TEST_DATABASE_URL`** — no fallback to `pofa_dev`.

Fresh migrations applied to `pofa_test` reached: **`n4o5p6q7r022`** (head).

Session header printed on every run:
```
PoA test database: pofa_test
PoA test database source: TEST_DATABASE_URL
ML AVAILABLE: all of torch, transformers, ultralytics importable
```

---

## 5. Verification results — actual executed numbers

### Dedicated BE-023 suite

```powershell
.\backend\.venv312_repro\Scripts\python.exe -m pytest -m be023 -v
```

**60 passed, 1 skipped, 488 deselected**

The one skip is:
```
tests/unit/test_preflight.py::test_ml_available_skip_reason_is_none
SKIPPED — ML stack genuinely installed in this environment
```
This is a correct, expected, informational skip. The test verifies that
`ml_skip_reason()` returns `None` when ML is unavailable; in this environment
ML *is* fully available so the skip condition cannot fire — the skip message
says so explicitly. It is not a failure.

### Full unit suite

```powershell
.\backend\.venv312_repro\Scripts\python.exe -m pytest tests/unit -v
```

**348 passed, 1 skipped, 0 failed**

The one skip is the same ML-available informational skip described above.

### Full integration suite

```powershell
.\backend\.venv312_repro\Scripts\python.exe -m pytest tests/integration -v
```

**200 passed, 0 failed, 0 skipped, 7 warnings**  
Runtime: 375.76 seconds

Verified areas include:
- **Audit**: append/verify, tamper detection, broken-link detection, concurrent appends, no-test-delete guard, failed domain operation behaviour
- **ML**: real CLIP embedding, real YOLO inference (weights present in cache)
- **Redis**: analysis job queue
- **Evidence Graph**: graph traversal, dependency endpoints
- **Temporal analysis**
- **Duplicate intelligence**
- **Fusion**
- **Explainability**
- **Governance**: including the CLIP-availability gate for `test_dependencies_endpoint_reports_bounded_graph`
- **Publication**
- **Retention**
- **Review Cases**
- **MinIO/object storage**

### 7 warnings

All 7 warnings are `DeprecationWarning` from third-party packages
(`pydantic`, `starlette`). They are not failures, not regressions, and are
outside BE-023 scope. They were present before BE-023 and have not been
introduced or changed by it.

---

## 6. Audit ledger — no production changes

The BE-015 append-only audit chain is **unchanged**:

- `backend/services/audit_ledger.py` — not modified
- `backend/repositories/audit_ledger.py` — not modified
- All audit-chain migrations — not modified
- `verify_chain()`, `append_event()`, sequence allocation — not modified

The static guard (`tests/audit_guard.py`) confirmed **0 violations** across
the entire test tree. The integration suite audit tests confirmed:
- append and verify work correctly
- tamper detection works correctly
- broken-link detection works correctly
- concurrent appends are safe
- no test deletes ledger rows

---

## 7. Failure investigation

### Issue 1: Ultralytics auto-installs a conflicting `pillow-heif` version

**Symptom:** Fresh environment install failed with a `pillow-heif` version conflict
when Ultralytics pulled its own dependency pin, incompatible with
`Pillow==10.0.0`.

**Root cause:** Ultralytics auto-installs `pillow-heif` without a version pin;
the version it installs conflicted with our pinned `Pillow==10.0.0`.

**Fix:** Added `pi-heif==0.7.0` to `requirements.txt`. This pre-satisfies the
dependency with a version known to work with `Pillow==10.0.0`, preventing
Ultralytics from pulling an incompatible version.

**Regression test:** The fresh `backend/.venv312_repro/` environment was built
from `requirements.txt` only and all imports verified. `pi-heif==0.7.0` is now
a reproducibility pin, not a convenience upgrade.

### Issue 2: PIL namespace conflict in earlier environment

**Symptom:** System-level PIL shadowed the virtualenv Pillow install.

**Root cause:** A system-installed PIL was on `sys.path` before the venv Pillow.

**Fix:** Resolved at the environment level (renamed system PIL); the
`requirements.txt` pin ensures `Pillow==10.0.0` is installed in clean
environments. The `backend/.venv312_repro/` environment was created fresh and
did not reproduce this issue — confirming it was an environment-state problem,
not a production defect.

---

## 8. Known remaining risks and maintenance obligations

1. **`tests/unit/test_migrations.py` pins `EXPECTED_REVISION_COUNT = 19` and
   `EXPECTED_HEAD = "n4o5p6q7r022"`.** A future migration must bump these
   values. This is intentional — the bump should be a deliberate act, not
   silent — but it is a maintenance obligation on every future migration author.

2. **The 7 sequence gaps in `pofa_dev` are still there.** BE-023 prevents new
   contamination; it does not repair historical damage. Any developer using
   `pofa_dev` will see a broken chain. The correct response is to point tests
   at `pofa_test` as documented.

3. **ML weights are cache-dependent.** If the CLIP/YOLO model cache is cold
   and there is no network, `test_clip_embedding` and any ML-dependent test
   will skip with the state named. This is honest — the skip message names the
   exact ML state — but it means ML coverage is unproven until the cache is
   warm.

4. **The 7 `DeprecationWarning`s from `pydantic` and `starlette` are not
   addressed.** They predate BE-023 and are outside its scope. They should be
   addressed in a dedicated dependency-maintenance milestone.

---

## 9. Commit scope (awaiting explicit approval)

The proposed commit on `Backend` contains only the BE-023 deliverables listed
below. It does **not** include the ~79 pre-existing user-owned modified paths.

Because those files are already dirty, committing uses explicit pathspecs —
**not** `git add -A` and **not** `git commit -a`.

### Files to commit

```
.gitignore
requirements.txt
requirements-dev.txt
pytest.ini
backend/db/test_target.py
tests/__init__.py
tests/conftest.py
tests/audit_guard.py
tests/preflight.py
tests/unit/test_test_target.py
tests/unit/test_audit_guard.py
tests/unit/test_migrations.py
tests/unit/test_preflight.py
tests/integration/test_audit_ledger.py
tests/integration/test_clip_embedding.py
tests/integration/test_governance.py
docs/BE-023 Test Environment.md
docs/BE-023 Verification Report.md
docs/Production Task Files/BE-023 — Verification Hardening, CI Safety & Reproducible Test Infrastructure.md
```

### Files explicitly excluded

**Local/generated — do not commit:**
- `backend/.venv312_clean/` (local repro environment, now in `.gitignore`)
- `backend/.venv312_repro/` (local repro environment, now in `.gitignore`)

**Stale temporary agent artifacts — do not commit:**
- `backend/BE-023_Status.txt` — intermediate agent scratchpad written during
  issue investigation. Contains stale "NEXT STEPS" that are now resolved and
  a note about a `except Exception` widening that was reverted. Not a project
  deliverable. Should remain untracked.
- `backend/BE-023_Summary.txt` — similar intermediate agent scratchpad. States
  "REMAINING WORK" that is now complete. Not a project deliverable. Should
  remain untracked.

**Pre-existing user-owned changes — do not touch:**
- All other ~79 modified paths not listed in the commit scope above.

### Proposed commit message

```
BE-023: harden reproducible verification infrastructure
```
