from __future__ import annotations

import asyncio
import os

from sqlalchemy import delete, select

from common_agent.adapters.persistence.database import Database
from common_agent.adapters.persistence.models import AuthUserRow, TenantRow


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


async def _cleanup() -> None:
    tenant_name = _required("COMMON_AGENT_E2E_TENANT_NAME")
    viewer_email = _required("COMMON_AGENT_E2E_VIEWER_EMAIL")
    database = Database(_required("COMMON_AGENT_DATABASE_URL"))
    await database.start()
    try:
        async with database.session() as session:
            tenant_ids = tuple(
                await session.scalars(select(TenantRow.id).where(TenantRow.name == tenant_name))
            )
            if len(tenant_ids) > 1:
                raise RuntimeError("租户/RBAC E2E 工作区名称不唯一")
            if tenant_ids:
                await session.execute(delete(TenantRow).where(TenantRow.id == tenant_ids[0]))
            await session.execute(delete(AuthUserRow).where(AuthUserRow.email == viewer_email))
            await session.commit()
    finally:
        await database.stop()


def main() -> None:
    asyncio.run(_cleanup())
    print("已清理租户/RBAC E2E 数据")


if __name__ == "__main__":
    main()
