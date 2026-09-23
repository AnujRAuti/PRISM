"""BE-017 retention worker entrypoint (explicit execution, no daemon loop).

Suitable for schedulers/cron: each invocation runs one bounded sweep
(evaluate indexed expiry candidates, archive eligible resources, delete
only with explicit opt-in) under the SYSTEM principal. Deletion never
runs implicitly: ``auto_delete`` must be passed deliberately.
"""

import argparse
import logging
import sys

from backend.db.session import get_session
from backend.services import retention as retention_service
from backend.services.authorization import system_principal
from backend.services.storage import StorageService


logger = logging.getLogger(__name__)


def run_sweep_once(*, auto_delete: bool = False, limit: int = 200) -> dict:
    """Run one retention sweep (bounded, audited, deterministic stats)."""
    db = get_session()
    try:
        principal = system_principal()
        stats = retention_service.run_sweep_once(
            db, StorageService(), actor_id=principal.principal_id,
            auto_delete=auto_delete, limit=limit,
        )
        return stats
    finally:
        db.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one retention sweep.")
    parser.add_argument("--auto-delete", action="store_true",
                        help="Allow eligible deletions (default: evaluate/archive only)")
    parser.add_argument("--limit", type=int, default=200)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO)
    stats = run_sweep_once(auto_delete=args.auto_delete, limit=args.limit)
    logger.info("retention sweep finished: %s", stats)
    return 0


if __name__ == "__main__":
    sys.exit(main())
