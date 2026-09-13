"""S3-compatible object storage abstraction for MinIO and production S3."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import boto3
from botocore.client import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError, EndpointConnectionError

from backend.core.config import settings


class StorageError(RuntimeError):
    """Base error for storage failures."""


class ObjectNotFoundError(StorageError):
    """Raised when an object does not exist."""


class BucketNotFoundError(StorageError):
    """Raised when a configured storage bucket does not exist."""


class PresignedUrlError(StorageError):
    """Raised when a presigned URL cannot be generated."""


class StorageConnectionError(StorageError):
    """Raised when the storage provider cannot be reached."""


@dataclass(frozen=True)
class ObjectMetadata:
    key: str
    size: int
    content_type: str | None
    etag: str | None
    last_modified: datetime | None


class StorageService:
    """Provider-neutral storage operations for the application."""

    def __init__(self, client: Any | None = None) -> None:
        self._client = client or boto3.client(
            "s3",
            endpoint_url=self._endpoint_url(),
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name=settings.s3_region,
            config=BotoConfig(
                signature_version="s3v4",
                retries={"max_attempts": 3, "mode": "standard"},
                s3={"addressing_style": "path"},
            ),
        )

    @property
    def client(self) -> Any:
        return self._client

    @property
    def quarantine_bucket(self) -> str:
        return settings.s3_quarantine_bucket

    @property
    def evidence_bucket(self) -> str:
        return settings.s3_evidence_bucket

    def ensure_buckets(self) -> None:
        for bucket in (self.quarantine_bucket, self.evidence_bucket):
            try:
                self._client.head_bucket(Bucket=bucket)
            except ClientError as error:
                if self._error_code(error) not in {"404", "NoSuchBucket", "NotFound"}:
                    raise self._translate(error, bucket=bucket) from error
                try:
                    params: dict[str, Any] = {"Bucket": bucket}
                    if settings.s3_region != "us-east-1":
                        params["CreateBucketConfiguration"] = {
                            "LocationConstraint": settings.s3_region
                        }
                    self._client.create_bucket(**params)
                except ClientError as create_error:
                    if self._error_code(create_error) not in {
                        "BucketAlreadyOwnedByYou",
                        "BucketAlreadyExists",
                    }:
                        raise self._translate(create_error, bucket=bucket) from create_error
            except (EndpointConnectionError, BotoCoreError) as error:
                raise StorageConnectionError("Unable to connect to object storage") from error

    def create_presigned_upload_url(
        self,
        bucket: str,
        key: str,
        *,
        content_type: str | None = None,
        expires_in: int = 900,
    ) -> str:
        params: dict[str, Any] = {"Bucket": self._bucket(bucket), "Key": self._key(key)}
        if content_type:
            params["ContentType"] = content_type
        try:
            return self._client.generate_presigned_url(
                "put_object", Params=params, ExpiresIn=expires_in, HttpMethod="PUT"
            )
        except (ClientError, BotoCoreError) as error:
            raise PresignedUrlError("Unable to generate an upload URL") from error

    def create_presigned_download_url(
        self, bucket: str, key: str, *, expires_in: int = 900
    ) -> str:
        params = {"Bucket": self._bucket(bucket), "Key": self._key(key)}
        try:
            return self._client.generate_presigned_url(
                "get_object", Params=params, ExpiresIn=expires_in, HttpMethod="GET"
            )
        except (ClientError, BotoCoreError) as error:
            raise PresignedUrlError("Unable to generate a download URL") from error

    def put_object(self, bucket: str, key: str, data: bytes, *, content_type: str) -> None:
        try:
            self._client.put_object(
                Bucket=self._bucket(bucket),
                Key=self._key(key),
                Body=data,
                ContentType=content_type,
            )
        except ClientError as error:
            raise self._translate(error, bucket=bucket, key=key) from error
        except (EndpointConnectionError, BotoCoreError) as error:
            raise StorageConnectionError("Unable to connect to object storage") from error

    def bucket_exists(self, bucket: str) -> bool:
        bucket_name = self._bucket(bucket)
        try:
            self._client.head_bucket(Bucket=bucket_name)
            return True
        except ClientError as error:
            if self._error_code(error) in {"403", "404", "NoSuchBucket", "NotFound"}:
                return False
            raise self._translate(error, bucket=bucket_name) from error
        except (EndpointConnectionError, BotoCoreError) as error:
            raise StorageConnectionError("Unable to connect to object storage") from error

    def object_exists(self, bucket: str, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket(bucket), Key=self._key(key))
            return True
        except ClientError as error:
            if self._error_code(error) in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise self._translate(error, bucket=bucket, key=key) from error
        except (EndpointConnectionError, BotoCoreError) as error:
            raise StorageConnectionError("Unable to connect to object storage") from error

    def get_object_metadata(self, bucket: str, key: str) -> ObjectMetadata:
        bucket_name = self._bucket(bucket)
        object_key = self._key(key)
        try:
            response = self._client.head_object(Bucket=bucket_name, Key=object_key)
            return ObjectMetadata(
                key=object_key,
                size=response["ContentLength"],
                content_type=response.get("ContentType"),
                etag=response.get("ETag"),
                last_modified=response.get("LastModified"),
            )
        except ClientError as error:
            raise self._translate(error, bucket=bucket_name, key=object_key) from error
        except (EndpointConnectionError, BotoCoreError) as error:
            raise StorageConnectionError("Unable to connect to object storage") from error

    def copy_object(
        self,
        source_bucket: str,
        source_key: str,
        destination_bucket: str,
        destination_key: str,
        *,
        delete_source: bool = False,
    ) -> None:
        source = {"Bucket": self._bucket(source_bucket), "Key": self._key(source_key)}
        destination_bucket_name = self._bucket(destination_bucket)
        destination_key_value = self._key(destination_key)
        try:
            self._client.copy_object(
                Bucket=destination_bucket_name,
                Key=destination_key_value,
                CopySource=source,
            )
            if delete_source:
                self._client.delete_object(**source)
        except ClientError as error:
            raise self._translate(error, bucket=destination_bucket_name, key=destination_key_value) from error
        except (EndpointConnectionError, BotoCoreError) as error:
            raise StorageConnectionError("Unable to connect to object storage") from error

    def delete_object(self, bucket: str, key: str) -> None:
        try:
            self._client.delete_object(Bucket=self._bucket(bucket), Key=self._key(key))
        except ClientError as error:
            raise self._translate(error, bucket=bucket, key=key) from error
        except (EndpointConnectionError, BotoCoreError) as error:
            raise StorageConnectionError("Unable to connect to object storage") from error

    def quarantine_key(self, evidence_id: str) -> str:
        return f"quarantine/{self._segment(evidence_id)}/original"

    def evidence_key(self, evidence_id: str) -> str:
        return f"evidence/{self._segment(evidence_id)}/original"

    @staticmethod
    def _endpoint_url() -> str | None:
        endpoint = settings.s3_endpoint.strip()
        if not endpoint:
            return None
        if "://" not in endpoint:
            scheme = "https" if settings.s3_use_ssl else "http"
            return f"{scheme}://{endpoint}"
        return endpoint

    def _bucket(self, bucket: str) -> str:
        allowed = {self.quarantine_bucket, self.evidence_bucket}
        if bucket not in allowed:
            raise StorageError("Storage bucket is not configured for application use")
        return bucket

    @staticmethod
    def _key(key: str) -> str:
        if not key or key.startswith(("/", "\\")) or "\x00" in key:
            raise StorageError("Storage object key is unsafe")
        parts = key.replace("\\", "/").split("/")
        if any(part in {"", ".", ".."} for part in parts):
            raise StorageError("Storage object key is unsafe")
        return "/".join(parts)

    @staticmethod
    def _segment(value: str) -> str:
        if not value or value in {".", ".."} or any(char in value for char in "/\\\x00"):
            raise StorageError("Storage identifier is unsafe")
        return value

    @staticmethod
    def _error_code(error: ClientError) -> str:
        return str(error.response.get("Error", {}).get("Code", ""))

    @staticmethod
    def _translate(error: ClientError, *, bucket: str, key: str | None = None) -> StorageError:
        code = str(error.response.get("Error", {}).get("Code", ""))
        if code in {"404", "NoSuchKey", "NotFound"} and key is not None:
            return ObjectNotFoundError(f"Object not found: {bucket}/{key}")
        if code in {"404", "NoSuchBucket", "NotFound"}:
            return BucketNotFoundError(f"Bucket not found: {bucket}")
        return StorageError("Object storage operation failed")