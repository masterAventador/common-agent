from __future__ import annotations

from collections.abc import Callable
from uuid import UUID, uuid4

from common_agent.application.resource_locks import (
    ResourceMutationGuard,
    employee_resource,
)
from common_agent.concurrency import KeyedLockPool
from common_agent.conversations.contracts import (
    ConversationBusy,
    EmployeeDirectory,
    KnowledgeResolver,
    StopAccepted,
    TurnAccepted,
)
from common_agent.conversations.durable import ConversationTaskCoordinator
from common_agent.conversations.events import ConversationEventBroker
from common_agent.conversations.persistence import ConversationPersistence
from common_agent.conversations.projection import ConversationMessageProjector
from common_agent.conversations.runtime import ConversationRuntimeCoordinator
from common_agent.domain.conversation import Conversation, Message
from common_agent.pagination import CursorPage, ListPageRequest
from common_agent.ports.conversations import ConversationUnitOfWorkFactory
from common_agent.runtimes.base import EmployeeRuntime
from common_agent.tasks import (
    DurableTask,
    TaskExecutionContext,
    TaskQueue,
)


class ConversationService:
    def __init__(
        self,
        unit_of_work_factory: ConversationUnitOfWorkFactory,
        *,
        employees: EmployeeDirectory,
        knowledge: KnowledgeResolver,
        runtime: EmployeeRuntime,
        events: ConversationEventBroker,
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
        self._durable = ConversationTaskCoordinator(
            tasks=tasks,
            tenant_id_provider=tenant_id_provider,
            maximum_attempts=task_max_attempts,
            employees=employees,
            persistence=self._persistence,
            projector=self._projector,
            runtime=self._runs,
        )

    async def list(self, *, employee_id: UUID | None = None) -> tuple[Conversation, ...]:
        return await self._persistence.list(employee_id=employee_id)

    async def page(
        self,
        page: ListPageRequest,
        *,
        employee_id: UUID | None = None,
    ) -> CursorPage[Conversation]:
        return await self._persistence.page(page, employee_id=employee_id)

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
    ) -> TurnAccepted:
        self._runs.ensure_open()
        async with self._locks.hold(conversation_id):
            if self._runs.is_active(conversation_id):
                raise ConversationBusy
            conversation, _ = await self._persistence.load(conversation_id)
            employee = await self._employees.get(conversation.employee_id)
            turn_id = uuid4()
            assistant_message_id = uuid4()
            task_request = self._durable.request(
                conversation_id=conversation_id,
                turn_id=turn_id,
                user_message_id=user_message_id,
                assistant_message_id=assistant_message_id,
                retry=False,
            )
            prepared = await self._persistence.append_turn(
                conversation_id,
                user_message_id=user_message_id,
                assistant_message_id=assistant_message_id,
                content=content,
                task_request=task_request,
                task_max_attempts=self._durable.maximum_attempts,
            )
            if not self._durable.enabled:
                await self._runs.start(
                    turn_id=turn_id,
                    employee=employee,
                    history=prepared.history,
                    user_message=prepared.user_message,
                    assistant_message=prepared.assistant_message,
                    retry=False,
                )
            return TurnAccepted(
                turn_id=turn_id,
                user_message=prepared.user_message,
                assistant_message=prepared.assistant_message,
                retry=False,
            )

    async def stop(self, conversation_id: UUID) -> StopAccepted:
        async with self._locks.hold(conversation_id):
            if self._durable.enabled:
                return await self._durable.stop(conversation_id)
            return self._runs.stop(conversation_id)

    async def retry(self, message_id: UUID) -> TurnAccepted:
        self._runs.ensure_open()
        message = await self._persistence.get_message(message_id)
        async with self._locks.hold(message.conversation_id):
            if self._runs.is_active(message.conversation_id):
                raise ConversationBusy
            prepared = await self._persistence.prepare_retry(message)
            employee = await self._employees.get(prepared.conversation.employee_id)
            turn_id = uuid4()
            task_request = self._durable.request(
                conversation_id=prepared.conversation.id,
                turn_id=turn_id,
                user_message_id=prepared.user_message.id,
                assistant_message_id=prepared.assistant_message.id,
                retry=True,
            )
            await self._persistence.commit_retry(
                prepared,
                task_request=task_request,
                task_max_attempts=self._durable.maximum_attempts,
            )
            if not self._durable.enabled:
                await self._runs.start(
                    turn_id=turn_id,
                    employee=employee,
                    history=prepared.history,
                    user_message=prepared.user_message,
                    assistant_message=prepared.assistant_message,
                    retry=True,
                )
            return TurnAccepted(
                turn_id=turn_id,
                user_message=prepared.user_message,
                assistant_message=prepared.assistant_message,
                retry=True,
            )

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
