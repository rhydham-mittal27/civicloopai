from __future__ import annotations

import hashlib
import os
import posixpath
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import quote


class StorageError(Exception):
    """Base error raised by object-storage adapters."""


class StorageObjectNotFound(StorageError):
    pass


class StorageIntegrityError(StorageError):
    pass


class InvalidStorageKey(StorageError):
    pass


@dataclass(frozen=True)
class StoredObject:
    key: str
    content_type: str
    size_bytes: int
    sha256: str
    etag: str | None = None


class ObjectStorageAdapter(Protocol):
    def put(self, key: str, content: bytes, content_type: str) -> StoredObject: ...

    def get(self, key: str) -> bytes: ...

    def delete(self, key: str) -> None: ...

    def exists(self, key: str) -> bool: ...

    def create_read_url(self, key: str, expires_seconds: int = 900) -> str: ...


def _validate_key(key: str) -> str:
    normalized = posixpath.normpath(key).replace("\\", "/")
    if (
        not key
        or normalized in {".", ".."}
        or normalized.startswith("../")
        or normalized.startswith("/")
        or ":" in normalized
    ):
        raise InvalidStorageKey(
            "Storage keys must be relative and cannot escape the storage root"
        )
    return normalized


def _stored_object(key: str, content: bytes, content_type: str) -> StoredObject:
    return StoredObject(
        key=key,
        content_type=content_type,
        size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
    )


class InMemoryObjectStorage:
    """Deterministic storage backend for tests and lightweight local runs."""

    def __init__(self) -> None:
        self._objects: dict[str, tuple[bytes, str]] = {}

    def put(self, key: str, content: bytes, content_type: str) -> StoredObject:
        safe_key = _validate_key(key)
        self._objects[safe_key] = (content, content_type)
        return _stored_object(safe_key, content, content_type)

    def get(self, key: str) -> bytes:
        safe_key = _validate_key(key)
        if safe_key not in self._objects:
            raise StorageObjectNotFound(safe_key)
        return self._objects[safe_key][0]

    def delete(self, key: str) -> None:
        safe_key = _validate_key(key)
        if safe_key not in self._objects:
            raise StorageObjectNotFound(safe_key)
        del self._objects[safe_key]

    def exists(self, key: str) -> bool:
        return _validate_key(key) in self._objects

    def create_read_url(self, key: str, expires_seconds: int = 900) -> str:
        if expires_seconds <= 0 or not self.exists(key):
            raise ValueError("A positive expiry and existing object are required")
        return f"memory://{quote(_validate_key(key))}"


class LocalFilesystemObjectStorage:
    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        safe_key = _validate_key(key)
        path = (self.root / safe_key).resolve()
        if self.root not in path.parents:
            raise InvalidStorageKey("Storage key escapes the configured root")
        return path

    def put(self, key: str, content: bytes, content_type: str) -> StoredObject:
        safe_key = _validate_key(key)
        path = self._path(safe_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=path.parent, delete=False
            ) as temporary:
                temporary.write(content)
                temporary.flush()
                os.fsync(temporary.fileno())
                temporary_path = Path(temporary.name)
            os.replace(temporary_path, path)
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()
        return _stored_object(safe_key, content, content_type)

    def get(self, key: str) -> bytes:
        path = self._path(key)
        if not path.is_file():
            raise StorageObjectNotFound(_validate_key(key))
        return path.read_bytes()

    def delete(self, key: str) -> None:
        path = self._path(key)
        if not path.is_file():
            raise StorageObjectNotFound(_validate_key(key))
        path.unlink()

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def create_read_url(self, key: str, expires_seconds: int = 900) -> str:
        if expires_seconds <= 0 or not self.exists(key):
            raise ValueError("A positive expiry and existing object are required")
        return f"local://{quote(_validate_key(key))}"


class S3ObjectStorage:
    """S3-compatible adapter with a lazy boto3 dependency."""

    def __init__(
        self,
        bucket: str,
        region: str | None = None,
        endpoint_url: str | None = None,
        client: Any = None,
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
    ) -> None:
        if not bucket:
            raise ValueError("S3 bucket is required")
        if client is None:
            try:
                import boto3
            except ImportError as error:
                raise StorageError(
                    "Install the storage extra to use S3ObjectStorage"
                ) from error
            kwargs: dict[str, Any] = {"region_name": region, "endpoint_url": endpoint_url}
            if access_key_id:
                kwargs["aws_access_key_id"] = access_key_id
            if secret_access_key:
                kwargs["aws_secret_access_key"] = secret_access_key
            client = boto3.client("s3", **kwargs)
        self.bucket = bucket
        self.client = client

    def put(self, key: str, content: bytes, content_type: str) -> StoredObject:
        safe_key = _validate_key(key)
        digest = hashlib.sha256(content).hexdigest()
        self.client.put_object(
            Bucket=self.bucket,
            Key=safe_key,
            Body=content,
            ContentType=content_type,
            Metadata={"sha256": digest},
        )
        return _stored_object(safe_key, content, content_type)

    def get(self, key: str) -> bytes:
        safe_key = _validate_key(key)
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=safe_key)
            return response["Body"].read()
        except Exception as error:
            raise StorageObjectNotFound(safe_key) from error

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=_validate_key(key))

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=_validate_key(key))
            return True
        except Exception:
            return False

    def create_read_url(self, key: str, expires_seconds: int = 900) -> str:
        if not 1 <= expires_seconds <= 86_400:
            raise ValueError("Expiry must be between 1 second and 24 hours")
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": _validate_key(key)},
            ExpiresIn=expires_seconds,
        )


def create_storage_from_env() -> ObjectStorageAdapter:
    backend = os.getenv("CIVICLOOP_STORAGE_BACKEND", "memory").lower()
    if backend == "memory":
        return InMemoryObjectStorage()
    if backend == "local":
        return LocalFilesystemObjectStorage(
            os.getenv("CIVICLOOP_STORAGE_ROOT", "./var/uploads")
        )
    if backend == "s3":
        return S3ObjectStorage(
            os.environ["CIVICLOOP_STORAGE_BUCKET"],
            region=os.getenv("CIVICLOOP_STORAGE_REGION"),
            endpoint_url=os.getenv("CIVICLOOP_STORAGE_ENDPOINT"),
            access_key_id=os.getenv("CIVICLOOP_STORAGE_ACCESS_KEY")
            or os.getenv("AWS_ACCESS_KEY_ID"),
            secret_access_key=os.getenv("CIVICLOOP_STORAGE_SECRET_KEY")
            or os.getenv("AWS_SECRET_ACCESS_KEY"),
        )
    raise ValueError(f"Unsupported storage backend: {backend}")
