from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from civicloop.models import AuditEvent
from civicloop.repositories import AuditEventRepository


class AuditService:
    def __init__(self, events: AuditEventRepository) -> None:
        self.events = events

    def record(
        self,
        actor_id: str | None,
        entity_type: str,
        entity_id: str,
        action: str,
        details: Mapping[str, Any] | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            actor_id=actor_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            details=dict(details or {}),
        )
        return self.events.add(event)

    def history(self, entity_type: str, entity_id: str) -> Sequence[AuditEvent]:
        return self.events.list_for_entity(entity_type, entity_id)

    def actor_history(self, actor_id: str) -> Sequence[AuditEvent]:
        return self.events.list_for_actor(actor_id)
