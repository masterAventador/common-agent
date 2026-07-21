from __future__ import annotations

import asyncio
import os

from sqlalchemy import delete

from common_agent.adapters.persistence.database import Database
from common_agent.adapters.persistence.models import EmployeeRow


async def main() -> None:
    database_url = os.environ["COMMON_AGENT_DATABASE_URL"]
    employee_name = os.environ["COMMON_AGENT_E2E_AUDIT_EMPLOYEE_NAME"]
    database = Database(database_url)
    await database.start()
    try:
        async with database.session() as session:
            await session.execute(delete(EmployeeRow).where(EmployeeRow.name == employee_name))
            await session.commit()
    finally:
        await database.stop()


if __name__ == "__main__":
    asyncio.run(main())
