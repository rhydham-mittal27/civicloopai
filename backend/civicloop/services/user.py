from __future__ import annotations

from civicloop.models import User, UserRole
from civicloop.repositories import AuditEventRepository, UserRepository
from civicloop.services.common import NotFoundError, record_audit, require_user


class UserService:
    def __init__(
        self, user_repository: UserRepository, audit_repository: AuditEventRepository
    ) -> None:
        self.users = user_repository
        self.audit = audit_repository

    def create_user(
        self, name: str, email: str, role: UserRole, actor_id: str | None = None
    ) -> User:
        if not name.strip() or "@" not in email:
            raise ValueError("Valid name and email are required")
        if self.users.get_by_email(email.strip().lower()) is not None:
            raise ValueError("Email is already registered")
        if actor_id is not None:
            require_user(self.users, actor_id, {UserRole.ADMIN})
        user = self.users.add(
            User(name=name.strip(), email=email.strip().lower(), role=role)
        )
        record_audit(
            self.audit, actor_id, "user", user.id, "created", {"role": role.value}
        )
        return user

    def get_user(self, user_id: str) -> User:
        user = self.users.get(user_id)
        if user is None:
            raise NotFoundError(f"User not found: {user_id}")
        return user

    def get_user_by_email(self, email: str) -> User | None:
        return self.users.get_by_email(email.strip().lower())

    def deactivate_user(self, user_id: str, actor_id: str) -> User:
        require_user(self.users, actor_id, {UserRole.ADMIN})
        user = self.get_user(user_id)
        user.is_active = False
        record_audit(self.audit, actor_id, "user", user.id, "deactivated")
        return user
