from __future__ import annotations

import asyncio
import re
import secrets
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from common_agent.auth.credentials import (
    create_recovery_codes,
    create_session_token,
    digest_secret,
    validate_password,
)
from common_agent.auth.models import (
    AuthConfiguration,
    AuthenticatedSession,
    IssuedAuthentication,
    ProvisionedMember,
    StoredAuthUser,
)
from common_agent.auth.ports import AuthStore, PasswordHasher
from common_agent.tenancy.models import TenantRole

_EMAIL_PATTERN = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+$")
_DUMMY_PASSWORD_HASH = (
    "$argon2id$v=19$m=19456,t=2,p=1$C3NaNPWXrno7K/tdRYCtkw$"
    "RVQmdTcj1mWEfFmZtNgE9XiYtW7+cmL5JwleBxZr+/A"
)


class AuthenticationError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class AuthenticationService:
    def __init__(
        self,
        store: AuthStore,
        password_hasher: PasswordHasher,
        configuration: AuthConfiguration,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._store = store
        self._password_hasher = password_hasher
        self._configuration = configuration
        self._clock = clock or (lambda: datetime.now(UTC))

    async def registration_available(self) -> bool:
        return (
            bool(self._configuration.bootstrap_token) and await self._store.registration_available()
        )

    async def register_owner(
        self,
        *,
        email: str,
        password: str,
        bootstrap_token: str,
    ) -> IssuedAuthentication:
        expected_token = self._configuration.bootstrap_token
        if not expected_token:
            raise AuthenticationError("registration_unavailable")
        if not secrets.compare_digest(bootstrap_token, expected_token):
            raise AuthenticationError("invalid_bootstrap_token")

        normalized_email = normalize_email(email)
        validate_password(password)
        password_hash = await asyncio.to_thread(self._password_hasher.hash, password)
        recovery_codes = create_recovery_codes()
        now = self._clock()
        user = await self._store.create_owner(
            email=normalized_email,
            password_hash=password_hash,
            recovery_digests=tuple(digest_secret(code) for code in recovery_codes),
            now=now,
        )
        if user is None:
            raise AuthenticationError("registration_unavailable")
        return await self._issue_session(user, now=now, recovery_codes=recovery_codes)

    async def login(
        self,
        *,
        email: str,
        password: str,
        client_address: str,
    ) -> IssuedAuthentication:
        normalized_email = normalize_email(email)
        keys = _attempt_keys("login", normalized_email, client_address)
        now = self._clock()
        if await self._store.is_login_blocked(keys, now=now):
            raise AuthenticationError("login_rate_limited")

        user = await self._store.find_user_by_email(normalized_email)
        encoded_hash = user.password_hash if user is not None else _DUMMY_PASSWORD_HASH
        verified = await asyncio.to_thread(self._password_hasher.verify, password, encoded_hash)
        if user is None or not user.is_active or not verified:
            await self._store.record_login_failure(
                keys,
                now=now,
                window_seconds=self._configuration.login_window_seconds,
                max_attempts=self._configuration.login_max_attempts,
            )
            raise AuthenticationError("invalid_credentials")

        await self._store.clear_login_failures(keys)
        if self._password_hasher.needs_rehash(user.password_hash):
            replacement_hash = await asyncio.to_thread(self._password_hasher.hash, password)
            await self._store.replace_password_hash(user.id, replacement_hash)
        return await self._issue_session(user, now=now)

    async def provision_member(
        self,
        *,
        tenant_id: UUID,
        email: str,
        password: str,
        role: TenantRole,
    ) -> ProvisionedMember:
        if role is TenantRole.OWNER:
            raise AuthenticationError("member_role_invalid")
        normalized_email = normalize_email(email)
        validate_password(password)
        password_hash = await asyncio.to_thread(self._password_hasher.hash, password)
        recovery_codes = create_recovery_codes()
        user = await self._store.create_member(
            tenant_id=tenant_id,
            email=normalized_email,
            password_hash=password_hash,
            recovery_digests=tuple(digest_secret(code) for code in recovery_codes),
            role=role,
            now=self._clock(),
        )
        if user is None:
            raise AuthenticationError("member_conflict")
        return ProvisionedMember(
            user_id=user.id,
            email=user.email,
            role=role,
            recovery_codes=recovery_codes,
        )

    async def authenticate(self, session_token: str) -> AuthenticatedSession:
        if not session_token:
            raise AuthenticationError("authentication_required")
        session = await self._store.find_active_session(
            digest_secret(session_token),
            now=self._clock(),
            idle_seconds=self._configuration.session_idle_seconds,
        )
        if session is None:
            raise AuthenticationError("authentication_required")
        return session

    def csrf_matches(self, session: AuthenticatedSession, csrf_token: str) -> bool:
        return bool(csrf_token) and secrets.compare_digest(session.csrf_token, csrf_token)

    async def logout(self, session_token: str) -> None:
        if not session_token:
            return
        await self._store.revoke_session(digest_secret(session_token), now=self._clock())

    async def reset_password(
        self,
        *,
        email: str,
        recovery_code: str,
        new_password: str,
        client_address: str,
    ) -> None:
        normalized_email = normalize_email(email)
        validate_password(new_password)
        keys = _attempt_keys("recovery", normalized_email, client_address)
        now = self._clock()
        if await self._store.is_login_blocked(keys, now=now):
            raise AuthenticationError("recovery_rate_limited")

        password_hash = await asyncio.to_thread(self._password_hasher.hash, new_password)
        recovered = await self._store.reset_password(
            email=normalized_email,
            recovery_digest=digest_secret(recovery_code.strip().upper()),
            password_hash=password_hash,
            now=now,
        )
        if not recovered:
            await self._store.record_login_failure(
                keys,
                now=now,
                window_seconds=self._configuration.login_window_seconds,
                max_attempts=self._configuration.login_max_attempts,
            )
            raise AuthenticationError("invalid_recovery_credentials")
        await self._store.clear_login_failures(keys)

    async def _issue_session(
        self,
        user: StoredAuthUser,
        *,
        now: datetime,
        recovery_codes: tuple[str, ...] = (),
    ) -> IssuedAuthentication:
        session_token = create_session_token()
        csrf_token = create_session_token()
        idle_expires_at = now + timedelta(seconds=self._configuration.session_idle_seconds)
        absolute_expires_at = now + timedelta(seconds=self._configuration.session_absolute_seconds)
        session = await self._store.create_session(
            user=user,
            session_id=str(uuid4()),
            token_digest=digest_secret(session_token),
            csrf_token=csrf_token,
            now=now,
            idle_expires_at=idle_expires_at,
            absolute_expires_at=absolute_expires_at,
        )
        return IssuedAuthentication(
            user_id=user.id,
            email=user.email,
            session_token=session_token,
            csrf_token=csrf_token,
            idle_expires_at=session.idle_expires_at,
            absolute_expires_at=session.absolute_expires_at,
            recovery_codes=recovery_codes,
        )


def normalize_email(email: str) -> str:
    normalized = email.strip().casefold()
    if (
        not 3 <= len(normalized) <= 254
        or not _EMAIL_PATTERN.fullmatch(normalized)
        or normalized.count("@") != 1
    ):
        raise AuthenticationError("invalid_email")
    local, domain = normalized.rsplit("@", 1)
    if (
        not 1 <= len(local) <= 64
        or local.startswith(".")
        or local.endswith(".")
        or ".." in local
        or domain.startswith(".")
        or domain.endswith(".")
        or ".." in domain
    ):
        raise AuthenticationError("invalid_email")
    return normalized


def _attempt_keys(scope: str, email: str, client_address: str) -> tuple[str, str]:
    return (
        digest_secret(f"{scope}:email:{email}"),
        digest_secret(f"{scope}:address:{client_address}"),
    )
