"""BE-022 §35 publication governance telemetry.

Counters and durations for the publication workflow and the public read
surface. Metric labels are strictly bounded closed vocabularies (status,
target_type, blocker, operation) — the spec explicitly forbids user_id,
project_id, evidence_id, claim_id, publication_id, and public_id as
Prometheus labels, so they are never passed through here.
"""

import logging
import time
from contextlib import contextmanager

try:
    from prometheus_client import Counter, Histogram
    PROMETHEUS_AVAILABLE = True
except ImportError:  # pragma: no cover - minimal environments
    PROMETHEUS_AVAILABLE = False

    class Counter:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs): pass
        def labels(self, **kwargs): return self
        def inc(self, amount=1): pass

    class Histogram:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs): pass
        def labels(self, **kwargs): return self
        def observe(self, amount): pass


from backend.core.config import settings


logger = logging.getLogger(__name__)

# Bounded label vocabularies (closed sets from the BE-022 spec).
PUBLICATION_STATUSES = (
    "DRAFT",
    "PENDING_REVIEW",
    "APPROVED",
    "PUBLISHED",
    "UNPUBLISHED",
    "REJECTED",
)
TARGET_TYPES = (
    "PROJECT",
    "ACTIVITY",
    "CLAIM",
    "EVIDENCE",
    "REVIEW_CASE",
    "FUSION_ASSESSMENT",
)
BLOCKERS = (
    "UNAUTHORIZED",
    "NOT_PUBLISHABLE_TYPE",
    "PRIVATE_VISIBILITY",
    "ACTIVE_DISPUTE",
    "UNRESOLVED_CORRECTION",
    "RETENTION_RESTRICTION",
    "LEGAL_HOLD",
    "MISSING_REQUIRED_APPROVAL",
    "SENSITIVE_DATA_PRESENT",
    "SOURCE_RESTRICTION",
    "UNAVAILABLE_PUBLIC_DERIVATIVE",
)

_configured = False
publications_created_total = None
publications_approved_total = None
publications_published_total = None
publications_unpublished_total = None
publication_eligibility_failures_total = None
public_publication_requests_total = None
public_publication_errors_total = None
publication_operation_duration_seconds = None


def _configure() -> None:
    """Create collectors once; no-op when Prometheus is unavailable or the
    feature is disabled (telemetry must never break publication)."""
    global _configured
    global publications_created_total, publications_approved_total
    global publications_published_total, publications_unpublished_total
    global publication_eligibility_failures_total
    global public_publication_requests_total, public_publication_errors_total
    global publication_operation_duration_seconds
    if _configured:
        return
    _configured = True
    if not PROMETHEUS_AVAILABLE or not settings.prometheus_enabled:
        return
    try:
        publications_created_total = Counter(
            "publications_created_total",
            "Publication requests created (by target type)",
            labelnames=["target_type"],
        )
        publications_approved_total = Counter(
            "publications_approved_total",
            "Publications approved (by target type)",
            labelnames=["target_type"],
        )
        publications_published_total = Counter(
            "publications_published_total",
            "Publications published (by target type)",
            labelnames=["target_type"],
        )
        publications_unpublished_total = Counter(
            "publications_unpublished_total",
            "Publications unpublished (by target type)",
            labelnames=["target_type"],
        )
        publication_eligibility_failures_total = Counter(
            "publication_eligibility_failures_total",
            "Releasability evaluations that failed (by structured blocker)",
            labelnames=["blocker"],
        )
        public_publication_requests_total = Counter(
            "public_publication_requests_total",
            "Public read requests served",
        )
        public_publication_errors_total = Counter(
            "public_publication_errors_total",
            "Public read requests that returned an error",
            labelnames=["error_type"],
        )
        publication_operation_duration_seconds = Histogram(
            "publication_operation_duration_seconds",
            "Duration of publication operations",
            labelnames=["operation"],
            buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
        )
    except Exception:
        # A duplicate registration (e.g. test re-import) must never raise.
        logger.exception("publication metrics registration failed")


def _bounded(value: str, allowed: tuple[str, ...], fallback: str) -> str:
    """Coerce a label to a bounded vocabulary member (spec §35)."""
    return value if value in allowed else fallback


def record_publication_created(target_type: str) -> None:
    _configure()
    if publications_created_total is not None:
        publications_created_total.labels(
            target_type=_bounded(target_type, TARGET_TYPES, "PROJECT")
        ).inc()


def record_publication_approved(target_type: str) -> None:
    _configure()
    if publications_approved_total is not None:
        publications_approved_total.labels(
            target_type=_bounded(target_type, TARGET_TYPES, "PROJECT")
        ).inc()


def record_publication_published(target_type: str) -> None:
    _configure()
    if publications_published_total is not None:
        publications_published_total.labels(
            target_type=_bounded(target_type, TARGET_TYPES, "PROJECT")
        ).inc()


def record_publication_unpublished(target_type: str) -> None:
    _configure()
    if publications_unpublished_total is not None:
        publications_unpublished_total.labels(
            target_type=_bounded(target_type, TARGET_TYPES, "PROJECT")
        ).inc()


def record_eligibility_failure(blocker: str) -> None:
    _configure()
    if publication_eligibility_failures_total is not None:
        publication_eligibility_failures_total.labels(
            blocker=_bounded(blocker, BLOCKERS, "SOURCE_RESTRICTION")
        ).inc()


def record_public_request() -> None:
    _configure()
    if public_publication_requests_total is not None:
        public_publication_requests_total.inc()


def record_public_error(error_type: str) -> None:
    _configure()
    if public_publication_errors_total is not None:
        allowed = ("NOT_FOUND", "FORBIDDEN", "SERVER_ERROR")
        public_publication_errors_total.labels(
            error_type=_bounded(error_type, allowed, "SERVER_ERROR")
        ).inc()


@contextmanager
def publication_operation_timer(operation: str):
    """Time one named publication operation; always bounded labels."""
    _configure()
    start = time.perf_counter()
    try:
        yield
    finally:
        duration = time.perf_counter() - start
        if publication_operation_duration_seconds is not None:
            try:
                publication_operation_duration_seconds.labels(operation=str(operation)).observe(
                    duration
                )
            except Exception:
                logger.exception("publication duration observation failed")
