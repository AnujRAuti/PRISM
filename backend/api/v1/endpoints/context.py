from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from geoalchemy2 import Geography
from sqlalchemy import cast, func
from sqlalchemy.orm import Session

from backend.db.models import Activity, Claim, Evidence, Project, User
from backend.db.session import get_db
from backend.schemas.context import (
    ActivityCreate,
    ActivityListResponse,
    ActivityResponse,
    ClaimCreate,
    ClaimListResponse,
    ClaimResponse,
    ClaimUpdate,
    EvidenceContextResponse,
    EvidenceContextUpdate,
    LocationResponse,
    LocationUpdate,
    NearbyEvidenceItem,
    NearbyEvidenceResponse,
    ProjectCreate,
    ProjectListResponse,
    ProjectResponse,
    ProjectUpdate,
)


router = APIRouter()


def _require_project(project_id: UUID, db: Session) -> Project:
    project = db.query(Project).filter(Project.id == str(project_id)).one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _require_user(user_id: UUID | None, db: Session, label: str) -> None:
    if user_id is not None and db.query(User).filter(User.id == str(user_id)).one_or_none() is None:
        raise HTTPException(status_code=404, detail=f"{label} not found")


@router.post("/projects", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(request: ProjectCreate, db: Session = Depends(get_db)) -> Project:
    _require_user(request.owner_id, db, "Owner")
    project = Project(name=request.name, owner_id=str(request.owner_id))
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("/projects", response_model=ProjectListResponse)
def list_projects(
    owner_id: UUID | None = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> ProjectListResponse:
    query = db.query(Project)
    if owner_id is not None:
        query = query.filter(Project.owner_id == str(owner_id))
    total = query.count()
    return ProjectListResponse(items=query.offset(offset).limit(limit).all(), limit=limit, offset=offset, total=total)


@router.get("/projects/{project_id}", response_model=ProjectResponse)
def get_project(project_id: UUID, db: Session = Depends(get_db)) -> Project:
    return _require_project(project_id, db)


@router.patch("/projects/{project_id}", response_model=ProjectResponse)
def update_project(project_id: UUID, request: ProjectUpdate, db: Session = Depends(get_db)) -> Project:
    project = _require_project(project_id, db)
    project.name = request.name
    db.commit()
    db.refresh(project)
    return project


@router.post("/projects/{project_id}/activities", response_model=ActivityResponse, status_code=status.HTTP_201_CREATED)
def create_activity(project_id: UUID, request: ActivityCreate, db: Session = Depends(get_db)) -> Activity:
    _require_project(project_id, db)
    _require_user(request.actor_id, db, "Actor")
    activity = Activity(project_id=str(project_id), actor_id=str(request.actor_id) if request.actor_id else None, verb=request.verb, details=request.details)
    db.add(activity)
    db.commit()
    db.refresh(activity)
    return activity


@router.get("/projects/{project_id}/activities", response_model=ActivityListResponse)
def list_activities(project_id: UUID, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), db: Session = Depends(get_db)) -> ActivityListResponse:
    _require_project(project_id, db)
    query = db.query(Activity).filter(Activity.project_id == str(project_id)).order_by(Activity.created_at.desc())
    return ActivityListResponse(items=query.offset(offset).limit(limit).all(), limit=limit, offset=offset, total=query.count())


@router.get("/projects/{project_id}/activities/{activity_id}", response_model=ActivityResponse)
def get_activity(project_id: UUID, activity_id: UUID, db: Session = Depends(get_db)) -> Activity:
    _require_project(project_id, db)
    activity = db.query(Activity).filter(Activity.id == str(activity_id), Activity.project_id == str(project_id)).one_or_none()
    if activity is None:
        raise HTTPException(status_code=404, detail="Activity not found")
    return activity


@router.post("/projects/{project_id}/claims", response_model=ClaimResponse, status_code=status.HTTP_201_CREATED)
def create_claim(project_id: UUID, request: ClaimCreate, db: Session = Depends(get_db)) -> Claim:
    _require_project(project_id, db)
    _require_user(request.claimant_id, db, "Claimant")
    if request.temporal_start_at is not None and request.temporal_end_at is not None:
        if request.temporal_start_at > request.temporal_end_at:
            raise HTTPException(status_code=422, detail="temporal_start_at must be <= temporal_end_at")
    claim = Claim(project_id=str(project_id), claimant_id=str(request.claimant_id) if request.claimant_id else None, title=request.title, description=request.description, temporal_start_at=request.temporal_start_at, temporal_end_at=request.temporal_end_at)
    db.add(claim)
    db.commit()
    db.refresh(claim)
    return claim


@router.get("/projects/{project_id}/claims", response_model=ClaimListResponse)
def list_claims(project_id: UUID, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), db: Session = Depends(get_db)) -> ClaimListResponse:
    _require_project(project_id, db)
    query = db.query(Claim).filter(Claim.project_id == str(project_id)).order_by(Claim.created_at.desc())
    return ClaimListResponse(items=query.offset(offset).limit(limit).all(), limit=limit, offset=offset, total=query.count())


@router.get("/projects/{project_id}/claims/{claim_id}", response_model=ClaimResponse)
def get_claim(project_id: UUID, claim_id: UUID, db: Session = Depends(get_db)) -> Claim:
    _require_project(project_id, db)
    claim = db.query(Claim).filter(Claim.id == str(claim_id), Claim.project_id == str(project_id)).one_or_none()
    if claim is None:
        raise HTTPException(status_code=404, detail="Claim not found")
    return claim


@router.patch("/projects/{project_id}/claims/{claim_id}", response_model=ClaimResponse)
def update_claim(project_id: UUID, claim_id: UUID, request: ClaimUpdate, db: Session = Depends(get_db)) -> Claim:
    claim = get_claim(project_id, claim_id, db)
    if not request.model_fields_set:
        raise HTTPException(status_code=422, detail="At least one claim field is required")
    if "title" in request.model_fields_set:
        claim.title = request.title
    if "description" in request.model_fields_set:
        claim.description = request.description
    if "temporal_start_at" in request.model_fields_set:
        claim.temporal_start_at = request.temporal_start_at
    if "temporal_end_at" in request.model_fields_set:
        claim.temporal_end_at = request.temporal_end_at
    if claim.temporal_start_at is not None and claim.temporal_end_at is not None:
        if claim.temporal_start_at > claim.temporal_end_at:
            raise HTTPException(status_code=422, detail="temporal_start_at must be <= temporal_end_at")
    db.commit()
    db.refresh(claim)
    return claim


@router.patch("/evidence/{evidence_id}/context", response_model=EvidenceContextResponse)
def update_evidence_context(evidence_id: UUID, request: EvidenceContextUpdate, db: Session = Depends(get_db)) -> EvidenceContextResponse:
    evidence = db.query(Evidence).filter(Evidence.id == str(evidence_id)).one_or_none()
    if evidence is None:
        raise HTTPException(status_code=404, detail="Evidence not found")
    _require_project(request.project_id, db)
    if request.claim_id is not None:
        claim = db.query(Claim).filter(Claim.id == str(request.claim_id)).one_or_none()
        if claim is None:
            raise HTTPException(status_code=404, detail="Claim not found")
        if str(claim.project_id) != str(request.project_id):
            raise HTTPException(status_code=409, detail="Claim belongs to a different project")
    evidence.project_id = str(request.project_id)
    evidence.claim_id = str(request.claim_id) if request.claim_id else None
    db.commit()
    return EvidenceContextResponse(evidence_id=evidence_id, project_id=request.project_id, claim_id=request.claim_id)


@router.patch("/evidence/{evidence_id}/location", response_model=LocationResponse)
def update_evidence_location(evidence_id: UUID, request: LocationUpdate, db: Session = Depends(get_db)) -> LocationResponse:
    evidence = db.query(Evidence).filter(Evidence.id == str(evidence_id)).one_or_none()
    if evidence is None:
        raise HTTPException(status_code=404, detail="Evidence not found")
    evidence.location = func.ST_SetSRID(func.ST_MakePoint(request.longitude, request.latitude), 4326)
    db.commit()
    return LocationResponse(evidence_id=evidence_id, location={"latitude": request.latitude, "longitude": request.longitude})


def _nearby_query(db: Session, latitude: float, longitude: float, radius: float, project_id: UUID | None, limit: int, offset: int):
    point = func.ST_SetSRID(func.ST_MakePoint(longitude, latitude), 4326)
    point_geography = cast(point, Geography)
    location_geography = cast(Evidence.location, Geography)
    query = db.query(
        Evidence.id.label("evidence_id"), Evidence.project_id, Evidence.claim_id,
        func.ST_Y(Evidence.location).label("latitude"), func.ST_X(Evidence.location).label("longitude"),
        func.ST_Distance(location_geography, point_geography).label("distance_meters"),
    ).filter(Evidence.location.is_not(None), func.ST_DWithin(location_geography, point_geography, radius))
    if project_id is not None:
        query = query.filter(Evidence.project_id == str(project_id))
    return query.order_by("distance_meters"), query


def _nearby_response(query_pair: tuple[Any, Any], limit: int, offset: int) -> NearbyEvidenceResponse:
    query, total_query = query_pair
    rows = query.offset(offset).limit(limit).all()
    return NearbyEvidenceResponse(items=[NearbyEvidenceItem(**row._mapping) for row in rows], limit=limit, offset=offset, total=total_query.count())


@router.get("/evidence/nearby", response_model=NearbyEvidenceResponse)
def nearby_evidence(latitude: float = Query(..., ge=-90, le=90), longitude: float = Query(..., ge=-180, le=180), radius: float = Query(..., gt=0, le=100000), limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), db: Session = Depends(get_db)) -> NearbyEvidenceResponse:
    return _nearby_response(_nearby_query(db, latitude, longitude, radius, None, limit, offset), limit, offset)


@router.get("/projects/{project_id}/evidence/nearby", response_model=NearbyEvidenceResponse)
def project_nearby_evidence(project_id: UUID, latitude: float = Query(..., ge=-90, le=90), longitude: float = Query(..., ge=-180, le=180), radius: float = Query(..., gt=0, le=100000), limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), db: Session = Depends(get_db)) -> NearbyEvidenceResponse:
    _require_project(project_id, db)
    return _nearby_response(_nearby_query(db, latitude, longitude, radius, project_id, limit, offset), limit, offset)