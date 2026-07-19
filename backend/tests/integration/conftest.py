from __future__ import annotations

import asyncio
import os
from collections.abc import Iterator

import pytest
from sqlalchemy.engine import make_url

from common_agent.employees.seeds import DEFAULT_KNOWLEDGE_ASSISTANT_ID
from tests.support.employees import delete_employees_from_database_url
from tests.support.settings import TEST_DATABASE_URL


@pytest.fixture(scope="session", autouse=True)
def clean_default_employee_after_integration_session() -> Iterator[None]:
    yield

    database_url = os.environ.get("TEST_PLATFORM_DATABASE_URL", TEST_DATABASE_URL)
    database_name = make_url(database_url).database or ""
    if not database_name.endswith("_test"):
        raise RuntimeError("集成测试清理只允许操作名称以 _test 结尾的数据库")
    asyncio.run(
        delete_employees_from_database_url(
            database_url,
            DEFAULT_KNOWLEDGE_ASSISTANT_ID,
        )
    )
