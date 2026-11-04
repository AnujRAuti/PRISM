"""BE-016 unit tests: principals, scopes, and can() decisions (no database)."""

from backend.services.authorization import (
    POLICY_VERSION,
    Principal,
    Resource,
    Scope,
    anonymous_principal,
    can,
    system_principal,
)


def user(perms):
    """Authenticated ACTIVE user with explicit permission -> scopes."""
    return Principal(
        principal_id="user-1", principal_type="USER", authenticated=True,
        status="ACTIVE", display_name="Test User",
        permissions={perm: tuple(scopes) for perm, scopes in perms.items()},
    )


def test_anonymous_is_denied_everything():
    decision = can(anonymous_principal(), "project.read",
                   Resource("project", "p1", project_id="p1"))
    assert decision.allowed is False
    assert decision.reason == "UNAUTHENTICATED"
    assert decision.policy_version == POLICY_VERSION


def test_disabled_principals_denied_despite_permissions():
    for status in ("SUSPENDED", "DISABLED"):
        principal = Principal(
            principal_id="u", principal_type="USER", authenticated=True,
            status=status,
            permissions={"project.read": (Scope("GLOBAL"),)},
        )
        decision = can(principal, "project.read", Resource("project", "p", "p"))
        assert decision.allowed is False
        assert decision.reason == "PRINCIPAL_DISABLED"


def test_global_scope_covers_everything():
    principal = user({"project.read": [Scope("GLOBAL")]})
    assert can(principal, "project.read",
               Resource("project", "p1", "p1", "o1", "u1")).allowed is True
    decision = can(principal, "project.read", Resource("project", "p2", "p2"))
    assert (decision.allowed, decision.scope) == (True, "GLOBAL")


def test_project_scope_narrowing():
    principal = user({"project.read": [Scope("PROJECT", project_id="pA")]})
    assert can(principal, "project.read",
               Resource("project", "pA", "pA")).allowed is True
    denied = can(principal, "project.read", Resource("project", "pB", "pB"))
    assert denied.allowed is False
    assert denied.reason == "SCOPE_DENIED"
    # A project grant never becomes organization-wide.
    denied_org = can(principal, "project.read",
                     Resource("project", "pB", "pB", organization_id="o1"))
    assert denied_org.allowed is False


def test_organization_scope_covers_member_projects():
    principal = user({"project.read": [Scope("ORGANIZATION", organization_id="o1")]})
    assert can(principal, "project.read",
               Resource("project", "p1", "p1", organization_id="o1")).allowed is True
    assert can(principal, "project.read",
               Resource("project", "p2", "p2", organization_id="o2")).allowed is False


def test_unit_scope_covers_member_projects_only():
    principal = user({"claim.read": [Scope("ORGANIZATIONAL_UNIT", organizational_unit_id="u1")]})
    assert can(principal, "claim.read",
               Resource("claim", "c1", project_id="p1", organizational_unit_id="u1")
               ).allowed is True
    assert can(principal, "claim.read",
               Resource("claim", "c2", project_id="p2",
                        organizational_unit_id="u2")).allowed is False


def test_missing_permission_denied():
    principal = user({"project.read": [Scope("GLOBAL")]})
    decision = can(principal, "review_case.decide", Resource("review_case", "c", "p"))
    assert decision.allowed is False
    assert decision.reason == "NO_PERMISSION"


def test_unscoped_resource_requires_global():
    scoped = user({"evidence.read": [Scope("PROJECT", project_id="pA")]})
    decision = can(scoped, "evidence.read", Resource("evidence", "e1", None))
    assert decision.allowed is False
    assert decision.reason == "RESOURCE_UNSCOPEABLE"
    global_user = user({"evidence.read": [Scope("GLOBAL")]})
    assert global_user.permissions and can(
        global_user, "evidence.read", Resource("evidence", "e1", None)).allowed is True


def test_unknown_permission_fails_closed():
    principal = user({"project.read": [Scope("GLOBAL")]})
    decision = can(principal, "mind.read", Resource("project", "p", "p"))
    assert decision.allowed is False
    assert decision.reason == "UNKNOWN_PERMISSION"


def test_admin_never_implies_substantive_authority():
    admin = user({
        "organization.manage": [Scope("GLOBAL")],
        "user.manage": [Scope("GLOBAL")],
        "role.manage": [Scope("GLOBAL")],
        "configuration.manage": [Scope("GLOBAL")],
        "audit.read": [Scope("GLOBAL")],
    })
    assert can(admin, "review_case.decide",
               Resource("review_case", "c", "p")).allowed is False
    assert can(admin, "review_case.resolve",
               Resource("review_case", "c", "p")).allowed is False
    assert can(admin, "organization.manage", Resource("global")).allowed is True


def test_substantive_permissions_are_distinct():
    reviewer = user({"review_case.read": [Scope("PROJECT", project_id="p")]})
    resource = Resource("review_case", "c", "p")
    assert can(reviewer, "review_case.read", resource).allowed is True
    assert can(reviewer, "review_case.decide", resource).allowed is False
    assert can(reviewer, "review_case.resolve", resource).allowed is False


def test_api_client_scopes():
    scoped_client = Principal(
        principal_id="client-1", principal_type="API_CLIENT", authenticated=True,
        status="ACTIVE", permissions={"evidence.read": (Scope("PROJECT", project_id="pA"),)},
        scopes=("evidence.read",),
    )
    assert can(scoped_client, "evidence.read",
               Resource("evidence", "e", "pA")).allowed is True
    assert can(scoped_client, "evidence.read",
               Resource("evidence", "e", "pB")).allowed is False
    assert can(scoped_client, "review_case.decide",
               Resource("review_case", "c", "pA")).allowed is False


def test_disabled_client_denied():
    client = Principal(
        principal_id="client-1", principal_type="API_CLIENT", authenticated=True,
        status="SUSPENDED", permissions={"evidence.read": (Scope("GLOBAL"),)},
    )
    assert can(client, "evidence.read", Resource("evidence", "e", "p")).allowed is False


def test_system_principal_is_global():
    system = system_principal()
    assert system.authenticated is True
    assert can(system, "audit.read", Resource("global")).allowed is True


def test_no_client_supplied_fields_influence_decisions():
    # Principals carry no claimed role/permission/scope fields: forging
    # request-body values cannot widen a decision because can() only reads
    # the server-resolved snapshot.
    principal = user({"project.read": [Scope("PROJECT", project_id="pA")]})
    assert not hasattr(principal, "claimed_role")
    assert not hasattr(principal, "claimed_permission")
    assert not hasattr(principal, "claimed_project_id")
    denied = can(principal, "project.read", Resource("project", "pB", "pB"))
    assert denied.allowed is False


def test_decisions_are_deterministic():
    principal = user({"claim.read": [Scope("ORGANIZATION", organization_id="o1")]})
    resource = Resource("claim", "c1", "p1", "o1")
    first = can(principal, "claim.read", resource)
    second = can(principal, "claim.read", resource)
    assert first == second
    assert first.policy_version == POLICY_VERSION


def test_response_schemas_have_no_secret_fields():
    from backend.schemas import authorization as auth_schemas

    for model in (auth_schemas.PrincipalResponse, auth_schemas.UserResponse,
                  auth_schemas.ApiClientResponse,
                  auth_schemas.AuthorizationDecisionResponse):
        fields = set(model.model_fields)
        assert not (fields & {"password", "secret", "token", "api_key", "private_key"})
