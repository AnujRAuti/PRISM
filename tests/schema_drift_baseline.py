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
            "Alembic 1.11.2 rebuilds each reflected UNIQUE constraint in "
            "autogenerate/compare.py::_make_unique_constraint() from column "
            "names and name alone, discarding the dialect options SQLAlchemy "
            "2.0.52 did hand it -- measured: get_unique_constraints() returns "
            "postgresql_nulls_not_distinct=True, and pg_get_constraintdef "
            "shows 'UNIQUE NULLS NOT DISTINCT (...)'. So the live side of the "
            "comparison lacks the flag, the model side has it, and the pair is "
            "permanent. Removing the flag from the model would make the pair "
            "vanish -- which would silently weaken the constraint. Tooling "
            "artifact, not drift. (Mechanism corrected 2026-10-10; BE-029 "
            "results §14.6. The original wording blamed reflection.)"
        ),
    ),
    AcceptedDrift(
        "add_constraint|user_role_assignments|uq_user_role_scoped",
        classification="B",
        reason="Second half of the nulls-not-distinct comparison artifact above.",
    ),
    # BE-028's four Category E entries (remove_index/add_index on
    # users.ix_users_username and users.ix_users_email) are gone, deliberately
    # and in the change that removed them: BE-029 archived and retired the
    # synthetic identity residue (r8s9t0u1v028), then recreated both indexes as
    # UNIQUE (s9t0u1v2w029) so the model's unique=True is now enforced by the
    # schema. `alembic check` reports no drift for them any more.
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
