from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import text

from common_agent.adapters.persistence.database import Database, DatabaseStartupError


def _database_url(path: Path) -> str:
    return f"sqlite+aiosqlite:///{path}"


def _revision(path: Path) -> str:
    with sqlite3.connect(path) as connection:
        row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
    assert row is not None
    return str(row[0])


def test_empty_database_is_migrated_and_can_restart(tmp_path: Path) -> None:
    path = tmp_path / "platform.db"

    async def exercise() -> None:
        first = Database(_database_url(path))
        await first.start()
        await first.stop()

        second = Database(_database_url(path))
        await second.start()
        await second.stop()

    asyncio.run(exercise())

    assert _revision(path) == "20260719_0001"


def test_session_rolls_back_failed_transaction(tmp_path: Path) -> None:
    path = tmp_path / "rollback.db"

    async def exercise() -> int:
        database = Database(_database_url(path))
        await database.start()
        try:
            async with database.session() as session:
                await session.execute(text("CREATE TABLE transaction_probe (value TEXT NOT NULL)"))
                await session.commit()

            with pytest.raises(RuntimeError, match="force rollback"):
                async with database.session() as session:
                    await session.execute(
                        text("INSERT INTO transaction_probe (value) VALUES ('pending')")
                    )
                    raise RuntimeError("force rollback")

            async with database.session() as session:
                result = await session.execute(text("SELECT COUNT(*) FROM transaction_probe"))
                return int(result.scalar_one())
        finally:
            await database.stop()

    assert asyncio.run(exercise()) == 0


def test_unwritable_database_parent_fails_without_leaking_url(tmp_path: Path) -> None:
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("blocked", encoding="utf-8")
    url = _database_url(blocker / "platform.db")

    async def exercise() -> None:
        database = Database(url)
        with pytest.raises(DatabaseStartupError) as captured:
            await database.start()

        assert url not in str(captured.value)

    asyncio.run(exercise())
