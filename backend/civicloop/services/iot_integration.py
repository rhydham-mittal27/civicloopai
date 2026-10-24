from __future__ import annotations

from datetime import datetime
from typing import Any

from civicloop.models import SensorReading
from civicloop.repositories import (
    AuditEventRepository,
    IncidentRepository,
    SensorReadingRepository,
)
from civicloop.services.common import NotFoundError, record_audit


class IoTIntegrationService:
    def __init__(
        self,
        readings: SensorReadingRepository,
        incidents: IncidentRepository,
        audit: AuditEventRepository,
    ) -> None:
        self.readings = readings
        self.incidents = incidents
        self.audit = audit

    def ingest_reading(
        self,
        sensor_id: str,
        latitude: float,
        longitude: float,
        reading: dict[str, Any],
        observed_at: datetime,
    ) -> SensorReading:
        if (
            not sensor_id
            or not reading
            or not -90 <= latitude <= 90
            or not -180 <= longitude <= 180
        ):
            raise ValueError("Valid sensor, coordinates, and reading are required")
        sensor_reading = self.readings.add(
            SensorReading(
                sensor_id=sensor_id,
                latitude=latitude,
                longitude=longitude,
                reading=reading,
                observed_at=observed_at,
            )
        )
        record_audit(self.audit, None, "sensor_reading", sensor_reading.id, "ingested")
        return sensor_reading

    def latest_reading(self, sensor_id: str) -> SensorReading | None:
        return self.readings.latest_for_sensor(sensor_id)

    def associate_with_incident(
        self, reading_id: str, incident_id: str
    ) -> SensorReading:
        reading = self.readings.get(reading_id)
        incident = self.incidents.get(incident_id)
        if reading is None or incident is None:
            raise NotFoundError("Sensor reading and incident must exist")
        if (
            abs(reading.latitude - incident.latitude) > 0.01
            or abs(reading.longitude - incident.longitude) > 0.01
        ):
            raise ValueError("Sensor and incident are too far apart")
        result = self.readings.attach_incident(reading_id, incident_id)
        record_audit(
            self.audit,
            None,
            "sensor_reading",
            reading_id,
            "associated",
            {"incident_id": incident_id},
        )
        return result
