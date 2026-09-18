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

