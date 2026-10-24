from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from civicloop.models import User, UserRole
from civicloop.repositories import AuditEventRepository, UserRepository


class ServiceError(Exception):
    """Base error for rejected service operations."""


class NotFoundError(ServiceError):
    pass


class PermissionDeniedError(ServiceError):
    pass


def require_user(
    user_repository: UserRepository, user_id: str, roles: set[UserRole] | None = None
) -> User:
    user = user_repository.get(user_id)
    if user is None or not user.is_active:
        raise PermissionDeniedError("Active user is required")
    if roles is not None and user.role not in roles:
        raise PermissionDeniedError("User role is not allowed")
    return user


def record_audit(
    audit_repository: AuditEventRepository,
    actor_id: str | None,
    entity_type: str,
    entity_id: str,
    action: str,
    details: Mapping[str, Any] | None = None,
) -> None:
    from civicloop.models import AuditEvent

    audit_repository.add(
        AuditEvent(
            actor_id=actor_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            details=dict(details or {}),
        )
    )
