from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from backend.db.session import get_db
from backend.schemas.analysis import AnalysisJobCreate, AnalysisJobResponse
from backend.security.authentication import is_development_bypass
from backend.security.authorization import enforce, require
from backend.services.analysis_jobs import (
    create_analysis_job,
    get_analysis_job,
    get_analysis_result,
)
from backend.services.authorization import Principal, resolve_resource_scope


router = APIRouter(prefix="/analysis")


@router.post("/jobs", response_model=AnalysisJobResponse, status_code=status.HTTP_202_ACCEPTED)
def create_job(
    payload: AnalysisJobCreate,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("intelligence.reprocess")),
) -> AnalysisJobResponse:
    try:
        UUID(payload.evidence_id)
        # The target evidence is named in the body, so its scope can only be
        # resolved here (the correction endpoint's pattern): a grant held for
        # one project must not enqueue worker work over another organization's
        # evidence. HTTPException is not caught by the handlers below.
        if not is_development_bypass(principal):
            enforce(
                principal,
                "intelligence.reprocess",
                resolve_resource_scope(db, "evidence", payload.evidence_id),
                request,
            )
        job = create_analysis_job(payload.evidence_id, db, job_type=payload.job_type)
    except ValueError as error:
        raise HTTPException(status_code=422, detail="Invalid evidence ID") from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return _response(job, db)


@router.get("/jobs/{job_id}", response_model=AnalysisJobResponse)
def get_job(
    job_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("evidence.read", "analysis_job", "job_id")),
) -> AnalysisJobResponse:
    try:
        UUID(job_id)
    except ValueError as error:
        raise HTTPException(status_code=422, detail="Invalid job ID") from error
    job = get_analysis_job(job_id, db)
    if job is None:
        raise HTTPException(status_code=404, detail="Analysis job not found")
    return _response(job, db)


def _response(job, db: Session) -> AnalysisJobResponse:
    result: Any = get_analysis_result(job.id, db)
    return AnalysisJobResponse(
        job_id=job.id,
        evidence_id=job.evidence_id,
        status=job.status,
        attempt_count=job.attempt_count,
        error=job.error,
        started_at=job.started_at,
        completed_at=job.completed_at,
        result=result.result if result else None,
    )