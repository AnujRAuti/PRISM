import json
import os
import subprocess
import time
import urllib.request
from uuid import uuid4

import pytest

from backend.core.config import settings
from backend.services.storage import ObjectNotFoundError, StorageError, StorageService

#: A run that wants the restart-persistence obligation executed must name the
#: MinIO container it created for itself. The variable is the only way this test
#: will ever restart anything.
DISPOSABLE_MINIO_CONTAINER_ENV = "POA_DISPOSABLE_MINIO_CONTAINER"


def _restart_target_container() -> str | None:
    return os.environ.get(DISPOSABLE_MINIO_CONTAINER_ENV, "").strip() or None


def _container_serves_configured_endpoint(container: str) -> bool:
    """True when ``container`` publishes the host port ``S3_ENDPOINT`` uses.

    Binding the armed name to the endpoint the assertions read from is what makes
    an accidental restart of some other (or the protected) container impossible:
    a name that does not answer for this configuration fails the check.
    """
    proc = subprocess.run(
        ["docker", "inspect", "-f", "{{json .NetworkSettings.Ports}}", container],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return False
    host_port = settings.s3_endpoint.rsplit(":", 1)[-1].split("/")[0]
    try:
        ports = json.loads(proc.stdout or "{}") or {}
    except json.JSONDecodeError:
        return False
    return any(
        binding.get("HostPort") == host_port
        for binding in (ports.get("9000/tcp") or [])
    )


def _wait_until_serving(service: StorageService, bucket: str, key: str, timeout: float) -> bool:
    """Poll until the endpoint answers again after a restart.

    Only the transport errors a shutting-down / still-starting S3 endpoint
    produces are tolerated; anything else is a real failure and propagates.
    """
    from botocore.exceptions import ConnectionError as BotoConnectionError
    from botocore.exceptions import HTTPClientError

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if service.object_exists(bucket, key):
                return True
        except (StorageError, BotoConnectionError, HTTPClientError):
            pass
        time.sleep(0.5)
    return False


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
    """Restart-persistence, executed only against storage this run owns.

    The obligation itself is unchanged: an object written before a MinIO restart
    must still be there, with the same metadata and bytes, afterwards. What
    changed is *which* server may be restarted. This test used to run
    ``docker compose restart minio`` from the repository root, which resolves to
    whatever compose project owns the checkout - i.e. the shared development
    stack - so any suite run could bounce the storage service other people were
    using. A restart is now performed only on the container named by
    ``POA_DISPOSABLE_MINIO_CONTAINER``, and only after that name is proved to be
    the endpoint under test. Unarmed, the check reports as skipped rather than
    touching a service it does not own.
    """
    container = _restart_target_container()
    if container is None:
        pytest.skip(
            f"{DISPOSABLE_MINIO_CONTAINER_ENV} is not set, so there is no MinIO this "
            "test owns. Restarting the shared compose stack from a test is not allowed; "
            "point the variable at this run's disposable MinIO container to execute the "
            "check."
        )
    assert _container_serves_configured_endpoint(container), (
        f"{container} does not publish the host port used by S3_ENDPOINT "
        f"({settings.s3_endpoint}); refusing to restart a container that is not the "
        "storage service under test."
    )

    key = f"tests/{uuid4()}/restart-persistence"
    payload = b"minio-restart-persistence-test"

    try:
        put_with_presigned_url(storage, key, payload)
        metadata_before = storage.get_object_metadata(storage.quarantine_bucket, key)

        subprocess.run(
            ["docker", "restart", container],
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
        restarted_storage = StorageService()
        assert _wait_until_serving(
            restarted_storage, restarted_storage.quarantine_bucket, key, timeout=90
        ), f"{container} did not resume serving within its deadline"

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