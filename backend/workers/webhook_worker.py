"""BE-019 webhook worker: sweeps pending webhook events and retries failed deliveries.

Never invoked synchronously from domain transactions. Runs as a periodic
background process or one-shot CLI.

Usage:
  python -m backend.workers.webhook_worker --sweep-events
  python -m backend.workers.webhook_worker --sweep-retries
  python -m backend.workers.webhook_worker --once
"""

import argparse
import json
import logging
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone

from backend.db.session import SessionLocal
from backend.repositories import integration as integration_repo
from backend.services import audit_ledger as audit_service
from backend.services.webhook import (
    build_webhook_payload,
    compute_next_webhook_attempt,
    is_retryable_status,
    sign_payload,
    utc_now,
    validate_webhook_url,
    MAX_DELIVERY_ATTEMPTS,
)


logger = logging.getLogger(__name__)

MAX_CONSECUTIVE_FAILURES_BEFORE_DISABLE = 10


def sweep_webhook_events(db, limit: int = 50) -> int:
    """Process PENDING webhook events: fan out deliveries to matching subscriptions."""
    events = integration_repo.fetch_pending_webhook_events(db, limit=limit)
    processed = 0
    for event in events:
        try:
            _fanout_event(db, event)
            integration_repo.update_webhook_event_status(db, event, "PUBLISHED")
            db.commit()
            processed += 1
        except Exception as exc:
            logger.warning("Failed to fan out webhook event %s: %s", event.id, exc)
            db.rollback()
            try:
                integration_repo.update_webhook_event_status(db, event, "FAILED")
                db.commit()
            except Exception:
                db.rollback()
    return processed


def _fanout_event(db, event) -> None:
    """Create delivery records for all active subscriptions matching the event type."""
    subscriptions = integration_repo.active_subscriptions_for_event(db, event.event_type)
    for sub in subscriptions:
        # Skip if delivery already exists (idempotent sweep)
        existing = (
            db.query(__import__("backend.db.models", fromlist=["WebhookDelivery"]).WebhookDelivery)
            .filter_by(webhook_event_id=str(event.id), subscription_id=str(sub.id))
            .one_or_none()
        )
        if existing:
            continue
        integration_repo.insert_webhook_delivery(
            db,
            webhook_event_id=str(event.id),
            subscription_id=str(sub.id),
            status="PENDING",
            next_attempt_at=utc_now(),
        )


def sweep_retries(db, limit: int = 50) -> int:
    """Retry RETRYING deliveries whose next_attempt_at is due."""
    deliveries = integration_repo.fetch_retrying_webhook_deliveries(db, limit=limit)
    processed = 0
    for delivery in deliveries:
        try:
            _attempt_delivery(db, delivery)
            db.commit()
            processed += 1
        except Exception as exc:
            logger.warning("Error processing delivery %s: %s", delivery.id, exc)
            db.rollback()
    return processed


def sweep_pending_deliveries(db, limit: int = 100) -> int:
    """Process PENDING deliveries (created by fanout)."""
    from backend.db.models import WebhookDelivery
    now = utc_now()
    deliveries = (
        db.query(WebhookDelivery)
        .filter(
            WebhookDelivery.status == "PENDING",
            WebhookDelivery.next_attempt_at <= now,
        )
        .order_by(WebhookDelivery.next_attempt_at)
        .limit(limit)
        .all()
    )
    processed = 0
    for delivery in deliveries:
        try:
            _attempt_delivery(db, delivery)
            db.commit()
            processed += 1
        except Exception as exc:
            logger.warning("Error processing pending delivery %s: %s", delivery.id, exc)
            db.rollback()
    return processed


def _attempt_delivery(db, delivery) -> None:
    """Execute a single webhook delivery attempt."""
    from backend.db.models import WebhookDelivery, WebhookEvent, WebhookSubscription

    event = db.query(WebhookEvent).filter_by(id=str(delivery.webhook_event_id)).one_or_none()
    sub = (
        db.query(WebhookSubscription).filter_by(id=str(delivery.subscription_id)).one_or_none()
    )

    if event is None or sub is None:
        integration_repo.update_webhook_delivery(db, delivery, status="FAILED",
                                                  last_error="event or subscription not found")
        return

    if sub.status == "DISABLED":
        integration_repo.update_webhook_delivery(db, delivery, status="DISABLED",
                                                  last_error="subscription disabled")
        return

    # Mark as PROCESSING
    integration_repo.update_webhook_delivery(db, delivery, status="PROCESSING")
    db.flush()

    timestamp = utc_now().isoformat()
    payload_dict = build_webhook_payload(
        event_id=str(event.id),
        event_type=event.event_type,
        aggregate_type=event.aggregate_type,
        aggregate_id=str(event.aggregate_id),
        project_id=str(event.project_id) if event.project_id else None,
        occurred_at=event.occurred_at,
        data=event.payload or {},
    )
    payload_bytes = json.dumps(payload_dict, separators=(",", ":")).encode("utf-8")
    signature = sign_payload(sub.secret_hash, payload_bytes, timestamp)

    headers = {
        "Content-Type": "application/json",
        "X-PoA-Event-ID": str(event.id),
        "X-PoA-Event-Type": event.event_type,
        "X-PoA-Timestamp": timestamp,
        "X-PoA-Signature": f"sha256={signature}",
        "X-PoA-Delivery-ID": str(delivery.id),
    }

    attempt_count = (delivery.attempt_count or 0) + 1
    status_code = None
    error_msg = None

    try:
        # Validate URL each delivery (SSRF protection; never follow redirects)
        validate_webhook_url(sub.endpoint_url)
        req = urllib.request.Request(sub.endpoint_url, data=payload_bytes, headers=headers,
                                     method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            status_code = resp.status
    except urllib.error.HTTPError as exc:
        status_code = exc.code
        error_msg = f"HTTP {exc.code}: {exc.reason}"
    except urllib.error.URLError as exc:
        error_msg = f"URLError: {exc.reason}"
    except ValueError as exc:
        error_msg = f"SSRF blocked: {exc}"
        # Permanent failure — do not retry
        integration_repo.update_webhook_delivery(
            db, delivery,
            status="FAILED",
            attempt_count=attempt_count,
            last_error=error_msg,
        )
        _record_delivery_audit(db, event, sub, delivery, success=False, error=error_msg)
        return
    except Exception as exc:
        error_msg = str(exc)

    delivered = status_code is not None and 200 <= status_code < 300

    if delivered:
        integration_repo.update_webhook_delivery(
            db, delivery,
            status="DELIVERED",
            attempt_count=attempt_count,
            last_status_code=status_code,
            last_error=None,
            delivered_at=utc_now(),
        )
        sub.consecutive_failures = 0
        sub.last_delivery_at = utc_now()
        db.flush()
        _record_delivery_audit(db, event, sub, delivery, success=True)
        return

    # Failed attempt
    can_retry = (
        attempt_count < MAX_DELIVERY_ATTEMPTS
        and (status_code is None or is_retryable_status(status_code))
    )
    next_attempt = compute_next_webhook_attempt(attempt_count) if can_retry else None
    new_status = "RETRYING" if can_retry and next_attempt else "FAILED"

    sub.consecutive_failures = (sub.consecutive_failures or 0) + 1
    if sub.consecutive_failures >= MAX_CONSECUTIVE_FAILURES_BEFORE_DISABLE:
        sub.status = "DISABLED"
        logger.warning(
            "Webhook subscription %s auto-disabled after %d consecutive failures",
            sub.id, sub.consecutive_failures,
        )
        new_status = "DISABLED"

    integration_repo.update_webhook_delivery(
        db, delivery,
        status=new_status,
        attempt_count=attempt_count,
        last_status_code=status_code,
        last_error=error_msg or (f"HTTP {status_code}" if status_code else "Connection failed"),
        next_attempt_at=next_attempt,
    )
    _record_delivery_audit(db, event, sub, delivery, success=False, error=error_msg)


def _record_delivery_audit(db, event, sub, delivery, success: bool, error: str | None = None) -> None:
    event_type_audit = (
        "WEBHOOK_DELIVERY_SUCCEEDED" if success else "WEBHOOK_DELIVERY_FAILED"
    )
    try:
        audit_service.append_event(
            db,
            event_type=event_type_audit,
            action="deliver",
            resource_type="webhook_delivery",
            resource_id=str(delivery.id),
            actor_id=None,
            project_id=str(event.project_id) if event.project_id else None,
            payload={
                "event_type": event.event_type,
                "subscription_id": str(sub.id),
                "success": success,
                "error": error,
            },
            source="webhook_worker",
        )
    except Exception as exc:
        logger.warning("Failed to write webhook delivery audit: %s", exc)


def run_worker_once(limit: int = 50) -> None:
    """Run one full pass: fanout events, then attempt deliveries."""
    db = SessionLocal()
    try:
        events_processed = sweep_webhook_events(db, limit=limit)
        deliveries_processed = sweep_pending_deliveries(db, limit=limit * 2)
        retries_processed = sweep_retries(db, limit=limit)
        logger.info(
            "Webhook worker pass: events=%d pending_deliveries=%d retries=%d",
            events_processed, deliveries_processed, retries_processed,
        )
    finally:
        db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    parser = argparse.ArgumentParser(description="BE-019 webhook worker")
    parser.add_argument("--sweep-events", action="store_true", help="Sweep pending events")
    parser.add_argument("--sweep-retries", action="store_true", help="Sweep retrying deliveries")
    parser.add_argument("--once", action="store_true", help="Full single pass")
    parser.add_argument("--limit", type=int, default=50, help="Max items per sweep")
    args = parser.parse_args()

    if args.once or (not args.sweep_events and not args.sweep_retries):
        run_worker_once(limit=args.limit)
    else:
        db = SessionLocal()
        try:
            if args.sweep_events:
                n = sweep_webhook_events(db, limit=args.limit)
                logger.info("Swept %d webhook events", n)
            if args.sweep_retries:
                n = sweep_retries(db, limit=args.limit)
                logger.info("Swept %d retries", n)
        finally:
            db.close()

