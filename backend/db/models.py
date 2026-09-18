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

