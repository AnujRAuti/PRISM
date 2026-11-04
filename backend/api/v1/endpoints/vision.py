"""BE-009 vision retrieval endpoint (read-only observations, no verdicts)."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.db.models import Evidence, VisionDetection
from backend.db.session import get_db
from backend.schemas.vision import (
    VisionBoundingBox,
    VisionDetectionItem,
    VisionEvidenceResponse,
    VisionResultPayload,
)
from backend.services.vision_intelligence import get_latest_vision_result
from backend.security.authorization import require
from backend.services.authorization import Principal


router = APIRouter()


@router.get("/evidence/{evidence_id}/vision", response_model=VisionEvidenceResponse)
def get_evidence_vision(
    evidence_id: UUID,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("evidence.read", "evidence", "evidence_id")),
) -> VisionEvidenceResponse:
    evidence = db.query(Evidence).filter(Evidence.id == str(evidence_id)).one_or_none()
    if evidence is None:
        raise HTTPException(status_code=404, detail="Evidence not found")
    result = get_latest_vision_result(str(evidence_id), db)
    if result is None or not isinstance(result.result, dict):
        raise HTTPException(status_code=404, detail="No vision analysis found for this evidence")
    try:
        payload = VisionResultPayload(**result.result)
    except ValueError as error:
        raise HTTPException(status_code=500, detail="Stored vision result is invalid") from error

    base_query = (
        db.query(VisionDetection)
        .filter(VisionDetection.analysis_result_id == result.id)
        .order_by(VisionDetection.confidence.desc(), VisionDetection.id)
    )
    total = base_query.count()
    rows = base_query.offset(offset).limit(limit).all()
    return VisionEvidenceResponse(
        evidence_id=evidence_id,
        job_id=UUID(result.job_id),
        result=payload,
        detections=[
            VisionDetectionItem(
                class_id=row.class_id,
                class_name=row.class_name,
                confidence=row.confidence,
                bounding_box=VisionBoundingBox(
                    x_min=row.x_min, y_min=row.y_min, x_max=row.x_max, y_max=row.y_max
                ),
            )
            for row in rows
        ],
        limit=limit,
        offset=offset,
        total=total,
    )
