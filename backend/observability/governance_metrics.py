"""BE-021 §33 governance telemetry.

Counters and durations for dispute/correction/invalidation/reprocessing
operations. Metric labels are strictly bounded: only closed vocabularies
(cause, category, resolution, outcome, operation name) are ever used as
labels — never user_id, project_id, evidence_id, claim_id, or dispute_id
(those are high-cardinality identifiers, forbidden as labels by the spec).
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

# Bounded label vocabularies (closed sets defined by the BE-021 spec).
CAUSES = ("DISPUTE", "CORRECTION", "DIRECT")
RESOLUTIONS = ("UPHELD", "REJECTED", "INCONCLUSIVE", "INSUFFICIENT_EVIDENCE")
CATEGORIES = (
    "PROJECT_ASSOCIATION",
    "CLAIM_ASSOCIATION",
    "LOCATION_CONTEXT",
    "CONTEXTUAL_METADATA",
    "DESCRIPTIVE_FIELD",
    "EVIDENCE_FILE",
)
REPROCESS_OUTCOMES = ("REPROCESSING_REQUESTED", "REPROCESSING_ALREADY_PENDING", "FAILED")

_configured = False
disputes_created_total = None
disputes_resolved_total = None
correction_requests_total = None
corrections_applied_total = None
intelligence_invalidations_total = None
reprocessing_requests_total = None
reprocessing_failures_total = None
governance_operation_duration_seconds = None


def _configure() -> None:
    """Create the collectors once; no-op when Prometheus is unavailable or
    the feature is disabled (telemetry must never break governance)."""
    global _configured
    global disputes_created_total, disputes_resolved_total
    global correction_requests_total, corrections_applied_total
    global intelligence_invalidations_total
    global reprocessing_requests_total, reprocessing_failures_total
    global governance_operation_duration_seconds
    if _configured:
        return
    _configured = True
    if not PROMETHEUS_AVAILABLE or not settings.prometheus_enabled:
        return
    try:
        disputes_created_total = Counter(
            "disputes_created_total",
            "Disputes created",
        )
        disputes_resolved_total = Counter(
            "disputes_resolved_total",
            "Disputes resolved (by resolution vocabulary)",
            labelnames=["resolution"],
        )
        correction_requests_total = Counter(
            "correction_requests_total",
            "Correction requests created (by category)",
            labelnames=["category"],
        )
        corrections_applied_total = Counter(
            "corrections_applied_total",
            "Corrections applied (by category)",
            labelnames=["category"],
        )
        intelligence_invalidations_total = Counter(
            "intelligence_invalidations_total",
            "Intelligence invalidations (by cause)",
            labelnames=["cause"],
        )
        reprocessing_requests_total = Counter(
            "reprocessing_requests_total",
            "Reprocessing requests (by outcome)",
            labelnames=["outcome"],
        )
        reprocessing_failures_total = Counter(
            "reprocessing_failures_total",
            "Reprocessing request failures",
        )
        governance_operation_duration_seconds = Histogram(
            "governance_operation_duration_seconds",
            "Duration of governance operations",
            labelnames=["operation"],
            buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
        )
    except Exception:
        # A duplicate registration (e.g. test re-import) must never raise.
        logger.exception("governance metrics registration failed")


def record_dispute_created() -> None:
    _configure()
    if disputes_created_total is not None:
        disputes_created_total.inc()


def record_dispute_resolved(resolution: str) -> None:
    _configure()
    if disputes_resolved_total is not None:
        if resolution not in RESOLUTIONS:
            resolution = "INCONCLUSIVE"  # bounded labels only
        disputes_resolved_total.labels(resolution=resolution).inc()


def record_correction_requested(category: str) -> None:
    _configure()
    if correction_requests_total is not None:
        if category not in CATEGORIES:
            category = "CONTEXTUAL_METADATA"
        correction_requests_total.labels(category=category).inc()


def record_correction_applied(category: str) -> None:
    _configure()
    if corrections_applied_total is not None:
        if category not in CATEGORIES:
            category = "CONTEXTUAL_METADATA"
        corrections_applied_total.labels(category=category).inc()


def record_invalidation(cause: str) -> None:
    _configure()
    if intelligence_invalidations_total is not None:
        if cause not in CAUSES:
            cause = "DIRECT"
        intelligence_invalidations_total.labels(cause=cause).inc()


def record_reprocessing(outcome: str) -> None:
    _configure()
    if reprocessing_requests_total is not None:
        if outcome not in REPROCESS_OUTCOMES:
            outcome = "FAILED"
        reprocessing_requests_total.labels(outcome=outcome).inc()


def record_reprocessing_failure() -> None:
    _configure()
    if reprocessing_failures_total is not None:
        reprocessing_failures_total.inc()


@contextmanager
def governance_operation_timer(operation: str):
    """Time one named governance operation; always bounded labels."""
    _configure()
    start = time.perf_counter()
    try:
        yield
    finally:
        duration = time.perf_counter() - start
        if governance_operation_duration_seconds is not None:
            try:
                governance_operation_duration_seconds.labels(operation=str(operation)).observe(
                    duration
                )
            except Exception:
                logger.exception("governance duration observation failed")
