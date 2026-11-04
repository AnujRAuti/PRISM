---
name: test-automation-frameworks
description: Choose and structure automation tooling—runner capabilities, fixture lifecycles, plugins, parallelization, and reporting wired into CI without lock-in.
metadata:
  domain: testing-and-debugging
  version: 1.0.0
  risk: low
---

# Test Automation Frameworks

## 1. Purpose

Pick the runner and structure the harness so tests are cheap to add, fast to run, and legible when they fail. Framework decisions are usually made by inertia (whatever the last project used) or by feature checklist, and then paid for over years in slow feedback and hard-to-extend fixtures. This skill covers runner selection criteria, fixture and hook design, plugin policy, parallel execution, reporting, and the extension points that keep a suite maintainable at thousands of tests.

**Scope:** your own repositories and CI. Automation frameworks run arbitrary code including third-party plugins—treat plugins as a supply-chain decision.

## 2. Activation Conditions

- Starting a project's test harness, or replacing an unmaintainable one.
- The suite is slow, the fixtures are tangled, or reports are unreadable.
- Multiple languages/services need a consistent convention.
- Evaluation between pytest/unittest, vitest/jest, Playwright/Cypress, JUnit/TestNG.
- Keywords: test framework, test runner, pytest, vitest, jest, Playwright, Cypress, fixtures, hooks, conftest, plugins, parallelization, xdist, reporting, JUnit XML, coverage integration.

## 3. When Not to Use

- Writing individual tests (use unit-testing / integration-testing / end-to-end-testing).
- Choosing test levels and gates (use testing-strategy).
- Non-test automation (build scripts, deployment tooling).

## 4. Required Context

1. Languages and platforms in the repo.
2. Test types needed: unit, integration, E2E, contract, performance.
3. CI system and its reporting/parallelization capabilities.
4. Team familiarity and hiring considerations.
5. Constraints: async support, plugins, license, ecosystem health.

## 5. Operating Procedure

1. **Select by capability requirements first**: async-native fixtures, parameterization, parallel execution, first-class tracing/reporting, and a maintained plugin ecosystem. Write the criteria down before comparing names.
2. **Standardize on one primary runner per language**; a second runner doubles CI wiring and reporting.
3. **Design the fixture hierarchy deliberately**: session-scoped expensive resources (containers, browser), function-scoped isolation (transactions, pages), and explicit teardown.
4. **Keep configuration in one place** (`pyproject.toml`, `playwright.config.ts`, `vitest.config.ts`) with markers/projects, not scattered CLI flags.
5. **Use markers/projects for layers and slow paths**, and make the default command run the fast set.
6. **Adopt plugins conservatively**: pin versions, review maintenance activity, and prefer standard-library features. Every plugin is code running in CI with your tokens.
7. **Make parallel execution the default** (xdist, workers, shards) with per-worker isolation.
8. **Emit machine-readable reports** (JUnit XML + coverage XML + HTML) and upload them; do not rely on console logs.
9. **Provide a consistent assertion library and error output**: failures must show the expected vs. actual value and the relevant context.
10. **Document the framework contract** for the team: how to add a test, a fixture, a marker, and where the config lives.
11. **Review the harness quarterly**: runtime, flake rate, plugin freshness, and unused fixtures.

## 6. Tools and Technologies

| Layer | Python | TypeScript/JS |
|---|---|---|
| Unit/integration runner | pytest (+ pytest-asyncio, xdist, cov) | vitest, jest, node:test |
| E2E runner | Playwright (Python) | Playwright, Cypress |
| Fixtures | `conftest.py`, factories | `beforeEach`, custom fixtures, `test.extend` |
| Assertions | plain `assert`, `pytest.raises` | `expect` (vitest/jest) |
| Mocks (HTTP) | respx, responses | msw, nock |
| Reporting | JUnit XML (`--junitxml`), HTML | JUnit XML, HTML reporters |
| Parallel | pytest-xdist, shards | workers/threads, Playwright shards |
| Lint for tests | ruff, mypy on tests | eslint, tsc on tests |

## 7. Practical Implementation

**Single configuration surface (Python):**

```toml
# pyproject.toml
[tool.pytest.ini_options]
minversion = "8.0"
testpaths = ["tests"]
addopts = [
  "-ra", "--strict-markers", "--strict-config",
  "--durations=15", "--junitxml=reports/junit.xml",
]
markers = [
  "unit: fast, hermetic",
  "integration: uses containers or a database",
  "e2e: drives a browser",
  "contract: verifies provider/consumer contracts",
  "slow: exceeds 2s",
]
filterwarnings = ["error"]
asyncio_mode = "auto"
```

**Fixture layering (session → function) with explicit teardown:**

```python
# tests/conftest.py
import pytest, pytest_asyncio
from testcontainers.postgres import PostgresContainer

@pytest.fixture(scope="session")
def pg():
    with PostgresContainer("postgres:16-alpine", driver="asyncpg") as container:
        yield container                      # one container per session: fast startup

@pytest_asyncio.fixture(scope="session")
async def engine(pg):
    eng = create_async_engine(pg.get_connection_url())
    await run_migrations(eng)
    yield eng
    await eng.dispose()

@pytest_asyncio.fixture
async def session(engine):
    conn = await engine.connect()
    tx = await conn.begin()
    maker = async_sessionmaker(bind=conn, expire_on_commit=False)
    async with maker() as s:
        yield s                              # function scope: isolated data
    await tx.rollback()
    await conn.close()

@pytest.fixture
def api_client(session, app):
    app.dependency_overrides[get_session] = lambda: session
    yield TestClient(app)
    app.dependency_overrides.clear()
```

**Marker-driven execution and parallel safety:**

```bash
pytest -m unit -n auto -q                      # pre-commit
pytest -m "unit or integration" -n 4 -q        # PR
pytest -m e2e --dist loadscope -n 2            # pre-deploy
pytest --co -q | wc -l                         # collection sanity check
```

```python
# conftest.py: guard against accidentally running integration in the fast job
import os
import pytest

def pytest_collection_modifyitems(config, items):
    if os.getenv("FAST_ONLY") == "1":
        keep, skip = [], pytest.mark.skip(reason="FAST_ONLY")
        for item in items:
            (keep if "unit" in item.keywords else skip).append(item)
        items[:] = keep
```

**TypeScript configuration with projects:**

```ts
// vitest.config.ts
import {defineConfig} from "vitest/config";

export default defineConfig({
  test: {
    projects: [
      {test: {name: "unit", include: ["src/**/*.test.ts"], environment: "node"}},
      {test: {name: "ui", include: ["src/**/*.test.tsx"], environment: "jsdom",
              setupFiles: ["./test/setup.ts"]}},
    ],
    coverage: {
      provider: "v8",
      reporter: ["text", "lcov", "json-summary"],
      exclude: ["**/*.d.ts", "src/generated/**"],
    },
    reporters: ["default", "junit"],
    outputFile: {junit: "./reports/junit.xml"},
    pool: "threads",
    sequence: {shuffle: true},
  },
});
```

**CI wiring with reports and caching:**

```yaml
- uses: actions/cache@v4
  with:
    path: ~/.cache/ms-playwright
    key: pw-${{ runner.os }}-${{ hashFiles('package-lock.json') }}
- run: npm ci && npx playwright install --with-deps chromium
- run: npx playwright test --reporter=junit,html
- uses: actions/upload-artifact@v4
  if: always()
  with:
    name: test-reports
    path: |
      reports/junit.xml
      playwright-report/
    retention-days: 7
- uses: dorny/test-reporter@v1
  if: always()
  with:
    name: Playwright results
    path: reports/junit.xml
    reporter: java-junit
```

**Custom fixture factory for domain data (extension point teams actually need):**

```python
# tests/conftest.py
@pytest.fixture
def make(session):
    """Single entry point for data creation; keeps tests one line long."""
    created: list = []

    async def _make(factory, **overrides):
        obj = await factory(session, **overrides)
        created.append(obj)
        return obj

    yield _make

    for obj in reversed(created):                # explicit teardown ordering
        session.delete(obj)
```

**Failure output quality (custom assertion helper):**

```python
def assert_problem_details(resp, *, status: int, type_suffix: str):
    body = resp.json()
    assert resp.status_code == status, f"expected {status}, got {resp.status_code}: {body}"
    assert body.get("type", "").endswith(type_suffix), f"unexpected problem type: {body.get('type')}"
    assert body.get("status") == status, f"problem body status mismatch: {body}"
    assert body.get("title"), "problem details must include a title"
```

**Plugin policy checklist:**

```text
[ ] Released within the last 12 months, or explicitly maintained
[ ] Pinned to an exact or bounded version in the lockfile
[ ] Reviewed source or reputation; no postinstall scripts without review
[ ] Has a documented exit strategy (what replaces it if abandoned)
[ ] Does not capture or upload test data to a third party by default
```

## 8. Quality Standards

- One primary runner per language, configured in a single file.
- Fixtures are layered by cost with explicit teardown; no module-level mutable state.
- Default command runs the fast suite; slow layers opt in by marker/project.
- Parallel execution is the default and safe (unique data per worker).
- Reports are machine-readable and uploaded in CI; console output alone is insufficient.
- Assertions include expected/actual values and domain context.
- Plugins are pinned, reviewed, and limited in number.
- A new contributor can add a test, a marker, and a fixture by following the README.

## 9. Verification and Testing

- Confirm collection works with `--collect-only` in each project/marker set.
- Run the fast suite in under 10 s for a small project; verify duration tuning with `--durations`.
- Verify parallel runs give identical results to serial runs.
- Check the CI report renders failures with file/line and a readable message.
- Simulate an unhandled error in a fixture and confirm the message names the fixture.
- Confirm coverage and JUnit XML artifacts are produced on failure as well as success.

## 10. Security Considerations

- Test plugins execute arbitrary code with CI credentials: pin versions, review new plugins, and avoid unpinned `latest`.
- Do not let reporters upload logs to external services without approval; configure destinations explicitly.
- Keep test configuration out of production bundles; ensure test-only entry points are stripped from builds.
- CI workflows triggered from forks must not receive repository secrets.
- Cached browser/dependency directories must be shared only within trusted scopes.
- Framework debug modes can print environment variables; disable verbose dumping in CI logs that are broadly visible.

## 11. Failure Handling

- **Fixtures couple across layers:** a function fixture depends on a session fixture that mutates shared state; push mutation into the function scope.
- **Suite slow after a new plugin:** measure with `--durations` and `--profile`; remove or replace the plugin.
- **Reports unreadable:** standardize on JUnit XML plus an HTML artifact; custom reporters drift.
- **Different behavior locally vs. CI:** pin tool versions in lockfiles and run the same command in both places.
- **Framework upgrade breaks many tests:** read the changelog, upgrade in a dedicated PR, and use deprecation warnings as a migration list.

## 12. Expected Deliverables

1. Framework selection criteria and decision record.
2. Configuration files committed to the repo.
3. Fixture hierarchy documentation.
4. Marker/project taxonomy and commands.
5. Parallelization and sharding configuration.
6. Reporting and artifact upload setup.
7. Plugin policy and inventory.

## 13. References

- pytest documentation — https://docs.pytest.org/en/stable/
- pytest fixtures — https://docs.pytest.org/en/stable/how-to/fixtures.html
- pytest-xdist — https://pytest-xdist.readthedocs.io/
- vitest configuration — https://vitest.dev/config/
- Playwright test configuration — https://playwright.dev/docs/test-configuration
- JUnit XML format (Surefire) — https://maven.apache.org/surefire/maven-surefire-plugin/xsd/surefire-test-report.xsd
- Cypress documentation — https://docs.cypress.io/
- GitHub Actions artifacts — https://docs.github.com/en/actions/using-workflows/storing-workflow-data-as-artifacts
