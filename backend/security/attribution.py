"""Stage 02 actor attribution: the authenticated principal is the only actor.

Decision makers and audit actors must come from the verified principal, so a
caller may not record an action under someone else's name. Request bodies may
still carry ``actor_id`` / ``decided_by`` / ``resolved_by`` (older integrations
send them), but such a value only restates the caller's own identity: anything
else is refused before any row is written.

Development mode is the single exception and it is deliberate: an *anonymous*
request there has no verified identity to derive from, and
``AUTH_MODE=development`` already bypasses authorization wholesale. Under
``AUTH_MODE=enforcing`` — the deployed posture — ``resolve_principal`` returns
401 before a handler runs, so this branch is unreachable.
"""

import logging

from fastapi import HTTPException, status

from backend.security.authentication import is_development_bypass
from backend.services.authorization import Principal

logger = logging.getLogger(__name__)


def derive_actor(principal: Principal, supplied: object | None = None, *,
                 field: str = "actor_id") -> str | None:
    """Return the actor id to persist, derived from ``principal``.

    ``supplied`` is the caller-provided value read from the request body; it is
    validated, never trusted. ``None`` means the request carried no actor field.
    """
    verified = principal.principal_id if principal.authenticated else None
    if supplied is None:
        return verified
    text = str(supplied)
    if verified is None:
        if is_development_bypass(principal):
            return text
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required to be recorded as the actor",
        )
    if text != str(verified):
        logger.warning(
            "attribution_refused field=%s principal_type=%s reason=ACTOR_MISMATCH",
            field, principal.principal_type,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"{field} must identify the authenticated principal; "
                "actors are derived from credentials, never from the request body"
            ),
        )
    return verified
