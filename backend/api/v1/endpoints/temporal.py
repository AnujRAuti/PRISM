from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.db.session import get_db
from backend.schemas.temporal import TemporalAnalysisResponse, TemporalRequest
from backend.services.temporal_intelligence import analyze_evidence


router = APIRouter(prefix="/analysis")


@router.post("/temporal/{evidence_id}", response_model=TemporalAnalysisResponse)
def run_temporal_analysis(
    evidence_id: UUID,
    request: TemporalRequest | None = None,
    db: Session = Depends(get_db),
) -> TemporalAnalysisResponse:
    compare_ids = [str(item) for item in (request.compare_evidence_ids if request else []) or []]
    for candidate in compare_ids:
        try:
            UUID(candidate)
        except ValueError as error:
            raise HTTPException(status_code=422, detail="Invalid compare evidence ID") from error
    try:
        result = analyze_evidence(str(evidence_id), db, compare_ids or None)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return TemporalAnalysisResponse(**result)
