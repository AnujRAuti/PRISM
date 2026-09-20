"""BE-016 FastAPI authentication adapter (thin; evaluation stays in service).

Development bearer tokens (``dev-user-<uuid>``, ``dev-client-<uuid>``) are
non-secret identifiers accepted only when explicitly enabled for
development/testing. They must never be treated as production
authentication; production OIDC/OAuth2 plugs into ``resolve_principal``
later. Anonymous requests are permitted only in development mode;
enforcing mode rejects them (401) and never falls back silently.
"""

import logging
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.db.session import get_db
from backend.repositories import authorization as auth_repo
from backend.services.authorization import (
    Principal,
    Resource,
    anonymous_principal,
    resolve_client_principal,
    resolve_user_principal,
    system_principal,
)


logger = logging.getLogger(__name__)
_dev_bypass_logged = False


def parse_bearer_token(request: Request) -> str | None:
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def resolve_principal(request: Request, db: Session) -> Principal:
    """Resolve credentials to a principal (401 on invalid/disabled)."""
    token = parse_bearer_token(request)
    if token is None:
        if settings.auth_mode == "enforcing":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                detail="Authentication required")
        return anonymous_principal()
    if not settings.auth_dev_tokens_enabled:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid credentials")
    if token.startswith("dev-user-"):
        try:
            subject = str(UUID(token[len("dev-user-"):]))
            principal = resolve_user_principal(db, subject)
        except (ValueError, SQLAlchemyError):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                detail="Invalid credentials")
        if not principal.authenticated or principal.status != "ACTIVE":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                detail="Invalid credentials")
        return principal
    if token.startswith("dev-client-"):
        try:
            client_id = str(UUID(token[len("dev-client-"):]))
        except ValueError:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                detail="Invalid credentials")
        client = auth_repo.get_client(db, client_id)
        if client is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                detail="Invalid credentials")
        principal = resolve_client_principal(db, client)
        if principal.status != "ACTIVE":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                detail="Invalid credentials")
        return principal
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Invalid credentials")


def resolve_system_principal() -> Principal:
    """Intra-process trusted principal for background workers (never HTTP)."""
    return system_principal()


def get_current_principal(request: Request, db: Session = Depends(get_db)) -> Principal:
    return resolve_principal(request, db)


def is_development_bypass(principal: Principal) -> bool:
    """Explicit, loudly-logged development bypass for anonymous requests."""
    global _dev_bypass_logged
    if principal.principal_type != "ANONYMOUS":
        return False
    if settings.auth_mode != "development":
        return False
    if not _dev_bypass_logged:
        logger.warning(
            "AUTH_MODE=development: anonymous requests bypass authorization. "
            "Set AUTH_MODE=enforcing for any shared deployment."
        )
        _dev_bypass_logged = True
    return True


def describe_principal(principal: Principal) -> str:
    return f"{principal.principal_type}:{principal.principal_id or 'anonymous'}"


def secure_log_decision(request: Request, principal: Principal, action: str,
                        resource: Resource, allowed: bool, reason: str) -> None:
    """Security log without secrets, payloads, or presigned material."""
    request_id = None
    try:
        from backend.core.logging import request_id_ctx

        request_id = request_id_ctx.get(None)
    except Exception:
        request_id = None
    logger.info(
        "authz action=%s resource=%s:%s principal=%s allowed=%s reason=%s request_id=%s",
        action, resource.resource_type, resource.resource_id,
        describe_principal(principal), allowed, reason, request_id,
    )
