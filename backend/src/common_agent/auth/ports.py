from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from common_agent.auth.models import AuthenticatedSession, StoredAuthUser
from common_agent.tenancy.models import TenantRole


class PasswordHasher(Protocol):
    def hash(self, password: str) -> str: ...

    def verify(self, password: str, encoded_hash: str) -> bool: ...

    def needs_rehash(self, encoded_hash: str) -> bool: ...


class AuthStore(Protocol):
    async def registration_available(self) -> bool: ...

    async def create_owner(
        self,
        *,
        email: str,
        password_hash: str,
        recovery_digests: tuple[str, ...],
        now: datetime,
    ) -> StoredAuthUser | None: ...

    async def create_member(
        self,
        *,
        tenant_id: UUID,
        email: str,
        password_hash: str,
        recovery_digests: tuple[str, ...],
        role: TenantRole,
        now: datetime,
    ) -> StoredAuthUser | None: ...

    async def find_user_by_email(self, email: str) -> StoredAuthUser | None: ...

    async def replace_password_hash(self, user_id: str, password_hash: str) -> None: ...

    async def create_session(
        self,
        *,
        user: StoredAuthUser,
        session_id: str,
        token_digest: str,
        csrf_token: str,
        now: datetime,
        idle_expires_at: datetime,
        absolute_expires_at: datetime,
    ) -> AuthenticatedSession: ...

    async def find_active_session(
        self,
        token_digest: str,
        *,
        now: datetime,
        idle_seconds: int,
    ) -> AuthenticatedSession | None: ...

    async def revoke_session(self, token_digest: str, *, now: datetime) -> None: ...

    async def is_login_blocked(self, keys: tuple[str, ...], *, now: datetime) -> bool: ...

    async def record_login_failure(
        self,
        keys: tuple[str, ...],
        *,
        now: datetime,
        window_seconds: int,
        max_attempts: int,
    ) -> None: ...

    async def clear_login_failures(self, keys: tuple[str, ...]) -> None: ...

    async def reset_password(
        self,
        *,
        email: str,
        recovery_digest: str,
        password_hash: str,
        now: datetime,
    ) -> bool: ...
