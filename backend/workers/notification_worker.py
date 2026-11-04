"""BE-018 notification worker entrypoint (sweep outbox, execute retries, consume stream).

Safe to restart, idempotent, transactional, and bounded.
"""

import argparse
import logging
import sys
from typing import Any

from backend.core.logging import setup_logging
from backend.db.session import get_session
from backend.repositories import notification as notif_repo
from backend.services import notification as notif_service


logger = logging.getLogger(__name__)


def sweep_outbox(limit: int = 50) -> dict[str, int]:
    """Process pending outbox events from PostgreSQL."""
    db = get_session()
    processed = 0
    failed = 0
    try:
        events = notif_repo.fetch_pending_outbox_events(db, limit=limit)
        for ev in events:
            try:
                notif_service.process_outbox_event(db, ev)
                db.commit()
                processed += 1
            except Exception as exc:
                db.rollback()
                logger.exception("Failed to process outbox event %s: %s", ev.id, exc)
                ev.status = "FAILED"
                ev.last_error = str(exc)
                db.commit()
                failed += 1
    finally:
        db.close()
    return {"processed": processed, "failed": failed}


def sweep_retries(limit: int = 50) -> dict[str, int]:
    """Process deliveries in RETRYING state whose next_attempt_at is due."""
    db = get_session()
    retried = 0
    succeeded = 0
    failed = 0
    try:
        deliveries = notif_repo.list_retrying_deliveries(db, limit=limit)
        for d in deliveries:
            try:
                retried += 1
                success = notif_service.retry_delivery(db, d)
                db.commit()
                if success:
                    succeeded += 1
                else:
                    failed += 1
            except Exception as exc:
                db.rollback()
                logger.exception("Failed to retry delivery %s: %s", d.id, exc)
                d.last_error = str(exc)
                d.status = "FAILED"
                db.commit()
                failed += 1
    finally:
        db.close()
    return {"retried": retried, "succeeded": succeeded, "failed": failed}


def run_worker_once(limit: int = 50) -> dict[str, Any]:
    """Execute one pass of outbox processing and delivery retries."""
    outbox_stats = sweep_outbox(limit=limit)
    retry_stats = sweep_retries(limit=limit)
    return {"outbox": outbox_stats, "retries": retry_stats}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run notification background worker pass.")
    parser.add_argument("--limit", type=int, default=50, help="Maximum items per sweep")
    parser.add_argument("--sweep-outbox", action="store_true", help="Only sweep pending outbox")
    parser.add_argument("--sweep-retries", action="store_true", help="Only sweep retrying deliveries")
    args = parser.parse_args(argv)
    setup_logging()

    if args.sweep_outbox:
        stats = sweep_outbox(limit=args.limit)
    elif args.sweep_retries:
        stats = sweep_retries(limit=args.limit)
    else:
        stats = run_worker_once(limit=args.limit)

    logger.info("Notification worker finished: %s", stats)
    return 0


if __name__ == "__main__":
    sys.exit(main())

