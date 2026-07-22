from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from common_agent.application.resource_locks import ResourceMutationGuard, employee_resource
from common_agent.concurrency import KeyedLockPool
from common_agent.conversations.contracts import (
    ConversationBusy,
    ConversationHistoryItem,
    ConversationTurnAccepted,
    EmployeeDirectory,
    KnowledgeResolver,
    ModelConfigurationDirectory,
    StopAccepted,
    ToolGrantDirectory,
    TurnAccepted,
)
from common_agent.conversations.durable import ConversationTaskCoordinator
from common_agent.conversations.events import ConversationEventBroker
from common_agent.conversations.persistence import ConversationPersistence
from common_agent.conversations.projection import ConversationMessageProjector
from common_agent.conversations.runtime import ConversationRuntimeCoordinator
from common_agent.conversations.targets import ConversationExecutionTargetResolver
from common_agent.conversations.turns import ConversationTurnCoordinator
from common_agent.domain.conversation import Conversation, ConversationSource, Message
from common_agent.pagination import CursorPage, ListPageRequest
from common_agent.ports.conversations import ConversationUnitOfWorkFactory
from common_agent.runtimes.base import EmployeeRuntime
from common_agent.tasks import DurableTask, TaskExecutionContext, TaskQueue


class ConversationService:
    def __init__(
        self,
        unit_of_work_factory: ConversationUnitOfWorkFactory,
        *,
        employees: EmployeeDirectory,
        knowledge: KnowledgeResolver,
        runtime: EmployeeRuntime,
        events: ConversationEventBroker,
        model_configurations: ModelConfigurationDirectory | None = None,
        tools: ToolGrantDirectory | None = None,
        guard: ResourceMutationGuard | None = None,
        tasks: TaskQueue | None = None,
        tenant_id_provider: Callable[[], UUID] | None = None,
        task_max_attempts: int = 3,
    ) -> None:
        self._employees = employees
        self._persistence = ConversationPersistence(unit_of_work_factory)
        self._projector = ConversationMessageProjector(unit_of_work_factory, events)
        self._locks: KeyedLockPool[UUID] = KeyedLockPool()
        self._guard = guard or ResourceMutationGuard()
        self._runs = ConversationRuntimeCoordinator(
            knowledge=knowledge,
            runtime=runtime,
            events=events,
            projector=self._projector,
            locks=self._locks,
        )
        targets = ConversationExecutionTargetResolver(
            employees=employees,
            model_configurations=model_configurations,
            tools=tools,
        )
        self._durable = ConversationTaskCoordinator(
            tasks=tasks,
            tenant_id_provider=tenant_id_provider,
            maximum_attempts=task_max_attempts,
            targets=targets,
            persistence=self._persistence,
            projector=self._projector,
            runtime=self._runs,
        )
        self._turns = ConversationTurnCoordinator(
            persistence=self._persistence,
            runtime=self._runs,
            durable=self._durable,
            targets=targets,
            locks=self._locks,
            guard=self._guard,
        )

    async def list(self, *, employee_id: UUID | None = None) -> tuple[Conversation, ...]:
        return await self._persistence.list(employee_id=employee_id)

    async def page(
        self,
        page: ListPageRequest,
        *,
        employee_id: UUID | None = None,
        source: ConversationSource | None = None,
    ) -> CursorPage[ConversationHistoryItem]:
        return await self._persistence.page(page, employee_id=employee_id, source=source)

    async def get(self, conversation_id: UUID) -> ConversationHistoryItem:
        conversation = await self._persistence.get(conversation_id)
        employee_name = None
        if conversation.employee_id is not None:
            employee_name = (await self._employees.get(conversation.employee_id)).name
        return ConversationHistoryItem(
            conversation=conversation,
            employee_name=employee_name,
        )

    async def create(
        self,
        *,
        employee_id: UUID,
        title: str,
        conversation_id: UUID | None = None,
    ) -> Conversation:
        async with self._guard.hold(employee_resource(employee_id)):
            await self._employees.get(employee_id)
            return await self._persistence.create(
                employee_id=employee_id,
                title=title,
                conversation_id=conversation_id,
            )

    async def list_messages(self, conversation_id: UUID) -> tuple[Message, ...]:
        return await self._persistence.list_messages(conversation_id)

    async def delete(self, conversation_id: UUID) -> bool:
        async with self._locks.hold(conversation_id):
            if self._runs.is_active(conversation_id):
                raise ConversationBusy
            return await self._persistence.delete(conversation_id)

    async def send(
        self,
        conversation_id: UUID,
        *,
        user_message_id: UUID,
        content: str,
        model_configuration_id: UUID | None = None,
    ) -> TurnAccepted:
        return await self._turns.send(
            conversation_id,
            user_message_id=user_message_id,
            content=content,
            model_configuration_id=model_configuration_id,
        )

    async def create_first_turn(
        self,
        *,
        conversation_id: UUID,
        user_message_id: UUID,
        employee_id: UUID | None,
        model_configuration_id: UUID,
        content: str,
    ) -> ConversationTurnAccepted:
        return await self._turns.create_first(
            conversation_id=conversation_id,
            user_message_id=user_message_id,
            employee_id=employee_id,
            model_configuration_id=model_configuration_id,
            content=content,
        )

    async def stop(self, conversation_id: UUID) -> StopAccepted:
        async with self._locks.hold(conversation_id):
            if self._durable.enabled:
                return await self._durable.stop(conversation_id)
            return self._runs.stop(conversation_id)

    async def retry(self, message_id: UUID) -> TurnAccepted:
        return await self._turns.retry(message_id)

    async def execute_reply_task(
        self,
        task: DurableTask,
        context: TaskExecutionContext,
    ) -> None:
        await self._durable.execute(task, context)

    async def recover_interrupted(self) -> int:
        return await self._projector.recover_interrupted()

    async def aclose(self) -> None:
        await self._runs.aclose()


__all__ = ["ConversationService"]
