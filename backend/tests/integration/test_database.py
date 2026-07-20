from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from common_agent.adapters.persistence.database import Database, DatabaseStartupError
from tests.support.settings import TEST_DATABASE_URL


def _database_url() -> str:
    return os.environ.get(
        "TEST_PLATFORM_DATABASE_URL",
        TEST_DATABASE_URL,
    )


async def _revision(database: Database) -> str:
    async with database.session() as session:
        result = await session.execute(text("SELECT version_num FROM alembic_version"))
        return str(result.scalar_one())


def test_empty_mysql_database_is_migrated_and_can_restart() -> None:
    async def exercise() -> tuple[str, str]:
        first = Database(_database_url())
        await first.start()
        try:
            first_revision = await _revision(first)
        finally:
            await first.stop()

        second = Database(_database_url())
        await second.start()
        try:
            second_revision = await _revision(second)
        finally:
            await second.stop()
        return first_revision, second_revision

    assert asyncio.run(exercise()) == ("20260720_0006", "20260720_0006")


def test_mysql_session_rolls_back_failed_transaction() -> None:
    table = f"transaction_probe_{uuid4().hex}"

    async def exercise() -> int:
        database = Database(_database_url())
        await database.start()
        try:
            async with database.session() as session:
                await session.execute(text(f"CREATE TABLE {table} (value VARCHAR(64) NOT NULL)"))
                await session.commit()

            with pytest.raises(RuntimeError, match="force rollback"):
                async with database.session() as session:
                    await session.execute(text(f"INSERT INTO {table} (value) VALUES ('pending')"))
                    raise RuntimeError("force rollback")

            async with database.session() as session:
                result = await session.execute(text(f"SELECT COUNT(*) FROM {table}"))
                return int(result.scalar_one())
        finally:
            async with database.session() as session:
                await session.execute(text(f"DROP TABLE IF EXISTS {table}"))
                await session.commit()
            await database.stop()

    assert asyncio.run(exercise()) == 0


def test_mysql_unique_conflict_rolls_back_and_keeps_committed_row() -> None:
    table = f"unique_probe_{uuid4().hex}"

    async def exercise() -> int:
        database = Database(_database_url())
        await database.start()
        try:
            async with database.session() as session:
                await session.execute(
                    text(
                        f"CREATE TABLE {table} ("
                        "id BIGINT PRIMARY KEY AUTO_INCREMENT, "
                        "value VARCHAR(64) NOT NULL UNIQUE)"
                    )
                )
                await session.execute(text(f"INSERT INTO {table} (value) VALUES ('same')"))
                await session.commit()

            with pytest.raises(IntegrityError):
                async with database.session() as session:
                    await session.execute(text(f"INSERT INTO {table} (value) VALUES ('same')"))

            async with database.session() as session:
                result = await session.execute(text(f"SELECT COUNT(*) FROM {table}"))
                return int(result.scalar_one())
        finally:
            async with database.session() as session:
                await session.execute(text(f"DROP TABLE IF EXISTS {table}"))
                await session.commit()
            await database.stop()

    assert asyncio.run(exercise()) == 1


def test_unavailable_mysql_fails_without_leaking_url() -> None:
    url = "mysql+asyncmy://common_agent:do-not-leak@127.0.0.1:1/common_agent"

    async def exercise() -> None:
        database = Database(url)
        with pytest.raises(DatabaseStartupError) as captured:
            await database.start()

        assert url not in str(captured.value)
        assert "do-not-leak" not in str(captured.value)

    asyncio.run(exercise())


def test_mysql_authentication_failure_does_not_leak_password() -> None:
    url = (
        "mysql+asyncmy://common_agent:wrong-password-must-not-leak@127.0.0.1:19506/"
        "common_agent?charset=utf8mb4"
    )

    async def exercise() -> None:
        database = Database(url)
        with pytest.raises(DatabaseStartupError) as captured:
            await database.start()

        assert url not in str(captured.value)
        assert "wrong-password-must-not-leak" not in str(captured.value)

    asyncio.run(exercise())


def test_mysql_migration_failure_is_closed_and_recovers_after_repair() -> None:
    async def exercise() -> str:
        keeper = Database(_database_url())
        await keeper.start()
        revision_is_broken = False
        candidate = Database(_database_url())
        try:
            async with keeper.session() as session:
                await session.execute(
                    text("UPDATE alembic_version SET version_num = 'missing_test_revision'")
                )
                await session.commit()
            revision_is_broken = True

            with pytest.raises(DatabaseStartupError):
                await candidate.start()

            async with keeper.session() as session:
                await session.execute(
                    text("UPDATE alembic_version SET version_num = '20260720_0006'")
                )
                await session.commit()
            revision_is_broken = False

            await candidate.start()
            return await _revision(candidate)
        finally:
            if revision_is_broken:
                async with keeper.session() as session:
                    await session.execute(
                        text("UPDATE alembic_version SET version_num = '20260720_0006'")
                    )
                    await session.commit()
            await candidate.stop()
            await keeper.stop()

    assert asyncio.run(exercise()) == "20260720_0006"
