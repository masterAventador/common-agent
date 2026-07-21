from __future__ import annotations

import asyncio
import os

from common_agent.adapters.persistence.database import Database
from tests.support.conversations import delete_conversations_for_employee_names
from tests.support.employees import delete_employees_named
from tests.support.model_configuration_e2e_state import delete_model_configurations_named


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


async def _cleanup() -> int:
    employee_name = _required("COMMON_AGENT_E2E_EMPLOYEE_MODEL_EMPLOYEE_NAME")
    model_name = _required("COMMON_AGENT_E2E_EMPLOYEE_MODEL_NAME")
    database = Database(_required("COMMON_AGENT_DATABASE_URL"))
    await database.start()
    try:
        await delete_conversations_for_employee_names(database, employee_name)
        await delete_employees_named(database, employee_name)
        return await delete_model_configurations_named(database, model_name)
    finally:
        await database.stop()


def main() -> None:
    models = asyncio.run(_cleanup())
    print(f"已清理员工默认模型 E2E 数据: 模型配置={models}")


if __name__ == "__main__":
    main()
