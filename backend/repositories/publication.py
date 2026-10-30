"""BE-022 publication repository: persistence and queries only.

Lifecycle rules, eligibility evaluation, snapshot projection, and audit
side effects live in ``backend.services.publication``. Nothing here decides
policy; this layer only reads and writes rows.

Publication mutations take a row lock (``with_for_update``) so concurrent
publish attempts serialize rather than racing to produce two live versions.
"""


from sqlalchemy.orm import Session

from backend.db.models import (
    Publication,
    PublicationEvent,
    PublicationPolicy,
    PublicationPolicyVersion,
    PublicationVersion,
    PublicIdentifier,
    PublicMediaDerivative,
)


# ---------------------------------------------------------------------------
# Publication policies (§9)
# ---------------------------------------------------------------------------


def get_policy(db: Session, policy_id: str):
    return db.query(PublicationPolicy).filter(PublicationPolicy.id == policy_id).one_or_none()


def get_policy_by_name(db: Session, name: str):
    return (
        db.query(PublicationPolicy)
        .filter(PublicationPolicy.name == name)
        .one_or_none()
    )


def list_policies(db: Session, *, limit: int | None, offset: int):
    query = db.query(PublicationPolicy).order_by(PublicationPolicy.name.asc())
    total = query.count()
    if limit is not None:
        query = query.limit(limit)
    return query.offset(offset).all(), total


def get_policy_version(db: Session, version_id: str):
    return (
        db.query(PublicationPolicyVersion)
        .filter(PublicationPolicyVersion.id == version_id)
        .one_or_none()
    )


def get_active_policy_version(db: Session, policy_id: str):
    """The single ACTIVE version for a policy (§9)."""
    return (
        db.query(PublicationPolicyVersion)
        .filter(
            PublicationPolicyVersion.policy_id == policy_id,
            PublicationPolicyVersion.status == "ACTIVE",
        )
        .one_or_none()
    )


def insert_policy(db: Session, **kwargs) -> PublicationPolicy:
    row = PublicationPolicy(**kwargs)
    db.add(row)
    db.flush()
    return row


def insert_policy_version(db: Session, **kwargs) -> PublicationPolicyVersion:
    row = PublicationPolicyVersion(**kwargs)
    db.add(row)
    db.flush()
    return row


def supersede_policy_versions(db: Session, policy_id: str) -> int:
    """Mark every ACTIVE version of a policy SUPERSEDED (new version wins)."""
    return (
        db.query(PublicationPolicyVersion)
        .filter(
            PublicationPolicyVersion.policy_id == policy_id,
            PublicationPolicyVersion.status == "ACTIVE",
        )
        .update({"status": "SUPERSEDED"}, synchronize_session=False)
    )


# ---------------------------------------------------------------------------
# Public identifiers (§16)
# ---------------------------------------------------------------------------


def get_identifier_by_public_id(db: Session, public_id: str):
    return (
        db.query(PublicIdentifier)
        .filter(PublicIdentifier.public_id == public_id)
        .one_or_none()
    )


def get_identifier_for_target(db: Session, target_type: str, target_id: str):
    return (
        db.query(PublicIdentifier)
        .filter(
            PublicIdentifier.target_type == target_type,
            PublicIdentifier.target_id == target_id,
        )
        .one_or_none()
    )


def next_public_id(db: Session, namespace: str, prefix: str) -> str:
    """Mint the next sequential public id for a namespace.

    NOT derived from the internal UUID or any secret (§16). Uniqueness is
    additionally enforced by the uq_public_identifier_public_id constraint,
    so a concurrent mint surfaces as IntegrityError rather than a collision.
    """
    count = (
        db.query(PublicIdentifier)
        .filter(PublicIdentifier.public_id.like(f"{namespace}-{prefix}-%"))
        .count()
    )
    candidate = f"{namespace}-{prefix}-{count + 1:06d}"
    while get_identifier_by_public_id(db, candidate) is not None:  # pragma: no cover
        count += 1
        candidate = f"{namespace}-{prefix}-{count + 1:06d}"
    return candidate


def insert_identifier(db: Session, **kwargs) -> PublicIdentifier:
    row = PublicIdentifier(**kwargs)
    db.add(row)
    db.flush()
    return row


# ---------------------------------------------------------------------------
# Publications (§6, §7)
# ---------------------------------------------------------------------------


def get_publication(db: Session, publication_id: str):
    return db.query(Publication).filter(Publication.id == publication_id).one_or_none()


def get_publication_for_update(db: Session, publication_id: str):
    """Row-locked publication read: serializes concurrent workflow transitions."""
    return (
        db.query(Publication)
        .filter(Publication.id == publication_id)
        .with_for_update()
        .one_or_none()
    )


def get_publication_for_target(db: Session, target_type: str, target_id: str):
    return (
        db.query(Publication)
        .filter(
            Publication.target_type == target_type,
            Publication.target_id == target_id,
        )
        .one_or_none()
    )


def list_publications(
    db: Session,
    *,
    status: str | None = None,
    target_type: str | None = None,
    policy_id: str | None = None,
    limit: int,
    offset: int,
):
    query = db.query(Publication)
    if status is not None:
        query = query.filter(Publication.status == status)
    if target_type is not None:
        query = query.filter(Publication.target_type == target_type)
    if policy_id is not None:
        query = query.filter(Publication.policy_id == policy_id)
    total = query.count()
    rows = (
        query.order_by(Publication.created_at.desc(), Publication.id.asc())
        .limit(limit)
        .offset(offset)
        .all()
    )
    return rows, total


def list_published_publications(
    db: Session,
    *,
    target_type: str | None = None,
    published_after=None,
    limit: int,
    offset: int,
):
    """Published-only listing for the public surface (§17).

    Every public read funnels through an explicit ``status == 'PUBLISHED'``
    filter so a DRAFT/REJECTED/UNPUBLISHED row can never be served publicly.
    """
    query = db.query(Publication).filter(Publication.status == "PUBLISHED")
    if target_type is not None:
        query = query.filter(Publication.target_type == target_type)
    if published_after is not None:
        query = query.filter(Publication.published_at >= published_after)
    total = query.count()
    rows = (
        query.order_by(Publication.published_at.desc(), Publication.id.asc())
        .limit(limit)
        .offset(offset)
        .all()
    )
    return rows, total


def insert_publication(db: Session, **kwargs) -> Publication:
    row = Publication(**kwargs)
    db.add(row)
    db.flush()
    return row


# ---------------------------------------------------------------------------
# Publication versions (§7, §8)
# ---------------------------------------------------------------------------


def insert_version(db: Session, **kwargs) -> PublicationVersion:
    row = PublicationVersion(**kwargs)
    db.add(row)
    db.flush()
    return row


def get_version(db: Session, version_id: str):
    return db.query(PublicationVersion).filter(PublicationVersion.id == version_id).one_or_none()


def list_versions(db: Session, publication_id: str):
    return (
        db.query(PublicationVersion)
        .filter(PublicationVersion.publication_id == publication_id)
        .order_by(PublicationVersion.version_number.asc())
        .all()
    )


def get_current_version(db: Session, publication_id: str):
    """The version backing the currently-public representation.

    Resolved via the publication's current_version_number rather than
    "latest row", so an unpublished newest draft never becomes the public
    source of truth.
    """
    pub = get_publication(db, publication_id)
    if pub is None or not pub.current_version_number:
        return None
    return (
        db.query(PublicationVersion)
        .filter(
            PublicationVersion.publication_id == publication_id,
            PublicationVersion.version_number == pub.current_version_number,
        )
        .one_or_none()
    )


def get_published_version_for_public_id(db: Session, public_id: str):
    """Resolve a public id to its PUBLISHED version snapshot (or None).

    Joins through the publication and requires BOTH versions.publication_id
    and the publication's PUBLISHED status, so a historical or unpublished
    version is not returned.
    """
    return (
        db.query(PublicationVersion)
        .join(Publication, Publication.id == PublicationVersion.publication_id)
        .filter(
            PublicationVersion.public_id == public_id,
            Publication.status == "PUBLISHED",
        )
        .order_by(PublicationVersion.version_number.desc())
        .first()
    )


# ---------------------------------------------------------------------------
# Publication events (append-only)
# ---------------------------------------------------------------------------


def insert_event(db: Session, **kwargs) -> PublicationEvent:
    row = PublicationEvent(**kwargs)
    db.add(row)
    db.flush()
    return row


def list_events(db: Session, publication_id: str, *, limit: int, offset: int):
    query = (
        db.query(PublicationEvent)
        .filter(PublicationEvent.publication_id == publication_id)
        .order_by(PublicationEvent.created_at.asc())
    )
    total = query.count()
    return query.limit(limit).offset(offset).all(), total


# ---------------------------------------------------------------------------
# Public media derivatives (§19, §20)
# ---------------------------------------------------------------------------


def insert_derivative(db: Session, **kwargs) -> PublicMediaDerivative:
    row = PublicMediaDerivative(**kwargs)
    db.add(row)
    db.flush()
    return row


def list_derivatives_for_publication(db: Session, publication_id: str):
    return (
        db.query(PublicMediaDerivative)
        .filter(PublicMediaDerivative.publication_id == publication_id)
        .all()
    )


def list_derivatives_for_evidence(db: Session, evidence_id: str):
    return (
        db.query(PublicMediaDerivative)
        .filter(PublicMediaDerivative.original_evidence_id == evidence_id)
        .all()
    )
