"""Environment preflight for the PoA verification suite (BE-023 §8, §9).

The suite exercises PostgreSQL/PostGIS/pgvector, Redis, MinIO and real ML
(CLIP embeddings, YOLO inference). Each of those can be absent, and the
dangerous failure mode is not a red test -- it is a *green* suite that
quietly verified less than it appears to, because an import failed and a
test skipped itself.

So this module makes dependency state explicit and observable:

* :func:`classify_ml` maps ML import state onto the four states BE-023 §8
  requires -- AVAILABLE / UNAVAILABLE / SKIPPED / FAILED -- and treats them
  as genuinely different outcomes. UNAVAILABLE is a *reported* environment
  fact; it is never laundered into a pass.
* :func:`probe_redis` / :func:`probe_storage` / :func:`probe_postgres`
  return a structured :class:`DependencyStatus` instead of raising, so the
  report can name exactly what is wrong and how to start it.
* :func:`require` turns an unmet *required* dependency into a loud failure
  carrying an actionable message.

Nothing here fabricates success. A probe that cannot reach a service
reports UNREACHABLE, and a missing ML stack reports UNAVAILABLE with the
list of what was looked for.
"""

from __future__ import annotations

import importlib
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Iterable

# --------------------------------------------------------------------------
# ML state (BE-023 §8)
# --------------------------------------------------------------------------


class MLState(str, Enum):
    """The four ML outcomes BE-023 requires the suite to distinguish.

    AVAILABLE   -- every required ML package imported; tests must really run.
    UNAVAILABLE -- a required ML package is missing. This is an environment
                  fact to be reported, never silently converted into a pass.
    SKIPPED     -- the operator explicitly opted out (POA_SKIP_ML_TESTS=1).
    FAILED      -- ML is installed but importing/initialising it raised. This
                  is a real defect and is reported as a failure.
    """

    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"


#: Packages required for the real ML paths. Versions are pinned in
#: requirements.txt; they are listed here only so the failure message can
#: name what is missing.
REQUIRED_ML_PACKAGES: tuple[str, ...] = ("torch", "transformers", "ultralytics")

#: Set to "1"/"true"/"yes" to deliberately opt out of ML tests. The default is
#: to attempt them, so a broken ML install is surfaced rather than hidden.
SKIP_ENV_VAR = "POA_SKIP_ML_TESTS"

_TRUTHY = {"1", "true", "yes", "on"}


def skip_requested(env: dict | None = None) -> bool:
    """True if the operator explicitly asked to skip ML tests."""
    source = env if env is not None else os.environ
    return str(source.get(SKIP_ENV_VAR, "")).strip().lower() in _TRUTHY


@dataclass(frozen=True)
class MLReport:
    """Outcome of the ML preflight, with enough detail to act on."""

    state: MLState
    missing: tuple[str, ...] = ()
    import_errors: tuple[str, ...] = ()
    detail: str = ""

    @property
    def ml_tests_may_run(self) -> bool:
        """Only AVAILABLE permits ML tests to execute for real."""
        return self.state is MLState.AVAILABLE

    def describe(self) -> str:
        if self.state is MLState.AVAILABLE:
            return f"ML {self.state.value}: all of {', '.join(REQUIRED_ML_PACKAGES)} importable"
        if self.state is MLState.UNAVAILABLE:
            return (
                f"ML {self.state.value}: missing {', '.join(self.missing)}. "
                "ML-dependent tests cannot verify anything and MUST NOT be "
                "reported as passing. Install the pinned requirements."
            )
        if self.state is MLState.SKIPPED:
            return f"ML {self.state.value}: {SKIP_ENV_VAR} is set; ML tests are excluded by request."
        return f"ML {self.state.value}: {self.detail}"


def classify_ml(
    env: dict | None = None,
    importer: Callable[[str], object] = importlib.import_module,
) -> MLReport:
    """Determine the ML state without importing torch eagerly.

    ``importlib.util.find_spec`` is used for detection because importing
    torch is slow and has side effects; the caller may still import for
    real. A package that is *present but broken* surfaces as FAILED via
    ``importer`` being exercised in :func:`run_ml_preflight`.
    """
    if skip_requested(env):
        return MLReport(state=MLState.SKIPPED, detail=f"{SKIP_ENV_VAR} set")

    import importlib.util

    missing = []
    for package in REQUIRED_ML_PACKAGES:
        try:
            if importlib.util.find_spec(package) is None:
                missing.append(package)
        except (ImportError, ValueError):
            # A package whose parent cannot be imported is, for our
            # purposes, missing.
            missing.append(package)

    if missing:
        return MLReport(state=MLState.UNAVAILABLE, missing=tuple(missing))

    # Everything is present. Prove it actually imports: a broken install
    # (e.g. torch present but failing on a missing CUDA library) is FAILED,
    # not AVAILABLE.
    errors = []
    for package in REQUIRED_ML_PACKAGES:
        try:
            importer(package)
        except Exception as exc:  # noqa: BLE001 - any import failure is a real defect
            errors.append(f"{package}: {type(exc).__name__}: {exc}")
    if errors:
        return MLReport(
            state=MLState.FAILED,
            import_errors=tuple(errors),
            detail="; ".join(errors),
        )
    return MLReport(state=MLState.AVAILABLE)


# --------------------------------------------------------------------------
# Service dependencies (BE-023 §9)
# --------------------------------------------------------------------------


class DependencyState(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNREACHABLE = "UNREACHABLE"
    NOT_INSTALLED = "NOT_INSTALLED"
    SKIPPED = "SKIPPED"


@dataclass(frozen=True)
class DependencyStatus:
    """Structured result of probing one external dependency."""

    name: str
    state: DependencyState
    detail: str = ""
    remedy: str = ""

    @property
    def ok(self) -> bool:
        return self.state is DependencyState.AVAILABLE

    def describe(self) -> str:
        suffix = f" -- {self.remedy}" if self.remedy else ""
        return f"{self.name}: {self.state.value} ({self.detail}){suffix}"


class MissingDependencyError(RuntimeError):
    """A required dependency is not available; the suite refuses to lie."""


def probe_redis(url: str, *, client_factory: Callable[[str], object] | None = None) -> DependencyStatus:
    """Ping Redis, reporting rather than raising."""
    remedy = "Start it with: docker compose up -d redis"
    try:
        if client_factory is not None:
            client = client_factory(url)
        else:
            import redis  # noqa: PLC0415 - optional dependency, imported on demand

            client = redis.from_url(url)
        client.ping()
        try:
            client.close()
        except Exception:  # noqa: BLE001 - close failure is irrelevant to reachability
            pass
        return DependencyStatus("redis", DependencyState.AVAILABLE, "PING responded", remedy)
    except ImportError as exc:
        return DependencyStatus("redis", DependencyState.NOT_INSTALLED, str(exc), remedy)
    except Exception as exc:  # noqa: BLE001 - any connection error is UNREACHABLE
        return DependencyStatus(
            "redis", DependencyState.UNREACHABLE, f"{type(exc).__name__}: {exc}", remedy
        )


def probe_storage(
    endpoint: str,
    access_key: str,
    secret_key: str,
    region: str = "us-east-1",
    *,
    client_factory: Callable[..., object] | None = None,
) -> DependencyStatus:
    """List MinIO/S3 buckets to confirm the object store is really usable."""
    remedy = "Start it with: docker compose up -d minio minio-init"
    try:
        if client_factory is not None:
            client = client_factory(endpoint, access_key, secret_key, region)
        else:
            import boto3  # noqa: PLC0415 - optional dependency, imported on demand

            client = boto3.client(
                "s3",
                endpoint_url=endpoint,
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
                region_name=region,
            )
        client.list_buckets()
        return DependencyStatus("storage", DependencyState.AVAILABLE, "list_buckets succeeded", remedy)
    except ImportError as exc:
        return DependencyStatus("storage", DependencyState.NOT_INSTALLED, str(exc), remedy)
    except Exception as exc:  # noqa: BLE001 - any client error is UNREACHABLE
        return DependencyStatus(
            "storage", DependencyState.UNREACHABLE, f"{type(exc).__name__}: {exc}", remedy
        )


def probe_postgres(
    url: str,
    *,
    engine_factory: Callable[[str], object] | None = None,
) -> DependencyStatus:
    """Confirm PostgreSQL is reachable and PostGIS + pgvector are installed."""
    remedy = (
        "Start it with: docker compose up -d db, then create the test database "
        "and enable: CREATE EXTENSION postgis; CREATE EXTENSION vector;"
    )
    try:
        if engine_factory is not None:
            # Injected engine (tests). Plain strings keep this path free of a
            # SQLAlchemy import so the probe logic is verifiable on its own.
            def _sql(statement: str):
                return statement

            engine = engine_factory(url)
        else:
            from sqlalchemy import create_engine, text  # noqa: PLC0415

            def _sql(statement: str):
                return text(statement)

            engine = create_engine(url)

        with engine.connect() as connection:
            connection.execute(_sql("SELECT 1"))
            installed = {
                row[0]
                for row in connection.execute(
                    _sql("SELECT extname FROM pg_extension")
                )
            }
    except Exception as exc:  # noqa: BLE001 - connection/permission errors are UNREACHABLE
        return DependencyStatus(
            "postgres", DependencyState.UNREACHABLE, f"{type(exc).__name__}: {exc}", remedy
        )

    missing = sorted({"postgis", "vector"} - installed)
    if missing:
        return DependencyStatus(
            "postgres",
            DependencyState.UNREACHABLE,
            f"reachable but missing extensions: {', '.join(missing)}",
            remedy,
        )
    return DependencyStatus(
        "postgres", DependencyState.AVAILABLE, "connected; postgis + vector present", remedy
    )


def require(statuses: Iterable[DependencyStatus], *, context: str = "integration tests") -> None:
    """Raise if any required dependency is not available.

    This is the mechanism that stops a missing service from turning into a
    silently reduced test run.
    """
    failures = [s for s in statuses if not s.ok]
    if not failures:
        return
    detail = "\n".join(f"  - {s.describe()}" for s in failures)
    raise MissingDependencyError(
        f"Required dependencies are not available for {context}:\n{detail}\n"
        "Fix the environment, or select only the tests that do not need these "
        "services. Do not convert this into a skip that reports success."
    )


def ml_skip_reason(report: MLReport | None = None) -> str | None:
    """Return a skip reason when ML tests may not run, else ``None``.

    BE-023 §8 requires ML TEST SKIPPED to be a *distinguished, reported*
    state rather than an anonymous skip. Tests that genuinely cannot run
    without ML should call this and skip with the returned text, so the
    pytest report says "ML UNAVAILABLE: missing torch" instead of just
    "skipped".

    This deliberately does NOT convert a skip into a pass. An environment
    without ML is a real limitation of what was verified, and the message
    says so.
    """
    state = report if report is not None else classify_ml()
    if state.ml_tests_may_run:
        return None
    return state.describe()


@dataclass
class PreflightReport:
    """Aggregate view of everything the preflight learned."""

    database: str = ""
    ml: MLReport | None = None
    dependencies: list[DependencyStatus] = field(default_factory=list)

    def lines(self) -> list[str]:
        out = [f"database: {self.database}"]
        if self.ml is not None:
            out.append(self.ml.describe())
        out.extend(s.describe() for s in self.dependencies)
        return out
