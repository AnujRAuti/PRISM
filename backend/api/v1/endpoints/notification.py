"""BE-018 notification endpoints: in-app inbox, read state, preferences, and delivery inspection."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from backend.db.models import NOTIFICATION_TYPES
from backend.db.session import get_db
from backend.repositories import notification as notif_repo
from backend.schemas.notification import (
    MarkReadResponse,
    NotificationDeliveryListResponse,
    NotificationDeliveryResponse,
    NotificationListResponse,
    NotificationPreferenceBulkUpdate,
    NotificationPreferenceItem,
    NotificationPreferencesResponse,
    NotificationResponse,
    ReadAllResponse,
    UnreadCountResponse,
)
from backend.security.authentication import is_development_bypass
from backend.security.authorization import require
from backend.services import audit_ledger as audit_service
from backend.services.authorization import Principal


router = APIRouter(prefix="/notifications", tags=["notifications"])


def _user_id(principal: Principal) -> str:
    if not principal.authenticated or not principal.principal_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return str(principal.principal_id)


# ---------------------------------------------------------------------------
# Notifications Inbox & Detail
# ---------------------------------------------------------------------------


@router.get("", response_model=NotificationListResponse)
def list_my_notifications(
    unread_only: bool = False,
    notification_type: str | None = None,
    project_id: str | None = None,
    from_date: datetime | None = None,
    to_date: datetime | None = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("notification.read")),
):
    """List paginated in-app notifications for the authenticated user."""
    uid = _user_id(principal)
    items, total = notif_repo.list_notifications(
        db,
        recipient_id=uid,
        unread_only=unread_only,
        notification_type=notification_type,
        project_id=project_id,
        from_date=from_date,
        to_date=to_date,
        limit=limit,
        offset=offset,
    )
    unread = notif_repo.count_unread(db, uid)
    return NotificationListResponse(
        items=[NotificationResponse.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        unread_count=unread,
    )


@router.get("/unread-count", response_model=UnreadCountResponse)
def get_unread_count(
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("notification.read")),
):
    """Fast indexed count of unread notifications for the caller."""
    uid = _user_id(principal)
    count = notif_repo.count_unread(db, uid)
    return UnreadCountResponse(unread_count=count)


@router.get("/preferences", response_model=NotificationPreferencesResponse)
def get_preferences(
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("notification.manage_preferences")),
):
    """Get caller's channel preferences across all supported notification types."""
    uid = _user_id(principal)
    existing = {p.notification_type: p for p in notif_repo.get_user_preferences(db, uid)}
    items: list[NotificationPreferenceItem] = []
    for ntype in NOTIFICATION_TYPES:
        pref = existing.get(ntype)
        if pref:
            items.append(
                NotificationPreferenceItem(
                    notification_type=ntype,
                    in_app_enabled=pref.in_app_enabled,
                    email_enabled=pref.email_enabled,
                    updated_at=pref.updated_at,
                )
            )
        else:
            items.append(
                NotificationPreferenceItem(
                    notification_type=ntype,
                    in_app_enabled=True,
                    email_enabled=True,
                    updated_at=None,
                )
            )
    return NotificationPreferencesResponse(preferences=items)


@router.patch("/preferences", response_model=NotificationPreferencesResponse)
def update_preferences(
    payload: NotificationPreferenceBulkUpdate,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("notification.manage_preferences")),
):
    """Update caller's channel preferences for specified notification types."""
    uid = _user_id(principal)
    for ntype, update in payload.preferences.items():
        if ntype not in NOTIFICATION_TYPES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unknown notification type: {ntype!r}",
            )
        notif_repo.upsert_user_preference(
            db,
            user_id=uid,
            notification_type=ntype,
            in_app_enabled=update.in_app_enabled,
            email_enabled=update.email_enabled,
        )

    audit_service.append_event(
        db,
        event_type="NOTIFICATION_PREFERENCE_CHANGED",
        action="update_preferences",
        resource_type="notification_preferences",
        resource_id=uid,
        actor_id=uid,
        payload={"updated_types": list(payload.preferences.keys())},
        source="notification_api",
    )
    db.commit()

    return get_preferences(db, principal)


@router.get("/{id}", response_model=NotificationResponse)
def get_notification(
    id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("notification.read")),
):
    """Get single notification detail. Only recipient or administrator may access."""
    uid = _user_id(principal)
    item = notif_repo.get_notification(db, id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")

    is_admin = "notification.admin" in principal.permissions or is_development_bypass(principal)
    if str(item.recipient_id) != uid and not is_admin:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")

    return NotificationResponse.model_validate(item)


@router.post("/{id}/read", response_model=MarkReadResponse)
def mark_notification_as_read(
    id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("notification.mark_read")),
):
    """Mark a notification as read. Only recipient may modify read state."""
    uid = _user_id(principal)
    item = notif_repo.get_notification(db, id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")

    if str(item.recipient_id) != uid and not is_development_bypass(principal):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")

    updated = notif_repo.mark_notification_read(db, id)
    db.commit()
    db.refresh(updated)
    return MarkReadResponse(
        notification_id=updated.id,
        status=updated.status,
        read_at=updated.read_at,
    )


@router.post("/read-all", response_model=ReadAllResponse)
def mark_all_as_read(
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("notification.mark_read")),
):
    """Mark all unread notifications for caller as read."""
    uid = _user_id(principal)
    count = notif_repo.mark_all_notifications_read(db, uid)
    db.commit()
    return ReadAllResponse(marked_read_count=count)


@router.get("/{id}/deliveries", response_model=NotificationDeliveryListResponse)
def list_notification_deliveries(
    id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("notification.admin")),
):
    """Administrative inspection of channel deliveries for a notification."""
    deliveries = notif_repo.list_deliveries_for_notification(db, id)
    return NotificationDeliveryListResponse(
        items=[NotificationDeliveryResponse.model_validate(d) for d in deliveries]
    )

