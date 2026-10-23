from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass

from civicloop.models import User, UserRole
from civicloop.repositories import UserRepository
from civicloop.services.common import PermissionDeniedError


class AuthenticationError(PermissionDeniedError):
    pass


@dataclass(frozen=True)
class AuthPrincipal:
    user_id: str
    role: UserRole
    expires_at: int
    tenant_id: str | None = (
        None  # filled from the database, never trusted from the token
    )
    is_platform_admin: bool = False


def hash_password(password: str, salt: bytes | None = None) -> str:
    if len(password) < 12:
        raise ValueError("Password must contain at least 12 characters")
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1)
    return f"scrypt$1${base64.urlsafe_b64encode(salt).decode()}${base64.urlsafe_b64encode(digest).decode()}"


def verify_password(password: str, encoded: str | None) -> bool:
    if not encoded or not encoded.startswith("scrypt$1$"):
        return False
    _, _, encoded_salt, encoded_digest = encoded.split("$", 3)
    salt = base64.urlsafe_b64decode(encoded_salt.encode())
    expected = base64.urlsafe_b64decode(encoded_digest.encode())
    actual = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1)
    return hmac.compare_digest(actual, expected)


class TokenAuthenticator:
    def __init__(self, secret: str, ttl_seconds: int = 3600) -> None:
        if len(secret) < 32:
            raise ValueError("Authentication secret must be at least 32 characters")
        self.secret = secret.encode("utf-8")
        self.ttl_seconds = ttl_seconds

    def issue(self, user: User, now: int | None = None) -> str:
        issued_at = now or int(time.time())
        payload = {
            "sub": user.id,
            "role": user.role.value,
            "iat": issued_at,
            "exp": issued_at + self.ttl_seconds,
        }
        encoded = self._encode(payload)
        signature = self._sign(encoded)
        return f"{encoded}.{signature}"

    def authenticate(self, authorization: str, now: int | None = None) -> AuthPrincipal:
        if not authorization.startswith("Bearer "):
            raise AuthenticationError("Bearer token is required")
        token = authorization[7:]
        try:
            encoded, signature = token.split(".", 1)
            if not hmac.compare_digest(signature, self._sign(encoded)):
                raise AuthenticationError("Invalid token signature")
            payload = json.loads(self._decode(encoded))
            current = now or int(time.time())
            if current >= int(payload["exp"]):
                raise AuthenticationError("Token has expired")
            return AuthPrincipal(
                str(payload["sub"]), UserRole(str(payload["role"])), int(payload["exp"])
            )
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
            raise AuthenticationError("Invalid authentication token") from error

    def _sign(self, value: str) -> str:
        digest = hmac.new(self.secret, value.encode("ascii"), hashlib.sha256).digest()
        return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")

    @staticmethod
    def _encode(payload: dict[str, object]) -> str:
        raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    @staticmethod
    def _decode(value: str) -> str:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)).decode("utf-8")


class AuthenticationService:
    def __init__(
        self, users: UserRepository, authenticator: TokenAuthenticator
    ) -> None:
        self.users = users
        self.authenticator = authenticator

    def login(self, email: str, password: str) -> str:
        user = self.users.get_by_email(email.strip().lower())
        if (
            user is None
            or not user.is_active
            or not verify_password(password, user.password_hash)
        ):
            raise AuthenticationError("Invalid credentials")
        return self.authenticator.issue(user)

    def set_password(self, user_id: str, password: str) -> User:
        user = self.users.get(user_id)
        if user is None:
            raise AuthenticationError("User not found")
        user.password_hash = hash_password(password)
        return self.users.update(user)


def authenticator_from_env() -> TokenAuthenticator:
    secret = os.environ.get("CIVICLOOP_AUTH_SECRET")
    if not secret:
        raise AuthenticationError("CIVICLOOP_AUTH_SECRET is required")
    return TokenAuthenticator(
        secret, int(os.environ.get("CIVICLOOP_AUTH_TTL_SECONDS", "3600"))
    )
