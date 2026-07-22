from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest

from common_agent.domain.employee import Employee
from common_agent.domain.knowledge import KnowledgeRetrievalResult, RetrievedChunk
from common_agent.domain.model_configuration import ModelConfiguration, ModelConfigurationInput
from common_agent.domain.workflow import (
    AiChatNodeConfig,
    AiChatTargetType,
    EmployeeAiChatTarget,
    ModelAiChatTarget,
)
from common_agent.domain.workflow_run import WorkflowAiTargetSummary
from common_agent.knowledge.service import KnowledgeBaseService
from common_agent.models.base import (
    ModelMessageRole,
    ModelProviderResponseInvalid,
    ModelRequest,
    ModelServiceError,
    ModelStreamCompleted,
    ModelStreamDelta,
    ModelStreamEvent,
    ModelStreamInterrupted,
)
from common_agent.runtimes.base import (
    EmployeeRuntimeRequest,
    RuntimeEvent,
    RuntimeEventEmitter,
    RuntimeEventKind,
    RuntimeStopSignal,
)
from common_agent.workflows.ai_targets import (
    WorkflowAiTargetExecutionFailed,
    WorkflowAiTargetExecutor,
)
from common_agent.workflows.errors import WorkflowExecutionStopped
from common_agent.workflows.execution import (
    WorkflowExecutionObserver,
    WorkflowExecutionStopToken,
    WorkflowNodeExecutionContext,
)
from tests.support.knowledge import KnowledgeProbe


class _Directory:
    def __init__(self, employee: Employee, model: ModelConfiguration) -> None:
        self.employee = employee
        self.model = model

    async def get_employee(self, employee_id: UUID) -> Employee:
        assert employee_id == self.employee.id
        return self.employee

    async def get_model_configuration(self, model_configuration_id: UUID) -> ModelConfiguration:
        assert model_configuration_id == self.model.id
        return self.model


class _Model:
    provider_name = "probe"

    def __init__(self, events: tuple[ModelStreamEvent, ...] | None = None) -> None:
        self.requests: list[ModelRequest] = []
        self.events = events or (
            ModelStreamDelta(text="目标模型回答"),
            ModelStreamCompleted(),
        )

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamEvent]:
        self.requests.append(request)
        for event in self.events:
            yield event

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


class _ModelResolver:
    def __init__(self, model: _Model) -> None:
        self.model = model
        self.identifiers: list[str] = []

    async def resolve(self, model_identifier: str) -> _Model:
        self.identifiers.append(model_identifier)
        return self.model


class _Runtime:
    def __init__(self, outcome: RuntimeEventKind = RuntimeEventKind.COMPLETED) -> None:
        self.requests: list[EmployeeRuntimeRequest] = []
        self.outcome = outcome

    async def stream(
        self,
        request: EmployeeRuntimeRequest,
        *,
        stop: RuntimeStopSignal,
    ) -> AsyncIterator[RuntimeEvent]:
        assert stop.is_requested is False
        self.requests.append(request)
        emitter = RuntimeEventEmitter(request.assistant_message_id)
        if self.outcome is RuntimeEventKind.COMPLETED:
            yield emitter.delta("数字员工回答")
            yield emitter.complete()
        elif self.outcome is RuntimeEventKind.FAILED:
            yield emitter.fail("employee_runtime_failed")
        elif self.outcome is RuntimeEventKind.STOPPED:
            yield emitter.stop()

    async def aclose(self) -> None:
        pass


class _InvalidRuntime:
    def __init__(self, scenario: str) -> None:
        self.scenario = scenario

    async def stream(
        self,
        request: EmployeeRuntimeRequest,
        *,
        stop: RuntimeStopSignal,
    ) -> AsyncIterator[RuntimeEvent]:
        del stop
        emitter = RuntimeEventEmitter(request.assistant_message_id)
        first = emitter.delta("不应进入工作流结果")
        if self.scenario == "foreign_message":
            yield RuntimeEvent(
                assistant_message_id=uuid4(),
                sequence=first.sequence,
                kind=first.kind,
                delta=first.delta,
            )
            yield emitter.complete()
            return
        yield first
        if self.scenario == "duplicate_sequence":
            yield RuntimeEvent(
                assistant_message_id=first.assistant_message_id,
                sequence=first.sequence,
                kind=first.kind,
                delta="重复序号内容",
            )
            yield emitter.complete()
            return
        yield RuntimeEvent(
            assistant_message_id=first.assistant_message_id,
            sequence=3,
            kind=RuntimeEventKind.COMPLETED,
        )

    async def aclose(self) -> None:
        pass


class _Observer(WorkflowExecutionObserver):
    def __init__(self) -> None:
        self.summaries: list[WorkflowAiTargetSummary] = []

    async def node_started(self, node_id: str) -> None:
        del node_id

    async def node_completed(self, node_id: str) -> None:
        del node_id

    async def ai_target_resolved(self, summary: WorkflowAiTargetSummary) -> None:
        self.summaries.append(summary)


def _model_configuration(
    *,
    enabled: bool = True,
    streaming_breaks_tool_calls: bool = False,
) -> ModelConfiguration:
    return ModelConfiguration.create(
        configuration=ModelConfigurationInput(
            display_name="工作流测试模型",
            model_identifier="qwen-max",
            enabled=enabled,
        ),
        streaming_breaks_tool_calls=streaming_breaks_tool_calls,
    )


def _employee(
    model: ModelConfiguration,
    *,
    knowledge_base_id: str | None = None,
) -> Employee:
    return Employee.create(
        name="工作流员工",
        system_prompt="只使用可验证的信息回答",
        default_model_configuration_id=model.id,
        default_model_identifier=model.model_identifier,
        knowledge_base_id=knowledge_base_id,
        allowed_workflow_ids=(uuid4(),),
    )


def _context(observer: _Observer) -> WorkflowNodeExecutionContext:
    return WorkflowNodeExecutionContext(
        user_input="用户问题",
        output="上游内容",
        knowledge=(),
        node_id="chat",
        run_id=uuid4(),
        observer=observer,
        stop=WorkflowExecutionStopToken(),
    )


def test_model_target_resolves_selected_enabled_configuration_and_records_snapshot() -> None:
    async def exercise() -> None:
        configuration = _model_configuration()
        employee = _employee(configuration)
        model = _Model()
        resolver = _ModelResolver(model)
        observer = _Observer()
        executor = WorkflowAiTargetExecutor(
            _Directory(employee, configuration),
            resolver,
            KnowledgeBaseService(KnowledgeProbe()),
        )

        result = await executor.execute(
            AiChatNodeConfig(
                prompt="按节点指令回答",
                target=ModelAiChatTarget(model_configuration_id=configuration.id),
            ),
            _context(observer),
        )

        assert result.output == "目标模型回答"
        assert resolver.identifiers == ["qwen-max"]
        assert model.requests[0].messages[-1].role is ModelMessageRole.USER
        assert model.requests[0].messages[-1].content == "上游内容"
        assert observer.summaries[0].target_type is AiChatTargetType.MODEL
        assert observer.summaries[0].model_identifier == "qwen-max"

    asyncio.run(exercise())


def test_employee_target_inherits_current_employee_configuration_for_deep_agent_runtime() -> None:
    async def exercise() -> None:
        configuration = _model_configuration(streaming_breaks_tool_calls=True)
        employee = _employee(configuration, knowledge_base_id="kb-valid")
        runtime = _Runtime()
        observer = _Observer()
        knowledge = KnowledgeProbe()
        knowledge.retrieval_result = KnowledgeRetrievalResult(
            chunks=(
                RetrievedChunk(
                    id="chunk-1",
                    document_id="document-1",
                    document_name="员工手册.txt",
                    content="可验证的知识片段",
                    score=0.91,
                ),
            )
        )
        executor = WorkflowAiTargetExecutor(
            _Directory(employee, configuration),
            _ModelResolver(_Model()),
            KnowledgeBaseService(knowledge),
            employee_runtime=runtime,
        )

        result = await executor.execute(
            AiChatNodeConfig(
                prompt="补充节点约束",
                target=EmployeeAiChatTarget(employee_id=employee.id),
            ),
            _context(observer),
        )

        request = runtime.requests[0]
        assert result.output == "数字员工回答"
        assert request.employee_id == employee.id
        assert request.model_identifier == "qwen-max"
        assert request.streaming_breaks_tool_calls is True
        assert request.allowed_workflow_ids == employee.allowed_workflow_ids
        assert "只使用可验证的信息回答" in request.system_instruction
        assert "补充节点约束" in request.system_instruction
        assert request.history[-1].content == "上游内容"
        assert request.knowledge_context[0].content == "可验证的知识片段"
        assert knowledge.retrieval_requests[0].query == "上游内容"
        assert request.workflow_run_id is not None
        assert observer.summaries[0].target_type is AiChatTargetType.EMPLOYEE

    asyncio.run(exercise())


@pytest.mark.parametrize(
    ("events", "expected"),
    [
        ((ModelStreamDelta(text="未完成"),), ModelStreamInterrupted),
        ((ModelStreamCompleted(),), ModelProviderResponseInvalid),
        (
            (ModelStreamCompleted(), ModelStreamCompleted()),
            ModelProviderResponseInvalid,
        ),
    ],
)
def test_model_target_rejects_incomplete_or_invalid_streams(
    events: tuple[ModelStreamEvent, ...],
    expected: type[ModelServiceError],
) -> None:
    async def exercise() -> None:
        configuration = _model_configuration()
        model = _Model(events)
        executor = WorkflowAiTargetExecutor(
            _Directory(_employee(configuration), configuration),
            _ModelResolver(model),
            KnowledgeBaseService(KnowledgeProbe()),
        )

        with pytest.raises(expected):
            await executor.execute(
                AiChatNodeConfig(
                    prompt="回答",
                    target=ModelAiChatTarget(model_configuration_id=configuration.id),
                ),
                _context(_Observer()),
            )

    asyncio.run(exercise())


@pytest.mark.parametrize(
    ("outcome", "expected_code"),
    [
        (RuntimeEventKind.FAILED, "employee_runtime_failed"),
        (RuntimeEventKind.DELTA, None),
    ],
)
def test_employee_target_propagates_runtime_failure_or_interruption(
    outcome: RuntimeEventKind,
    expected_code: str | None,
) -> None:
    async def exercise() -> None:
        configuration = _model_configuration()
        employee = _employee(configuration)
        runtime = _Runtime(outcome)
        executor = WorkflowAiTargetExecutor(
            _Directory(employee, configuration),
            _ModelResolver(_Model()),
            KnowledgeBaseService(KnowledgeProbe()),
            employee_runtime=runtime,
        )

        with pytest.raises(WorkflowAiTargetExecutionFailed) as captured:
            await executor.execute(
                AiChatNodeConfig(
                    prompt="回答",
                    target=EmployeeAiChatTarget(employee_id=employee.id),
                ),
                _context(_Observer()),
            )
        assert captured.value.code == (expected_code or "model_stream_interrupted")

    asyncio.run(exercise())


@pytest.mark.parametrize(
    "scenario",
    ("foreign_message", "duplicate_sequence", "sequence_gap"),
)
def test_employee_target_rejects_runtime_events_outside_the_current_ordered_stream(
    scenario: str,
) -> None:
    async def exercise() -> None:
        configuration = _model_configuration()
        employee = _employee(configuration)
        executor = WorkflowAiTargetExecutor(
            _Directory(employee, configuration),
            _ModelResolver(_Model()),
            KnowledgeBaseService(KnowledgeProbe()),
            employee_runtime=_InvalidRuntime(scenario),
        )

        with pytest.raises(WorkflowAiTargetExecutionFailed) as captured:
            await executor.execute(
                AiChatNodeConfig(
                    prompt="回答",
                    target=EmployeeAiChatTarget(employee_id=employee.id),
                ),
                _context(_Observer()),
            )

        assert captured.value.code == "runtime_response_invalid"

    asyncio.run(exercise())


def test_employee_target_stop_and_runtime_binding_guards() -> None:
    async def exercise() -> None:
        configuration = _model_configuration()
        employee = _employee(configuration)
        executor = WorkflowAiTargetExecutor(
            _Directory(employee, configuration),
            _ModelResolver(_Model()),
            KnowledgeBaseService(KnowledgeProbe()),
            employee_runtime=_Runtime(RuntimeEventKind.STOPPED),
        )
        with pytest.raises(WorkflowExecutionStopped):
            await executor.execute(
                AiChatNodeConfig(
                    prompt="回答",
                    target=EmployeeAiChatTarget(employee_id=employee.id),
                ),
                _context(_Observer()),
            )
        with pytest.raises(RuntimeError, match="不能重复绑定"):
            executor.bind_employee_runtime(_Runtime())

    asyncio.run(exercise())


def test_disabled_model_target_fails_before_provider_call() -> None:
    async def exercise() -> None:
        configuration = _model_configuration(enabled=False)
        employee = _employee(configuration)
        resolver = _ModelResolver(_Model())
        executor = WorkflowAiTargetExecutor(
            _Directory(employee, configuration),
            resolver,
            KnowledgeBaseService(KnowledgeProbe()),
        )

        with pytest.raises(WorkflowAiTargetExecutionFailed) as captured:
            await executor.execute(
                AiChatNodeConfig(
                    prompt="回答",
                    target=ModelAiChatTarget(model_configuration_id=configuration.id),
                ),
                _context(_Observer()),
            )

        assert captured.value.code == "workflow_model_configuration_disabled"
        assert resolver.identifiers == []

    asyncio.run(exercise())
