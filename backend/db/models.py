"""SQLAlchemy models for PoA backend (BE-001).

Notes:
- UUID primary keys are used as strings.
- PostGIS `Geometry` is used for location fields (SRID 4326).
- `AnalysisResult.embedding` uses pgvector `Vector(512)` for CLIP embeddings.
"""

import uuid

from sqlalchemy import (
    Column,
    String,
    DateTime,
    ForeignKey,
    Text,
    Boolean,
    Integer,
    func,
    Float,
    CheckConstraint,
    Index,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from pgvector.sqlalchemy import Vector
from sqlalchemy.orm import declarative_base, relationship

from geoalchemy2 import Geometry

Base = declarative_base()


def gen_uuid():
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    username = Column(String(128), unique=True, index=True, nullable=False)
    email = Column(String(256), unique=True, index=True, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Project(Base):
    __tablename__ = "projects"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    name = Column(String(256), index=True, nullable=False)
    owner_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    owner = relationship("User")


class Activity(Base):
    __tablename__ = "activities"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    project_id = Column(UUID(as_uuid=False), ForeignKey("projects.id"), nullable=False)
    actor_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=True)
    verb = Column(String(128), nullable=False)
    details = Column(JSONB)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    project = relationship("Project")
    actor = relationship("User")


class Claim(Base):
    __tablename__ = "claims"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    project_id = Column(UUID(as_uuid=False), ForeignKey("projects.id"), nullable=False)
    claimant_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=True)
    title = Column(String(512), nullable=False)
    description = Column(Text)
    temporal_start_at = Column(DateTime(timezone=True), nullable=True)
    temporal_end_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    project = relationship("Project")
    claimant = relationship("User")


class Evidence(Base):
    __tablename__ = "evidence"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    project_id = Column(UUID(as_uuid=False), ForeignKey("projects.id"), nullable=True)
    claim_id = Column(UUID(as_uuid=False), ForeignKey("claims.id"), nullable=True)
    filename = Column(String(512), nullable=False)
    content_type = Column(String(128))
    storage_key = Column(String(1024), nullable=False, default="legacy/unknown")
    file_size = Column(Integer, nullable=False, default=0)
    status = Column(String(50), nullable=False, default="uploaded_quarantine")
    sha256 = Column(String(64), nullable=True, index=True)
    phash = Column(String(64), nullable=True)
    location = Column(Geometry(geometry_type="POINT", srid=4326), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    project = relationship("Project")
    claim = relationship("Claim")


class EvidenceMetadata(Base):
    __tablename__ = "evidence_metadata"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    evidence_id = Column(UUID(as_uuid=False), ForeignKey("evidence.id"), nullable=False, index=True)
    metadata_json = Column("metadata", JSONB)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    evidence = relationship("Evidence")


class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    evidence_id = Column(UUID(as_uuid=False), ForeignKey("evidence.id"), nullable=False)
    status = Column(String(50), nullable=False, index=True)
    job_type = Column(String(50), nullable=False, server_default="fingerprint", default="fingerprint")
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    attempt_count = Column(Integer, nullable=False, default=0)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    evidence = relationship("Evidence")


class AnalysisResult(Base):
    __tablename__ = "analysis_results"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    job_id = Column(UUID(as_uuid=False), ForeignKey("analysis_jobs.id"), nullable=False)
    result = Column(JSONB)
    embedding = Column(Vector(512), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    job = relationship("AnalysisJob")
    detections = relationship(
        "VisionDetection", back_populates="analysis_result", cascade="all, delete-orphan"
    )


class VisionDetection(Base):
    """BE-009: one row per YOLO detection (normalized 0..1 bounding boxes).

    Individual detections live in a dedicated table rather than an unbounded
    JSON array so they stay queryable; the summary/provenance payload lives
    in the owning ``AnalysisResult.result`` under ``vision_analysis``.
    """

    __tablename__ = "vision_detections"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    analysis_result_id = Column(
        UUID(as_uuid=False),
        ForeignKey("analysis_results.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    class_id = Column(Integer, nullable=False)
    class_name = Column(String(128), nullable=False, index=True)
    confidence = Column(Float, nullable=False)
    x_min = Column(Float, nullable=False)
    y_min = Column(Float, nullable=False)
    x_max = Column(Float, nullable=False)
    y_max = Column(Float, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    analysis_result = relationship("AnalysisResult", back_populates="detections")


class Anomaly(Base):
    __tablename__ = "anomalies"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    evidence_id = Column(UUID(as_uuid=False), ForeignKey("evidence.id"), nullable=False)
    score = Column(Integer)
    details = Column(JSONB)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    evidence = relationship("Evidence")


class DuplicateMatch(Base):
    __tablename__ = "duplicate_matches"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    evidence_id = Column(UUID(as_uuid=False), ForeignKey("evidence.id"), nullable=False)
    matched_evidence_id = Column(UUID(as_uuid=False), ForeignKey("evidence.id"), nullable=False)
    similarity = Column(Integer)
    match_type = Column(String(50), nullable=False, default="candidate")
    phash_distance = Column(Integer, nullable=True)
    embedding_similarity = Column(Float, nullable=True)
    signals = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ReviewDecision(Base):
    __tablename__ = "review_decisions"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    evidence_id = Column(UUID(as_uuid=False), ForeignKey("evidence.id"), nullable=False)
    reviewer_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=True)
    decision = Column(String(50), nullable=False)
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    event_type = Column(String(128), nullable=False)
    actor_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=True)
    payload = Column(JSONB)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# ---------------------------------------------------------------------------
# BE-010 Evidence Graph vocabularies (single source of truth; mirrored by
# CHECK constraints below and by the BE-010 Alembic migration).
# ---------------------------------------------------------------------------

GRAPH_NODE_TYPES = (
    "PROJECT",
    "ACTIVITY",
    "CLAIM",
    "EVIDENCE",
    "ANALYSIS_RESULT",
    "VISION_DETECTION",
    "DUPLICATE_MATCH",
)

GRAPH_RELATIONSHIP_TYPES = (
    "BELONGS_TO",
    "CONTAINS_ACTIVITY",
    "RELATES_TO_CLAIM",
    "SUPPORTS",
    "CONTRADICTS",
    "ASSOCIATED_WITH",
    "DUPLICATE_OF",
    "TEMPORALLY_RELATED_TO",
    "HAS_ANALYSIS",
    "HAS_DETECTION",
    "DERIVED_FROM",
)

GRAPH_RELATIONSHIP_STATUSES = (
    "ACTIVE",
    "SUPERSEDED",
    "INVALIDATED",
)


class GraphNode(Base):
    """BE-010: deterministic identity for an existing domain/intelligence object.

    The node references the underlying row via ``(node_type, entity_id)``
    and never duplicates its payload. ``(node_type, entity_id)`` is unique:
    the same Evidence entity always resolves to the same graph node.
    """

    __tablename__ = "graph_nodes"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    node_type = Column(String(50), nullable=False)
    entity_id = Column(UUID(as_uuid=False), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("node_type", "entity_id", name="uq_graph_node_identity"),
        CheckConstraint(
            "node_type IN ('PROJECT', 'ACTIVITY', 'CLAIM', 'EVIDENCE', "
            "'ANALYSIS_RESULT', 'VISION_DETECTION', 'DUPLICATE_MATCH')",
            name="ck_graph_node_type",
        ),
        Index("ix_graph_nodes_type_entity", "node_type", "entity_id"),
    )


class GraphRelationship(Base):
    """BE-010: a directed, typed, provenance-aware edge between graph nodes.

    Historical record: superseding/invalidating changes status, never deletes.
    ``dedupe_key`` (unique among ACTIVE rows via a partial index in the
    migration) makes same-run re-assertion idempotent while preserving
    history across different analysis runs. Provenance answers where the
    edge came from — never whether it is true.
    """

    __tablename__ = "graph_relationships"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    source_node_id = Column(
        UUID(as_uuid=False),
        ForeignKey("graph_nodes.id", ondelete="RESTRICT"),
        nullable=False,
    )
    target_node_id = Column(
        UUID(as_uuid=False),
        ForeignKey("graph_nodes.id", ondelete="RESTRICT"),
        nullable=False,
    )
    relationship_type = Column(String(50), nullable=False)
    relationship_status = Column(
        String(50), nullable=False, default="ACTIVE", server_default="ACTIVE"
    )
    analysis_run_id = Column(UUID(as_uuid=False), nullable=True)
    method = Column(String(256), nullable=True)
    method_version = Column(String(256), nullable=True)
    dedupe_key = Column(String(512), nullable=False)
    provenance = Column(JSONB, nullable=False, default=dict)
    explanation = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    source_node = relationship("GraphNode", foreign_keys=[source_node_id])
    target_node = relationship("GraphNode", foreign_keys=[target_node_id])

    __table_args__ = (
        CheckConstraint(
            "relationship_type IN ('BELONGS_TO', 'CONTAINS_ACTIVITY', "
            "'RELATES_TO_CLAIM', 'SUPPORTS', 'CONTRADICTS', 'ASSOCIATED_WITH', "
            "'DUPLICATE_OF', 'TEMPORALLY_RELATED_TO', 'HAS_ANALYSIS', "
            "'HAS_DETECTION', 'DERIVED_FROM')",
            name="ck_graph_relationship_type",
        ),
        CheckConstraint(
            "relationship_status IN ('ACTIVE', 'SUPERSEDED', 'INVALIDATED')",
            name="ck_graph_relationship_status",
        ),
        CheckConstraint("source_node_id != target_node_id", name="ck_graph_no_self_loop"),
        Index("ix_graph_relationships_source", "source_node_id"),
        Index("ix_graph_relationships_target", "target_node_id"),
        Index("ix_graph_relationships_type", "relationship_type"),
        Index("ix_graph_relationships_run", "analysis_run_id"),
        Index("ix_graph_relationships_dedupe", "dedupe_key"),
    )


# ---------------------------------------------------------------------------
# BE-011 Fusion Engine vocabularies (single source of truth; mirrored by
# CHECK constraints below and by the BE-011 Alembic migration).
# ---------------------------------------------------------------------------

FUSION_TARGETS = ("CLAIM", "EVIDENCE")

FUSION_RUN_STATUSES = ("RUNNING", "COMPLETED", "FAILED")

FUSION_ASSESSMENT_VALUES = (
    "SUPPORTED",
    "MIXED",
    "CONTRADICTED",
    "INSUFFICIENT_EVIDENCE",
    "UNKNOWN",
)

FUSION_ASSESSMENT_STATUSES = ("ACTIVE", "SUPERSEDED", "INVALIDATED")

FUSION_PRIORITIES = ("LOW", "NORMAL", "HIGH", "URGENT")

FUSION_SIGNAL_STATES = (
    "POSITIVE",
    "NEGATIVE",
    "NEUTRAL",
    "UNKNOWN",
    "UNAVAILABLE",
    "CONFLICTING",
    "NOT_APPLICABLE",
    "NOT_GENERATED",
)

FUSION_METHOD = "deterministic_signal_fusion"
FUSION_METHOD_VERSION = "fusion-v1"
FUSION_DEFAULT_CONFIG_VERSION = "v1"


class FusionConfiguration(Base):
    """BE-011: versioned fusion methodology configuration (weights/thresholds)."""

    __tablename__ = "fusion_configurations"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    version = Column(String(50), nullable=False, unique=True)
    name = Column(String(256), nullable=False)
    enabled = Column(Boolean, nullable=False, default=True, server_default="true")
    method_version = Column(String(50), nullable=False)
    weights = Column(JSONB, nullable=False, default=dict)
    thresholds = Column(JSONB, nullable=False, default=dict)
    priority = Column(JSONB, nullable=False, default=dict)
    signals = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class FusionRun(Base):
    """BE-011: one versioned fusion execution over a target (append-only)."""

    __tablename__ = "fusion_runs"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    target_type = Column(String(50), nullable=False)
    target_id = Column(UUID(as_uuid=False), nullable=False)
    status = Column(String(50), nullable=False, default="RUNNING", server_default="RUNNING")
    method = Column(String(256), nullable=False)
    method_version = Column(String(50), nullable=False)
    configuration_version = Column(String(50), nullable=False)
    input_snapshot = Column(JSONB, nullable=False, default=dict)
    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint("target_type IN ('CLAIM', 'EVIDENCE')", name="ck_fusion_target_type"),
        CheckConstraint(
            "status IN ('RUNNING', 'COMPLETED', 'FAILED')", name="ck_fusion_run_status"
        ),
        Index("ix_fusion_runs_target", "target_type", "target_id"),
        Index("ix_fusion_runs_status", "status"),
        Index("ix_fusion_runs_created", "created_at"),
    )


class FusionSignal(Base):
    """BE-011: one normalized contributing signal of a fusion run."""

    __tablename__ = "fusion_signals"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    fusion_run_id = Column(
        UUID(as_uuid=False),
        ForeignKey("fusion_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    signal_type = Column(String(100), nullable=False)
    state = Column(String(50), nullable=False)
    source = Column(String(256), nullable=False)
    source_entity_id = Column(UUID(as_uuid=False), nullable=True)
    source_analysis_run_id = Column(UUID(as_uuid=False), nullable=True)
    raw_value = Column(JSONB, nullable=True)
    normalized_value = Column(Float, nullable=True)
    weight = Column(Float, nullable=False, default=0.0)
    method = Column(String(256), nullable=False)
    method_version = Column(String(50), nullable=False)
    details = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    run = relationship("FusionRun")

    __table_args__ = (
        CheckConstraint(
            "state IN ('POSITIVE', 'NEGATIVE', 'NEUTRAL', 'UNKNOWN', 'UNAVAILABLE', "
            "'CONFLICTING', 'NOT_APPLICABLE', 'NOT_GENERATED')",
            name="ck_fusion_signal_state",
        ),
        Index("ix_fusion_signals_run", "fusion_run_id"),
        Index("ix_fusion_signals_type", "signal_type"),
    )


class IntegrityAssessment(Base):
    """BE-011: automated evidence-integrity assessment (not a human decision)."""

    __tablename__ = "integrity_assessments"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    fusion_run_id = Column(
        UUID(as_uuid=False),
        ForeignKey("fusion_runs.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    target_type = Column(String(50), nullable=False)
    target_id = Column(UUID(as_uuid=False), nullable=False)
    assessment_status = Column(
        String(50), nullable=False, default="ACTIVE", server_default="ACTIVE"
    )
    assessment_value = Column(String(50), nullable=False)
    integrity_score = Column(Float, nullable=True)
    signal_summary = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    run = relationship("FusionRun")

    __table_args__ = (
        CheckConstraint("target_type IN ('CLAIM', 'EVIDENCE')", name="ck_assessment_target"),
        CheckConstraint(
            "assessment_value IN ('SUPPORTED', 'MIXED', 'CONTRADICTED', "
            "'INSUFFICIENT_EVIDENCE', 'UNKNOWN')",
            name="ck_assessment_value",
        ),
        CheckConstraint(
            "assessment_status IN ('ACTIVE', 'SUPERSEDED', 'INVALIDATED')",
            name="ck_assessment_status",
        ),
        Index("ix_assessments_target", "target_type", "target_id"),
        Index("ix_assessments_run", "fusion_run_id"),
    )


class ReviewPriority(Base):
    """BE-011: operational review-allocation signal (not a fraud ranking)."""

    __tablename__ = "review_priorities"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    fusion_run_id = Column(
        UUID(as_uuid=False),
        ForeignKey("fusion_runs.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    target_type = Column(String(50), nullable=False)
    target_id = Column(UUID(as_uuid=False), nullable=False)
    priority = Column(String(50), nullable=False)
    priority_score = Column(Float, nullable=False)
    signal_summary = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    run = relationship("FusionRun")

    __table_args__ = (
        CheckConstraint("target_type IN ('CLAIM', 'EVIDENCE')", name="ck_priority_target"),
        CheckConstraint(
            "priority IN ('LOW', 'NORMAL', 'HIGH', 'URGENT')", name="ck_priority_value"
        ),
        Index("ix_priorities_target", "target_type", "target_id"),
        Index("ix_priorities_run", "fusion_run_id"),
    )


# ---------------------------------------------------------------------------
# BE-012 Explainability vocabularies (single source of truth; mirrored by
# CHECK constraints below and by the BE-012 Alembic migration).
# ---------------------------------------------------------------------------

EXPLANATION_METHOD = "deterministic_fusion_explanation"
EXPLANATION_METHOD_VERSION = "explanation-v1"

EXPLANATION_RUN_STATUSES = ("GENERATED", "FAILED")


class ExplanationRun(Base):
    """BE-012: one materialized explanation per fusion run (append-only).

    The structured snapshot preserves the explanation exactly as generated,
    so historical explanations stay stable when newer runs, edges, or configs
    appear. Per-signal inputs are NOT duplicated here: the authoritative
    signal rows live in ``fusion_signals`` and are referenced by fusion run.
    """

    __tablename__ = "explanation_runs"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    fusion_run_id = Column(
        UUID(as_uuid=False),
        ForeignKey("fusion_runs.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    status = Column(String(50), nullable=False, default="GENERATED", server_default="GENERATED")
    method = Column(String(256), nullable=False)
    method_version = Column(String(50), nullable=False)
    summary = Column(JSONB, nullable=False, default=dict)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    run = relationship("FusionRun")

    __table_args__ = (
        CheckConstraint(
            "status IN ('GENERATED', 'FAILED')", name="ck_explanation_run_status"
        ),
        Index("ix_explanation_runs_run", "fusion_run_id"),
    )

