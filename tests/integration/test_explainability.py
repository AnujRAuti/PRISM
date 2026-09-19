"""BE-012 integration tests against real PostgreSQL infrastructure."""

import json
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
    Claim,
    DuplicateMatch,
    Evidence,
    EvidenceMetadata,
    ExplanationRun,
    FusionRun,
    FusionSignal,
    GraphNode,
    GraphRelationship,
    IntegrityAssessment,
    Project,
    ReviewPriority,
    User,
    VisionDetection,
)
from backend.db.session import get_session
from backend.services.storage import StorageService


client = TestClient(app)


def image_bytes(color=(60, 130, 200)) -> bytes:
    output = BytesIO()
    Image.new("RGB", (16, 16), color=color).save(output, format="JPEG")
    return output.getvalue()


def setup_user() -> User:
    session = get_session()
    user = User(username=f"be012-{uuid4()}", email=f"{uuid4()}@example.com")
    session.add(user)
    session.commit()
    session.refresh(user)
    session.close()
    return user


def api_create_project(user_id: str, name: str = "BE-012 project") -> dict:
    response = client.post("/api/v1/projects", json={"name": name, "owner_id": user_id})
    assert response.status_code == 201
    return response.json()


def api_create_claim(project_id: str) -> dict:
    response = client.post(
        f"/api/v1/projects/{project_id}/claims",
        json={"title": "BE-012 claim", "description": "explanation test"},
    )
    assert response.status_code == 201
    return response.json()


def api_upload(data: bytes, filename: str) -> dict:
    response = client.post("/api/v1/evidence", files={"file": (filename, data, "image/jpeg")})
    assert response.status_code == 201
    return response.json()


def api_edge(source_type, source_id, target_type, target_id, rel_type, provenance=None):
    return client.post(
        "/api/v1/graph/relationships",
        json={
            "source": {"node_type": source_type, "entity_id": source_id},
            "target": {"node_type": target_type, "entity_id": target_id},
            "relationship_type": rel_type,
            "provenance": provenance or {"source": "human_review", "method": "manual_link"},
        },
    )


def link_evidence(evidence_id: str, project_id: str, claim_id: str | None = None) -> None:
    session = get_session()
    try:
        evidence = session.query(Evidence).filter_by(id=evidence_id).one()
        evidence.project_id = project_id
        evidence.claim_id = claim_id
        session.commit()
    finally:
        session.close()


def cleanup(user_id, project_ids, evidence_ids) -> None:
    storage = StorageService()
    session = get_session()
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
        claim_ids = [
            row[0] for row in session.query(Claim.id).filter(Claim.project_id.in_(project_ids)).all()
        ]
        run_ids = [
            row[0]
            for row in session.query(FusionRun.id)
            .filter(FusionRun.target_id.in_(claim_ids + evidence_ids))
            .all()
        ]
        if run_ids:
            session.query(ExplanationRun).filter(ExplanationRun.fusion_run_id.in_(run_ids)).delete(
                synchronize_session=False
            )
            session.query(FusionSignal).filter(FusionSignal.fusion_run_id.in_(run_ids)).delete(
                synchronize_session=False
            )
            session.query(IntegrityAssessment).filter(
                IntegrityAssessment.fusion_run_id.in_(run_ids)
            ).delete(synchronize_session=False)
            session.query(ReviewPriority).filter(ReviewPriority.fusion_run_id.in_(run_ids)).delete(
                synchronize_session=False
            )
            session.query(FusionRun).filter(FusionRun.id.in_(run_ids)).delete(synchronize_session=False)
        job_ids = [
            row[0]
            for row in session.query(AnalysisJob.id).filter(AnalysisJob.evidence_id.in_(evidence_ids)).all()
        ]
        entity_ids = list(evidence_ids) + list(project_ids) + claim_ids + job_ids
        if job_ids:
            entity_ids.extend(
                row[0]
                for row in session.query(AnalysisResult.id).filter(AnalysisResult.job_id.in_(job_ids)).all()
            )
        entity_ids.extend(
            row[0]
            for row in session.query(DuplicateMatch.id)
            .filter(
                DuplicateMatch.evidence_id.in_(evidence_ids)
                | DuplicateMatch.matched_evidence_id.in_(evidence_ids)
            )
            .all()
        )
        node_ids = [
            row[0] for row in session.query(GraphNode.id).filter(GraphNode.entity_id.in_(entity_ids)).all()
        ]
        if node_ids:
            session.query(GraphRelationship).filter(
                GraphRelationship.source_node_id.in_(node_ids)
                | GraphRelationship.target_node_id.in_(node_ids)
            ).delete(synchronize_session=False)
            session.query(GraphNode).filter(GraphNode.id.in_(node_ids)).delete(synchronize_session=False)
        if job_ids:
            result_ids = [
                row[0]
                for row in session.query(AnalysisResult.id).filter(AnalysisResult.job_id.in_(job_ids)).all()
            ]
            if result_ids:
                session.query(VisionDetection).filter(
                    VisionDetection.analysis_result_id.in_(result_ids)
                ).delete(synchronize_session=False)
            session.query(AnalysisResult).filter(AnalysisResult.job_id.in_(job_ids)).delete(
                synchronize_session=False
            )
            session.query(AnalysisJob).filter(AnalysisJob.id.in_(job_ids)).delete(synchronize_session=False)
        session.query(DuplicateMatch).filter(
            DuplicateMatch.evidence_id.in_(evidence_ids)
            | DuplicateMatch.matched_evidence_id.in_(evidence_ids)
        ).delete(synchronize_session=False)
        session.query(EvidenceMetadata).filter(EvidenceMetadata.evidence_id.in_(evidence_ids)).delete(
            synchronize_session=False
        )
        session.query(Activity).filter(Activity.project_id.in_(project_ids)).delete(synchronize_session=False)
        session.query(Evidence).filter(Evidence.id.in_(evidence_ids)).update(
            {Evidence.project_id: None, Evidence.claim_id: None}, synchronize_session=False
        )
        session.query(Claim).filter(Claim.project_id.in_(project_ids)).delete(synchronize_session=False)
        session.query(Evidence).filter(Evidence.id.in_(evidence_ids)).delete(synchronize_session=False)
        session.query(Project).filter(Project.id.in_(project_ids)).delete(synchronize_session=False)
        session.query(User).filter(User.id == user_id).delete(synchronize_session=False)
        session.commit()
    finally:
        session.close()


def setup_supported_claim(user, color=(61, 131, 201)):
    project = api_create_project(str(user.id))
    claim = api_create_claim(project["id"])
    evidence = api_upload(image_bytes(color), f"exp-{uuid4().hex[:8]}.jpg")
    link_evidence(evidence["evidence_id"], project["id"], claim["id"])
    assert (
        api_edge("EVIDENCE", evidence["evidence_id"], "CLAIM", claim["id"], "SUPPORTS").status_code
        == 201
    )
    run = client.post(f"/api/v1/fusion/CLAIM/{claim['id']}", json={}).json()["run"]
    return project, claim, evidence, run


def strip_volatile(content: dict) -> dict:
    return {k: v for k, v in content.items() if k not in ("generated_at",)}


def test_successful_explanation_has_all_sections():
    user = setup_user()
    project_ids, evidence_ids = [], []
    try:
        project, claim, evidence, run = setup_supported_claim(user)
        project_ids.append(project["id"])
        evidence_ids.append(evidence["evidence_id"])

        response = client.get(f"/api/v1/explanations/fusion/{run['id']}")
        assert response.status_code == 200, response.text
        body = response.json()
        for section in ("fusion_run_id", "target_type", "target_id", "integrity_assessment",
                        "review_priority", "methodology", "configuration", "summary", "signals",
                        "rules", "priority_trace", "unknowns", "provenance", "generated_at"):
            assert section in body, section
        assert body["fusion_run_id"] == run["id"]
        assert body["target_type"] == "CLAIM"
        assert body["target_id"] == claim["id"]
        assert body["integrity_assessment"]["value"] == "SUPPORTED"
        assert body["methodology"]["explanation_method_version"] == "explanation-v1"
        assert body["methodology"]["fusion_method_version"] == "fusion-v1"
        assert body["methodology"]["configuration_version"] == "v1"
        assert body["rules"][0]["rule_id"] == "POSITIVE_ONLY"
        assert body["rules"][0]["result"] == "SUPPORTED"
        types = {item["signal_type"] for item in body["signals"]}
        assert "GRAPH_SUPPORT" in types
        assert body["materialized"] is False
        assert body["explanation_id"] is None
        blob = json.dumps(body).lower()
        assert "explanation-v1" in blob
    finally:
        cleanup(str(user.id), project_ids, evidence_ids)


def test_signal_and_graph_lineage():
    user = setup_user()
    project_ids, evidence_ids = [], []
    try:
        project, claim, evidence, run = setup_supported_claim(user)
        project_ids.append(project["id"])
        evidence_ids.append(evidence["evidence_id"])
        body = client.get(f"/api/v1/explanations/fusion/{run['id']}").json()

        support = next(item for item in body["signals"] if item["signal_type"] == "GRAPH_SUPPORT")
        assert support["source"] == "evidence_graph"
        assert support["source_entity_id"] == evidence["evidence_id"]
        assert support["method"] == "deterministic_signal_fusion"
        assert support["contribution"] == 0.3
        lineage = support["lineage"]
        assert lineage["kind"] == "graph_relationship"
        assert lineage["relationship_type"] == "SUPPORTS"
        assert lineage["status_at_fusion_time"] == "ACTIVE"
        assert lineage["current_status"] == "ACTIVE"
        assert lineage["source"] == {"node_type": "EVIDENCE", "entity_id": evidence["evidence_id"]}
        assert lineage["target"] == {"node_type": "CLAIM", "entity_id": claim["id"]}
        assert lineage["provenance"]["source"] == "human_review"

        session = get_session()
        try:
            edge = session.query(GraphRelationship).filter_by(id=lineage["edge_id"]).one()
            assert edge.relationship_type == "SUPPORTS"
        finally:
            session.close()
    finally:
        cleanup(str(user.id), project_ids, evidence_ids)


def test_materialize_is_idempotent_and_stable_across_runs():
    user = setup_user()
    project_ids, evidence_ids = [], []
    try:
        project, claim, evidence, run = setup_supported_claim(user)
        project_ids.append(project["id"])
        evidence_ids.append(evidence["evidence_id"])

        first = client.post(f"/api/v1/explanations/fusion/{run['id']}")
        assert first.status_code == 201, first.text
        assert first.json()["materialized"] is True
        explanation_id = first.json()["explanation_id"]
        second = client.post(f"/api/v1/explanations/fusion/{run['id']}")
        assert second.status_code == 200
        assert second.json()["explanation_id"] == explanation_id
        assert strip_volatile(first.json()) == strip_volatile(second.json())

        # A newer fusion run does not rewrite the materialized record.
        evidence2 = api_upload(image_bytes((62, 132, 202)), "exp2.jpg")
        evidence_ids.append(evidence2["evidence_id"])
        link_evidence(evidence2["evidence_id"], project["id"], claim["id"])
        api_edge("EVIDENCE", evidence2["evidence_id"], "CLAIM", claim["id"], "CONTRADICTS")
        run2 = client.post(f"/api/v1/fusion/CLAIM/{claim['id']}", json={}).json()["run"]

        reread = client.get(f"/api/v1/explanations/fusion/{run['id']}").json()
        # Fresh reads reflect the current lifecycle (run #2 superseded run #1)
        # while the materialized snapshot preserves history.
        assert reread["integrity_assessment"]["status"] == "SUPERSEDED"
        assert reread["integrity_assessment"]["value"] == "SUPPORTED"
        for key in ("signals", "rules", "summary", "configuration", "methodology",
                    "priority_trace", "unknowns", "provenance", "review_priority"):
            assert reread[key] == first.json()[key], key

        latest = client.get(f"/api/v1/explanations/CLAIM/{claim['id']}").json()
        assert latest["fusion_run_id"] == run2["id"]
        assert latest["integrity_assessment"]["value"] == "MIXED"
    finally:
        cleanup(str(user.id), project_ids, evidence_ids)


def test_invalidated_edge_preserves_historical_contribution():
    user = setup_user()
    project_ids, evidence_ids = [], []
    try:
        project, claim, evidence, run = setup_supported_claim(user)
        project_ids.append(project["id"])
        evidence_ids.append(evidence["evidence_id"])
        snapshot = client.post(f"/api/v1/explanations/fusion/{run['id']}").json()
        edge_id = next(
            item["lineage"]["edge_id"]
            for item in snapshot["signals"]
            if item["signal_type"] == "GRAPH_SUPPORT"
        )

        patched = client.patch(
            f"/api/v1/graph/relationships/{edge_id}", json={"relationship_status": "INVALIDATED"}
        )
        assert patched.status_code == 200

        fresh = client.get(f"/api/v1/explanations/fusion/{run['id']}").json()
        support = next(item for item in fresh["signals"] if item["signal_type"] == "GRAPH_SUPPORT")
        # Historical contribution preserved; current status now visible.
        assert support["lineage"]["status_at_fusion_time"] == "ACTIVE"
        assert support["lineage"]["current_status"] == "INVALIDATED"
        # Materialized snapshot is byte-stable apart from generation metadata.
        assert strip_volatile(snapshot) == strip_volatile(
            client.post(f"/api/v1/explanations/fusion/{run['id']}").json()
        )
    finally:
        cleanup(str(user.id), project_ids, evidence_ids)


def test_unknown_zero_signal_failed_and_invalid_cases():
    user = setup_user()
    project_ids, evidence_ids = [], []
    try:
        project = api_create_project(str(user.id))
        project_ids.append(project["id"])
        claim = api_create_claim(project["id"])
        evidence = api_upload(image_bytes((63, 133, 203)), "exp-u.jpg")
        evidence_ids.append(evidence["evidence_id"])
        link_evidence(evidence["evidence_id"], project["id"], claim["id"])
        run = client.post(f"/api/v1/fusion/CLAIM/{claim['id']}", json={}).json()["run"]

        body = client.get(f"/api/v1/explanations/fusion/{run['id']}").json()
        assert body["integrity_assessment"]["value"] in ("UNKNOWN", "INSUFFICIENT_EVIDENCE")
        assert any(item["signal_type"] == "LOCATION_UNKNOWN" for item in body["unknowns"])
        assert any("unavailable" in item["sentence"] or "unknown" in item["sentence"].lower()
                   for item in body["unknowns"])

        # Zero-signal claim.
        claim2 = api_create_claim(project["id"])
        run2 = client.post(f"/api/v1/fusion/CLAIM/{claim2['id']}", json={}).json()["run"]
        zero = client.get(f"/api/v1/explanations/fusion/{run2['id']}").json()
        assert zero["integrity_assessment"]["value"] == "INSUFFICIENT_EVIDENCE"
        assert zero["signals"] == []
        assert zero["rules"][0]["rule_id"] == "NO_SIGNALS"

        # Failed fusion run → explicit unavailable state, never success.
        session = get_session()
        try:
            from backend.repositories import fusion as fusion_repo

            failed = fusion_repo.insert_run(
                session, target_type="CLAIM", target_id=claim["id"],
                method="deterministic_signal_fusion", method_version="fusion-v1",
                configuration_version="v1", input_snapshot={},
            )
            failed.status = "FAILED"
            failed.error = "boom"
            session.commit()
            failed_id = failed.id
        finally:
            session.close()
        failed_resp = client.get(f"/api/v1/explanations/fusion/{failed_id}")
        assert failed_resp.status_code == 422
        assert "EXPLANATION_UNAVAILABLE" in failed_resp.text
        assert client.post(f"/api/v1/explanations/fusion/{failed_id}").status_code == 422
        session = get_session()
        try:
            from backend.db.models import ExplanationRun as ExplanationRunModel

            assert session.query(ExplanationRunModel).filter_by(fusion_run_id=failed_id).count() == 0
            session.query(FusionRun).filter_by(id=failed_id).delete()
            session.commit()
        finally:
            session.close()

        # Invalid identifiers.
        assert client.get("/api/v1/explanations/fusion/not-a-uuid").status_code == 422
        assert client.get(f"/api/v1/explanations/fusion/{uuid4()}").status_code == 404
        assert client.get(f"/api/v1/explanations/CLAIM/{uuid4()}").status_code == 404
        assert client.get("/api/v1/explanations/CLAIM/not-a-uuid").status_code == 422
        assert client.get("/api/v1/explanations/PROJECT/not-a-uuid").status_code == 422
    finally:
        cleanup(str(user.id), project_ids, evidence_ids)


def test_cross_project_lineage_without_ownership_change():
    user = setup_user()
    project_ids, evidence_ids = [], []
    try:
        from backend.services.duplicate_intelligence import analyze_duplicates
        from backend.services.fingerprinting import process_evidence
        from backend.services import evidence_graph as graph_service

        project_a = api_create_project(str(user.id), "exp proj A")
        project_b = api_create_project(str(user.id), "exp proj B")
        project_ids.extend([project_a["id"], project_b["id"]])
        payload = image_bytes((64, 134, 204))
        evidence_a = api_upload(payload, "xp-a.jpg")
        evidence_b = api_upload(payload, "xp-b.jpg")
        evidence_ids.extend([evidence_a["evidence_id"], evidence_b["evidence_id"]])
        link_evidence(evidence_a["evidence_id"], project_a["id"])
        link_evidence(evidence_b["evidence_id"], project_b["id"])

        session = get_session()
        try:
            process_evidence(evidence_a["evidence_id"], session)
            process_evidence(evidence_b["evidence_id"], session)
            analyze_duplicates(evidence_a["evidence_id"], session)
            match = (
                session.query(DuplicateMatch)
                .filter(
                    DuplicateMatch.evidence_id
                    == min(evidence_a["evidence_id"], evidence_b["evidence_id"]),
                    DuplicateMatch.matched_evidence_id
                    == max(evidence_a["evidence_id"], evidence_b["evidence_id"]),
                )
                .one()
            )
            graph_service.record_duplicate_relationship(session, match.id)
        finally:
            session.close()

        run = client.post(f"/api/v1/fusion/EVIDENCE/{evidence_a['evidence_id']}", json={}).json()["run"]
        body = client.get(f"/api/v1/explanations/fusion/{run['id']}").json()
        dup = next(item for item in body["signals"] if item["signal_type"].startswith("DUPLICATE_"))
        assert dup["lineage"].get("cross_project") is True
        assert sorted(dup["lineage"]["evidence_projects"]) == sorted([project_a["id"], project_b["id"]])

        session = get_session()
        try:
            row = session.query(Evidence).filter_by(id=evidence_b["evidence_id"]).one()
            assert str(row.project_id) == project_b["id"]
        finally:
            session.close()
    finally:
        cleanup(str(user.id), project_ids, evidence_ids)


def test_deterministic_ordering_and_bounded_response():
    user = setup_user()
    project_ids, evidence_ids = [], []
    try:
        project, claim, evidence, run = setup_supported_claim(user)
        project_ids.append(project["id"])
        evidence_ids.append(evidence["evidence_id"])
        first = client.get(f"/api/v1/explanations/fusion/{run['id']}").json()
        second = client.get(f"/api/v1/explanations/fusion/{run['id']}").json()
        assert strip_volatile(first) == strip_volatile(second)
        signals = first["signals"]
        keys = [(-abs(item["contribution"]), item["signal_type"],
                 str(item["source_entity_id"] or "")) for item in signals]
        assert keys == sorted(keys)
        # Bounded: references only, no raw evidence payloads.
        blob = json.dumps(first)
        assert len(blob) < 100_000
        for forbidden in ("storage_key", "s3_secret", "presigned", "exif"):
            assert forbidden not in blob.lower()
    finally:
        cleanup(str(user.id), project_ids, evidence_ids)
