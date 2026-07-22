from __future__ import annotations

import asyncio
from types import TracebackType
from uuid import UUID, uuid4

import pytest

from common_agent.adapters.security.tool_credentials import AesGcmToolCredentialCipher
from common_agent.ports.tool_credentials import (
    StoredMcpCredential,
    ToolCredentialRepository,
)
from common_agent.tools.credential_service import (
    McpCredentialSourceNotFound,
    PlatformCredentialNotAllowed,
    ToolCredentialService,
)
from common_agent.tools.credentials import (
    CREDENTIAL_MASK,
    McpCredential,
    McpCredentialAction,
    McpCredentialCommand,
)
from common_agent.tools.models import McpSourceType


class FakeRepository:
    def __init__(self, source_id: UUID, source_type: McpSourceType) -> None:
        self.source_id = source_id
        self.source_type_value = source_type
        self.stored: StoredMcpCredential | None = None

    async def source_type(self, source_id: UUID) -> McpSourceType | None:
        return self.source_type_value if source_id == self.source_id else None

    async def get(self, source_id: UUID) -> StoredMcpCredential | None:
        return self.stored if source_id == self.source_id else None

    async def put(self, credential: StoredMcpCredential) -> None:
        self.stored = credential

    async def delete(self, source_id: UUID) -> None:
        if source_id == self.source_id:
            self.stored = None


class FakeUnitOfWork:
    def __init__(self, repository: ToolCredentialRepository) -> None:
        self.repository = repository
        self.commits = 0

    @property
    def credentials(self) -> ToolCredentialRepository:
        return self.repository

    async def __aenter__(self) -> FakeUnitOfWork:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_type, exc_value, traceback

    async def commit(self) -> None:
        self.commits += 1


def _service(
    repository: FakeRepository,
    tenant_id: UUID,
) -> tuple[ToolCredentialService, FakeUnitOfWork]:
    unit = FakeUnitOfWork(repository)
    return (
        ToolCredentialService(
            lambda: unit,
            cipher=AesGcmToolCredentialCipher(
                keys={"active": b"a" * 32},
                active_key_id="active",
            ),
            tenant_id_provider=lambda: tenant_id,
        ),
        unit,
    )


def test_replace_masks_response_and_keep_preserves_ciphertext_exactly() -> None:
    tenant_id = uuid4()
    source_id = uuid4()
    repository = FakeRepository(source_id, McpSourceType.EXTERNAL)
    service, unit = _service(repository, tenant_id)

    replaced = asyncio.run(
        service.update(
            source_id,
            McpCredentialCommand(
                action=McpCredentialAction.REPLACE,
                credential=McpCredential.bearer("plain-secret"),
            ),
        )
    )
    assert replaced.credential is not None
    assert replaced.credential.bearer_token == CREDENTIAL_MASK
    assert repository.stored is not None
    original = repository.stored

    kept = asyncio.run(
        service.update(
            source_id,
            McpCredentialCommand(action=McpCredentialAction.KEEP),
        )
    )

    assert kept == replaced
    assert repository.stored is original
    assert unit.commits == 1


def test_clear_is_idempotent_and_commits_only_when_record_existed() -> None:
    tenant_id = uuid4()
    source_id = uuid4()
    repository = FakeRepository(source_id, McpSourceType.MANAGED_HTTP)
    service, unit = _service(repository, tenant_id)
    asyncio.run(
        service.update(
            source_id,
            McpCredentialCommand(
                action=McpCredentialAction.REPLACE,
                credential=McpCredential.custom_headers({"X-Api-Key": "secret"}),
            ),
        )
    )

    cleared = asyncio.run(
        service.update(source_id, McpCredentialCommand(action=McpCredentialAction.CLEAR))
    )
    cleared_again = asyncio.run(
        service.update(source_id, McpCredentialCommand(action=McpCredentialAction.CLEAR))
    )

    assert cleared.configured is False
    assert cleared_again.configured is False
    assert unit.commits == 2


def test_missing_and_platform_sources_fail_closed() -> None:
    tenant_id = uuid4()
    source_id = uuid4()
    repository = FakeRepository(source_id, McpSourceType.PLATFORM)
    service, _ = _service(repository, tenant_id)
    replace = McpCredentialCommand(
        action=McpCredentialAction.REPLACE,
        credential=McpCredential.bearer("secret"),
    )

    with pytest.raises(McpCredentialSourceNotFound):
        asyncio.run(service.update(uuid4(), replace))
    with pytest.raises(PlatformCredentialNotAllowed):
        asyncio.run(service.update(source_id, replace))
