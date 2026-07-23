from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from common_agent.adapters.persistence.database import Database, DatabaseStartupError
from tests.support.settings import TEST_DATABASE_URL

HEAD_REVISION = "20260723_0027"


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

    assert asyncio.run(exercise()) == (HEAD_REVISION, HEAD_REVISION)


def test_authentication_tables_are_migrated_with_server_side_secret_boundaries() -> None:
    async def exercise() -> dict[str, set[str]]:
        database = Database(_database_url())
        await database.start()
        try:
            async with database.session() as session:
                result = await session.execute(
                    text(
                        "SELECT TABLE_NAME, COLUMN_NAME FROM information_schema.COLUMNS "
                        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME IN "
                        "('auth_users', 'auth_sessions', 'auth_recovery_codes', "
                        "'auth_login_attempts')"
                    )
                )
                columns: dict[str, set[str]] = {}
                for table_name, column_name in result.all():
                    columns.setdefault(str(table_name), set()).add(str(column_name))
                return columns
        finally:
            await database.stop()

    columns = asyncio.run(exercise())

    assert columns["auth_users"] >= {"email", "password_hash", "password_changed_at"}
    assert "password" not in columns["auth_users"]
    assert columns["auth_sessions"] >= {
        "token_digest",
        "csrf_token",
        "idle_expires_at",
        "absolute_expires_at",
        "revoked_at",
    }
    assert "token" not in columns["auth_sessions"]
    assert columns["auth_recovery_codes"] >= {"code_digest", "consumed_at"}
    assert columns["auth_login_attempts"] >= {
        "key_digest",
        "failure_count",
        "locked_until",
    }


def test_tool_catalog_and_exact_grants_have_tenant_scoped_relational_tables() -> None:
    expected = {
        "mcp_sources",
        "mcp_source_credentials",
        "tool_capabilities",
        "tool_collections",
        "tool_collection_sources",
        "employee_tool_collection_selections",
        "employee_tool_grants",
        "conversation_tool_collection_selections",
        "conversation_tool_grants",
    }

    async def exercise() -> tuple[set[str], dict[str, set[str]]]:
        database = Database(_database_url())
        await database.start()
        try:
            async with database.session() as session:
                table_result = await session.execute(
                    text(
                        "SELECT TABLE_NAME FROM information_schema.TABLES "
                        "WHERE TABLE_SCHEMA = DATABASE()"
                    )
                )
                column_result = await session.execute(
                    text(
                        "SELECT TABLE_NAME, COLUMN_NAME FROM information_schema.COLUMNS "
                        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME IN "
                        "('mcp_sources', 'mcp_source_credentials', 'tool_capabilities')"
                    )
                )
                columns: dict[str, set[str]] = {}
                for table_name, column_name in column_result.all():
                    columns.setdefault(str(table_name), set()).add(str(column_name))
                return {str(row[0]) for row in table_result.all()}, columns
        finally:
            await database.stop()

    tables, columns = asyncio.run(exercise())

    assert expected <= tables
    assert {"tenant_id", "source_type", "endpoint_url", "status"} <= columns["mcp_sources"]
    assert {
        "tenant_id",
        "source_id",
        "remote_name",
        "input_schema",
        "schema_fingerprint",
        "status",
    } <= columns["tool_capabilities"]
    assert not {"username", "password", "token", "headers"} & columns["mcp_sources"]
    assert {
        "tenant_id",
        "source_id",
        "credential_type",
        "format_version",
        "key_id",
        "nonce",
        "ciphertext",
        "header_names",
    } <= columns["mcp_source_credentials"]
    assert not {"username", "password", "token", "header_values"} & columns[
        "mcp_source_credentials"
    ]


def test_model_tool_streaming_compatibility_is_platform_managed_and_evidence_backed() -> None:
    async def exercise() -> tuple[set[str], set[str], tuple[object, ...]]:
        database = Database(_database_url())
        await database.start()
        try:
            async with database.session() as session:
                column_result = await session.execute(
                    text(
                        "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
                        "WHERE TABLE_SCHEMA = DATABASE() "
                        "AND TABLE_NAME = 'model_tool_streaming_capabilities'"
                    )
                )
                seed_result = await session.execute(
                    text(
                        "SELECT provider, model_identifier, streaming_breaks_tool_calls, "
                        "evidence_revision FROM model_tool_streaming_capabilities "
                        "WHERE provider = 'bailian' AND model_identifier = 'deepseek-v4-pro'"
                    )
                )
                configuration_column_result = await session.execute(
                    text(
                        "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
                        "WHERE TABLE_SCHEMA = DATABASE() "
                        "AND TABLE_NAME = 'model_configurations'"
                    )
                )
                return (
                    {str(row[0]) for row in column_result.all()},
                    {str(row[0]) for row in configuration_column_result.all()},
                    tuple(seed_result.one()),
                )
        finally:
            await database.stop()

    columns, configuration_columns, seed = asyncio.run(exercise())

    assert columns == {
        "provider",
        "model_identifier",
        "streaming_breaks_tool_calls",
        "evidence_revision",
        "observed_at",
        "updated_at",
    }
    assert "tenant_id" not in columns
    assert "streaming_breaks_tool_calls" not in configuration_columns
    assert seed == (
        "bailian",
        "deepseek-v4-pro",
        1,
        "bailian-real-trace-2026-07-23",
    )


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
    url = "mysql+aiomysql://common_agent:do-not-leak@127.0.0.1:1/common_agent"

    async def exercise() -> None:
        database = Database(url)
        with pytest.raises(DatabaseStartupError) as captured:
            await database.start()

        assert url not in str(captured.value)
        assert "do-not-leak" not in str(captured.value)

    asyncio.run(exercise())


def test_mysql_authentication_failure_does_not_leak_password() -> None:
    url = (
        "mysql+aiomysql://common_agent:wrong-password-must-not-leak@127.0.0.1:19506/"
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
                    text("UPDATE alembic_version SET version_num = :revision"),
                    {"revision": HEAD_REVISION},
                )
                await session.commit()
            revision_is_broken = False

            await candidate.start()
            return await _revision(candidate)
        finally:
            if revision_is_broken:
                async with keeper.session() as session:
                    await session.execute(
                        text("UPDATE alembic_version SET version_num = :revision"),
                        {"revision": HEAD_REVISION},
                    )
                    await session.commit()
            await candidate.stop()
            await keeper.stop()

    assert asyncio.run(exercise()) == HEAD_REVISION
