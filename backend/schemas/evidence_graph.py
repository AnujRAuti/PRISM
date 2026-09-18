"""BE-010 Pydantic v2 schemas for the Evidence Graph.

Relationships record observed/analytical structure with provenance. They
are not determinations of truth, fraud, authenticity, risk, or compliance.
"""

from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class NodeType(str, Enum):
    PROJECT = "PROJECT"
    ACTIVITY = "ACTIVITY"
    CLAIM = "CLAIM"
    EVIDENCE = "EVIDENCE"
    ANALYSIS_RESULT = "ANALYSIS_RESULT"
    VISION_DETECTION = "VISION_DETECTION"
    DUPLICATE_MATCH = "DUPLICATE_MATCH"


class RelationshipType(str, Enum):
    BELONGS_TO = "BELONGS_TO"
    CONTAINS_ACTIVITY = "CONTAINS_ACTIVITY"
    RELATES_TO_CLAIM = "RELATES_TO_CLAIM"
    SUPPORTS = "SUPPORTS"
    CONTRADICTS = "CONTRADICTS"
    ASSOCIATED_WITH = "ASSOCIATED_WITH"
    DUPLICATE_OF = "DUPLICATE_OF"
    TEMPORALLY_RELATED_TO = "TEMPORALLY_RELATED_TO"
    HAS_ANALYSIS = "HAS_ANALYSIS"
    HAS_DETECTION = "HAS_DETECTION"
    DERIVED_FROM = "DERIVED_FROM"


class RelationshipStatus(str, Enum):
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    INVALIDATED = "INVALIDATED"


class Direction(str, Enum):
    OUTGOING = "outgoing"
    INCOMING = "incoming"
    BOTH = "both"


class NodeRef(BaseModel):
    node_type: NodeType = Field(description="Typed graph node (domain or intelligence object)")
    entity_id: UUID = Field(description="UUID of the underlying domain/intelligence row")


class Provenance(BaseModel):
    source: str = Field(
        min_length=1,
        max_length=256,
        description="Where the relationship came from (never what is true)",
    )
    method: str = Field(min_length=1, max_length=256)
    method_version: str | None = Field(default=None, max_length=256)
    analysis_run_id: UUID | None = Field(
        default=None, description="Analysis execution that generated this edge, if any"
    )


class RelationshipCreate(BaseModel):
    source: NodeRef
    target: NodeRef
    relationship_type: RelationshipType
    provenance: Provenance
    explanation: str | None = Field(default=None, max_length=2000)


class NodeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    node_type: NodeType
    entity_id: UUID


class RelationshipResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source: NodeResponse
    target: NodeResponse
    relationship_type: RelationshipType
    relationship_status: RelationshipStatus
    provenance: dict
    method: str | None = None
    method_version: str | None = None
    analysis_run_id: UUID | None = None
    explanation: str | None = None
    created_at: str | None = None


class RelationshipListResponse(BaseModel):
    node: NodeResponse | None = Field(
        default=None, description="Null when the entity has no graph node yet (no edges recorded)"
    )
    items: list[RelationshipResponse]
    limit: int
    offset: int
    total: int


class RelationshipStatusUpdate(BaseModel):
    relationship_status: RelationshipStatus = Field(
        description="ACTIVE edges may transition to SUPERSEDED or INVALIDATED"
    )
