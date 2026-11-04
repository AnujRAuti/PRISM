"""BE-009 Pydantic v2 schemas for vision intelligence retrieval."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class VisionBoundingBox(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    x_min: float = Field(ge=0.0, le=1.0)
    y_min: float = Field(ge=0.0, le=1.0)
    x_max: float = Field(ge=0.0, le=1.0)
    y_max: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _check_ordering(self) -> "VisionBoundingBox":
        if not self.x_min < self.x_max:
            raise ValueError("x_min must be < x_max")
        if not self.y_min < self.y_max:
            raise ValueError("y_min must be < y_max")
        return self


class VisionDetectionItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    class_id: int = Field(ge=0)
    class_name: str = Field(min_length=1, max_length=128)
    confidence: float = Field(ge=0.0, le=1.0)
    bounding_box: VisionBoundingBox


class VisionModelInfo(BaseModel):
    name: str = Field(min_length=1)
    version: str | None = None
    conf_threshold: float = Field(ge=0.0, le=1.0)
    iou_threshold: float = Field(ge=0.0, le=1.0)
    max_detections: int = Field(ge=1)
    device: str = Field(min_length=1)


class VisionImageInfo(BaseModel):
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class VisionResultPayload(BaseModel):
    analysis_type: Literal["vision_detection"]
    model: VisionModelInfo
    image: VisionImageInfo
    detection_count: int = Field(ge=0)
    invalid_boxes_dropped: int = Field(ge=0)
    duration_ms: float = Field(ge=0.0)
    status: Literal["success"]


class VisionEvidenceResponse(BaseModel):
    evidence_id: UUID
    job_id: UUID
    result: VisionResultPayload
    detections: list[VisionDetectionItem]
    limit: int
    offset: int
    total: int
