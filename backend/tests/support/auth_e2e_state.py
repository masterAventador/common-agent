from __future__ import annotations

import argparse
import asyncio
import os

from sqlalchemy import text

from common_agent.adapters.persistence.database import Database
from common_agent.tenancy.constants import DEFAULT_TENANT_ID


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


async def _reset() -> None:
    database = Database(_required("COMMON_AGENT_DATABASE_URL"))
    await database.start()
    try:
        async with database.session() as session:
            await session.execute(text("DELETE FROM auth_login_attempts"))
            await session.execute(
                text("DELETE FROM tenants WHERE id <> :default_tenant_id"),
                {"default_tenant_id": str(DEFAULT_TENANT_ID)},
            )
            await session.execute(text("DELETE FROM auth_users"))
            await session.commit()
    finally:
        await database.stop()


async def _expire() -> None:
    database = Database(_required("COMMON_AGENT_DATABASE_URL"))
    await database.start()
    try:
        async with database.session() as session:
            active_count = await session.scalar(
                text("SELECT COUNT(*) FROM auth_sessions WHERE revoked_at IS NULL")
            )
            if not active_count:
                raise RuntimeError("no active E2E session to expire")
            await session.execute(
                text(
                    "UPDATE auth_sessions SET "
                    "created_at = UTC_TIMESTAMP(6) - INTERVAL 10 SECOND, "
                    "last_seen_at = UTC_TIMESTAMP(6) - INTERVAL 9 SECOND, "
                    "idle_expires_at = UTC_TIMESTAMP(6) - INTERVAL 8 SECOND, "
                    "absolute_expires_at = UTC_TIMESTAMP(6) - INTERVAL 7 SECOND "
                    "WHERE revoked_at IS NULL"
                )
            )
            await session.commit()
    finally:
        await database.stop()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("reset", "expire"))
    arguments = parser.parse_args()
    if arguments.action == "reset":
        asyncio.run(_reset())
        print("已重置平台 E2E 认证与测试工作区状态")
    else:
        asyncio.run(_expire())
        print("已使平台 E2E 会话过期")


if __name__ == "__main__":
    main()
