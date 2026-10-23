# MediaAssetService

## Repositories

- `MediaAssetRepository`: planned `get`, `add`, `list_for_incident`
- `IncidentRepository`: `get`
- `AuditEventRepository`: planned `add`

## Functions

### `store_for_incident(incident_id, image, is_after_cleanup)`

```text
incident = IncidentRepository.get(incident_id)
require incident exists
validate content type, byte size, and image decodability
sha256 = hash(image.bytes)
storage_key = ObjectStorageAdapter.put(image.bytes)
asset = MediaAsset(incident_id, storage_key, content_type, sha256,
                   is_after_cleanup=is_after_cleanup)
MediaAssetRepository.add(asset)
return asset
```

### `list_evidence(incident_id, after_cleanup=None)`

```text
require IncidentRepository.get(incident_id) exists
return MediaAssetRepository.list_for_incident(incident_id, after_cleanup=after_cleanup)
```

### `delete_asset(asset_id, actor_id)`

```text
asset = MediaAssetRepository.get(asset_id)
require actor is ADMIN and asset exists
ObjectStorageAdapter.delete(asset.storage_key)
MediaAssetRepository.delete(asset)
AuditEventRepository.add(actor_id, "media_asset", asset_id, "deleted", {})
```