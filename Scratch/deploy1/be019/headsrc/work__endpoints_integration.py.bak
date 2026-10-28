"""BE-019 External Integrations & API Client Platform endpoints."""

import json
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.db.models import ApiCredential, Claim, Project
from backend.db.session import get_db
from backend.repositories import integration as integration_repo
from backend.schemas.evidence import EvidenceUploadResponse
from backend.schemas.integration import (
    ApiClientCreate,
    ApiClientResponse,
    ApiCredentialResponse,
    ExternalClaimImport,
    ExternalReferenceCreate,
    ExternalReferenceResponse,
    ExternalSystemCreate,
    ExternalSystemResponse,
    IntegrationEventResponse,
    WebhookSubscriptionCreate,
    WebhookSubscriptionResponse,
    WebhookSubscriptionUpdate,
)
from backend.security.authentication import is_development_bypass
from backend.security.authorization import (
    enforce,
    require,
    visible_organization_ids,
    visible_project_ids,
)
from backend.services import audit_ledger as audit_service
from backend.services import integration as integration_service
from backend.services import webhook as webhook_service
from backend.services.authorization import Principal, Resource, resolve_resource_scope
from backend.services.evidence_ingestion import ingest_evidence
from backend.services.integration import (
    check_idempotency,
    compute_request_hash,
    record_idempotency,
)


router = APIRouter(prefix="/integrations", tags=["integrations"])


def _check_idempotency(
    db: Session,
    principal: Principal,
    idempotency_key: str | None,
    payload_data: Any,
) -> tuple[str | None, str | None, dict | None]:
    if not idempotency_key:
        return None, None, None
    client_id = principal.principal_id or "anonymous"
    req_hash = compute_request_hash(payload_data)
    result = check_idempotency(db, client_id, idempotency_key, req_hash)
    if result.outcome == "CONFLICT":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Idempotency key conflict: request payload differs from previous request with this key",
        )
    if result.outcome == "REPLAY":
        return idempotency_key, req_hash, result.result_payload
    return idempotency_key, req_hash, None


# ---------------------------------------------------------------------------
# External Systems
# ---------------------------------------------------------------------------


@router.get(
    "/systems",
    response_model=list[ExternalSystemResponse],
    summary="List registered external systems (requires integration.read)",
)
def list_systems(
    organization_id: UUID | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("integration.read")),
) -> list[ExternalSystemResponse]:
    """List external systems the caller's ``integration.read`` grant covers.

    Organization-level rows: a non-GLOBAL grant sees its own organizations (unit
    grants include the parent), and a project-scoped grant sees none. The
    caller-supplied ``organization_id`` can only narrow this set, never widen it.
    """
    systems = integration_repo.list_external_systems(
        db,
        organization_id=str(organization_id) if organization_id else None,
        status=status,
        limit=min(limit, 100),
        offset=offset,
        allowed_organization_ids=visible_organization_ids(db, principal, "integration.read"),
    )
    return [ExternalSystemResponse.model_validate(s) for s in systems]


@router.post(
    "/systems",
    response_model=ExternalSystemResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register an external system (requires integration.manage)",
)
def create_system(
    body: ExternalSystemCreate,
    request: Request,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("integration.manage")),
) -> ExternalSystemResponse:
    """Register an external system inside a scope the caller already holds.

    Naming an organization does not grant authority over it: ``integration.manage``
    must cover ``body.organization_id`` (an organization or unit grant, or GLOBAL).
    A system with no organization is platform-wide configuration, so it requires
    the GLOBAL grant — the bare resource resolves to nothing else.
    """
    if not is_development_bypass(principal):
        enforce(
            principal,
            "integration.manage",
            (
                resolve_resource_scope(db, "organization", str(body.organization_id))
                if body.organization_id
                else Resource("organization")
            ),
            request,
        )

    idem_key, req_hash, replay_data = _check_idempotency(
        db, principal, idempotency_key, body.model_dump(mode="json")
    )
    if replay_data is not None:
        return ExternalSystemResponse.model_validate(replay_data)

    existing = integration_repo.get_external_system_by_code(db, body.code)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"External system with code {body.code!r} already exists",
        )

    system = integration_service.create_external_system(
        db,
        name=body.name,
        code=body.code,
        system_type=body.system_type,
        actor_id=principal.principal_id,
        organization_id=str(body.organization_id) if body.organization_id else None,
        description=body.description,
        metadata=body.metadata,
    )
    db.commit()
    db.refresh(system)

    resp = ExternalSystemResponse.model_validate(system)
    if idem_key and req_hash:
        record_idempotency(db, principal.principal_id, idem_key, req_hash, resp.model_dump(mode="json"))
        db.commit()

    return resp


# ---------------------------------------------------------------------------
# API Clients
# ---------------------------------------------------------------------------


@router.get(
    "/clients",
    response_model=list[ApiClientResponse],
    summary="List API clients (requires integration.read)",
)
def list_clients(
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("integration.read")),
) -> list[ApiClientResponse]:
    """List API clients the caller's ``integration.read`` grant covers.

    Project-level rows: a non-GLOBAL grant sees the clients bound to its own
    projects (organization and unit grants expand to their projects). A client
    with no project acts platform-wide and stays GLOBAL-only.
    """
    clients = integration_repo.list_api_clients(
        db,
        status=status,
        limit=min(limit, 100),
        offset=offset,
        allowed_project_ids=visible_project_ids(db, principal, "integration.read"),
    )
    return [ApiClientResponse.model_validate(c) for c in clients]


class ApiClientCreateResponse(BaseModel_resp := ApiClientResponse):
    secret: str  # shown once on creation; never stored plaintext


@router.post(
    "/clients",
    response_model=ApiClientCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create API client with initial credential (requires api_client.manage)",
)
def create_client(
    body: ApiClientCreate,
    request: Request,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("api_client.manage")),
) -> Any:
    """Create an API client bound to a project the caller already manages.

    Naming a project does not grant authority over it: ``api_client.manage`` must
    cover ``body.project_id``. A client with no project is platform-wide, so it
    requires the GLOBAL grant — and the initial credential this route returns is
    then usable against every project.
    """
    if not is_development_bypass(principal):
        enforce(
            principal,
            "api_client.manage",
            (
                resolve_resource_scope(db, "project", str(body.project_id))
                if body.project_id
                else Resource("project")
            ),
            request,
        )

    idem_key, req_hash, replay_data = _check_idempotency(
        db, principal, idempotency_key, body.model_dump(mode="json")
    )
    if replay_data is not None:
        return replay_data

    client, plaintext_secret = integration_service.create_api_client(
        db,
        name=body.name,
        actor_id=principal.principal_id,
        project_id=str(body.project_id) if body.project_id else None,
        scopes=body.scopes,
    )
    db.commit()
    db.refresh(client)

    result = {
        "id": str(client.id),
        "name": client.name,
        "scopes": client.scopes or [],
        "project_id": str(client.project_id) if client.project_id else None,
        "status": client.status,
        "created_at": client.created_at.isoformat(),
        "updated_at": client.updated_at.isoformat(),
        "secret": plaintext_secret,
    }
    if idem_key and req_hash:
        record_idempotency(db, principal.principal_id, idem_key, req_hash, result)
        db.commit()

    return result


@router.get(
    "/clients/{client_id}",
    response_model=ApiClientResponse,
    summary="Get API client details (requires integration.read)",
)
def get_client(
    client_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("integration.read", "api_client", "client_id")),
) -> ApiClientResponse:
    client = integration_repo.get_api_client(db, str(client_id))
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API client not found")
    return ApiClientResponse.model_validate(client)


@router.post(
    "/clients/{client_id}/credentials",
    response_model=ApiCredentialResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Issue a new credential for an API client (requires credential.manage)",
)
def create_credential(
    client_id: UUID,
    expires_in_days: int | None = None,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("credential.manage", "api_client", "client_id")),
) -> ApiCredentialResponse:
    client = integration_repo.get_api_client(db, str(client_id))
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API client not found")

    cred, plaintext = integration_service.create_credential(
        db, str(client_id), actor_id=principal.principal_id, expires_in_days=expires_in_days
    )
    db.commit()
    db.refresh(cred)

    return ApiCredentialResponse(
        credential_id=cred.id,
        client_id=cred.client_id,
        secret=plaintext,
        expires_at=cred.expires_at,
        created_at=cred.created_at,
    )


@router.post(
    "/credentials/{credential_id}/revoke",
    summary="Revoke an API credential immediately (requires credential.manage)",
)
def revoke_credential_endpoint(
    credential_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("credential.manage")),
) -> dict[str, Any]:
    row = db.query(ApiCredential).filter(ApiCredential.id == str(credential_id)).one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Credential not found or already revoked",
        )
    if not is_development_bypass(principal):
        # A credential carries no scope column of its own: it inherits its
        # client's project, which is what the sibling issue route enforces.
        enforce(
            principal,
            "credential.manage",
            resolve_resource_scope(db, "api_client", str(row.client_id)),
            request,
        )

    success = integration_service.revoke_credential(
        db, str(credential_id), actor_id=principal.principal_id
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Credential not found or already revoked",
        )
    db.commit()
    return {"revoked": True, "credential_id": str(credential_id)}


# ---------------------------------------------------------------------------
# External References
# ---------------------------------------------------------------------------


@router.get(
    "/references",
    response_model=list[ExternalReferenceResponse],
    summary="Query external references (requires external_data.read)",
)
def list_references(
    external_system_id: UUID | None = None,
    resource_type: str | None = None,
    resource_id: UUID | None = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("external_data.read")),
) -> list[ExternalReferenceResponse]:
    """List external references the caller's ``external_data.read`` grant covers.

    References carry no scope column of their own, so ownership resolves through
    the NOT NULL ``external_system_id`` foreign key — the same derivation used for
    webhook subscriptions. A non-GLOBAL grant sees the references under its own
    organizations (unit grants include the parent); references under an
    organization-less, platform-wide system stay GLOBAL-only, so the join cannot
    leak them. The polymorphic ``resource_id`` has no foreign key and is still not
    validated against a project — that is the write-side mapping gap, not the read
    scope closed here.
    """
    refs = integration_repo.list_external_references(
        db,
        external_system_id=str(external_system_id) if external_system_id else None,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id else None,
        limit=min(limit, 100),
        offset=offset,
        allowed_organization_ids=visible_organization_ids(db, principal, "external_data.read"),
    )
    return [ExternalReferenceResponse.model_validate(r) for r in refs]


@router.post(
    "/references",
    response_model=ExternalReferenceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Map or update an external reference (requires external_data.write)",
)
def create_reference(
    body: ExternalReferenceCreate,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("external_data.write")),
) -> ExternalReferenceResponse:
    idem_key, req_hash, replay_data = _check_idempotency(
        db, principal, idempotency_key, body.model_dump(mode="json")
    )
    if replay_data is not None:
        return ExternalReferenceResponse.model_validate(replay_data)

    ref = integration_repo.upsert_external_reference(
        db,
        external_system_id=str(body.external_system_id),
        resource_type=body.resource_type,
        resource_id=str(body.resource_id),
        external_id=body.external_id,
        external_version=body.external_version,
    )
    audit_service.append_event(
        db,
        event_type="EXTERNAL_REFERENCE_CREATED",
        action="create",
        resource_type=body.resource_type,
        resource_id=str(body.resource_id),
        actor_id=principal.principal_id,
        project_id=None,
        payload={
            "external_system_id": str(body.external_system_id),
            "external_id": body.external_id,
            "resource_type": body.resource_type,
        },
        source="integration_service",
    )
    db.commit()
    db.refresh(ref)

    resp = ExternalReferenceResponse.model_validate(ref)
    if idem_key and req_hash:
        record_idempotency(db, principal.principal_id, idem_key, req_hash, resp.model_dump(mode="json"))
        db.commit()

    return resp


# ---------------------------------------------------------------------------
# External Evidence Ingestion (BE-003 reuse)
# ---------------------------------------------------------------------------


@router.post(
    "/evidence",
    response_model=EvidenceUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="External evidence ingestion preserving provenance (requires external_data.write)",
)
async def submit_external_evidence(
    file: UploadFile = File(...),
    external_system_id: UUID = Form(...),
    external_evidence_id: str | None = Form(None),
    project_id: UUID | None = Form(None),
    source_timestamp: str | None = Form(None),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("external_data.write")),
) -> EvidenceUploadResponse:
    ext_sys = integration_repo.get_external_system(db, str(external_system_id))
    if ext_sys is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="External system not found")
    if ext_sys.status != "ACTIVE":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="External system is not active"
        )

    declared_type = (file.content_type or "").lower().strip()
    data = await file.read(settings.max_upload_size + 1)

    parsed_time: datetime | None = None
    if source_timestamp:
        try:
            parsed_time = datetime.fromisoformat(source_timestamp)
            if parsed_time.tzinfo is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="source_timestamp must be timezone-aware",
                )
        except ValueError as err:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid source_timestamp: {err}",
            )

    evidence = ingest_evidence(data, file.filename or "unnamed", declared_type, db)
    if project_id:
        evidence.project_id = str(project_id)
        db.flush()

    # Record external assertion preserving provenance
    integration_repo.insert_external_assertion(
        db,
        external_system_id=str(external_system_id),
        resource_type="evidence",
        resource_id=str(evidence.id),
        external_id=external_evidence_id,
        source_timestamp=parsed_time,
        payload={
            "filename": file.filename,
            "declared_type": declared_type,
            "file_size": len(data),
        },
        api_client_id=principal.principal_id if principal.principal_type == "API_CLIENT" else None,
    )

    if external_evidence_id:
        integration_repo.upsert_external_reference(
            db,
            external_system_id=str(external_system_id),
            resource_type="evidence",
            resource_id=str(evidence.id),
            external_id=external_evidence_id,
        )

    db.commit()

    return EvidenceUploadResponse(
        evidence_id=evidence.id,
        status="uploaded",
        storage_key=evidence.storage_key,
        content_type=evidence.content_type,
        size=evidence.file_size,
    )


# ---------------------------------------------------------------------------
# External Claim Import
# ---------------------------------------------------------------------------


@router.post(
    "/claims",
    status_code=status.HTTP_201_CREATED,
    summary="Import external claim preserving provenance (requires external_data.write)",
)
def import_external_claim(
    body: ExternalClaimImport,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("external_data.write")),
) -> dict[str, Any]:
    idem_key, req_hash, replay_data = _check_idempotency(
        db, principal, idempotency_key, body.model_dump(mode="json")
    )
    if replay_data is not None:
        return replay_data

    ext_sys = integration_repo.get_external_system(db, str(body.external_system_id))
    if ext_sys is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="External system not found")
    if ext_sys.status != "ACTIVE":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="External system is not active"
        )

    # Check project scope
    project = db.query(Project).filter(Project.id == str(body.subject_id)).one_or_none()
    project_id = str(project.id) if project else None

    # Create Claim with source preserved
    claim = Claim(
        project_id=project_id,
        title=f"External Claim: {body.claim_type} ({body.external_reference})",
        description=json.dumps(body.assertion),
    )
    db.add(claim)
    db.flush()

    # Create external reference
    integration_repo.upsert_external_reference(
        db,
        external_system_id=str(body.external_system_id),
        resource_type="claim",
        resource_id=str(claim.id),
        external_id=body.external_reference,
    )

    # Create assertion preserving provenance
    assertion = integration_repo.insert_external_assertion(
        db,
        external_system_id=str(body.external_system_id),
        resource_type="claim",
        resource_id=str(claim.id),
        external_id=body.external_reference,
        source_timestamp=body.source_timestamp,
        payload=body.assertion,
        api_client_id=principal.principal_id if principal.principal_type == "API_CLIENT" else None,
    )

    audit_service.append_event(
        db,
        event_type="EXTERNAL_REFERENCE_CREATED",
        action="import_claim",
        resource_type="claim",
        resource_id=str(claim.id),
        actor_id=principal.principal_id,
        project_id=project_id,
        payload={
            "external_system_id": str(body.external_system_id),
            "external_reference": body.external_reference,
            "claim_type": body.claim_type,
        },
        source="integration_service",
    )

    db.commit()

    result = {
        "claim_id": str(claim.id),
        "external_system_id": str(body.external_system_id),
        "external_reference": body.external_reference,
        "source": "EXTERNAL",
        "imported_at": assertion.ingested_at.isoformat(),
    }
    if idem_key and req_hash:
        record_idempotency(db, principal.principal_id, idem_key, req_hash, result)
        db.commit()

    return result


# ---------------------------------------------------------------------------
# Webhooks
# ---------------------------------------------------------------------------


class WebhookSubscriptionCreateResponse(WebhookSubscriptionResponse):
    secret: str  # shown once on creation


@router.get(
    "/webhooks",
    response_model=list[WebhookSubscriptionResponse],
    summary="List webhook subscriptions (requires webhook.read)",
)
def list_webhooks(
    external_system_id: UUID | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("webhook.read")),
) -> list[WebhookSubscriptionResponse]:
    """List webhook subscriptions the caller's ``webhook.read`` grant covers.

    A subscription inherits its external system's organization, the same
    resolution the single-object ``PATCH /webhooks/{id}`` guard already uses, so
    the collection and the item agree. Systems with no organization are
    GLOBAL-only rows.
    """
    subs = integration_repo.list_webhook_subscriptions(
        db,
        external_system_id=str(external_system_id) if external_system_id else None,
        status=status,
        limit=min(limit, 100),
        offset=offset,
        allowed_organization_ids=visible_organization_ids(db, principal, "webhook.read"),
    )
    return [WebhookSubscriptionResponse.model_validate(s) for s in subs]


@router.post(
    "/webhooks",
    response_model=WebhookSubscriptionCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create webhook subscription with SSRF validation (requires webhook.manage)",
)
def create_webhook(
    body: WebhookSubscriptionCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("webhook.manage")),
) -> WebhookSubscriptionCreateResponse:
    # SSRF Protection
    try:
        webhook_service.validate_webhook_url(body.endpoint_url)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid webhook URL: {err}",
        )

    ext_sys = integration_repo.get_external_system(db, str(body.external_system_id))
    if ext_sys is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="External system not found")

    plaintext_secret = integration_service.generate_secret()
    secret_hash = integration_service.hash_secret(plaintext_secret)

    sub = integration_repo.insert_webhook_subscription(
        db,
        external_system_id=str(body.external_system_id),
        endpoint_url=body.endpoint_url,
        subscribed_events=body.subscribed_events,
        secret_hash=secret_hash,
        status="ACTIVE",
    )
    audit_service.append_event(
        db,
        event_type="WEBHOOK_CREATED",
        action="create",
        resource_type="webhook_subscription",
        resource_id=str(sub.id),
        actor_id=principal.principal_id,
        project_id=None,
        payload={
            "external_system_id": str(body.external_system_id),
            "endpoint_url": body.endpoint_url,
            "subscribed_events": body.subscribed_events,
        },
        source="webhook_service",
    )
    db.commit()
    db.refresh(sub)

    resp = WebhookSubscriptionResponse.model_validate(sub)
    return WebhookSubscriptionCreateResponse(
        **resp.model_dump(),
        secret=plaintext_secret,
    )


@router.patch(
    "/webhooks/{subscription_id}",
    response_model=WebhookSubscriptionResponse,
    summary="Update webhook subscription status/events (requires webhook.manage)",
)
def update_webhook(
    subscription_id: UUID,
    body: WebhookSubscriptionUpdate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(
        require("webhook.manage", "webhook_subscription", "subscription_id")
    ),
) -> WebhookSubscriptionResponse:
    sub = integration_repo.get_webhook_subscription(db, str(subscription_id))
    if sub is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Webhook subscription not found"
        )

    updates: dict[str, Any] = {}
    if body.status is not None:
        updates["status"] = body.status
    if body.subscribed_events is not None:
        updates["subscribed_events"] = body.subscribed_events

    updated_sub = integration_repo.update_webhook_subscription(db, sub, **updates)
    if body.status == "DISABLED":
        audit_service.append_event(
            db,
            event_type="WEBHOOK_DISABLED",
            action="disable",
            resource_type="webhook_subscription",
            resource_id=str(subscription_id),
            actor_id=principal.principal_id,
            project_id=None,
            payload={"reason": "user_action"},
            source="webhook_service",
        )
    db.commit()
    db.refresh(updated_sub)

    return WebhookSubscriptionResponse.model_validate(updated_sub)


# ---------------------------------------------------------------------------
# Integration Events
# ---------------------------------------------------------------------------


@router.get(
    "/events",
    response_model=list[IntegrationEventResponse],
    summary="Query durable integration events (requires integration.read)",
)
def list_events(
    event_type: str | None = None,
    aggregate_type: str | None = None,
    project_id: UUID | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("integration.read")),
) -> list[IntegrationEventResponse]:
    """GAP-SCHEMA: permission-gated only, with no row filter.

    ``IntegrationEvent.project_id`` is a nullable UUID with **no** foreign key to
    ``projects``, so nothing guarantees the value names a real project: filtering
    a caller's project set against it would authorize rows through an unvalidated
    column, and a ``NULL`` project would be invisible to every non-GLOBAL caller.
    The scope predicate waits on the FK/validity decision recorded in the scope
    classification.
    """
    events = integration_repo.list_integration_events(
        db,
        event_type=event_type,
        aggregate_type=aggregate_type,
        project_id=str(project_id) if project_id else None,
        status=status,
        limit=min(limit, 100),
        offset=offset,
    )
    return [IntegrationEventResponse.model_validate(e) for e in events]

