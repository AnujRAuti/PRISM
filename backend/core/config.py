"""Configuration using Pydantic BaseSettings."""

import ipaddress
from urllib.parse import urlsplit

from pydantic import model_validator
from pydantic_settings import BaseSettings

#: Values that must never authenticate a real deployment. The placeholder is the
#: documented development default (``jwt_secret = "changeme"``); the empty string
#: is what an unset variable collapses to. Rejecting both in production closes the
#: BE-032 finding that a development default could silently become a production
#: credential. The minimum length keeps a trivially short hand-set secret out too.
UNSAFE_JWT_SECRETS = frozenset({"", "changeme"})
MIN_JWT_SECRET_LENGTH = 32

#: Identity-provider hosts that can never resolve to a real provider.
#: ``supabase.auth.local`` was committed as the default issuer (PRISM-1): it
#: satisfied the non-blank + ``https://`` checks while pointing at a host that
#: does not exist, so a deployment booted looking verified and refused every
#: reviewer. Loopback and ``0.0.0.0`` are where a developer's own process lives,
#: the suffixes are reserved-non-public TLDs, and a single-label name is a local
#: mDNS/hosts-entry alias rather than a hosted issuer.
PLACEHOLDER_OIDC_HOSTS = frozenset({
    "supabase.auth.local", "localhost", "localhost.localdomain", "0.0.0.0", "::1",
})
NON_PUBLIC_OIDC_SUFFIXES = (
    ".local", ".localhost", ".internal", ".test", ".example", ".invalid",
    ".localdomain", ".onion",
)


def oidc_endpoint_host(label: str, value: str) -> str:
    """Validate one identity endpoint and return its lowercase hostname.

    Raises ``ValueError`` with the offending field named, because a
    half-configured verifier fails every request in a way that looks like the
    provider is broken. Only the host appears in the message — an issuer URL is
    not secret, but a full value in a boot error tends to end up in shared logs.
    """
    stripped = (value or "").strip()
    if not stripped:
        raise ValueError(f"{label} must be set when auth_oidc_enabled is true")
    if not stripped.lower().startswith("https://"):
        raise ValueError(
            f"{label} must be an https:// address when auth_oidc_enabled is true"
        )
    try:
        host = (urlsplit(stripped).hostname or "").lower().rstrip(".")
    except ValueError as error:  # an unparseable authority, e.g. a bad IPv6 literal
        raise ValueError(f"{label} is not a parseable https:// URL") from error
    if not host:
        raise ValueError(f"{label} must name a hostname")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and (
        address.is_loopback or address.is_unspecified or address.is_link_local
    ):
        raise ValueError(
            f"{label} points at a non-routable address ({host}); an identity "
            "provider must be reachable from the deployment"
        )
    if (host in PLACEHOLDER_OIDC_HOSTS or "." not in host
            or host.endswith(NON_PUBLIC_OIDC_SUFFIXES)):
        raise ValueError(
            f"{label} uses the non-public host {host!r}, which cannot be a real "
            "identity provider; set the provider's published issuer address"
        )
    return host


class Settings(BaseSettings):
    app_name: str = "proof-of-action-backend"
    environment: str = "development"

    # Data stores
    # Use PostgreSQL in development by default (do not use SQLite).
    database_url: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/pofa_dev"
    # BE-037 Phase A: the identity Alembic connects with. It defaults to
    # ``database_url`` (see ``migration_database_url`` below) so development,
    # test and staging setups that provide only DATABASE_URL are unchanged. In a
    # production deployment the API/workers run as the least-privileged
    # ``poa_runtime`` role (DATABASE_URL) while migrations run as the owning
    # ``poa_migrator`` role via this variable, keeping schema DDL off the runtime
    # credential. ``poa_runtime`` has no DDL rights, so a migration attempted
    # through it fails loudly rather than silently escalating.
    migration_database_url: str | None = None
    redis_url: str = "redis://localhost:6379/0"
    analysis_queue_name: str = "pofa:analysis:jobs"
    analysis_max_attempts: int = 3
    analysis_abandoned_timeout_seconds: int = 300
    # BE-037 I1: how the analysis worker waits out a Redis outage. The wait is
    # ``min(max, base * 2 ** failures)``, split half fixed and half jitter so
    # several workers do not retry in lockstep. Bounded on purpose: a long
    # outage settles at a steady poll rate rather than a growing one, and the
    # worker never gives up (queued work is in Redis, so exiting would leave it
    # stranded). The poll interval is what lets SIGTERM stop a wait early.
    analysis_retry_backoff_base_seconds: float = 1.0
    analysis_retry_backoff_max_seconds: float = 60.0
    analysis_shutdown_poll_seconds: float = 0.5
    # BE-037 WS-C: finite socket bounds for the queue connection. Measured on a
    # disposable Redis with the previous settings (redis-py 4.6.0 defaults, all
    # three ``None``/0): a frozen server left ``ping`` and the blocking
    # ``brpoplpush`` hanging past a 45-second budget, so the worker could neither
    # process nor reach its backoff path — a stall with no clean disconnect is
    # invisible to the outage handler until the read itself has a deadline.
    # ``socket_timeout`` must exceed the blocking dequeue's own wait, or a healthy
    # idle poll would look like a failure; that invariant is asserted where the
    # two values meet (see AnalysisQueue). ``health_check_interval`` is a
    # complement, not a substitute: redis-py only checks the socket *before* the
    # next command, never mid-reply.
    analysis_redis_socket_timeout_seconds: float = 30.0
    analysis_redis_socket_connect_timeout_seconds: float = 10.0
    analysis_redis_health_check_interval_seconds: float = 15.0
    #: How long a blocking dequeue waits for a message before returning nothing.
    analysis_dequeue_block_seconds: int = 5
    phash_max_hamming_distance: int = 8
    embedding_model_name: str = "openai/clip-vit-base-patch32"
    embedding_dimension: int = 512
    embedding_top_k: int = 10

    # BE-009 Vision Intelligence (Ultralytics YOLO; weights auto-downloaded
    # at runtime, never committed to Git).
    vision_enabled: bool = True
    vision_model_name: str = "yolo11n.pt"
    vision_conf_threshold: float = 0.25
    vision_iou_threshold: float = 0.45
    vision_max_detections: int = 100
    vision_device: str = "auto"
    vision_imgsz: int = 640

    # S3 / MinIO
    s3_endpoint: str = "http://localhost:9000"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_region: str = "us-east-1"
    s3_use_ssl: bool = False
    s3_quarantine_bucket: str = "pofa-quarantine"
    s3_evidence_bucket: str = "pofa-evidence"
    max_upload_size: int = 10 * 1024 * 1024

    jwt_secret: str = "changeme"

    # CORS. Comma-separated list of the origins allowed to call this API with
    # credentials. The default keeps the historical development behaviour
    # (every origin), which must be replaced for any shared deployment: with
    # allow_credentials on, a wildcard makes the middleware echo back whatever
    # Origin the caller sent, so any website can read authenticated responses.
    cors_allow_origins: str = "*"

    # BE-016 Authentication & Authorization foundation.
    # development: anonymous requests are permitted (existing behavior) while
    # presented credentials are fully enforced. enforcing: anonymous requests
    # are rejected (401); use in any shared/production deployment.
    # The default is the permissive one on purpose. Hardening lives in
    # ``_validate_production_settings``, so a deployment cannot inherit these
    # values silently; putting the safe values here instead would break local
    # work (a checkout with no sign-in path could not call its own API).
    auth_mode: str = "development"
    # Development bearer tokens (dev-user-<uuid>, dev-client-<id>) are
    # non-secret identifiers accepted only when this is explicitly enabled.
    # Production OIDC/OAuth2 integration must disable this.
    auth_dev_tokens_enabled: bool = True

    # Stage 02 — trusted human identity (Supabase Auth, verified locally over
    # JWKS). Off by default so an unconfigured deployment keeps the existing
    # service-credential-only posture; enabling it is what lets a browser send
    # the reviewer's own sign-in token instead of a service secret.
    # No endpoint is shipped as a default: an unset issuer is visibly unset,
    # whereas a placeholder reads as configured while refusing every reviewer.
    auth_oidc_enabled: bool = False
    auth_oidc_issuer: str = ""
    auth_oidc_jwks_uri: str = ""
    auth_oidc_audience: str = "authenticated"
    # The users.identity_provider value a verified token's `sub` is looked up under.
    auth_oidc_identity_provider: str = "supabase"
    # Only asymmetric algorithms are accepted; a JWKS entry using any other
    # `alg` is refused, which is what blocks key-type confusion attacks.
    # Set this to the algorithm the provider actually signs with (Supabase's
    # current key is ES256) — a mismatch fails closed, it never falls open.
    auth_oidc_algorithms: str = "RS256"
    auth_oidc_jwks_ttl_seconds: int = 300

    # BE-020 Observability Configuration
    otel_enabled: bool = False
    otel_service_name: str = "poa-backend"
    otel_exporter_otlp_endpoint: str = ""
    otel_trace_sample_rate: float = 0.1
    prometheus_enabled: bool = True
    observability_log_format: str = "json"
    observability_redact_sensitive: bool = True

    @property
    def alembic_database_url(self) -> str:
        """The DSN Alembic should connect with.

        Falls back to the runtime ``database_url`` when no dedicated migration
        identity is configured, so single-credential (dev/test/staging) setups
        keep working unchanged.
        """
        return self.migration_database_url or self.database_url

    @property
    def cors_origin_list(self) -> list[str]:
        """The allowlist as a list; an empty or blank value keeps every origin."""
        origins = [o.strip() for o in self.cors_allow_origins.split(",") if o.strip()]
        return origins or ["*"]

    @model_validator(mode="after")
    def _validate_production_settings(self):
        """Refuse any insecure development default in a production deployment.

        Fails at ``Settings()`` construction — i.e. at import time, before any
        request is served — so a misconfigured production process cannot start.
        These are the settings BE-032R closed for ``jwt_secret`` and BE-037
        extends to the rest of the security-critical surface: each default is
        safe for local work but silently dangerous if it reaches production.
        Development, testing and staging keep the permissive defaults; no secret
        value is ever echoed into the error.
        """
        if self.environment.strip().lower() in {"production", "prod"}:
            secret = self.jwt_secret or ""
            if secret in UNSAFE_JWT_SECRETS or len(secret) < MIN_JWT_SECRET_LENGTH:
                raise ValueError(
                    "jwt_secret is unsafe for production: set a distinct secret of at "
                    f"least {MIN_JWT_SECRET_LENGTH} characters (the development default "
                    "and blank values are rejected). The secret value is not shown here."
                )
            # Authentication posture: development mode lets anonymous requests
            # bypass authorization, so production must be explicitly enforcing.
            if self.auth_mode.strip().lower() != "enforcing":
                raise ValueError(
                    "auth_mode must be 'enforcing' in production (got "
                    f"{self.auth_mode!r}); the development mode accepts anonymous "
                    "requests and bypasses authorization."
                )
            # Development bearer tokens are non-secret identifiers and must be
            # disabled alongside enforcing mode for any real deployment.
            if self.auth_dev_tokens_enabled:
                raise ValueError(
                    "auth_dev_tokens_enabled must be false in production: the "
                    "development tokens are non-secret identifiers."
                )
            # With allow_credentials on (see backend/app/main.py), a wildcard
            # origin makes the middleware echo back any caller's Origin, so every
            # website could read authenticated responses.
            if "*" in self.cors_origin_list:
                raise ValueError(
                    "cors_allow_origins must be an explicit origin allowlist in "
                    "production; the wildcard '*' is unsafe because credentials are "
                    "enabled, so list the real frontend origins instead."
                )
            # PRISM-1: a production reviewer deployment whose only credential is a
            # service secret has no human identity path, so every review action
            # would be attributed to an integration client (or refused). Stage 02
            # made the verifier the supported way in, therefore production must
            # have it on and pointed at a real provider — the endpoint rules
            # themselves run in _validate_oidc_settings, in every environment.
            if not self.auth_oidc_enabled:
                raise ValueError(
                    "auth_oidc_enabled must be true in production: reviewers sign in "
                    "through the identity provider, and with it off the only accepted "
                    "credential is a service client secret."
                )
            if not (self.auth_oidc_identity_provider or "").strip():
                raise ValueError(
                    "auth_oidc_identity_provider must name the provider whose tokens "
                    "production accepts; a verified subject is looked up under it."
                )
        return self

    @model_validator(mode="after")
    def _validate_oidc_settings(self):
        """A switched-on but unusable identity verifier must not start.

        ``AUTH_OIDC_ENABLED=true`` with a blank, plain-HTTP, loopback or
        placeholder issuer/JWKS address would accept nothing while looking like it
        accepts something, which is worse than leaving it off — and a key set
        fetched from a different host than the issuer is not that issuer's key set.
        Checked in every environment, not only production: the failure mode is
        identical. Only the offending host is echoed, never a full configured value.
        """
        if not self.auth_oidc_enabled:
            return self
        issuer_host = oidc_endpoint_host("auth_oidc_issuer", self.auth_oidc_issuer)
        jwks_host = oidc_endpoint_host("auth_oidc_jwks_uri", self.auth_oidc_jwks_uri)
        if issuer_host != jwks_host:
            raise ValueError(
                "auth_oidc_issuer and auth_oidc_jwks_uri must be served by the same "
                f"host (got {issuer_host!r} and {jwks_host!r}); keys from another "
                "authority cannot vouch for this issuer's tokens"
            )
        if not (self.auth_oidc_audience or "").strip():
            raise ValueError("auth_oidc_audience must not be blank when OIDC is enabled")
        algorithms = [a.strip() for a in (self.auth_oidc_algorithms or "").split(",") if a.strip()]
        if not algorithms:
            raise ValueError("auth_oidc_algorithms must list at least one algorithm")
        # Only asymmetric signing families are accepted; "none" and the HMAC
        # family would let a key material forged from the public JWKS pass.
        if any(not a[:2] in {"RS", "ES", "PS"} for a in algorithms):
            raise ValueError(
                "auth_oidc_algorithms may only contain asymmetric algorithms "
                f"(RS*/ES*/PS*); {sum(1 for a in algorithms if not a[:2] in {'RS', 'ES', 'PS'})} "
                "refused entry(ies) are not accepted."
            )
        return self

    class Config:
        env_file = ".env"


settings = Settings()
