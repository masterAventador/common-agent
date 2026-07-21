from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from common_agent.adapters.auth.passwords import Argon2PasswordHasher
from common_agent.auth.models import AuthConfiguration, AuthenticatedSession, StoredAuthUser
from common_agent.auth.service import AuthenticationError, AuthenticationService
from common_agent.tenancy import TenantRole


@dataclass
class _Attempt:
    count: int
    window_started_at: datetime
    locked_until: datetime | None = None


class _FakeAuthStore:
    def __init__(self) -> None:
        self.users: dict[str, StoredAuthUser] = {}
        self.sessions: dict[str, AuthenticatedSession] = {}
        self.recovery_digests: dict[str, set[str]] = {}
        self.attempts: dict[str, _Attempt] = {}

    async def registration_available(self) -> bool:
        return not self.users

    async def create_owner(
        self,
        *,
        email: str,
        password_hash: str,
        recovery_digests: tuple[str, ...],
        now: datetime,
    ) -> StoredAuthUser | None:
        if self.users:
            return None
        user = StoredAuthUser(
            id=str(uuid4()),
            email=email,
            password_hash=password_hash,
            is_active=True,
        )
        self.users[email] = user
        self.recovery_digests[user.id] = set(recovery_digests)
        return user

    async def create_member(
        self,
        *,
        tenant_id: UUID,
        email: str,
        password_hash: str,
        recovery_digests: tuple[str, ...],
        role: TenantRole,
        now: datetime,
    ) -> StoredAuthUser | None:
        del tenant_id, role, now
        if email in self.users:
            return None
        user = StoredAuthUser(
            id=str(uuid4()),
            email=email,
            password_hash=password_hash,
            is_active=True,
        )
        self.users[email] = user
        self.recovery_digests[user.id] = set(recovery_digests)
        return user

    async def find_user_by_email(self, email: str) -> StoredAuthUser | None:
        return self.users.get(email)

    async def replace_password_hash(self, user_id: str, password_hash: str) -> None:
        user = next(user for user in self.users.values() if user.id == user_id)
        self.users[user.email] = StoredAuthUser(
            id=user.id,
            email=user.email,
            password_hash=password_hash,
            is_active=user.is_active,
        )

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
    ) -> AuthenticatedSession:
        session = AuthenticatedSession(
            id=session_id,
            user_id=user.id,
            email=user.email,
            csrf_token=csrf_token,
            idle_expires_at=idle_expires_at,
            absolute_expires_at=absolute_expires_at,
        )
        self.sessions[token_digest] = session
        return session

    async def find_active_session(
        self,
        token_digest: str,
        *,
        now: datetime,
        idle_seconds: int,
    ) -> AuthenticatedSession | None:
        session = self.sessions.get(token_digest)
        if session is None:
            return None
        if now >= session.idle_expires_at or now >= session.absolute_expires_at:
            self.sessions.pop(token_digest, None)
            return None
        refreshed = AuthenticatedSession(
            id=session.id,
            user_id=session.user_id,
            email=session.email,
            csrf_token=session.csrf_token,
            idle_expires_at=min(
                now + timedelta(seconds=idle_seconds),
                session.absolute_expires_at,
            ),
            absolute_expires_at=session.absolute_expires_at,
        )
        self.sessions[token_digest] = refreshed
        return refreshed

    async def revoke_session(self, token_digest: str, *, now: datetime) -> None:
        del now
        self.sessions.pop(token_digest, None)

    async def is_login_blocked(self, keys: tuple[str, ...], *, now: datetime) -> bool:
        return any(
            attempt.locked_until is not None and now < attempt.locked_until
            for key in keys
            if (attempt := self.attempts.get(key)) is not None
        )

    async def record_login_failure(
        self,
        keys: tuple[str, ...],
        *,
        now: datetime,
        window_seconds: int,
        max_attempts: int,
    ) -> None:
        for key in keys:
            attempt = self.attempts.get(key)
            if attempt is None or now >= attempt.window_started_at + timedelta(
                seconds=window_seconds
            ):
                attempt = _Attempt(count=0, window_started_at=now)
            attempt.count += 1
            if attempt.count >= max_attempts:
                attempt.locked_until = now + timedelta(seconds=window_seconds)
            self.attempts[key] = attempt

    async def clear_login_failures(self, keys: tuple[str, ...]) -> None:
        for key in keys:
            self.attempts.pop(key, None)

    async def reset_password(
        self,
        *,
        email: str,
        recovery_digest: str,
        password_hash: str,
        now: datetime,
    ) -> bool:
        del now
        user = self.users.get(email)
        if user is None or recovery_digest not in self.recovery_digests[user.id]:
            return False
        self.recovery_digests[user.id].remove(recovery_digest)
        await self.replace_password_hash(user.id, password_hash)
        self.sessions = {
            digest: session
            for digest, session in self.sessions.items()
            if session.user_id != user.id
        }
        return True


class _Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 7, 21, 10, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


def _service(store: _FakeAuthStore, clock: _Clock) -> AuthenticationService:
    return AuthenticationService(
        store,
        Argon2PasswordHasher(),
        AuthConfiguration(
            bootstrap_token="bootstrap-token-that-is-at-least-32-characters",
            session_idle_seconds=300,
            session_absolute_seconds=3600,
            login_window_seconds=60,
            login_max_attempts=3,
        ),
        clock=clock,
    )


async def _register(service: AuthenticationService) -> tuple[str, tuple[str, ...]]:
    issued = await service.register_owner(
        email="Owner@Example.com",
        password="correct horse battery staple",
        bootstrap_token="bootstrap-token-that-is-at-least-32-characters",
    )
    return issued.session_token, issued.recovery_codes


def test_owner_registration_requires_bootstrap_and_closes_after_first_success() -> None:
    async def exercise() -> None:
        store = _FakeAuthStore()
        clock = _Clock()
        service = _service(store, clock)

        with pytest.raises(AuthenticationError, match="invalid_bootstrap_token"):
            await service.register_owner(
                email="owner@example.com",
                password="correct horse battery staple",
                bootstrap_token="wrong-bootstrap-token-value-123456",
            )

        token, recovery_codes = await _register(service)
        assert token
        assert len(recovery_codes) == 8
        assert set(store.users) == {"owner@example.com"}
        assert await service.registration_available() is False

        with pytest.raises(AuthenticationError, match="registration_unavailable"):
            await service.register_owner(
                email="second@example.com",
                password="another correct horse password",
                bootstrap_token="bootstrap-token-that-is-at-least-32-characters",
            )

    import asyncio

    asyncio.run(exercise())


def test_login_is_generic_rate_limited_by_account_and_address_then_recovers() -> None:
    async def exercise() -> None:
        store = _FakeAuthStore()
        clock = _Clock()
        service = _service(store, clock)
        await _register(service)

        for _ in range(3):
            with pytest.raises(AuthenticationError, match="invalid_credentials"):
                await service.login(
                    email="owner@example.com",
                    password="wrong password value",
                    client_address="127.0.0.1",
                )

        with pytest.raises(AuthenticationError, match="login_rate_limited"):
            await service.login(
                email="owner@example.com",
                password="correct horse battery staple",
                client_address="127.0.0.1",
            )

        clock.now += timedelta(seconds=61)
        issued = await service.login(
            email="owner@example.com",
            password="correct horse battery staple",
            client_address="127.0.0.1",
        )
        assert issued.email == "owner@example.com"

    import asyncio

    asyncio.run(exercise())


def test_owner_can_provision_a_login_account_with_an_explicit_tenant_role() -> None:
    async def exercise() -> None:
        store = _FakeAuthStore()
        clock = _Clock()
        service = _service(store, clock)
        await _register(service)

        provisioned = await service.provision_member(
            tenant_id=UUID("10000000-0000-4000-8000-000000000001"),
            email="Viewer@Example.com",
            password="viewer initial password is secure",
            role=TenantRole.VIEWER,
        )

        assert provisioned.email == "viewer@example.com"
        assert provisioned.role is TenantRole.VIEWER
        assert len(provisioned.recovery_codes) == 8
        logged_in = await service.login(
            email="viewer@example.com",
            password="viewer initial password is secure",
            client_address="127.0.0.2",
        )
        assert logged_in.user_id == provisioned.user_id

        with pytest.raises(AuthenticationError, match="member_conflict"):
            await service.provision_member(
                tenant_id=UUID("10000000-0000-4000-8000-000000000001"),
                email="viewer@example.com",
                password="another secure initial password",
                role=TenantRole.EDITOR,
            )

    import asyncio

    asyncio.run(exercise())


def test_member_provisioning_rejects_owner_role() -> None:
    async def exercise() -> None:
        store = _FakeAuthStore()
        service = _service(store, _Clock())

        with pytest.raises(AuthenticationError, match="member_role_invalid"):
            await service.provision_member(
                tenant_id=UUID("10000000-0000-4000-8000-000000000001"),
                email="owner-member@example.com",
                password="owner member password is secure",
                role=TenantRole.OWNER,
            )

        assert store.users == {}

    import asyncio

    asyncio.run(exercise())


def test_session_csrf_expiry_logout_and_replay_fail_closed() -> None:
    async def exercise() -> None:
        store = _FakeAuthStore()
        clock = _Clock()
        service = _service(store, clock)
        token, _ = await _register(service)

        session = await service.authenticate(token)
        assert service.csrf_matches(session, session.csrf_token) is True
        assert service.csrf_matches(session, "wrong-csrf-token") is False

        await service.logout(token)
        with pytest.raises(AuthenticationError, match="authentication_required"):
            await service.authenticate(token)

        replacement = await service.login(
            email="owner@example.com",
            password="correct horse battery staple",
            client_address="127.0.0.1",
        )
        clock.now += timedelta(seconds=301)
        with pytest.raises(AuthenticationError, match="authentication_required"):
            await service.authenticate(replacement.session_token)

    import asyncio

    asyncio.run(exercise())


def test_recovery_code_is_single_use_and_revokes_existing_sessions() -> None:
    async def exercise() -> None:
        store = _FakeAuthStore()
        clock = _Clock()
        service = _service(store, clock)
        old_token, recovery_codes = await _register(service)

        await service.reset_password(
            email="owner@example.com",
            recovery_code=recovery_codes[0].lower(),
            new_password="replacement horse battery password",
            client_address="127.0.0.1",
        )
        with pytest.raises(AuthenticationError, match="authentication_required"):
            await service.authenticate(old_token)
        with pytest.raises(AuthenticationError, match="invalid_recovery_credentials"):
            await service.reset_password(
                email="owner@example.com",
                recovery_code=recovery_codes[0],
                new_password="another replacement password",
                client_address="127.0.0.1",
            )

        issued = await service.login(
            email="owner@example.com",
            password="replacement horse battery password",
            client_address="127.0.0.1",
        )
        assert issued.session_token

    import asyncio

    asyncio.run(exercise())
