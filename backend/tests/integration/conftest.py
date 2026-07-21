from __future__ import annotations

import asyncio
import os
from collections.abc import Iterator
from uuid import UUID

import pytest
from sqlalchemy.engine import make_url

from common_agent.employees.seeds import DEFAULT_KNOWLEDGE_ASSISTANT_ID
from common_agent.tenancy import TenantAccess, TenantRole, bind_tenant
from common_agent.tenancy.constants import DEFAULT_TENANT_ID
from tests.support.employees import delete_employees_from_database_url
from tests.support.settings import TEST_DATABASE_URL


@pytest.fixture(autouse=True)
def bind_default_test_tenant() -> Iterator[None]:
    access = TenantAccess(
        tenant_id=DEFAULT_TENANT_ID,
        user_id=UUID("00000000-0000-4000-8000-000000000099"),
        role=TenantRole.OWNER,
    )
    with bind_tenant(access):
        yield


@pytest.fixture(scope="session", autouse=True)
def clean_default_employee_after_integration_session() -> Iterator[None]:
    database_url = os.environ.get("TEST_PLATFORM_DATABASE_URL", TEST_DATABASE_URL)
    database_name = make_url(database_url).database or ""
    if not database_name.endswith("_test"):
        raise RuntimeError("集成测试清理只允许操作名称以 _test 结尾的数据库")
    asyncio.run(_delete_test_authentication(database_url))
    yield

    asyncio.run(
        delete_employees_from_database_url(
            database_url,
            DEFAULT_KNOWLEDGE_ASSISTANT_ID,
        )
    )
    asyncio.run(_delete_test_authentication(database_url))


async def _delete_test_authentication(database_url: str) -> None:
    from common_agent.adapters.persistence.database import Database

    database = Database(database_url)
    await database.start()
    try:
        async with database.session() as session:
            from sqlalchemy import text

            await session.execute(text("DELETE FROM auth_login_attempts"))
            await session.execute(text("DELETE FROM auth_users"))
            await session.commit()
    finally:
        await database.stop()
