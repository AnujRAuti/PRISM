#!/usr/bin/env python3
"""
Test script to verify authorization on vision and temporal endpoints
"""
import os
import sys
from io import BytesIO
from uuid import uuid4

from PIL import Image
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.db.models import User
from backend.db.session import get_session
from backend.services import authorization as auth_service

client = TestClient(app)

def image_bytes(color=(100, 170, 240)) -> bytes:
    output = BytesIO()
    Image.new("RGB", (16, 16), color=color).save(output, format="JPEG")
    return output.getvalue()

def headers_for(user_id: str) -> dict:
    return {"Authorization": f"Bearer dev-user-{user_id}"}

def make_user(username: str) -> User:
    session = get_session()
    try:
        user = User(username=f"{username}-{uuid4().hex[:8]}",
                    email=f"{uuid4().hex[:8]}@example.com")
        session.add(user)
        session.commit()
        session.refresh(user)
        session.expunge(user)
        return user
    finally:
        session.close()

def assign(user_id: str, role: str, scope: str, scope_id: str | None = None):
    session = get_session()
    try:
        kwargs: dict = {}
        if scope == "ORGANIZATION":
            kwargs["organization_id"] = scope_id
        elif scope == "ORGANIZATIONAL_UNIT":
            kwargs["organizational_unit_id"] = scope_id
        elif scope == "PROJECT":
            kwargs["project_id"] = scope_id
        row, _ = auth_service.assign_role(
            session, user_id=user_id, role_name=role, scope_type=scope, **kwargs)
        session.commit()
        return row
    finally:
        session.close()

def cleanup(user_ids, project_ids, evidence_ids):
    from backend.services.storage import StorageService
    storage = StorageService()
    session = get_session()
    try:
        keys = [
            row[0] for row in session.query(Evidence.storage_key)
            .filter(Evidence.id.in_(evidence_ids)).all()
        ] if evidence_ids else []
        for key in keys:
            if storage.object_exists(storage.quarantine_bucket, key):
                storage.delete_object(storage.quarantine_bucket, key)
        if evidence_ids:
            session.query(Evidence).filter(Evidence.id.in_(evidence_ids)).delete(
                synchronize_session=False)
        if user_ids:
            session.query(User).filter(User.id.in_(user_ids)).delete(
                synchronize_session=False)
        session.commit()
    finally:
        session.close()

def setup_basic_evidence():
    """Create a piece of evidence and run vision analysis on it"""
    # Create evidence
    evidence_data = client.post(
        "/api/v1/evidence",
        files={"file": ("test.jpg", image_bytes(), "image/jpeg")}
    )
    assert evidence_data.status_code == 201
    evidence = evidence_data.json()
    
    # Create analysis job for vision
    job_data = client.post(
        "/api/v1/analysis/jobs",
        json={"evidence_id": evidence["evidence_id"], "job_type": "vision"}
    )
    assert job_data.status_code == 202
    job_id = job_data.json()["job_id"]
    
    # In a real test we'd wait for the job to complete, but for auth testing
    # we just need the evidence to exist
    return evidence["evidence_id"]

def test_vision_endpoint_authorization():
    """Test authorization on the vision endpoint"""
    print("Testing vision endpoint authorization...")
    
    # Setup: create evidence and user
    evidence_id = setup_basic_evidence()
    user = make_user("test-user")
    
    try:
        # Test 1: Unauthenticated request should be rejected
        response = client.get(f"/api/v1/evidence/{evidence_id}/vision")
        assert response.status_code in (401, 403), f"Expected 401/403 for unauthenticated request, got {response.status_code}"
        print("✓ Unauthenticated request correctly rejected")
        
        # Test 2: Authenticated user with no permissions should be rejected
        response = client.get(f"/api/v1/evidence/{evidence_id}/vision", headers=headers_for(str(user.id)))
        assert response.status_code in (401, 403), f"Expected 401/403 for non-permissioned user, got {response.status_code}"
        print("✓ Non-permissioned authenticated request correctly rejected")
        
        print("✓ Vision endpoint authorization tests completed")
        
    finally:
        cleanup([str(user.id)], [], [evidence_id])

def test_temporal_endpoint_authorization():
    """Test authorization on the temporal endpoint"""
    print("Testing temporal endpoint authorization...")
    
    # Setup: create evidence and user
    evidence_id = setup_basic_evidence()
    user = make_user("test-user-temporal")
    
    try:
        # Test 1: Unauthenticated request should be rejected
        response = client.post(f"/api/v1/analysis/temporal/{evidence_id}", json={})
        assert response.status_code in (401, 403), f"Expected 401/403 for unauthenticated request, got {response.status_code}"
        print("✓ Unauthenticated request correctly rejected")
        
        # Test 2: Authenticated user with no permissions should be rejected
        response = client.post(f"/api/v1/analysis/temporal/{evidence_id}", json={}, headers=headers_for(str(user.id)))
        assert response.status_code in (401, 403), f"Expected 401/403 for non-permissioned user, got {response.status_code}"
        print("✓ Non-permissioned authenticated request correctly rejected")
        
        print("✓ Temporal endpoint authorization tests completed")
        
    finally:
        cleanup([str(user.id)], [], [evidence_id])

if __name__ == "__main__":
    # Set the test database URL
    os.environ["TEST_DATABASE_URL"] = "postgresql+psycopg2://postgres:postgres@localhost:5432/pofa_test"
    
    try:
        test_vision_endpoint_authorization()
        test_temporal_endpoint_authorization()
        print("\n✅ All authorization tests completed!")
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
