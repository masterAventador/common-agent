from __future__ import annotations

import asyncio
import os

from sqlalchemy import select

from common_agent.adapters.persistence.database import Database
from common_agent.adapters.persistence.models import ConversationRow, EmployeeRow
from tests.support.conversations import (
    delete_conversations,
    delete_conversations_for_employee_names,
)
from tests.support.employees import delete_employees_named


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


async def _cleanup() -> tuple[int, int]:
    employee_name = _required("COMMON_AGENT_E2E_TOOL_EMPLOYEE_NAME")
    generic_prefix = _required("COMMON_AGENT_E2E_TOOL_GENERIC_PREFIX")
    database = Database(_required("COMMON_AGENT_DATABASE_URL"))
    await database.start()
    try:
        async with database.session() as session:
            generic_ids = tuple(
                await session.scalars(
                    select(ConversationRow.id).where(
                        ConversationRow.source == "generic",
                        ConversationRow.title.startswith(generic_prefix, autoescape=True),
                    )
                )
            )
            employee_ids = tuple(
                await session.scalars(
                    select(EmployeeRow.id).where(EmployeeRow.name == employee_name)
                )
            )
        await delete_conversations(database, *generic_ids)
        await delete_conversations_for_employee_names(database, employee_name)
        await delete_employees_named(database, employee_name)
        return len(generic_ids), len(employee_ids)
    finally:
        await database.stop()


def main() -> None:
    generic_conversations, employees = asyncio.run(_cleanup())
    print(
        "已清理工具授权 E2E 数据: "
        f"通用会话={generic_conversations},员工={employees}"
    )


if __name__ == "__main__":
    main()
