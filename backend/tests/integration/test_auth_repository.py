from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import text

from common_agent.adapters.auth.passwords import Argon2PasswordHasher
from common_agent.adapters.persistence.auth import SqlAlchemyAuthStore
from common_agent.adapters.persistence.database import Database
from common_agent.auth.credentials import digest_secret
from tests.support.settings import TEST_DATABASE_URL


def _database_url() -> str:
    return os.environ.get("TEST_PLATFORM_DATABASE_URL", TEST_DATABASE_URL)


async def _clear_auth(database: Database) -> None:
    async with database.session() as session:
        await session.execute(text("DELETE FROM auth_login_attempts"))
        await session.execute(text("DELETE FROM auth_users"))
        await session.commit()


def test_mysql_auth_store_serializes_owner_bootstrap_and_persists_session_security() -> None:
    async def exercise() -> None:
        database = Database(_database_url())
        await database.start()
        await _clear_auth(database)
        store = SqlAlchemyAuthStore(database)
        hasher = Argon2PasswordHasher()
        now = datetime(2026, 7, 21, 11, 0, tzinfo=UTC)
        try:
            candidates = await asyncio.gather(
                *(
                    store.create_owner(
                        email=f"owner-{index}@example.com",
                        password_hash=hasher.hash("correct horse battery staple"),
                        recovery_digests=(digest_secret(f"RECOVERY-{index}"),),
                        now=now,
                    )
                    for index in range(2)
                )
            )
            created = [candidate for candidate in candidates if candidate is not None]
            assert len(created) == 1
            user = created[0]
            assert await store.registration_available() is False

            raw_token = "raw-session-token-that-must-not-persist"
            token_digest = digest_secret(raw_token)
            session = await store.create_session(
                user=user,
                session_id=str(uuid4()),
                token_digest=token_digest,
                csrf_token="A" * 43,
                now=now,
                idle_expires_at=now + timedelta(minutes=5),
                absolute_expires_at=now + timedelta(hours=1),
            )
            assert session.email == user.email
            assert (
                await store.find_active_session(
                    token_digest,
                    now=now + timedelta(minutes=1),
                    idle_seconds=300,
                )
                is not None
            )

            async with database.session() as sql_session:
                result = await sql_session.execute(
                    text("SELECT token_digest FROM auth_sessions WHERE id = :id"),
                    {"id": session.id},
                )
                assert result.scalar_one() == token_digest
            assert raw_token != token_digest

            await store.revoke_session(token_digest, now=now + timedelta(minutes=2))
            assert (
                await store.find_active_session(
                    token_digest,
                    now=now + timedelta(minutes=2),
                    idle_seconds=300,
                )
                is None
            )
        finally:
            await _clear_auth(database)
            await database.stop()

    asyncio.run(exercise())


def test_mysql_auth_store_locks_attempts_and_consumes_recovery_code_atomically() -> None:
    async def exercise() -> None:
        database = Database(_database_url())
        await database.start()
        await _clear_auth(database)
        store = SqlAlchemyAuthStore(database)
        hasher = Argon2PasswordHasher()
        now = datetime(2026, 7, 21, 12, 0, tzinfo=UTC)
        recovery_digest = digest_secret("ABCDEFGH-JKLMNPQR")
        try:
            user = await store.create_owner(
                email="owner@example.com",
                password_hash=hasher.hash("correct horse battery staple"),
                recovery_digests=(recovery_digest,),
                now=now,
            )
            assert user is not None
            await store.create_session(
                user=user,
                session_id=str(uuid4()),
                token_digest=digest_secret("existing-session-token"),
                csrf_token="B" * 43,
                now=now,
                idle_expires_at=now + timedelta(minutes=5),
                absolute_expires_at=now + timedelta(hours=1),
            )

            keys = (digest_secret("login:email"), digest_secret("login:address"))
            for _ in range(3):
                await store.record_login_failure(
                    keys,
                    now=now,
                    window_seconds=60,
                    max_attempts=3,
                )
            assert await store.is_login_blocked(keys, now=now + timedelta(seconds=1)) is True
            assert await store.is_login_blocked(keys, now=now + timedelta(seconds=61)) is False

            fresh_keys = (digest_secret("fresh:email"), digest_secret("fresh:address"))
            await store.record_login_failure(
                fresh_keys,
                now=now + timedelta(minutes=2),
                window_seconds=60,
                max_attempts=3,
            )
            async with database.session() as sql_session:
                remaining_attempts = await sql_session.scalar(
                    text("SELECT COUNT(*) FROM auth_login_attempts")
                )
            assert remaining_attempts == 2

            reset = await store.reset_password(
                email=user.email,
                recovery_digest=recovery_digest,
                password_hash=hasher.hash("replacement horse battery password"),
                now=now + timedelta(minutes=2),
            )
            replayed = await store.reset_password(
                email=user.email,
                recovery_digest=recovery_digest,
                password_hash=hasher.hash("another replacement password"),
                now=now + timedelta(minutes=3),
            )
            assert reset is True
            assert replayed is False
            assert (
                await store.find_active_session(
                    digest_secret("existing-session-token"),
                    now=now + timedelta(minutes=2),
                    idle_seconds=300,
                )
                is None
            )
        finally:
            await _clear_auth(database)
            await database.stop()

    asyncio.run(exercise())
