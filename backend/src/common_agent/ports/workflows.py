from __future__ import annotations

from types import TracebackType
from typing import Protocol
from uuid import UUID

from common_agent.domain.workflow import WorkflowDefinition
from common_agent.domain.workflow_run import WorkflowRun


class WorkflowAlreadyExists(Exception):
    """Raised when a workflow identity is already persisted."""


class WorkflowRunAlreadyExists(Exception):
    """Raised when a workflow run identity is already persisted."""


class WorkflowRepository(Protocol):
    async def list(self) -> tuple[WorkflowDefinition, ...]: ...

    async def get(self, workflow_id: UUID) -> WorkflowDefinition | None: ...

    async def add(self, workflow: WorkflowDefinition) -> None: ...

    async def update(self, workflow: WorkflowDefinition) -> bool: ...


class WorkflowRunRepository(Protocol):
    async def get(self, run_id: UUID) -> WorkflowRun | None: ...

    async def list_active(self) -> tuple[WorkflowRun, ...]: ...

    async def list_for_conversation(self, conversation_id: UUID) -> tuple[WorkflowRun, ...]: ...

    async def add(self, run: WorkflowRun) -> None: ...

    async def update(self, run: WorkflowRun) -> bool: ...


class WorkflowUnitOfWork(Protocol):
    @property
    def workflows(self) -> WorkflowRepository: ...

    @property
    def workflow_runs(self) -> WorkflowRunRepository: ...

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
