# Object Storage Adapter Plan

## 1. Goal

Add a provider-independent object-storage layer for CivicLoopAI images and model artifacts.

The adapter must support:

- Resident and field-worker incident photographs
- Before-cleanup and after-cleanup evidence
- Stable storage keys recorded in `MediaAsset.storage_key`
- SHA-256 integrity checks recorded in `MediaAsset.sha256`
- Local development without cloud credentials
- S3-compatible production storage without changing application services

## 2. Current Gap

`MediaAssetService` currently validates image bytes and writes a storage key to the database, but it does not upload or delete the actual object. The next change should inject an object-storage adapter into that service.

Current flow:

```text
image bytes -> MediaAssetService -> MediaAssetRepository
```

Target flow:

```text
image bytes -> validate/hash -> ObjectStorageAdapter.put -> MediaAssetRepository.add
```

Deletion should remove the object only after the database record and authorization checks are valid.

## 3. Adapter Contract

Create `civicloop/storage.py` with a provider-neutral protocol:

```python
class ObjectStorageAdapter(Protocol):
    def put(self, key: str, content: bytes, content_type: str) -> StoredObject: ...
    def get(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...
    def exists(self, key: str) -> bool: ...
    def create_read_url(self, key: str, expires_seconds: int = 900) -> str: ...
```

`StoredObject` should contain:

- `key`
- `content_type`
- `size_bytes`
- `sha256`
- optional provider `etag`

The adapter must not know about incidents, users, verification, or SQLAlchemy models.

## 4. Implementations

### 4.1 Local filesystem adapter

Use for tests and local development.

- Root directory configured by `CIVICLOOP_STORAGE_ROOT`.
- Create parent directories from the generated key.
- Write bytes atomically using a temporary file followed by rename.
- Refuse path traversal and absolute keys.
- Generate read URLs as controlled application download URLs or local file references only in development.
- Delete only files inside the configured root.

### 4.2 S3-compatible adapter

Use for pilot and production environments.

- Configure endpoint, bucket, region, and credentials through environment variables.
- Support AWS S3 and compatible providers such as MinIO.
- Use server-side encryption where supported.
- Upload with the validated content type and SHA-256 metadata.
- Generate short-lived presigned read URLs.
- Never expose bucket credentials to the browser.

Recommended environment variables:

```text
CIVICLOOP_STORAGE_BACKEND=local
CIVICLOOP_STORAGE_ROOT=./var/uploads
CIVICLOOP_STORAGE_BUCKET=
CIVICLOOP_STORAGE_ENDPOINT=
CIVICLOOP_STORAGE_REGION=
CIVICLOOP_STORAGE_ACCESS_KEY=
CIVICLOOP_STORAGE_SECRET_KEY=
```

Secrets must only exist in local environment configuration or a secret manager, never in source control.

## 5. Key and Metadata Policy

Use opaque, deterministic keys that do not expose email addresses or personal data:

```text
incidents/{incident_id}/{asset_id}/{sha256}.{extension}
```

The asset ID should be created before upload so the key is stable. If the current model default is generated only during flush, generate the ID in the service or use a temporary key and update the record after upload.

Persist these values in `MediaAsset`:

- `storage_key`: provider-independent object key
- `content_type`: validated MIME type
- `sha256`: content integrity hash
- `captured_at`: source capture timestamp when available
- `is_after_cleanup`: before/after evidence classification

Do not store raw image bytes in SQLAlchemy JSON or relational columns.

## 6. Media Service Changes

Update `MediaAssetService` constructor:

```python
MediaAssetService(assets, incidents, users, audit, storage)
```

Update `store_for_incident`:

1. Confirm the incident exists.
2. Validate image content type, size, and decodability.
3. Calculate SHA-256.
4. Create a stable object key.
5. Call `storage.put(key, image, content_type)`.
6. Confirm returned hash/size matches the request.
7. Persist `MediaAsset` through `MediaAssetRepository.add`.
8. If database persistence fails after upload, delete the orphaned object and re-raise.
9. Return the persisted media asset.

Update `delete_asset`:

1. Authorize the admin through `UserRepository`.
2. Load the asset through `MediaAssetRepository.get`.
3. Call `storage.delete(asset.storage_key)`.
4. Delete the database record through `MediaAssetRepository.delete`.
5. Write the audit event.

For stricter consistency, use a deletion status or retry job if the provider delete succeeds but the database transaction fails.

## 7. API Integration

The API should not send storage credentials to clients.

- Upload route: `POST /api/v1/incidents/{incident_id}/media`
- Read metadata route: `GET /api/v1/incidents/{incident_id}/media`
- Download route: `GET /api/v1/media/{asset_id}/content`
- Admin delete route: `DELETE /api/v1/media/{asset_id}`

The download route should:

1. Check authentication and incident visibility.
2. Load the `MediaAsset` from `MediaAssetRepository`.
3. Call `storage.create_read_url` or stream through the API.
4. Return a short-lived URL or response stream.

Reporters should only access their own permitted evidence. Supervisors may access evidence for incidents in their operational scope. Admins may access all evidence.

## 8. Security Requirements

- Limit upload size, for example 10 MB per image in the MVP.
- Allow only configured image MIME types.
- Inspect file signatures instead of trusting only the filename or header.
- Strip or separately control EXIF data if GPS privacy requires it.
- Avoid putting personal data in storage keys.
- Use private buckets and short-lived read URLs.
- Encrypt data in transit and at rest.
- Add malware scanning before exposing uploaded objects where pilot policy requires it.
- Apply per-user and per-incident upload limits.
- Log object operations without logging image bytes, credentials, or signed URLs.

## 9. Failure Handling

| Failure | Behavior |
| --- | --- |
| Invalid image | Return `400`; do not call storage or repository. |
| Storage upload failure | Return retryable error; do not create `MediaAsset`. |
| Database failure after upload | Delete orphaned object and retry transaction. |
| Missing object during download | Return `404` and record an operational error. |
| Storage delete failure | Keep database record, return retryable error, and enqueue cleanup. |
| Provider timeout | Retry with bounded exponential backoff in a worker. |
| Hash mismatch | Delete uploaded object and reject the operation. |

## 10. Tests

### Unit tests

- Local adapter writes and reads bytes.
- Local adapter rejects traversal keys.
- Local adapter deletes only within its root.
- S3 adapter maps provider errors to storage exceptions.
- SHA-256 and content type are preserved.
- Presigned URL expiry is bounded.

### Service tests

- Successful upload creates both object and `MediaAsset`.
- Invalid image creates neither object nor database row.
- Database failure cleans up an uploaded object.
- Delete requires admin role.
- Delete removes the object and database row.
- Before and after assets retain their classification.

### API tests

- Multipart upload returns `201`.
- Oversized and unsupported files return `400`.
- Unauthorized download returns `403`.
- Missing asset returns `404`.
- Signed URL is not exposed to unauthorized users.

## 11. Delivery Sequence

1. Add `StoredObject`, adapter protocol, and storage-specific exceptions.
2. Implement the local filesystem adapter.
3. Refactor `MediaAssetService` to call the adapter.
4. Add object-storage unit and service tests.
5. Add the S3-compatible adapter behind `CIVICLOOP_STORAGE_BACKEND`.
6. Add media download/read URL API route.
7. Add cleanup retry handling and operational metrics.
8. Document local setup and production bucket policy in the README.

## 12. Acceptance Criteria

- The same `MediaAssetService` works with local and S3-compatible storage.
- Every persisted asset has a valid key, content type, and SHA-256 hash.
- A failed upload never leaves a database row without an object.
- A failed database write does not leave an unmanaged object.
- Images are private by default and accessed through authorization-controlled short-lived URLs.
- Before/after evidence remains linked to the same incident and is auditable.
- Tests cover successful, invalid, provider-failure, and cleanup paths.