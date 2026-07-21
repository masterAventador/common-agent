from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select

from common_agent.adapters.persistence.conversations import (
    SqlAlchemyConversationRepository,
    SqlAlchemyConversationUnitOfWorkFactory,
    SqlAlchemyMessageRepository,
)
from common_agent.adapters.persistence.database import Database
from common_agent.adapters.persistence.employees import SqlAlchemyEmployeeRepository
from common_agent.adapters.persistence.models import DurableTaskRow
from common_agent.adapters.persistence.tasks import SqlAlchemyTaskQueue
from common_agent.conversations.contracts import ConversationBusy, MessageRequestConflict
from common_agent.conversations.events import (
    ConversationEvent,
    ConversationEventBroker,
    ConversationEventKind,
)
from common_agent.conversations.service import ConversationService
from common_agent.domain.conversation import Conversation, Message, MessageStatus
from common_agent.domain.employee import Employee
from common_agent.employees.service import EmployeeNotFound
from common_agent.knowledge.retrieval import ResolvedKnowledgeContext
from common_agent.runtimes.base import (
    EmployeeRuntimeRequest,
    RuntimeEvent,
    RuntimeEventEmitter,
    RuntimeStopSignal,
)
from common_agent.tasks import TaskKind, TaskWorker
from common_agent.tenancy.constants import DEFAULT_TENANT_ID
from tests.support.conversations import delete_conversations
from tests.support.employees import default_employee_model_fields, delete_employees
from tests.support.settings import TEST_DATABASE_URL


def _database_url() -> str:
    return os.environ.get("TEST_PLATFORM_DATABASE_URL", TEST_DATABASE_URL)


@asynccontextmanager
async def _database() -> AsyncIterator[Database]:
    database = Database(_database_url())
    await database.start()
    try:
        yield database
    finally:
        await database.stop()


class _Employees:
    def __init__(self, employee: Employee) -> None:
        self.employee = employee

    async def get(self, employee_id: UUID) -> Employee:
        assert employee_id == self.employee.id
        return self.employee


class _UnavailableAfterValidationEmployees(_Employees):
    def __init__(self, employee: Employee) -> None:
        super().__init__(employee)
        self.calls = 0

    async def get(self, employee_id: UUID) -> Employee:
        self.calls += 1
        if self.calls > 2:
            raise EmployeeNotFound
        return await super().get(employee_id)


class _NoKnowledge:
    async def resolve(self, employee: Employee, user_message: object) -> ResolvedKnowledgeContext:
        assert employee.knowledge_base_id is None
        return ResolvedKnowledgeContext(
            knowledge_base_id=None,
            runtime_chunks=(),
            citations=(),
        )


class _ScriptedRuntime:
    def __init__(self, *, block_first_until_stopped: bool = False) -> None:
        self.block_first_until_stopped = block_first_until_stopped
        self.requests: list[EmployeeRuntimeRequest] = []
        self.closed = False

    async def stream(
        self,
        request: EmployeeRuntimeRequest,
        *,
        stop: RuntimeStopSignal,
    ) -> AsyncIterator[RuntimeEvent]:
        self.requests.append(request)
        emitter = RuntimeEventEmitter(request.assistant_message_id)
        yield emitter.delta("第一段")
        if self.block_first_until_stopped and len(self.requests) == 1:
            await stop.wait()
            yield emitter.stop()
            return
        yield emitter.delta("第二段")
        yield emitter.complete()

    async def aclose(self) -> None:
        self.closed = True


class _InterruptedRuntime:
    async def stream(
        self,
        request: EmployeeRuntimeRequest,
        *,
        stop: RuntimeStopSignal,
    ) -> AsyncIterator[RuntimeEvent]:
        del stop
        yield RuntimeEventEmitter(request.assistant_message_id).delta("断流前内容")

    async def aclose(self) -> None:
        return None


class _RetryingRuntime:
    def __init__(self) -> None:
        self.attempts = 0

    async def stream(
        self,
        request: EmployeeRuntimeRequest,
        *,
        stop: RuntimeStopSignal,
    ) -> AsyncIterator[RuntimeEvent]:
        del stop
        self.attempts += 1
        emitter = RuntimeEventEmitter(request.assistant_message_id)
        if self.attempts == 1:
            yield emitter.delta("不应保留的半截内容")
            raise RuntimeError("temporary disconnect")
        yield emitter.delta("重试后的完整内容")
        yield emitter.complete()

    async def aclose(self) -> None:
        return None


class _FailTerminalEventOnce(ConversationEventBroker):
    def __init__(self) -> None:
        super().__init__()
        self.failed = False

    async def publish(
        self,
        *,
        turn_id: UUID,
        message: Message,
        kind: ConversationEventKind,
        delta: str | None = None,
        retry: bool = False,
    ) -> ConversationEvent:
        if kind is ConversationEventKind.ASSISTANT_COMPLETED and not self.failed:
            self.failed = True
            raise RuntimeError("event journal temporarily unavailable")
        return await super().publish(
            turn_id=turn_id,
            message=message,
            kind=kind,
            delta=delta,
            retry=retry,
        )


class _InvalidSequenceRuntime:
    async def stream(
        self,
        request: EmployeeRuntimeRequest,
        *,
        stop: RuntimeStopSignal,
    ) -> AsyncIterator[RuntimeEvent]:
        del stop
        emitter = RuntimeEventEmitter(request.assistant_message_id)
        yield emitter.delta("第一段")
        first = emitter.delta("不应落库的乱序内容")
        yield RuntimeEvent(
            assistant_message_id=first.assistant_message_id,
            sequence=1,
            kind=first.kind,
            delta=first.delta,
        )

    async def aclose(self) -> None:
        return None


class _LateEventRuntime:
    def __init__(self) -> None:
        self.resumed_after_terminal = False

    async def stream(
        self,
        request: EmployeeRuntimeRequest,
        *,
        stop: RuntimeStopSignal,
    ) -> AsyncIterator[RuntimeEvent]:
        del stop
        emitter = RuntimeEventEmitter(request.assistant_message_id)
        yield emitter.delta("完整内容")
        yield emitter.complete()
        self.resumed_after_terminal = True
        yield RuntimeEvent(
            assistant_message_id=request.assistant_message_id,
            sequence=3,
            kind=emitter.delta("晚到内容").kind,
            delta="晚到内容",
        )

    async def aclose(self) -> None:
        return None


class _CompletionAfterStopRuntime:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release_completion = asyncio.Event()

    async def stream(
        self,
        request: EmployeeRuntimeRequest,
        *,
        stop: RuntimeStopSignal,
    ) -> AsyncIterator[RuntimeEvent]:
        del stop
        emitter = RuntimeEventEmitter(request.assistant_message_id)
        yield emitter.delta("停止前内容")
        self.started.set()
        await self.release_completion.wait()
        yield emitter.complete()

    async def aclose(self) -> None:
        return None


async def _delete_durable_tasks(database: Database) -> None:
    async with database.session() as session:
        await session.execute(delete(DurableTaskRow))
        await session.commit()


async def _events_until_terminal(
    broker: ConversationEventBroker,
    conversation_id: UUID,
    *,
    after_sequence: int = 0,
) -> list[ConversationEvent]:
    result: list[ConversationEvent] = []
    stream = broker.stream(conversation_id, after_sequence=after_sequence)
    try:
        async with asyncio.timeout(3):
            async for event in stream:
                result.append(event)
                if event.kind.value in {
                    "assistant.completed",
                    "assistant.failed",
                    "assistant.stopped",
                }:
                    return result
    finally:
        await stream.aclose()
    raise AssertionError("terminal event was not received")


def test_service_persists_each_state_before_publishing_monotonic_events() -> None:
    employee = Employee.create(
        name=f"service-{uuid4().hex}",
        system_prompt="直接回答问题",
        **default_employee_model_fields(),
    )
    conversation_id = uuid4()

    async def exercise() -> None:
        async with _database() as database:
            runtime = _ScriptedRuntime()
            events = ConversationEventBroker()
            service = ConversationService(
                SqlAlchemyConversationUnitOfWorkFactory(database),
                employees=_Employees(employee),
                knowledge=_NoKnowledge(),
                runtime=runtime,
                events=events,
            )
            try:
                async with database.session() as session:
                    await SqlAlchemyEmployeeRepository(session).add(employee)
                    await session.commit()

                created = await service.create(
                    employee_id=employee.id,
                    title="真实会话",
                    conversation_id=conversation_id,
                )
                accepted = await service.send(
                    conversation_id,
                    user_message_id=uuid4(),
                    content="请给出简短回答",
                )
                delivered = await _events_until_terminal(events, conversation_id)
                stored = await service.list_messages(conversation_id)

                assert created.id == conversation_id
                assert accepted.user_message.status is MessageStatus.COMPLETED
                assert accepted.assistant_message.status is MessageStatus.PENDING
                assert [event.sequence for event in delivered] == [1, 2, 3, 4]
                assert [event.message.status for event in delivered] == [
                    MessageStatus.PENDING,
                    MessageStatus.STREAMING,
                    MessageStatus.STREAMING,
                    MessageStatus.COMPLETED,
                ]
                assert stored == (
                    accepted.user_message,
                    delivered[-1].message,
                )
                assert stored[-1].content == "第一段第二段"
                assert runtime.requests[0].history[-1].content == "请给出简短回答"
                assert runtime.requests[0].system_instruction == "直接回答问题"
            finally:
                await service.aclose()
                await delete_conversations(database, conversation_id)
                await delete_employees(database, employee.id)

        assert runtime.closed is True

    asyncio.run(exercise())


def test_durable_service_commits_reply_task_and_only_worker_executes_runtime() -> None:
    employee = Employee.create(
        name=f"durable-{uuid4().hex}",
        system_prompt="直接回答问题",
        **default_employee_model_fields(),
    )
    conversation_id = uuid4()

    async def exercise() -> None:
        async with _database() as database:
            await _delete_durable_tasks(database)
            runtime = _ScriptedRuntime()
            events = ConversationEventBroker()
            queue = SqlAlchemyTaskQueue(database)
            service = ConversationService(
                SqlAlchemyConversationUnitOfWorkFactory(database),
                employees=_Employees(employee),
                knowledge=_NoKnowledge(),
                runtime=runtime,
                events=events,
                tasks=queue,
                tenant_id_provider=lambda: DEFAULT_TENANT_ID,
                task_max_attempts=3,
            )
            worker = TaskWorker(
                queue,
                handlers={TaskKind.CONVERSATION_REPLY: service.execute_reply_task},
                worker_id="conversation-worker",
            )
            try:
                async with database.session() as session:
                    await SqlAlchemyEmployeeRepository(session).add(employee)
                    await session.commit()
                await service.create(
                    employee_id=employee.id,
                    title="持久任务会话",
                    conversation_id=conversation_id,
                )

                accepted = await service.send(
                    conversation_id,
                    user_message_id=uuid4(),
                    content="由独立 Worker 回答",
                )

                assert runtime.requests == []
                assert accepted.assistant_message.status is MessageStatus.PENDING
                with pytest.raises(ConversationBusy):
                    await service.delete(conversation_id)
                assert (await queue.backlog()).pending == 1
                assert await worker.run_once() is True

                delivered = await _events_until_terminal(events, conversation_id)
                stored = await service.list_messages(conversation_id)
                assert [event.kind.value for event in delivered] == [
                    "assistant.started",
                    "assistant.delta",
                    "assistant.delta",
                    "assistant.completed",
                ]
                assert stored[-1].status is MessageStatus.COMPLETED
                assert stored[-1].content == "第一段第二段"
                assert runtime.requests[0].conversation_id == conversation_id
                assert (await queue.backlog()).pending == 0
                assert (await queue.backlog()).running == 0
            finally:
                await service.aclose()
                await delete_conversations(database, conversation_id)
                await delete_employees(database, employee.id)
                await _delete_durable_tasks(database)

    asyncio.run(exercise())


def test_durable_worker_persists_business_failure_when_setup_exhausts_attempts() -> None:
    employee = Employee.create(
        name=f"setup-failure-{uuid4().hex}",
        system_prompt="直接回答问题",
        **default_employee_model_fields(),
    )
    conversation_id = uuid4()

    async def exercise() -> None:
        async with _database() as database:
            await _delete_durable_tasks(database)
            queue = SqlAlchemyTaskQueue(database)
            service = ConversationService(
                SqlAlchemyConversationUnitOfWorkFactory(database),
                employees=_UnavailableAfterValidationEmployees(employee),
                knowledge=_NoKnowledge(),
                runtime=_ScriptedRuntime(),
                events=ConversationEventBroker(),
                tasks=queue,
                tenant_id_provider=lambda: DEFAULT_TENANT_ID,
                task_max_attempts=1,
            )
            worker = TaskWorker(
                queue,
                handlers={TaskKind.CONVERSATION_REPLY: service.execute_reply_task},
                worker_id="setup-failure-worker",
            )
            try:
                async with database.session() as session:
                    await SqlAlchemyEmployeeRepository(session).add(employee)
                    await session.commit()
                await service.create(
                    employee_id=employee.id,
                    title="执行准备失败",
                    conversation_id=conversation_id,
                )
                await service.send(
                    conversation_id,
                    user_message_id=uuid4(),
                    content="员工读取失败也必须收敛业务终态",
                )

                assert await worker.run_once() is True

                stored = await service.list_messages(conversation_id)
                assert stored[-1].status is MessageStatus.FAILED
                assert stored[-1].error_code == "employee_not_found"
            finally:
                await service.aclose()
                await delete_conversations(database, conversation_id)
                await delete_employees(database, employee.id)
                await _delete_durable_tasks(database)

    asyncio.run(exercise())


def test_durable_worker_retries_interrupted_reply_without_duplicate_content() -> None:
    employee = Employee.create(
        name=f"retry-{uuid4().hex}",
        system_prompt="直接回答问题",
        **default_employee_model_fields(),
    )
    conversation_id = uuid4()

    async def exercise() -> None:
        async with _database() as database:
            await _delete_durable_tasks(database)
            runtime = _RetryingRuntime()
            events = ConversationEventBroker()
            queue = SqlAlchemyTaskQueue(database)
            service = ConversationService(
                SqlAlchemyConversationUnitOfWorkFactory(database),
                employees=_Employees(employee),
                knowledge=_NoKnowledge(),
                runtime=runtime,
                events=events,
                tasks=queue,
                tenant_id_provider=lambda: DEFAULT_TENANT_ID,
                task_max_attempts=3,
            )
            clock = [datetime.now(UTC)]
            worker = TaskWorker(
                queue,
                handlers={TaskKind.CONVERSATION_REPLY: service.execute_reply_task},
                worker_id="retry-worker",
                base_retry_delay=timedelta(seconds=1),
                clock=lambda: clock[0],
            )
            try:
                async with database.session() as session:
                    await SqlAlchemyEmployeeRepository(session).add(employee)
                    await session.commit()
                await service.create(
                    employee_id=employee.id,
                    title="自动重试",
                    conversation_id=conversation_id,
                )
                await service.send(
                    conversation_id,
                    user_message_id=uuid4(),
                    content="请自动重试",
                )

                clock[0] = datetime.now(UTC) + timedelta(seconds=1)
                assert await worker.run_once() is True
                clock[0] += timedelta(seconds=2)
                assert await worker.run_once() is True

                delivered = await _events_until_terminal(events, conversation_id)
                stored = await service.list_messages(conversation_id)
                async with database.session() as session:
                    task_state = await session.scalar(
                        select(DurableTaskRow.state).where(
                            DurableTaskRow.aggregate_id == str(conversation_id)
                        )
                    )
                assert runtime.attempts == 2
                assert stored[-1].status is MessageStatus.COMPLETED
                assert stored[-1].content == "重试后的完整内容"
                assert "不应保留" not in stored[-1].content
                assert delivered[-1].message == stored[-1]
                assert task_state == "succeeded"
            finally:
                await service.aclose()
                await delete_conversations(database, conversation_id)
                await delete_employees(database, employee.id)
                await _delete_durable_tasks(database)

    asyncio.run(exercise())


def test_durable_stop_crosses_api_and_worker_through_persisted_heartbeat() -> None:
    employee = Employee.create(
        name=f"stop-{uuid4().hex}",
        system_prompt="直接回答问题",
        **default_employee_model_fields(),
    )
    conversation_id = uuid4()

    async def exercise() -> None:
        async with _database() as database:
            await _delete_durable_tasks(database)
            runtime = _ScriptedRuntime(block_first_until_stopped=True)
            events = ConversationEventBroker()
            queue = SqlAlchemyTaskQueue(database)
            service = ConversationService(
                SqlAlchemyConversationUnitOfWorkFactory(database),
                employees=_Employees(employee),
                knowledge=_NoKnowledge(),
                runtime=runtime,
                events=events,
                tasks=queue,
                tenant_id_provider=lambda: DEFAULT_TENANT_ID,
                task_max_attempts=3,
            )
            worker = TaskWorker(
                queue,
                handlers={TaskKind.CONVERSATION_REPLY: service.execute_reply_task},
                worker_id="stop-worker",
                lease_for=timedelta(seconds=3),
                heartbeat_interval=timedelta(seconds=1),
            )
            try:
                async with database.session() as session:
                    await SqlAlchemyEmployeeRepository(session).add(employee)
                    await session.commit()
                await service.create(
                    employee_id=employee.id,
                    title="跨进程停止",
                    conversation_id=conversation_id,
                )
                accepted = await service.send(
                    conversation_id,
                    user_message_id=uuid4(),
                    content="开始后停止",
                )
                execution = asyncio.create_task(worker.run_once())
                while True:
                    stored = await service.list_messages(conversation_id)
                    if stored[-1].status is MessageStatus.STREAMING:
                        break
                    await asyncio.sleep(0.01)

                stopped = await service.stop(conversation_id)
                assert stopped.assistant_message_id == accepted.assistant_message.id
                assert await asyncio.wait_for(execution, timeout=3) is True

                delivered = await _events_until_terminal(events, conversation_id)
                stored = await service.list_messages(conversation_id)
                async with database.session() as session:
                    task_state = await session.scalar(
                        select(DurableTaskRow.state).where(
                            DurableTaskRow.aggregate_id == str(conversation_id)
                        )
                    )
                assert stored[-1].status is MessageStatus.STOPPED
                assert delivered[-1].message == stored[-1]
                assert task_state == "cancelled"
            finally:
                await service.aclose()
                await delete_conversations(database, conversation_id)
                await delete_employees(database, employee.id)
                await _delete_durable_tasks(database)

    asyncio.run(exercise())


def test_durable_retry_repairs_terminal_event_after_state_commit_succeeds() -> None:
    employee = Employee.create(
        name=f"event-{uuid4().hex}",
        system_prompt="直接回答问题",
        **default_employee_model_fields(),
    )
    conversation_id = uuid4()

    async def exercise() -> None:
        async with _database() as database:
            await _delete_durable_tasks(database)
            runtime = _ScriptedRuntime()
            events = _FailTerminalEventOnce()
            queue = SqlAlchemyTaskQueue(database)
            service = ConversationService(
                SqlAlchemyConversationUnitOfWorkFactory(database),
                employees=_Employees(employee),
                knowledge=_NoKnowledge(),
                runtime=runtime,
                events=events,
                tasks=queue,
                tenant_id_provider=lambda: DEFAULT_TENANT_ID,
                task_max_attempts=3,
            )
            clock = [datetime.now(UTC) + timedelta(seconds=1)]
            worker = TaskWorker(
                queue,
                handlers={TaskKind.CONVERSATION_REPLY: service.execute_reply_task},
                worker_id="event-repair-worker",
                base_retry_delay=timedelta(seconds=1),
                clock=lambda: clock[0],
            )
            try:
                async with database.session() as session:
                    await SqlAlchemyEmployeeRepository(session).add(employee)
                    await session.commit()
                await service.create(
                    employee_id=employee.id,
                    title="终态事件修复",
                    conversation_id=conversation_id,
                )
                await service.send(
                    conversation_id,
                    user_message_id=uuid4(),
                    content="验证终态事件",
                )

                assert await worker.run_once() is True
                clock[0] += timedelta(seconds=2)
                assert await worker.run_once() is True

                delivered = await _events_until_terminal(events, conversation_id)
                stored = await service.list_messages(conversation_id)
                assert stored[-1].status is MessageStatus.COMPLETED
                assert delivered[-1].kind is ConversationEventKind.ASSISTANT_COMPLETED
                assert delivered[-1].message == stored[-1]
            finally:
                await service.aclose()
                await delete_conversations(database, conversation_id)
                await delete_employees(database, employee.id)
                await _delete_durable_tasks(database)

    asyncio.run(exercise())


def test_service_stops_active_turn_retries_same_message_and_rejects_duplicates() -> None:
    employee = Employee.create(
        name=f"service-stop-{uuid4().hex}",
        system_prompt="直接回答问题",
        **default_employee_model_fields(),
    )
    conversation_id = uuid4()
    user_message_id = uuid4()

    async def exercise() -> None:
        async with _database() as database:
            runtime = _ScriptedRuntime(block_first_until_stopped=True)
            events = ConversationEventBroker()
            service = ConversationService(
                SqlAlchemyConversationUnitOfWorkFactory(database),
                employees=_Employees(employee),
                knowledge=_NoKnowledge(),
                runtime=runtime,
                events=events,
            )
            try:
                async with database.session() as session:
                    await SqlAlchemyEmployeeRepository(session).add(employee)
                    await session.commit()
                await service.create(
                    employee_id=employee.id,
                    title="停止与重试",
                    conversation_id=conversation_id,
                )
                accepted = await service.send(
                    conversation_id,
                    user_message_id=user_message_id,
                    content="第一次问题",
                )

                while True:
                    active = await service.list_messages(conversation_id)
                    if active[-1].status is MessageStatus.STREAMING:
                        break
                    await asyncio.sleep(0)

                with pytest.raises(ConversationBusy):
                    await service.send(
                        conversation_id,
                        user_message_id=uuid4(),
                        content="并发问题",
                    )

                stopped_turn = await service.stop(conversation_id)
                first_events = await _events_until_terminal(events, conversation_id)
                assert stopped_turn.assistant_message_id == accepted.assistant_message.id
                assert first_events[-1].message.status is MessageStatus.STOPPED

                retried = await service.retry(accepted.assistant_message.id)
                retry_events = await _events_until_terminal(
                    events,
                    conversation_id,
                    after_sequence=first_events[-1].sequence,
                )
                assert retried.assistant_message.id == accepted.assistant_message.id
                assert retry_events[0].retry is True
                assert retry_events[-1].message.status is MessageStatus.COMPLETED
                assert retry_events[-1].message.content == "第一段第二段"
                assert len(await service.list_messages(conversation_id)) == 2

                with pytest.raises(MessageRequestConflict):
                    await service.send(
                        conversation_id,
                        user_message_id=user_message_id,
                        content="重复提交",
                    )
            finally:
                await service.aclose()
                await delete_conversations(database, conversation_id)
                await delete_employees(database, employee.id)

    asyncio.run(exercise())


def test_stop_accepted_before_a_late_completion_wins_with_one_persisted_terminal() -> None:
    employee = Employee.create(
        name=f"service-race-{uuid4().hex}",
        system_prompt="直接回答问题",
        **default_employee_model_fields(),
    )
    conversation_id = uuid4()

    async def exercise() -> None:
        async with _database() as database:
            runtime = _CompletionAfterStopRuntime()
            events = ConversationEventBroker()
            service = ConversationService(
                SqlAlchemyConversationUnitOfWorkFactory(database),
                employees=_Employees(employee),
                knowledge=_NoKnowledge(),
                runtime=runtime,
                events=events,
            )
            try:
                async with database.session() as session:
                    await SqlAlchemyEmployeeRepository(session).add(employee)
                    await session.commit()
                await service.create(
                    employee_id=employee.id,
                    title="停止完成竞态",
                    conversation_id=conversation_id,
                )
                accepted = await service.send(
                    conversation_id,
                    user_message_id=uuid4(),
                    content="在完成前停止",
                )
                await asyncio.wait_for(runtime.started.wait(), timeout=1)
                stopped = await service.stop(conversation_id)
                runtime.release_completion.set()

                delivered = await _events_until_terminal(events, conversation_id)
                stored = await service.list_messages(conversation_id)

                assert stopped.assistant_message_id == accepted.assistant_message.id
                assert stored[-1].status is MessageStatus.STOPPED
                assert delivered[-1].message == stored[-1]
                assert sum(event.message.is_terminal for event in delivered) == 1
            finally:
                runtime.release_completion.set()
                await service.aclose()
                await delete_conversations(database, conversation_id)
                await delete_employees(database, employee.id)

    asyncio.run(exercise())


def test_service_recovers_interrupted_messages_as_persisted_failures() -> None:
    employee = Employee.create(
        name=f"service-recover-{uuid4().hex}",
        system_prompt="直接回答问题",
        **default_employee_model_fields(),
    )
    conversation = Conversation.create(employee_id=employee.id, title="中断恢复")
    user = Message.create_user(
        conversation_id=conversation.id,
        sequence_number=1,
        content="重启前的问题",
    )
    pending = Message.create_assistant(
        conversation_id=conversation.id,
        sequence_number=2,
    )

    async def exercise() -> None:
        async with _database() as database:
            runtime = _ScriptedRuntime()
            events = ConversationEventBroker()
            service = ConversationService(
                SqlAlchemyConversationUnitOfWorkFactory(database),
                employees=_Employees(employee),
                knowledge=_NoKnowledge(),
                runtime=runtime,
                events=events,
            )
            try:
                async with database.session() as session:
                    await SqlAlchemyEmployeeRepository(session).add(employee)
                    await SqlAlchemyConversationRepository(session).add(conversation)
                    await SqlAlchemyMessageRepository(session).add(user)
                    await SqlAlchemyMessageRepository(session).add(pending)
                    await session.commit()

                recovered_count = await service.recover_interrupted()
                delivered = await _events_until_terminal(events, conversation.id)
                stored = await service.list_messages(conversation.id)

                assert recovered_count == 1
                assert stored[-1].status is MessageStatus.FAILED
                assert stored[-1].error_code == "generation_interrupted"
                assert delivered[-1].message == stored[-1]
            finally:
                await service.aclose()
                await delete_conversations(database, conversation.id)
                await delete_employees(database, employee.id)

    asyncio.run(exercise())


@pytest.mark.parametrize(
    ("runtime", "expected_status", "expected_error"),
    [
        (_InterruptedRuntime(), MessageStatus.FAILED, "runtime_stream_interrupted"),
        (_InvalidSequenceRuntime(), MessageStatus.FAILED, "runtime_response_invalid"),
        (_LateEventRuntime(), MessageStatus.COMPLETED, None),
    ],
)
def test_service_closes_interrupted_or_invalid_streams_and_ignores_late_events(
    runtime: _InterruptedRuntime | _InvalidSequenceRuntime | _LateEventRuntime,
    expected_status: MessageStatus,
    expected_error: str | None,
) -> None:
    employee = Employee.create(
        name=f"service-failure-{uuid4().hex}",
        system_prompt="直接回答问题",
        **default_employee_model_fields(),
    )
    conversation_id = uuid4()

    async def exercise() -> None:
        async with _database() as database:
            events = ConversationEventBroker()
            service = ConversationService(
                SqlAlchemyConversationUnitOfWorkFactory(database),
                employees=_Employees(employee),
                knowledge=_NoKnowledge(),
                runtime=runtime,
                events=events,
            )
            try:
                async with database.session() as session:
                    await SqlAlchemyEmployeeRepository(session).add(employee)
                    await session.commit()
                await service.create(
                    employee_id=employee.id,
                    title="失败边界",
                    conversation_id=conversation_id,
                )
                await service.send(
                    conversation_id,
                    user_message_id=uuid4(),
                    content="触发失败边界",
                )
                delivered = await _events_until_terminal(events, conversation_id)
                stored = await service.list_messages(conversation_id)

                assert delivered[-1].message == stored[-1]
                assert stored[-1].status is expected_status
                assert stored[-1].error_code == expected_error
                if isinstance(runtime, _InvalidSequenceRuntime):
                    assert "不应落库" not in stored[-1].content
                if isinstance(runtime, _LateEventRuntime):
                    assert runtime.resumed_after_terminal is False
                    assert stored[-1].content == "完整内容"
            finally:
                await service.aclose()
                await delete_conversations(database, conversation_id)
                await delete_employees(database, employee.id)

    asyncio.run(exercise())
