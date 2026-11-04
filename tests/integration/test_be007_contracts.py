from io import BytesIO
from uuid import uuid4

from fastapi.testclient import TestClient
from PIL import Image

from backend.app.main import app
from backend.db.models import Activity, Claim, Evidence, Project, User
from backend.db.session import get_session
from backend.services.storage import StorageService


client = TestClient(app)


def image_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (8, 8), color=(30, 90, 160)).save(output, format="JPEG")
    return output.getvalue()


def setup_user() -> User:
    session = get_session()
    user = User(username=f"be007-{uuid4()}", email=f"{uuid4()}@example.com")
    session.add(user)
    session.commit()
    session.refresh(user)
    session.close()
    return user


def upload_evidence() -> dict:
    response = client.post(
        "/api/v1/evidence",
        files={"file": ("be007.jpg", image_bytes(), "image/jpeg")},
    )
    assert response.status_code == 201
    return response.json()


def cleanup(user_id: str, project_ids: list[str], evidence_ids: list[str]) -> None:
    storage = StorageService()
    session = get_session()
    storage_keys = [
        row[0]
        for row in session.query(Evidence.storage_key).filter(Evidence.id.in_(evidence_ids)).all()
    ]
    for storage_key in storage_keys:
        if storage.object_exists(storage.quarantine_bucket, storage_key):
            storage.delete_object(storage.quarantine_bucket, storage_key)
    session.query(Activity).filter(Activity.project_id.in_(project_ids)).delete(synchronize_session=False)
    session.query(Claim).filter(Claim.project_id.in_(project_ids)).delete(synchronize_session=False)
    session.query(Evidence).filter(Evidence.id.in_(evidence_ids)).update(
        {Evidence.project_id: None, Evidence.claim_id: None}, synchronize_session=False
    )
    session.query(Evidence).filter(Evidence.id.in_(evidence_ids)).delete(synchronize_session=False)
    session.query(Project).filter(Project.id.in_(project_ids)).delete(synchronize_session=False)
    session.query(User).filter(User.id == user_id).delete(synchronize_session=False)
    session.commit()
    session.close()


def test_project_activity_claim_contracts_and_references():
    user = setup_user()
    project_ids: list[str] = []
    try:
        project_response = client.post(
            "/api/v1/projects",
            json={"name": "BE-007 project", "owner_id": str(user.id)},
        )
        assert project_response.status_code == 201
        project = project_response.json()
        project_ids.append(project["id"])

        activity_response = client.post(
            f"/api/v1/projects/{project['id']}/activities",
            json={"actor_id": str(user.id), "verb": "evidence_uploaded", "details": {"ok": True}},
        )
        assert activity_response.status_code == 201
        assert activity_response.json()["project_id"] == project["id"]

        claim_response = client.post(
            f"/api/v1/projects/{project['id']}/claims",
            json={"claimant_id": str(user.id), "title": "Work complete", "description": "Initial"},
        )
        assert claim_response.status_code == 201
        claim = claim_response.json()
        claim_update = client.patch(
            f"/api/v1/projects/{project['id']}/claims/{claim['id']}",
            json={"description": "Updated"},
        )
        assert claim_update.status_code == 200
        assert claim_update.json()["description"] == "Updated"

        listing = client.get(f"/api/v1/projects/{project['id']}/activities?limit=1&offset=0")
        assert listing.status_code == 200
        assert listing.json()["total"] == 1
    finally:
        cleanup(str(user.id), project_ids, [])


def test_evidence_context_cross_project_conflict_and_location():
    user = setup_user()
    project_ids: list[str] = []
    evidence_ids: list[str] = []
    try:
        project_a = client.post("/api/v1/projects", json={"name": "A", "owner_id": str(user.id)}).json()
        project_b = client.post("/api/v1/projects", json={"name": "B", "owner_id": str(user.id)}).json()
        project_ids.extend([project_a["id"], project_b["id"]])
        claim_a = client.post(
            f"/api/v1/projects/{project_a['id']}/claims",
            json={"title": "Claim A"},
        ).json()
        evidence = upload_evidence()
        evidence_ids.append(evidence["evidence_id"])

        conflict = client.patch(
            f"/api/v1/evidence/{evidence['evidence_id']}/context",
            json={"project_id": project_b["id"], "claim_id": claim_a["id"]},
        )
        assert conflict.status_code == 409

        context = client.patch(
            f"/api/v1/evidence/{evidence['evidence_id']}/context",
            json={"project_id": project_b["id"]},
        )
        assert context.status_code == 200
        location = client.patch(
            f"/api/v1/evidence/{evidence['evidence_id']}/location",
            json={"latitude": 18.5204, "longitude": 73.8567},
        )
        assert location.status_code == 200
        assert location.json()["location"] == {"latitude": 18.5204, "longitude": 73.8567}

        invalid = client.patch(
            f"/api/v1/evidence/{evidence['evidence_id']}/location",
            json={"latitude": 91, "longitude": 73.8567},
        )
        assert invalid.status_code == 422
    finally:
        cleanup(str(user.id), project_ids, evidence_ids)


def test_nearby_queries_use_postgis_radius_and_project_scope():
    user = setup_user()
    project_ids: list[str] = []
    evidence_ids: list[str] = []
    try:
        project = client.post("/api/v1/projects", json={"name": "Nearby", "owner_id": str(user.id)}).json()
        other = client.post("/api/v1/projects", json={"name": "Other", "owner_id": str(user.id)}).json()
        project_ids.extend([project["id"], other["id"]])
        for latitude, longitude, project_id in [
            (18.5204, 73.8567, project["id"]),
            (18.5205, 73.8568, project["id"]),
            (18.6000, 73.9000, project["id"]),
            (18.5204, 73.8567, other["id"]),
        ]:
            evidence = upload_evidence()
            evidence_ids.append(evidence["evidence_id"])
            assert client.patch(
                f"/api/v1/evidence/{evidence['evidence_id']}/context",
                json={"project_id": project_id},
            ).status_code == 200
            assert client.patch(
                f"/api/v1/evidence/{evidence['evidence_id']}/location",
                json={"latitude": latitude, "longitude": longitude},
            ).status_code == 200

        nearby = client.get(
            "/api/v1/evidence/nearby?latitude=18.5204&longitude=73.8567&radius=1000"
        )
        assert nearby.status_code == 200
        assert nearby.json()["total"] == 3
        distances = [item["distance_meters"] for item in nearby.json()["items"]]
        assert distances == sorted(distances)

        scoped = client.get(
            f"/api/v1/projects/{project['id']}/evidence/nearby?latitude=18.5204&longitude=73.8567&radius=1000"
        )
        assert scoped.status_code == 200
        assert scoped.json()["total"] == 2
        assert all(item["project_id"] == project["id"] for item in scoped.json()["items"])

        invalid_radius = client.get(
            "/api/v1/evidence/nearby?latitude=18.5204&longitude=73.8567&radius=100001"
        )
        assert invalid_radius.status_code == 422
    finally:
        cleanup(str(user.id), project_ids, evidence_ids)