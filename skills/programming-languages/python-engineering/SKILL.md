---
name: python-engineering
description: Write production Python—typing and mypy/pyright, packaging with pyproject, async correctness, dependency pinning, and performance profiling where it matters.
metadata:
  domain: programming-languages
  version: 1.0.0
  risk: medium
---

# Python Engineering

## 1. Purpose

Ship Python that behaves correctly under concurrency, installs reproducibly, and stays fast enough. Python's failure modes are specific: mutable default arguments, blocking calls inside `async def`, silent `except Exception`, unpinned dependencies that break at deploy time, and slow loops that should be vectorized or pushed to the database. This skill covers typing, packaging, async discipline, error handling, performance, and toolchain configuration.

**Scope:** your own code and dependencies. Installing packages executes code at build time: pin versions, use hashes or a lockfile, and never `pip install` from an untrusted URL or run `curl | python`.

## 2. Activation Conditions

- New service, library, or CLI in Python.
- `mypy`/type errors ignored or absent.
- Reproducibility problems ("works on my machine", surprise upgrades).
- Async code that blocks, or slow hot paths.
- Keywords: Python, typing, mypy, pyright, pydantic, asyncio, pyproject.toml, uv, poetry, ruff, pytest, profiling, py-spy, packaging, venv.

## 3. When Not to Use

- Data/ML pipeline design (use the AI/ML domain skills).
- Shell-level automation (use shell-scripting).
- Frontend or browser code (use javascript/typescript skills).

## 4. Required Context

1. Target Python version(s) and deployment environment.
2. Runtime shape: web service, worker, CLI, library.
3. Dependency policy and internal package index.
4. Concurrency model: sync, async, threads, multiprocessing.
5. Performance requirements and current bottlenecks.

## 5. Operating Procedure

1. **Pin the interpreter** (`.python-version`, `requires-python`) and the dependency set (lockfile with hashes).
2. **Type the public surface**: annotate function signatures, use `Protocol` for interfaces, `TypedDict` for structured dicts, and run `mypy --strict` (or pyright) in CI on new code.
3. **Configure one linter/formatter** (ruff) with rules enabled deliberately; format on save and check in CI.
4. **Never use mutable default arguments**; use `None` sentinel or `field(default_factory=...)`.
5. **Handle errors precisely**: catch the narrowest exception, never bare `except:`, use `raise ... from exc`, and define domain exceptions.
6. **In async code, never call blocking I/O**: use async clients, `asyncio.to_thread` for unavoidable blocking calls, and set timeouts on every await that crosses a network.
7. **Prefer dataclasses/Pydantic models over dicts** for structured data; validate at boundaries.
8. **Profile before optimizing**: `py-spy`, `cProfile`, `scalene`; optimize algorithms and I/O patterns before micro-tuning.
9. **Bound memory**: stream large data, avoid loading whole files, use generators, and be explicit about copying in pandas/numpy.
10. **Package properly**: `pyproject.toml` with a build backend, versioned entry points, and `src/` layout to avoid import shadowing.

## 6. Tools and Technologies

| Concern | Options |
|---|---|
| Env/deps | `uv`, Poetry, pip-tools, venv/`virtualenv` |
| Typing | mypy, pyright, pydantic v2, `typing_extensions` |
| Lint/format | ruff (lint + format), black (legacy) |
| Test | pytest, `pytest-asyncio`, hypothesis, coverage.py |
| Profiling | cProfile + `snakeviz`, py-spy, scalene, `tracemalloc` |
| Async | asyncio, `anyio`, httpx, asyncpg |
| Packaging | hatchling, setuptools, `uv build`, `twine` |
| Security | `pip-audit`, `bandit`, `safety` |

## 7. Practical Implementation

**`pyproject.toml` with typed, reproducible configuration:**

```toml
[project]
name = "orders-service"
version = "1.4.0"
requires-python = ">=3.12"
dependencies = [
  "fastapi>=0.115,<1.0",
  "pydantic>=2.9,<3.0",
  "asyncpg>=0.29,<0.30",
  "httpx>=0.27,<0.28",
]

[project.optional-dependencies]
dev = ["pytest>=8.3", "pytest-asyncio>=0.24", "mypy>=1.11", "ruff>=0.6", "pip-audit>=2.7"]

[project.scripts]
orders = "orders_service.cli:main"

[build-system]
requires = ["hatchling>=1.25"]
build-backend = "hatchling.build"

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM", "ASYNC", "S", "RUF"]
ignore = ["E501"]            # line length handled by the formatter

[tool.mypy]
python_version = "3.12"
strict = true
warn_unreachable = true
disallow_any_explicit = false   # enable per-module as legacy code is typed

[tool.pytest.ini_options]
addopts = "-q --strict-markers"
asyncio_mode = "auto"
```

**Typed, explicit code (no mutable defaults, precise errors):**

```python
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Protocol, Sequence


class PricingError(Exception):
    """Raised when an order cannot be priced."""


class DiscountRule(Protocol):
    def apply(self, subtotal: Decimal) -> Decimal: ...


@dataclass(frozen=True, slots=True)
class Order:
    id: str
    lines: tuple[Line, ...] = field(default_factory=tuple)

    def total(self) -> Decimal:
        if not self.lines:
            raise PricingError(f"order {self.id} has no lines")
        return sum((line.subtotal for line in self.lines), start=Decimal("0.00"))


@dataclass(frozen=True, slots=True)
class Line:
    product_id: int
    quantity: int
    unit_price: Decimal

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise PricingError(f"quantity must be positive, got {self.quantity}")
        if self.unit_price < 0:
            raise PricingError("unit_price must be non-negative")

    @property
    def subtotal(self) -> Decimal:
        return self.unit_price * self.quantity


def price_order(order: Order, rules: Sequence[DiscountRule]) -> Decimal:
    subtotal = order.total()
    discounted = subtotal
    for rule in rules:
        try:
            discounted = rule.apply(discounted)
        except ValueError as exc:
            raise PricingError(f"discount rule failed: {exc}") from exc
    return max(discounted, Decimal("0.00"))
```

**Correct async: no blocking calls, always a timeout:**

```python
import asyncio
import httpx
import asyncpg


async def fetch_quote(client: httpx.AsyncClient, sku: str) -> dict:
    # timeout is mandatory: an unbounded await is an outage waiting to happen
    resp = await client.get(f"/quotes/{sku}", timeout=httpx.Timeout(2.0, connect=1.0))
    resp.raise_for_status()
    return resp.json()


async def enrich(rows: list[dict], pool: asyncpg.Pool) -> list[dict]:
    async with pool.acquire() as conn:            # pool bounds concurrency
        prices = await conn.fetch("SELECT sku, price_cents FROM price WHERE sku = ANY($1)",
                                  [r["sku"] for r in rows])
    by_sku = {p["sku"]: p["price_cents"] for p in prices}
    return [{**r, "price_cents": by_sku.get(r["sku"], 0)} for r in rows]


async def run_blocking_legacy(path: str) -> bytes:
    # blocking library: push it off the event loop explicitly
    return await asyncio.to_thread(_read_file_sync, path)


def _read_file_sync(path: str) -> bytes:
    with open(path, "rb") as fh:
        return fh.read()


async def gather_bounded(items: list[str], limit: int = 10) -> list[dict]:
    sem = asyncio.Semaphore(limit)

    async def one(sku: str) -> dict:
        async with sem:
            async with httpx.AsyncClient(base_url=BASE) as client:
                return await fetch_quote(client, sku)

    return await asyncio.gather(*(one(i) for i in items))
```

**Streaming instead of loading everything into memory:**

```python
from collections.abc import Iterator
import csv


def iter_rows(path: str) -> Iterator[dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as fh:
        yield from csv.DictReader(fh)          # constant memory for large files


def batched(rows: Iterator[dict[str, str]], size: int = 1000) -> Iterator[list[dict]]:
    batch: list[dict] = []
    for row in rows:
        batch.append(row)
        if len(batch) == size:
            yield batch
            batch = []
    if batch:
        yield batch
```

**Toolchain commands for CI:**

```bash
uv sync --frozen                     # install exactly the lockfile
ruff check . && ruff format --check .
mypy src tests
pytest -m unit -q --cov=orders_service --cov-branch
pip-audit --strict --requirement <(uv export --format requirements-txt) || true
bandit -r src -ll
```

**Profiling a hot path (measure first):**

```bash
# Which functions dominate wall clock in a real workload?
py-spy record -o profile.svg --pid 4821 --duration 30
py-spy top --pid 4821

# Allocation hotspots
python -X tracemalloc=10 -m orders_service.cli export --days 30
```

```python
# Confirm the fix with a benchmark, don't guess
import timeit

setup = "from orders_service.pricing import price_order, Order, Line; from decimal import Decimal"
stmt = "price_order(Order('o1', tuple(Line(i, 2, Decimal('9.99')) for i in range(50))), [])"
print(timeit.repeat(stmt, setup, number=1000, repeat=3))
```

## 8. Quality Standards

- `mypy --strict` (or pyright) passes for new and changed modules; `Any` is justified with a comment.
- ruff lint and format checks pass in CI; no disabled rules without a reason in config.
- No mutable default arguments, bare `except`, or swallowed exceptions.
- Every network await has a timeout; no blocking call inside `async def`.
- Dependencies are lockfile-pinned with hashes; `pip-audit` runs in CI.
- Public functions have type hints and docstrings describing errors raised.
- Large datasets are streamed; memory usage is bounded by design.
- Performance changes are backed by a profile and a benchmark.

## 9. Verification and Testing

```bash
python -W error::DeprecationWarning -m pytest -q     # catch deprecations early
pytest -m unit --cov-branch --cov-fail-under=85
mypy --strict src
python -X dev -m orders_service.cli export --days 1  # dev mode surfaces resource warnings
```

- Run the test suite on the minimum and maximum supported Python versions.
- Verify a fresh `uv sync --frozen` in a clean container reproduces the environment.
- Load-test async endpoints and confirm no `event loop is blocked` warnings and stable latency.
- Check `tracemalloc` peak memory on large-input paths before/after an optimization.

## 10. Security Considerations

- Never `eval`/`exec` untrusted input, and avoid `pickle`/`yaml.load` (use `yaml.safe_load`) for data from outside the process.
- Deserialization and templating are injection points: `subprocess` with `shell=False` and argument lists; parameterized SQL always.
- Secrets come from the environment/secret manager, never hard-coded or logged; scrub exception messages that may include them.
- Pin dependencies with hashes and audit them; a typosquatted package executes on install.
- `assert` statements are removed under `-O`: never use them for security checks.
- Temporary files via `tempfile` with safe permissions; validate any path built from user input to prevent traversal.
- Run services as non-root in containers with a read-only filesystem where possible.

## 11. Failure Handling

- **`ModuleNotFoundError` in production only:** the package is not in `dependencies` or the `src/` layout is missing an `__init__.py`; build and install the wheel in a clean container in CI.
- **Type check slow or noisy on legacy code:** apply `strict` per-module via overrides and ratchet upward; do not disable the whole check.
- **Async endpoint latency spikes:** a blocking call on the event loop — profile with `py-spy` and look for sync DB or file calls.
- **Memory growth over time:** unbounded caches or accumulating task references; use `tracemalloc` and bound caches with `cachetools`.
- **Dependency upgrade breaks the build:** pin back, read the changelog, and upgrade in an isolated PR with the full test suite.

## 12. Expected Deliverables

1. `pyproject.toml` with dependencies, tools, and build configuration.
2. Lockfile and pinned interpreter.
3. Typed public interfaces with Protocol-based boundaries.
4. Async code with timeouts and bounded concurrency.
5. Error taxonomy with domain exceptions.
6. CI pipeline: lint, format, types, tests, audit.
7. Profiling evidence for any performance change.

## 13. References

- Python documentation — https://docs.python.org/3/
- `pyproject.toml` specification — https://packaging.python.org/en/latest/specifications/pyproject-toml/
- mypy documentation — https://mypy.readthedocs.io/
- ruff — https://docs.astral.sh/ruff/
- uv — https://docs.astral.sh/uv/
- asyncio documentation — https://docs.python.org/3/library/asyncio.html
- py-spy — https://github.com/benfred/py-spy
- pip-audit — https://pypi.org/project/pip-audit/
- Python Packaging User Guide — https://packaging.python.org/
