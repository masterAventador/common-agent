from __future__ import annotations

import asyncio
import os

from sqlalchemy import delete, select

from common_agent.adapters.persistence.database import Database
from common_agent.adapters.persistence.models import ConversationRow, EmployeeRow, McpSourceRow
from tests.support.conversations import (
    delete_conversations,
    delete_conversations_for_employee_names,
)
from tests.support.employees import delete_employees_named
from tests.support.model_configuration_e2e_state import delete_model_configurations_named


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


async def _cleanup() -> tuple[int, int, int, int]:
    employee_name = _required("COMMON_AGENT_E2E_TOOL_EMPLOYEE_NAME")
    generic_prefix = _required("COMMON_AGENT_E2E_TOOL_GENERIC_PREFIX")
    model_name = _required("COMMON_AGENT_E2E_TOOL_MODEL_NAME")
    source_names = (
        _required("COMMON_AGENT_E2E_TOOL_MANAGED_SOURCE_NAME"),
        _required("COMMON_AGENT_E2E_TOOL_EXTERNAL_SOURCE_NAME"),
    )
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
        models = await delete_model_configurations_named(database, model_name)
        async with database.session() as session:
            source_ids = tuple(
                await session.scalars(
                    select(McpSourceRow.id).where(McpSourceRow.name.in_(source_names))
                )
            )
            if source_ids:
                await session.execute(
                    delete(McpSourceRow).where(McpSourceRow.id.in_(source_ids))
                )
                await session.commit()
        return len(generic_ids), len(employee_ids), models, len(source_ids)
    finally:
        await database.stop()


def main() -> None:
    generic_conversations, employees, models, sources = asyncio.run(_cleanup())
    print(
        "已清理工具授权 E2E 数据: "
        f"通用会话={generic_conversations},员工={employees},模型={models},MCP 来源={sources}"
    )


if __name__ == "__main__":
    main()
