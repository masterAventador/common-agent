from __future__ import annotations

import asyncio
import os

from common_agent.adapters.persistence.database import Database
from tests.support.employees import delete_employees_named


async def main() -> None:
    database_url = os.environ["COMMON_AGENT_DATABASE_URL"]
    employee_name = os.environ["COMMON_AGENT_E2E_AUDIT_EMPLOYEE_NAME"]
    database = Database(database_url)
    await database.start()
    try:
        await delete_employees_named(database, employee_name)
    finally:
        await database.stop()


if __name__ == "__main__":
    asyncio.run(main())
