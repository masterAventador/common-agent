from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from common_agent.ports.tool_credentials import (
    StoredMcpCredential,
    ToolCredentialCipher,
    ToolCredentialUnitOfWorkFactory,
)
from common_agent.tools.credentials import (
    CREDENTIAL_MASK,
    MaskedMcpCredential,
    McpCredential,
    McpCredentialAction,
    McpCredentialCommand,
    McpCredentialKind,
    McpCredentialSummary,
)
from common_agent.tools.models import McpSourceType


class ToolCredentialServiceError(Exception):
    code: str
    message: str
    retryable = False

    def __init__(self) -> None:
        super().__init__(self.message)


class McpCredentialSourceNotFound(ToolCredentialServiceError):
    code = "mcp_credential_source_not_found"
    message = "MCP 来源不存在"


class PlatformCredentialNotAllowed(ToolCredentialServiceError):
    code = "platform_mcp_credential_not_allowed"
    message = "平台内置 MCP 不接受外部凭据"


class ToolCredentialService:
    def __init__(
        self,
        unit_of_work_factory: ToolCredentialUnitOfWorkFactory,
        *,
        cipher: ToolCredentialCipher,
        tenant_id_provider: Callable[[], UUID],
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._cipher = cipher
        self._tenant_id_provider = tenant_id_provider

    async def get(self, source_id: UUID) -> McpCredentialSummary:
        async with self._unit_of_work_factory() as unit_of_work:
            if await unit_of_work.credentials.source_type(source_id) is None:
                raise McpCredentialSourceNotFound
            return _summary(source_id, await unit_of_work.credentials.get(source_id))

    async def update(
        self,
        source_id: UUID,
        command: McpCredentialCommand,
    ) -> McpCredentialSummary:
        async with self._unit_of_work_factory() as unit_of_work:
            source_type = await unit_of_work.credentials.source_type(source_id)
            if source_type is None:
                raise McpCredentialSourceNotFound
            existing = await unit_of_work.credentials.get(source_id)
            if command.action is McpCredentialAction.KEEP:
                return _summary(source_id, existing)
            if command.action is McpCredentialAction.CLEAR:
                if existing is not None:
                    await unit_of_work.credentials.delete(source_id)
                    await unit_of_work.commit()
                return _summary(source_id, None)
            if source_type is McpSourceType.PLATFORM:
                raise PlatformCredentialNotAllowed
            credential = command.credential
            if credential is None:
                raise RuntimeError("替换凭据命令缺少已校验的新值")
            now = datetime.now(UTC)
            stored = StoredMcpCredential(
                source_id=source_id,
                kind=credential.kind,
                encrypted=self._cipher.encrypt(
                    self._tenant_id_provider(),
                    source_id,
                    credential,
                ),
                header_names=tuple(credential.headers),
                created_at=existing.created_at if existing is not None else now,
                updated_at=now,
            )
            await unit_of_work.credentials.put(stored)
            await unit_of_work.commit()
            return _summary(source_id, stored)

    async def resolve(self, source_id: UUID) -> McpCredential | None:
        async with self._unit_of_work_factory() as unit_of_work:
            if await unit_of_work.credentials.source_type(source_id) is None:
                raise McpCredentialSourceNotFound
            stored = await unit_of_work.credentials.get(source_id)
            if stored is None:
                return None
            return self._cipher.decrypt(
                self._tenant_id_provider(),
                source_id,
                stored.encrypted,
            )


def _summary(
    source_id: UUID,
    stored: StoredMcpCredential | None,
) -> McpCredentialSummary:
    if stored is None:
        return McpCredentialSummary(
            source_id=source_id,
            configured=False,
            credential=None,
            updated_at=None,
        )
    if stored.kind is McpCredentialKind.BEARER:
        masked = MaskedMcpCredential(
            kind=stored.kind,
            bearer_token=CREDENTIAL_MASK,
        )
    else:
        masked = MaskedMcpCredential(
            kind=stored.kind,
            headers={name: CREDENTIAL_MASK for name in stored.header_names},
        )
    return McpCredentialSummary(
        source_id=source_id,
        configured=True,
        credential=masked,
        updated_at=stored.updated_at,
    )


__all__ = [
    "McpCredentialSourceNotFound",
    "PlatformCredentialNotAllowed",
    "ToolCredentialService",
    "ToolCredentialServiceError",
]
