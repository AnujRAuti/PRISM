"""BE-010 integration tests against real PostgreSQL infrastructure."""

from io import BytesIO
from pathlib import Path
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
    GraphNode,
    GraphRelationship,
    Project,
    User,
    VisionDetection,
)
from backend.db.session import get_session
from backend.services import evidence_graph as graph_service
from backend.services.storage import StorageService


client = TestClient(app)


def image_bytes(color=(30, 90, 160)) -> bytes:
    output = BytesIO()
    Image.new("RGB", (16, 16), color=color).save(output, format="JPEG")
    return output.getvalue()


def setup_user() -> User:
    session = get_session()
    user = User(username=f"be010-{uuid4()}", email=f"{uuid4()}@example.com")
    session.add(user)
    session.commit()
    session.refresh(user)
    session.close()
    return user


def setup_project(user_id: str, name: str = "BE-010 project") -> dict:
    response = client.post("/api/v1/projects", json={"name": name, "owner_id": user_id})
    assert response.status_code == 201
    return response.json()


def setup_claim(project_id: str) -> dict:
    response = client.post(
        f"/api/v1/projects/{project_id}/claims",
        json={"title": "BE-010 claim", "description": "graph test"},
    )
    assert response.status_code == 201
    return response.json()


def upload(filename: str = "be010.jpg") -> dict:
    response = client.post(
        "/api/v1/evidence",
        files={"file": (filename, image_bytes(), "image/jpeg")},
    )
    assert response.status_code == 201
    return response.json()


def cleanup(user_id, project_ids, evidence_ids, node_entity_ids=None) -> None:
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
        entity_ids = list(evidence_ids) + list(project_ids) + list(node_entity_ids or [])
        job_ids = [
            row[0] for row in session.query(AnalysisJob.id).filter(AnalysisJob.evidence_id.in_(evidence_ids)).all()
        ]
        if job_ids:
            entity_ids.extend(job_ids)
            entity_ids.extend(
                row[0]
                for row in session.query(AnalysisResult.id).filter(AnalysisResult.job_id.in_(job_ids)).all()
            )
            entity_ids.extend(
                row[0]
                for row in session.query(VisionDetection.id)
                .join(AnalysisResult, AnalysisResult.id == VisionDetection.analysis_result_id)
                .filter(AnalysisResult.job_id.in_(job_ids))
                .all()
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
                (GraphRelationship.source_node_id.in_(node_ids))
                | (GraphRelationship.target_node_id.in_(node_ids))
            ).delete(synchronize_session=False)
            session.query(GraphNode).filter(GraphNode.id.in_(node_ids)).delete(
                synchronize_session=False
            )
        result_ids = [
            row[0]
            for row in session.query(AnalysisResult.id)
            .join(AnalysisJob, AnalysisJob.id == AnalysisResult.job_id)
            .filter(AnalysisJob.evidence_id.in_(evidence_ids))
            .all()
        ]
        if result_ids:
            session.query(VisionDetection).filter(
                VisionDetection.analysis_result_id.in_(result_ids)
            ).delete(synchronize_session=False)
        session.query(AnalysisResult).filter(
            AnalysisResult.job_id.in_(
                session.query(AnalysisJob.id).filter(AnalysisJob.evidence_id.in_(evidence_ids))
            )
        ).delete(synchronize_session=False)
        session.query(AnalysisJob).filter(AnalysisJob.evidence_id.in_(evidence_ids)).delete(
            synchronize_session=False
        )
        session.query(DuplicateMatch).filter(
            DuplicateMatch.evidence_id.in_(evidence_ids)
            | DuplicateMatch.matched_evidence_id.in_(evidence_ids)
        ).delete(synchronize_session=False)
        session.query(EvidenceMetadata).filter(
            EvidenceMetadata.evidence_id.in_(evidence_ids)
        ).delete(synchronize_session=False)
        session.query(Activity).filter(Activity.project_id.in_(project_ids)).delete(
            synchronize_session=False
        )
        session.query(Claim).filter(Claim.project_id.in_(project_ids)).delete(
            synchronize_session=False
        )
        session.query(Evidence).filter(Evidence.id.in_(evidence_ids)).update(
            {Evidence.project_id: None, Evidence.claim_id: None}, synchronize_session=False
        )
        session.query(Evidence).filter(Evidence.id.in_(evidence_ids)).delete(
            synchronize_session=False
        )
        session.query(Project).filter(Project.id.in_(project_ids)).delete(synchronize_session=False)
        session.query(User).filter(User.id == user_id).delete(synchronize_session=False)
        session.commit()
    finally:
        session.close()


def link_evidence_to_project(evidence_id: str, project_id: str) -> None:
    session = get_session()
    try:
        evidence = session.query(Evidence).filter_by(id=evidence_id).one()
        evidence.project_id = project_id
        session.commit()
    finally:
        session.close()


def post_edge(source_type, source_id, target_type, target_id, rel_type, provenance=None):
    return client.post(
        "/api/v1/graph/relationships",
        json={
            "source": {"node_type": source_type, "entity_id": source_id},
            "target": {"node_type": target_type, "entity_id": target_id},
            "relationship_type": rel_type,
            "provenance": provenance or {"source": "human_review", "method": "manual_link"},
        },
    )


def test_domain_nodes_resolve_and_supports_edge_persists():
    user = setup_user()
    project_ids, evidence_ids = [], []
    try:
        project = setup_project(str(user.id))
        project_ids.append(project["id"])
        claim = setup_claim(project["id"])
        evidence = upload()
        evidence_ids.append(evidence["evidence_id"])
        link_evidence_to_project(evidence["evidence_id"], project["id"])

        created = post_edge("EVIDENCE", evidence["evidence_id"], "CLAIM", claim["id"], "SUPPORTS")
        assert created.status_code == 201
        body = created.json()
        assert body["relationship_type"] == "SUPPORTS"
        assert body["relationship_status"] == "ACTIVE"
        assert body["source"]["entity_id"] == evidence["evidence_id"]
        assert body["target"]["entity_id"] == claim["id"]
        assert body["provenance"]["source"] == "human_review"

        # Deterministic identity: same entity never yields a second node.
        session = get_session()
        try:
            count = (
                session.query(GraphNode)
                .filter_by(node_type="EVIDENCE", entity_id=evidence["evidence_id"])
                .count()
            )
            assert count == 1
        finally:
            session.close()

        traversal = client.get(f"/api/v1/graph/EVIDENCE/{evidence['evidence_id']}")
        assert traversal.status_code == 200
        assert traversal.json()["total"] == 1
    finally:
        cleanup(str(user.id), project_ids, evidence_ids, [])


def test_contradicts_and_direction_filtering():
    user = setup_user()
    project_ids, evidence_ids = [], []
    try:
        project = setup_project(str(user.id))
        project_ids.append(project["id"])
        claim = setup_claim(project["id"])
        evidence = upload("contra.jpg")
        evidence_ids.append(evidence["evidence_id"])

        assert (
            post_edge("EVIDENCE", evidence["evidence_id"], "CLAIM", claim["id"], "SUPPORTS").status_code
            == 201
        )
        assert (
            post_edge("EVIDENCE", evidence["evidence_id"], "CLAIM", claim["id"], "CONTRADICTS").status_code
            == 201
        )

        outgoing = client.get(
            f"/api/v1/graph/EVIDENCE/{evidence['evidence_id']}", params={"direction": "outgoing"}
        )
        assert outgoing.json()["total"] == 2
        incoming = client.get(
            f"/api/v1/graph/CLAIM/{claim['id']}", params={"direction": "incoming"}
        )
        assert incoming.json()["total"] == 2
        reverse = client.get(
            f"/api/v1/graph/CLAIM/{claim['id']}", params={"direction": "outgoing"}
        )
        assert reverse.json()["total"] == 0
        typed = client.get(
            f"/api/v1/graph/EVIDENCE/{evidence['evidence_id']}",
            params={"relationship_type": "CONTRADICTS"},
        )
        assert typed.json()["total"] == 1
    finally:
        cleanup(str(user.id), project_ids, evidence_ids, [])


def test_idempotent_reassertion_and_history_across_runs():
    user = setup_user()
    project_ids, evidence_ids = [], []
    try:
        project = setup_project(str(user.id))
        project_ids.append(project["id"])
        claim = setup_claim(project["id"])
        evidence = upload("idem.jpg")
        evidence_ids.append(evidence["evidence_id"])

        first = post_edge("EVIDENCE", evidence["evidence_id"], "CLAIM", claim["id"], "SUPPORTS")
        assert first.status_code == 201
        repeat = post_edge("EVIDENCE", evidence["evidence_id"], "CLAIM", claim["id"], "SUPPORTS")
        assert repeat.status_code == 200
        assert repeat.json()["id"] == first.json()["id"]

        run_a, run_b = str(uuid4()), str(uuid4())
        edge_a = post_edge(
            "EVIDENCE", evidence["evidence_id"], "CLAIM", claim["id"], "ASSOCIATED_WITH",
            {"source": "analysis", "method": "m", "analysis_run_id": run_a},
        )
        edge_b = post_edge(
            "EVIDENCE", evidence["evidence_id"], "CLAIM", claim["id"], "ASSOCIATED_WITH",
            {"source": "analysis", "method": "m", "analysis_run_id": run_b},
        )
        assert edge_a.status_code == 201 and edge_b.status_code == 201
        assert edge_a.json()["id"] != edge_b.json()["id"]

        session = get_session()
        try:
            assert (
                session.query(GraphRelationship)
                .filter_by(relationship_type="ASSOCIATED_WITH")
                .count()
                == 2
            )
        finally:
            session.close()
    finally:
        cleanup(str(user.id), project_ids, evidence_ids, [])


def test_duplicate_relationship_from_real_be006_output():
    from backend.services.duplicate_intelligence import analyze_duplicates
    from backend.services.fingerprinting import process_evidence

    user = setup_user()
    project_ids, evidence_ids = [], []
    try:
        project = setup_project(str(user.id))
        project_ids.append(project["id"])
        payload = image_bytes()
        first = client.post("/api/v1/evidence", files={"file": ("dup-a.jpg", payload, "image/jpeg")}).json()
        second = client.post("/api/v1/evidence", files={"file": ("dup-b.jpg", payload, "image/jpeg")}).json()
        evidence_ids.extend([first["evidence_id"], second["evidence_id"]])

        session = get_session()
        try:
            process_evidence(first["evidence_id"], session)
            process_evidence(second["evidence_id"], session)
            analyze_duplicates(first["evidence_id"], session)
            match = (
                session.query(DuplicateMatch)
                .filter(
                    DuplicateMatch.evidence_id
                    == min(first["evidence_id"], second["evidence_id"]),
                    DuplicateMatch.matched_evidence_id
                    == max(first["evidence_id"], second["evidence_id"]),
                )
                .one()
            )
            run_id = str(uuid4())
            edge, created = graph_service.record_duplicate_relationship(
                session, match.id, analysis_run_id=run_id
            )
            assert created is True
            assert edge.relationship_type == "DUPLICATE_OF"
            assert edge.analysis_run_id == run_id
            assert edge.provenance["source"] == "duplicate_intelligence"
            # Idempotent for the same run.
            _, created_again = graph_service.record_duplicate_relationship(
                session, match.id, analysis_run_id=run_id
            )
            assert created_again is False
        finally:
            session.close()

        traversal = client.get(f"/api/v1/graph/EVIDENCE/{first['evidence_id']}")
        assert traversal.status_code == 200
        assert any(item["relationship_type"] == "DUPLICATE_OF" for item in traversal.json()["items"])
    finally:
        cleanup(str(user.id), project_ids, evidence_ids, [])


def test_temporal_relationship_from_real_be008_verdict():
    from backend.services.temporal_intelligence import compare_pair

    user = setup_user()
    project_ids, evidence_ids = [], []
    try:
        first, second = upload("temp-a.jpg"), upload("temp-b.jpg")
        evidence_ids.extend([first["evidence_id"], second["evidence_id"]])
        session = get_session()
        try:
            session.add(
                EvidenceMetadata(
                    evidence_id=first["evidence_id"],
                    metadata_json={"exif": {"EXIF DateTimeOriginal": "2024:01:01 10:00:00"}},
                )
            )
            session.add(
                EvidenceMetadata(
                    evidence_id=second["evidence_id"],
                    metadata_json={"exif": {"EXIF DateTimeOriginal": "2024:01:02 10:00:00"}},
                )
            )
            session.commit()
            pair = compare_pair(first["evidence_id"], second["evidence_id"], session)
            assert pair["relationship"] == "CAPTURED_BEFORE"
            edge, created = graph_service.record_temporal_relationship(session, pair)
            assert created is True
            assert edge.relationship_type == "TEMPORALLY_RELATED_TO"
            assert edge.provenance["temporal_relationship"] == "CAPTURED_BEFORE"
        finally:
            session.close()
    finally:
        cleanup(str(user.id), project_ids, evidence_ids, [])


def test_vision_relationship_from_real_be009_output():
    from backend.services.analysis_queue import AnalysisQueue
    from backend.workers.analysis_worker import process_message

    user = setup_user()
    project_ids, evidence_ids = [], []
    queue = AnalysisQueue()
    queue.clear()
    job_id = None
    try:
        # Real photo fixture: YOLO yields actual detections (a generated
        # solid-color image would honestly yield zero).
        photo = Path(__file__).parents[2] / "test-image.jpg"
        assert photo.exists(), "test-image.jpg fixture is required"
        uploaded = client.post(
            "/api/v1/evidence",
            files={"file": ("vision-graph.jpg", photo.read_bytes(), "image/jpeg")},
        )
        assert uploaded.status_code == 201
        evidence = uploaded.json()
        evidence_ids.append(evidence["evidence_id"])
        job_id = client.post(
            "/api/v1/analysis/jobs",
            json={"evidence_id": evidence["evidence_id"], "job_type": "vision"},
        ).json()["job_id"]
        message = queue.dequeue(timeout=10)
        assert message is not None
        assert process_message(message, queue) == "completed"

        session = get_session()
        try:
            detection = (
                session.query(VisionDetection)
                .join(AnalysisResult, AnalysisResult.id == VisionDetection.analysis_result_id)
                .filter(AnalysisResult.job_id == job_id)
                .first()
            )
            assert detection is not None
            edge, created = graph_service.record_vision_relationship(session, detection.id)
            assert created is True
            assert edge.relationship_type == "HAS_DETECTION"
            assert edge.analysis_run_id == job_id
            result = session.query(AnalysisResult).filter_by(job_id=job_id).one()
            has_analysis, _ = graph_service.record_has_analysis(
                session, evidence["evidence_id"], result.id
            )
            assert has_analysis.relationship_type == "HAS_ANALYSIS"
        finally:
            session.close()
    finally:
        queue.clear()
        cleaner = get_session()
        try:
            if job_id:
                cleaner.query(AnalysisResult).filter_by(job_id=job_id).delete()
                cleaner.query(AnalysisJob).filter_by(id=job_id).delete()
                cleaner.commit()
        finally:
            cleaner.close()
        cleanup(str(user.id), project_ids, evidence_ids, [])


def test_cross_project_edge_without_ownership_change():
    user = setup_user()
    project_ids, evidence_ids = [], []
    try:
        project_a = setup_project(str(user.id), "proj A")
        project_b = setup_project(str(user.id), "proj B")
        project_ids.extend([project_a["id"], project_b["id"]])
        evidence_a, evidence_b = upload("xa.jpg"), upload("xb.jpg")
        evidence_ids.extend([evidence_a["evidence_id"], evidence_b["evidence_id"]])
        link_evidence_to_project(evidence_a["evidence_id"], project_a["id"])
        link_evidence_to_project(evidence_b["evidence_id"], project_b["id"])

        created = post_edge(
            "EVIDENCE", evidence_a["evidence_id"], "EVIDENCE", evidence_b["evidence_id"], "ASSOCIATED_WITH"
        )
        assert created.status_code == 201

        session = get_session()
        try:
            row_a = session.query(Evidence).filter_by(id=evidence_a["evidence_id"]).one()
            row_b = session.query(Evidence).filter_by(id=evidence_b["evidence_id"]).one()
            assert str(row_a.project_id) == project_a["id"]
            assert str(row_b.project_id) == project_b["id"]
        finally:
            session.close()
    finally:
        cleanup(str(user.id), project_ids, evidence_ids, [])


def test_invalid_combination_rejected_with_no_row():
    user = setup_user()
    project_ids, evidence_ids = [], []
    try:
        project = setup_project(str(user.id))
        project_ids.append(project["id"])
        evidence = upload("bad-edge.jpg")
        evidence_ids.append(evidence["evidence_id"])

        bad = post_edge("PROJECT", project["id"], "EVIDENCE", evidence["evidence_id"], "SUPPORTS")
        assert bad.status_code == 422
        missing = post_edge("EVIDENCE", evidence["evidence_id"], "CLAIM", str(uuid4()), "SUPPORTS")
        assert missing.status_code == 404
        bad_uuid = client.get("/api/v1/graph/EVIDENCE/not-a-uuid")
        assert bad_uuid.status_code == 422

        # Scoped to this test's entity: no edge may reference it.
        session = get_session()
        try:
            node_ids = [
                row.id
                for row in session.query(GraphNode)
                .filter_by(node_type="EVIDENCE", entity_id=evidence["evidence_id"])
                .all()
            ]
            leftovers = (
                session.query(GraphRelationship)
                .filter(
                    GraphRelationship.source_node_id.in_(node_ids)
                    | GraphRelationship.target_node_id.in_(node_ids)
                )
                .count()
                if node_ids
                else 0
            )
            assert leftovers == 0
        finally:
            session.close()
    finally:
        cleanup(str(user.id), project_ids, evidence_ids, [])


def test_status_lifecycle_and_pagination():
    user = setup_user()
    project_ids, evidence_ids = [], []
    try:
        project = setup_project(str(user.id))
        project_ids.append(project["id"])
        claim = setup_claim(project["id"])
        evidence = upload("page.jpg")
        evidence_ids.append(evidence["evidence_id"])
        for rel_type in ("SUPPORTS", "CONTRADICTS", "ASSOCIATED_WITH"):
            assert (
                post_edge("EVIDENCE", evidence["evidence_id"], "CLAIM", claim["id"], rel_type).status_code
                == 201
            )
        page = client.get(
            f"/api/v1/graph/EVIDENCE/{evidence['evidence_id']}",
            params={"limit": 2, "offset": 1},
        )
        assert page.status_code == 200
        assert page.json()["total"] == 3
        assert len(page.json()["items"]) == 2

        rel_id = page.json()["items"][0]["id"]
        patched = client.patch(
            f"/api/v1/graph/relationships/{rel_id}", json={"relationship_status": "SUPERSEDED"}
        )
        assert patched.status_code == 200
        assert patched.json()["relationship_status"] == "SUPERSEDED"
        # Terminal history is immutable.
        assert (
            client.patch(
                f"/api/v1/graph/relationships/{rel_id}", json={"relationship_status": "ACTIVE"}
            ).status_code
            == 422
        )
        session = get_session()
        try:
            node_ids = [
                row.id
                for row in session.query(GraphNode)
                .filter_by(node_type="EVIDENCE", entity_id=evidence["evidence_id"])
                .all()
            ]
            assert (
                session.query(GraphRelationship)
                .filter(
                    GraphRelationship.source_node_id.in_(node_ids)
                    | GraphRelationship.target_node_id.in_(node_ids)
                )
                .count()
                == 3
            )
        finally:
            session.close()
    finally:
        cleanup(str(user.id), project_ids, evidence_ids, [])


def test_failed_analysis_produces_no_graph_relationship():
    user = setup_user()
    project_ids, evidence_ids = [], []
    try:
        evidence = upload("doomed-graph.jpg")
        evidence_ids.append(evidence["evidence_id"])
        session = get_session()
        try:
            with pytest.raises(LookupError):
                graph_service.record_vision_relationship(session, str(uuid4()))
            with pytest.raises(LookupError):
                graph_service.record_has_analysis(session, evidence["evidence_id"], str(uuid4()))
            node_ids = [
                row.id
                for row in session.query(GraphNode)
                .filter_by(node_type="EVIDENCE", entity_id=evidence["evidence_id"])
                .all()
            ]
            leftovers = (
                session.query(GraphRelationship)
                .filter(
                    GraphRelationship.source_node_id.in_(node_ids)
                    | GraphRelationship.target_node_id.in_(node_ids)
                )
                .count()
                if node_ids
                else 0
            )
            assert leftovers == 0
        finally:
            session.close()
    finally:
        cleanup(str(user.id), project_ids, evidence_ids, [])
