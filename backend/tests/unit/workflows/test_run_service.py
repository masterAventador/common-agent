from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence
from uuid import UUID, uuid4

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage

from common_agent.application.workflow_service import (
    WorkflowNotFound,
    WorkflowRunConflict,
    WorkflowRunNotActive,
    WorkflowRunNotFound,
    WorkflowService,
)
from common_agent.domain.workflow_run import (
    WorkflowRun,
    WorkflowRunOrigin,
    WorkflowRunStatus,
    WorkflowRunTrigger,
)
from common_agent.knowledge.service import KnowledgeBaseService
from common_agent.models.base import ModelServiceError, ModelServiceUnavailable
from common_agent.runtimes.base import RuntimeStopSignal
from common_agent.workflows.compiler import CompiledWorkflow, WorkflowCompiler
from common_agent.workflows.events import WorkflowEventBroker, WorkflowEventKind
from common_agent.workflows.nodes.registry import create_workflow_node_registry
from common_agent.workflows.state import WorkflowExecutionObserver, WorkflowExecutionResult
from tests.support.knowledge import KnowledgeProbe
from tests.unit.workflows.support import WorkflowUnitOfWorkFactoryProbe, workflow_configuration


class RunModelProbe:
    provider_name = "probe"

    def __init__(self, *, block: bool = False, fail: bool = False) -> None:
        self.block = block
        self.fail = fail
        self.started = asyncio.Event()

    @property
    def chat_model(self) -> BaseChatModel:
        raise NotImplementedError

    async def stream_text(self, messages: Sequence[BaseMessage]) -> AsyncIterator[str]:
        del messages
        self.started.set()
        if self.fail:
            raise ModelServiceUnavailable
        if self.block:
            await asyncio.Event().wait()
        yield "工作流结果"

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


def _service(
    *,
    model: RunModelProbe | None = None,
    units: WorkflowUnitOfWorkFactoryProbe | None = None,
) -> tuple[WorkflowService, WorkflowUnitOfWorkFactoryProbe, WorkflowEventBroker, RunModelProbe]:
    active_units = units or WorkflowUnitOfWorkFactoryProbe()
    knowledge = KnowledgeProbe()
    active_model = model or RunModelProbe()
    events = WorkflowEventBroker()
    compiler = WorkflowCompiler(
        create_workflow_node_registry(active_model, KnowledgeBaseService(knowledge))
    )
    return (
        WorkflowService(
            active_units,
            KnowledgeBaseService(knowledge),
            compiler=compiler,
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

    asyncio.run(exercise())


def test_wait_for_run_rejects_unknown_run() -> None:
    async def exercise() -> None:
        service, _, _, _ = _service()

        with pytest.raises(WorkflowRunNotFound):
            await service.wait_for_run(uuid4())
        await service.aclose()

    asyncio.run(exercise())


def test_employee_run_persists_origin_and_lists_only_its_conversation() -> None:
    async def exercise() -> None:
        service, _, _, _ = _service()
        workflow = await service.create(workflow_configuration())
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


def test_compiler_result_mismatch_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    async def invalid_invoke(
        compiled: CompiledWorkflow,
        user_input: str,
        *,
        observer: WorkflowExecutionObserver | None = None,
        stop: RuntimeStopSignal | None = None,
    ) -> WorkflowExecutionResult:
        del compiled, user_input, observer, stop
        return WorkflowExecutionResult(
            output="不可信结果",
            completed_node_ids=("not-persisted",),
            step_count=1,
        )

    monkeypatch.setattr(CompiledWorkflow, "invoke", invalid_invoke)

    async def exercise() -> None:
        service, _, broker, _ = _service()
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
