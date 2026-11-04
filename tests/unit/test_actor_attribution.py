"""Unit tests for the single actor-attribution policy point (Stage 02-3).

The HTTP surface is covered by ``tests/integration/test_stage02_actor_attribution.py``;
what lives here are the branches that endpoint guards make unreachable in one
mode or another — the development-bypass exception and the refusal to credit an
unauthenticated caller — so the docstring in ``backend/security/attribution.py``
stays a measured claim instead of a promise.
"""

from uuid import uuid4

import pytest
from fastapi import HTTPException

from backend.core.config import settings
from backend.security.attribution import derive_actor
from backend.services.authorization import Principal


def user_principal(user_id: str) -> Principal:
    return Principal(principal_id=user_id, principal_type="USER",
                     authenticated=True, status="ACTIVE")


def anonymous_principal() -> Principal:
    return Principal(principal_id=None, principal_type="ANONYMOUS",
                     authenticated=False, status="ANONYMOUS")


@pytest.fixture
def enforcing(monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "enforcing")


@pytest.fixture
def development(monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "development")


def test_missing_actor_field_is_filled_from_the_credential(enforcing):
    assert derive_actor(user_principal("principal-1")) == "principal-1"
    assert derive_actor(user_principal("principal-1"), None, field="decided_by") == "principal-1"


def test_restatement_of_the_callers_own_id_is_accepted(enforcing):
    assert derive_actor(user_principal("principal-1"), "principal-1") == "principal-1"


def test_naming_someone_else_is_refused_before_any_write(enforcing):
    victim = str(uuid4())
    with pytest.raises(HTTPException) as refusal:
        derive_actor(user_principal("principal-1"), victim, field="decided_by")
    assert refusal.value.status_code == 403
    assert "decided_by" in refusal.value.detail


def test_a_uuid_value_matches_the_string_principal_id(enforcing):
    from uuid import UUID

    principal_id = str(uuid4())
    assert derive_actor(user_principal(principal_id), UUID(principal_id)) == principal_id


def test_an_unauthenticated_caller_may_not_be_recorded_as_an_actor(enforcing):
    with pytest.raises(HTTPException) as refusal:
        derive_actor(anonymous_principal(), str(uuid4()))
    assert refusal.value.status_code == 401


def test_development_mode_is_the_documented_exception(development):
    """AUTH_MODE=development has no verified identity to derive from."""
    supplied = str(uuid4())
    assert derive_actor(anonymous_principal(), supplied) == supplied
    assert derive_actor(anonymous_principal()) is None
