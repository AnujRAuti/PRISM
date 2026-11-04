"""BE-011 Fusion Engine endpoints (assessments, not verdicts)."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.db.session import get_db
from backend.schemas.fusion import (
    AssessmentStatus,
    AssessmentValue,
    FusionConfigurationCreate,
    FusionConfigurationItem,
    FusionExecuteRequest,
    FusionExecuteResponse,
    FusionHistoryResponse,
    FusionLatestResponse,
    FusionRunDetailResponse,
    FusionRunItem,
    FusionRunStatus,
    FusionSignalItem,
    FusionTargetType,
    IntegrityAssessmentItem,
    ReviewPriorityItem,
    ReviewPriorityLevel,
)
from backend.services import fusion as fusion_service
from backend.security.authorization import require, require_target
from backend.services.authorization import Principal


router = APIRouter(prefix="/fusion")


def _dt(value) -> str | None:
    return value.isoformat() if value is not None else None


def _run_item(run) -> FusionRunItem:
    return FusionRunItem(
        id=UUID(run.id),
        target_type=FusionTargetType(run.target_type),
        target_id=UUID(run.target_id),
        status=FusionRunStatus(run.status),
        method=run.method,
        method_version=run.method_version,
        configuration_version=run.configuration_version,
        error=run.error,
        started_at=_dt(run.started_at),
        completed_at=_dt(run.completed_at),
    )


def _signal_items(signals) -> list[FusionSignalItem]:
    normalized = [
        item
        if isinstance(item, dict)
        else {
            "signal_type": item.signal_type,
            "state": item.state,
            "source": item.source,
            "source_entity_id": item.source_entity_id,
            "source_analysis_run_id": item.source_analysis_run_id,
            "raw_value": item.raw_value,
            "normalized_value": item.normalized_value,
            "weight": item.weight,
            "method": item.method,
            "method_version": item.method_version,
            "details": item.details,
        }
        for item in signals
    ]
    return [
        FusionSignalItem(
            signal_type=item["signal_type"],
            state=item["state"],
            source=item["source"],
            source_entity_id=UUID(item["source_entity_id"])
            if item["source_entity_id"]
            else None,
            source_analysis_run_id=UUID(item["source_analysis_run_id"])
            if item["source_analysis_run_id"]
            else None,
            raw_value=item.get("raw_value"),
            normalized_value=item.get("normalized_value"),
            weight=item.get("weight", 0.0),
            method=item["method"],
            method_version=item["method_version"],
            details=dict(item.get("details") or {}),
        )
        for item in normalized
    ]


def _assessment_item(assessment, run) -> IntegrityAssessmentItem:
    return IntegrityAssessmentItem(
        id=UUID(assessment.id),
        target_type=FusionTargetType(assessment.target_type),
        target_id=UUID(assessment.target_id),
        assessment_status=AssessmentStatus(assessment.assessment_status),
        assessment_value=AssessmentValue(assessment.assessment_value),
        integrity_score=assessment.integrity_score,
        signal_summary=dict(assessment.signal_summary or {}),
        method_version=run.method_version,
        configuration_version=run.configuration_version,
    )


def _priority_item(priority, run) -> ReviewPriorityItem:
    return ReviewPriorityItem(
        id=UUID(priority.id),
        target_type=FusionTargetType(priority.target_type),
        target_id=UUID(priority.target_id),
        priority=ReviewPriorityLevel(priority.priority),
        priority_score=priority.priority_score,
        signal_summary=dict(priority.signal_summary or {}),
        method_version=run.method_version,
        configuration_version=run.configuration_version,
    )


@router.post(
    "/{target_type}/{target_id}",
    response_model=FusionExecuteResponse,
    summary="Execute fusion for a claim or evidence target (append-only run)",
)
def execute_fusion(
    target_type: FusionTargetType,
    target_id: UUID,
    request: FusionExecuteRequest | None = None,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_target("fusion.execute")),
) -> FusionExecuteResponse:
    try:
        run, assessment, priority, signals = fusion_service.run_fusion(
            db,
            target_type.value,
            str(target_id),
            configuration_version=(request.configuration_version if request else None),
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return FusionExecuteResponse(
        run=_run_item(run),
        assessment=_assessment_item(assessment, run),
        priority=_priority_item(priority, run),
        signals=_signal_items(signals),
    )


@router.get(
    "/runs/{run_id}",
    response_model=FusionRunDetailResponse,
    summary="Retrieve one fusion execution with its signals and outputs",
)
def get_fusion_run(
    run_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("fusion.read", "fusion_run", "run_id")),
) -> FusionRunDetailResponse:
    try:
        run, signals, assessment, priority = fusion_service.get_run_detail(db, str(run_id))
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return FusionRunDetailResponse(
        run=_run_item(run),
        assessment=_assessment_item(assessment, run) if assessment else None,
        priority=_priority_item(priority, run) if priority else None,
        signals=_signal_items(signals),
    )


@router.get(
    "/{target_type}/{target_id}",
    response_model=FusionLatestResponse,
    summary="Latest fusion assessment and review priority for a target",
)
def get_latest_fusion(
    target_type: FusionTargetType,
    target_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_target("fusion.read")),
) -> FusionLatestResponse:
    try:
        run, assessment, priority = fusion_service.get_latest(db, target_type.value, str(target_id))
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if run is None or assessment is None or priority is None:
        raise HTTPException(status_code=404, detail="No fusion assessment found for this target")
    signals = fusion_service.fusion_repo.signals_for_run(db, run.id)
    return FusionLatestResponse(
        run=_run_item(run),
        assessment=_assessment_item(assessment, run),
        priority=_priority_item(priority, run),
        signals=_signal_items(signals),
    )


@router.get(
    "/{target_type}/{target_id}/history",
    response_model=FusionHistoryResponse,
    summary="Paginated fusion execution history for a target",
)
def get_fusion_history(
    target_type: FusionTargetType,
    target_id: UUID,
    status: FusionRunStatus | None = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_target("fusion.read")),
) -> FusionHistoryResponse:
    try:
        rows, total = fusion_service.run_history(
            db,
            target_type.value,
            str(target_id),
            status=status.value if status else None,
            limit=limit,
            offset=offset,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return FusionHistoryResponse(
        target_type=target_type,
        target_id=target_id,
        items=[_run_item(row) for row in rows],
        limit=limit,
        offset=offset,
        total=total,
    )


@router.post(
    "/configurations",
    response_model=FusionConfigurationItem,
    summary="Store a new versioned fusion configuration",
)
def create_configuration(
    request: FusionConfigurationCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("configuration.manage")),
) -> FusionConfigurationItem:
    try:
        row = fusion_service.create_configuration(
            db,
            version=request.version,
            name=request.name,
            weights=request.weights,
            thresholds=request.thresholds,
            priority=request.priority,
            signals=request.signals,
            method_version=request.method_version,
            enabled=request.enabled,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return FusionConfigurationItem.model_validate(row)
