from __future__ import annotations

import asyncio
from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy import select, text

from common_agent.adapters.persistence.database import Database
from common_agent.adapters.persistence.models import McpSourceCredentialRow, McpSourceRow
from common_agent.adapters.persistence.tool_credentials import (
    SqlAlchemyToolCredentialRepository,
)
from common_agent.tenancy.constants import DEFAULT_TENANT_ID
from common_agent.tools import McpSource, McpSourceStatus, McpSourceType
from tests.support.http import assert_error_response, authenticated_client, running_api
from tests.support.settings import TEST_DATABASE_URL


@dataclass(frozen=True, slots=True)
class RawCredential:
    credential_type: str
    key_id: str
    nonce: bytes
    ciphertext: bytes
    header_names: tuple[str, ...]
    updated_at: object


async def _seed_source(source_type: McpSourceType) -> McpSource:
    source = McpSource.create(
        name=f"凭据正式测试-{uuid4().hex}",
        source_type=source_type,
        endpoint_url=(
            "https://mcp.example.com/mcp" if source_type is not McpSourceType.PLATFORM else None
        ),
        status=McpSourceStatus.READY,
    )
    database = Database(TEST_DATABASE_URL)
    await database.start()
    try:
        async with database.session() as session:
            session.add(
                McpSourceRow(
                    id=str(source.id),
                    tenant_id=str(DEFAULT_TENANT_ID),
                    name=source.name,
                    description=source.description,
                    source_type=source.source_type.value,
                    endpoint_url=source.endpoint_url,
                    status=source.status.value,
                    created_at=source.created_at.replace(tzinfo=None),
                    updated_at=source.updated_at.replace(tzinfo=None),
                )
            )
            await session.commit()
    finally:
        await database.stop()
    return source


async def _raw(source_id: UUID) -> RawCredential | None:
    database = Database(TEST_DATABASE_URL)
    await database.start()
    try:
        async with database.session() as session:
            row = await session.scalar(
                select(McpSourceCredentialRow).where(
                    McpSourceCredentialRow.tenant_id == str(DEFAULT_TENANT_ID),
                    McpSourceCredentialRow.source_id == str(source_id),
                )
            )
            if row is None:
                return None
            return RawCredential(
                credential_type=row.credential_type,
                key_id=row.key_id,
                nonce=bytes(row.nonce),
                ciphertext=bytes(row.ciphertext),
                header_names=tuple(row.header_names),
                updated_at=row.updated_at,
            )
    finally:
        await database.stop()


async def _assert_other_tenant_cannot_read(source_id: UUID) -> None:
    database = Database(TEST_DATABASE_URL)
    await database.start()
    try:
        async with database.session() as session:
            repository = SqlAlchemyToolCredentialRepository(session, uuid4())
            assert await repository.source_type(source_id) is None
            assert await repository.get(source_id) is None
    finally:
        await database.stop()


async def _secret_absent_from_audit(secret: str) -> None:
    database = Database(TEST_DATABASE_URL)
    await database.start()
    try:
        async with database.session() as session:
            rows = (
                await session.execute(
                    text(
                        "SELECT action, resource_type, resource_id, error_code "
                        "FROM audit_events WHERE action = 'tool.credentials.updated'"
                    )
                )
            ).all()
            assert rows
            assert secret not in repr(rows)
    finally:
        await database.stop()


async def _cleanup(*source_ids: UUID) -> None:
    database = Database(TEST_DATABASE_URL)
    await database.start()
    try:
        async with database.session() as session:
            for source_id in source_ids:
                await session.execute(
                    text("DELETE FROM mcp_sources WHERE id = :source_id"),
                    {"source_id": str(source_id)},
                )
            await session.commit()
    finally:
        await database.stop()


def test_mcp_credentials_are_encrypted_masked_preserved_and_tenant_scoped() -> None:
    source = asyncio.run(_seed_source(McpSourceType.EXTERNAL))
    platform = asyncio.run(_seed_source(McpSourceType.PLATFORM))
    bearer_secret = "bearer-plain-value-must-not-leak"
    header_secret = "header-plain-value-must-not-leak"
    try:
        with (
            running_api(TEST_DATABASE_URL) as api_url,
            authenticated_client(base_url=api_url, timeout=5) as client,
        ):
            empty = client.get(f"/api/v1/mcp-sources/{source.id}/credentials")
            assert empty.status_code == 200
            assert empty.json() == {
                "source_id": str(source.id),
                "configured": False,
                "credential": None,
                "updated_at": None,
            }

            bearer = client.put(
                f"/api/v1/mcp-sources/{source.id}/credentials",
                json={
                    "action": "replace",
                    "kind": "bearer",
                    "bearer_token": bearer_secret,
                },
            )
            assert bearer.status_code == 200
            assert bearer_secret not in bearer.text
            assert bearer.json()["credential"] == {
                "kind": "bearer",
                "bearer_token": "********",
                "headers": {},
            }
            first = asyncio.run(_raw(source.id))
            assert first is not None
            assert first.credential_type == "bearer"
            assert first.header_names == ()
            assert bearer_secret.encode() not in first.ciphertext

            kept = client.put(
                f"/api/v1/mcp-sources/{source.id}/credentials",
                json={"action": "keep"},
            )
            assert kept.status_code == 200
            second = asyncio.run(_raw(source.id))
            assert second == first

            headers = client.put(
                f"/api/v1/mcp-sources/{source.id}/credentials",
                json={
                    "action": "replace",
                    "kind": "custom_headers",
                    "headers": {"X-Api-Key": header_secret},
                },
            )
            assert headers.status_code == 200
            assert header_secret not in headers.text
            assert headers.json()["credential"] == {
                "kind": "custom_headers",
                "bearer_token": None,
                "headers": {"X-Api-Key": "********"},
            }
            third = asyncio.run(_raw(source.id))
            assert third is not None
            assert third.header_names == ("X-Api-Key",)
            assert header_secret.encode() not in third.ciphertext

            invalid = client.put(
                f"/api/v1/mcp-sources/{source.id}/credentials",
                json={
                    "action": "replace",
                    "kind": "custom_headers",
                    "headers": {"Host": "override"},
                },
            )
            assert_error_response(invalid, status=422, code="validation_error")
            platform_rejected = client.put(
                f"/api/v1/mcp-sources/{platform.id}/credentials",
                json={
                    "action": "replace",
                    "kind": "bearer",
                    "bearer_token": bearer_secret,
                },
            )
            assert_error_response(
                platform_rejected,
                status=409,
                code="platform_mcp_credential_not_allowed",
            )
            missing = client.get(f"/api/v1/mcp-sources/{uuid4()}/credentials")
            assert_error_response(
                missing,
                status=404,
                code="mcp_credential_source_not_found",
            )

            cleared = client.put(
                f"/api/v1/mcp-sources/{source.id}/credentials",
                json={"action": "clear"},
            )
            assert cleared.status_code == 200
            assert cleared.json()["configured"] is False
            assert asyncio.run(_raw(source.id)) is None

        asyncio.run(_assert_other_tenant_cannot_read(source.id))
        asyncio.run(_secret_absent_from_audit(header_secret))
    finally:
        asyncio.run(_cleanup(source.id, platform.id))
