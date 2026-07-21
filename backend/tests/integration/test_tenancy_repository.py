from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import delete

from common_agent.adapters.auth.passwords import Argon2PasswordHasher
from common_agent.adapters.persistence.auth import SqlAlchemyAuthStore
from common_agent.adapters.persistence.database import Database
from common_agent.adapters.persistence.models import AuthUserRow, TenantRow
from common_agent.adapters.persistence.tenancy import SqlAlchemyTenancyStore
from common_agent.auth.credentials import digest_secret
from common_agent.tenancy.constants import DEFAULT_ORGANIZATION_ID, DEFAULT_TENANT_ID
from common_agent.tenancy.models import TenantRole
from tests.support.settings import TEST_DATABASE_URL


def _database_url() -> str:
    return os.environ.get("TEST_PLATFORM_DATABASE_URL", TEST_DATABASE_URL)


def test_owner_bootstrap_atomically_owns_legacy_tenant_and_can_create_an_isolated_tenant() -> None:
    async def exercise() -> None:
        database = Database(_database_url())
        await database.start()
        auth_store = SqlAlchemyAuthStore(database)
        tenancy_store = SqlAlchemyTenancyStore(database)
        email = f"tenant-owner-{uuid4()}@example.com"
        now = datetime(2026, 7, 21, 13, 0, tzinfo=UTC)
        try:
            async with database.session() as session:
                await session.execute(
                    delete(AuthUserRow).where(AuthUserRow.bootstrap_slot == "owner")
                )
                await session.commit()
            user = await auth_store.create_owner(
                email=email,
                password_hash=Argon2PasswordHasher().hash("correct horse battery staple"),
                recovery_digests=(digest_secret("TENANT-RECOVERY"),),
                now=now,
            )
            assert user is not None
            user_id = UUID(user.id)

            default_access = await tenancy_store.find_access(user_id, DEFAULT_TENANT_ID)
            assert default_access is not None
            assert default_access.organization_id == DEFAULT_ORGANIZATION_ID
            assert default_access.role is TenantRole.OWNER

            created = await tenancy_store.create_tenant(
                owner_user_id=user_id,
                organization_id=DEFAULT_ORGANIZATION_ID,
                name="隔离工作区",
                now=now,
            )
            assert created.role is TenantRole.OWNER
            assert created.tenant_id != DEFAULT_TENANT_ID
            assert {item.tenant_id for item in await tenancy_store.list_access(user_id)} == {
                DEFAULT_TENANT_ID,
                created.tenant_id,
            }
        finally:
            async with database.session() as session:
                await session.execute(delete(TenantRow).where(TenantRow.name == "隔离工作区"))
                await session.execute(delete(AuthUserRow).where(AuthUserRow.email == email))
                await session.commit()
            await database.stop()

    asyncio.run(exercise())
