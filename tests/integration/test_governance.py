"""BE-021 integration tests against real PostgreSQL infrastructure.

Exercises the complete governance workflows end to end (§36): dispute and
correction lifecycles, dependency invalidation, staleness propagation,
immutable evidence protection, version lineage, reprocessing delegation
through the existing BE-005 pipeline, review-case preservation, human
decision preservation, role separation, authorization isolation,
concurrency, retention interaction, external-assertion governance,
notification integration, and telemetry.

The unauthenticated TestClient runs in development-bypass mode, so actor
identities are supplied explicitly in request bodies (initiator_id,
requester_id, resolved_by, ...). Authenticated tests use
``Bearer dev-user-{id}`` headers with real role assignments.
"""

import threading
from io import BytesIO
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from backend.app.main import app
from backend.db.models import (
    Activity,
    AnalysisJob,
    AnalysisResult,
    AuditLedgerEvent,
    Claim,
    CorrectionEvent,
    CorrectionRequest,
    Dispute,
    DisputeEvent,
    DuplicateMatch,
    Evidence,
    EvidenceMetadata,
    ExplanationRun,
    ExternalAssertion,
    ExternalSystem,
    FusionRun,
    GraphNode,
    GraphRelationship,
    IntegrityAssessment,
    IntelligenceInvalidation,
    NotificationOutbox,
    Organization,
    Project,
    ReprocessingRequest,
    RetentionHold,
    ReviewCase,
    ReviewCaseEvent,
    User,
    UserRoleAssignment,
)
from backend.db.session import get_session
from backend.observability import governance_metrics
from backend.services import authorization as auth_service
from backend.services import governance as governance_service
from backend.services import retention as retention_service
from backend.services.storage import StorageService


client = TestClient(app)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def image_bytes(color=(80, 150, 220)) -> bytes:
    output = BytesIO()
    Image.new("RGB", (16, 16), color=color).save(output, format="JPEG")
    return output.getvalue()


def setup_user() -> User:
    session = get_session()
    user = User(username=f"be021-{uuid4()}", email=f"{uuid4()}@example.com")
    session.add(user)
    session.commit()
    session.refresh(user)
    session.close()
    return user


def headers_for(user_id: str) -> dict:
    return {"Authorization": f"Bearer dev-user-{user_id}"}


def assign(user_id: str, role: str, scope: str, scope_id: str | None = None):
    session = get_session()
    try:
        kwargs: dict = {}
        if scope == "PROJECT":
            kwargs["project_id"] = scope_id
        row, _ = auth_service.assign_role(
            session, user_id=user_id, role_name=role, scope_type=scope, **kwargs
        )
        session.commit()
        return row
    finally:
        session.close()


def api_create_project(user_id: str, name: str = "BE-021 project") -> dict:
    response = client.post("/api/v1/projects", json={"name": name, "owner_id": user_id})
    assert response.status_code == 201, response.text
    return response.json()


def api_create_claim(project_id: str) -> dict:
    response = client.post(
        f"/api/v1/projects/{project_id}/claims",
        json={"title": "BE-021 claim", "description": "governance test"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def api_upload(data: bytes, filename: str) -> dict:
    response = client.post(
        "/api/v1/evidence", files={"file": (filename, data, "image/jpeg")}
    )
    assert response.status_code == 201, response.text
    return response.json()


def link_evidence(evidence_id: str, project_id: str, claim_id: str | None = None) -> None:
    session = get_session()
    try:
        evidence = session.query(Evidence).filter_by(id=evidence_id).one()
        evidence.project_id = project_id
        evidence.claim_id = claim_id
        session.commit()
    finally:
        session.close()


def process(evidence_id: str) -> str:
    """Run fingerprint + duplicate analysis directly (no worker needed).

    BE-006 creates the AnalysisJob; the worker would normally do this. The job
    is created here (same pattern as test_duplicate_intelligence) and its id is
    threaded into analyze_duplicates so the embedding branch persists an
    AnalysisResult — that row is the ANALYSIS_RESULT node governance
    invalidation must reach. Without a job_id, analyze_duplicates skips the
    embedding branch and no AnalysisResult exists to invalidate.
    """
    return process_with_analysis(evidence_id)[0]


def process_with_analysis(evidence_id: str) -> tuple[str, object]:
    """Same as :func:`process`, but also returns the DuplicateAnalysis.

    BE-023: an AnalysisResult is persisted *only* when the CLIP embedding
    succeeds — ``analyze_duplicates`` creates that row inside the branch that
    calls ``image_embedding``, and swallows any failure into
    ``DuplicateAnalysis.embedding_error``. So whether an ANALYSIS_RESULT node
    can exist at all is an ML-availability precondition, not a governance
    guarantee.

    This exposes the already-returned ``DuplicateAnalysis`` (it carries
    ``embedding_status``/``embedding_error``) so a test can tell "ML could not
    run" apart from "the graph failed to traverse". No production contract is
    added; :func:`process` keeps its exact signature and behaviour for its
    existing callers.
    """
    from backend.services.duplicate_intelligence import analyze_duplicates
    from backend.services.fingerprinting import process_evidence

    session = get_session()
    try:
        job = AnalysisJob(evidence_id=evidence_id, status="running", attempt_count=1)
        session.add(job)
        session.commit()
        session.refresh(job)

        process_evidence(evidence_id, session)
        analysis = analyze_duplicates(evidence_id, session, StorageService(), job.id)
        return str(job.id), analysis
    finally:
        session.close()


def add_graph_edge(evidence_id: str, claim_id: str) -> GraphRelationship:
    session = get_session()
    try:
        evidence_node = GraphNode(node_type="EVIDENCE", entity_id=evidence_id)
        claim_node = GraphNode(node_type="CLAIM", entity_id=claim_id)
        session.add_all([evidence_node, claim_node])
        session.flush()
        edge = GraphRelationship(
            source_node_id=evidence_node.id,
            target_node_id=claim_node.id,
            relationship_type="SUPPORTS",
            dedupe_key=f"be021:{uuid4()}",
            provenance={"source": "be021_test", "method": "fixture"},
        )
        session.add(edge)
        session.commit()
        session.refresh(edge)
        session.expunge(edge)
        return edge
    finally:
        session.close()


def add_fusion_chain(evidence_id: str) -> dict:
    """Insert an owned downstream chain: fusion run -> assessment +
    explanation run, plus a review case referencing the evidence."""
    session = get_session()
    try:
        run = FusionRun(
            target_type="EVIDENCE",
            target_id=evidence_id,
            status="COMPLETED",
            method="weighted_average",
            method_version="v1",
            configuration_version="v1",
            input_snapshot={},
        )
        session.add(run)
        session.flush()
        assessment = IntegrityAssessment(
            fusion_run_id=run.id,
            target_type="EVIDENCE",
            target_id=evidence_id,
            assessment_status="ACTIVE",
            assessment_value="SUPPORTED",
            signal_summary={},
        )
        explanation = ExplanationRun(
            fusion_run_id=run.id,
            method="template_v1",
            method_version="v1",
            summary={"text": "fixture explanation"},
        )
        case = ReviewCase(
            evidence_id=evidence_id,
            origin="SYSTEM_SIGNAL",
            status="OPEN",
        )
        session.add_all([assessment, explanation, case])
        session.commit()
        ids = {
            "fusion_run_id": str(run.id),
            "assessment_id": str(assessment.id),
            "explanation_id": str(explanation.id),
            "case_id": str(case.id),
        }
        return ids
    finally:
        session.close()


def row(session, model, **filters):
    return session.query(model).filter_by(**filters).one_or_none()


def cleanup(
    user_ids, project_ids, evidence_ids, org_ids=None, system_ids=None, extra_target_ids=None
) -> None:
    storage = StorageService()
    session = get_session()
    org_ids = org_ids or []
    system_ids = system_ids or []
    # Disputes may target non-evidence rows (external assertions, fusion
    # assessments); those targets must be cleaned up with the same care.
    extra_target_ids = list(extra_target_ids or [])
    try:
        keys = [
            row[0]
            for row in session.query(Evidence.storage_key)
            .filter(Evidence.id.in_(evidence_ids))
            .all()
        ]
        for key in keys:
            if storage.object_exists(storage.quarantine_bucket, key):
                storage.delete_object(storage.quarantine_bucket, key)

        # BE-021 governance rows (children first; FK-safe order).
        evidence_filter = Evidence.id.in_(evidence_ids)
        session.query(ReprocessingRequest).filter(
            ReprocessingRequest.evidence_id.in_(evidence_ids)
        ).delete(synchronize_session=False)
        dispute_ids = [
            r[0]
            for r in session.query(Dispute.id)
            .filter(
                Dispute.project_id.in_(project_ids)
                | Dispute.target_id.in_(evidence_ids + extra_target_ids)
            )
            .all()
        ]
        correction_ids = [
            r[0]
            for r in session.query(CorrectionRequest.id)
            .filter(CorrectionRequest.target_id.in_(evidence_ids))
            .all()
        ]
        if dispute_ids or correction_ids:
            session.query(IntelligenceInvalidation).filter(
                IntelligenceInvalidation.dispute_id.in_(dispute_ids)
                | IntelligenceInvalidation.correction_id.in_(correction_ids)
            ).delete(synchronize_session=False)
        if correction_ids:
            session.query(CorrectionEvent).filter(
                CorrectionEvent.correction_id.in_(correction_ids)
            ).delete(synchronize_session=False)
            session.query(CorrectionRequest).filter(
                CorrectionRequest.id.in_(correction_ids)
            ).delete(synchronize_session=False)
        if dispute_ids:
            session.query(DisputeEvent).filter(
                DisputeEvent.dispute_id.in_(dispute_ids)
            ).delete(synchronize_session=False)
            session.query(Dispute).filter(Dispute.id.in_(dispute_ids)).delete(
                synchronize_session=False
            )

        # Review cases + events for these projects/evidence.
        case_ids = [
            r[0]
            for r in session.query(ReviewCase.id)
            .filter(
                ReviewCase.project_id.in_(project_ids)
                | ReviewCase.evidence_id.in_(evidence_ids)
            )
            .all()
        ]
        run_ids = [
            r[0]
            for r in session.query(FusionRun.id)
            .filter(FusionRun.target_id.in_(evidence_ids + project_ids))
            .all()
        ]
        if case_ids:
            session.query(ReviewCaseEvent).filter(
                ReviewCaseEvent.case_id.in_(case_ids)
            ).delete(synchronize_session=False)
            session.query(ReviewCase).filter(ReviewCase.id.in_(case_ids)).delete(
                synchronize_session=False
            )
        if run_ids:
            session.query(ExplanationRun).filter(
                ExplanationRun.fusion_run_id.in_(run_ids)
            ).delete(synchronize_session=False)
            session.query(IntegrityAssessment).filter(
                IntegrityAssessment.fusion_run_id.in_(run_ids)
            ).delete(synchronize_session=False)
            session.query(FusionRun).filter(FusionRun.id.in_(run_ids)).delete(
                synchronize_session=False
            )

        # Audit twins + notification outbox for governance aggregates.
        all_ids = (
            set(dispute_ids)
            | set(correction_ids)
            | set(evidence_ids)
            | set(case_ids)
            | set(run_ids)
            | set(extra_target_ids)
        )
        # BE-015: audit_ledger_events is append-only and is deliberately
        # NEVER deleted here. The previous cleanup removed rows by
        # resource_id / actor_id / project_id, which matched events at
        # arbitrary positions in the chain and left permanent sequence
        # gaps -- sequence numbers are allocated as max(sequence_number)+1
        # and are never reused, so a deleted row's number can never be
        # reclaimed. An audit event that outlives the user, project or
        # governance row it references is correct ledger behaviour: the
        # ledger records that the actor existed and acted, and it holds no
        # FK to any subject, so nothing is orphaned by retaining it.
        session.query(NotificationOutbox).filter(
            NotificationOutbox.aggregate_id.in_(all_ids)
        ).delete(synchronize_session=False)

        # Retention holds created by tests.
        session.query(RetentionHold).filter(
            RetentionHold.resource_id.in_(evidence_ids)
            | RetentionHold.project_id.in_(project_ids)
        ).delete(synchronize_session=False)

        # External fixtures.
        session.query(ExternalAssertion).filter(
            ExternalAssertion.external_system_id.in_(system_ids)
        ).delete(synchronize_session=False)
        if system_ids:
            session.query(ExternalSystem).filter(
                ExternalSystem.id.in_(system_ids)
            ).delete(synchronize_session=False)

        # Analysis pipeline rows.
        job_ids = [
            r[0]
            for r in session.query(AnalysisJob.id)
            .filter(AnalysisJob.evidence_id.in_(evidence_ids))
            .all()
        ]
        if job_ids:
            session.query(AnalysisResult).filter(
                AnalysisResult.job_id.in_(job_ids)
            ).delete(synchronize_session=False)
            session.query(AnalysisJob).filter(AnalysisJob.id.in_(job_ids)).delete(
                synchronize_session=False
            )
        session.query(DuplicateMatch).filter(
            DuplicateMatch.evidence_id.in_(evidence_ids)
            | DuplicateMatch.matched_evidence_id.in_(evidence_ids)
        ).delete(synchronize_session=False)

        # Graph rows.
        entity_ids = list(evidence_ids) + list(project_ids)
        claim_ids = [
            r[0]
            for r in session.query(Claim.id).filter(Claim.project_id.in_(project_ids)).all()
        ]
        entity_ids += claim_ids
        node_ids = [
            r[0]
            for r in session.query(GraphNode.id)
            .filter(GraphNode.entity_id.in_(entity_ids))
            .all()
        ]
        if node_ids:
            session.query(GraphRelationship).filter(
                GraphRelationship.source_node_id.in_(node_ids)
                | GraphRelationship.target_node_id.in_(node_ids)
            ).delete(synchronize_session=False)
            session.query(GraphNode).filter(GraphNode.id.in_(node_ids)).delete(
                synchronize_session=False
            )

        # Core rows (same order proven by the BE-013 suite).
        session.query(EvidenceMetadata).filter(
            EvidenceMetadata.evidence_id.in_(evidence_ids)
        ).delete(synchronize_session=False)
        session.query(Activity).filter(
            Activity.project_id.in_(project_ids)
        ).delete(synchronize_session=False)
        session.query(Evidence).filter(evidence_filter).update(
            {Evidence.project_id: None, Evidence.claim_id: None}, synchronize_session=False
        )
        session.query(Claim).filter(Claim.project_id.in_(project_ids)).delete(
            synchronize_session=False
        )
        # Role assignments reference the project, so they must go first or the
        # Project delete fails on the FK. Scope to these projects as well as
        # these users: a role may have been granted at project scope.
        session.query(UserRoleAssignment).filter(
            UserRoleAssignment.user_id.in_(user_ids)
            | UserRoleAssignment.project_id.in_(project_ids)
        ).delete(synchronize_session=False)
        session.query(Project).filter(Project.id.in_(project_ids)).delete(
            synchronize_session=False
        )
        if org_ids:
            session.query(Organization).filter(
                Organization.id.in_(org_ids)
            ).delete(synchronize_session=False)
        session.query(User).filter(User.id.in_(user_ids)).delete(synchronize_session=False)
        session.commit()
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Dispute workflow (§36: create, review, resolve, audit)
# ---------------------------------------------------------------------------


def test_dispute_lifecycle_history_audit_and_decision_preservation():
    initiator = setup_user()
    reviewer = setup_user()
    escalation_target = setup_user()
    project = api_create_project(str(initiator.id))
    claim = api_create_claim(project["id"])
    payload = image_bytes()
    evidence = api_upload(payload, f"be021-dispute-{uuid4().hex[:8]}.jpg")
    link_evidence(evidence["evidence_id"], project["id"], claim["id"])
    try:
        created = client.post(
            "/api/v1/disputes",
            json={
                "target_type": "EVIDENCE",
                "target_id": evidence["evidence_id"],
                "reason": "Metadata appears inconsistent",
                "description": "Challenging the derived context",
                "initiator_id": str(initiator.id),
            },
        )
        assert created.status_code == 201, created.text
        dispute = created.json()
        assert dispute["status"] == "OPEN"
        dispute_id = dispute["id"]

        # Duplicate creation is idempotent (§28): same active dispute.
        duplicate = client.post(
            "/api/v1/disputes",
            json={
                "target_type": "EVIDENCE",
                "target_id": evidence["evidence_id"],
                "reason": "Metadata appears inconsistent",
                "initiator_id": str(initiator.id),
            },
        )
        assert duplicate.status_code == 200
        assert duplicate.json()["id"] == dispute_id

        # Workflow: review -> assign -> escalate -> back to review -> resolve.
        assert (
            client.post(f"/api/v1/disputes/{dispute_id}/start-review").status_code == 200
        )
        assigned = client.post(
            f"/api/v1/disputes/{dispute_id}/assign",
            json={"assigned_to": str(reviewer.id), "actor_id": str(reviewer.id)},
        )
        assert assigned.status_code == 200
        escalated = client.post(
            f"/api/v1/disputes/{dispute_id}/escalate",
            json={
                "escalated_to": str(escalation_target.id),
                "reason": "needs senior adjudication",
                "actor_id": str(reviewer.id),
            },
        )
        assert escalated.status_code == 200
        assert escalated.json()["status"] == "ESCALATED"
        back = client.post(f"/api/v1/disputes/{dispute_id}/start-review")
        assert back.status_code == 200
        assert back.json()["status"] == "UNDER_REVIEW"

        resolved = client.post(
            f"/api/v1/disputes/{dispute_id}/resolve",
            json={
                "resolution": "INCONCLUSIVE",
                "rationale": "insufficient grounds to uphold",
                "resolved_by": str(reviewer.id),
            },
        )
        assert resolved.status_code == 200, resolved.text
        assert resolved.json()["status"] == "RESOLVED"
        assert resolved.json()["resolution"] == "INCONCLUSIVE"

        # INCONCLUSIVE never invalidates intelligence (§13).
        session = get_session()
        try:
            assert (
                session.query(IntelligenceInvalidation)
                .filter_by(dispute_id=dispute_id)
                .count()
                == 0
            )
        finally:
            session.close()

        # Human decisions are append-only (§21): same resolution retries are
        # idempotent, different resolutions are refused.
        same = client.post(
            f"/api/v1/disputes/{dispute_id}/resolve",
            json={
                "resolution": "INCONCLUSIVE",
                "rationale": "retry of the same adjudication",
                "resolved_by": str(reviewer.id),
            },
        )
        assert same.status_code == 200
        assert same.json()["resolution"] == "INCONCLUSIVE"
        changed = client.post(
            f"/api/v1/disputes/{dispute_id}/resolve",
            json={
                "resolution": "UPHELD",
                "rationale": "attempting to overturn history",
                "resolved_by": str(reviewer.id),
            },
        )
        assert changed.status_code == 422

        # Append-only history reflects the actual workflow.
        history = client.get(f"/api/v1/disputes/{dispute_id}/history")
        assert history.status_code == 200
        events = history.json()["items"]
        assert [e["event_type"] for e in events] == [
            "CREATED", "REVIEW_STARTED", "ASSIGNED", "ESCALATED",
            "REVIEW_STARTED", "RESOLVED",
        ]

        # Audit twins exist for every governance step (§23).
        session = get_session()
        try:
            audit_types = {
                row[0]
                for row in session.query(AuditLedgerEvent.event_type)
                .filter(AuditLedgerEvent.resource_id == dispute_id)
                .all()
            }
            assert {
                "DISPUTE_CREATED", "DISPUTE_ASSIGNED", "DISPUTE_ESCALATED",
                "DISPUTE_RESOLVED",
            } <= audit_types
            # Exactly one resolution: history was not rewritten.
            resolutions = (
                session.query(AuditLedgerEvent)
                .filter(
                    AuditLedgerEvent.event_type == "DISPUTE_RESOLVED",
                    AuditLedgerEvent.resource_id == dispute_id,
                )
                .count()
            )
            assert resolutions == 1
        finally:
            session.close()

        # Terminal disputes reject every workflow action.
        assert (
            client.post(f"/api/v1/disputes/{dispute_id}/start-review").status_code == 422
        )
        withdrawal = client.post(
            f"/api/v1/disputes/{dispute_id}/withdraw",
            json={"actor_id": str(initiator.id)},
        )
        assert withdrawal.status_code == 422

        # Listing filters by status and target.
        listed = client.get(
            "/api/v1/disputes",
            params={"status": "RESOLVED", "target_id": evidence["evidence_id"]},
        )
        assert listed.status_code == 200
        assert any(item["id"] == dispute_id for item in listed.json()["items"])
    finally:
        cleanup(
            [str(initiator.id), str(reviewer.id), str(escalation_target.id)],
            [project["id"]],
            [evidence["evidence_id"]],
        )


def test_upheld_dispute_invalidates_downstream_and_reprocesses():
    initiator = setup_user()
    resolver = setup_user()
    project = api_create_project(str(initiator.id))
    claim = api_create_claim(project["id"])
    evidence = api_upload(image_bytes(), f"be021-inv-{uuid4().hex[:8]}.jpg")
    link_evidence(evidence["evidence_id"], project["id"], claim["id"])
    original_job_id = process(evidence["evidence_id"])
    edge = add_graph_edge(evidence["evidence_id"], claim["id"])
    chain = add_fusion_chain(evidence["evidence_id"])
    try:
        dispute = client.post(
            "/api/v1/disputes",
            json={
                "target_type": "EVIDENCE",
                "target_id": evidence["evidence_id"],
                "reason": "location context is wrong",
                "initiator_id": str(initiator.id),
            },
        ).json()
        resolved = client.post(
            f"/api/v1/disputes/{dispute['id']}/resolve",
            json={
                "resolution": "UPHELD",
                "rationale": "challenge verified by two reviewers",
                "resolved_by": str(resolver.id),
            },
        )
        assert resolved.status_code == 200, resolved.text

        session = get_session()
        try:
            # Every downstream output is MARKED, never deleted (§13, §14).
            job = session.query(AnalysisJob).filter_by(id=original_job_id).one()
            assert job.staleness == "INVALIDATED"
            fusion = (
                session.query(FusionRun).filter_by(id=chain["fusion_run_id"]).one()
            )
            assert fusion.staleness == "INVALIDATED"
            explanation = (
                session.query(ExplanationRun)
                .filter_by(id=chain["explanation_id"])
                .one()
            )
            # Historical explanation remains available, marked invalidated.
            assert explanation.staleness == "INVALIDATED"
            assert explanation.summary == {"text": "fixture explanation"}
            assessment = (
                session.query(IntegrityAssessment)
                .filter_by(id=chain["assessment_id"])
                .one()
            )
            assert assessment.assessment_status == "INVALIDATED"
            edge_row = (
                session.query(GraphRelationship).filter_by(id=edge.id).one()
            )
            assert edge_row.relationship_status == "INVALIDATED"

            # The invalidation record captures the reach (§15).
            invalidation = (
                session.query(IntelligenceInvalidation)
                .filter_by(dispute_id=dispute["id"])
                .one()
            )
            assert invalidation.cause == "DISPUTE"
            assert invalidation.target_type == "EVIDENCE"
            assert invalidation.invalidated_by == str(resolver.id)
            assert invalidation.affected_analysis >= 1
            assert invalidation.affected_fusion >= 1
            assert invalidation.affected_explanations >= 1
            assert invalidation.affected_relationships >= 1
            assert invalidation.affected_assessments >= 1

            # Review cases are preserved, never auto-resolved, and receive a
            # dependency-changed event (§20).
            case = session.query(ReviewCase).filter_by(id=chain["case_id"]).one()
            assert case.status == "OPEN"
            case_events = (
                session.query(ReviewCaseEvent.event_type)
                .filter(ReviewCaseEvent.case_id == chain["case_id"])
                .all()
            )
            assert ("DEPENDENT_INTELLIGENCE_CHANGED",) in case_events

            # Reprocessing was delegated through BE-005: a new analysis run
            # exists and the request references it (§17).
            reprocessing = (
                session.query(ReprocessingRequest)
                .filter_by(evidence_id=evidence["evidence_id"])
                .one()
            )
            assert reprocessing.status == "PENDING"
            assert reprocessing.analysis_job_id is not None
            assert reprocessing.analysis_job_id != original_job_id
            new_job = (
                session.query(AnalysisJob)
                .filter_by(id=reprocessing.analysis_job_id)
                .one()
            )
            assert new_job.evidence_id == evidence["evidence_id"]

            # Exactly-once invalidation per dispute (§28).
            assert (
                session.query(IntelligenceInvalidation)
                .filter_by(dispute_id=dispute["id"])
                .count()
                == 1
            )
        finally:
            session.close()
    finally:
        cleanup(
            [str(initiator.id), str(resolver.id)],
            [project["id"]],
            [evidence["evidence_id"]],
        )


def test_correction_workflow_immutable_evidence_and_staleness():
    requester = setup_user()
    approver = setup_user()
    project = api_create_project(str(requester.id))
    evidence = api_upload(image_bytes(), f"be021-cor-{uuid4().hex[:8]}.jpg")
    link_evidence(evidence["evidence_id"], project["id"])
    original_job_id = process(evidence["evidence_id"])
    before = {}
    session = get_session()
    try:
        row_ = session.query(Evidence).filter_by(id=evidence["evidence_id"]).one()
        before = {
            "sha256": row_.sha256,
            "storage_key": row_.storage_key,
            "filename": row_.filename,
        }
    finally:
        session.close()
    try:
        created = client.post(
            "/api/v1/corrections",
            json={
                "target_id": evidence["evidence_id"],
                "category": "LOCATION_CONTEXT",
                "requested_change": {"latitude": 10.5, "longitude": 20.5},
                "reason": "capture location was mislabeled",
                "requester_id": str(requester.id),
            },
        )
        assert created.status_code == 201, created.text
        correction = created.json()
        assert correction["status"] == "REQUESTED"
        correction_id = correction["id"]

        # Identical retry returns the same request (§28)…
        duplicate = client.post(
            "/api/v1/corrections",
            json={
                "target_id": evidence["evidence_id"],
                "category": "LOCATION_CONTEXT",
                "requested_change": {"latitude": 10.5, "longitude": 20.5},
                "reason": "capture location was mislabeled",
                "requester_id": str(requester.id),
            },
        )
        assert duplicate.status_code == 200
        assert duplicate.json()["id"] == correction_id
        # …but a *different* active change for the same target+category by the
        # same requester is refused until the first one settles.
        conflicting = client.post(
            "/api/v1/corrections",
            json={
                "target_id": evidence["evidence_id"],
                "category": "LOCATION_CONTEXT",
                "requested_change": {"latitude": 1.5, "longitude": 2.5},
                "reason": "different location",
                "requester_id": str(requester.id),
            },
        )
        assert conflicting.status_code == 422

        # Requester cannot approve their own correction (§12).
        self_approval = client.post(
            f"/api/v1/corrections/{correction_id}/approve",
            json={"rationale": "looks right", "resolver_id": str(requester.id)},
        )
        assert self_approval.status_code == 422

        approved = client.post(
            f"/api/v1/corrections/{correction_id}/approve",
            json={"rationale": "verified against the field report", "resolver_id": str(approver.id)},
        )
        assert approved.status_code == 200, approved.text
        assert approved.json()["status"] == "APPROVED"

        applied = client.post(
            f"/api/v1/corrections/{correction_id}/apply",
            json={"applied_by": str(approver.id)},
        )
        assert applied.status_code == 200, applied.text
        assert applied.json()["status"] == "APPLIED"

        session = get_session()
        try:
            from sqlalchemy import text as sql_text

            # Mutable context changed…
            lat, lon = session.execute(
                sql_text(
                    "SELECT ST_Y(location::geometry), ST_X(location::geometry) "
                    "FROM evidence WHERE id = :id"
                ),
                {"id": evidence["evidence_id"]},
            ).one()
            assert (round(lat, 4), round(lon, 4)) == (10.5, 20.5)
            # …while evidence identity stayed immutable (§8).
            row_ = session.query(Evidence).filter_by(id=evidence["evidence_id"]).one()
            assert row_.sha256 == before["sha256"]
            assert row_.storage_key == before["storage_key"]
            assert row_.filename == before["filename"]

            # Context corrections mark downstream STALE (§14) and reprocess.
            job = session.query(AnalysisJob).filter_by(id=original_job_id).one()
            assert job.staleness == "STALE"
            invalidation = (
                session.query(IntelligenceInvalidation)
                .filter_by(correction_id=correction_id)
                .one()
            )
            assert invalidation.cause == "CORRECTION"
            assert (
                session.query(ReprocessingRequest)
                .filter_by(evidence_id=evidence["evidence_id"])
                .count()
                == 1
            )

            # Append-only history + audit twins.
            events = [
                row[0]
                for row in session.query(CorrectionEvent.event_type)
                .filter(CorrectionEvent.correction_id == correction_id)
                .order_by(CorrectionEvent.created_at)
                .all()
            ]
            assert events == ["REQUESTED", "APPROVED", "APPLIED"]
            audit_types = {
                row[0]
                for row in session.query(AuditLedgerEvent.event_type)
                .filter(AuditLedgerEvent.resource_id == correction_id)
                .all()
            }
            assert {
                "CORRECTION_REQUESTED", "CORRECTION_APPROVED", "CORRECTION_APPLIED",
            } <= audit_types
        finally:
            session.close()

        # Approving an already-applied correction is refused as an invalid
        # transition (approval and application are distinct, §10).
        reapprove = client.post(
            f"/api/v1/corrections/{correction_id}/approve",
            json={"rationale": "again", "resolver_id": str(approver.id)},
        )
        assert reapprove.status_code == 422
    finally:
        cleanup(
            [str(requester.id), str(approver.id)],
            [project["id"]],
            [evidence["evidence_id"]],
        )


def test_evidence_file_correction_supersedes_and_links_lineage():
    requester = setup_user()
    approver = setup_user()
    project = api_create_project(str(requester.id))
    old = api_upload(image_bytes((10, 20, 30)), f"be021-old-{uuid4().hex[:8]}.jpg")
    new = api_upload(image_bytes((200, 210, 220)), f"be021-new-{uuid4().hex[:8]}.jpg")
    link_evidence(old["evidence_id"], project["id"])
    old_job = process(old["evidence_id"])
    process(new["evidence_id"])
    before = {}
    session = get_session()
    try:
        row_ = session.query(Evidence).filter_by(id=old["evidence_id"]).one()
        before = {"sha256": row_.sha256, "storage_key": row_.storage_key}
    finally:
        session.close()
    try:
        correction = client.post(
            "/api/v1/corrections",
            json={
                "target_id": old["evidence_id"],
                "category": "EVIDENCE_FILE",
                "requested_change": {"new_evidence_id": new["evidence_id"]},
                "reason": "sharper capture of the same scene",
                "requester_id": str(requester.id),
            },
        ).json()
        assert (
            client.post(
                f"/api/v1/corrections/{correction['id']}/approve",
                json={"rationale": "replacement verified", "resolver_id": str(approver.id)},
            ).status_code
            == 200
        )
        applied = client.post(
            f"/api/v1/corrections/{correction['id']}/apply",
            json={"applied_by": str(approver.id)},
        )
        assert applied.status_code == 200, applied.text

        session = get_session()
        try:
            # Original evidence bytes and identity are never rewritten (§8).
            row_ = session.query(Evidence).filter_by(id=old["evidence_id"]).one()
            assert row_.sha256 == before["sha256"]
            assert row_.storage_key == before["storage_key"]

            # The new version links to the old one via a DERIVED_FROM edge
            # (new is the source), and the old chain is SUPERSEDED (§14).
            new_node = (
                session.query(GraphNode)
                .filter_by(node_type="EVIDENCE", entity_id=new["evidence_id"])
                .one()
            )
            old_node = (
                session.query(GraphNode)
                .filter_by(node_type="EVIDENCE", entity_id=old["evidence_id"])
                .one()
            )
            lineage = (
                session.query(GraphRelationship)
                .filter_by(
                    source_node_id=new_node.id,
                    target_node_id=old_node.id,
                    relationship_type="DERIVED_FROM",
                )
                .one()
            )
            assert lineage.relationship_status == "ACTIVE"
            assert lineage.provenance["correction_id"] == correction["id"]

            old_job_row = session.query(AnalysisJob).filter_by(id=old_job).one()
            assert old_job_row.staleness == "SUPERSEDED"

            # File replacements do not reprocess the superseded evidence
            # (§17); the new version carries its own fresh analysis.
            assert (
                session.query(ReprocessingRequest)
                .filter_by(evidence_id=old["evidence_id"])
                .count()
                == 0
            )
            invalidation = (
                session.query(IntelligenceInvalidation)
                .filter_by(correction_id=correction["id"])
                .one()
            )
            assert invalidation.affected_analysis >= 1

            # Idempotent re-apply: same record, no duplicate lineage edge.
            again = client.post(
                f"/api/v1/corrections/{correction['id']}/apply",
                json={"applied_by": str(approver.id)},
            )
            assert again.status_code == 200
            assert again.json()["id"] == correction["id"]
            assert (
                session.query(GraphRelationship)
                .filter(
                    GraphRelationship.source_node_id == new_node.id,
                    GraphRelationship.relationship_type == "DERIVED_FROM",
                )
                .count()
                == 1
            )
            assert (
                session.query(IntelligenceInvalidation)
                .filter_by(correction_id=correction["id"])
                .count()
                == 1
            )
        finally:
            session.close()
    finally:
        cleanup(
            [str(requester.id), str(approver.id)],
            [project["id"]],
            [old["evidence_id"], new["evidence_id"]],
        )


# ---------------------------------------------------------------------------
# Dependency inspection (§16) and reprocessing (§17)
# ---------------------------------------------------------------------------


def test_dependencies_endpoint_reports_bounded_graph():
    requester = setup_user()
    project = api_create_project(str(requester.id))
    claim = api_create_claim(project["id"])
    evidence = api_upload(image_bytes(), f"be021-dep-{uuid4().hex[:8]}.jpg")
    link_evidence(evidence["evidence_id"], project["id"], claim["id"])
    _, analysis = process_with_analysis(evidence["evidence_id"])
    add_graph_edge(evidence["evidence_id"], claim["id"])
    chain = add_fusion_chain(evidence["evidence_id"])
    try:
        # BE-023 §8: the ANALYSIS_RESULT node below depends on the CLIP
        # embedding branch having actually run. analyze_duplicates creates
        # that row *inside* the branch that calls image_embedding, and
        # swallows any failure into DuplicateAnalysis.embedding_error -- so
        # when the ML stack is unavailable there is no AnalysisResult for the
        # graph to traverse, and this assertion would fail for an
        # environmental reason that has nothing to do with governance.
        #
        # The skip is therefore tied to the observed embedding outcome, not
        # to convenience. When ML is available the branch succeeds and every
        # assertion below -- including ANALYSIS_RESULT -- runs unchanged.
        if analysis.embedding_status != "success":
            from tests.preflight import classify_ml

            ml_state = classify_ml()
            pytest.skip(
                f"{ml_state.describe()} | CLIP embedding did not succeed "
                f"(embedding_status={analysis.embedding_status!r}, "
                f"embedding_error={analysis.embedding_error!r}); no AnalysisResult "
                "row exists, so the ANALYSIS_RESULT dependency node cannot be "
                "traversed. This is an ML precondition, not a governance failure."
            )

        response = client.get(
            f"/api/v1/governance/EVIDENCE/{evidence['evidence_id']}/dependencies"
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["target_type"] == "EVIDENCE"
        assert body["truncated"] is False
        kinds = [node["kind"] for node in body["nodes"]]
        assert kinds[0] == "EVIDENCE"
        assert body["nodes"][0]["depth"] == 0
        assert "ANALYSIS_JOB" in kinds
        assert "ANALYSIS_RESULT" in kinds
        assert "FUSION_RUN" in kinds
        assert "GRAPH_RELATIONSHIP" in kinds
        assert "EXPLANATION_RUN" in kinds
        assert "INTEGRITY_ASSESSMENT" in kinds
        assert "REVIEW_CASE" in kinds
        assert body["counts"]["ANALYSIS_JOB"] >= 1
        assert body["counts"]["FUSION_RUN"] >= 1
        # Depth increases monotonically away from the target.
        depths = [node["depth"] for node in body["nodes"]]
        assert depths == sorted(depths)
        by_kind = {node["kind"]: node for node in body["nodes"]}
        assert by_kind["FUSION_RUN"]["depth"] > by_kind["EVIDENCE"]["depth"]

        # Bounds are honored and honestly reported (§16).
        shallow = client.get(
            f"/api/v1/governance/EVIDENCE/{evidence['evidence_id']}/dependencies",
            params={"max_depth": 1},
        ).json()
        assert all(node["depth"] <= 1 for node in shallow["nodes"])
        tight = client.get(
            f"/api/v1/governance/EVIDENCE/{evidence['evidence_id']}/dependencies",
            params={"max_nodes": 1},
        ).json()
        assert len(tight["nodes"]) == 1
        assert tight["truncated"] is True

        # Error contracts.
        assert (
            client.get(
                f"/api/v1/governance/EVIDENCE/{uuid4()}/dependencies"
            ).status_code
            == 404
        )
        assert (
            client.get(
                f"/api/v1/governance/EVIDENCE/{evidence['evidence_id']}/dependencies",
                params={"max_depth": 11},
            ).status_code
            == 422
        )
        assert (
            client.get(
                f"/api/v1/governance/PLANET/{evidence['evidence_id']}/dependencies"
            ).status_code
            == 422
        )
    finally:
        cleanup([str(requester.id)], [project["id"]], [evidence["evidence_id"]])


def test_reprocessing_idempotent_delegation_and_completion():
    requester = setup_user()
    project = api_create_project(str(requester.id))
    evidence = api_upload(image_bytes(), f"be021-rep-{uuid4().hex[:8]}.jpg")
    link_evidence(evidence["evidence_id"], project["id"])
    original_job = process(evidence["evidence_id"])
    try:
        first = client.post(
            f"/api/v1/governance/EVIDENCE/{evidence['evidence_id']}/reprocess",
            json={"reason": "intelligence invalidated", "requested_by": str(requester.id)},
        )
        assert first.status_code == 201, first.text
        assert first.json()["result"] == "REPROCESSING_REQUESTED"
        request_id = first.json()["reprocessing_request_id"]
        assert first.json()["analysis_job_id"] is not None
        assert first.json()["analysis_job_id"] != original_job

        # Duplicate request while PENDING returns the same request (§28).
        second = client.post(
            f"/api/v1/governance/EVIDENCE/{evidence['evidence_id']}/reprocess",
            json={"reason": "retry", "requested_by": str(requester.id)},
        )
        assert second.status_code == 200
        assert second.json()["result"] == "REPROCESSING_ALREADY_PENDING"
        assert second.json()["reprocessing_request_id"] == request_id

        # The delegation created a new analysis run through BE-005.
        session = get_session()
        try:
            new_job = (
                session.query(AnalysisJob)
                .filter_by(id=first.json()["analysis_job_id"])
                .one()
            )
            assert new_job.evidence_id == evidence["evidence_id"]
        finally:
            session.close()

        # Worker-hook completion is idempotent (§17): the request flips to
        # COMPLETED exactly once, with audit + notification twins.
        session = get_session()
        try:
            governance_service.complete_reprocessing(
                session, analysis_job_id=first.json()["analysis_job_id"]
            )
            completed = (
                session.query(ReprocessingRequest).filter_by(id=request_id).one()
            )
            assert completed.status == "COMPLETED"
            # Idempotent second completion does not duplicate state.
            governance_service.complete_reprocessing(
                session, analysis_job_id=first.json()["analysis_job_id"]
            )
            assert (
                session.query(AuditLedgerEvent)
                .filter(
                    AuditLedgerEvent.event_type == "INTELLIGENCE_REPROCESS_COMPLETED",
                    AuditLedgerEvent.resource_id == request_id,
                )
                .count()
                == 1
            )
            assert (
                session.query(NotificationOutbox)
                .filter(
                    NotificationOutbox.event_type == "REPROCESSING_COMPLETED",
                    NotificationOutbox.aggregate_id == request_id,
                )
                .count()
                == 1
            )
        finally:
            session.close()

        # After completion a new request is legitimate again.
        third = client.post(
            f"/api/v1/governance/EVIDENCE/{evidence['evidence_id']}/reprocess",
            json={"reason": "second cycle", "requested_by": str(requester.id)},
        )
        assert third.status_code == 201
        assert third.json()["reprocessing_request_id"] != request_id

        # Reprocessing only applies to evidence (§17).
        rejected = client.post(
            f"/api/v1/governance/CLAIM/{project['id']}/reprocess",
            json={"reason": "not evidence", "requested_by": str(requester.id)},
        )
        assert rejected.status_code == 422
        assert (
            client.post(
                f"/api/v1/governance/EVIDENCE/{uuid4()}/reprocess",
                json={"reason": "missing", "requested_by": str(requester.id)},
            ).status_code
            == 404
        )
    finally:
        cleanup([str(requester.id)], [project["id"]], [evidence["evidence_id"]])


# ---------------------------------------------------------------------------
# Concurrency (§29)
# ---------------------------------------------------------------------------


def test_concurrent_resolution_yields_single_outcome():
    initiator = setup_user()
    resolver_a = setup_user()
    resolver_b = setup_user()
    project = api_create_project(str(initiator.id))
    evidence = api_upload(image_bytes(), f"be021-race-{uuid4().hex[:8]}.jpg")
    link_evidence(evidence["evidence_id"], project["id"])
    dispute = client.post(
        "/api/v1/disputes",
        json={
            "target_type": "EVIDENCE",
            "target_id": evidence["evidence_id"],
            "reason": "concurrent adjudication race",
            "initiator_id": str(initiator.id),
        },
    ).json()
    outcomes: list = []
    barrier = threading.Barrier(2)

    def resolve(user, resolution):
        barrier.wait()
        response = client.post(
            f"/api/v1/disputes/{dispute['id']}/resolve",
            json={
                "resolution": resolution,
                "rationale": f"adjudicated by {resolution}",
                "resolved_by": str(user.id),
            },
        )
        outcomes.append(response.status_code)

    try:
        threads = [
            threading.Thread(target=resolve, args=(resolver_a, "UPHELD")),
            threading.Thread(target=resolve, args=(resolver_b, "REJECTED")),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        # Exactly one adjudication wins; the loser sees a 422 conflict.
        assert sorted(outcomes) == [200, 422]
        session = get_session()
        try:
            row_ = session.query(Dispute).filter_by(id=dispute["id"]).one()
            assert row_.status == "RESOLVED"
            assert row_.resolution in ("UPHELD", "REJECTED")
            assert (
                session.query(AuditLedgerEvent)
                .filter(
                    AuditLedgerEvent.event_type == "DISPUTE_RESOLVED",
                    AuditLedgerEvent.resource_id == dispute["id"],
                )
                .count()
                == 1
            )
            invalidations = (
                session.query(IntelligenceInvalidation)
                .filter_by(dispute_id=dispute["id"])
                .count()
            )
            assert invalidations == (1 if row_.resolution == "UPHELD" else 0)
        finally:
            session.close()
    finally:
        cleanup(
            [str(initiator.id), str(resolver_a.id), str(resolver_b.id)],
            [project["id"]],
            [evidence["evidence_id"]],
        )


def test_concurrent_correction_application_single_invalidation():
    requester = setup_user()
    approver = setup_user()
    project = api_create_project(str(requester.id))
    evidence = api_upload(image_bytes(), f"be021-app-{uuid4().hex[:8]}.jpg")
    link_evidence(evidence["evidence_id"], project["id"])
    correction = client.post(
        "/api/v1/corrections",
        json={
            "target_id": evidence["evidence_id"],
            "category": "DESCRIPTIVE_FIELD",
            "requested_change": {"filename": "renamed.jpg"},
            "reason": "typo in filename",
            "requester_id": str(requester.id),
        },
    ).json()
    assert (
        client.post(
            f"/api/v1/corrections/{correction['id']}/approve",
            json={"rationale": "approved for application", "resolver_id": str(approver.id)},
        ).status_code
        == 200
    )
    barrier = threading.Barrier(2)
    results: list = []

    def apply():
        barrier.wait()
        response = client.post(
            f"/api/v1/corrections/{correction['id']}/apply",
            json={"applied_by": str(approver.id)},
        )
        results.append(response.status_code)

    try:
        threads = [threading.Thread(target=apply) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        # Application is idempotent: both callers observe success.
        assert results == [200, 200]
        session = get_session()
        try:
            row_ = (
                session.query(CorrectionRequest)
                .filter_by(id=correction["id"])
                .one()
            )
            assert row_.status == "APPLIED"
            # Exactly-once downstream effects (§28, §29).
            assert (
                session.query(IntelligenceInvalidation)
                .filter_by(correction_id=correction["id"])
                .count()
                == 1
            )
            assert (
                session.query(ReprocessingRequest)
                .filter_by(evidence_id=evidence["evidence_id"])
                .count()
                == 1
            )
            applied_events = (
                session.query(CorrectionEvent)
                .filter(
                    CorrectionEvent.correction_id == correction["id"],
                    CorrectionEvent.event_type == "APPLIED",
                )
                .count()
            )
            assert applied_events == 1
        finally:
            session.close()
    finally:
        cleanup(
            [str(requester.id), str(approver.id)],
            [project["id"]],
            [evidence["evidence_id"]],
        )


# ---------------------------------------------------------------------------
# Role separation (§12) and authorization isolation (§11, §34)
# ---------------------------------------------------------------------------


def test_role_separation_via_api():
    citizen = setup_user()
    supervisor = setup_user()
    project = api_create_project(str(citizen.id))
    evidence = api_upload(image_bytes(), f"be021-roles-{uuid4().hex[:8]}.jpg")
    link_evidence(evidence["evidence_id"], project["id"])
    assign(str(citizen.id), "CITIZEN", "PROJECT", project["id"])
    assign(str(supervisor.id), "SUPERVISOR", "PROJECT", project["id"])
    citizen_headers = headers_for(str(citizen.id))
    supervisor_headers = headers_for(str(supervisor.id))
    try:
        # The citizen initiates a dispute within their project scope.
        created = client.post(
            "/api/v1/disputes",
            json={
                "target_type": "EVIDENCE",
                "target_id": evidence["evidence_id"],
                "reason": "citizen challenge",
            },
            headers=citizen_headers,
        )
        assert created.status_code == 201, created.text
        dispute = created.json()
        assert dispute["initiator_id"] == str(citizen.id)

        # The initiator cannot review or resolve it (no permission, and the
        # service additionally blocks initiator self-adjudication).
        assert (
            client.post(
                f"/api/v1/disputes/{dispute['id']}/start-review",
                headers=citizen_headers,
            ).status_code
            == 403
        )
        assert (
            client.post(
                f"/api/v1/disputes/{dispute['id']}/resolve",
                json={"resolution": "UPHELD", "rationale": "self-adjudication"},
                headers=citizen_headers,
            ).status_code
            == 403
        )

        # A role-separated supervisor reviews and resolves.
        assert (
            client.post(
                f"/api/v1/disputes/{dispute['id']}/start-review",
                headers=supervisor_headers,
            ).status_code
            == 200
        )
        resolved = client.post(
            f"/api/v1/disputes/{dispute['id']}/resolve",
            json={"resolution": "UPHELD", "rationale": "challenge accepted"},
            headers=supervisor_headers,
        )
        assert resolved.status_code == 200, resolved.text
        assert resolved.json()["resolved_by"] == str(supervisor.id)

        # The initiator cannot withdraw someone else's dispute… (this one is
        # theirs, so withdrawal of an ACTIVE dispute is the initiator's
        # right — verified on a fresh dispute below).
        second = client.post(
            "/api/v1/disputes",
            json={
                "target_type": "EVIDENCE",
                "target_id": evidence["evidence_id"],
                "reason": "second citizen challenge",
            },
            headers=citizen_headers,
        ).json()
        # The supervisor did not initiate it, so they cannot withdraw it.
        assert (
            client.post(
                f"/api/v1/disputes/{second['id']}/withdraw",
                headers=supervisor_headers,
            ).status_code
            == 422
        )
        withdrawn = client.post(
            f"/api/v1/disputes/{second['id']}/withdraw", headers=citizen_headers
        )
        assert withdrawn.status_code == 200
        assert withdrawn.json()["status"] == "WITHDRAWN"

        # A supervisor who initiates a dispute cannot resolve it themselves
        # even though they hold dispute.resolve (§12 substantive rule).
        own = client.post(
            "/api/v1/disputes",
            json={
                "target_type": "EVIDENCE",
                "target_id": evidence["evidence_id"],
                "reason": "supervisor's own challenge",
            },
            headers=supervisor_headers,
        ).json()
        assert (
            client.post(
                f"/api/v1/disputes/{own['id']}/resolve",
                json={"resolution": "REJECTED", "rationale": "own dispute"},
                headers=supervisor_headers,
            ).status_code
            == 422
        )

        # Correction role separation: the citizen requester lacks the
        # approval permission entirely (403)…
        correction = client.post(
            "/api/v1/corrections",
            json={
                "target_id": evidence["evidence_id"],
                "category": "DESCRIPTIVE_FIELD",
                "requested_change": {"filename": "citizen-fix.jpg"},
                "reason": "typo",
            },
            headers=citizen_headers,
        ).json()
        assert (
            client.post(
                f"/api/v1/corrections/{correction['id']}/approve",
                json={"rationale": "self approval attempt"},
                headers=citizen_headers,
            ).status_code
            == 403
        )
        # …and a requester who *holds* the approval permission still cannot
        # approve their own request (§12 substantive rule -> 422).
        own_correction = client.post(
            "/api/v1/corrections",
            json={
                "target_id": evidence["evidence_id"],
                "category": "DESCRIPTIVE_FIELD",
                "requested_change": {"filename": "supervisor-fix.jpg"},
                "reason": "supervisor's own correction",
            },
            headers=supervisor_headers,
        ).json()
        assert (
            client.post(
                f"/api/v1/corrections/{own_correction['id']}/approve",
                json={"rationale": "self approval attempt"},
                headers=supervisor_headers,
            ).status_code
            == 422
        )
        approved = client.post(
            f"/api/v1/corrections/{correction['id']}/approve",
            json={"rationale": "approved by supervisor"},
            headers=supervisor_headers,
        )
        assert approved.status_code == 200
        # The requester cannot apply either (no permission and §12 rule).
        assert (
            client.post(
                f"/api/v1/corrections/{correction['id']}/apply",
                headers=citizen_headers,
            ).status_code
            == 403
        )
        applied = client.post(
            f"/api/v1/corrections/{correction['id']}/apply",
            headers=supervisor_headers,
        )
        assert applied.status_code == 200
    finally:
        cleanup(
            [str(citizen.id), str(supervisor.id)],
            [project["id"]],
            [evidence["evidence_id"]],
        )


def test_authorization_isolation_across_projects():
    owner_a = setup_user()
    supervisor_a = setup_user()
    owner_b = setup_user()
    supervisor_b = setup_user()
    # §12 keeps the dispute initiator out of the review, and #214 derives that
    # initiator from the credential, so project B needs two humans: one to
    # raise the dispute and one to review it.
    reviewer_b = setup_user()
    administrator = setup_user()
    project_a = api_create_project(str(owner_a.id), "BE-021 project A")
    project_b = api_create_project(str(owner_b.id), "BE-021 project B")
    evidence_a = api_upload(image_bytes(), f"be021-iso-a-{uuid4().hex[:8]}.jpg")
    evidence_b = api_upload(image_bytes((5, 5, 5)), f"be021-iso-b-{uuid4().hex[:8]}.jpg")
    link_evidence(evidence_a["evidence_id"], project_a["id"])
    link_evidence(evidence_b["evidence_id"], project_b["id"])
    process(evidence_b["evidence_id"])
    assign(str(supervisor_a.id), "SUPERVISOR", "PROJECT", project_a["id"])
    assign(str(supervisor_b.id), "SUPERVISOR", "PROJECT", project_b["id"])
    assign(str(reviewer_b.id), "REVIEWER", "PROJECT", project_b["id"])
    assign(str(administrator.id), "ADMINISTRATOR", "GLOBAL", None)
    headers_a = headers_for(str(supervisor_a.id))
    headers_b = headers_for(str(supervisor_b.id))
    headers_reviewer_b = headers_for(str(reviewer_b.id))
    headers_admin = headers_for(str(administrator.id))
    try:
        dispute_a = client.post(
            "/api/v1/disputes",
            json={
                "target_type": "EVIDENCE",
                "target_id": evidence_a["evidence_id"],
                "reason": "challenge inside project A",
            },
            headers=headers_a,
        ).json()
        dispute_b = client.post(
            "/api/v1/disputes",
            json={
                "target_type": "EVIDENCE",
                "target_id": evidence_b["evidence_id"],
                "reason": "challenge inside project B",
                # No initiator_id: §12 forbids the dispute initiator from
                # reviewing it, and #214 derives the initiator from the
                # credential, so reviewer_b raises it and supervisor_b reviews.
            },
            headers=headers_reviewer_b,
        ).json()
        assert dispute_b["initiator_id"] == str(reviewer_b.id)

        # Out-of-scope resources are indistinguishable from absent (404).
        assert (
            client.get(
                f"/api/v1/disputes/{dispute_b['id']}", headers=headers_a
            ).status_code
            == 404
        )
        assert (
            client.get(
                f"/api/v1/governance/EVIDENCE/{evidence_b['evidence_id']}/dependencies",
                headers=headers_a,
            ).status_code
            == 404
        )
        assert (
            client.post(
                f"/api/v1/governance/EVIDENCE/{evidence_b['evidence_id']}/invalidate",
                json={"reason": "cross-project attempt"},
                headers=headers_a,
            ).status_code
            == 404
        )
        # Creating a dispute on another project's evidence is scope-denied.
        assert (
            client.post(
                "/api/v1/disputes",
                json={
                    "target_type": "EVIDENCE",
                    "target_id": evidence_b["evidence_id"],
                    "reason": "out of scope dispute",
                },
                headers=headers_a,
            ).status_code
            == 404
        )

        # Listings only show in-scope disputes.
        listed_a = client.get("/api/v1/disputes", headers=headers_a).json()
        listed_ids = {item["id"] for item in listed_a["items"]}
        assert dispute_a["id"] in listed_ids
        assert dispute_b["id"] not in listed_ids

        # The B supervisor can act inside their own project…
        assert (
            client.post(
                f"/api/v1/disputes/{dispute_b['id']}/start-review", headers=headers_b
            ).status_code
            == 200
        )
        # …and the A supervisor still cannot touch it.
        assert (
            client.post(
                f"/api/v1/disputes/{dispute_b['id']}/start-review", headers=headers_a
            ).status_code
            == 404
        )

        # Administrators read governance globally but hold no substantive
        # decision rights (§12: admins are not decision-makers).
        assert (
            client.get(
                f"/api/v1/disputes/{dispute_a['id']}", headers=headers_admin
            ).status_code
            == 200
        )
        assert (
            client.post(
                f"/api/v1/disputes/{dispute_a['id']}/resolve",
                json={"resolution": "UPHELD", "rationale": "admin override attempt"},
                headers=headers_admin,
            ).status_code
            == 403
        )
        assert (
            client.post(
                f"/api/v1/governance/EVIDENCE/{evidence_a['evidence_id']}/invalidate",
                json={"reason": "admin invalidation attempt"},
                headers=headers_admin,
            ).status_code
            == 403
        )
    finally:
        cleanup(
            [str(owner_a.id), str(supervisor_a.id), str(owner_b.id),
             str(supervisor_b.id), str(reviewer_b.id), str(administrator.id)],
            [project_a["id"], project_b["id"]],
            [evidence_a["evidence_id"], evidence_b["evidence_id"]],
        )


# ---------------------------------------------------------------------------
# Retention (§26), external assertions (§25), notifications (§24),
# sensitive-data protection (§34), and telemetry (§33)
# ---------------------------------------------------------------------------


def test_retention_hold_survives_invalidation():
    requester = setup_user()
    resolver = setup_user()
    project = api_create_project(str(requester.id))
    evidence = api_upload(image_bytes(), f"be021-hold-{uuid4().hex[:8]}.jpg")
    link_evidence(evidence["evidence_id"], project["id"])
    process(evidence["evidence_id"])
    session = get_session()
    try:
        hold = retention_service.create_hold(
            session,
            scope="RESOURCE",
            reason="under legal review",
            resource_type="EVIDENCE",
            resource_id=evidence["evidence_id"],
            created_by=str(requester.id),
        )
        session.commit()
        hold_id = str(hold.id)
    finally:
        session.close()
    try:
        dispute = client.post(
            "/api/v1/disputes",
            json={
                "target_type": "EVIDENCE",
                "target_id": evidence["evidence_id"],
                "reason": "challenged while held",
                "initiator_id": str(requester.id),
            },
        ).json()
        resolved = client.post(
            f"/api/v1/disputes/{dispute['id']}/resolve",
            json={
                "resolution": "UPHELD",
                "rationale": "upheld under hold",
                "resolved_by": str(resolver.id),
            },
        )
        assert resolved.status_code == 200, resolved.text

        session = get_session()
        try:
            # Governance marked intelligence and reprocessed — but the held
            # evidence and the hold itself were preserved (§26).
            evidence_row = (
                session.query(Evidence).filter_by(id=evidence["evidence_id"]).one()
            )
            assert evidence_row is not None
            hold_row = session.query(RetentionHold).filter_by(id=hold_id).one()
            assert hold_row.status == "ACTIVE"
            job = (
                session.query(AnalysisJob)
                .filter(AnalysisJob.evidence_id == evidence["evidence_id"])
                .first()
            )
            assert job.staleness == "INVALIDATED"
            assert (
                session.query(ReprocessingRequest)
                .filter_by(evidence_id=evidence["evidence_id"])
                .count()
                == 1
            )
        finally:
            session.close()
    finally:
        cleanup(
            [str(requester.id), str(resolver.id)],
            [project["id"]],
            [evidence["evidence_id"]],
        )


def test_external_assertion_dispute_records_without_mutating_source():
    requester = setup_user()
    resolver = setup_user()
    session = get_session()
    try:
        system = ExternalSystem(
            name="Portal", code=f"be021-portal-{uuid4().hex[:6]}",
            system_type="GOVERNMENT_PORTAL",
        )
        session.add(system)
        session.flush()
        assertion = ExternalAssertion(
            external_system_id=system.id,
            resource_type="EVIDENCE",
            payload={"official_status": "VERIFIED"},
        )
        session.add(assertion)
        session.commit()
        assertion_id = str(assertion.id)
        system_id = str(system.id)
    finally:
        session.close()
    try:
        dispute = client.post(
            "/api/v1/disputes",
            json={
                "target_type": "EXTERNAL_ASSERTION",
                "target_id": assertion_id,
                "reason": "assertion conflicts with local evidence",
                "initiator_id": str(requester.id),
            },
        )
        assert dispute.status_code == 201, dispute.text
        resolved = client.post(
            f"/api/v1/disputes/{dispute.json()['id']}/resolve",
            json={
                "resolution": "UPHELD",
                "rationale": "external assertion disputed",
                "resolved_by": str(resolver.id),
            },
        )
        assert resolved.status_code == 200, resolved.text

        session = get_session()
        try:
            # The invalidation is recorded locally (§25)…
            invalidation = (
                session.query(IntelligenceInvalidation)
                .filter_by(dispute_id=dispute.json()["id"])
                .one()
            )
            assert invalidation.target_type == "EXTERNAL_ASSERTION"
            assert invalidation.affected_analysis == 0
            # …and the external source record is never mutated.
            assertion_row = (
                session.query(ExternalAssertion).filter_by(id=assertion_id).one()
            )
            assert assertion_row.payload == {"official_status": "VERIFIED"}
        finally:
            session.close()

        # A fusion-assessment dispute marks the derived intelligence itself.
        chain_evidence = api_upload(image_bytes(), f"be021-fa-{uuid4().hex[:8]}.jpg")
        project = api_create_project(str(requester.id))
        link_evidence(chain_evidence["evidence_id"], project["id"])
        chain = add_fusion_chain(chain_evidence["evidence_id"])
        assessment_dispute = client.post(
            "/api/v1/disputes",
            json={
                "target_type": "FUSION_ASSESSMENT",
                "target_id": chain["assessment_id"],
                "reason": "assessment is wrong",
                "initiator_id": str(requester.id),
            },
        ).json()
        resolved_assessment = client.post(
            f"/api/v1/disputes/{assessment_dispute['id']}/resolve",
            json={
                "resolution": "UPHELD",
                "rationale": "assessment disputed successfully",
                "resolved_by": str(resolver.id),
            },
        )
        assert resolved_assessment.status_code == 200
        session = get_session()
        try:
            assessment = (
                session.query(IntegrityAssessment)
                .filter_by(id=chain["assessment_id"])
                .one()
            )
            assert assessment.assessment_status == "INVALIDATED"
        finally:
            session.close()
        cleanup(
            [str(requester.id)],
            [project["id"]],
            [chain_evidence["evidence_id"]],
            extra_target_ids=[chain["assessment_id"]],
        )
    finally:
        cleanup(
            [str(requester.id), str(resolver.id)],
            [],
            [],
            system_ids=[system_id],
            extra_target_ids=[assertion_id],
        )


def collect_keys(value, keys):
    if isinstance(value, dict):
        for key, item in value.items():
            keys.add(key)
            collect_keys(item, keys)
    elif isinstance(value, list):
        for item in value:
            collect_keys(item, keys)


def test_governance_responses_expose_no_evidence_content():
    requester = setup_user()
    resolver = setup_user()
    project = api_create_project(str(requester.id))
    claim = api_create_claim(project["id"])
    evidence = api_upload(image_bytes(), f"be021-safe-{uuid4().hex[:8]}.jpg")
    link_evidence(evidence["evidence_id"], project["id"], claim["id"])
    process(evidence["evidence_id"])
    try:
        dispute = client.post(
            "/api/v1/disputes",
            json={
                "target_type": "EVIDENCE",
                "target_id": evidence["evidence_id"],
                "reason": "challenge for payload inspection",
                "initiator_id": str(requester.id),
            },
        ).json()
        correction = client.post(
            "/api/v1/corrections",
            json={
                "target_id": evidence["evidence_id"],
                "category": "CONTEXTUAL_METADATA",
                "requested_change": {"metadata": {"note": "context note"}},
                "reason": "missing context",
                "requester_id": str(requester.id),
            },
        ).json()

        forbidden = {
            "sha256", "storage_key", "content", "bytes", "data", "data_url",
            "base64", "thumbnail", "exif", "file_content", "payload_bytes",
            "checksum",
        }
        responses = [
            client.get(f"/api/v1/disputes/{dispute['id']}"),
            client.get("/api/v1/disputes"),
            client.get(f"/api/v1/disputes/{dispute['id']}/history"),
            client.get(f"/api/v1/corrections/{correction['id']}"),
            client.get("/api/v1/corrections"),
            client.get(f"/api/v1/corrections/{correction['id']}/history"),
            client.get(
                f"/api/v1/governance/EVIDENCE/{evidence['evidence_id']}/dependencies"
            ),
        ]
        keys: set = set()
        for response in responses:
            assert response.status_code == 200, response.text
            collect_keys(response.json(), keys)
        assert keys & forbidden == set(), keys & forbidden

        # Notification payloads carry reference IDs only (§24).
        session = get_session()
        try:
            outbox = (
                session.query(NotificationOutbox)
                .filter(
                    NotificationOutbox.aggregate_id == dispute["id"],
                    NotificationOutbox.event_type == "DISPUTE_CREATED",
                )
                .one()
            )
            payload_keys = set(outbox.payload.keys())
            assert payload_keys <= {
                "dispute_id", "project_id", "target_type", "target_id",
                "status", "resource_type", "resource_id",
                "assigned_to", "escalated_to", "resolution", "recipients",
            }
            # The human-written reason text never leaks into notifications.
            assert "challenge for payload inspection" not in str(outbox.payload)
        finally:
            session.close()
    finally:
        cleanup(
            [str(requester.id), str(resolver.id)],
            [project["id"]],
            [evidence["evidence_id"]],
        )


def test_telemetry_counters_recorded():
    if governance_metrics.disputes_created_total is None:
        import pytest

        pytest.skip("prometheus client unavailable or telemetry disabled")
    from prometheus_client import REGISTRY

    requester = setup_user()
    project = api_create_project(str(requester.id))
    evidence = api_upload(image_bytes(), f"be021-tel-{uuid4().hex[:8]}.jpg")
    link_evidence(evidence["evidence_id"], project["id"])
    try:
        before = REGISTRY.get_sample_value("disputes_created_total") or 0
        created = client.post(
            "/api/v1/disputes",
            json={
                "target_type": "EVIDENCE",
                "target_id": evidence["evidence_id"],
                "reason": "telemetry probe",
                "initiator_id": str(requester.id),
            },
        )
        assert created.status_code == 201
        after = REGISTRY.get_sample_value("disputes_created_total") or 0
        assert after == before + 1

        correction = client.post(
            "/api/v1/corrections",
            json={
                "target_id": evidence["evidence_id"],
                "category": "DESCRIPTIVE_FIELD",
                "requested_change": {"filename": "tel.jpg"},
                "reason": "telemetry probe",
                "requester_id": str(requester.id),
            },
        )
        assert correction.status_code == 201
        correction_before = (
            REGISTRY.get_sample_value(
                "correction_requests_total", {"category": "DESCRIPTIVE_FIELD"}
            )
            or 0
        )
        # Bounded-label fallback: an out-of-vocabulary value still records
        # under a closed label instead of raising.
        governance_metrics.record_invalidation("MYSTERY_CAUSE")
        assert (
            REGISTRY.get_sample_value(
                "intelligence_invalidations_total", {"cause": "DIRECT"}
            )
            is not None
        )
        assert correction_before >= 1
    finally:
        cleanup([str(requester.id)], [project["id"]], [evidence["evidence_id"]])
