# IoTIntegrationService

## Repositories

- `SensorReadingRepository`: planned `add`, `list_for_location`, `latest_for_sensor`
- `IncidentRepository`: `list_for_location`, `get`
- `AuditEventRepository`: planned `add`

## Functions

### `ingest_reading(sensor_id, latitude, longitude, reading, observed_at)`

```text
validate sensor identity, coordinates, timestamp, and reading schema
sensor_reading = SensorReading(sensor_id, latitude, longitude, reading, observed_at)
SensorReadingRepository.add(sensor_reading)
nearby = IncidentRepository.list_for_location(latitude, longitude)
if reading indicates elevated risk:
    emit hotspot_signal for HotspotRiskService
AuditEventRepository.add(None, "sensor_reading", sensor_reading.id, "ingested", {})
return sensor_reading
```

### `latest_reading(sensor_id)`

```text
return SensorReadingRepository.latest_for_sensor(sensor_id)
```

### `associate_with_incident(reading_id, incident_id)`

```text
reading = SensorReadingRepository.get(reading_id)
incident = IncidentRepository.get(incident_id)
require both exist and coordinates are within configured tolerance
SensorReadingRepository.attach_incident(reading_id, incident_id)
AuditEventRepository.add(None, "sensor_reading", reading_id, "associated", {"incident_id": incident_id})
return reading
```

IoT remains optional and must not be required for the core report workflow.