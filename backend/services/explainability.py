"""BE-012 deterministic Explainability Engine (presentation, not analysis).

Reads persisted BE-011 fusion outputs (and the BE-010/BE-004..BE-009 rows
they reference) and renders a structured, traceable explanation of how an
automated result was produced. It never recalculates analytical outputs,
never invents provenance, and never produces truth/fraud determinations.

Anti-drift guarantees:

- The rule label is derived with BE-011's own ``decide_assessment``
  function (same rule, not a competing one) and its outcome must equal the
  persisted assessment value; any mismatch raises instead of explaining.
- Numeric contributions reuse persisted ``normalized_value`` × ``weight``.
- The priority band shown is checked against persisted thresholds/score.

Conventions: ``ValueError`` for semantic failures (incl. the explicit
``EXPLANATION_UNAVAILABLE`` state for FAILED fusion runs), ``LookupError``
for missing rows.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.db.models import (
    EXPLANATION_METHOD,
    EXPLANATION_METHOD_VERSION,
    Evidence,
)
from backend.repositories import explainability as explain_repo
from backend.services import fusion as fusion_service


logger = logging.getLogger(__name__)

METHOD = EXPLANATION_METHOD
METHOD_VERSION = EXPLANATION_METHOD_VERSION

BAND_ORDER = ("LOW", "NORMAL", "HIGH", "URGENT")

# Static unknown-state sentences. Placeholders are filled only from
# persisted facts (signal type, entity id); no reasons are invented.
UNKNOWN_SENTENCES = {
    "LOCATION_UNKNOWN": (
        "No location was recorded for evidence {entity}; "
        "spatial presence was therefore unknown, not negative."
    ),
    "TEMPORAL_UNKNOWN": (
        "Temporal consistency was not evaluated for evidence {entity} "
        "because the required source timestamp was unavailable."
    ),
    "TEMPORAL_WINDOW_UNKNOWN": (
        "Claim-window placement was not evaluated for evidence {entity} "
        "because required timestamps or claim bounds were unavailable."
    ),
    "DUPLICATE_UNKNOWN": (
        "Duplicate observation for evidence {entity} was inconclusive."
    ),
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _require_uuid(value: str, label: str) -> str:
    from uuid import UUID

    try:
        return str(UUID(str(value)))
    except (ValueError, AttributeError, TypeError) as error:
        raise ValueError(f"Invalid {label}: {value!r}") from error


def describe_rule(signal_states: list[str]) -> tuple[str, str, str]:
    """Name the BE-011 assessment rule for a set of persisted signal states.

    Returns ``(rule_id, rule_version, outcome)`` where the outcome is
    produced by BE-011's own ``decide_assessment`` (same rule, reused).
    """
    states = set(signal_states)
    # Outcome reuses BE-011's own rule (same function, same methodology);
    # only the human-stable rule label is assigned here.
    outcome = fusion_service.decide_assessment([{"state": state} for state in states])
    if not states:
        rule_id = "NO_SIGNALS"
    elif "CONFLICTING" in states:
        rule_id = "CONFLICTING_INPUTS"
    elif "POSITIVE" in states and "NEGATIVE" in states:
        rule_id = "POSITIVE_AND_NEGATIVE"
    elif "NEGATIVE" in states:
        rule_id = "NEGATIVE_ONLY"
    elif "POSITIVE" in states:
        rule_id = "POSITIVE_ONLY"
    elif states & {"UNKNOWN", "UNAVAILABLE"}:
        rule_id = "UNKNOWN_INPUTS_ONLY"
    else:
        rule_id = "NEUTRAL_ONLY"
    return rule_id, fusion_service.METHOD_VERSION, outcome


def contribution_of(normalized: float | None, weight: float) -> float:
    """Presentation of two persisted numbers (documented, deterministic)."""
    return round(float(normalized or 0.0) * float(weight or 0.0), 3)


def unknown_sentence(signal_type: str, entity_id: str | None) -> str:
    template = UNKNOWN_SENTENCES.get(
        signal_type,
        "No usable observation for {signal} on {entity}; state preserved as recorded.",
    )
    return template.format(
        entity=entity_id or "unknown entity", signal=signal_type
    )


def build_summary(
    *,
    assessment_value: str,
    priority: str,
    priority_score: float,
    counts: dict[str, int],
    top_contributors: list[dict],
    unknown_count: int,
) -> str:
    """Deterministic template summary assembled only from structured facts."""
    parts = [
        f"The target received an automated integrity assessment of {assessment_value} "
        f"with review priority {priority} (allocation score {priority_score:.3f})."
    ]
    pos = counts.get("POSITIVE", 0)
    neg = counts.get("NEGATIVE", 0)
    if pos and neg:
        parts.append(
            f"Positive and negative evidence signals were both present "
            f"({pos} positive, {neg} negative); neither side was discarded."
        )
    elif neg:
        parts.append(f"Negative evidence signals were present ({neg}); no positive signals were recorded.")
    elif pos:
        parts.append(f"Positive evidence signals were present ({pos}); no negative signals were recorded.")
    else:
        parts.append("No positive or negative evidence signals were recorded.")
    if top_contributors:
        rendered = "; ".join(
            f"{item['signal_type']} ({item['contribution']:+.3f})"
            for item in top_contributors[:3]
        )
        parts.append(f"Largest score contributions: {rendered}.")
    if unknown_count:
        parts.append(
            f"{unknown_count} input(s) were unknown or unavailable and were "
            f"preserved as such rather than treated as negative."
        )
    parts.append(
        "This is an automated assessment state and an operational prioritization signal; "
        "neither determines truth, fraud, or authenticity."
    )
    return " ".join(parts)


def _signal_entries(signals) -> list[dict]:
    """Render persisted fusion signals with contributions (deterministic order)."""
    entries = []
    for row in signals:
        normalized = row.normalized_value
        weight = float(row.weight or 0.0)
        entries.append(
            {
                "signal_type": row.signal_type,
                "state": row.state,
                "source": row.source,
                "source_entity_id": row.source_entity_id,
                "source_analysis_run_id": row.source_analysis_run_id,
                "raw_value": row.raw_value,
                "normalized_value": normalized,
                "weight": weight,
                "contribution": contribution_of(normalized, weight),
                "method": row.method,
                "method_version": row.method_version,
                "details": dict(row.details or {}),
                "included": row.state in ("POSITIVE", "NEGATIVE", "NEUTRAL", "CONFLICTING"),
                "reason": (
                    "APPLIED_TO_SCORE"
                    if row.state in ("POSITIVE", "NEGATIVE") and weight > 0.0
                    else (
                        "RECORDED_ZERO_WEIGHT"
                        if row.state in ("POSITIVE", "NEGATIVE", "NEUTRAL", "CONFLICTING")
                        else f"{row.state}_STATE"
                    )
                ),
            }
        )
    entries.sort(
        key=lambda e: (
            -abs(e["contribution"]),
            e["signal_type"],
            str(e["source_entity_id"] or ""),
        )
    )
    return entries


def _resolve_edge_lineage(db: Session, entries: list[dict]) -> None:
    """Attach bounded graph provenance to entries referencing edges (in place)."""
    edge_ids: list[str] = []
    for entry in entries:
        raw = entry["raw_value"] if isinstance(entry["raw_value"], dict) else {}
        for key in ("graph_edge_id", "edge_id"):
            if raw.get(key):
                edge_ids.append(str(raw[key]))
    edges = explain_repo.bulk_relationships(db, edge_ids)
    nodes = explain_repo.bulk_nodes(
        db,
        [node_id for edge in edges.values() for node_id in (edge.source_node_id, edge.target_node_id)],
    )
    by_edge_id: dict[str, dict] = {}
    for edge_id, edge in edges.items():
        source, target = nodes.get(edge.source_node_id), nodes.get(edge.target_node_id)
        by_edge_id[edge_id] = {
            "edge_id": edge.id,
            "relationship_type": edge.relationship_type,
            "status_at_fusion_time": "ACTIVE",
            "current_status": edge.relationship_status,
            "source": {"node_type": source.node_type, "entity_id": source.entity_id}
            if source
            else None,
            "target": {"node_type": target.node_type, "entity_id": target.entity_id}
            if target
            else None,
            "method": edge.method,
            "method_version": edge.method_version,
            "analysis_run_id": edge.analysis_run_id,
            "provenance": dict(edge.provenance or {}),
        }
    for entry in entries:
        raw = entry["raw_value"] if isinstance(entry["raw_value"], dict) else {}
        for key in ("graph_edge_id", "edge_id"):
            if raw.get(key) and str(raw[key]) in by_edge_id:
                entry["lineage"] = {"kind": "graph_relationship", **by_edge_id[str(raw[key])]}
                break
        else:
            entry["lineage"] = {
                "kind": "analytical_output",
                "source": entry["source"],
                "source_entity_id": entry["source_entity_id"],
                "source_analysis_run_id": entry["source_analysis_run_id"],
                "method": entry["method"],
                "method_version": entry["method_version"],
            }


def _resolve_cross_project(db: Session, entries: list[dict]) -> None:
    """Flag duplicate-pair signals spanning projects (bounded, read-only)."""
    pairs = []
    for entry in entries:
        raw = entry["raw_value"] if isinstance(entry["raw_value"], dict) else {}
        pair = raw.get("evidence_pair")
        if isinstance(pair, list) and len(pair) == 2:
            pairs.append((entry, [str(pair[0]), str(pair[1])]))
    if not pairs:
        return
    wanted = sorted({entity for _, pair in pairs for entity in pair})
    rows = db.query(Evidence.id, Evidence.project_id).filter(Evidence.id.in_(wanted)).all()
    projects = {str(row[0]): (str(row[1]) if row[1] else None) for row in rows}
    for entry, pair in pairs:
        entry_projects = {projects.get(entity) for entity in pair} - {None}
        entry["lineage"]["cross_project"] = len(entry_projects) > 1
        entry["lineage"]["evidence_projects"] = sorted(entry_projects)


def build_explanation(db: Session, fusion_run_id: str) -> dict:
    """Assemble the structured explanation for one fusion run (read-only).

    Raises ``LookupError`` for unknown runs and ``ValueError`` with the
    explicit ``EXPLANATION_UNAVAILABLE`` state for FAILED runs or missing
    outputs — failures never become successful explanations.
    """
    fusion_run_id = _require_uuid(fusion_run_id, "fusion_run_id")
    bundle = explain_repo.get_fusion_bundle(db, fusion_run_id)
    if bundle is None:
        raise LookupError(f"Fusion run not found: {fusion_run_id}")
    run, signals, assessment, priority, config = bundle
    if run.status == "FAILED":
        raise ValueError(
            f"EXPLANATION_UNAVAILABLE: fusion run {fusion_run_id} FAILED "
            f"({run.error or 'no error recorded'})"
        )
    if assessment is None or priority is None:
        raise ValueError(
            f"EXPLANATION_UNAVAILABLE: fusion run {fusion_run_id} has no persisted outputs"
        )
    if config is None:
        raise ValueError(
            f"EXPLANATION_UNAVAILABLE: configuration {run.configuration_version} not found"
        )

    entries = _signal_entries(signals)
    _resolve_edge_lineage(db, entries)
    _resolve_cross_project(db, entries)

    rule_id, rule_version, rule_outcome = describe_rule([e["state"] for e in entries])
    if rule_outcome != assessment.assessment_value:
        raise RuntimeError(
            "Explanation drift detected: rule outcome "
            f"{rule_outcome!r} != persisted assessment {assessment.assessment_value!r}"
        )

    thresholds = config.thresholds or {}
    band = (
        "LOW"
        if priority.priority_score < float(thresholds["low_max"])
        else "NORMAL"
        if priority.priority_score < float(thresholds["normal_max"])
        else "HIGH"
        if priority.priority_score < float(thresholds["high_max"])
        else "URGENT"
    )
    if band != priority.priority:
        raise RuntimeError(
            "Explanation drift detected: priority band "
            f"{band!r} != persisted priority {priority.priority!r}"
        )

    weights = config.weights or {}
    involved_weights = {
        signal_type: weights[signal_type]
        for signal_type in sorted({e["signal_type"] for e in entries})
        if signal_type in weights
    }
    unknowns = [
        {
            "signal_type": e["signal_type"],
            "state": e["state"],
            "source_entity_id": e["source_entity_id"],
            "sentence": unknown_sentence(e["signal_type"], e["source_entity_id"]),
        }
        for e in entries
        if e["state"] in ("UNKNOWN", "UNAVAILABLE", "NOT_APPLICABLE", "NOT_GENERATED")
    ]
    counts: dict[str, int] = {}
    for e in entries:
        counts[e["state"]] = counts.get(e["state"], 0) + 1
    top = [e for e in entries if e["contribution"] != 0.0]
    summary_text = build_summary(
        assessment_value=assessment.assessment_value,
        priority=priority.priority,
        priority_score=float(priority.priority_score),
        counts=counts,
        top_contributors=top,
        unknown_count=len(unknowns),
    )
    priority_cfg = config.priority or {}
    contributions = priority_cfg.get("contributions", {})
    priority_trace = {
        "base": priority_cfg.get("base"),
        "bands": {
            "low_max": thresholds.get("low_max"),
            "normal_max": thresholds.get("normal_max"),
            "high_max": thresholds.get("high_max"),
        },
        "observed_score": float(priority.priority_score),
        "observed_band": priority.priority,
        "drivers": [
            {
                "signal_type": signal_type,
                "count": sum(1 for e in entries if e["signal_type"] == signal_type),
                "per_unit": contributions.get(signal_type, 0.0),
            }
            for signal_type in sorted(
                {e["signal_type"] for e in entries} & set(contributions)
            )
        ],
    }
    return {
        "fusion_run_id": run.id,
        "target": {"target_type": run.target_type, "target_id": run.target_id},
        "integrity_assessment": {
            "value": assessment.assessment_value,
            "status": assessment.assessment_status,
            "integrity_score": assessment.integrity_score,
        },
        "review_priority": {
            "priority": priority.priority,
            "priority_score": float(priority.priority_score),
        },
        "methodology": {
            "fusion_method": run.method,
            "fusion_method_version": run.method_version,
            "explanation_method": METHOD,
            "explanation_method_version": METHOD_VERSION,
            "configuration_version": run.configuration_version,
        },
        "configuration": {
            "version": config.version,
            "method_version": config.method_version,
            "weights": involved_weights,
            "thresholds": dict(thresholds),
            "priority_bands": priority_trace["bands"],
        },
        "summary": {"text": summary_text, "state_counts": counts},
        "signals": entries,
        "rules": [
            {
                "rule_id": rule_id,
                "rule_version": rule_version,
                "triggered": True,
                "result": rule_outcome,
                "parameters": {"signal_states": sorted({e["state"] for e in entries})},
            }
        ],
        "priority_trace": priority_trace,
        "unknowns": unknowns,
        "provenance": {
            "fusion_run_id": run.id,
            "fusion_started_at": run.started_at.isoformat() if run.started_at else None,
            "fusion_completed_at": run.completed_at.isoformat() if run.completed_at else None,
        },
        "generated_at": utc_now().isoformat(),
    }


def materialize_explanation(db: Session, fusion_run_id: str) -> tuple[dict, bool]:
    """Persist the explanation snapshot for a run (idempotent per run).

    Returns ``(explanation_dict, created)``. A second call returns the
    stored snapshot content enriched with the explanation id — historical
    records never change.
    """
    from sqlalchemy.exc import IntegrityError

    fusion_run_id = _require_uuid(fusion_run_id, "fusion_run_id")
    existing = explain_repo.get_explanation(db, fusion_run_id)
    if existing is not None:
        content = dict(existing.summary or {})
        content["explanation_id"] = existing.id
        content["materialized"] = True
        return content, False
    content = build_explanation(db, fusion_run_id)
    try:
        row = explain_repo.insert_explanation(
            db,
            fusion_run_id=fusion_run_id,
            method=METHOD,
            method_version=METHOD_VERSION,
            summary={k: v for k, v in content.items() if k != "generated_at"},
        )
        row.completed_at = utc_now()
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = explain_repo.get_explanation(db, fusion_run_id)
        if existing is not None:
            content = dict(existing.summary or {})
            content["explanation_id"] = existing.id
            content["materialized"] = True
            return content, False
        raise
    db.refresh(row)
    logger.info("explanation materialized fusion_run_id=%s", fusion_run_id)
    content["explanation_id"] = row.id
    content["materialized"] = True
    return content, True


def latest_for_target(db: Session, target_type: str, target_id: str) -> dict:
    """Build the explanation for a target's latest COMPLETED fusion run."""
    if target_type not in fusion_service.TARGETS:
        raise ValueError(f"Unsupported fusion target type: {target_type!r}")
    target_id = _require_uuid(target_id, "target_id")
    run, assessment, priority = fusion_service.get_latest(db, target_type, target_id)
    if run is None or assessment is None or priority is None:
        raise LookupError(f"No fusion assessment found for {target_type}:{target_id}")
    return build_explanation(db, run.id)
