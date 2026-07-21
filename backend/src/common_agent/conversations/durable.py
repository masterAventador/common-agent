from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, UUID, uuid5

from common_agent.conversations.contracts import (
    EmployeeDirectory,
    GenerationNotActive,
    StopAccepted,
)
from common_agent.conversations.persistence import ConversationPersistence
from common_agent.conversations.projection import ConversationMessageProjector, safe_error_code
from common_agent.conversations.runtime import (
    ConversationExecutionFailed,
    ConversationRuntimeCoordinator,
)
from common_agent.domain.conversation import MessageStatus
from common_agent.tasks import (
    ConversationReplyPayload,
    DurableTask,
    TaskCancelled,
    TaskExecutionContext,
    TaskFatalError,
    TaskKind,
    TaskNotFound,
    TaskQueue,
    TaskRequest,
    TaskRetryableError,
)


class ConversationTaskCoordinator:
    def __init__(
        self,
        *,
        tasks: TaskQueue | None,
        tenant_id_provider: Callable[[], UUID] | None,
        maximum_attempts: int,
        employees: EmployeeDirectory,
        persistence: ConversationPersistence,
        projector: ConversationMessageProjector,
        runtime: ConversationRuntimeCoordinator,
    ) -> None:
        if (tasks is None) != (tenant_id_provider is None):
            raise ValueError("tasks and tenant_id_provider must be configured together")
        if not 1 <= maximum_attempts <= 100:
            raise ValueError("maximum_attempts must be between 1 and 100")
        self._tasks = tasks
        self._tenant_id_provider = tenant_id_provider
        self.maximum_attempts = maximum_attempts
        self._employees = employees
        self._persistence = persistence
        self._projector = projector
        self._runtime = runtime

    @property
    def enabled(self) -> bool:
        return self._tasks is not None

    def request(
        self,
        *,
        conversation_id: UUID,
        turn_id: UUID,
        user_message_id: UUID,
        assistant_message_id: UUID,
        retry: bool,
    ) -> TaskRequest | None:
        if self._tasks is None:
            return None
        tenant_id = self._tenant_id
        key = f"conversation:{conversation_id}:turn:{turn_id}"
        return TaskRequest(
            task_id=uuid5(NAMESPACE_URL, f"common-agent:{tenant_id}:{key}"),
            tenant_id=tenant_id,
            kind=TaskKind.CONVERSATION_REPLY,
            idempotency_key=key,
            aggregate_id=conversation_id,
            payload=ConversationReplyPayload(
                conversation_id=conversation_id,
                turn_id=turn_id,
                user_message_id=user_message_id,
                assistant_message_id=assistant_message_id,
                retry=retry,
            ),
            created_at=datetime.now(UTC),
        )

    async def stop(self, conversation_id: UUID) -> StopAccepted:
        if self._tasks is None:
            raise RuntimeError("durable tasks are not configured")
        try:
            task = await self._tasks.request_stop_for_aggregate(
                tenant_id=self._tenant_id,
                kind=TaskKind.CONVERSATION_REPLY,
                aggregate_id=conversation_id,
                now=datetime.now(UTC),
            )
        except TaskNotFound:
            raise GenerationNotActive from None
        payload = task.request.payload
        if not isinstance(payload, ConversationReplyPayload):
            raise RuntimeError("conversation task payload is invalid")
        return StopAccepted(
            turn_id=payload.turn_id,
            assistant_message_id=payload.assistant_message_id,
        )

    async def execute(self, task: DurableTask, context: TaskExecutionContext) -> None:
        payload = self._payload(task)
        conversation, messages = await self._persistence.load(payload.conversation_id)
        user_message = next((item for item in messages if item.id == payload.user_message_id), None)
        assistant_message = next(
            (item for item in messages if item.id == payload.assistant_message_id),
            None,
        )
        if (
            user_message is None
            or assistant_message is None
            or user_message.conversation_id != conversation.id
            or assistant_message.conversation_id != conversation.id
            or assistant_message.sequence_number != user_message.sequence_number + 1
        ):
            raise TaskFatalError("conversation_task_state_invalid")
        if assistant_message.is_terminal:
            await self._projector.republish_terminal(payload.turn_id, assistant_message)
            if assistant_message.status is MessageStatus.STOPPED:
                raise TaskCancelled
            if assistant_message.status is MessageStatus.FAILED:
                raise TaskFatalError(assistant_message.error_code or "generation_failed")
            return
        if context.stop_requested:
            await self._projector.persist_stopped(payload.turn_id, assistant_message.id)
            raise TaskCancelled
        try:
            if task.attempts > 1:
                assistant_message = await self._projector.restart_execution(assistant_message.id)
            employee = await self._employees.get(conversation.employee_id)
            await self._runtime.execute(
                turn_id=payload.turn_id,
                employee=employee,
                history=messages,
                user_message=user_message,
                assistant_message=assistant_message,
                stop=context,
                retry=payload.retry,
                persist_failures=False,
            )
        except ConversationExecutionFailed as error:
            error_code = error.code
        except Exception as error:
            error_code = safe_error_code(error)
        else:
            persisted = await self._persistence.get_message(assistant_message.id)
            if persisted.status is MessageStatus.STOPPED:
                raise TaskCancelled
            if persisted.status is MessageStatus.FAILED:
                raise TaskFatalError(persisted.error_code or "generation_failed")
            return

        if task.attempts < task.max_attempts:
            raise TaskRetryableError(error_code) from None
        await self._projector.persist_failure(
            payload.turn_id,
            assistant_message.id,
            error_code,
        )
        raise TaskFatalError(error_code) from None

    @staticmethod
    def _payload(task: DurableTask) -> ConversationReplyPayload:
        if task.request.kind is not TaskKind.CONVERSATION_REPLY or not isinstance(
            task.request.payload, ConversationReplyPayload
        ):
            raise TaskFatalError("conversation_task_payload_invalid")
        return task.request.payload

    @property
    def _tenant_id(self) -> UUID:
        if self._tenant_id_provider is None:
            raise RuntimeError("durable task tenant provider is not configured")
        return self._tenant_id_provider()


__all__ = ["ConversationTaskCoordinator"]
