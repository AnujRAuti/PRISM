"""PRISM-3 — prove the configured identity provider really is the intended project.

:mod:`backend.core.config` refuses to boot on a placeholder or unparseable
endpoint, and :mod:`backend.security.oidc` verifies every token against the key
set it fetches. Neither of them knows which provider project the deployment is
*supposed* to talk to, so a config can be internally consistent and still point
at the wrong project: another Supabase project's issuer is a real https host with
a real key set, and its tokens verify — they just belong to different people. The
algorithm the provider actually signs with is the other half of the same trap: a
verifier configured for RS256 against a provider whose current key is ES256 boots
cleanly and then refuses every reviewer, which reads like an authorization bug.

This module is the operator-facing answer. It reads the live configuration,
compares the issuer against the project ref the operator names, fetches the real
key set, and reports whether that key set can actually verify a token under the
configured algorithms. It is a release gate, not a startup hook: it makes
outbound requests, so the application never calls it.

Nothing secret is ever reported — key identifiers and algorithm names are public
metadata, and a probe token is named only by its outcome.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlsplit

from backend.security import oidc


class CheckStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class Check:
    """One preflight assertion and what it learned."""

    name: str
    status: CheckStatus
    detail: str

    def line(self) -> str:
        return f"{self.status.value:<8} {self.name}: {self.detail}"


def host_of(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").lower().rstrip(".")
    except ValueError:
        return ""


def project_ref_of(url: str) -> str | None:
    """The provider project ref embedded in an endpoint host, if there is one."""
    host = host_of(url)
    if not host:
        return None
    labels = host.split(".")
    if host.endswith(".supabase.co") or host.endswith(".auth0.com"):
        return labels[0]
    return None


def path_of(url: str) -> str:
    return (urlsplit(url).path or "").rstrip("/")


def _endpoint_host(label: str, url: str) -> Check | None:
    """A blank or non-https endpoint is a refusal; ``None`` means it is usable."""
    if not (url or "").strip():
        return Check(label, CheckStatus.FAIL, "is not set; the verifier cannot anchor trust")
    if not url.lower().startswith("https://"):
        return Check(label, CheckStatus.FAIL, f"{label} must be https:// (got scheme "
                                              f"{urlsplit(url).scheme or 'none'!r})")
    if not host_of(url):
        return Check(label, CheckStatus.FAIL, "has no parseable host")
    return None


def run(*, expected_project_ref: str | None = None,
        probe_token: str | None = None) -> list[Check]:
    """Every assertion the release gate needs, in dependency order.

    The configuration read here is the verifier's own (:data:`oidc.settings`), so
    a gate that says PASS describes the settings the application would actually
    use — not a copy of them.
    """
    config = oidc.settings
    checks: list[Check] = []

    if not config.auth_oidc_enabled:
        return [Check("oidc_enabled", CheckStatus.FAIL,
                      "auth_oidc_enabled is false: reviewers cannot sign in, and only "
                      "service client secrets are accepted")]
    checks.append(Check("oidc_enabled", CheckStatus.PASS, "the verifier is on"))

    for label, url in (("auth_oidc_issuer", config.auth_oidc_issuer),
                       ("auth_oidc_jwks_uri", config.auth_oidc_jwks_uri)):
        refusal = _endpoint_host(label, url)
        checks.append(refusal or Check(label, CheckStatus.PASS,
                                       f"host={host_of(url)} path={path_of(url) or '/'!r}"))

    issuer_host = host_of(config.auth_oidc_issuer)
    jwks_host = host_of(config.auth_oidc_jwks_uri)
    if not issuer_host or not jwks_host:
        return checks
    if issuer_host != jwks_host:
        return checks + [Check("same_authority", CheckStatus.FAIL,
                               f"issuer host {issuer_host!r} and JWKS host {jwks_host!r} "
                               "differ: keys from one authority cannot vouch for the other")]
    checks.append(Check("same_authority", CheckStatus.PASS, f"both served by {issuer_host}"))

    # The provider's own auth path: any other path on the same host is someone
    # else's application, not the issuer that mints these tokens.
    if issuer_host.endswith(".supabase.co"):
        expected_path = "/auth/v1"
        if path_of(config.auth_oidc_issuer) != expected_path:
            checks.append(Check("issuer_shape", CheckStatus.FAIL,
                                f"a {issuer_host} issuer must be {expected_path}, got "
                                f"{path_of(config.auth_oidc_issuer) or '/'!r}"))
        else:
            checks.append(Check("issuer_shape", CheckStatus.PASS,
                                f"{expected_path} is that provider's auth path"))
    else:
        checks.append(Check("issuer_shape", CheckStatus.BLOCKED,
                            f"{issuer_host} is not a domain whose issuer path this tool "
                            "knows; confirm the path against the provider's docs"))

    derived = project_ref_of(config.auth_oidc_issuer)
    if not expected_project_ref:
        checks.append(Check("project_identity", CheckStatus.BLOCKED,
                            "no expected project ref was given, so the issuer was not "
                            "tied to a project; a syntactically valid endpoint can "
                            "still be the wrong tenant"))
    elif derived is None:
        checks.append(Check("project_identity", CheckStatus.BLOCKED,
                            f"{issuer_host} does not embed a project ref this tool can "
                            "read; verify the host against the provider's project by hand"))
    elif derived != expected_project_ref.strip().lower():
        checks.append(Check("project_identity", CheckStatus.FAIL,
                            f"issuer is project {derived!r} but the release expects "
                            f"{expected_project_ref.strip().lower()!r}: tokens would "
                            "verify and identify the wrong project's users"))
    else:
        checks.append(Check("project_identity", CheckStatus.PASS,
                            f"issuer belongs to project {derived!r}, as expected"))

    algorithms = oidc.allowed_algorithms()
    checks.append(Check("configured_algorithms",
                        CheckStatus.PASS if algorithms else CheckStatus.FAIL,
                        f"accepts {', '.join(algorithms) or 'nothing'}; identity provider "
                        f"is {config.auth_oidc_identity_provider or 'unnamed'!r}"))
    if not algorithms:
        return checks

    try:
        payload = oidc._fetch_key_set(config.auth_oidc_jwks_uri)
    except Exception as error:  # noqa: BLE001 - any provider refusal is a gate failure
        return checks + [Check("key_set_reachable", CheckStatus.FAIL,
                               f"{type(error).__name__} while fetching the published key "
                               "set; the verifier would refuse every reviewer")]
    entries = payload.get("keys") or []
    checks.append(Check("key_set_reachable", CheckStatus.PASS,
                        f"{len(entries)} published entr"
                        f"{'y' if len(entries) == 1 else 'ies'}"))

    if not entries:
        return checks + [Check("usable_keys", CheckStatus.FAIL,
                               "the key set is empty; nothing can be verified")]

    declared = [(str(entry.get("kty", "")), str(entry.get("alg", "")), str(entry.get("kid", "")))
                for entry in entries if isinstance(entry, dict)]
    families = sorted({f"{kty}/{alg or 'unspecified'}" for kty, alg, _ in declared})
    usable = oidc._index(payload, set(algorithms))
    if not usable:
        return checks + [Check(
            "usable_keys", CheckStatus.FAIL,
            f"no published key is usable under {', '.join(algorithms)}; the provider "
            f"publishes {', '.join(families)}; a symmetric or foreign-algorithm entry is "
            "never accepted, and an algorithm mismatch refuses every reviewer")]
    checks.append(Check("usable_keys", CheckStatus.PASS,
                        f"{len(usable)} verifiable key(s): "
                        f"{', '.join(sorted(usable))} (published: {', '.join(families)})"))

    accepted_families = {k.key_type for k in usable.values()}
    if accepted_families - oidc.ALLOWED_KEY_TYPES:
        checks.append(Check("key_types", CheckStatus.FAIL,
                            f"accepted key types outside {sorted(oidc.ALLOWED_KEY_TYPES)}: "
                            f"{sorted(accepted_families)}"))
    else:
        checks.append(Check("key_types", CheckStatus.PASS,
                            f"only asymmetric key types: {', '.join(sorted(accepted_families))}"))

    if probe_token:
        try:
            oidc.verify_token(probe_token)
        except oidc.OIDCError as error:
            checks.append(Check("probe_token", CheckStatus.FAIL,
                                f"a token from the provider was refused: {error.reason}"))
        except Exception as error:  # noqa: BLE001 - reported, never raised through a gate
            checks.append(Check("probe_token", CheckStatus.FAIL,
                                f"{type(error).__name__} while verifying the probe token"))
        else:
            checks.append(Check("probe_token", CheckStatus.PASS,
                                "signature, issuer, audience, lifetime and required "
                                "claims all verified"))
    else:
        checks.append(Check("probe_token", CheckStatus.BLOCKED,
                            "no real token was supplied (pass --token-file); the key set "
                            "is usable but no issued token has been verified end to end"))
    return checks


def verdict(checks: list[Check]) -> CheckStatus:
    if any(check.status is CheckStatus.FAIL for check in checks):
        return CheckStatus.FAIL
    if any(check.status is CheckStatus.BLOCKED for check in checks):
        return CheckStatus.BLOCKED
    return CheckStatus.PASS


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m backend.security.oidc_preflight",
        description="Verify the configured identity provider is the intended project "
                    "and that its published key set can verify tokens. Reads the same "
                    "environment as the application; makes outbound requests; writes "
                    "nothing.")
    parser.add_argument("--expected-project-ref", default=None,
                        help="the provider project ref this deployment must trust, e.g. "
                             "the ref in its Supabase URL. Without it the identity check "
                             "is reported as BLOCKED, not passed.")
    parser.add_argument("--token-file", default=None,
                        help="path to a file holding one real access token, used to prove "
                             "verification end to end. Never pass a token as a command "
                             "line argument: arguments leak into shell history.")
    parser.add_argument("--json", action="store_true", dest="as_json",
                        help="emit the checks as JSON for evidence capture")
    args = parser.parse_args(argv)

    token = None
    if args.token_file:
        with open(args.token_file, encoding="utf-8") as handle:
            token = handle.read().strip()

    checks = run(expected_project_ref=args.expected_project_ref, probe_token=token)
    outcome = verdict(checks)

    if args.as_json:
        print(json.dumps({"verdict": outcome.value,
                          "checks": [{"name": c.name, "status": c.status.value,
                                      "detail": c.detail} for c in checks]},
                         indent=2))
    else:
        for check in checks:
            print(check.line())
        print(f"\nverdict: {outcome.value}")
    return {CheckStatus.PASS: 0, CheckStatus.FAIL: 1, CheckStatus.BLOCKED: 2}[outcome]


if __name__ == "__main__":
    sys.exit(main())
