"""Documented schema-drift baseline and the pure comparison used by the gate.

BE-028 §19-§21. The rule this encodes:

* Drift is *never* suppressed globally. ``alembic check`` still reports
  everything it finds; this file lists only the operations that have been
  investigated, classified and consciously left open, each with a reason.
* The gate fails on any operation not listed here.
* The gate ALSO fails when a listed operation disappears, because that means
  someone resolved it (or broke it) and this baseline is now a lie. Resolving
  drift requires editing this file in the same change -- a deliberate act, not
  an accident.

``signature()`` reduces one Alembic diff entry to ``kind|table|object`` so the
comparison does not depend on Alembic's repr of column types, which varies with
reflection order.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AcceptedDrift:
    signature: str
    classification: str   # BE-028 §13 category
    reason: str


def signature(entry) -> str:
    """'kind|table|object' for one Alembic compare_metadata() diff entry."""
    kind = entry[0]
    table = None
    name = None
    for item in entry[1:]:
        if isinstance(item, str):
            if table is None:
                table = item
            continue
        obj_name = getattr(item, "name", None)
        if obj_name is not None:
            if table is None:
                table = getattr(getattr(item, "table", None), "name", None)
            if name is None:
                name = obj_name
        elif table is None and hasattr(item, "tablename"):
            table = item.tablename
    return f"{kind}|{table}|{name}"


#: Operations investigated in BE-028 and intentionally left in place.
#: Keys are (kind|table|object); every entry carries its §13 classification.
ACCEPTED: tuple[AcceptedDrift, ...] = (
    AcceptedDrift(
        "remove_constraint|user_role_assignments|uq_user_role_scoped",
        classification="B",
        reason=(
            "Alembic 1.11.2 reflects a UNIQUE constraint without carrying "
            "NULLS NOT DISTINCT, so it compares the live constraint (which IS "
            "nulls-not-distinct, per pg_get_constraintdef) against the model as "
            "if they differed. Removing the flag from the model makes the pair "
            "vanish -- which would silently weaken the constraint. Tooling "
            "artifact, not drift."
        ),
    ),
    AcceptedDrift(
        "add_constraint|user_role_assignments|uq_user_role_scoped",
        classification="B",
        reason="Second half of the nulls-not-distinct comparison artifact above.",
    ),
    AcceptedDrift(
        "remove_index|users|ix_users_email",
        classification="E",
        reason=(
            "B-1: the model declares users.email unique, the schema does not "
            "enforce it, and pofa_test/pofa_dev both contain rows sharing an "
            "email. Creating the unique index would fail on existing data, and "
            "deleting that data is destructive and unapproved. Unresolved by "
            "decision -- see the BE-028 results document and proposed BE-029."
        ),
    ),
    AcceptedDrift(
        "add_index|users|ix_users_email",
        classification="E",
        reason="Second half of the B-1 email uniqueness blocker.",
    ),
    AcceptedDrift(
        "remove_index|users|ix_users_username",
        classification="E",
        reason="B-1: same blocker for username (duplicate rows exist).",
    ),
    AcceptedDrift(
        "add_index|users|ix_users_username",
        classification="E",
        reason="Second half of the B-1 username uniqueness blocker.",
    ),
)

ACCEPTED_SIGNATURES = frozenset(d.signature for d in ACCEPTED)


@dataclass(frozen=True)
class DriftVerdict:
    """What the gate learned, in a form the failure messages can act on."""

    new: tuple[str, ...]
    resolved: tuple[str, ...]

    @property
    def clean(self) -> bool:
        return not self.new and not self.resolved


def compare(collected_signatures, baseline=ACCEPTED_SIGNATURES) -> DriftVerdict:
    """Diff observed drift against the documented baseline, in both directions."""
    collected = set(collected_signatures)
    return DriftVerdict(
        new=tuple(sorted(collected - baseline)),
        resolved=tuple(sorted(baseline - collected)),
    )
