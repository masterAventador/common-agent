from __future__ import annotations

from types import TracebackType
from typing import Protocol
from uuid import UUID

from common_agent.domain.workflow import WorkflowDefinition


class WorkflowAlreadyExists(Exception):
    """Raised when a workflow identity is already persisted."""


class WorkflowRepository(Protocol):
    async def list(self) -> tuple[WorkflowDefinition, ...]: ...

    async def get(self, workflow_id: UUID) -> WorkflowDefinition | None: ...

    async def add(self, workflow: WorkflowDefinition) -> None: ...

    async def update(self, workflow: WorkflowDefinition) -> bool: ...


class WorkflowUnitOfWork(Protocol):
    @property
    def workflows(self) -> WorkflowRepository: ...

    async def __aenter__(self) -> WorkflowUnitOfWork: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...


class WorkflowUnitOfWorkFactory(Protocol):
    def __call__(self) -> WorkflowUnitOfWork: ...
