"""BE-011 deterministic Fusion Engine (versioned signals, no ML).

Consumes real BE-004/BE-006/BE-007/BE-008/BE-009/BE-010 outputs and produces
two independent outputs: an Integrity Assessment (automated assessment state,
never a truth/fraud verdict) and a Review Priority (operational allocation,
never a fraud ranking).

Methodology ``deterministic_signal_fusion`` / ``fusion-v1``:

- Signals are extracted from persisted analytical outputs and ACTIVE graph
  edges only. FAILED runs leave no output rows and therefore contribute
  nothing; COMPLETED-with-zero-observations contributes an explicit
  zero/unknown signal. Missing data is NEVER negative by default.
- Same (signal_type, source, source_entity, analysis_run) identity folds to
  ONE signal (no double counting across DuplicateMatch rows and the
  DUPLICATE_OF edges that reference them; latest ACTIVE edge wins).
- ``integrity_score`` in [-1, 1] = weighted mean over applied signals
  (POSITIVE=+1, NEGATIVE=-1; NEUTRAL/UNKNOWN/CONFLICTING carry no score
  weight). Rounded to 3 decimals. It is a documented aggregation, not a
  probability.
- ``assessment_value`` follows an explicit presence rule (see
  ``decide_assessment``), with SUPPORTS+CONTRADICTS coexistence yielding
  MIXED per the configured conflict policy.
- ``priority_score`` in [0, 1] = clamped base + configured contributions.
  Bands LOW/NORMAL/HIGH/URGENT are configuration.

Conventions: ``ValueError`` for invalid input/configuration,
``LookupError`` for missing targets/rows. One commit per successful run
(transactional); failures leave a FAILED run row, never partial outputs.
"""

import logging
import time
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.db.models import (
    FUSION_ASSESSMENT_STATUSES,
    FUSION_ASSESSMENT_VALUES,
    FUSION_METHOD,
    FUSION_METHOD_VERSION,
    FUSION_DEFAULT_CONFIG_VERSION,
    FUSION_PRIORITIES,
    FUSION_RUN_STATUSES,
    FUSION_SIGNAL_STATES,
    FUSION_TARGETS,
    AnalysisJob,
    AnalysisResult,
    Claim,
    DuplicateMatch,
    Evidence,
    FusionRun,
    IntegrityAssessment,
    ReviewPriority,
)
from backend.repositories import fusion as fusion_repo
from backend.services import audit_ledger as audit_service
from backend.services import evidence_graph as graph_service
from backend.services.temporal_intelligence import analyze_single
from backend.services.vision_intelligence import get_latest_vision_result


logger = logging.getLogger(__name__)

TARGETS = frozenset(FUSION_TARGETS)
RUN_STATUSES = frozenset(FUSION_RUN_STATUSES)
ASSESSMENT_VALUES = frozenset(FUSION_ASSESSMENT_VALUES)
ASSESSMENT_STATUSES = frozenset(FUSION_ASSESSMENT_STATUSES)
PRIORITIES = frozenset(FUSION_PRIORITIES)
SIGNAL_STATES = frozenset(FUSION_SIGNAL_STATES)

METHOD = FUSION_METHOD
METHOD_VERSION = FUSION_METHOD_VERSION
DEFAULT_CONFIG_VERSION = FUSION_DEFAULT_CONFIG_VERSION

STATE_VALUES = {"POSITIVE": 1.0, "NEGATIVE": -1.0}

# Canonical V1 signal types and their documented semantics.
SIGNAL_TYPES = frozenset(
    {
        "GRAPH_SUPPORT",
        "GRAPH_CONTRADICT",
        "GRAPH_CONFLICT",
        "GRAPH_ASSOCIATION",
        "DUPLICATE_EXACT",
        "DUPLICATE_SIMILAR",
        "DUPLICATE_UNKNOWN",
        "TEMPORAL_CONSISTENT",
        "TEMPORAL_INCONSISTENT",
        "TEMPORAL_UNKNOWN",
        "TEMPORAL_WINDOW_IN",
        "TEMPORAL_WINDOW_OUT",
        "TEMPORAL_WINDOW_UNKNOWN",
        "TEMPORAL_PAIR",
        "VISION_OBSERVED",
        "VISION_EMPTY",
        "PROJECT_LINKED",
        "LOCATION_PRESENT",
        "LOCATION_UNKNOWN",
    }
)

SUPPORT_FAMILY = {"SUPPORTS"}
CONTRADICT_FAMILY = {"CONTRADICTS"}
ASSOC_FAMILY = {"ASSOCIATED_WITH", "RELATES_TO_CLAIM"}

DEFAULT_CONFIG_V1: dict = {
    "version": "v1",
    "name": "fusion-v1 defaults",
    "method_version": METHOD_VERSION,
    "weights": {
        "GRAPH_SUPPORT": 0.30,
        "GRAPH_CONTRADICT": 0.30,
        "GRAPH_CONFLICT": 0.30,
        "DUPLICATE_EXACT": 0.40,
        "DUPLICATE_SIMILAR": 0.25,
        "TEMPORAL_CONSISTENT": 0.20,
        "TEMPORAL_INCONSISTENT": 0.35,
        "TEMPORAL_WINDOW_IN": 0.15,
        "TEMPORAL_WINDOW_OUT": 0.30,
        "GRAPH_ASSOCIATION": 0.0,
        "DUPLICATE_UNKNOWN": 0.0,
        "TEMPORAL_UNKNOWN": 0.0,
        "TEMPORAL_WINDOW_UNKNOWN": 0.0,
        "TEMPORAL_PAIR": 0.0,
        "VISION_OBSERVED": 0.0,
        "VISION_EMPTY": 0.0,
        "PROJECT_LINKED": 0.0,
        "LOCATION_PRESENT": 0.0,
        "LOCATION_UNKNOWN": 0.0,
    },
    "thresholds": {"low_max": 0.25, "normal_max": 0.5, "high_max": 0.75},
    "priority": {
        "base": 0.10,
        "contributions": {
            "GRAPH_CONTRADICT": 0.25,
            "GRAPH_CONFLICT": 0.25,
            "DUPLICATE_EXACT": 0.30,
            "DUPLICATE_SIMILAR": 0.15,
            "TEMPORAL_INCONSISTENT": 0.30,
            "TEMPORAL_WINDOW_OUT": 0.20,
        },
        "unknown_each": 0.05,
        "unknown_cap": 0.20,
    },
    "signals": {"enabled": sorted(SIGNAL_TYPES)},
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _require_uuid(value: str, label: str) -> str:
    from uuid import UUID

    try:
        return str(UUID(str(value)))
    except (ValueError, AttributeError, TypeError) as error:
        raise ValueError(f"Invalid {label}: {value!r}") from error


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def validate_configuration(config: dict) -> dict:
    """Validate a fusion configuration mapping (fail clearly, never clamp)."""
    if not isinstance(config, dict):
        raise ValueError("Fusion configuration must be a mapping")
    if config.get("method_version") != METHOD_VERSION:
        raise ValueError(
            f"Unsupported methodology version: {config.get('method_version')!r}"
        )
    weights = config.get("weights")
    if not isinstance(weights, dict) or not weights:
        raise ValueError("Fusion configuration requires a non-empty 'weights' mapping")
    unknown_types = set(weights) - SIGNAL_TYPES
    if unknown_types:
        raise ValueError(f"Unknown signal types in weights: {sorted(unknown_types)}")
    for signal_type, weight in weights.items():
        if not isinstance(weight, (int, float)) or not 0.0 <= float(weight) <= 1.0:
            raise ValueError(f"Weight for {signal_type!r} must be a number in [0, 1]")
    thresholds = config.get("thresholds")
    if not isinstance(thresholds, dict):
        raise ValueError("Fusion configuration requires a 'thresholds' mapping")
    try:
        low, normal, high = (
            float(thresholds["low_max"]),
            float(thresholds["normal_max"]),
            float(thresholds["high_max"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("Thresholds require numeric low_max/normal_max/high_max") from error
    if not 0.0 <= low < normal < high <= 1.0:
        raise ValueError("Thresholds must satisfy 0 <= low_max < normal_max < high_max <= 1")
    priority = config.get("priority")
    if not isinstance(priority, dict):
        raise ValueError("Fusion configuration requires a 'priority' mapping")
    try:
        base = float(priority.get("base", 0.0))
        unknown_each = float(priority.get("unknown_each", 0.0))
        unknown_cap = float(priority.get("unknown_cap", 0.0))
    except (TypeError, ValueError) as error:
        raise ValueError("Priority base/unknown_each/unknown_cap must be numeric") from error
    if not 0.0 <= base <= 1.0:
        raise ValueError("Priority base must be in [0, 1]")
    if unknown_each < 0.0 or unknown_cap < 0.0:
        raise ValueError("Priority unknown_each/unknown_cap must be >= 0")
    contributions = priority.get("contributions", {})
    if not isinstance(contributions, dict):
        raise ValueError("Priority contributions must be a mapping")
    for signal_type, value in contributions.items():
        if signal_type not in SIGNAL_TYPES:
            raise ValueError(f"Unknown signal type in priority contributions: {signal_type!r}")
        if not isinstance(value, (int, float)) or float(value) < 0.0:
            raise ValueError(f"Priority contribution for {signal_type!r} must be >= 0")
    enabled = (config.get("signals") or {}).get("enabled", sorted(SIGNAL_TYPES))
    if not isinstance(enabled, list) or not enabled:
        raise ValueError("Configuration 'signals.enabled' must be a non-empty list")
    unknown_enabled = set(enabled) - SIGNAL_TYPES
    if unknown_enabled:
        raise ValueError(f"Unknown enabled signal types: {sorted(unknown_enabled)}")
    return config


def get_configuration(db: Session, version: str | None = None) -> dict:
    """Fetch and validate a stored configuration (default v1, created once)."""
    version = version or DEFAULT_CONFIG_VERSION
    row = fusion_repo.get_configuration(db, version)
    if row is None:
        if version != DEFAULT_CONFIG_VERSION:
            raise LookupError(f"Fusion configuration not found: {version}")
        row = fusion_repo.insert_configuration(
            db,
            version=DEFAULT_CONFIG_V1["version"],
            name=DEFAULT_CONFIG_V1["name"],
            method_version=DEFAULT_CONFIG_V1["method_version"],
            weights=dict(DEFAULT_CONFIG_V1["weights"]),
            thresholds=dict(DEFAULT_CONFIG_V1["thresholds"]),
            priority={
                "base": DEFAULT_CONFIG_V1["priority"]["base"],
                "contributions": dict(DEFAULT_CONFIG_V1["priority"]["contributions"]),
                "unknown_each": DEFAULT_CONFIG_V1["priority"]["unknown_each"],
                "unknown_cap": DEFAULT_CONFIG_V1["priority"]["unknown_cap"],
            },
            signals={"enabled": list(DEFAULT_CONFIG_V1["signals"]["enabled"])},
            enabled=True,
        )
        db.commit()
        db.refresh(row)
    if not row.enabled:
        raise ValueError(f"Fusion configuration is disabled: {version}")
    return validate_configuration(
        {
            "version": row.version,
            "name": row.name,
            "method_version": row.method_version,
            "weights": dict(row.weights or {}),
            "thresholds": dict(row.thresholds or {}),
            "priority": dict(row.priority or {}),
            "signals": dict(row.signals or {}),
        }
    )


def create_configuration(
    db: Session,
    *,
    version: str,
    name: str,
    weights: dict,
    thresholds: dict,
    priority: dict,
    signals: dict | None = None,
    method_version: str = METHOD_VERSION,
    enabled: bool = True,
):
    """Store a new versioned configuration (validated; versions immutable)."""
    if not version or not str(version).strip():
        raise ValueError("Configuration version is required")
    if fusion_repo.get_configuration(db, version) is not None:
        raise ValueError(f"Fusion configuration already exists: {version}")
    payload = validate_configuration(
        {
            "version": version,
            "name": name,
            "method_version": method_version,
            "weights": weights,
            "thresholds": thresholds,
            "priority": priority,
            "signals": signals if signals is not None else {"enabled": sorted(SIGNAL_TYPES)},
        }
    )
    row = fusion_repo.insert_configuration(
        db,
        version=payload["version"],
        name=name,
        method_version=payload["method_version"],
        weights=payload["weights"],
        thresholds=payload["thresholds"],
        priority=payload["priority"],
        signals=payload["signals"],
        enabled=enabled,
    )
    db.commit()
    db.refresh(row)
    return row


# ---------------------------------------------------------------------------
# Pure calculation (unit-testable without a database)
# ---------------------------------------------------------------------------


def normalize_state_value(state: str) -> float | None:
    """Map a signal state to its score contribution (None = excluded)."""
    return STATE_VALUES.get(state)


def decide_assessment(signals: list[dict]) -> str:
    """Explicit presence rule over signal states (documented conflict policy)."""
    if not signals:
        return "INSUFFICIENT_EVIDENCE"
    states = {item["state"] for item in signals}
    has_pos = bool(states & {"POSITIVE"})
    has_neg = bool(states & {"NEGATIVE"})
    if "CONFLICTING" in states or (has_pos and has_neg):
        return "MIXED"
    if has_neg:
        return "CONTRADICTED"
    if has_pos:
        return "SUPPORTED"
    if "UNKNOWN" in states or "UNAVAILABLE" in states:
        return "UNKNOWN"
    return "INSUFFICIENT_EVIDENCE"


def compute_integrity_score(signals: list[dict], weights: dict) -> float | None:
    """Weighted mean over applied signals; None when nothing applies."""
    total_weight = 0.0
    total = 0.0
    for item in signals:
        value = normalize_state_value(item["state"])
        weight = float(weights.get(item["signal_type"], 0.0))
        item["weight"] = weight
        if value is None or weight <= 0.0:
            continue
        total_weight += weight
        total += weight * value
    if total_weight <= 0.0:
        return None
    return round(total / total_weight, 3)


def compute_priority(signals: list[dict], priority_config: dict, thresholds: dict) -> tuple[str, float]:
    """Operational priority band + score (allocation only, never fraud odds)."""
    base = float(priority_config.get("base", 0.0))
    contributions = priority_config.get("contributions", {})
    unknown_each = float(priority_config.get("unknown_each", 0.0))
    unknown_cap = float(priority_config.get("unknown_cap", 0.0))
    counts: dict[str, int] = {}
    for item in signals:
        counts[item["signal_type"]] = counts.get(item["signal_type"], 0) + 1
    score = base
    for signal_type, count in counts.items():
        score += float(contributions.get(signal_type, 0.0)) * count
    unknowns = sum(
        counts.get(state_type, 0)
        for state_type in ("TEMPORAL_UNKNOWN", "TEMPORAL_WINDOW_UNKNOWN", "LOCATION_UNKNOWN",
                           "DUPLICATE_UNKNOWN")
    )
    score += min(unknowns * unknown_each, unknown_cap)
    score = round(min(max(score, 0.0), 1.0), 3)
    low, normal, high = (
        float(thresholds["low_max"]),
        float(thresholds["normal_max"]),
        float(thresholds["high_max"]),
    )
    if score < low:
        return "LOW", score
    if score < normal:
        return "NORMAL", score
    if score < high:
        return "HIGH", score
    return "URGENT", score


def summarize_signals(signals: list[dict]) -> dict:
    by_type: dict[str, dict[str, int]] = {}
    for item in signals:
        entry = by_type.setdefault(item["signal_type"], {"count": 0, "states": {}})
        entry["count"] += 1
        entry["states"][item["state"]] = entry["states"].get(item["state"], 0) + 1
    return {
        "signal_count": len(signals),
        "by_type": {
            signal_type: {"count": entry["count"], "states": entry["states"]}
            for signal_type, entry in sorted(by_type.items())
        },
    }


# ---------------------------------------------------------------------------
# Signal extraction (consumes persisted outputs; never recalculates them)
# ---------------------------------------------------------------------------


def _signal(
    signal_type: str,
    state: str,
    source: str,
    *,
    source_entity_id: str | None = None,
    source_analysis_run_id: str | None = None,
    raw_value: dict | None = None,
    details: dict | None = None,
) -> dict:
    if signal_type not in SIGNAL_TYPES:
        raise ValueError(f"Unknown signal type: {signal_type!r}")
    if state not in SIGNAL_STATES:
        raise ValueError(f"Unknown signal state: {state!r}")
    return {
        "signal_type": signal_type,
        "state": state,
        "source": source,
        "source_entity_id": source_entity_id,
        "source_analysis_run_id": source_analysis_run_id,
        "raw_value": raw_value,
        "normalized_value": normalize_state_value(state),
        "weight": 0.0,
        "method": METHOD,
        "method_version": METHOD_VERSION,
        "details": details or {},
    }


def _claim_evidences(db: Session, claim_id: str) -> list[str]:
    """Evidence for a claim: domain FK union ACTIVE claim-directed graph edges."""
    domain_ids = {
        str(row[0])
        for row in db.query(Evidence.id).filter(Evidence.claim_id == claim_id).all()
    }
    graph_ids: set[str] = set()
    for rel_type in ("SUPPORTS", "CONTRADICTS", "ASSOCIATED_WITH", "RELATES_TO_CLAIM"):
        rows, _ = graph_service.list_for_entity(
            db, "CLAIM", claim_id, direction="incoming", relationship_type=rel_type,
            relationship_status="ACTIVE", limit=1000, offset=0,
        )
        for row in rows:
            node = row.source_node
            if node.node_type == "EVIDENCE":
                graph_ids.add(str(node.entity_id))
    return sorted(domain_ids | graph_ids)


def _newest(rows: list):
    """Latest row by (created_at, id); None when empty (deterministic)."""
    if not rows:
        return None
    return max(rows, key=lambda row: (str(row.created_at), str(row.id)))


def _claim_graph_signals(db: Session, claim_id: str, evidence_ids: list[str]) -> list[dict]:
    """Fold ACTIVE claim-directed edges per (evidence, family); conflicts kept."""
    signals: list[dict] = []
    node_cache: dict[str, object] = {}

    def evidence_node(evidence_id: str):
        if evidence_id not in node_cache:
            node_cache[evidence_id] = graph_service.resolve_node(
                db, "EVIDENCE", evidence_id, create=False
            )
        return node_cache[evidence_id]

    for evidence_id in evidence_ids:
        node = evidence_node(evidence_id)
        if node is None:
            continue
        families: dict[str, list] = {"SUPPORTS": [], "CONTRADICTS": [], "ASSOC": []}
        for rel_type in ("SUPPORTS", "CONTRADICTS", "ASSOCIATED_WITH", "RELATES_TO_CLAIM"):
            rows, _ = graph_service.list_for_entity(
                db, "EVIDENCE", evidence_id, direction="outgoing",
                relationship_type=rel_type, relationship_status="ACTIVE",
                limit=1000, offset=0,
            )
            for row in rows:
                if row.target_node.node_type != "CLAIM" or str(row.target_node.entity_id) != claim_id:
                    continue
                family = (
                    "SUPPORTS" if rel_type in SUPPORT_FAMILY
                    else "CONTRADICTS" if rel_type in CONTRADICT_FAMILY else "ASSOC"
                )
                families[family].append(row)
        support = _newest(families["SUPPORTS"])
        contradict = _newest(families["CONTRADICTS"])
        assoc = sorted(families["ASSOC"], key=lambda r: (str(r.created_at), str(r.id)))
        if support is not None and contradict is not None and str(support.analysis_run_id) != str(
            contradict.analysis_run_id
        ):
            signals.append(
                _signal(
                    "GRAPH_CONFLICT", "CONFLICTING", "evidence_graph",
                    source_entity_id=evidence_id,
                    raw_value={"support_run": support.analysis_run_id,
                               "contradict_run": contradict.analysis_run_id},
                    details={"evidence_id": evidence_id, "claim_id": claim_id},
                )
            )
        else:
            if support is not None:
                signals.append(
                    _signal(
                        "GRAPH_SUPPORT", "POSITIVE", "evidence_graph",
                        source_entity_id=evidence_id,
                        source_analysis_run_id=support.analysis_run_id,
                        raw_value={"relationship": "SUPPORTS", "edge_id": support.id},
                        details={"evidence_id": evidence_id, "claim_id": claim_id},
                    )
                )
            if contradict is not None:
                signals.append(
                    _signal(
                        "GRAPH_CONTRADICT", "NEGATIVE", "evidence_graph",
                        source_entity_id=evidence_id,
                        source_analysis_run_id=contradict.analysis_run_id,
                        raw_value={"relationship": "CONTRADICTS", "edge_id": contradict.id},
                        details={"evidence_id": evidence_id, "claim_id": claim_id},
                    )
                )
        for edge in assoc:
            signals.append(
                _signal(
                    "GRAPH_ASSOCIATION", "NEUTRAL", "evidence_graph",
                    source_entity_id=evidence_id,
                    source_analysis_run_id=edge.analysis_run_id,
                    raw_value={"relationship": edge.relationship_type, "edge_id": edge.id},
                    details={"evidence_id": evidence_id, "claim_id": claim_id},
                )
            )
    return signals


def _duplicate_signals(db: Session, evidence_ids: list[str]) -> list[dict]:
    """One signal per underlying duplicate fact (match rows and graph edges fold)."""
    by_pair: dict[tuple[str, str], dict] = {}
    matches = (
        db.query(DuplicateMatch)
        .filter(
            DuplicateMatch.evidence_id.in_(evidence_ids)
            | DuplicateMatch.matched_evidence_id.in_(evidence_ids)
        )
        .order_by(DuplicateMatch.created_at, DuplicateMatch.id)
        .all()
    )
    for match in matches:
        pair = (str(min(match.evidence_id, match.matched_evidence_id)),
                str(max(match.evidence_id, match.matched_evidence_id)))
        entry = by_pair.setdefault(pair, {"match": None, "edge": None})
        entry["match"] = match
    for evidence_id in evidence_ids:
        rows, _ = graph_service.list_for_entity(
            db, "EVIDENCE", evidence_id, direction="both",
            relationship_type="DUPLICATE_OF", relationship_status="ACTIVE",
            limit=1000, offset=0,
        )
        for row in rows:
            other = (
                row.target_node.entity_id
                if str(row.source_node.entity_id) == evidence_id
                else row.source_node.entity_id
            )
            pair = (str(min(evidence_id, str(other))), str(max(evidence_id, str(other))))
            entry = by_pair.setdefault(pair, {"match": None, "edge": None})
            # Latest ACTIVE edge wins (deterministic: traversal already orders
            # newest-first, so keep the first seen per pair).
            if entry["edge"] is None:
                entry["edge"] = row
    signals: list[dict] = []
    for (first, second), entry in sorted(by_pair.items()):
        match, edge = entry["match"], entry["edge"]
        run_id = None
        if edge is not None and edge.analysis_run_id:
            run_id = str(edge.analysis_run_id)
        if match is not None:
            match_type = match.match_type or "candidate"
            if match_type == "sha256":
                signal_type, state = "DUPLICATE_EXACT", "NEGATIVE"
            elif match_type in ("phash", "embedding"):
                signal_type, state = "DUPLICATE_SIMILAR", "NEGATIVE"
            else:
                signal_type, state = "DUPLICATE_UNKNOWN", "UNKNOWN"
            signals.append(
                _signal(
                    signal_type, state, "duplicate_intelligence",
                    source_entity_id=first,
                    source_analysis_run_id=run_id,
                    raw_value={
                        "match_type": match_type,
                        "phash_distance": match.phash_distance,
                        "embedding_similarity": match.embedding_similarity,
                        "duplicate_match_id": match.id,
                        "graph_edge_id": edge.id if edge is not None else None,
                        "evidence_pair": [first, second],
                    },
                    details={"note": "match row and graph edge folded to one fact"},
                )
            )
        elif edge is not None:
            signals.append(
                _signal(
                    "DUPLICATE_SIMILAR", "NEGATIVE", "evidence_graph",
                    source_entity_id=first,
                    source_analysis_run_id=run_id,
                    raw_value={"graph_edge_id": edge.id, "evidence_pair": [first, second]},
                    details={"note": "graph-only duplicate reference"},
                )
            )
    return signals


def _temporal_signals(db: Session, evidence_ids: list[str], claim_id: str | None) -> list[dict]:
    """BE-008 verdicts via the BE-008 service (consumed, never recomputed)."""
    signals: list[dict] = []
    for evidence_id in sorted(evidence_ids):
        try:
            result = analyze_single(evidence_id, db)
        except LookupError:
            continue
        capture = result.get("capture_upload")
        if capture == "TEMPORALLY_CONSISTENT":
            signals.append(_signal("TEMPORAL_CONSISTENT", "POSITIVE", "temporal_intelligence",
                                   source_entity_id=evidence_id,
                                   raw_value={"capture_upload": capture}))
        elif capture == "TEMPORAL_INCONSISTENCY":
            signals.append(_signal("TEMPORAL_INCONSISTENT", "NEGATIVE", "temporal_intelligence",
                                   source_entity_id=evidence_id,
                                   raw_value={"capture_upload": capture}))
        else:
            signals.append(_signal("TEMPORAL_UNKNOWN", "UNKNOWN", "temporal_intelligence",
                                   source_entity_id=evidence_id,
                                   raw_value={"capture_upload": capture}))
        window = result.get("claim_window")
        if claim_id is not None and result.get("claim_id") == claim_id:
            if window == "WITHIN_CLAIM_WINDOW":
                signals.append(_signal("TEMPORAL_WINDOW_IN", "POSITIVE", "temporal_intelligence",
                                       source_entity_id=evidence_id,
                                       raw_value={"claim_window": window}))
            elif window in ("BEFORE_CLAIM_WINDOW", "AFTER_CLAIM_WINDOW"):
                signals.append(_signal("TEMPORAL_WINDOW_OUT", "NEGATIVE", "temporal_intelligence",
                                       source_entity_id=evidence_id,
                                       raw_value={"claim_window": window}))
            else:
                signals.append(_signal("TEMPORAL_WINDOW_UNKNOWN", "UNKNOWN", "temporal_intelligence",
                                       source_entity_id=evidence_id,
                                       raw_value={"claim_window": window}))
    # Pairwise orderings already recorded as ACTIVE graph edges (either direction).
    seen_pairs: set[tuple[str, str]] = set()
    for evidence_id in sorted(evidence_ids):
        rows, _ = graph_service.list_for_entity(
            db, "EVIDENCE", evidence_id, direction="both",
            relationship_type="TEMPORALLY_RELATED_TO", relationship_status="ACTIVE",
            limit=1000, offset=0,
        )
        for row in rows:
            other = (
                row.target_node.entity_id
                if str(row.source_node.entity_id) == evidence_id
                else row.source_node.entity_id
            )
            pair = (str(min(evidence_id, str(other))), str(max(evidence_id, str(other))))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            signals.append(
                _signal("TEMPORAL_PAIR", "NEUTRAL", "evidence_graph",
                        source_entity_id=pair[0],
                        source_analysis_run_id=row.analysis_run_id,
                        raw_value={"evidence_pair": list(pair), "edge_id": row.id},
                        details={"temporal_relationship": (row.provenance or {}).get(
                            "temporal_relationship")})
            )
    return signals


def _vision_signals(db: Session, evidence_ids: list[str]) -> list[dict]:
    """Latest BE-009 observations per evidence (YOLO confidence is not truth)."""
    signals: list[dict] = []
    for evidence_id in sorted(evidence_ids):
        result = get_latest_vision_result(evidence_id, db)
        if result is None:
            continue
        payload = result.result if isinstance(result.result, dict) else {}
        count = int(payload.get("detection_count", 0) or 0)
        job_id = result.job_id
        if count > 0:
            signals.append(
                _signal("VISION_OBSERVED", "NEUTRAL", "vision_intelligence",
                        source_entity_id=evidence_id, source_analysis_run_id=job_id,
                        raw_value={"detection_count": count,
                                   "model": (payload.get("model") or {}).get("name")},
                        details={"note": "detections are model observations, not verdicts"})
            )
        else:
            signals.append(
                _signal("VISION_EMPTY", "NEUTRAL", "vision_intelligence",
                        source_entity_id=evidence_id, source_analysis_run_id=job_id,
                        raw_value={"detection_count": 0},
                        details={"note": "completed analysis with zero observations"})
            )
    return signals


def _spatial_signals(db: Session, evidence_ids: list[str]) -> list[dict]:
    """BE-007 domain facts (association/location presence, never new geo math)."""
    signals: list[dict] = []
    rows = db.query(Evidence).filter(Evidence.id.in_(sorted(evidence_ids))).all()
    for evidence in sorted(rows, key=lambda e: str(e.id)):
        if evidence.project_id is not None:
            signals.append(_signal("PROJECT_LINKED", "NEUTRAL", "project_context",
                                   source_entity_id=evidence.id,
                                   raw_value={"project_id": str(evidence.project_id)}))
        if evidence.location is not None:
            signals.append(_signal("LOCATION_PRESENT", "NEUTRAL", "project_context",
                                   source_entity_id=evidence.id,
                                   raw_value={"has_location": True}))
        else:
            # Missing GPS stays UNKNOWN: absence is not negative evidence.
            signals.append(_signal("LOCATION_UNKNOWN", "UNKNOWN", "project_context",
                                   source_entity_id=evidence.id,
                                   raw_value={"has_location": False}))
    return signals


def extract_signals(db: Session, target_type: str, target_id: str) -> list[dict]:
    """Collect + fold all eligible signals for a target (deterministic order)."""
    if target_type == "CLAIM":
        if db.query(Claim.id).filter(Claim.id == target_id).one_or_none() is None:
            raise LookupError(f"CLAIM not found: {target_id}")
        evidence_ids = _claim_evidences(db, target_id)
        claim_id: str | None = target_id
    elif target_type == "EVIDENCE":
        if db.query(Evidence.id).filter(Evidence.id == target_id).one_or_none() is None:
            raise LookupError(f"EVIDENCE not found: {target_id}")
        evidence_ids = [target_id]
        claim_id = None
    else:
        raise ValueError(f"Unsupported fusion target type: {target_type!r}")
    signals: list[dict] = []
    if target_type == "CLAIM":
        signals.extend(_claim_graph_signals(db, target_id, evidence_ids))
    signals.extend(_duplicate_signals(db, evidence_ids))
    signals.extend(_temporal_signals(db, evidence_ids, claim_id))
    signals.extend(_vision_signals(db, evidence_ids))
    signals.extend(_spatial_signals(db, evidence_ids))
    signals.sort(key=lambda s: (s["signal_type"], str(s["source_entity_id"] or ""),
                                str(s["source_analysis_run_id"] or "")))
    return signals


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


def run_fusion(
    db: Session,
    target_type: str,
    target_id: str,
    *,
    configuration_version: str | None = None,
) -> tuple[FusionRun, IntegrityAssessment, ReviewPriority, list[dict]]:
    """Execute one fusion run synchronously (append-only; failures are FAILED).

    Each call is a new execution by documented contract; identical inputs
    yield identical values (determinism), never shared rows (history).
    """
    if target_type not in TARGETS:
        raise ValueError(f"Unsupported fusion target type: {target_type!r}")
    target_id = _require_uuid(target_id, "target_id")
    config = get_configuration(db, configuration_version)
    enabled = set((config.get("signals") or {}).get("enabled", []))

    run = fusion_repo.insert_run(
        db,
        target_type=target_type,
        target_id=target_id,
        method=METHOD,
        method_version=METHOD_VERSION,
        configuration_version=config["version"],
        input_snapshot={"target_type": target_type, "target_id": target_id,
                        "configuration_version": config["version"],
                        "method_version": METHOD_VERSION},
    )
    db.flush()
    extract_started = time.perf_counter()
    try:
        signals = [s for s in extract_signals(db, target_type, target_id)
                   if s["signal_type"] in enabled]
        extract_ms = (time.perf_counter() - extract_started) * 1000.0
        compute_started = time.perf_counter()
        value = decide_assessment(signals)
        score = compute_integrity_score(signals, config["weights"])
        priority, priority_score = compute_priority(
            signals, config["priority"], config["thresholds"])
        compute_ms = (time.perf_counter() - compute_started) * 1000.0
        summary = summarize_signals(signals)
        run.input_snapshot = {
            **run.input_snapshot,
            "signal_count": len(signals),
            "signal_summary": summary,
            "extract_ms": round(extract_ms, 2),
            "compute_ms": round(compute_ms, 2),
        }
        fusion_repo.insert_signals(db, run.id, signals)
        assessment = fusion_repo.insert_assessment(
            db, run_id=run.id, target_type=target_type, target_id=target_id,
            value=value, score=score, signal_summary=summary)
        priority_row = fusion_repo.insert_priority(
            db, run_id=run.id, target_type=target_type, target_id=target_id,
            priority=priority, score=priority_score, signal_summary=summary)
        fusion_repo.supersede_prior_outputs(db, target_type, target_id, run.id)
        run.status = "COMPLETED"
        run.completed_at = utc_now()
        audit_service.append_event(
            db,
            event_type="FUSION_RUN_CREATED",
            action="run",
            resource_type="fusion_runs",
            resource_id=run.id,
            actor_id=None,
            project_id=None,
            payload={"fusion_run_id": run.id, "target_type": target_type,
                     "target_id": target_id, "assessment": value,
                     "priority": priority,
                     "configuration_version": run.configuration_version},
            source="fusion_service",
        )
        try:
            from backend.services import webhook as webhook_service

            webhook_service.enqueue_webhook_event(
                db,
                event_type="fusion.completed",
                aggregate_type="FUSION_RUN",
                aggregate_id=str(run.id),
                project_id=None,
                data={
                    "fusion_run_id": str(run.id),
                    "target_type": target_type,
                    "target_id": target_id,
                    "assessment": value,
                    "priority": priority,
                },
            )
        except Exception as exc:
            logger.warning("Failed to emit webhook for fusion run %s: %s", run.id, exc)
        db.commit()
    except Exception as error:
        db.rollback()
        failed = fusion_repo.insert_run(
            db, target_type=target_type, target_id=target_id, method=METHOD,
            method_version=METHOD_VERSION,
            configuration_version=config.get("version", DEFAULT_CONFIG_VERSION),
            input_snapshot={"target_type": target_type, "target_id": target_id},
        )
        failed.status = "FAILED"
        failed.error = f"{type(error).__name__}: {error}"
        failed.completed_at = utc_now()
        db.commit()
        logger.exception("fusion run failed target=%s:%s", target_type, target_id)
        raise
    db.refresh(run)
    logger.info("fusion run completed run_id=%s target=%s:%s assessment=%s priority=%s",
                run.id, target_type, target_id, value, priority)
    return run, assessment, priority_row, signals


def get_latest(db: Session, target_type: str, target_id: str):
    """Latest COMPLETED run with ACTIVE outputs (None-triple when absent)."""
    if target_type not in TARGETS:
        raise ValueError(f"Unsupported fusion target type: {target_type!r}")
    target_id = _require_uuid(target_id, "target_id")
    return fusion_repo.latest_outputs(db, target_type, target_id)


def get_run_detail(db: Session, run_id: str):
    """Run + signals + outputs for one execution (LookupError when missing)."""
    run_id = _require_uuid(run_id, "run_id")
    run = fusion_repo.get_run(db, run_id)
    if run is None:
        raise LookupError(f"Fusion run not found: {run_id}")
    signals = fusion_repo.signals_for_run(db, run_id)
    assessment = (
        db.query(IntegrityAssessment)
        .filter(IntegrityAssessment.fusion_run_id == run_id).one_or_none()
    )
    priority = (
        db.query(ReviewPriority)
        .filter(ReviewPriority.fusion_run_id == run_id).one_or_none()
    )
    return run, signals, assessment, priority


def run_history(
    db: Session, target_type: str, target_id: str, *,
    status: str | None = None, limit: int = 50, offset: int = 0,
) -> tuple[list[FusionRun], int]:
    """Paginated run history, newest first (deterministic tiebreak)."""
    if target_type not in TARGETS:
        raise ValueError(f"Unsupported fusion target type: {target_type!r}")
    if status is not None and status not in RUN_STATUSES:
        raise ValueError(f"Unknown fusion run status: {status!r}")
    if limit < 1 or offset < 0:
        raise ValueError("Invalid pagination")
    target_id = _require_uuid(target_id, "target_id")
    query = fusion_repo.run_history_query(db, target_type, target_id, status)
    return query.offset(offset).limit(limit).all(), query.count()
