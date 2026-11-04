"""Stage 02 — a reviewer signs in as themselves, and this proves it locally.

The browser holds the user's own access token from the identity provider
(Supabase Auth today); the service credential never leaves the server. Trust is
anchored on the provider's published JWKS: the signature, algorithm, issuer,
audience and lifetime are all verified here, in this process, before any
authorization decision is made. Nothing about a token is logged, and the key set
is cached so the provider is not fetched per request.

Refusals are raised as :class:`OIDCError` with a reason code; the HTTP layer maps
them to 401 and the reason is what reaches the security log.
"""

import logging
import threading
import time

import httpx
import jwt
from jwt import PyJWK
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.db.models import User
from backend.services.authorization import Principal, resolve_user_principal

logger = logging.getLogger(__name__)

#: Symmetric (``oct``) entries are never accepted as verification keys: a public
#: key set that also carried a shared secret would let a caller forge a token the
#: service then trusts.
ALLOWED_KEY_TYPES = {"RSA", "EC", "OKP"}

_lock = threading.Lock()
_keys: dict[str, tuple[float, dict[str, PyJWK]]] = {}
_last_forced_refresh: dict[str, float] = {}

#: A token whose ``kid`` is unknown is worth one refetch per this window, so a
#: key rotation does not need a restart but a flood of bad tokens cannot turn
#: into a flood of outbound requests.
REFRESH_COOLDOWN_SECONDS = 30.0


class OIDCError(Exception):
    """A verification refusal. The reason is safe to log; the token never is."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def allowed_algorithms() -> list[str]:
    return [a.strip() for a in (settings.auth_oidc_algorithms or "").split(",") if a.strip()]


def _fetch_key_set(uri: str) -> dict:
    """One GET against the provider's published key set."""
    response = httpx.get(uri, timeout=(3.0, 5.0), headers={"Accept": "application/json"})
    response.raise_for_status()
    return response.json()


def _index(payload: dict, algorithms: set[str] | None = None) -> dict[str, PyJWK]:
    algorithms = set(allowed_algorithms()) if algorithms is None else set(algorithms)
    indexed: dict[str, PyJWK] = {}
    for entry in payload.get("keys", []) or []:
        if str(entry.get("kty", "")) not in ALLOWED_KEY_TYPES:
            continue
        declared = str(entry.get("alg", ""))
        if declared and declared not in algorithms:
            continue
        kid = str(entry.get("kid", ""))
        if not kid:
            continue
        try:
            indexed[kid] = PyJWK(entry)
        except Exception:  # a malformed entry must not poison the whole set
            logger.warning("oidc_jwks_key_skipped kid=%s", kid)
    return indexed


def signing_keys(*, force_refresh: bool = False) -> dict[str, PyJWK]:
    """The provider's verification keys, cached for ``auth_oidc_jwks_ttl_seconds``."""
    uri = settings.auth_oidc_jwks_uri
    now = time.monotonic()
    with _lock:
        cached = _keys.get(uri)
        if cached and cached[0] > now and not force_refresh:
            return cached[1]
        if force_refresh:
            last = _last_forced_refresh.get(uri, 0.0)
            if now - last < REFRESH_COOLDOWN_SECONDS:
                if cached:
                    return cached[1]
                raise OIDCError("KEY_SET_UNAVAILABLE")
            _last_forced_refresh[uri] = now
        try:
            payload = _fetch_key_set(uri)
        except (httpx.HTTPError, ValueError) as error:
            # Serve the previous (still unexpired) key set rather than turning a
            # provider hiccup into an outage for every signed-in reviewer.
            if cached and cached[0] > now:
                logger.warning("oidc_jwks_refresh_failed_using_stale=True")
                return cached[1]
            logger.warning("oidc_jwks_unavailable")
            raise OIDCError("KEY_SET_UNAVAILABLE") from error
        fresh = _index(payload)
        _keys[uri] = (now + max(30, int(settings.auth_oidc_jwks_ttl_seconds)), fresh)
        return fresh


def verify_token(token: str) -> dict:
    """Return the verified claims, or raise :class:`OIDCError`."""
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as error:
        raise OIDCError("MALFORMED_TOKEN") from error
    algorithms = allowed_algorithms()
    declared = str(header.get("alg", ""))
    if declared not in algorithms:
        logger.warning("oidc_refused reason=ALGORITHM_REFUSED")
        raise OIDCError("ALGORITHM_REFUSED")
    kid = str(header.get("kid", ""))
    key = signing_keys().get(kid)
    if key is None:
        key = signing_keys(force_refresh=True).get(kid)
    if key is None:
        logger.warning("oidc_refused reason=UNKNOWN_KEY_ID")
        raise OIDCError("UNKNOWN_KEY_ID")
    try:
        claims = jwt.decode(
            token,
            key=key.key,
            algorithms=algorithms,
            audience=settings.auth_oidc_audience,
            issuer=settings.auth_oidc_issuer,
            leeway=30.0,
            options={"require": ["exp", "iat", "sub", "aud", "iss"]},
        )
    except jwt.PyJWTError as error:
        logger.warning("oidc_refused reason=TOKEN_REJECTED")
        raise OIDCError("TOKEN_REJECTED") from error
    # Some providers issue refresh tokens as JWTs with the same issuer and
    # audience. A refresh token is not proof of a signed-in session.
    if str(claims.get("use", "")) == "refresh":
        logger.warning("oidc_refused reason=REFRESH_TOKEN")
        raise OIDCError("REFRESH_TOKEN")
    return claims


def resolve_oidc_principal(db: Session, token: str) -> Principal:
    """Map a verified token onto the internal PoA user it belongs to.

    The link is the pair the ``users`` table already stores — ``identity_provider``
    plus ``external_subject`` — and there is deliberately no auto-provisioning:
    a sign-in nobody has granted a role to would resolve to a principal with no
    permissions, so an account is created by an administrator first.
    """
    subject = str(verify_token(token)["sub"])
    user = (
        db.query(User)
        .filter(User.identity_provider == settings.auth_oidc_identity_provider,
                User.external_subject == subject)
        .one_or_none()
    )
    if user is None:
        logger.warning("oidc_refused reason=NO_LINKED_USER")
        raise OIDCError("NO_LINKED_USER")
    principal = resolve_user_principal(db, str(user.id))
    if not principal.authenticated or principal.status != "ACTIVE":
        logger.warning("oidc_refused reason=PRINCIPAL_NOT_ACTIVE")
        raise OIDCError("PRINCIPAL_NOT_ACTIVE")
    return principal


def looks_like_jwt(token: str) -> bool:
    return token.count(".") == 2 and all(part for part in token.split("."))


def reset_key_cache() -> None:
    """Drop the cached key sets (used by tests and after a provider rotation)."""
    with _lock:
        _keys.clear()
        _last_forced_refresh.clear()
