"""BE-011 integration tests against real PostgreSQL infrastructure."""

import json
from io import BytesIO
from pathlib import Path
from uuid import uuid4

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
    FusionConfiguration,
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
FIXTURE_PHOTO = Path(__file__).parents[2] / "test-image.jpg"


def image_bytes(color=(40, 110, 190)) -> bytes:
    output = BytesIO()
    Image.new("RGB", (16, 16), color=color).save(output, format="JPEG")
    return output.getvalue()


def setup_user() -> User:
    session = get_session()
    user = User(username=f"be011-{uuid4()}", email=f"{uuid4()}@example.com")
    session.add(user)
    session.commit()
    session.refresh(user)
    session.close()
    return user


def api_create_project(user_id: str, name: str = "BE-011 project") -> dict:
    response = client.post("/api/v1/projects", json={"name": name, "owner_id": user_id})
    assert response.status_code == 201
    return response.json()


def api_create_claim(project_id: str) -> dict:
    response = client.post(
        f"/api/v1/projects/{project_id}/claims",
        json={"title": "BE-011 claim", "description": "fusion test"},
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


def cleanup(user_id, project_ids, evidence_ids, config_versions=None) -> None:
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
        job_ids = [
            row[0]
            for row in session.query(AnalysisJob.id).filter(AnalysisJob.evidence_id.in_(evidence_ids)).all()
        ]
        run_ids = [
            row[0]
            for row in session.query(FusionRun.id)
            .filter(FusionRun.target_id.in_(project_ids + evidence_ids))
            .all()
        ]
        # Runs are also found by direct target match below; belt and braces.
        claim_ids = [
            row[0] for row in session.query(Claim.id).filter(Claim.project_id.in_(project_ids)).all()
        ]
        run_ids.extend(
            row[0]
            for row in session.query(FusionRun.id)
            .filter(FusionRun.target_type == "CLAIM", FusionRun.target_id.in_(claim_ids))
            .all()
        )
        run_ids = list(set(run_ids))
        if run_ids:
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
        for version in config_versions or []:
            if version != "v1":
                session.query(FusionConfiguration).filter_by(version=version).delete()
        session.commit()
    finally:
        session.close()


def link_evidence(evidence_id: str, project_id: str, claim_id: str | None = None) -> None:
    session = get_session()
    try:
        evidence = session.query(Evidence).filter_by(id=evidence_id).one()
        evidence.project_id = project_id
        evidence.claim_id = claim_id
        session.commit()
    finally:
        session.close()


def fuse(target_type: str, target_id: str, config_version: str | None = None):
    body = {} if config_version is None else {"configuration_version": config_version}
    return client.post(f"/api/v1/fusion/{target_type}/{target_id}", json=body)


def test_claim_fusion_with_support_persists_run_assessment_priority():
    user = setup_user()
    project_ids, evidence_ids = [], []
    try:
        project = api_create_project(str(user.id))
        project_ids.append(project["id"])
        claim = api_create_claim(project["id"])
        evidence = api_upload(image_bytes(), "fusion-a.jpg")
        evidence_ids.append(evidence["evidence_id"])
        link_evidence(evidence["evidence_id"], project["id"], claim["id"])
        assert (
            api_edge("EVIDENCE", evidence["evidence_id"], "CLAIM", claim["id"], "SUPPORTS").status_code
            == 201
        )

        response = fuse("CLAIM", claim["id"])
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["run"]["status"] == "COMPLETED"
        assert body["run"]["method_version"] == "fusion-v1"
        assert body["run"]["configuration_version"] == "v1"
        assert body["assessment"]["assessment_value"] == "SUPPORTED"
        assert body["assessment"]["integrity_score"] == 1.0
        assert body["assessment"]["assessment_status"] == "ACTIVE"
        assert body["priority"]["priority"] in ("LOW", "NORMAL", "HIGH", "URGENT")
        types = {item["signal_type"] for item in body["signals"]}
        assert "GRAPH_SUPPORT" in types
        assert body["assessment"]["signal_summary"]["signal_count"] == len(body["signals"])
        forbidden = ("fraud", "risk_score", "authenticity", "truth_score", "compliance")
        serialized = json.dumps({**body["assessment"], **body["priority"]}).lower()
        assert not any(token in serialized for token in forbidden)

        session = get_session()
        try:
            assert session.query(FusionSignal).join(
                FusionRun, FusionRun.id == FusionSignal.fusion_run_id
            ).filter(FusionRun.id == body["run"]["id"]).count() == len(body["signals"])
        finally:
            session.close()
    finally:
        cleanup(str(user.id), project_ids, evidence_ids)


def test_contradiction_yields_contradicted_and_conflict_yields_mixed():
    user = setup_user()
    project_ids, evidence_ids = [], []
    try:
        project = api_create_project(str(user.id))
        project_ids.append(project["id"])
        claim = api_create_claim(project["id"])
        evidence = api_upload(image_bytes((9, 9, 9)), "fusion-c.jpg")
        evidence_ids.append(evidence["evidence_id"])
        link_evidence(evidence["evidence_id"], project["id"], claim["id"])
        api_edge("EVIDENCE", evidence["evidence_id"], "CLAIM", claim["id"], "CONTRADICTS")

        only_contra = fuse("CLAIM", claim["id"]).json()
        assert only_contra["assessment"]["assessment_value"] == "CONTRADICTED"
        assert only_contra["assessment"]["integrity_score"] == -1.0

        evidence2 = api_upload(image_bytes((10, 10, 10)), "fusion-c2.jpg")
        evidence_ids.append(evidence2["evidence_id"])
        link_evidence(evidence2["evidence_id"], project["id"], claim["id"])
        api_edge("EVIDENCE", evidence2["evidence_id"], "CLAIM", claim["id"], "SUPPORTS")

        mixed = fuse("CLAIM", claim["id"]).json()
        assert mixed["assessment"]["assessment_value"] == "MIXED"
        assert mixed["assessment"]["integrity_score"] == 0.0
        # Neither side was discarded: both signals persisted.
        persisted = {item["signal_type"] for item in mixed["signals"]}
        assert {"GRAPH_SUPPORT", "GRAPH_CONTRADICT"} <= persisted
    finally:
        cleanup(str(user.id), project_ids, evidence_ids)


def test_unknown_signals_do_not_reduce_assessment():
    user = setup_user()
    project_ids, evidence_ids = [], []
    try:
        project = api_create_project(str(user.id))
        project_ids.append(project["id"])
        claim = api_create_claim(project["id"])
        # No location, no EXIF, no analyses: only UNKNOWN/NEUTRAL signals exist.
        evidence = api_upload(image_bytes((11, 11, 11)), "fusion-u.jpg")
        evidence_ids.append(evidence["evidence_id"])
        link_evidence(evidence["evidence_id"], project["id"], claim["id"])

        body = fuse("CLAIM", claim["id"]).json()
        assert body["run"]["status"] == "COMPLETED"
        assert body["assessment"]["assessment_value"] in ("UNKNOWN", "INSUFFICIENT_EVIDENCE")
        assert body["assessment"]["assessment_value"] != "CONTRADICTED"
        assert any(
            item["signal_type"] == "LOCATION_UNKNOWN" and item["state"] == "UNKNOWN"
            for item in body["signals"]
        )
    finally:
        cleanup(str(user.id), project_ids, evidence_ids)


def test_zero_signal_claim_yields_insufficient_evidence():
    user = setup_user()
    project_ids, evidence_ids = [], []
    try:
        project = api_create_project(str(user.id))
        project_ids.append(project["id"])
        claim = api_create_claim(project["id"])
        body = fuse("CLAIM", claim["id"]).json()
        assert body["run"]["status"] == "COMPLETED"
        assert body["assessment"]["assessment_value"] == "INSUFFICIENT_EVIDENCE"
        assert body["assessment"]["integrity_score"] is None
        assert body["signals"] == []
    finally:
        cleanup(str(user.id), project_ids, evidence_ids)


def test_failed_analysis_contributes_no_signal():
    from backend.services.analysis_queue import AnalysisQueue
    from backend.workers.analysis_worker import process_message

    user = setup_user()
    project_ids, evidence_ids = [], []
    queue = AnalysisQueue()
    queue.clear()
    try:
        evidence = api_upload(image_bytes((12, 12, 12)), "fusion-f.jpg")
        evidence_ids.append(evidence["evidence_id"])
        storage = StorageService()
        storage.delete_object(storage.quarantine_bucket, evidence["storage_key"])
        job_id = client.post(
            "/api/v1/analysis/jobs",
            json={"evidence_id": evidence["evidence_id"], "job_type": "vision"},
        ).json()["job_id"]
        for _ in range(3):
            message = queue.dequeue(timeout=5)
            assert message is not None
            process_message(message, queue)

        body = fuse("EVIDENCE", evidence["evidence_id"]).json()
        assert body["run"]["status"] == "COMPLETED"
        assert not [item for item in body["signals"] if item["signal_type"].startswith("VISION_")]
        # Still distinguishable from a failed fusion run.
        assert body["assessment"]["assessment_value"] in ("UNKNOWN", "INSUFFICIENT_EVIDENCE")
    finally:
        queue.clear()
        cleanup(str(user.id), project_ids, evidence_ids)


def test_reprocessing_preserves_history_and_supersedes():
    user = setup_user()
    project_ids, evidence_ids = [], []
    try:
        project = api_create_project(str(user.id))
        project_ids.append(project["id"])
        claim = api_create_claim(project["id"])
        evidence = api_upload(image_bytes((13, 13, 13)), "fusion-r.jpg")
        evidence_ids.append(evidence["evidence_id"])
        link_evidence(evidence["evidence_id"], project["id"], claim["id"])
        api_edge("EVIDENCE", evidence["evidence_id"], "CLAIM", claim["id"], "SUPPORTS")

        first = fuse("CLAIM", claim["id"]).json()
        second = fuse("CLAIM", claim["id"]).json()
        assert first["run"]["id"] != second["run"]["id"]
        # Determinism: identical inputs yield identical values, distinct rows.
        assert first["assessment"]["assessment_value"] == second["assessment"]["assessment_value"]
        assert first["assessment"]["integrity_score"] == second["assessment"]["integrity_score"]
        assert first["priority"]["priority"] == second["priority"]["priority"]
        assert first["priority"]["priority_score"] == second["priority"]["priority_score"]

        history = client.get(
            f"/api/v1/fusion/CLAIM/{claim['id']}/history", params={"limit": 10, "offset": 0}
        ).json()
        assert history["total"] == 2
        assert len(history["items"]) == 2

        session = get_session()
        try:
            assessments = (
                session.query(IntegrityAssessment)
                .join(FusionRun, FusionRun.id == IntegrityAssessment.fusion_run_id)
                .filter(FusionRun.target_id == claim["id"])
                .all()
            )
            assert len(assessments) == 2
            statuses = {row.assessment_status for row in assessments}
            assert statuses == {"ACTIVE", "SUPERSEDED"}
        finally:
            session.close()

        latest = client.get(f"/api/v1/fusion/CLAIM/{claim['id']}").json()
        assert latest["run"]["id"] == second["run"]["id"]
        detail = client.get(f"/api/v1/fusion/runs/{first['run']['id']}").json()
        assert detail["run"]["id"] == first["run"]["id"]
        assert detail["assessment"]["assessment_status"] == "SUPERSEDED"
    finally:
        cleanup(str(user.id), project_ids, evidence_ids)


def test_configuration_versioning_pins_original_runs():
    user = setup_user()
    project_ids, evidence_ids = [], []
    try:
        project = api_create_project(str(user.id))
        project_ids.append(project["id"])
        claim = api_create_claim(project["id"])
        evidence = api_upload(image_bytes((14, 14, 14)), "fusion-v.jpg")
        evidence_ids.append(evidence["evidence_id"])
        link_evidence(evidence["evidence_id"], project["id"], claim["id"])
        api_edge("EVIDENCE", evidence["evidence_id"], "CLAIM", claim["id"], "SUPPORTS")

        first = fuse("CLAIM", claim["id"]).json()
        assert first["run"]["configuration_version"] == "v1"

        created = client.post(
            "/api/v1/fusion/configurations",
            json={
                "version": "v2-test",
                "name": "test config",
                "method_version": "fusion-v1",
                "weights": {"GRAPH_SUPPORT": 1.0, "GRAPH_CONTRADICT": 1.0},
                "thresholds": {"low_max": 0.25, "normal_max": 0.5, "high_max": 0.75},
                "priority": {"base": 0.0, "contributions": {}, "unknown_each": 0.0, "unknown_cap": 0.0},
                "signals": {"enabled": ["GRAPH_SUPPORT", "GRAPH_CONTRADICT"]},
            },
        )
        assert created.status_code == 200, created.text
        # Duplicate versions and invalid configs are rejected, not clamped.
        assert (
            client.post(
                "/api/v1/fusion/configurations",
                json={
                    "version": "v2-test", "name": "dup", "weights": {"GRAPH_SUPPORT": 0.5},
                    "thresholds": {"low_max": 0.25, "normal_max": 0.5, "high_max": 0.75},
                    "priority": {"base": 0.0},
                },
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/api/v1/fusion/configurations",
                json={
                    "version": "vbad", "name": "bad", "weights": {"GRAPH_SUPPORT": 5.0},
                    "thresholds": {"low_max": 0.25, "normal_max": 0.5, "high_max": 0.75},
                    "priority": {"base": 0.0},
                },
            ).status_code
            == 422
        )

        second = fuse("CLAIM", claim["id"], config_version="v2-test").json()
        assert second["run"]["configuration_version"] == "v2-test"
        assert second["assessment"]["integrity_score"] == 1.0

        session = get_session()
        try:
            first_run = session.query(FusionRun).filter_by(id=first["run"]["id"]).one()
            assert first_run.configuration_version == "v1"
        finally:
            session.close()
    finally:
        cleanup(str(user.id), project_ids, evidence_ids, config_versions=["v2-test"])


def test_invalid_targets_rejected():
    assert client.post("/api/v1/fusion/CLAIM/not-a-uuid", json={}).status_code == 422
    assert client.post("/api/v1/fusion/EVIDENCE/not-a-uuid", json={}).status_code == 422
    assert client.post(f"/api/v1/fusion/CLAIM/{uuid4()}", json={}).status_code == 404
    assert client.get(f"/api/v1/fusion/CLAIM/{uuid4()}").status_code == 404
    assert client.get(f"/api/v1/fusion/runs/{uuid4()}").status_code == 404
    assert client.post("/api/v1/fusion/PROJECT/not-a-uuid", json={}).status_code == 422


def test_evidence_target_with_duplicate_temporal_and_vision():
    from backend.services.duplicate_intelligence import analyze_duplicates
    from backend.services.fingerprinting import process_evidence
    from backend.services import evidence_graph as graph_service
    from backend.services.analysis_queue import AnalysisQueue
    from backend.workers.analysis_worker import process_message

    user = setup_user()
    project_ids, evidence_ids = [], []
    queue = AnalysisQueue()
    queue.clear()
    try:
        assert FIXTURE_PHOTO.exists(), "test-image.jpg fixture is required"
        payload = FIXTURE_PHOTO.read_bytes()
        first = client.post(
            "/api/v1/evidence", files={"file": ("multi-a.jpg", payload, "image/jpeg")}
        ).json()
        second = client.post(
            "/api/v1/evidence", files={"file": ("multi-b.jpg", payload, "image/jpeg")}
        ).json()
        evidence_ids.extend([first["evidence_id"], second["evidence_id"]])

        session = get_session()
        try:
            process_evidence(first["evidence_id"], session)
            process_evidence(second["evidence_id"], session)
            analyze_duplicates(first["evidence_id"], session)
            existing_metadata = (
                session.query(EvidenceMetadata)
                .filter_by(evidence_id=first["evidence_id"])
                .one()
            )
            existing_metadata.metadata_json = {
                **(existing_metadata.metadata_json or {}),
                "exif": {"EXIF DateTimeOriginal": "2024:01:01 10:00:00"},
            }
            session.commit()
        finally:
            session.close()

        job_id = client.post(
            "/api/v1/analysis/jobs",
            json={"evidence_id": first["evidence_id"], "job_type": "vision"},
        ).json()["job_id"]
        message = queue.dequeue(timeout=10)
        assert message is not None
        assert process_message(message, queue) == "completed"

        body = fuse("EVIDENCE", first["evidence_id"]).json()
        assert body["run"]["status"] == "COMPLETED"
        types = {item["signal_type"] for item in body["signals"]}
        # Real duplicate + temporal + vision outputs all consumed exactly once.
        assert "DUPLICATE_EXACT" in types
        assert "TEMPORAL_CONSISTENT" in types
        assert "VISION_OBSERVED" in types
        assert sum(1 for t in types if t.startswith("DUPLICATE_")) >= 1
        dup_signals = [item for item in body["signals"] if item["signal_type"].startswith("DUPLICATE_")]
        pair_signals = [
            item
            for item in dup_signals
            if set((item["raw_value"] or {}).get("evidence_pair", []))
            == {first["evidence_id"], second["evidence_id"]}
        ]
        # The (first, second) fact folds match row + edge to exactly one signal.
        assert len(pair_signals) == 1
        assert pair_signals[0]["signal_type"] == "DUPLICATE_EXACT"
        assert body["assessment"]["assessment_value"] == "MIXED"
        # Persisted outputs must equal the documented methodology applied to
        # the persisted signals (recomputed here; the shared dev database may
        # hold additional duplicate pairs from other fixtures).
        from backend.services.fusion import (
            DEFAULT_CONFIG_V1,
            compute_integrity_score,
            compute_priority,
            decide_assessment,
        )

        assert (
            decide_assessment(body["signals"])
            == body["assessment"]["assessment_value"]
        )
        assert (
            compute_integrity_score(body["signals"], DEFAULT_CONFIG_V1["weights"])
            == body["assessment"]["integrity_score"]
        )
        expected_priority, expected_score = compute_priority(
            body["signals"],
            DEFAULT_CONFIG_V1["priority"],
            DEFAULT_CONFIG_V1["thresholds"],
        )
        assert body["priority"]["priority"] == expected_priority
        assert body["priority"]["priority_score"] == expected_score

        # Deterministic rerun: identical values.
        again = fuse("EVIDENCE", first["evidence_id"]).json()
        assert again["assessment"]["assessment_value"] == body["assessment"]["assessment_value"]
        assert again["assessment"]["integrity_score"] == body["assessment"]["integrity_score"]
    finally:
        queue.clear()
        cleanup(str(user.id), project_ids, evidence_ids)


def test_cross_project_duplicate_consumed_without_ownership_change():
    from backend.services.duplicate_intelligence import analyze_duplicates
    from backend.services.fingerprinting import process_evidence
    from backend.services import evidence_graph as graph_service

    user = setup_user()
    project_ids, evidence_ids = [], []
    try:
        project_a = api_create_project(str(user.id), "fusion proj A")
        project_b = api_create_project(str(user.id), "fusion proj B")
        project_ids.extend([project_a["id"], project_b["id"]])
        payload = image_bytes((15, 15, 15))
        evidence_a = api_upload(payload, "x-a.jpg")
        evidence_b = api_upload(payload, "x-b.jpg")
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

        body = fuse("EVIDENCE", evidence_a["evidence_id"]).json()
        assert any(
            item["signal_type"] in ("DUPLICATE_EXACT", "DUPLICATE_SIMILAR")
            for item in body["signals"]
        )
        session = get_session()
        try:
            row = session.query(Evidence).filter_by(id=evidence_b["evidence_id"]).one()
            assert str(row.project_id) == project_b["id"]
        finally:
            session.close()
    finally:
        cleanup(str(user.id), project_ids, evidence_ids)
