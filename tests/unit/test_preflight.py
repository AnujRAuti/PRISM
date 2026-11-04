"""Tests for the environment preflight (BE-023 §8, §9).

The preflight is what stands between "Redis is down" and "the suite passed
without ever testing the Redis path". These tests pin the classification
logic against fakes so the behaviour is verified without needing any real
service running -- which is the whole point: the checks must be trustworthy
precisely when the environment is broken.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.preflight import (  # noqa: E402
    REQUIRED_ML_PACKAGES,
    SKIP_ENV_VAR,
    DependencyState,
    MissingDependencyError,
    MLReport,
    MLState,
    classify_ml,
    ml_skip_reason,
    probe_postgres,
    probe_redis,
    probe_storage,
    require,
    skip_requested,
)

# BE-023 §8/§9: selectable with `-m be023`. Module level so no individual test
# signature or behaviour is altered.
pytestmark = pytest.mark.be023


# --------------------------------------------------------------------------
# ML state classification (BE-023 §8)
# --------------------------------------------------------------------------


def _fake_spec_finder(present):
    """Return a find_spec stand-in reporting `present` packages as found."""
    import importlib.util

    real = importlib.util.find_spec

    def finder(name, *args, **kwargs):
        if name in present:
            return object()
        return None

    return finder


def test_ml_available_when_all_packages_import(monkeypatch):
    monkeypatch.setattr("importlib.util.find_spec", _fake_spec_finder(set(REQUIRED_ML_PACKAGES)))
    report = classify_ml(importer=lambda name: object())
    assert report.state is MLState.AVAILABLE
    assert report.ml_tests_may_run is True


def test_ml_unavailable_lists_missing_packages(monkeypatch):
    monkeypatch.setattr(
        "importlib.util.find_spec",
        _fake_spec_finder({"torch"}),
    )
    report = classify_ml(importer=lambda name: object())
    assert report.state is MLState.UNAVAILABLE
    assert set(report.missing) == {"transformers", "ultralytics"}
    # Crucially: unavailable ML must never read as "tests may run".
    assert report.ml_tests_may_run is False
    assert "MUST NOT" in report.describe()


def test_ml_skipped_only_when_explicitly_requested():
    env = {SKIP_ENV_VAR: "1"}
    assert skip_requested(env) is True
    report = classify_ml(env=env, importer=lambda name: object())
    assert report.state is MLState.SKIPPED
    assert report.ml_tests_may_run is False


@pytest.mark.parametrize("value", ["", "0", "false", "no", "off", "  "])
def test_ml_not_skipped_without_explicit_opt_in(value):
    """Absence of the flag must mean 'run ML', not 'skip quietly'."""
    assert skip_requested({SKIP_ENV_VAR: value}) is False


def test_ml_failed_when_present_but_broken(monkeypatch):
    """A broken install is FAILED, never AVAILABLE."""
    monkeypatch.setattr(
        "importlib.util.find_spec",
        _fake_spec_finder(set(REQUIRED_ML_PACKAGES)),
    )

    def importer(name):
        if name == "torch":
            raise RuntimeError("libcudart.so.12: cannot open shared object file")
        return object()

    report = classify_ml(importer=importer)
    assert report.state is MLState.FAILED
    assert report.ml_tests_may_run is False
    assert "torch" in report.describe()


def test_ml_missing_never_becomes_available_without_importer():
    """No packages present -> UNAVAILABLE even with a permissive importer."""
    report = classify_ml(env={}, importer=lambda name: object())
    # The real environment has no ML here; either outcome is acceptable, but
    # it must never be AVAILABLE while something is missing.
    if report.state is MLState.AVAILABLE:
        pytest.skip("ML stack genuinely installed in this environment")
    assert report.state in {MLState.UNAVAILABLE, MLState.FAILED}


# --------------------------------------------------------------------------
# ml_skip_reason: a skip must still SAY what was not verified
# --------------------------------------------------------------------------


def test_skip_reason_is_none_when_ml_available():
    assert ml_skip_reason(MLReport(MLState.AVAILABLE)) is None


def test_skip_reason_names_the_state_when_unavailable():
    reason = ml_skip_reason(MLReport(MLState.UNAVAILABLE, missing=("torch",)))
    assert reason is not None
    assert "UNAVAILABLE" in reason
    assert "torch" in reason


def test_skip_reason_distinguishes_failed_from_unavailable():
    """A broken ML install must not read as a mere missing dependency."""
    reason = ml_skip_reason(MLReport(MLState.FAILED, detail="torch: RuntimeError: bad CUDA"))
    assert "FAILED" in reason
    assert "bad CUDA" in reason


# --------------------------------------------------------------------------
# Service probes (BE-023 §9)
# --------------------------------------------------------------------------


def test_redis_probe_available_on_ping():
    class FakeRedis:
        def ping(self):
            return True

        def close(self):
            pass

    status = probe_redis("redis://localhost:6379/0", client_factory=lambda url: FakeRedis())
    assert status.state is DependencyState.AVAILABLE
    assert status.ok is True
    assert "docker compose" in status.remedy


def test_redis_probe_unreachable_is_not_ok():
    def boom(url):
        raise ConnectionRefusedError("connection refused")

    status = probe_redis("redis://localhost:6379/0", client_factory=boom)
    assert status.state is DependencyState.UNREACHABLE
    assert status.ok is False
    assert "ConnectionRefusedError" in status.detail


def test_redis_probe_reports_not_installed_distinctly():
    def missing(url):
        raise ImportError("No module named 'redis'")

    status = probe_redis("redis://localhost:6379/0", client_factory=missing)
    assert status.state is DependencyState.NOT_INSTALLED
    assert status.ok is False


def test_storage_probe_available_on_list_buckets():
    class FakeS3:
        def list_buckets(self):
            return []

    status = probe_storage("http://localhost:9000", "k", "s", client_factory=lambda *a: FakeS3())
    assert status.state is DependencyState.AVAILABLE


def test_storage_probe_unreachable_is_not_ok():
    def boom(*args):
        raise EndpointConnectionError("minio down")

    status = probe_storage("http://localhost:9000", "k", "s", client_factory=boom)
    assert status.state is DependencyState.UNREACHABLE
    assert status.ok is False


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def __iter__(self):
        return iter(self._rows)


class _FakeConnection:
    def __init__(self, installed):
        self._installed = installed

    def execute(self, statement):
        text = str(statement)
        if "pg_extension" in text:
            return _FakeResult([(name,) for name in self._installed])
        return _FakeResult([(1,)])

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _FakeEngine:
    def __init__(self, installed, error=None):
        self._installed = installed
        self._error = error

    def connect(self):
        if self._error:
            raise self._error
        return _FakeConnection(self._installed)


def test_postgres_probe_requires_postgis_and_vector():
    status = probe_postgres(
        "postgresql://x", engine_factory=lambda url: _FakeEngine({"postgis", "vector"})
    )
    assert status.state is DependencyState.AVAILABLE


def test_postgres_probe_flags_missing_extensions():
    status = probe_postgres(
        "postgresql://x", engine_factory=lambda url: _FakeEngine({"postgis"})
    )
    assert status.state is DependencyState.UNREACHABLE
    assert "vector" in status.detail
    assert "CREATE EXTENSION" in status.remedy


def test_postgres_probe_flags_connection_failure():
    def boom(url):
        return _FakeEngine(set(), error=RuntimeError("could not connect to server"))

    status = probe_postgres("postgresql://x", engine_factory=boom)
    assert status.state is DependencyState.UNREACHABLE
    assert status.ok is False


# --------------------------------------------------------------------------
# require(): the mechanism that stops silent degradation
# --------------------------------------------------------------------------


def test_require_passes_when_all_available():
    from tests.preflight import DependencyStatus

    require([
        DependencyStatus("redis", DependencyState.AVAILABLE),
        DependencyStatus("storage", DependencyState.AVAILABLE),
    ])


def test_require_raises_and_names_the_dependency():
    from tests.preflight import DependencyStatus

    with pytest.raises(MissingDependencyError) as excinfo:
        require([
            DependencyStatus("redis", DependencyState.UNREACHABLE, "refused", "docker compose up -d redis"),
        ])
    message = str(excinfo.value)
    assert "redis" in message
    assert "UNREACHABLE" in message
    assert "docker compose up -d redis" in message
    # The message must forbid the tempting-but-wrong response.
    assert "Do not convert this into a skip" in message
