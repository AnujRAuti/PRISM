import subprocess
import urllib.request
from pathlib import Path
from uuid import uuid4

import pytest

from backend.services.storage import ObjectNotFoundError, StorageError, StorageService


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def storage():
    service = StorageService()
    service.ensure_buckets()
    return service


@pytest.fixture
def object_context(storage):
    key = f"tests/{uuid4()}/original"
    payload = b"proof-of-action-storage-test"
    yield storage, key, payload
    storage.delete_object(storage.quarantine_bucket, key)
    storage.delete_object(storage.evidence_bucket, key.replace("tests/", "evidence/", 1))


def put_with_presigned_url(storage, key, payload):
    url = storage.create_presigned_upload_url(
        storage.quarantine_bucket, key, content_type="text/plain"
    )
    request = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "text/plain"}, method="PUT"
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        assert response.status == 200


def test_minio_connectivity_and_bucket_initialization(storage):
    storage.ensure_buckets()
    storage.ensure_buckets()
    assert storage.bucket_exists(storage.quarantine_bucket)
    assert storage.bucket_exists(storage.evidence_bucket)


def test_presigned_upload_and_metadata(object_context):
    storage, key, payload = object_context
    put_with_presigned_url(storage, key, payload)

    metadata = storage.get_object_metadata(storage.quarantine_bucket, key)
    assert metadata.key == key
    assert metadata.size == len(payload)
    assert metadata.content_type == "text/plain"
    assert storage.object_exists(storage.quarantine_bucket, key)


def test_presigned_download_returns_uploaded_bytes(object_context):
    storage, key, payload = object_context
    put_with_presigned_url(storage, key, payload)

    url = storage.create_presigned_download_url(storage.quarantine_bucket, key)
    with urllib.request.urlopen(url, timeout=10) as response:
        assert response.read() == payload


def test_object_persists_across_minio_restart(storage):
    key = f"tests/{uuid4()}/restart-persistence"
    payload = b"minio-restart-persistence-test"

    try:
        put_with_presigned_url(storage, key, payload)
        metadata_before = storage.get_object_metadata(storage.quarantine_bucket, key)

        subprocess.run(
            ["docker", "compose", "restart", "minio"],
            cwd=REPOSITORY_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )

        restarted_storage = StorageService()
        metadata_after = restarted_storage.get_object_metadata(
            restarted_storage.quarantine_bucket, key
        )
        download_url = restarted_storage.create_presigned_download_url(
            restarted_storage.quarantine_bucket, key
        )
        with urllib.request.urlopen(download_url, timeout=10) as response:
            assert response.read() == payload

        assert metadata_after == metadata_before
    finally:
        storage.delete_object(storage.quarantine_bucket, key)


def test_copy_promotes_object(object_context):
    storage, key, payload = object_context
    put_with_presigned_url(storage, key, payload)
    destination_key = key.replace("tests/", "evidence/", 1)

    storage.copy_object(
        storage.quarantine_bucket,
        key,
        storage.evidence_bucket,
        destination_key,
    )

    assert storage.object_exists(storage.evidence_bucket, destination_key)
    assert storage.get_object_metadata(storage.evidence_bucket, destination_key).size == len(payload)


def test_missing_object_raises_application_error(storage):
    with pytest.raises(ObjectNotFoundError):
        storage.get_object_metadata(storage.quarantine_bucket, f"tests/{uuid4()}/missing")


def test_unsafe_key_is_rejected(storage):
    with pytest.raises(StorageError, match="Storage object key is unsafe"):
        storage.object_exists(storage.quarantine_bucket, "../outside")