"""BE-019 integration repository: DB access for external systems, credentials, references,
assertions, idempotency keys, webhooks, integration events."""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from backend.db.models import (
    ApiClient,
    ApiCredential,
    ExternalAssertion,
    ExternalReference,
    ExternalSystem,
    IdempotencyKey,
    IntegrationEvent,
    WebhookDelivery,
    WebhookEvent,
    WebhookSubscription,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# External Systems
# ---------------------------------------------------------------------------


def get_external_system(db: Session, system_id: str) -> ExternalSystem | None:
    return db.query(ExternalSystem).filter(ExternalSystem.id == system_id).one_or_none()


def get_external_system_by_code(db: Session, code: str) -> ExternalSystem | None:
    return db.query(ExternalSystem).filter(ExternalSystem.code == code).one_or_none()


def list_external_systems(
    db: Session,
    organization_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[ExternalSystem]:
    q = db.query(ExternalSystem)
    if organization_id:
        q = q.filter(ExternalSystem.organization_id == organization_id)
    if status:
        q = q.filter(ExternalSystem.status == status)
    return q.order_by(ExternalSystem.created_at.desc()).offset(offset).limit(limit).all()


def insert_external_system(db: Session, **kwargs: Any) -> ExternalSystem:
    system = ExternalSystem(**kwargs)
    db.add(system)
    db.flush()
    return system


# ---------------------------------------------------------------------------
# API Clients
# ---------------------------------------------------------------------------


def get_api_client(db: Session, client_id: str) -> ApiClient | None:
    return db.query(ApiClient).filter(ApiClient.id == client_id).one_or_none()


def list_api_clients(
    db: Session,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[ApiClient]:
    q = db.query(ApiClient)
    if status:
        q = q.filter(ApiClient.status == status)
    return q.order_by(ApiClient.created_at.desc()).offset(offset).limit(limit).all()


def insert_api_client(db: Session, **kwargs: Any) -> ApiClient:
    client = ApiClient(**kwargs)
    db.add(client)
    db.flush()
    return client


# ---------------------------------------------------------------------------
# API Credentials
# ---------------------------------------------------------------------------


def insert_credential(db: Session, **kwargs: Any) -> ApiCredential:
    cred = ApiCredential(**kwargs)
    db.add(cred)
    db.flush()
    return cred


def get_credential(db: Session, credential_id: str) -> ApiCredential | None:
    return db.query(ApiCredential).filter(ApiCredential.id == credential_id).one_or_none()


def list_active_credentials(db: Session, client_id: str) -> list[ApiCredential]:
    """Return non-revoked, non-expired credentials for a client."""
    now = utc_now()
    return (
        db.query(ApiCredential)
        .filter(
            ApiCredential.client_id == client_id,
            ApiCredential.revoked_at.is_(None),
            (ApiCredential.expires_at.is_(None)) | (ApiCredential.expires_at > now),
        )
        .all()
    )


def revoke_credential(db: Session, credential_id: str) -> ApiCredential | None:
    cred = db.query(ApiCredential).filter(ApiCredential.id == credential_id).one_or_none()
    if cred and cred.revoked_at is None:
        cred.revoked_at = utc_now()
        db.flush()
    return cred


def touch_credential_used(db: Session, credential_id: str) -> None:
    cred = db.query(ApiCredential).filter(ApiCredential.id == credential_id).one_or_none()
    if cred:
        cred.last_used_at = utc_now()
        db.flush()


# ---------------------------------------------------------------------------
# External References
# ---------------------------------------------------------------------------


def get_external_reference(
    db: Session, external_system_id: str, resource_type: str, external_id: str
) -> ExternalReference | None:
    return (
        db.query(ExternalReference)
        .filter(
            ExternalReference.external_system_id == external_system_id,
            ExternalReference.resource_type == resource_type,
            ExternalReference.external_id == external_id,
        )
        .one_or_none()
    )


def list_external_references(
    db: Session,
    external_system_id: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[ExternalReference]:
    q = db.query(ExternalReference)
    if external_system_id:
        q = q.filter(ExternalReference.external_system_id == external_system_id)
    if resource_type:
        q = q.filter(ExternalReference.resource_type == resource_type)
    if resource_id:
        q = q.filter(ExternalReference.resource_id == resource_id)
    return q.order_by(ExternalReference.first_seen_at.desc()).offset(offset).limit(limit).all()


def upsert_external_reference(
    db: Session,
    external_system_id: str,
    resource_type: str,
    resource_id: str,
    external_id: str,
    external_version: str | None = None,
) -> ExternalReference:
    existing = get_external_reference(db, external_system_id, resource_type, external_id)
    if existing:
        existing.last_seen_at = utc_now()
        if external_version:
            existing.external_version = external_version
        db.flush()
        return existing
    ref = ExternalReference(
        external_system_id=external_system_id,
        resource_type=resource_type,
        resource_id=resource_id,
        external_id=external_id,
        external_version=external_version,
    )
    db.add(ref)
    db.flush()
    return ref


# ---------------------------------------------------------------------------
# External Assertions
# ---------------------------------------------------------------------------


def insert_external_assertion(db: Session, **kwargs: Any) -> ExternalAssertion:
    assertion = ExternalAssertion(**kwargs)
    db.add(assertion)
    db.flush()
    return assertion


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def get_idempotency_key(
    db: Session, client_id: str, key: str
) -> IdempotencyKey | None:
    return (
        db.query(IdempotencyKey)
        .filter(
            IdempotencyKey.client_id == client_id,
            IdempotencyKey.idempotency_key == key,
        )
        .one_or_none()
    )


def insert_idempotency_key(
    db: Session,
    client_id: str,
    key: str,
    request_hash: str,
    result_payload: dict | None = None,
    expires_at: datetime | None = None,
) -> IdempotencyKey:
    record = IdempotencyKey(
        client_id=client_id,
        idempotency_key=key,
        request_hash=request_hash,
        result_payload=result_payload,
        expires_at=expires_at,
    )
    db.add(record)
    db.flush()
    return record


def update_idempotency_result(
    db: Session, record: IdempotencyKey, result_payload: dict
) -> None:
    record.result_payload = result_payload
    db.flush()


# ---------------------------------------------------------------------------
# Webhook Subscriptions
# ---------------------------------------------------------------------------


def get_webhook_subscription(db: Session, subscription_id: str) -> WebhookSubscription | None:
    return (
        db.query(WebhookSubscription)
        .filter(WebhookSubscription.id == subscription_id)
        .one_or_none()
    )


def list_webhook_subscriptions(
    db: Session,
    external_system_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[WebhookSubscription]:
    q = db.query(WebhookSubscription)
    if external_system_id:
        q = q.filter(WebhookSubscription.external_system_id == external_system_id)
    if status:
        q = q.filter(WebhookSubscription.status == status)
    return q.order_by(WebhookSubscription.created_at.desc()).offset(offset).limit(limit).all()


def active_subscriptions_for_event(
    db: Session, event_type: str
) -> list[WebhookSubscription]:
    """Return all ACTIVE subscriptions that have subscribed to the given event_type."""
    return (
        db.query(WebhookSubscription)
        .filter(
            WebhookSubscription.status == "ACTIVE",
            WebhookSubscription.subscribed_events.contains([event_type]),
        )
        .all()
    )


def insert_webhook_subscription(db: Session, **kwargs: Any) -> WebhookSubscription:
    sub = WebhookSubscription(**kwargs)
    db.add(sub)
    db.flush()
    return sub


def update_webhook_subscription(
    db: Session, subscription: WebhookSubscription, **kwargs: Any
) -> WebhookSubscription:
    for k, v in kwargs.items():
        setattr(subscription, k, v)
    db.flush()
    return subscription


# ---------------------------------------------------------------------------
# Webhook Events
# ---------------------------------------------------------------------------


def insert_webhook_event(db: Session, **kwargs: Any) -> WebhookEvent:
    event = WebhookEvent(**kwargs)
    db.add(event)
    db.flush()
    return event


def fetch_pending_webhook_events(db: Session, limit: int = 50) -> list[WebhookEvent]:
    return (
        db.query(WebhookEvent)
        .filter(WebhookEvent.status == "PENDING")
        .order_by(WebhookEvent.created_at)
        .limit(limit)
        .all()
    )


def update_webhook_event_status(
    db: Session, event: WebhookEvent, status: str
) -> None:
    event.status = status
    if status in ("PUBLISHED", "FAILED"):
        event.processed_at = utc_now()
    db.flush()


def list_webhook_events(
    db: Session,
    event_type: str | None = None,
    project_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[WebhookEvent]:
    q = db.query(WebhookEvent)
    if event_type:
        q = q.filter(WebhookEvent.event_type == event_type)
    if project_id:
        q = q.filter(WebhookEvent.project_id == project_id)
    if status:
        q = q.filter(WebhookEvent.status == status)
    return q.order_by(WebhookEvent.created_at.desc()).offset(offset).limit(limit).all()


# ---------------------------------------------------------------------------
# Webhook Deliveries
# ---------------------------------------------------------------------------


def insert_webhook_delivery(db: Session, **kwargs: Any) -> WebhookDelivery:
    delivery = WebhookDelivery(**kwargs)
    db.add(delivery)
    db.flush()
    return delivery


def get_webhook_delivery(db: Session, delivery_id: str) -> WebhookDelivery | None:
    return db.query(WebhookDelivery).filter(WebhookDelivery.id == delivery_id).one_or_none()


def fetch_retrying_webhook_deliveries(db: Session, limit: int = 50) -> list[WebhookDelivery]:
    now = utc_now()
    return (
        db.query(WebhookDelivery)
        .filter(
            WebhookDelivery.status == "RETRYING",
            WebhookDelivery.next_attempt_at <= now,
        )
        .order_by(WebhookDelivery.next_attempt_at)
        .limit(limit)
        .all()
    )


def update_webhook_delivery(
    db: Session, delivery: WebhookDelivery, **kwargs: Any
) -> WebhookDelivery:
    for k, v in kwargs.items():
        setattr(delivery, k, v)
    db.flush()
    return delivery


# ---------------------------------------------------------------------------
# Integration Events
# ---------------------------------------------------------------------------


def insert_integration_event(db: Session, **kwargs: Any) -> IntegrationEvent:
    event = IntegrationEvent(**kwargs)
    db.add(event)
    db.flush()
    return event


def list_integration_events(
    db: Session,
    event_type: str | None = None,
    aggregate_type: str | None = None,
    project_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[IntegrationEvent]:
    q = db.query(IntegrationEvent)
    if event_type:
        q = q.filter(IntegrationEvent.event_type == event_type)
    if aggregate_type:
        q = q.filter(IntegrationEvent.aggregate_type == aggregate_type)
    if project_id:
        q = q.filter(IntegrationEvent.project_id == project_id)
    if status:
        q = q.filter(IntegrationEvent.status == status)
    return q.order_by(IntegrationEvent.created_at.desc()).offset(offset).limit(limit).all()

