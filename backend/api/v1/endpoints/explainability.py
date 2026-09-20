"""BE-012 Explainability endpoints (reasoning traces, not verdicts)."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from backend.db.session import get_db
from backend.schemas.explainability import ExplanationResponse, ExplanationTargetType
from backend.services import explainability as explain_service
from backend.security.authorization import require, require_target
from backend.services.authorization import Principal


router = APIRouter(prefix="/explanations")


def _to_response(content: dict) -> ExplanationResponse:
    target = content["target"]
    return ExplanationResponse(
        explanation_id=UUID(content["explanation_id"]) if content.get("explanation_id") else None,
        materialized=bool(content.get("materialized", False)),
        fusion_run_id=UUID(content["fusion_run_id"]),
        target_type=ExplanationTargetType(target["target_type"]),
        target_id=UUID(target["target_id"]),
        integrity_assessment=content["integrity_assessment"],
        review_priority=content["review_priority"],
        methodology=content["methodology"],
        configuration=content["configuration"],
        summary=content["summary"],
        signals=content["signals"],
        rules=content["rules"],
        priority_trace=content.get("priority_trace", {}),
        unknowns=content.get("unknowns", []),
        provenance=content.get("provenance", {}),
        generated_at=content.get("generated_at"),
    )


@router.post(
    "/fusion/{fusion_run_id}",
    status_code=status.HTTP_201_CREATED,
    summary="Materialize the explanation for a fusion run (idempotent per run)",
)
def materialize_explanation(
    fusion_run_id: UUID,
    response: Response,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("fusion.read", "fusion_run", "fusion_run_id")),
) -> ExplanationResponse:
    try:
        content, created = explain_service.materialize_explanation(db, str(fusion_run_id))
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    if not created:
        response.status_code = status.HTTP_200_OK
    return _to_response(content)


@router.get(
    "/fusion/{fusion_run_id}",
    summary="Generate the explanation for a fusion run (read-only)",
)
def get_fusion_explanation(
    fusion_run_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("fusion.read", "fusion_run", "fusion_run_id")),
) -> ExplanationResponse:
    try:
        content = explain_service.build_explanation(db, str(fusion_run_id))
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return _to_response(content)


@router.get(
    "/{target_type}/{target_id}",
    summary="Explain a target's latest fusion assessment",
)
def get_target_explanation(
    target_type: ExplanationTargetType,
    target_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_target("fusion.read")),
) -> ExplanationResponse:
    try:
        content = explain_service.latest_for_target(db, target_type.value, str(target_id))
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return _to_response(content)
