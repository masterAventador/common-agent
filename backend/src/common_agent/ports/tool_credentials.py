from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from types import TracebackType
from typing import Protocol
from uuid import UUID

from common_agent.tools.credentials import (
    EncryptedMcpCredential,
    McpCredential,
    McpCredentialKind,
)
from common_agent.tools.models import McpSourceType


@dataclass(frozen=True, slots=True)
class StoredMcpCredential:
    source_id: UUID
    kind: McpCredentialKind
    encrypted: EncryptedMcpCredential = field(repr=False)
    header_names: tuple[str, ...]
    created_at: datetime
    updated_at: datetime


class ToolCredentialCipher(Protocol):
    def encrypt(
        self,
        tenant_id: UUID,
        source_id: UUID,
        credential: McpCredential,
    ) -> EncryptedMcpCredential: ...

    def decrypt(
        self,
        tenant_id: UUID,
        source_id: UUID,
        encrypted: EncryptedMcpCredential,
    ) -> McpCredential: ...


class ToolCredentialRepository(Protocol):
    async def source_type(self, source_id: UUID) -> McpSourceType | None: ...

    async def get(self, source_id: UUID) -> StoredMcpCredential | None: ...

    async def put(self, credential: StoredMcpCredential) -> None: ...

    async def delete(self, source_id: UUID) -> None: ...


class ToolCredentialUnitOfWork(Protocol):
    @property
    def credentials(self) -> ToolCredentialRepository: ...

    async def __aenter__(self) -> ToolCredentialUnitOfWork: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...


class ToolCredentialUnitOfWorkFactory(Protocol):
    def __call__(self) -> ToolCredentialUnitOfWork: ...


__all__ = [
    "StoredMcpCredential",
    "ToolCredentialCipher",
    "ToolCredentialRepository",
    "ToolCredentialUnitOfWork",
    "ToolCredentialUnitOfWorkFactory",
]
