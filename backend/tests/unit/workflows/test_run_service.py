from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import timedelta
from io import StringIO
from typing import cast
from uuid import UUID, uuid4

import pytest

from common_agent.adapters.workflow.langgraph import LangGraphWorkflowCompiler
from common_agent.application.workflow_service import (
    WorkflowExecutionUnavailable,
    WorkflowNotFound,
    WorkflowRunConflict,
    WorkflowRunNotActive,
    WorkflowRunNotFound,
    WorkflowService,
)
from common_agent.domain.workflow import WorkflowDefinition
from common_agent.domain.workflow_run import (
    WorkflowRun,
    WorkflowRunOrigin,
    WorkflowRunStatus,
    WorkflowRunTrigger,
)
from common_agent.knowledge.service import KnowledgeBaseService
from common_agent.models.base import (
    ModelRequest,
    ModelServiceError,
    ModelServiceUnavailable,
    ModelStreamCompleted,
    ModelStreamDelta,
    ModelStreamEvent,
)
from common_agent.observability import JsonLogFormatter
from common_agent.tasks import (
    DurableTask,
    TaskCancelled,
    TaskExecutionContext,
    TaskFatalError,
    TaskKind,
    TaskQueue,
    TaskRetryableError,
    TaskState,
)
from common_agent.tenancy.constants import DEFAULT_TENANT_ID
from common_agent.workflows.events import (
    WorkflowEventBroker,
    WorkflowEventKind,
    WorkflowRunEvent,
)
from common_agent.workflows.execution import (
    CompiledWorkflow,
    WorkflowCompiler,
    WorkflowExecutionObserver,
    WorkflowExecutionResult,
    WorkflowExecutionStopSignal,
)
from common_agent.workflows.nodes.registry import create_workflow_node_registry
from tests.support.knowledge import KnowledgeProbe
from tests.unit.workflows.support import WorkflowUnitOfWorkFactoryProbe, workflow_configuration


class RunModelProbe:
    provider_name = "probe"

    def __init__(self, *, block: bool = False, fail: bool = False) -> None:
        self.block = block
        self.fail = fail
        self.started = asyncio.Event()

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamEvent]:
        del request
        self.started.set()
        if self.fail:
            raise ModelServiceUnavailable
        if self.block:
            await asyncio.Event().wait()
        yield ModelStreamDelta(text="工作流结果")
        yield ModelStreamCompleted()

    def translate_error(
        self,
        error: Exception,
        *,
        stream_started: bool,
    ) -> ModelServiceError | None:
        del error, stream_started
        return None

    async def aclose(self) -> None:
        pass


class FailCompletedEventOnce(WorkflowEventBroker):
    def __init__(self) -> None:
        super().__init__()
        self.failed = False

    async def publish(
        self,
        *,
        run: WorkflowRun,
        kind: WorkflowEventKind,
        node_id: str | None = None,
    ) -> WorkflowRunEvent:
        if kind is WorkflowEventKind.RUN_COMPLETED and not self.failed:
            self.failed = True
            raise RuntimeError("event journal temporarily unavailable")
        return await super().publish(run=run, kind=kind, node_id=node_id)


class DurableStopQueueProbe:
    def __init__(self) -> None:
        self.task: DurableTask | None = None
        self.stop_requests = 0

    async def request_stop_for_aggregate(self, **kwargs: object) -> DurableTask:
        del kwargs
        self.stop_requests += 1
        if self.task is None:
            raise AssertionError("durable task was not prepared")
        return replace(self.task, stop_requested=True)


def _service(
    *,
    model: RunModelProbe | None = None,
    units: WorkflowUnitOfWorkFactoryProbe | None = None,
    compiler: WorkflowCompiler | None = None,
) -> tuple[WorkflowService, WorkflowUnitOfWorkFactoryProbe, WorkflowEventBroker, RunModelProbe]:
    active_units = units or WorkflowUnitOfWorkFactoryProbe()
    knowledge = KnowledgeProbe()
    active_model = model or RunModelProbe()
    events = WorkflowEventBroker()
    active_compiler = compiler or LangGraphWorkflowCompiler(
        create_workflow_node_registry(active_model, KnowledgeBaseService(knowledge))
    )
    return (
        WorkflowService(
            active_units,
            KnowledgeBaseService(knowledge),
            compiler=active_compiler,
            events=events,
        ),
        active_units,
        events,
        active_model,
    )


async def _terminal(service: WorkflowService, run_id: UUID) -> WorkflowRun:
    for _ in range(100):
        run = await service.get_run(run_id)
        if run.is_terminal:
            return run
        await asyncio.sleep(0.01)
    pytest.fail("工作流运行未进入终态")


def test_manual_run_persists_each_node_then_completed_summary_and_events() -> None:
    output = StringIO()
    handler = logging.StreamHandler(output)
    handler.setFormatter(JsonLogFormatter())
    logger = logging.getLogger("common_agent.workflows")
    previous_level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    async def exercise() -> None:
        service, units, broker, _ = _service()
        workflow = await service.create(workflow_configuration())
        run_id = uuid4()

        accepted = await service.start_run(
            workflow.id,
            run_id=run_id,
            input="执行这个工作流",
            trigger=WorkflowRunTrigger.MANUAL,
        )
        completed = await service.wait_for_run(run_id)
        stream = broker.stream(run_id)
        events = [await anext(stream) for _ in range(8)]
        await stream.aclose()
        await service.aclose()

        assert accepted.status is WorkflowRunStatus.RUNNING
        assert completed.status is WorkflowRunStatus.COMPLETED
        assert completed.output == "工作流结果"
        assert completed.completed_node_ids == ("start", "chat", "end")
        assert [event.kind for event in events] == [
            WorkflowEventKind.RUN_STARTED,
            WorkflowEventKind.NODE_STARTED,
            WorkflowEventKind.NODE_COMPLETED,
            WorkflowEventKind.NODE_STARTED,
            WorkflowEventKind.NODE_COMPLETED,
            WorkflowEventKind.NODE_STARTED,
            WorkflowEventKind.NODE_COMPLETED,
            WorkflowEventKind.RUN_COMPLETED,
        ]
        assert units.commit_count >= 6

    try:
        asyncio.run(exercise())
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)

    records = [json.loads(line) for line in output.getvalue().splitlines()]
    started = next(record for record in records if record["event"] == "workflow.run.started")
    finished = next(record for record in records if record["event"] == "workflow.run.finished")
    assert started["workflow_id"] == finished["workflow_id"]
    assert started["run_id"] == finished["run_id"]
    assert started["status"] == "running"
    assert finished["status"] == "completed"
    assert finished["error_code"] is None
    assert finished["duration_ms"] >= 0


def test_durable_run_is_committed_pending_and_only_worker_executes_compiler() -> None:
    async def exercise() -> None:
        units = WorkflowUnitOfWorkFactoryProbe()
        knowledge = KnowledgeProbe()
        model = RunModelProbe()
        events = WorkflowEventBroker()
        service = WorkflowService(
            units,
            KnowledgeBaseService(knowledge),
            compiler=LangGraphWorkflowCompiler(
                create_workflow_node_registry(model, KnowledgeBaseService(knowledge))
            ),
            events=events,
            tasks=cast(TaskQueue, object()),
            tenant_id_provider=lambda: DEFAULT_TENANT_ID,
            task_max_attempts=3,
        )
        workflow = await service.create(workflow_configuration())
        run_id = uuid4()

        accepted = await service.start_run(
            workflow.id,
            run_id=run_id,
            input="由独立 Worker 执行",
            trigger=WorkflowRunTrigger.MANUAL,
        )

        assert accepted.status is WorkflowRunStatus.PENDING
        assert model.started.is_set() is False
        assert len(units.tasks.requests) == 1
        request, maximum_attempts = units.tasks.requests[0]
        assert request.kind is TaskKind.WORKFLOW_RUN
        assert maximum_attempts == 3
        pending_task = (await units.tasks.enqueue(request, max_attempts=3)).task
        claimed_task = replace(
            pending_task,
            state=TaskState.RUNNING,
            attempts=1,
            lease_owner="workflow-worker",
            lease_token=uuid4(),
            lease_until=pending_task.available_at + timedelta(seconds=30),
        )

        await service.execute_workflow_task(claimed_task, TaskExecutionContext())
        completed = await service.get_run(run_id)
        stream = events.stream(run_id)
        delivered = [await anext(stream) for _ in range(8)]
        await stream.aclose()
        await service.aclose()

        assert completed.status is WorkflowRunStatus.COMPLETED
        assert completed.output == "工作流结果"
        assert delivered[0].kind is WorkflowEventKind.RUN_STARTED
        assert delivered[-1].kind is WorkflowEventKind.RUN_COMPLETED

    asyncio.run(exercise())


def test_durable_workflow_retries_before_persisting_final_failure() -> None:
    async def exercise() -> None:
        units = WorkflowUnitOfWorkFactoryProbe()
        knowledge = KnowledgeProbe()
        model = RunModelProbe(fail=True)
        service = WorkflowService(
            units,
            KnowledgeBaseService(knowledge),
            compiler=LangGraphWorkflowCompiler(
                create_workflow_node_registry(model, KnowledgeBaseService(knowledge))
            ),
            events=WorkflowEventBroker(),
            tasks=cast(TaskQueue, object()),
            tenant_id_provider=lambda: DEFAULT_TENANT_ID,
            task_max_attempts=3,
        )
        workflow = await service.create(workflow_configuration())
        run_id = uuid4()
        await service.start_run(
            workflow.id,
            run_id=run_id,
            input="失败后自动重试",
            trigger=WorkflowRunTrigger.MANUAL,
        )
        request, _ = units.tasks.requests[0]
        pending_task = (await units.tasks.enqueue(request, max_attempts=3)).task
        first_attempt = replace(
            pending_task,
            state=TaskState.RUNNING,
            attempts=1,
            lease_owner="workflow-worker",
            lease_token=uuid4(),
            lease_until=pending_task.available_at + timedelta(seconds=30),
        )

        with pytest.raises(TaskRetryableError) as retryable:
            await service.execute_workflow_task(first_attempt, TaskExecutionContext())
        assert retryable.value.code == "model_unavailable"
        assert (await service.get_run(run_id)).status is WorkflowRunStatus.RUNNING

        final_attempt = replace(first_attempt, attempts=3, lease_token=uuid4())
        with pytest.raises(TaskFatalError) as fatal:
            await service.execute_workflow_task(final_attempt, TaskExecutionContext())
        failed = await service.get_run(run_id)
        await service.aclose()

        assert fatal.value.code == "model_unavailable"
        assert failed.status is WorkflowRunStatus.FAILED
        assert failed.error_code == "model_unavailable"

    asyncio.run(exercise())


def test_durable_stop_acceptance_immediately_persists_stopped_summary() -> None:
    async def exercise() -> None:
        units = WorkflowUnitOfWorkFactoryProbe()
        knowledge = KnowledgeProbe()
        queue = DurableStopQueueProbe()
        service = WorkflowService(
            units,
            KnowledgeBaseService(knowledge),
            compiler=LangGraphWorkflowCompiler(
                create_workflow_node_registry(
                    RunModelProbe(),
                    KnowledgeBaseService(knowledge),
                )
            ),
            events=WorkflowEventBroker(),
            tasks=cast(TaskQueue, queue),
            tenant_id_provider=lambda: DEFAULT_TENANT_ID,
        )
        workflow = await service.create(workflow_configuration())
        run_id = uuid4()
        await service.start_run(
            workflow.id,
            run_id=run_id,
            input="接受停止后立即收敛摘要",
            trigger=WorkflowRunTrigger.MANUAL,
        )
        request, _ = units.tasks.requests[-1]
        queue.task = (await units.tasks.enqueue(request, max_attempts=3)).task

        accepted = await service.stop_run(run_id)
        stopped = await service.get_run(run_id)
        await service.aclose()

        assert accepted.run_id == run_id
        assert queue.stop_requests == 1
        assert stopped.status is WorkflowRunStatus.STOPPED

    asyncio.run(exercise())


def test_durable_workflow_persists_failure_when_definition_lookup_exhausts_attempts() -> None:
    async def exercise() -> None:
        units = WorkflowUnitOfWorkFactoryProbe()
        service = WorkflowService(
            units,
            KnowledgeBaseService(KnowledgeProbe()),
            compiler=LangGraphWorkflowCompiler(
                create_workflow_node_registry(
                    RunModelProbe(),
                    KnowledgeBaseService(KnowledgeProbe()),
                )
            ),
            events=WorkflowEventBroker(),
            tasks=cast(TaskQueue, object()),
            tenant_id_provider=lambda: DEFAULT_TENANT_ID,
            task_max_attempts=1,
        )
        workflow = await service.create(workflow_configuration())
        run_id = uuid4()
        await service.start_run(
            workflow.id,
            run_id=run_id,
            input="定义读取失败也必须收敛业务终态",
            trigger=WorkflowRunTrigger.MANUAL,
        )
        request, _ = units.tasks.requests[0]
        pending_task = (await units.tasks.enqueue(request, max_attempts=1)).task
        claimed_task = replace(
            pending_task,
            state=TaskState.RUNNING,
            attempts=1,
            lease_owner="workflow-worker",
            lease_token=uuid4(),
            lease_until=pending_task.available_at + timedelta(seconds=30),
        )
        units.repository.values.pop(workflow.id)

        with pytest.raises(TaskFatalError) as fatal:
            await service.execute_workflow_task(claimed_task, TaskExecutionContext())
        failed = await service.get_run(run_id)
        await service.aclose()

        assert fatal.value.code == "workflow_not_found"
        assert failed.status is WorkflowRunStatus.FAILED
        assert failed.error_code == "workflow_not_found"

    asyncio.run(exercise())


def test_durable_workflow_retry_repairs_terminal_event_without_reexecution() -> None:
    async def exercise() -> None:
        units = WorkflowUnitOfWorkFactoryProbe()
        knowledge = KnowledgeProbe()
        model = RunModelProbe()
        events = FailCompletedEventOnce()
        service = WorkflowService(
            units,
            KnowledgeBaseService(knowledge),
            compiler=LangGraphWorkflowCompiler(
                create_workflow_node_registry(model, KnowledgeBaseService(knowledge))
            ),
            events=events,
            tasks=cast(TaskQueue, object()),
            tenant_id_provider=lambda: DEFAULT_TENANT_ID,
            task_max_attempts=3,
        )
        workflow = await service.create(workflow_configuration())
        run_id = uuid4()
        await service.start_run(
            workflow.id,
            run_id=run_id,
            input="补写终态事件",
            trigger=WorkflowRunTrigger.MANUAL,
        )
        request, _ = units.tasks.requests[0]
        pending_task = (await units.tasks.enqueue(request, max_attempts=3)).task
        first_attempt = replace(
            pending_task,
            state=TaskState.RUNNING,
            attempts=1,
            lease_owner="workflow-worker",
            lease_token=uuid4(),
            lease_until=pending_task.available_at + timedelta(seconds=30),
        )
        with pytest.raises(TaskRetryableError):
            await service.execute_workflow_task(first_attempt, TaskExecutionContext())
        completed_before_repair = await service.get_run(run_id)

        await service.execute_workflow_task(
            replace(first_attempt, attempts=2, lease_token=uuid4()),
            TaskExecutionContext(),
        )
        stream = events.stream(run_id)
        delivered = [await anext(stream) for _ in range(8)]
        await stream.aclose()
        await service.aclose()

        assert completed_before_repair.status is WorkflowRunStatus.COMPLETED
        assert delivered[-1].kind is WorkflowEventKind.RUN_COMPLETED
        assert delivered[-1].run == completed_before_repair

    asyncio.run(exercise())


def test_durable_terminal_retries_republish_stopped_and_failed_events() -> None:
    async def exercise() -> None:
        units = WorkflowUnitOfWorkFactoryProbe()
        knowledge = KnowledgeProbe()
        events = WorkflowEventBroker()
        service = WorkflowService(
            units,
            KnowledgeBaseService(knowledge),
            compiler=LangGraphWorkflowCompiler(
                create_workflow_node_registry(RunModelProbe(), KnowledgeBaseService(knowledge))
            ),
            events=events,
            tasks=cast(TaskQueue, object()),
            tenant_id_provider=lambda: DEFAULT_TENANT_ID,
        )
        workflow = await service.create(workflow_configuration())

        stopped_id = uuid4()
        stopped_pending = await service.start_run(
            workflow.id,
            run_id=stopped_id,
            input="补写停止事件",
            trigger=WorkflowRunTrigger.MANUAL,
        )
        stopped_request, _ = units.tasks.requests[-1]
        stopped_task = (await units.tasks.enqueue(stopped_request, max_attempts=3)).task
        stopped_claim = replace(
            stopped_task,
            state=TaskState.RUNNING,
            attempts=2,
            lease_owner="workflow-worker",
            lease_token=uuid4(),
            lease_until=stopped_task.available_at + timedelta(seconds=30),
        )
        units.run_repository.values[stopped_id] = stopped_pending.stop()

        with pytest.raises(TaskCancelled):
            await service.execute_workflow_task(stopped_claim, TaskExecutionContext())
        stopped_stream = events.stream(stopped_id)
        stopped_event = await anext(stopped_stream)
        await stopped_stream.aclose()

        failed_id = uuid4()
        failed_pending = await service.start_run(
            workflow.id,
            run_id=failed_id,
            input="补写失败事件",
            trigger=WorkflowRunTrigger.MANUAL,
        )
        failed_request, _ = units.tasks.requests[-1]
        failed_task = (await units.tasks.enqueue(failed_request, max_attempts=3)).task
        failed_claim = replace(
            failed_task,
            state=TaskState.RUNNING,
            attempts=2,
            lease_owner="workflow-worker",
            lease_token=uuid4(),
            lease_until=failed_task.available_at + timedelta(seconds=30),
        )
        units.run_repository.values[failed_id] = (
            failed_pending.start().start_node("chat").fail("model_unavailable")
        )

        with pytest.raises(TaskFatalError, match="model_unavailable"):
            await service.execute_workflow_task(failed_claim, TaskExecutionContext())
        failed_stream = events.stream(failed_id)
        failed_events = [await anext(failed_stream) for _ in range(2)]
        await failed_stream.aclose()
        await service.aclose()

        assert stopped_event.kind is WorkflowEventKind.RUN_STOPPED
        assert [event.kind for event in failed_events] == [
            WorkflowEventKind.NODE_FAILED,
            WorkflowEventKind.RUN_FAILED,
        ]
        assert failed_events[0].node_id == "chat"

    asyncio.run(exercise())


def test_wait_for_run_rejects_unknown_run() -> None:
    async def exercise() -> None:
        service, _, _, _ = _service()

        with pytest.raises(WorkflowRunNotFound):
            await service.wait_for_run(uuid4())
        await service.aclose()

    asyncio.run(exercise())


def test_start_run_requires_platform_compiler_and_event_ports() -> None:
    async def exercise() -> None:
        service = WorkflowService(
            WorkflowUnitOfWorkFactoryProbe(),
            KnowledgeBaseService(KnowledgeProbe()),
            events=WorkflowEventBroker(),
        )

        with pytest.raises(WorkflowExecutionUnavailable):
            await service.start_run(
                uuid4(),
                run_id=uuid4(),
                input="缺少编译器",
                trigger=WorkflowRunTrigger.MANUAL,
            )

        await service.aclose()

    asyncio.run(exercise())


def test_durable_workflow_configuration_rejects_partial_or_unsafe_task_settings() -> None:
    units = WorkflowUnitOfWorkFactoryProbe()
    knowledge = KnowledgeBaseService(KnowledgeProbe())

    with pytest.raises(ValueError, match="configured together"):
        WorkflowService(units, knowledge, tasks=cast(TaskQueue, object()))
    with pytest.raises(ValueError, match="configured together"):
        WorkflowService(
            units,
            knowledge,
            tenant_id_provider=lambda: DEFAULT_TENANT_ID,
        )
    with pytest.raises(ValueError, match="between 1 and 100"):
        WorkflowService(units, knowledge, task_max_attempts=0)


def test_employee_run_persists_origin_and_lists_only_its_conversation() -> None:
    async def exercise() -> None:
        service, _, _, _ = _service()
        workflow = await service.create(workflow_configuration())
        assert await service.list() == (workflow,)
        origin = WorkflowRunOrigin(
            employee_id=uuid4(),
            conversation_id=uuid4(),
            assistant_message_id=uuid4(),
        )
        run_id = uuid4()

        await service.start_run(
            workflow.id,
            run_id=run_id,
            input="员工关联运行",
            trigger=WorkflowRunTrigger.EMPLOYEE,
            origin=origin,
        )
        completed = await service.wait_for_run(run_id)
        own_runs = await service.list_runs_for_conversation(origin.conversation_id)
        other_runs = await service.list_runs_for_conversation(uuid4())
        await service.aclose()

        assert completed.origin == origin
        assert own_runs == (completed,)
        assert other_runs == ()

    asyncio.run(exercise())


def test_duplicate_run_id_and_missing_workflow_fail_closed() -> None:
    async def exercise() -> None:
        service, _, _, _ = _service()
        workflow = await service.create(workflow_configuration())
        run_id = uuid4()
        await service.start_run(
            workflow.id,
            run_id=run_id,
            input="input",
            trigger=WorkflowRunTrigger.MANUAL,
        )
        with pytest.raises(WorkflowRunConflict):
            await service.start_run(
                workflow.id,
                run_id=run_id,
                input="duplicate",
                trigger=WorkflowRunTrigger.MANUAL,
            )
        with pytest.raises(WorkflowNotFound):
            await service.start_run(
                uuid4(),
                run_id=uuid4(),
                input="missing",
                trigger=WorkflowRunTrigger.MANUAL,
            )
        with pytest.raises(WorkflowRunNotFound):
            await service.get_run(uuid4())
        await service.aclose()

    asyncio.run(exercise())


def test_stop_interrupts_active_node_and_persists_stopped_summary() -> None:
    async def exercise() -> None:
        blocking_model = RunModelProbe(block=True)
        service, _, broker, _ = _service(model=blocking_model)
        workflow = await service.create(workflow_configuration())
        run_id = uuid4()
        await service.start_run(
            workflow.id,
            run_id=run_id,
            input="stop me",
            trigger=WorkflowRunTrigger.MANUAL,
        )
        await asyncio.wait_for(blocking_model.started.wait(), timeout=1)

        accepted = await service.stop_run(run_id)
        stopped = await _terminal(service, run_id)
        stream = broker.stream(run_id)
        events = [await anext(stream) for _ in range(5)]
        await stream.aclose()
        with pytest.raises(WorkflowRunNotActive):
            await service.stop_run(run_id)
        await service.aclose()

        assert accepted.run_id == run_id
        assert stopped.status is WorkflowRunStatus.STOPPED
        assert stopped.current_node_id == "chat"
        assert stopped.completed_node_ids == ("start",)
        assert events[-1].kind is WorkflowEventKind.RUN_STOPPED
        assert WorkflowEventKind.NODE_COMPLETED not in [
            event.kind for event in events if event.node_id == "chat"
        ]

    asyncio.run(exercise())


def test_node_failure_is_persisted_without_exposing_provider_error() -> None:
    async def exercise() -> None:
        service, _, broker, _ = _service(model=RunModelProbe(fail=True))
        workflow = await service.create(workflow_configuration())
        run_id = uuid4()
        await service.start_run(
            workflow.id,
            run_id=run_id,
            input="fail safely",
            trigger=WorkflowRunTrigger.MANUAL,
        )

        failed = await _terminal(service, run_id)
        stream = broker.stream(run_id)
        events = [await anext(stream) for _ in range(6)]
        await stream.aclose()
        await service.aclose()

        assert failed.status is WorkflowRunStatus.FAILED
        assert failed.output == ""
        assert failed.failed_node_id == "chat"
        assert failed.error_code == "model_unavailable"
        assert [event.kind for event in events] == [
            WorkflowEventKind.RUN_STARTED,
            WorkflowEventKind.NODE_STARTED,
            WorkflowEventKind.NODE_COMPLETED,
            WorkflowEventKind.NODE_STARTED,
            WorkflowEventKind.NODE_FAILED,
            WorkflowEventKind.RUN_FAILED,
        ]

    asyncio.run(exercise())


class _InvalidCompiledWorkflow:
    workflow_id = "invalid-result"

    async def invoke(
        self,
        user_input: str,
        *,
        observer: WorkflowExecutionObserver | None = None,
        stop: WorkflowExecutionStopSignal | None = None,
    ) -> WorkflowExecutionResult:
        del user_input, observer, stop
        return WorkflowExecutionResult(
            output="不可信结果",
            completed_node_ids=("not-persisted",),
            step_count=1,
        )


class _InvalidCompiler:
    def compile(self, workflow: WorkflowDefinition) -> CompiledWorkflow:
        del workflow
        return _InvalidCompiledWorkflow()


def test_compiler_result_mismatch_fails_closed() -> None:

    async def exercise() -> None:
        service, _, broker, _ = _service(compiler=_InvalidCompiler())
        workflow = await service.create(workflow_configuration())
        run_id = uuid4()
        await service.start_run(
            workflow.id,
            run_id=run_id,
            input="reject mismatched result",
            trigger=WorkflowRunTrigger.MANUAL,
        )

        failed = await _terminal(service, run_id)
        stream = broker.stream(run_id)
        events = [await anext(stream) for _ in range(2)]
        await stream.aclose()
        await service.aclose()

        assert failed.status is WorkflowRunStatus.FAILED
        assert failed.failed_node_id is None
        assert failed.error_code == "workflow_run_result_invalid"
        assert [event.kind for event in events] == [
            WorkflowEventKind.RUN_STARTED,
            WorkflowEventKind.RUN_FAILED,
        ]

    asyncio.run(exercise())


def test_recovery_fails_interrupted_runs_with_stable_summary() -> None:
    async def exercise() -> None:
        service, units, _, _ = _service()
        workflow = await service.create(workflow_configuration())
        pending = await service.start_run(
            workflow.id,
            run_id=uuid4(),
            input="will be replaced",
            trigger=WorkflowRunTrigger.MANUAL,
        )
        await service.aclose()
        interrupted = pending.start_node("start")
        units.run_repository.values[pending.id] = interrupted

        recovered_service = _service(units=units)[0]
        count = await recovered_service.recover_interrupted()
        recovered = await recovered_service.get_run(pending.id)

        assert count == 1
        assert recovered.status is WorkflowRunStatus.FAILED
        assert recovered.error_code == "workflow_run_interrupted"
        assert recovered.failed_node_id == "start"
        await recovered_service.aclose()

    asyncio.run(exercise())
