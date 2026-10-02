"""SQLAlchemy models for PoA backend (BE-001).

Notes:
- UUID primary keys are used as strings.
- PostGIS `Geometry` is used for location fields (SRID 4326).
- `AnalysisResult.embedding` uses pgvector `Vector(512)` for CLIP embeddings.
"""

import uuid

from sqlalchemy import (
    BigInteger,
    Column,
    String,
    DateTime,
    ForeignKey,
    Text,
    Boolean,
    Integer,
    func,
    Float,
    Numeric,
    CheckConstraint,
    Index,
    UniqueConstraint,
    text,
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
    # BE-016 identity fields. external_subject is only unique together with
    # its identity_provider (never a global identifier on its own).
    external_subject = Column(String(512), nullable=True)
    identity_provider = Column(String(128), nullable=False, default="local",
                               server_default="local")
    display_name = Column(String(256), nullable=True)
    status = Column(String(50), nullable=False, default="ACTIVE", server_default="ACTIVE")
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("identity_provider", "external_subject",
                         name="uq_user_identity_subject"),
        CheckConstraint("status IN ('ACTIVE', 'SUSPENDED', 'DISABLED')",
                        name="ck_user_status"),
    )


class Project(Base):
    __tablename__ = "projects"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    name = Column(String(256), index=True, nullable=False)
    owner_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    # BE-016 organizational scope (nullable: pre-existing projects stay
    # unscoped and behave exactly as before).
    organization_id = Column(UUID(as_uuid=False), ForeignKey("organizations.id"), nullable=True)
    organizational_unit_id = Column(UUID(as_uuid=False), ForeignKey("organizational_units.id"),
                                    nullable=True)

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
    # BE-021: derived-intelligence staleness, orthogonal to the execution
    # status above (queued/running/completed/failed describe the worker;
    # staleness describes whether the output is still current governance-wise).
    staleness = Column(
        String(20), nullable=False, default="CURRENT", server_default="CURRENT"
    )
    job_type = Column(String(50), nullable=False, server_default="fingerprint", default="fingerprint")
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    attempt_count = Column(Integer, nullable=False, default=0)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    evidence = relationship("Evidence")

    __table_args__ = (
        CheckConstraint(
            "staleness IN ('CURRENT', 'STALE', 'INVALIDATED', 'SUPERSEDED')",
            name="ck_analysis_job_staleness",
        ),
        Index("ix_analysis_jobs_staleness", "staleness"),
    )


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
    # BE-021: staleness of the fused output — a stale run stays historical and
    # queryable but must no longer be treated as current intelligence.
    staleness = Column(
        String(20), nullable=False, default="CURRENT", server_default="CURRENT"
    )
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
        CheckConstraint(
            "staleness IN ('CURRENT', 'STALE', 'INVALIDATED', 'SUPERSEDED')",
            name="ck_fusion_run_staleness",
        ),
        Index("ix_fusion_runs_target", "target_type", "target_id"),
        Index("ix_fusion_runs_status", "status"),
        Index("ix_fusion_runs_staleness", "staleness"),
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
    # BE-021: historical explanations stay retrievable; staleness marks that
    # the lineage behind them is no longer current. Content is never mutated.
    staleness = Column(
        String(20), nullable=False, default="CURRENT", server_default="CURRENT"
    )
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
        CheckConstraint(
            "staleness IN ('CURRENT', 'STALE', 'INVALIDATED', 'SUPERSEDED')",
            name="ck_explanation_run_staleness",
        ),
        Index("ix_explanation_runs_run", "fusion_run_id"),
        Index("ix_explanation_runs_staleness", "staleness"),
    )


# ---------------------------------------------------------------------------
# BE-013 Review Case vocabularies (single source of truth; mirrored by
# CHECK constraints below and by the BE-013 Alembic migration).
# ---------------------------------------------------------------------------

REVIEW_CASE_ORIGINS = (
    "SYSTEM_SIGNAL",
    "AUTHORIZED_USER",
    "CITIZEN_REPORT",
    "EXTERNAL_SYSTEM",
)

REVIEW_CASE_STATUSES = (
    "OPEN",
    "ASSIGNED",
    "INVESTIGATING",
    "DECISION_PENDING",
    "RESOLVED",
    "ESCALATED",
)

REVIEW_CASE_DECISIONS = (
    "SUPPORTED",
    "CONTRADICTED",
    "INCONCLUSIVE",
    "INSUFFICIENT_EVIDENCE",
)

CASE_GENERATION_METHOD = "deterministic_case_generation"
CASE_GENERATION_METHOD_VERSION = "case-generation-v1"
CASE_GENERATION_DEFAULT_CONFIG_VERSION = "v1"

CASE_GENERATION_RUN_STATUSES = ("RUNNING", "COMPLETED", "FAILED")


class CaseGenerationConfiguration(Base):
    """BE-013: immutable versioned case-generation policy (never mutated)."""

    __tablename__ = "case_generation_configurations"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    version = Column(String(50), nullable=False, unique=True)
    name = Column(String(256), nullable=False)
    enabled = Column(Boolean, nullable=False, default=True, server_default="true")
    configuration = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CaseGenerationRun(Base):
    """BE-013: one traceable case-generation evaluation (append-only)."""

    __tablename__ = "case_generation_runs"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    fusion_run_id = Column(
        UUID(as_uuid=False),
        ForeignKey("fusion_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    configuration_id = Column(
        UUID(as_uuid=False),
        ForeignKey("case_generation_configurations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    method = Column(String(256), nullable=False)
    method_version = Column(String(50), nullable=False)
    input_snapshot = Column(JSONB, nullable=False, default=dict)
    status = Column(String(50), nullable=False, default="RUNNING", server_default="RUNNING")
    error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    fusion_run = relationship("FusionRun")
    configuration = relationship("CaseGenerationConfiguration")

    __table_args__ = (
        CheckConstraint(
            "status IN ('RUNNING', 'COMPLETED', 'FAILED')",
            name="ck_case_generation_run_status",
        ),
        Index("ix_case_generation_runs_run", "fusion_run_id"),
    )


class ReviewCase(Base):
    """BE-013: human-review work item (workflow state, never a verdict itself)."""

    __tablename__ = "review_cases"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    project_id = Column(UUID(as_uuid=False), ForeignKey("projects.id"), nullable=True)
    claim_id = Column(UUID(as_uuid=False), ForeignKey("claims.id"), nullable=True)
    evidence_id = Column(UUID(as_uuid=False), ForeignKey("evidence.id"), nullable=True)
    fusion_run_id = Column(
        UUID(as_uuid=False),
        ForeignKey("fusion_runs.id", ondelete="RESTRICT"),
        nullable=True,
    )
    case_generation_run_id = Column(
        UUID(as_uuid=False),
        ForeignKey("case_generation_runs.id", ondelete="RESTRICT"),
        nullable=True,
    )
    origin = Column(String(50), nullable=False)
    status = Column(String(50), nullable=False, default="OPEN", server_default="OPEN")
    priority_band = Column(String(50), nullable=True)
    priority_value = Column(Float, nullable=True)
    priority_source = Column(String(256), nullable=True)
    priority_config_version = Column(String(50), nullable=True)
    assigned_to = Column(UUID(as_uuid=False), nullable=True)
    assigned_at = Column(DateTime(timezone=True), nullable=True)
    decision = Column(String(50), nullable=True)
    decision_rationale = Column(Text, nullable=True)
    decided_by = Column(UUID(as_uuid=False), nullable=True)
    decided_at = Column(DateTime(timezone=True), nullable=True)
    escalated_to = Column(UUID(as_uuid=False), nullable=True)
    escalated_at = Column(DateTime(timezone=True), nullable=True)
    escalation_reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    resolved_at = Column(DateTime(timezone=True), nullable=True)

    fusion_run = relationship("FusionRun")
    generation_run = relationship("CaseGenerationRun")

    __table_args__ = (
        CheckConstraint(
            "origin IN ('SYSTEM_SIGNAL', 'AUTHORIZED_USER', 'CITIZEN_REPORT', 'EXTERNAL_SYSTEM')",
            name="ck_review_case_origin",
        ),
        CheckConstraint(
            "status IN ('OPEN', 'ASSIGNED', 'INVESTIGATING', 'DECISION_PENDING', "
            "'RESOLVED', 'ESCALATED')",
            name="ck_review_case_status",
        ),
        Index("ix_review_cases_project", "project_id"),
        Index("ix_review_cases_status", "status"),
        Index("ix_review_cases_priority", "priority_band"),
        Index("ix_review_cases_assigned", "assigned_to"),
        Index("ix_review_cases_run", "fusion_run_id"),
        Index("ix_review_cases_created", "created_at"),
    )


class ReviewCaseEvent(Base):
    """BE-013: append-only case workflow history (never modified)."""

    __tablename__ = "review_case_events"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    case_id = Column(
        UUID(as_uuid=False),
        ForeignKey("review_cases.id", ondelete="RESTRICT"),
        nullable=False,
    )
    event_type = Column(String(50), nullable=False)
    from_status = Column(String(50), nullable=True)
    to_status = Column(String(50), nullable=True)
    actor_id = Column(UUID(as_uuid=False), nullable=True)
    event_metadata = Column("metadata", JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    case = relationship("ReviewCase")

    __table_args__ = (
        Index("ix_review_case_events_case", "case_id", "created_at"),
    )


# ---------------------------------------------------------------------------
# BE-014 Evidence Request vocabularies (single source of truth; mirrored by
# CHECK constraints below and by the BE-014 Alembic migration).
# ---------------------------------------------------------------------------

EVIDENCE_REQUEST_STATUSES = (
    "DRAFT",
    "OPEN",
    "ACKNOWLEDGED",
    "FULFILLED",
    "PARTIALLY_FULFILLED",
    "DECLINED",
    "EXPIRED",
    "CANCELLED",
)

EVIDENCE_REQUEST_PRIORITIES = ("LOW", "NORMAL", "HIGH", "URGENT")

EVIDENCE_REQUEST_ITEM_STATUSES = (
    "REQUESTED",
    "RECEIVED",
    "ACCEPTED_FOR_REQUEST",
    "REJECTED_FOR_REQUEST",
)


class EvidenceRequest(Base):
    """BE-014: auditable request for additional evidence (never evidence itself)."""

    __tablename__ = "evidence_requests"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    review_case_id = Column(
        UUID(as_uuid=False),
        ForeignKey("review_cases.id", ondelete="RESTRICT"),
        nullable=True,
    )
    project_id = Column(UUID(as_uuid=False), ForeignKey("projects.id"), nullable=True)
    activity_id = Column(UUID(as_uuid=False), ForeignKey("activities.id"), nullable=True)
    claim_id = Column(UUID(as_uuid=False), ForeignKey("claims.id"), nullable=True)
    evidence_id = Column(UUID(as_uuid=False), ForeignKey("evidence.id"), nullable=True)
    requester_id = Column(UUID(as_uuid=False), nullable=True)
    recipient_id = Column(UUID(as_uuid=False), nullable=True)
    instructions = Column(Text, nullable=False)
    due_at = Column(DateTime(timezone=True), nullable=True)
    priority = Column(String(50), nullable=False, default="NORMAL", server_default="NORMAL")
    status = Column(String(50), nullable=False, default="DRAFT", server_default="DRAFT")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    review_case = relationship("ReviewCase")

    __table_args__ = (
        CheckConstraint(
            "status IN ('DRAFT', 'OPEN', 'ACKNOWLEDGED', 'FULFILLED', "
            "'PARTIALLY_FULFILLED', 'DECLINED', 'EXPIRED', 'CANCELLED')",
            name="ck_evidence_request_status",
        ),
        CheckConstraint(
            "priority IN ('LOW', 'NORMAL', 'HIGH', 'URGENT')",
            name="ck_evidence_request_priority",
        ),
        Index("ix_evidence_requests_project", "project_id"),
        Index("ix_evidence_requests_case", "review_case_id"),
        Index("ix_evidence_requests_status", "status"),
        Index("ix_evidence_requests_priority", "priority"),
        Index("ix_evidence_requests_requester", "requester_id"),
        Index("ix_evidence_requests_recipient", "recipient_id"),
        Index("ix_evidence_requests_due", "due_at"),
    )


class EvidenceRequestItem(Base):
    """BE-014: one requested-evidence slot; filled by linking real evidence.

    ACCEPTED_FOR_REQUEST is operational (fulfills this request item), never
    a statement about the evidence's truth or authenticity.
    """

    __tablename__ = "evidence_request_items"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    request_id = Column(
        UUID(as_uuid=False),
        ForeignKey("evidence_requests.id", ondelete="CASCADE"),
        nullable=False,
    )
    description = Column(Text, nullable=True)
    required = Column(Boolean, nullable=False, default=True, server_default="true")
    evidence_id = Column(UUID(as_uuid=False), ForeignKey("evidence.id"), nullable=True)
    item_status = Column(String(50), nullable=False, default="REQUESTED", server_default="REQUESTED")
    linked_at = Column(DateTime(timezone=True), nullable=True)
    linked_by = Column(UUID(as_uuid=False), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    request = relationship("EvidenceRequest")
    evidence = relationship("Evidence")

    __table_args__ = (
        CheckConstraint(
            "item_status IN ('REQUESTED', 'RECEIVED', 'ACCEPTED_FOR_REQUEST', "
            "'REJECTED_FOR_REQUEST')",
            name="ck_evidence_request_item_status",
        ),
        # Same evidence linked twice to one request collides; open slots
        # (NULL evidence) never collide with each other.
        UniqueConstraint("request_id", "evidence_id", name="uq_request_evidence_link"),
        Index("ix_evidence_request_items_request", "request_id"),
        Index("ix_evidence_request_items_evidence", "evidence_id"),
    )


class EvidenceRequestEvent(Base):
    """BE-014: append-only request workflow history (never modified)."""

    __tablename__ = "evidence_request_events"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    request_id = Column(
        UUID(as_uuid=False),
        ForeignKey("evidence_requests.id", ondelete="RESTRICT"),
        nullable=False,
    )
    event_type = Column(String(50), nullable=False)
    from_status = Column(String(50), nullable=True)
    to_status = Column(String(50), nullable=True)
    actor_id = Column(UUID(as_uuid=False), nullable=True)
    event_metadata = Column("metadata", JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    request = relationship("EvidenceRequest")

    __table_args__ = (
        Index("ix_evidence_request_events_request", "request_id", "created_at"),
    )


# ---------------------------------------------------------------------------
# BE-015 Audit Ledger vocabularies (single source of truth; the event
# vocabulary is enforced by the service layer to stay incrementally
# extensible without migrations).
# ---------------------------------------------------------------------------

AUDIT_HASH_ALGORITHM = "SHA-256"
AUDIT_LEDGER_VERSION = "audit-v1"
AUDIT_GENESIS_HASH = "GENESIS"

# Explicit governance event vocabulary (BE-015 §20). Only these types may
# be appended; anything else is rejected rather than recorded vaguely.
AUDIT_EVENT_TYPES = frozenset(
    {
        "EVIDENCE_UPLOADED",
        "ANALYSIS_COMPLETED",
        "ANALYSIS_FAILED",
        "FUSION_RUN_CREATED",
        "EXPLANATION_GENERATED",
        "REVIEW_CASE_CREATED",
        "REVIEW_CASE_ASSIGNED",
        "REVIEW_CASE_DECISION_RECORDED",
        "REVIEW_CASE_ESCALATED",
        "REVIEW_CASE_RESOLVED",
        "REVIEW_CASE_REOPENED",
        "EVIDENCE_REQUEST_CREATED",
        "EVIDENCE_REQUEST_ISSUED",
        "EVIDENCE_REQUEST_ACKNOWLEDGED",
        "EVIDENCE_REQUEST_FULFILLED",
        "EVIDENCE_REQUEST_DECLINED",
        "EVIDENCE_REQUEST_CANCELLED",
        "EVIDENCE_REQUEST_EXPIRED",
        "GRAPH_RELATIONSHIP_CREATED",
        "GRAPH_RELATIONSHIP_INVALIDATED",
        "GRAPH_RELATIONSHIP_SUPERSEDED",
        "USER_CREATED",
        "ORGANIZATION_CREATED",
        "ORGANIZATIONAL_UNIT_CREATED",
        "ROLE_ASSIGNED",
        "ROLE_REVOKED",
        "RETENTION_POLICY_CREATED",
        "RETENTION_POLICY_ACTIVATED",
        "RETENTION_HOLD_CREATED",
        "RETENTION_HOLD_RELEASED",
        "RESOURCE_ARCHIVED",
        "RESOURCE_RESTORED",
        "DELETION_REQUESTED",
        "RESOURCE_DELETED",
        "DELETION_BLOCKED",
        "NOTIFICATION_PREFERENCE_CHANGED",
        "NOTIFICATION_DELIVERY_FAILED",
        "NOTIFICATION_DELIVERY_SUCCEEDED",
        # BE-019 integration audit events
        "API_CLIENT_CREATED",
        "API_CLIENT_DISABLED",
        "API_CREDENTIAL_CREATED",
        "API_CREDENTIAL_REVOKED",
        "EXTERNAL_SYSTEM_CREATED",
        "EXTERNAL_REFERENCE_CREATED",
        "WEBHOOK_CREATED",
        "WEBHOOK_DISABLED",
        "WEBHOOK_DELIVERY_FAILED",
        "WEBHOOK_DELIVERY_SUCCEEDED",
        # BE-021 governance audit events. The spec (§23) lists twelve
        # minimum events; the remaining five cover other explicit governance
        # actions so that every action has an accurate audit twin (§23 also
        # requires "every governance action" to emit an audit event).
        "DISPUTE_CREATED",
        "DISPUTE_ASSIGNED",
        "DISPUTE_REVIEW_STARTED",
        "DISPUTE_ESCALATED",
        "DISPUTE_RESOLVED",
        "DISPUTE_REJECTED",
        "DISPUTE_WITHDRAWN",
        "CORRECTION_REQUESTED",
        "CORRECTION_REVIEW_STARTED",
        "CORRECTION_APPROVED",
        "CORRECTION_REJECTED",
        "CORRECTION_APPLIED",
        "CORRECTION_CANCELLED",
        "INTELLIGENCE_INVALIDATED",
        # Emitted as a review-case event when an invalidation changes the
        # intelligence a non-resolved case depends on (§20). Registered here so
        # the governed event vocabulary stays complete and auditable.
        "DEPENDENT_INTELLIGENCE_CHANGED",
        "INTELLIGENCE_REPROCESS_REQUESTED",
        "INTELLIGENCE_REPROCESS_COMPLETED",
        "INTELLIGENCE_REPROCESS_FAILED",
        # BE-022 publication governance audit events (§26). Every publication
        # mutation emits its accurate audit twin.
        "PUBLICATION_CREATED",
        "PUBLICATION_REVIEW_STARTED",
        "PUBLICATION_APPROVED",
        "PUBLICATION_REJECTED",
        "PUBLICATION_PUBLISHED",
        "PUBLICATION_UNPUBLISHED",
        "PUBLICATION_POLICY_CREATED",
        "PUBLICATION_POLICY_UPDATED",
        "PUBLICATION_ELIGIBILITY_FAILED",
        "PUBLIC_PUBLICATION_VERSION_CREATED",
        # BE-025 administrative control-plane audit events. Every admin
        # mutation emits its accurate audit twin.
        "ORGANIZATION_UPDATED",
        "ORGANIZATIONAL_UNIT_UPDATED",
        "USER_STATUS_CHANGED",
        "PROJECT_SCOPE_CHANGED",
        "PROJECT_OWNERSHIP_CHANGED",
        # BE-026 field operations and offline synchronization. Security
        # failures and conflicts are events, never silent outcomes.
        "FIELD_ASSIGNMENT_CREATED",
        "FIELD_ASSIGNMENT_STATUS_CHANGED",
        "FIELD_ASSIGNMENT_EXPIRED",
        "FIELD_ASSIGNMENT_ACCESSED",
        "FIELD_ASSIGNMENT_SECURITY_FAILURE",
        "FIELD_SESSION_OPENED",
        "FIELD_SESSION_CLOSED",
        "FIELD_SYNC_ACCEPTED",
        "FIELD_SYNC_DUPLICATE",
        "FIELD_SYNC_REJECTED",
        "FIELD_SYNC_CONFLICT",
        "FIELD_SYNC_CONFLICT_RESOLVED",
        "FIELD_EVIDENCE_ASSOCIATED",
    }
)


class AuditLedgerEvent(Base):
    """BE-015: append-only tamper-evident audit record (never updated/deleted).

    Ordering comes from the database-assigned ``sequence_number`` (unique,
    monotonic; assigned under an advisory transaction lock at append time),
    never from timestamps. ``event_hash`` covers the canonical serialization
    of all protected fields; ``previous_hash`` chains to the predecessor.
    """

    __tablename__ = "audit_ledger_events"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    sequence_number = Column(BigInteger, nullable=False, unique=True)
    event_type = Column(String(100), nullable=False)
    action = Column(String(100), nullable=False)
    resource_type = Column(String(100), nullable=False)
    resource_id = Column(UUID(as_uuid=False), nullable=True)
    actor_id = Column(UUID(as_uuid=False), nullable=True)
    project_id = Column(UUID(as_uuid=False), nullable=True)
    payload = Column(JSONB, nullable=False, default=dict)
    event_metadata = Column("metadata", JSONB, nullable=False, default=dict)
    previous_hash = Column(String(256), nullable=False)
    event_hash = Column(String(256), nullable=False)
    hash_algorithm = Column(String(50), nullable=False, default=AUDIT_HASH_ALGORITHM)
    ledger_version = Column(String(50), nullable=False, default=AUDIT_LEDGER_VERSION)
    created_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_audit_ledger_sequence", "sequence_number"),
        Index("ix_audit_ledger_created", "created_at"),
        Index("ix_audit_ledger_actor", "actor_id"),
        Index("ix_audit_ledger_type", "event_type"),
        Index("ix_audit_ledger_resource", "resource_type", "resource_id"),
        Index("ix_audit_ledger_project", "project_id"),
    )


# ---------------------------------------------------------------------------
# BE-016 Authentication & Authorization vocabularies (single source of truth;
# mirrored by CHECK constraints below and by the BE-016 Alembic migration).
# ---------------------------------------------------------------------------

AUTH_PRINCIPAL_TYPES = ("USER", "API_CLIENT", "SYSTEM", "ANONYMOUS")

AUTH_USER_STATUSES = ("ACTIVE", "SUSPENDED", "DISABLED")

AUTH_ORG_STATUSES = ("ACTIVE", "SUSPENDED", "DISABLED")

AUTH_SCOPE_TYPES = ("GLOBAL", "ORGANIZATION", "ORGANIZATIONAL_UNIT", "PROJECT")

# Baseline roles from the frozen architecture. Roles grant permissions;
# scopes determine where they apply; neither implies the other.
AUTH_ROLES = (
    "CITIZEN",
    "FIELD_OFFICER",
    "REVIEWER",
    "SUPERVISOR",
    "ADMINISTRATOR",
    "API_CLIENT",
)

# Stable explicit permission catalogue. Substantive (decide/resolve) and
# administrative (*.manage) permissions are disjoint by construction.
AUTH_PERMISSIONS = (
    "project.read",
    "project.create",
    "project.update",
    "activity.read",
    "activity.create",
    "activity.update",
    "claim.read",
    "claim.create",
    "claim.update",
    "evidence.read",
    "evidence.create",
    "evidence.update_context",
    "evidence.read_sensitive",
    "graph.read",
    "fusion.read",
    "fusion.execute",
    "review_case.read",
    "review_case.assign",
    "review_case.investigate",
    "review_case.decide",
    "review_case.escalate",
    "review_case.resolve",
    "review_case.reopen",
    "evidence_request.read",
    "evidence_request.create",
    "evidence_request.issue",
    "evidence_request.respond",
    "audit.read",
    "organization.manage",
    "user.manage",
    "role.manage",
    "configuration.manage",
    "retention.read",
    "retention.manage_policy",
    "retention.manage_hold",
    "retention.archive",
    "retention.restore",
    "retention.delete",
    "notification.read",
    "notification.mark_read",
    "notification.manage_preferences",
    "notification.admin",
    # BE-019 integration permissions
    "integration.read",
    "integration.manage",
    "api_client.manage",
    "credential.manage",
    "external_data.read",
    "external_data.write",
    "webhook.manage",
    "webhook.read",
    # BE-021 governance permissions (narrowly scoped; substantive actions
    # stay disjoint from administrative ones per §12)
    "dispute.create",
    "dispute.read",
    "dispute.review",
    "dispute.resolve",
    "correction.create",
    "correction.read",
    "correction.approve",
    "correction.apply",
    "intelligence.invalidate",
    "intelligence.reprocess",
    # BE-022 publication governance permissions (§14). Substantive actions
    # (approve/publish/unpublish) stay disjoint from administrative ones
    # (policy.manage), and administrators are NOT granted the substantive
    # actions by default — §14 requires explicit grant.
    "publication.create",
    "publication.read",
    "publication.review",
    "publication.approve",
    "publication.publish",
    "publication.unpublish",
    "publication.policy.manage",
    # BE-026 field operations. Both are purely additive: a field assignment
    # is operational work, never an authorization grant, so synchronization
    # requires this permission AND a server-verified scope AND an active
    # assignment. Nothing else gains either one.
    "field.sync",
    "field_assignment.manage",
)

# Baseline role -> permissions mapping (also seeded for tests/dev via the
# authorization service; the database remains authoritative at runtime).
AUTH_ROLE_PERMISSIONS = {
    "CITIZEN": (
        "evidence.create",
        "evidence.read",
        "evidence_request.create",
        "evidence_request.respond",
        "claim.read",
        "notification.read",
        "notification.mark_read",
        "notification.manage_preferences",
        # BE-021: citizens may raise disputes and request corrections, but
        # never review/resolve/approve them.
        "dispute.create",
        "dispute.read",
        "correction.create",
        "correction.read",
    ),
    "FIELD_OFFICER": (
        "project.read",
        "activity.read",
        "activity.create",
        "claim.read",
        "claim.create",
        "claim.update",
        "evidence.read",
        "evidence.create",
        "evidence.update_context",
        "graph.read",
        "fusion.read",
        "review_case.read",
        "evidence_request.create",
        "evidence_request.issue",
        "evidence_request.respond",
        "notification.read",
        "notification.mark_read",
        "notification.manage_preferences",
        # BE-021: officers may dispute/request corrections and trigger
        # reprocessing through the existing pipeline; not approvers.
        "dispute.create",
        "dispute.read",
        "correction.create",
        "correction.read",
        "intelligence.reprocess",
        # BE-022: officers may request publication but never approve or
        # publish their own request (§15 separation of duties).
        "publication.create",
        "publication.read",
        # BE-026: synchronize captures captured against an active field
        # assignment. Scope and assignment state are re-checked server-side.
        "field.sync",
    ),
    "REVIEWER": (
        "project.read",
        "claim.read",
        "evidence.read",
        "evidence.read_sensitive",
        "graph.read",
        "fusion.read",
        "review_case.read",
        "review_case.assign",
        "review_case.investigate",
        "review_case.escalate",
        "review_case.reopen",
        "evidence_request.read",
        "evidence_request.respond",
        "audit.read",
        "notification.read",
        "notification.mark_read",
        "notification.manage_preferences",
        # BE-021: reviewers investigate disputes but do not resolve them.
        "dispute.create",
        "dispute.read",
        "dispute.review",
        "correction.create",
        "correction.read",
        # BE-022: reviewers review publication requests but do not approve,
        # publish, or unpublish them (§15).
        "publication.create",
        "publication.read",
        "publication.review",
    ),
    "SUPERVISOR": (
        "project.read",
        "project.create",
        "claim.read",
        "evidence.read",
        "evidence.read_sensitive",
        "graph.read",
        "fusion.read",
        "fusion.execute",
        "review_case.read",
        "review_case.assign",
        "review_case.investigate",
        "review_case.decide",
        "review_case.escalate",
        "review_case.resolve",
        "review_case.reopen",
        "evidence_request.read",
        "evidence_request.respond",
        "audit.read",
        "notification.read",
        "notification.mark_read",
        "notification.manage_preferences",
        "integration.read",
        "external_data.read",
        "webhook.read",
        # BE-021: supervisors are the substantive governance decision-makers
        # (resolve disputes, approve/apply corrections, invalidate, reprocess).
        "dispute.create",
        "dispute.read",
        "dispute.review",
        "dispute.resolve",
        "correction.create",
        "correction.read",
        "correction.approve",
        "correction.apply",
        "intelligence.invalidate",
        "intelligence.reprocess",
        # BE-022: supervisors are the substantive publication decision-makers
        # (approve, publish, unpublish) — but never manage policy, which stays
        # administrative (§14).
        "publication.create",
        "publication.read",
        "publication.review",
        "publication.approve",
        "publication.publish",
        "publication.unpublish",
    ),
    "ADMINISTRATOR": (
        "organization.manage",
        "user.manage",
        "role.manage",
        "configuration.manage",
        "audit.read",
        "retention.read",
        "retention.manage_policy",
        "retention.manage_hold",
        "retention.archive",
        "retention.restore",
        "retention.delete",
        "notification.read",
        "notification.mark_read",
        "notification.manage_preferences",
        "notification.admin",
        "integration.read",
        "integration.manage",
        "api_client.manage",
        "credential.manage",
        "external_data.read",
        "external_data.write",
        "webhook.manage",
        "webhook.read",
        # BE-021: administrators get governance READ ONLY — they must not
        # automatically become substantive decision-makers (§12).
        "dispute.read",
        "correction.read",
        # BE-022: administrators manage policy (administrative) and read
        # publications, but are NOT granted approve/publish/unpublish.
        # §14: administrative authority never implies substantive publication
        # authority. Policy management could otherwise be used to widen the
        # allowed field set and then self-approve the result.
        "publication.read",
        "publication.policy.manage",
        # BE-026: field assignment administration and conflict resolution are
        # administrative. SUPERVISOR is deliberately not granted this in
        # BE-026 (reviewers/supervisors keep existing semantics unchanged).
        "field_assignment.manage",
    ),
    "API_CLIENT": (),
}


class Organization(Base):
    """BE-016: top-level ownership/scope boundary (never hard-coded)."""

    __tablename__ = "organizations"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    name = Column(String(256), nullable=False)
    code = Column(String(128), nullable=False, unique=True)
    status = Column(String(50), nullable=False, default="ACTIVE", server_default="ACTIVE")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('ACTIVE', 'SUSPENDED', 'DISABLED')",
            name="ck_organization_status",
        ),
        Index("ix_organizations_code", "code"),
    )


class OrganizationalUnit(Base):
    """BE-016: internal structure within an organization (generic, not governmental)."""

    __tablename__ = "organizational_units"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    organization_id = Column(
        UUID(as_uuid=False), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    name = Column(String(256), nullable=False)
    code = Column(String(128), nullable=False)
    status = Column(String(50), nullable=False, default="ACTIVE", server_default="ACTIVE")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    organization = relationship("Organization")

    __table_args__ = (
        UniqueConstraint("organization_id", "code", name="uq_org_unit_code"),
        CheckConstraint(
            "status IN ('ACTIVE', 'SUSPENDED', 'DISABLED')",
            name="ck_org_unit_status",
        ),
        Index("ix_org_units_org", "organization_id"),
    )


class Role(Base):
    """BE-016: named permission bundle (grants permissions, never scope)."""

    __tablename__ = "roles"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    name = Column(String(128), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    status = Column(String(50), nullable=False, default="ACTIVE", server_default="ACTIVE")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('ACTIVE', 'SUSPENDED', 'DISABLED')",
            name="ck_role_status",
        ),
        Index("ix_roles_name", "name"),
    )


class Permission(Base):
    """BE-016: single explicit stable permission string."""

    __tablename__ = "permissions"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    name = Column(String(256), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (Index("ix_permissions_name", "name"),)


class RolePermission(Base):
    """BE-016: role -> permission mapping (unique pairs)."""

    __tablename__ = "role_permissions"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    role_id = Column(
        UUID(as_uuid=False), ForeignKey("roles.id", ondelete="CASCADE"), nullable=False
    )
    permission_id = Column(
        UUID(as_uuid=False), ForeignKey("permissions.id", ondelete="CASCADE"), nullable=False
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    role = relationship("Role")
    permission = relationship("Permission")

    __table_args__ = (
        UniqueConstraint("role_id", "permission_id", name="uq_role_permission"),
        Index("ix_role_permissions_role", "role_id"),
    )


class UserRoleAssignment(Base):
    """BE-016: user holds a role within exactly one scope (global/org/unit/project)."""

    __tablename__ = "user_role_assignments"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    user_id = Column(
        UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role_id = Column(
        UUID(as_uuid=False), ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False
    )
    scope_type = Column(String(50), nullable=False)
    organization_id = Column(UUID(as_uuid=False), ForeignKey("organizations.id"), nullable=True)
    organizational_unit_id = Column(
        UUID(as_uuid=False), ForeignKey("organizational_units.id"), nullable=True
    )
    project_id = Column(UUID(as_uuid=False), ForeignKey("projects.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user = relationship("User")
    role = relationship("Role")

    __table_args__ = (
        CheckConstraint(
            "scope_type IN ('GLOBAL', 'ORGANIZATION', 'ORGANIZATIONAL_UNIT', 'PROJECT')",
            name="ck_assignment_scope",
        ),
        CheckConstraint(
            "(scope_type = 'GLOBAL' AND organization_id IS NULL"
            " AND organizational_unit_id IS NULL AND project_id IS NULL)"
            " OR (scope_type = 'ORGANIZATION' AND organization_id IS NOT NULL"
            " AND organizational_unit_id IS NULL AND project_id IS NULL)"
            " OR (scope_type = 'ORGANIZATIONAL_UNIT' AND organizational_unit_id IS NOT NULL"
            " AND organization_id IS NULL AND project_id IS NULL)"
            " OR (scope_type = 'PROJECT' AND project_id IS NOT NULL"
            " AND organization_id IS NULL AND organizational_unit_id IS NULL)",
            name="ck_assignment_scope_matrix",
        ),
        UniqueConstraint(
            "user_id",
            "role_id",
            "scope_type",
            "organization_id",
            "organizational_unit_id",
            "project_id",
            name="uq_user_role_scoped",
            postgresql_nulls_not_distinct=True,
        ),
        Index("ix_assignments_user", "user_id"),
        Index("ix_assignments_project", "project_id"),
        Index("ix_assignments_org", "organization_id"),
    )


class ApiClient(Base):
    """BE-016: first-class API actor with explicit scopes.

    No secret material is stored in V1: development bearer tokens reference
    the client id directly and are accepted only when explicitly enabled
    for development/testing. Production key issuance/rotation is deferred.
    """

    __tablename__ = "api_clients"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    name = Column(String(256), nullable=False, unique=True)
    scopes = Column(JSONB, nullable=False, default=list)
    project_id = Column(UUID(as_uuid=False), ForeignKey("projects.id"), nullable=True)
    status = Column(String(50), nullable=False, default="ACTIVE", server_default="ACTIVE")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('ACTIVE', 'SUSPENDED', 'DISABLED')",
            name="ck_api_client_status",
        ),
        Index("ix_api_clients_name", "name"),
    )


# ---------------------------------------------------------------------------
# BE-017 Retention & Data Governance vocabularies (single source of truth;
# mirrored by CHECK constraints below and by the BE-017 Alembic migration).
# ---------------------------------------------------------------------------

RETENTION_RESOURCE_TYPES = (
    "EVIDENCE",
    "ANALYSIS_RESULT",
    "FUSION_RUN",
    "REVIEW_CASE",
    "EVIDENCE_REQUEST",
    "AUDIT_LEDGER_EVENT",
)

RETENTION_STATES = (
    "ACTIVE",
    "ELIGIBLE_FOR_ARCHIVE",
    "ARCHIVED",
    "ELIGIBLE_FOR_DELETION",
    "DELETION_PENDING",
    "DELETED",
)

RETENTION_ANCHORS = (
    "INGESTED_AT",
    "CAPTURED_AT",
    "PROJECT_COMPLETED_AT",
    "CASE_RESOLVED_AT",
    "REQUEST_FULFILLED_AT",
    "DECISION_AT",
    "SUPERSEDED_AT",
    "CUSTOM_POLICY_EVENT",
)

RETENTION_POLICY_STATUSES = ("DRAFT", "ACTIVE", "SUPERSEDED", "RETIRED")

RETENTION_HOLD_STATUSES = ("ACTIVE", "RELEASED", "EXPIRED", "CANCELLED")

RETENTION_HOLD_SCOPES = ("RESOURCE", "PROJECT", "CASE", "CLAIM", "ORGANIZATION")

RETENTION_OPERATION_TYPES = ("ARCHIVE", "RESTORE", "DELETE")

RETENTION_OPERATION_STATUSES = ("RUNNING", "COMPLETED", "FAILED")


class RetentionPolicy(Base):
    """BE-017: named retention policy identity (rules live in versions)."""

    __tablename__ = "retention_policies"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    name = Column(String(256), nullable=False)
    description = Column(Text, nullable=True)
    resource_type = Column(String(50), nullable=False)
    scope_type = Column(String(50), nullable=False)
    organization_id = Column(UUID(as_uuid=False), ForeignKey("organizations.id"), nullable=True)
    organizational_unit_id = Column(
        UUID(as_uuid=False), ForeignKey("organizational_units.id"), nullable=True
    )
    project_id = Column(UUID(as_uuid=False), ForeignKey("projects.id"), nullable=True)
    created_by = Column(UUID(as_uuid=False), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "resource_type IN ('EVIDENCE', 'ANALYSIS_RESULT', 'FUSION_RUN', "
            "'REVIEW_CASE', 'EVIDENCE_REQUEST', 'AUDIT_LEDGER_EVENT')",
            name="ck_retention_policy_resource",
        ),
        CheckConstraint(
            "scope_type IN ('GLOBAL', 'ORGANIZATION', 'ORGANIZATIONAL_UNIT', 'PROJECT')",
            name="ck_retention_policy_scope",
        ),
        Index("ix_retention_policies_resource", "resource_type"),
        Index("ix_retention_policies_project", "project_id"),
        Index("ix_retention_policies_org", "organization_id"),
    )


class RetentionPolicyVersion(Base):
    """BE-017: immutable versioned rules (new version, never mutation)."""

    __tablename__ = "retention_policy_versions"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    policy_id = Column(
        UUID(as_uuid=False),
        ForeignKey("retention_policies.id", ondelete="CASCADE"),
        nullable=False,
    )
    version = Column(Integer, nullable=False)
    rules = Column(JSONB, nullable=False, default=dict)
    status = Column(String(50), nullable=False, default="DRAFT", server_default="DRAFT")
    effective_from = Column(DateTime(timezone=True), nullable=True)
    effective_until = Column(DateTime(timezone=True), nullable=True)
    created_by = Column(UUID(as_uuid=False), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    policy = relationship("RetentionPolicy")

    __table_args__ = (
        UniqueConstraint("policy_id", "version", name="uq_policy_version"),
        CheckConstraint(
            "status IN ('DRAFT', 'ACTIVE', 'SUPERSEDED', 'RETIRED')",
            name="ck_policy_version_status",
        ),
        Index("ix_policy_versions_policy", "policy_id"),
    )


class RetentionState(Base):
    """BE-017: explicit retention lifecycle per resource (separate from domain)."""

    __tablename__ = "retention_states"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    resource_type = Column(String(50), nullable=False)
    resource_id = Column(UUID(as_uuid=False), nullable=False)
    project_id = Column(UUID(as_uuid=False), nullable=True)
    organization_id = Column(UUID(as_uuid=False), nullable=True)
    state = Column(String(50), nullable=False, default="ACTIVE", server_default="ACTIVE")
    policy_version_id = Column(
        UUID(as_uuid=False), ForeignKey("retention_policy_versions.id"), nullable=True
    )
    anchor = Column(String(50), nullable=True)
    anchor_timestamp = Column(DateTime(timezone=True), nullable=True)
    expiry_timestamp = Column(DateTime(timezone=True), nullable=True)
    previous_storage_key = Column(Text, nullable=True)
    evaluated_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("resource_type", "resource_id", name="uq_retention_state_resource"),
        CheckConstraint(
            "state IN ('ACTIVE', 'ELIGIBLE_FOR_ARCHIVE', 'ARCHIVED', "
            "'ELIGIBLE_FOR_DELETION', 'DELETION_PENDING', 'DELETED')",
            name="ck_retention_state",
        ),
        Index("ix_retention_states_resource", "resource_type", "resource_id"),
        Index("ix_retention_states_state", "state"),
        Index("ix_retention_states_expiry", "expiry_timestamp"),
        Index("ix_retention_states_project", "project_id"),
        Index("ix_retention_states_policy", "policy_version_id"),
    )


class RetentionHold(Base):
    """BE-017: first-class hold (history preserved; never deleted)."""

    __tablename__ = "retention_holds"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    scope = Column(String(50), nullable=False)
    resource_type = Column(String(50), nullable=True)
    resource_id = Column(UUID(as_uuid=False), nullable=True)
    project_id = Column(UUID(as_uuid=False), ForeignKey("projects.id"), nullable=True)
    claim_id = Column(UUID(as_uuid=False), ForeignKey("claims.id"), nullable=True)
    case_id = Column(UUID(as_uuid=False), ForeignKey("review_cases.id"), nullable=True)
    organization_id = Column(UUID(as_uuid=False), ForeignKey("organizations.id"), nullable=True)
    reason = Column(Text, nullable=False)
    authority = Column(String(256), nullable=True)
    status = Column(String(50), nullable=False, default="ACTIVE", server_default="ACTIVE")
    created_by = Column(UUID(as_uuid=False), nullable=True)
    released_by = Column(UUID(as_uuid=False), nullable=True)
    release_reason = Column(Text, nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    released_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "scope IN ('RESOURCE', 'PROJECT', 'CASE', 'CLAIM', 'ORGANIZATION')",
            name="ck_hold_scope",
        ),
        CheckConstraint(
            "status IN ('ACTIVE', 'RELEASED', 'EXPIRED', 'CANCELLED')",
            name="ck_hold_status",
        ),
        Index("ix_holds_status", "status"),
        Index("ix_holds_project", "project_id"),
        Index("ix_holds_resource", "resource_type", "resource_id"),
    )


class RetentionOperation(Base):
    """BE-017: traceable archive/restore/delete execution (append-only)."""

    __tablename__ = "retention_operations"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    resource_type = Column(String(50), nullable=False)
    resource_id = Column(UUID(as_uuid=False), nullable=False)
    operation = Column(String(50), nullable=False)
    status = Column(String(50), nullable=False, default="RUNNING", server_default="RUNNING")
    policy_version_id = Column(
        UUID(as_uuid=False), ForeignKey("retention_policy_versions.id"), nullable=True
    )
    actor_id = Column(UUID(as_uuid=False), nullable=True)
    details = Column(JSONB, nullable=False, default=dict)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "operation IN ('ARCHIVE', 'RESTORE', 'DELETE')",
            name="ck_retention_operation_type",
        ),
        CheckConstraint(
            "status IN ('RUNNING', 'COMPLETED', 'FAILED')",
            name="ck_retention_operation_status",
        ),
        Index("ix_retention_operations_resource", "resource_type", "resource_id"),
        Index("ix_retention_operations_status", "status"),
    )


# ---------------------------------------------------------------------------
# BE-018 Notifications & Event Delivery vocabularies (single source of truth;
# mirrored by CHECK constraints below and by the BE-018 Alembic migration).
# ---------------------------------------------------------------------------

NOTIFICATION_TYPES = (
    "REVIEW_CASE_ASSIGNED",
    "REVIEW_CASE_ESCALATED",
    "REVIEW_CASE_DECISION_PENDING",
    "REVIEW_CASE_REOPENED",
    "EVIDENCE_REQUEST_ISSUED",
    "EVIDENCE_REQUEST_ACKNOWLEDGED",
    "EVIDENCE_REQUEST_PARTIALLY_FULFILLED",
    "EVIDENCE_REQUEST_FULFILLED",
    "EVIDENCE_REQUEST_DECLINED",
    "EVIDENCE_REQUEST_EXPIRED",
    "RETENTION_HOLD_CREATED",
    "RETENTION_HOLD_RELEASED",
    "SYSTEM_SECURITY_EVENT",
    # BE-021 governance notifications (reference IDs only; never evidence
    # content — §24)
    "DISPUTE_CREATED",
    "DISPUTE_ASSIGNED",
    "DISPUTE_ESCALATED",
    "DISPUTE_RESOLVED",
    "CORRECTION_APPROVED",
    "CORRECTION_REJECTED",
    "CORRECTION_APPLIED",
    "INTELLIGENCE_INVALIDATED",
    "REPROCESSING_COMPLETED",
    # BE-022 publication notifications (§27). Reference IDs only, routed
    # through the existing outbox — no direct email delivery.
    "PUBLICATION_SUBMITTED",
    "PUBLICATION_APPROVED",
    "PUBLICATION_REJECTED",
    "PUBLICATION_PUBLISHED",
    "PUBLICATION_UNPUBLISHED",
    "PUBLICATION_REQUIRES_REVIEW",
)

NOTIFICATION_STATUSES = ("UNREAD", "READ")

NOTIFICATION_SEVERITIES = ("INFO", "WARNING", "CRITICAL")

NOTIFICATION_CHANNELS = ("IN_APP", "EMAIL")

NOTIFICATION_DELIVERY_STATUSES = (
    "PENDING",
    "PROCESSING",
    "DELIVERED",
    "FAILED",
    "RETRYING",
    "CANCELLED",
)

NOTIFICATION_OUTBOX_STATUSES = (
    "PENDING",
    "PROCESSING",
    "PUBLISHED",
    "FAILED",
)


class Notification(Base):
    """BE-018: first-class in-app notification record."""

    __tablename__ = "notifications"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    recipient_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    organization_id = Column(UUID(as_uuid=False), ForeignKey("organizations.id"), nullable=True)
    project_id = Column(UUID(as_uuid=False), ForeignKey("projects.id"), nullable=True)
    notification_type = Column(String(50), nullable=False)
    title = Column(String(256), nullable=False)
    body = Column(Text, nullable=False)
    resource_type = Column(String(50), nullable=True)
    resource_id = Column(UUID(as_uuid=False), nullable=True)
    severity = Column(String(20), nullable=False, default="INFO", server_default="INFO")
    status = Column(String(20), nullable=False, default="UNREAD", server_default="UNREAD")
    read_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "status IN ('UNREAD', 'READ')",
            name="ck_notification_status",
        ),
        CheckConstraint(
            "severity IN ('INFO', 'WARNING', 'CRITICAL')",
            name="ck_notification_severity",
        ),
        Index("ix_notifications_recipient_created", "recipient_id", "created_at"),
        Index("ix_notifications_recipient_status", "recipient_id", "status"),
        Index("ix_notifications_project", "project_id"),
        Index("ix_notifications_created_at", "created_at"),
    )


class NotificationDelivery(Base):
    """BE-018: delivery status per channel for a notification."""

    __tablename__ = "notification_deliveries"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    notification_id = Column(
        UUID(as_uuid=False), ForeignKey("notifications.id", ondelete="CASCADE"), nullable=False
    )
    channel = Column(String(20), nullable=False)
    status = Column(String(20), nullable=False, default="PENDING", server_default="PENDING")
    attempts = Column(Integer, nullable=False, default=0, server_default="0")
    provider = Column(String(50), nullable=False)
    provider_message_id = Column(String(256), nullable=True)
    last_error = Column(Text, nullable=True)
    next_attempt_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    delivered_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("notification_id", "channel", name="uq_delivery_notification_channel"),
        CheckConstraint(
            "channel IN ('IN_APP', 'EMAIL')",
            name="ck_notification_delivery_channel",
        ),
        CheckConstraint(
            "status IN ('PENDING', 'PROCESSING', 'DELIVERED', 'FAILED', 'RETRYING', 'CANCELLED')",
            name="ck_notification_delivery_status",
        ),
        Index("ix_notification_deliveries_status_next_attempt", "status", "next_attempt_at"),
        Index("ix_notification_deliveries_notification", "notification_id"),
    )


class NotificationPreference(Base):
    """BE-018: user notification channel preferences per notification type."""

    __tablename__ = "notification_preferences"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    notification_type = Column(String(50), nullable=False)
    in_app_enabled = Column(Boolean, nullable=False, default=True, server_default="true")
    email_enabled = Column(Boolean, nullable=False, default=True, server_default="true")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("user_id", "notification_type", name="uq_notification_preference_user_type"),
        Index("ix_notification_preferences_user", "user_id"),
    )


class NotificationOutbox(Base):
    """BE-018: transactional outbox event for reliable asynchronous delivery."""

    __tablename__ = "notification_outbox"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    event_type = Column(String(50), nullable=False)
    aggregate_type = Column(String(50), nullable=False)
    aggregate_id = Column(UUID(as_uuid=False), nullable=False)
    payload = Column(JSONB, nullable=False, default=dict)
    status = Column(String(20), nullable=False, default="PENDING", server_default="PENDING")
    attempts = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING', 'PROCESSING', 'PUBLISHED', 'FAILED')",
            name="ck_notification_outbox_status",
        ),
        Index("ix_notification_outbox_status", "status", "created_at"),
    )


# ---------------------------------------------------------------------------
# BE-019 External Integrations & API Client Platform vocabularies.
# ---------------------------------------------------------------------------

EXTERNAL_SYSTEM_TYPES = (
    "GOVERNMENT_PORTAL",
    "FIELD_SYSTEM",
    "PROJECT_MANAGEMENT",
    "DOCUMENT_SYSTEM",
    "INSPECTION_SYSTEM",
    "DATA_PLATFORM",
    "OTHER",
)

EXTERNAL_SYSTEM_STATUSES = ("ACTIVE", "SUSPENDED", "DISABLED")

WEBHOOK_EVENT_TYPES = (
    "review_case.created",
    "review_case.assigned",
    "review_case.escalated",
    "review_case.resolved",
    "evidence_request.issued",
    "evidence_request.fulfilled",
    "evidence_request.declined",
    "evidence_request.expired",
    "fusion.completed",
    "retention.archived",
    "retention.deleted",
)

WEBHOOK_DELIVERY_STATUSES = ("PENDING", "PROCESSING", "DELIVERED", "RETRYING", "FAILED", "DISABLED")

INTEGRATION_EVENT_STATUSES = ("PENDING", "PUBLISHED", "FAILED")


class ExternalSystem(Base):
    """BE-019: registered external system (government portal, field system, etc.)."""

    __tablename__ = "external_systems"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    organization_id = Column(
        UUID(as_uuid=False), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=True
    )
    name = Column(String(256), nullable=False)
    code = Column(String(128), nullable=False, unique=True)
    system_type = Column(String(50), nullable=False)
    status = Column(String(50), nullable=False, default="ACTIVE", server_default="ACTIVE")
    description = Column(Text, nullable=True)
    metadata_ = Column("metadata", JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "system_type IN ('GOVERNMENT_PORTAL','FIELD_SYSTEM','PROJECT_MANAGEMENT',"
            "'DOCUMENT_SYSTEM','INSPECTION_SYSTEM','DATA_PLATFORM','OTHER')",
            name="ck_external_system_type",
        ),
        CheckConstraint(
            "status IN ('ACTIVE', 'SUSPENDED', 'DISABLED')",
            name="ck_external_system_status",
        ),
        Index("ix_external_systems_org", "organization_id"),
        Index("ix_external_systems_code", "code"),
    )


class ApiCredential(Base):
    """BE-019: hashed API credential for an ApiClient. Secret never stored plaintext."""

    __tablename__ = "api_credentials"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    client_id = Column(
        UUID(as_uuid=False), ForeignKey("api_clients.id", ondelete="CASCADE"), nullable=False
    )
    credential_hash = Column(String(256), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    last_used_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_api_credentials_client", "client_id"),
        Index("ix_api_credentials_client_revoked", "client_id", "revoked_at"),
    )


class ExternalReference(Base):
    """BE-019: bidirectional mapping between PoA resources and external system identifiers."""

    __tablename__ = "external_references"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    external_system_id = Column(
        UUID(as_uuid=False), ForeignKey("external_systems.id", ondelete="RESTRICT"), nullable=False
    )
    resource_type = Column(String(100), nullable=False)
    resource_id = Column(UUID(as_uuid=False), nullable=False)
    external_id = Column(String(512), nullable=False)
    external_version = Column(String(128), nullable=True)
    first_seen_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_seen_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "external_system_id",
            "resource_type",
            "external_id",
            name="uq_external_reference_source_id",
        ),
        Index("ix_external_references_system", "external_system_id"),
        Index("ix_external_references_resource", "resource_type", "resource_id"),
    )


class ExternalAssertion(Base):
    """BE-019: provenance-preserving assertion from an external system (not PoA truth)."""

    __tablename__ = "external_assertions"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    external_system_id = Column(
        UUID(as_uuid=False), ForeignKey("external_systems.id", ondelete="RESTRICT"), nullable=False
    )
    resource_type = Column(String(100), nullable=True)
    resource_id = Column(UUID(as_uuid=False), nullable=True)
    external_id = Column(String(512), nullable=True)
    source_timestamp = Column(DateTime(timezone=True), nullable=True)
    ingested_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    payload = Column(JSONB, nullable=False, default=dict)
    api_client_id = Column(UUID(as_uuid=False), ForeignKey("api_clients.id"), nullable=True)
    request_id = Column(String(256), nullable=True)

    __table_args__ = (
        Index("ix_external_assertions_system", "external_system_id"),
        Index("ix_external_assertions_resource", "resource_type", "resource_id"),
        Index("ix_external_assertions_ingested", "ingested_at"),
    )


class IdempotencyKey(Base):
    """BE-019: per-client idempotency key with request body hash for conflict detection."""

    __tablename__ = "idempotency_keys"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    client_id = Column(
        UUID(as_uuid=False), ForeignKey("api_clients.id", ondelete="CASCADE"), nullable=False
    )
    idempotency_key = Column(String(256), nullable=False)
    request_hash = Column(String(256), nullable=False)
    result_payload = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("client_id", "idempotency_key", name="uq_idempotency_client_key"),
        Index("ix_idempotency_keys_client", "client_id"),
        Index("ix_idempotency_keys_expires", "expires_at"),
    )


class WebhookSubscription(Base):
    """BE-019: outbound webhook subscription for an external system."""

    __tablename__ = "webhook_subscriptions"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    external_system_id = Column(
        UUID(as_uuid=False), ForeignKey("external_systems.id", ondelete="CASCADE"), nullable=False
    )
    endpoint_url = Column(String(2048), nullable=False)
    status = Column(String(50), nullable=False, default="ACTIVE", server_default="ACTIVE")
    subscribed_events = Column(JSONB, nullable=False, default=list)
    secret_hash = Column(String(256), nullable=False)
    consecutive_failures = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    last_delivery_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('ACTIVE', 'SUSPENDED', 'DISABLED')",
            name="ck_webhook_subscription_status",
        ),
        Index("ix_webhook_subscriptions_system", "external_system_id"),
        Index("ix_webhook_subscriptions_status", "status"),
    )


class WebhookEvent(Base):
    """BE-019: durable integration event written transactionally (outbox for webhook delivery)."""

    __tablename__ = "webhook_events"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    event_type = Column(String(100), nullable=False)
    event_version = Column(Integer, nullable=False, default=1, server_default="1")
    aggregate_type = Column(String(100), nullable=False)
    aggregate_id = Column(UUID(as_uuid=False), nullable=False)
    project_id = Column(UUID(as_uuid=False), nullable=True)
    payload = Column(JSONB, nullable=False, default=dict)
    status = Column(String(20), nullable=False, default="PENDING", server_default="PENDING")
    occurred_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    processed_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING', 'PUBLISHED', 'FAILED')",
            name="ck_webhook_event_status",
        ),
        Index("ix_webhook_events_status", "status", "created_at"),
        Index("ix_webhook_events_project", "project_id"),
    )


class WebhookDelivery(Base):
    """BE-019: delivery attempt for one webhook event to one subscription."""

    __tablename__ = "webhook_deliveries"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    webhook_event_id = Column(
        UUID(as_uuid=False), ForeignKey("webhook_events.id", ondelete="CASCADE"), nullable=False
    )
    subscription_id = Column(
        UUID(as_uuid=False),
        ForeignKey("webhook_subscriptions.id", ondelete="CASCADE"),
        nullable=False,
    )
    status = Column(String(20), nullable=False, default="PENDING", server_default="PENDING")
    attempt_count = Column(Integer, nullable=False, default=0, server_default="0")
    last_status_code = Column(Integer, nullable=True)
    last_error = Column(Text, nullable=True)
    next_attempt_at = Column(DateTime(timezone=True), nullable=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "webhook_event_id", "subscription_id", name="uq_webhook_delivery_event_sub"
        ),
        CheckConstraint(
            "status IN ('PENDING', 'PROCESSING', 'DELIVERED', 'RETRYING', 'FAILED', 'DISABLED')",
            name="ck_webhook_delivery_status",
        ),
        Index("ix_webhook_deliveries_status_next", "status", "next_attempt_at"),
        Index("ix_webhook_deliveries_event", "webhook_event_id"),
        Index("ix_webhook_deliveries_subscription", "subscription_id"),
    )


class IntegrationEvent(Base):
    """BE-019: stable integration event store with immutable identity."""

    __tablename__ = "integration_events"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    event_type = Column(String(100), nullable=False)
    event_version = Column(Integer, nullable=False, default=1, server_default="1")
    aggregate_type = Column(String(100), nullable=False)
    aggregate_id = Column(UUID(as_uuid=False), nullable=False)
    project_id = Column(UUID(as_uuid=False), nullable=True)
    payload = Column(JSONB, nullable=False, default=dict)
    status = Column(String(20), nullable=False, default="PENDING", server_default="PENDING")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING', 'PUBLISHED', 'FAILED')",
            name="ck_integration_event_status",
        ),
        Index("ix_integration_events_status", "status", "created_at"),
        Index("ix_integration_events_aggregate", "aggregate_type", "aggregate_id"),
        Index("ix_integration_events_project", "project_id"),
    )


# ---------------------------------------------------------------------------
# BE-021 Dispute, Correction & Intelligence Invalidation Governance
# vocabularies (single source of truth; mirrored by CHECK constraints below
# and by the BE-021 Alembic migration).
# ---------------------------------------------------------------------------

# Staleness of derived intelligence (§14). Kept in a dedicated column so the
# established execution semantics of each parent status are never overloaded.
INTELLIGENCE_STALENESS_STATES = ("CURRENT", "STALE", "INVALIDATED", "SUPERSEDED")

# Objects that may be disputed (§5.1). "Fusion Assessment" maps to the BE-011
# integrity assessment; "Review Case outcome" disputes the recorded human
# decision without reopening or rewriting it (§20-21).
DISPUTE_TARGET_TYPES = (
    "EVIDENCE",
    "EVIDENCE_CLAIM_RELATIONSHIP",
    "CLAIM",
    "EXTERNAL_ASSERTION",
    "FUSION_ASSESSMENT",
    "REVIEW_CASE",
)

DISPUTE_STATUSES = (
    "OPEN",
    "UNDER_REVIEW",
    "RESOLVED",
    "REJECTED",
    "WITHDRAWN",
    "ESCALATED",
)

# Statuses that still represent an active challenge (idempotency window).
DISPUTE_ACTIVE_STATUSES = ("OPEN", "UNDER_REVIEW", "ESCALATED")

# Human resolution vocabulary (§7) — deliberately excludes FRAUD/AUTHENTIC/
# FAKE/TRUE/FALSE: those collapse evidence state and human governance.
DISPUTE_RESOLUTIONS = ("UPHELD", "REJECTED", "INCONCLUSIVE", "INSUFFICIENT_EVIDENCE")

# Corrections apply to mutable CONTEXT of evidence (§8); evidence bytes and
# their cryptographic identity stay immutable. EVIDENCE_FILE corrections
# never overwrite the original — a new version is ingested through the
# normal pipeline and linked via DERIVED_FROM lineage (§9).
CORRECTION_TARGET_TYPES = ("EVIDENCE",)

CORRECTION_CATEGORIES = (
    "PROJECT_ASSOCIATION",
    "CLAIM_ASSOCIATION",
    "LOCATION_CONTEXT",
    "CONTEXTUAL_METADATA",
    "DESCRIPTIVE_FIELD",
    "EVIDENCE_FILE",
)

# Approval and application remain distinct steps (§10).
CORRECTION_STATUSES = (
    "REQUESTED",
    "UNDER_REVIEW",
    "APPROVED",
    "APPLIED",
    "REJECTED",
    "CANCELLED",
)

# What triggered an invalidation of governed intelligence.
INVALIDATION_CAUSES = ("DISPUTE", "CORRECTION", "DIRECT")

# Reprocessing delegates to the existing BE-005 analysis pipeline (§17).
REPROCESSING_TARGET_TYPES = ("EVIDENCE",)
REPROCESSING_STATUSES = ("PENDING", "COMPLETED", "FAILED")


class Dispute(Base):
    """BE-021: authorized challenge against an object or assertion (§5.6).

    A dispute never mutates its target: resolution records human governance
    metadata only. One active dispute per (target, initiator) is enforced by
    a partial unique index so retries stay idempotent (§28).
    """

    __tablename__ = "disputes"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    target_type = Column(String(50), nullable=False)
    target_id = Column(UUID(as_uuid=False), nullable=False)
    project_id = Column(UUID(as_uuid=False), ForeignKey("projects.id"), nullable=True)
    initiator_id = Column(UUID(as_uuid=False), nullable=False)
    reason = Column(String(256), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(50), nullable=False, default="OPEN", server_default="OPEN")
    assigned_to = Column(UUID(as_uuid=False), nullable=True)
    assigned_at = Column(DateTime(timezone=True), nullable=True)
    escalated_to = Column(UUID(as_uuid=False), nullable=True)
    escalated_at = Column(DateTime(timezone=True), nullable=True)
    escalation_reason = Column(Text, nullable=True)
    resolution = Column(String(50), nullable=True)
    resolution_rationale = Column(Text, nullable=True)
    resolved_by = Column(UUID(as_uuid=False), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "target_type IN ('EVIDENCE', 'EVIDENCE_CLAIM_RELATIONSHIP', 'CLAIM', "
            "'EXTERNAL_ASSERTION', 'FUSION_ASSESSMENT', 'REVIEW_CASE')",
            name="ck_dispute_target_type",
        ),
        CheckConstraint(
            "status IN ('OPEN', 'UNDER_REVIEW', 'RESOLVED', 'REJECTED', "
            "'WITHDRAWN', 'ESCALATED')",
            name="ck_dispute_status",
        ),
        CheckConstraint(
            "resolution IN ('UPHELD', 'REJECTED', 'INCONCLUSIVE', "
            "'INSUFFICIENT_EVIDENCE') OR resolution IS NULL",
            name="ck_dispute_resolution",
        ),
        CheckConstraint(
            "(resolution IS NULL AND resolved_by IS NULL AND resolved_at IS NULL) "
            "OR (resolution IS NOT NULL AND resolved_by IS NOT NULL "
            "AND resolved_at IS NOT NULL)",
            name="ck_dispute_resolution_complete",
        ),
        CheckConstraint(
            "(resolution IS NULL) = (status <> 'RESOLVED')",
            name="ck_dispute_resolution_status_consistent",
        ),
        Index("ix_disputes_target", "target_type", "target_id"),
        Index("ix_disputes_status", "status"),
        Index("ix_disputes_project", "project_id"),
        Index("ix_disputes_initiator", "initiator_id"),
        Index("ix_disputes_assigned", "assigned_to"),
        Index("ix_disputes_created", "created_at"),
        # Idempotency (§28): at most one ACTIVE challenge per target+initiator.
        Index(
            "uq_disputes_active_target_initiator",
            "target_type",
            "target_id",
            "initiator_id",
            unique=True,
            postgresql_where=text("status IN ('OPEN', 'UNDER_REVIEW', 'ESCALATED')"),
        ),
    )


class DisputeEvent(Base):
    """BE-021: append-only dispute workflow history (never modified)."""

    __tablename__ = "dispute_events"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    dispute_id = Column(
        UUID(as_uuid=False),
        ForeignKey("disputes.id", ondelete="RESTRICT"),
        nullable=False,
    )
    event_type = Column(String(50), nullable=False)
    from_status = Column(String(50), nullable=True)
    to_status = Column(String(50), nullable=True)
    actor_id = Column(UUID(as_uuid=False), nullable=True)
    event_metadata = Column("metadata", JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    dispute = relationship("Dispute")

    __table_args__ = (
        Index("ix_dispute_events_dispute", "dispute_id", "created_at"),
    )


class CorrectionRequest(Base):
    """BE-021: first-class correction workflow for mutable evidence context (§10).

    Approval and application are distinct. ``requested_change`` carries the
    proposed context diff; ``applied_change`` records what was actually
    applied (for EVIDENCE_FILE corrections: the new evidence version and its
    lineage edge). Evidence bytes and checksums are never rewritten (§8).
    """

    __tablename__ = "correction_requests"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    target_type = Column(String(50), nullable=False)
    target_id = Column(UUID(as_uuid=False), nullable=False)
    project_id = Column(UUID(as_uuid=False), ForeignKey("projects.id"), nullable=True)
    category = Column(String(50), nullable=False)
    requested_change = Column(JSONB, nullable=False, default=dict)
    reason = Column(Text, nullable=False)
    requester_id = Column(UUID(as_uuid=False), nullable=False)
    status = Column(String(50), nullable=False, default="REQUESTED", server_default="REQUESTED")
    resolver_id = Column(UUID(as_uuid=False), nullable=True)
    resolution_rationale = Column(Text, nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    applied_by = Column(UUID(as_uuid=False), nullable=True)
    applied_at = Column(DateTime(timezone=True), nullable=True)
    applied_change = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint("target_type IN ('EVIDENCE')", name="ck_correction_target_type"),
        CheckConstraint(
            "category IN ('PROJECT_ASSOCIATION', 'CLAIM_ASSOCIATION', "
            "'LOCATION_CONTEXT', 'CONTEXTUAL_METADATA', 'DESCRIPTIVE_FIELD', "
            "'EVIDENCE_FILE')",
            name="ck_correction_category",
        ),
        CheckConstraint(
            "status IN ('REQUESTED', 'UNDER_REVIEW', 'APPROVED', 'APPLIED', "
            "'REJECTED', 'CANCELLED')",
            name="ck_correction_status",
        ),
        CheckConstraint(
            "(status = 'APPLIED') = (applied_at IS NOT NULL AND applied_by IS NOT NULL)",
            name="ck_correction_application_consistent",
        ),
        Index("ix_correction_requests_target", "target_type", "target_id"),
        Index("ix_correction_requests_status", "status"),
        Index("ix_correction_requests_project", "project_id"),
        Index("ix_correction_requests_requester", "requester_id"),
        Index("ix_correction_requests_created", "created_at"),
        # Idempotency (§28) / integrity (§39): at most one ACTIVE request per
        # (target, category, requester). A different requester may still file
        # their own request for the same change; the service-level dedupe
        # additionally collapses identical changes across requesters.
        Index(
            "uq_correction_active_target_category_requester",
            "target_type",
            "target_id",
            "category",
            "requester_id",
            unique=True,
            postgresql_where=text(
                "status IN ('REQUESTED', 'UNDER_REVIEW', 'APPROVED')"
            ),
        ),
    )


class CorrectionEvent(Base):
    """BE-021: append-only correction workflow history (never modified)."""

    __tablename__ = "correction_events"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    correction_id = Column(
        UUID(as_uuid=False),
        ForeignKey("correction_requests.id", ondelete="RESTRICT"),
        nullable=False,
    )
    event_type = Column(String(50), nullable=False)
    from_status = Column(String(50), nullable=True)
    to_status = Column(String(50), nullable=True)
    actor_id = Column(UUID(as_uuid=False), nullable=True)
    event_metadata = Column("metadata", JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    correction = relationship("CorrectionRequest")

    __table_args__ = (
        Index("ix_correction_events_correction", "correction_id", "created_at"),
    )


class IntelligenceInvalidation(Base):
    """BE-021: record of a governed invalidation and its downstream reach.

    The target row itself is never deleted or rewritten; downstream outputs
    are marked stale/invalidated via their staleness columns / existing graph
    and assessment lifecycles. The affected_* counts are bounded aggregates
    for audit payloads — not a second lineage store.
    """

    __tablename__ = "intelligence_invalidations"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    target_type = Column(String(50), nullable=False)
    target_id = Column(UUID(as_uuid=False), nullable=False)
    project_id = Column(UUID(as_uuid=False), ForeignKey("projects.id"), nullable=True)
    cause = Column(String(50), nullable=False)
    dispute_id = Column(
        UUID(as_uuid=False), ForeignKey("disputes.id", ondelete="RESTRICT"), nullable=True
    )
    correction_id = Column(
        UUID(as_uuid=False),
        ForeignKey("correction_requests.id", ondelete="RESTRICT"),
        nullable=True,
    )
    reason = Column(Text, nullable=False)
    invalidated_by = Column(UUID(as_uuid=False), nullable=False)
    affected_analysis = Column(Integer, nullable=False, default=0, server_default="0")
    affected_fusion = Column(Integer, nullable=False, default=0, server_default="0")
    affected_explanations = Column(Integer, nullable=False, default=0, server_default="0")
    affected_relationships = Column(Integer, nullable=False, default=0, server_default="0")
    affected_assessments = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "target_type IN ('EVIDENCE', 'EVIDENCE_CLAIM_RELATIONSHIP', 'CLAIM', "
            "'EXTERNAL_ASSERTION', 'FUSION_ASSESSMENT', 'REVIEW_CASE')",
            name="ck_invalidation_target_type",
        ),
        CheckConstraint(
            "cause IN ('DISPUTE', 'CORRECTION', 'DIRECT')", name="ck_invalidation_cause"
        ),
        Index("ix_intelligence_invalidations_target", "target_type", "target_id"),
        Index("ix_intelligence_invalidations_dispute", "dispute_id"),
        Index("ix_intelligence_invalidations_correction", "correction_id"),
        Index("ix_intelligence_invalidations_created", "created_at"),
    )


class ReprocessingRequest(Base):
    """BE-021: request to re-run the existing analysis pipeline (§17).

    Delegation only: the referenced ``analysis_job_id`` is created through
    BE-005's :func:`create_analysis_job`; BE-021 never duplicates worker
    logic, and no historical run is ever modified. One PENDING request per
    evidence item is enforced by a partial unique index (§28).
    """

    __tablename__ = "reprocessing_requests"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    evidence_id = Column(
        UUID(as_uuid=False), ForeignKey("evidence.id", ondelete="RESTRICT"), nullable=False
    )
    project_id = Column(UUID(as_uuid=False), ForeignKey("projects.id"), nullable=True)
    invalidation_id = Column(
        UUID(as_uuid=False),
        ForeignKey("intelligence_invalidations.id", ondelete="RESTRICT"),
        nullable=True,
    )
    requested_by = Column(UUID(as_uuid=False), nullable=False)
    reason = Column(Text, nullable=False)
    status = Column(String(50), nullable=False, default="PENDING", server_default="PENDING")
    analysis_job_id = Column(
        UUID(as_uuid=False), ForeignKey("analysis_jobs.id", ondelete="RESTRICT"), nullable=True
    )
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint("status IN ('PENDING', 'COMPLETED', 'FAILED')",
                        name="ck_reprocessing_status"),
        Index("ix_reprocessing_requests_evidence", "evidence_id"),
        Index("ix_reprocessing_requests_status", "status"),
        Index("ix_reprocessing_requests_invalidation", "invalidation_id"),
        Index("ix_reprocessing_requests_created", "created_at"),
        # Idempotency (§28): one PENDING reprocessing request per evidence item.
        Index(
            "uq_reprocessing_pending_evidence",
            "evidence_id",
            unique=True,
            postgresql_where=text("status = 'PENDING'"),
        ),
    )


# ---------------------------------------------------------------------------
# BE-022 Publication, Transparency & Public Evidence Governance vocabularies
# (single source of truth; mirrored by CHECK constraints below and by the
# BE-022 Alembic migration n4o5p6q7r022).
# ---------------------------------------------------------------------------

# §10 Default visibility classes. These are the architecture's pre-existing
# visibility concepts. Only PUBLIC may ever be returned through public
# endpoints — read authorization on an internal object does NOT imply PUBLIC.
PUBLIC_VISIBILITY_CLASSES = (
    "PUBLIC",
    "CITIZEN_OWNED_PRIVATE",
    "OPERATIONAL",
    "INTELLIGENCE_INTERNAL",
    "ADMINISTRATIVE_SECURITY",
)

# §4 Publication targets. This tuple IS the explicit allowlist: a target type
# absent from it is NOT_PUBLISHABLE_TYPE, never a policy accident.
PUBLICATION_TARGET_TYPES = (
    "PROJECT",
    "ACTIVITY",
    "CLAIM",
    "EVIDENCE",
    "REVIEW_CASE",
    "FUSION_ASSESSMENT",
)

# §6 Controlled publication lifecycle. A PUBLISHED item may never silently
# return to an editable published state; material changes create a new version.
PUBLICATION_STATUSES = (
    "DRAFT",
    "PENDING_REVIEW",
    "APPROVED",
    "PUBLISHED",
    "UNPUBLISHED",
    "REJECTED",
)

# §11 Deterministic releasability blockers. These are returned as structured
# reasons; they are never collapsed into a single NOT_ALLOWED.
PUBLICATION_BLOCKERS = (
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

# §14 Authorization levels for publication policies (min_authorization_level).
PUBLICATION_AUTHORIZATION_LEVELS = ("REVIEWER", "SUPERVISOR", "ADMINISTRATOR")

# §15 Role vocabulary used only for approval-separation bookkeeping.
PUBLICATION_POLICY_ROLES = ("REQUESTER", "REVIEWER", "SUPERVISOR_APPROVER", "PUBLISHER")

# §22 Location precision policies for public projection.
LOCATION_PRECISION_POLICIES = ("EXACT", "APPROXIMATE", "AREA", "HIDDEN")

# §9 Redaction levels.
PUBLICATION_REDACTION_LEVELS = ("NONE", "STANDARD", "STRICT")

# §20 Public media derivative types.
PUBLIC_MEDIA_DERIVATIVE_TYPES = (
    "ORIGINAL",
    "THUMBNAIL",
    "PREVIEW",
    "REDACTED",
    "TRANSCODED",
)

# §4/§19 Objects that may never be exposed publicly regardless of policy.
# Enforced defensively by the projection layer.
PUBLICATION_INTERNALLY_PROHIBITED_FIELDS = (
    "storage_key",
    "credential",
    "credentials",
    "auth",
    "authorization",
    "password",
    "token",
    "secret",
    "exif",
    "private_metadata",
    "internal_notes",
    "reviewer_notes",
    "priority_score",
    "review_priority",
    "fusion_signals",
    "internal_graph",
    "user_id",
    "user_ids",
    "actor_id",
    "reviewer_id",
)


class PublicationPolicy(Base):
    """BE-022: named publication policy identity (rules live in versions).

    A policy is the reusable identity; its rules are versioned through
    :class:`PublicationPolicyVersion`, which is immutable. Changing a policy
    creates a new version — it never mutates the existing one (§9).
    """

    __tablename__ = "publication_policies"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    versions = relationship(
        "PublicationPolicyVersion",
        back_populates="policy",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("name", name="uq_publication_policy_name"),
    )


class PublicationPolicyVersion(Base):
    """BE-022: immutable versioned publication rules (§9).

    One version is the ACTIVE one at a time; publishing a new version
    SUPERSEDES the prior. Historical versions stay queryable because a
    published snapshot must remain attributable to the exact policy that
    authorized it.
    """

    __tablename__ = "publication_policy_versions"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    policy_id = Column(
        UUID(as_uuid=False),
        ForeignKey("publication_policies.id", ondelete="CASCADE"),
        nullable=False,
    )
    version = Column(String(20), nullable=False)
    status = Column(String(20), nullable=False, default="DRAFT", server_default="DRAFT")
    allowed_target_types = Column(JSONB, nullable=False, default=list)
    public_fields = Column(JSONB, nullable=False, default=list)
    prohibited_fields = Column(JSONB, nullable=False, default=list)
    allow_media_exposure = Column(Boolean, nullable=False, default=False, server_default="false")
    allow_derived_intelligence = Column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    allow_review_outcomes = Column(Boolean, nullable=False, default=False, server_default="false")
    min_authorization_level = Column(
        String(20), nullable=False, default="REVIEWER", server_default="REVIEWER"
    )
    required_approvals = Column(Integer, nullable=False, default=1, server_default="1")
    require_separation_of_duties = Column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    location_precision = Column(
        String(20), nullable=False, default="HIDDEN", server_default="HIDDEN"
    )
    retention_publication_duration_days = Column(Integer, nullable=True)
    geographic_restrictions = Column(JSONB, nullable=True)
    privacy_restrictions = Column(JSONB, nullable=True)
    redaction_level = Column(
        String(20), nullable=False, default="STANDARD", server_default="STANDARD"
    )
    created_by = Column(UUID(as_uuid=False), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    policy = relationship("PublicationPolicy", back_populates="versions")

    __table_args__ = (
        UniqueConstraint("policy_id", "version", name="uq_publication_policy_version"),
        CheckConstraint(
            "status IN ('DRAFT', 'ACTIVE', 'SUPERSEDED', 'RETIRED')",
            name="ck_publication_policy_version_status",
        ),
        CheckConstraint(
            "min_authorization_level IN ('REVIEWER', 'SUPERVISOR', 'ADMINISTRATOR')",
            name="ck_publication_policy_auth_level",
        ),
        CheckConstraint(
            "location_precision IN ('EXACT', 'APPROXIMATE', 'AREA', 'HIDDEN')",
            name="ck_publication_policy_location_precision",
        ),
        CheckConstraint(
            "redaction_level IN ('NONE', 'STANDARD', 'STRICT')",
            name="ck_publication_policy_redaction",
        ),
        CheckConstraint("required_approvals >= 1", name="ck_publication_policy_required_approvals"),
        CheckConstraint(
            "version ~ '^\\d+\\.\\d+$'", name="ck_publication_policy_version_format"
        ),
        # Exactly one ACTIVE version per policy.
        Index(
            "uq_publication_policy_active_version",
            "policy_id",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
        ),
        Index("ix_publication_policy_versions_policy", "policy_id"),
    )


class PublicIdentifier(Base):
    """BE-022: stable, non-sensitive public identifier (§16).

    Never derived from a secret and never exposing the internal UUID. The
    identifier is stable across publication versions: it is minted once per
    target and reused by every version of that target's publication.
    """

    __tablename__ = "public_identifiers"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    target_type = Column(String(50), nullable=False)
    target_id = Column(UUID(as_uuid=False), nullable=False)
    public_id = Column(String(50), nullable=False)
    namespace = Column(String(20), nullable=False, default="POA", server_default="POA")
    identifier_type = Column(
        String(20), nullable=False, default="SEQUENTIAL", server_default="SEQUENTIAL"
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("public_id", name="uq_public_identifier_public_id"),
        # One identifier per target: stability across versions is structural.
        UniqueConstraint(
            "target_type", "target_id", name="uq_public_identifier_target"
        ),
        CheckConstraint(
            "target_type IN ('PROJECT', 'ACTIVITY', 'CLAIM', 'EVIDENCE', "
            "'REVIEW_CASE', 'FUSION_ASSESSMENT')",
            name="ck_public_identifier_target_type",
        ),
        CheckConstraint(
            "identifier_type IN ('SEQUENTIAL', 'HASHED', 'RANDOM')",
            name="ck_public_identifier_type",
        ),
        Index("ix_public_identifiers_public_id", "public_id"),
        Index("ix_public_identifiers_target", "target_type", "target_id"),
    )


class Publication(Base):
    """BE-022: first-class governed public representation (§4).

    The publication row is the *governance container*; the actual
    public-facing payload lives in immutable :class:`PublicationVersion`
    snapshots. Status on this row tracks the current lifecycle state.

    Publication means "this specific information has been authorized for
    public visibility" — it never asserts that the underlying evidence is
    true (§2).
    """

    __tablename__ = "publications"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    target_type = Column(String(50), nullable=False)
    target_id = Column(UUID(as_uuid=False), nullable=False)
    policy_id = Column(
        UUID(as_uuid=False),
        ForeignKey("publication_policies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    policy_version_id = Column(
        UUID(as_uuid=False),
        ForeignKey("publication_policy_versions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    public_id = Column(String(50), nullable=True)
    current_version_number = Column(
        Integer, nullable=False, default=0, server_default="0"
    )
    status = Column(String(20), nullable=False, default="DRAFT", server_default="DRAFT")
    requested_by = Column(UUID(as_uuid=False), nullable=False)
    reviewer_id = Column(UUID(as_uuid=False), nullable=True)
    approver_id = Column(UUID(as_uuid=False), nullable=True)
    publisher_id = Column(UUID(as_uuid=False), nullable=True)
    reason = Column(Text, nullable=False)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    published_at = Column(DateTime(timezone=True), nullable=True)
    unpublished_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    versions = relationship(
        "PublicationVersion",
        back_populates="publication",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        CheckConstraint(
            "target_type IN ('PROJECT', 'ACTIVITY', 'CLAIM', 'EVIDENCE', "
            "'REVIEW_CASE', 'FUSION_ASSESSMENT')",
            name="ck_publication_target_type",
        ),
        CheckConstraint(
            "status IN ('DRAFT', 'PENDING_REVIEW', 'APPROVED', 'PUBLISHED', "
            "'UNPUBLISHED', 'REJECTED')",
            name="ck_publication_status",
        ),
        CheckConstraint("current_version_number >= 0", name="ck_publication_version_number"),
        # §6: a published item may not silently return to an editable state.
        CheckConstraint(
            "(status = 'PUBLISHED') = (published_at IS NOT NULL AND unpublished_at IS NULL)",
            name="ck_publication_published_consistent",
        ),
        CheckConstraint(
            "(status = 'UNPUBLISHED') = (unpublished_at IS NOT NULL)",
            name="ck_publication_unpublished_consistent",
        ),
        Index("ix_publications_target", "target_type", "target_id"),
        Index("ix_publications_status", "status"),
        Index("ix_publications_public_id", "public_id"),
        Index("ix_publications_created", "created_at"),
        # One governed publication container per target.
        UniqueConstraint(
            "target_type", "target_id", name="uq_publication_active_target"
        ),
    )


class PublicationVersion(Base):
    """BE-022: immutable published snapshot version (§7, §8, §32).

    Once ``status`` reaches PUBLISHED the row is frozen: the snapshot is the
    historical public representation and is never rebuilt from mutable domain
    records. Material changes create a new version rather than mutating this
    one. JSONB is used for the structured snapshot; raw media never lives here.
    """

    __tablename__ = "publication_versions"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    publication_id = Column(
        UUID(as_uuid=False),
        ForeignKey("publications.id", ondelete="CASCADE"),
        nullable=False,
    )
    version_number = Column(Integer, nullable=False)
    snapshot = Column(JSONB, nullable=False, default=dict)
    public_id = Column(String(50), nullable=False)
    target_type = Column(String(50), nullable=False)
    target_id = Column(UUID(as_uuid=False), nullable=False)
    status = Column(String(20), nullable=False, default="DRAFT", server_default="DRAFT")
    policy_version_id = Column(
        UUID(as_uuid=False),
        ForeignKey("publication_policy_versions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    source_version_references = Column(JSONB, nullable=True)
    requested_by = Column(UUID(as_uuid=False), nullable=False)
    approved_by = Column(UUID(as_uuid=False), nullable=True)
    published_by = Column(UUID(as_uuid=False), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    published_at = Column(DateTime(timezone=True), nullable=True)
    unpublished_at = Column(DateTime(timezone=True), nullable=True)

    publication = relationship("Publication", back_populates="versions")

    __table_args__ = (
        UniqueConstraint(
            "publication_id", "version_number", name="uq_publication_version_number"
        ),
        CheckConstraint("version_number >= 1", name="ck_publication_version_positive"),
        CheckConstraint(
            "status IN ('DRAFT', 'PENDING_REVIEW', 'APPROVED', 'PUBLISHED', "
            "'UNPUBLISHED', 'REJECTED')",
            name="ck_publication_version_status",
        ),
        CheckConstraint(
            "(status = 'PUBLISHED') = (published_at IS NOT NULL AND unpublished_at IS NULL)",
            name="ck_publication_version_published_consistent",
        ),
        Index("ix_publication_versions_publication", "publication_id"),
        Index("ix_publication_versions_status", "status"),
        Index("ix_publication_versions_public_id", "public_id"),
        Index("ix_publication_versions_created", "created_at"),
    )


class PublicationEvent(Base):
    """BE-022: append-only publication workflow history (never modified)."""

    __tablename__ = "publication_events"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    publication_id = Column(
        UUID(as_uuid=False),
        ForeignKey("publications.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type = Column(String(50), nullable=False)
    from_status = Column(String(20), nullable=True)
    to_status = Column(String(20), nullable=True)
    actor_id = Column(UUID(as_uuid=False), nullable=True)
    reason = Column(Text, nullable=True)
    event_metadata = Column("metadata", JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_publication_events_publication", "publication_id", "created_at"),
        Index("ix_publication_events_created", "created_at"),
    )


class PublicMediaDerivative(Base):
    """BE-022: approved public-safe derivative of original evidence (§19, §20).

    The derivative references the original evidence row; original evidence
    bytes are never modified. Storage keys recorded here are derivative
    storage references governed by BE-002, and are NEVER exposed through a
    public response — the public surface serves media by public ID only.
    """

    __tablename__ = "public_media_derivatives"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    publication_id = Column(
        UUID(as_uuid=False),
        ForeignKey("publications.id", ondelete="CASCADE"),
        nullable=False,
    )
    publication_version_id = Column(
        UUID(as_uuid=False),
        ForeignKey("publication_versions.id", ondelete="CASCADE"),
        nullable=True,
    )
    original_evidence_id = Column(
        UUID(as_uuid=False),
        ForeignKey("evidence.id", ondelete="RESTRICT"),
        nullable=False,
    )
    derivative_type = Column(String(20), nullable=False)
    storage_key = Column(String(255), nullable=False)
    storage_bucket = Column(String(100), nullable=False)
    transformation = Column(Text, nullable=True)
    transformation_version = Column(String(20), nullable=True)
    sha256 = Column(String(64), nullable=True)
    created_by = Column(UUID(as_uuid=False), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "derivative_type IN ('ORIGINAL', 'THUMBNAIL', 'PREVIEW', "
            "'REDACTED', 'TRANSCODED')",
            name="ck_public_media_derivative_type",
        ),
        Index("ix_public_media_derivatives_publication", "publication_id"),
        Index("ix_public_media_derivatives_evidence", "original_evidence_id"),
    )


# ---------------------------------------------------------------------------
# BE-026: field operations and offline evidence capture
# ---------------------------------------------------------------------------

FIELD_ASSIGNMENT_STATUSES = ("ACTIVE", "RELEASED", "REVOKED", "EXPIRED")
FIELD_SESSION_STATUSES = ("ACTIVE", "CLOSED", "EXPIRED")
#: ``PENDING`` is a reservation, not a queue position: ``ingest_evidence``
#: commits the Evidence row itself, so the operation identity has to be
#: committed *before* ingest runs. That is what makes a concurrent or repeated
#: submission physically unable to create a second Evidence row.
FIELD_OPERATION_STATUSES = ("PENDING", "ACCEPTED", "VALIDATION_FAILED", "CONFLICT")
FIELD_CONFLICT_REASONS = (
    "PAYLOAD_MISMATCH",
    "ASSIGNMENT_REVOKED",
    "ASSIGNMENT_EXPIRED",
    "SESSION_CLOSED",
    "OPERATION_SESSION_MISMATCH",
    "CONTEXT_RESOURCE_MISSING",
    "ASSIGNMENT_SUPERSEDED",
)
FIELD_LOCATION_SOURCES = ("DEVICE_GPS", "DEVICE_MANUAL", "CLIENT_INFERRED", "UNKNOWN")
FIELD_RESOLUTION_STATUSES = ("UNRESOLVED", "RESOLVED")

#: Response-only synchronization vocabulary (task §11). ``rejected`` and
#: ``temporarily_unavailable`` are deliberately absent from the persisted
#: ``FIELD_OPERATION_STATUSES``: a denial never mutates domain state, and a
#: dependency outage rolls back so a retry can succeed. ``PENDING`` is the
#: inverse case — an internal reservation that is never a response; a caller
#: that reaches a live reservation is told ``temporarily_unavailable`` so it
#: retries into the real outcome.
FIELD_SYNC_STATUSES = (
    "accepted",
    "already_synchronized",
    "rejected",
    "conflict",
    "authorization_denied",
    "validation_failed",
    "temporarily_unavailable",
)


class FieldAssignment(Base):
    """BE-026: operational field work. Grants no authority whatsoever.

    Authorization continues to come only from ``user_role_assignments`` via
    ``can()``. A synchronization succeeds when the permission gate, the
    server-resolved scope gate and one ACTIVE row of this table all hold; an
    assignment for a user without the matching role grant produces a denial,
    never access. Revocation closes the row instead of deleting it so that
    "assignment revoked while the device was offline" stays testable.
    """

    __tablename__ = "field_assignments"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    user_id = Column(
        UUID(as_uuid=False), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    project_id = Column(
        UUID(as_uuid=False), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    # Organizational scope is derived server-side from the project and is never
    # accepted from a client, so there is no field to forge.
    organization_id = Column(UUID(as_uuid=False), ForeignKey("organizations.id"), nullable=True)
    organizational_unit_id = Column(
        UUID(as_uuid=False), ForeignKey("organizational_units.id"), nullable=True
    )
    claim_id = Column(UUID(as_uuid=False), ForeignKey("claims.id"), nullable=True)
    activity_id = Column(UUID(as_uuid=False), ForeignKey("activities.id"), nullable=True)
    status = Column(String(32), nullable=False, default="ACTIVE", server_default="ACTIVE")
    valid_from = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    instructions = Column(Text, nullable=True)
    created_by = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=True)
    revoked_by = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    closed_reason = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('ACTIVE', 'RELEASED', 'REVOKED', 'EXPIRED')",
            name="ck_field_assignment_status",
        ),
        CheckConstraint(
            "expires_at IS NULL OR valid_from IS NULL OR expires_at > valid_from",
            name="ck_field_assignment_validity_window",
        ),
        CheckConstraint(
            "closed_reason IS NULL OR status <> 'ACTIVE'",
            name="ck_field_assignment_closed_reason",
        ),
        # One general ACTIVE assignment per (officer, project) ...
        Index(
            "uq_field_assignments_active_general",
            "user_id", "project_id",
            unique=True,
            postgresql_where=text("status = 'ACTIVE' AND claim_id IS NULL"),
        ),
        # ... and one per (officer, project, claim) for claim-scoped work.
        Index(
            "uq_field_assignments_active_claim",
            "user_id", "project_id", "claim_id",
            unique=True,
            postgresql_where=text("status = 'ACTIVE' AND claim_id IS NOT NULL"),
        ),
        Index("ix_field_assignments_user_status", "user_id", "status"),
        Index("ix_field_assignments_project", "project_id"),
    )


class FieldSession(Base):
    """BE-026: server-minted execution context for one assignment.

    The session is what stops an offline client from authorizing itself with a
    stale assignment snapshot: it is created by the server after the authority
    check, and every synchronization is re-validated against both the session
    row and the current assignment row.
    """

    __tablename__ = "field_sessions"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    assignment_id = Column(
        UUID(as_uuid=False),
        ForeignKey("field_assignments.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # Copied from the assignment at open time; never accepted from a client.
    user_id = Column(
        UUID(as_uuid=False), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    project_id = Column(
        UUID(as_uuid=False), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    organization_id = Column(UUID(as_uuid=False), ForeignKey("organizations.id"), nullable=True)
    status = Column(String(32), nullable=False, default="ACTIVE", server_default="ACTIVE")
    session_label = Column(String(128), nullable=True)
    client_device_id = Column(String(128), nullable=True)
    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    #: Lets the client compute its own clock skew. Never used to rewrite or
    #: backfill a client-reported timestamp.
    server_time_at_open = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    closed_at = Column(DateTime(timezone=True), nullable=True)
    close_reason = Column(String(255), nullable=True)
    last_sync_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('ACTIVE', 'CLOSED', 'EXPIRED')",
            name="ck_field_session_status",
        ),
        CheckConstraint(
            "(status = 'ACTIVE' AND closed_at IS NULL)"
            " OR (status <> 'ACTIVE' AND closed_at IS NOT NULL)",
            name="ck_field_session_close_shape",
        ),
        Index(
            "uq_field_sessions_active_device",
            "assignment_id", "client_device_id",
            unique=True,
            postgresql_where=text("status = 'ACTIVE' AND client_device_id IS NOT NULL"),
        ),
        Index("ix_field_sessions_user_status", "user_id", "status"),
        Index("ix_field_sessions_assignment", "assignment_id"),
    )


class FieldCaptureOperation(Base):
    """BE-026: idempotent offline synchronization ledger and provenance record.

    One row per (officer, ``client_operation_id``). The unique constraint is
    what makes a retry after a timeout answerable and a duplicate Evidence
    impossible; ``request_hash`` (which covers a digest of the payload bytes)
    is what turns "same identity, different payload" into an explicit conflict
    instead of a silent overwrite. Client-asserted and server-observed
    timestamps are stored separately and independently nullable, so a value
    that was never known stays unknown rather than being fabricated from a
    neighbouring column.
    """

    __tablename__ = "field_capture_operations"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    user_id = Column(
        UUID(as_uuid=False), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    client_operation_id = Column(String(128), nullable=False)
    client_capture_id = Column(String(128), nullable=True)
    client_device_id = Column(String(128), nullable=True)
    session_id = Column(UUID(as_uuid=False), ForeignKey("field_sessions.id"), nullable=True)
    assignment_id = Column(UUID(as_uuid=False), ForeignKey("field_assignments.id"), nullable=True)
    project_id = Column(UUID(as_uuid=False), ForeignKey("projects.id"), nullable=True)
    claim_id = Column(UUID(as_uuid=False), ForeignKey("claims.id"), nullable=True)
    # SET NULL: retention may later remove the canonical row, but the
    # synchronization and provenance record must survive.
    evidence_id = Column(UUID(as_uuid=False), ForeignKey("evidence.id", ondelete="SET NULL"),
                         nullable=True)

    request_hash = Column(String(64), nullable=False)
    #: Idempotency digest of the submitted bytes. Not the Evidence fingerprint
    #: (that stays the analysis job's job); both hash the same bytes, so they
    #: agree, and Stage D verifies exactly that.
    payload_sha256 = Column(String(64), nullable=False)
    declared_content_type = Column(String(128), nullable=True)
    filename = Column(String(512), nullable=True)
    file_size = Column(BigInteger, nullable=False)

    status = Column(String(32), nullable=False)
    #: Machine-readable reasons for a pre-ingest rejection, kept on the row so
    #: the durable record explains itself to a retrying client and to audit.
    validation_errors = Column(
        JSONB, nullable=False, default=list, server_default=text("'[]'")
    )

    captured_at = Column(DateTime(timezone=True), nullable=True)
    queued_at = Column(DateTime(timezone=True), nullable=True)
    uploaded_at = Column(DateTime(timezone=True), nullable=True)
    received_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    #: Observed ordering anomalies (labels, never rewrites or rejections).
    timestamp_flags = Column(JSONB, nullable=False, default=list, server_default=text("'[]'"))

    latitude = Column(Numeric(9, 6), nullable=True)
    longitude = Column(Numeric(9, 6), nullable=True)
    capture_accuracy_m = Column(Numeric(10, 2), nullable=True)
    altitude_m = Column(Numeric(8, 2), nullable=True)
    location_source = Column(String(32), nullable=True)
    zero_island_confirmed = Column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )

    conflict_reason = Column(String(64), nullable=True)
    conflict_detail = Column(JSONB, nullable=True)
    resolution_status = Column(
        String(32), nullable=False, default="UNRESOLVED", server_default="UNRESOLVED"
    )
    resolved_by = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolution_note = Column(Text, nullable=True)
    #: Terminal annotation kind: DISMISSED or RESUBMISSION_REQUIRED.
    resolution_outcome = Column(String(32), nullable=True)

    sync_count = Column(Integer, nullable=False, default=1, server_default=text("1"))
    last_synced_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "user_id", "client_operation_id", name="uq_field_operations_user_client_id"
        ),
        CheckConstraint(
            "char_length(client_operation_id) >= 8",
            name="ck_field_operations_operation_id_length",
        ),
        CheckConstraint(
            "status IN ('PENDING', 'ACCEPTED', 'VALIDATION_FAILED', 'CONFLICT')",
            name="ck_field_operations_status",
        ),
        CheckConstraint(
            "status <> 'VALIDATION_FAILED' OR validation_errors <> '[]'::jsonb",
            name="ck_field_operations_validation_shape",
        ),
        CheckConstraint(
            "status <> 'PENDING' OR evidence_id IS NULL",
            name="ck_field_operations_pending_is_reservation",
        ),
        CheckConstraint(
            "conflict_reason IN ('PAYLOAD_MISMATCH', 'ASSIGNMENT_REVOKED',"
            " 'ASSIGNMENT_EXPIRED', 'SESSION_CLOSED', 'OPERATION_SESSION_MISMATCH',"
            " 'CONTEXT_RESOURCE_MISSING', 'ASSIGNMENT_SUPERSEDED')",
            name="ck_field_operations_conflict_reason",
        ),
        # A conflict is either a CONFLICT row with a reason or a row with
        # neither; the CHECK also keeps PAYLOAD_MISMATCH (recorded in the
        # ledger against the untouched existing row) out of this table.
        CheckConstraint(
            "(status = 'CONFLICT' AND conflict_reason IS NOT NULL)"
            " OR (status <> 'CONFLICT' AND conflict_reason IS NULL)",
            name="ck_field_operations_conflict_shape",
        ),
        CheckConstraint(
            "resolution_status = 'UNRESOLVED' OR status = 'CONFLICT'",
            name="ck_field_operations_resolution_needs_conflict",
        ),
        CheckConstraint(
            "resolution_status IN ('UNRESOLVED', 'RESOLVED')",
            name="ck_field_operations_resolution_status",
        ),
        # No "ACCEPTED implies evidence_id IS NOT NULL" CHECK: the evidence FK
        # is ON DELETE SET NULL, so a retention purge legitimately leaves an
        # accepted operation pointing at nothing. A CHECK here would abort that
        # purge (and every later UPDATE of the row), so the pairing is a
        # service-level invariant instead: the executor writes status and
        # evidence_id in one statement and never writes ACCEPTED without one.
        CheckConstraint("latitude IS NULL OR (latitude >= -90 AND latitude <= 90)",
                        name="ck_field_operations_latitude_range"),
        CheckConstraint("longitude IS NULL OR (longitude >= -180 AND longitude <= 180)",
                        name="ck_field_operations_longitude_range"),
        CheckConstraint("capture_accuracy_m IS NULL OR (capture_accuracy_m > 0"
                        " AND capture_accuracy_m <= 100000)",
                        name="ck_field_operations_accuracy_range"),
        CheckConstraint("altitude_m IS NULL OR (altitude_m >= -1000 AND altitude_m <= 10000)",
                        name="ck_field_operations_altitude_range"),
        CheckConstraint(
            "num_nonnulls(latitude, longitude) IN (0, 2)",
            name="ck_field_operations_coordinate_pair",
        ),
        # Missing GPS can never be silently recorded as 0,0.
        CheckConstraint(
            "NOT (latitude = 0 AND longitude = 0 AND zero_island_confirmed IS NOT TRUE)",
            name="ck_field_operations_zero_island_confirmed",
        ),
        CheckConstraint("latitude IS NULL OR location_source IS NOT NULL",
                        name="ck_field_operations_source_when_located"),
        CheckConstraint("capture_accuracy_m IS NULL OR latitude IS NOT NULL",
                        name="ck_field_operations_accuracy_needs_fix"),
        CheckConstraint(
            "location_source IS NULL OR location_source IN"
            " ('DEVICE_GPS', 'DEVICE_MANUAL', 'CLIENT_INFERRED', 'UNKNOWN')",
            name="ck_field_operations_location_source",
        ),
        Index("ix_field_operations_user_status", "user_id", "status"),
        Index("ix_field_operations_session", "session_id"),
        Index("ix_field_operations_evidence", "evidence_id"),
        Index(
            "ix_field_operations_open_conflicts",
            "created_at",
            postgresql_where=text("status = 'CONFLICT' AND resolution_status = 'UNRESOLVED'"),
        ),
    )
