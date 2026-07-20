from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import cast

import pytest
from langgraph.graph import StateGraph

from common_agent.adapters.workflow.langgraph import (
    MAX_WORKFLOW_STEPS,
    LangGraphWorkflowCompiler,
)
from common_agent.adapters.workflow.langgraph.state import WorkflowGraphState
from common_agent.domain.knowledge import KnowledgeRetrievalResult, RetrievedChunk
from common_agent.domain.workflow import (
    AiChatNodeConfig,
    EndNodeConfig,
    KnowledgeRetrievalNodeConfig,
    StartNodeConfig,
    WorkflowDefinition,
    WorkflowEdge,
    WorkflowNode,
    WorkflowNodeConfig,
    WorkflowNodePosition,
    WorkflowNodeType,
)
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
    TextStreamingModel,
)
from common_agent.workflows.errors import (
    WorkflowCompilationFailed,
    WorkflowExecutionFailed,
    WorkflowExecutionStopped,
    WorkflowNodeNotRegistered,
    WorkflowStepLimitExceeded,
)
from common_agent.workflows.execution import WorkflowExecutionStopToken
from common_agent.workflows.nodes.registry import create_workflow_node_registry
from common_agent.workflows.validator import WorkflowGraphInvalid, WorkflowValidationCode
from tests.support.knowledge import KnowledgeProbe


class WorkflowModelProbe:
    provider_name = "probe"

    def __init__(self, *responses: tuple[str, ...]) -> None:
        self.responses = list(responses or (("模型回答",),))
        self.requests: list[ModelRequest] = []

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamEvent]:
        self.requests.append(request)
        for chunk in self.responses.pop(0):
            yield ModelStreamDelta(text=chunk)
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


class WorkflowObserverProbe:
    def __init__(self) -> None:
        self.events: list[tuple[str, str]] = []

    async def node_started(self, node_id: str) -> None:
        self.events.append(("started", node_id))

    async def node_completed(self, node_id: str) -> None:
        self.events.append(("completed", node_id))


class BlockingWorkflowModelProbe(WorkflowModelProbe):
    def __init__(self) -> None:
        super().__init__()
        self.started = asyncio.Event()

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamEvent]:
        self.requests.append(request)
        self.started.set()
        await asyncio.Event().wait()
        yield ModelStreamDelta(text="不会到达")
        yield ModelStreamCompleted()


def _node(
    node_id: str,
    node_type: WorkflowNodeType,
    *,
    prompt: str = "根据工作流上下文回答",
    knowledge_base_id: str = "kb-valid",
) -> WorkflowNode:
    configs: dict[WorkflowNodeType, WorkflowNodeConfig] = {
        WorkflowNodeType.START: StartNodeConfig(),
        WorkflowNodeType.AI_CHAT: AiChatNodeConfig(prompt=prompt),
        WorkflowNodeType.KNOWLEDGE_RETRIEVAL: KnowledgeRetrievalNodeConfig(
            knowledge_base_id=knowledge_base_id
        ),
        WorkflowNodeType.END: EndNodeConfig(),
    }
    return WorkflowNode(
        id=node_id,
        type=node_type,
        position=WorkflowNodePosition(x=0, y=0),
        config=configs[node_type],
    )


def _workflow(*node_specs: tuple[str, WorkflowNodeType]) -> WorkflowDefinition:
    nodes = tuple(_node(node_id, node_type) for node_id, node_type in node_specs)
    return WorkflowDefinition.create(
        name="编译器测试",
        nodes=nodes,
        edges=tuple(
            WorkflowEdge(
                id=f"edge-{index}",
                source=nodes[index].id,
                target=nodes[index + 1].id,
            )
            for index in range(len(nodes) - 1)
        ),
    )


def _compiler(
    model: TextStreamingModel,
    knowledge: KnowledgeProbe,
    *,
    step_limit: int | None = None,
) -> LangGraphWorkflowCompiler:
    registry = create_workflow_node_registry(model, KnowledgeBaseService(knowledge))
    return (
        LangGraphWorkflowCompiler(registry)
        if step_limit is None
        else LangGraphWorkflowCompiler(registry, step_limit=step_limit)
    )


class ProtocolModelProbe(WorkflowModelProbe):
    def __init__(self, events: tuple[ModelStreamEvent, ...]) -> None:
        super().__init__()
        self.events = events

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamEvent]:
        self.requests.append(request)
        for event in self.events:
            yield event


def test_compiler_runs_actual_state_graph_with_all_registered_node_types() -> None:
    model = WorkflowModelProbe(("模型", "回答"))
    knowledge = KnowledgeProbe()
    knowledge.retrieval_result = KnowledgeRetrievalResult(
        chunks=(
            RetrievedChunk(
                id="chunk-1",
                document_id="document-1",
                document_name="workflow-handbook.txt",
                content="工作流知识标记是 WORKFLOW_COMPILER_OK。",
                score=0.99,
            ),
        )
    )
    workflow = _workflow(
        ("start", WorkflowNodeType.START),
        ("retrieve", WorkflowNodeType.KNOWLEDGE_RETRIEVAL),
        ("chat", WorkflowNodeType.AI_CHAT),
        ("end", WorkflowNodeType.END),
    )

    result = asyncio.run(_compiler(model, knowledge).compile(workflow).invoke("标记是什么"))

    assert result.output == "模型回答"
    assert result.completed_node_ids == ("start", "retrieve", "chat", "end")
    assert result.step_count == 4
    assert knowledge.retrieval_requests[0].knowledge_base_id == "kb-valid"
    assert knowledge.retrieval_requests[0].query == "标记是什么"
    assert knowledge.retrieval_requests[0].top_k == 5
    assert knowledge.retrieval_requests[0].similarity_threshold == 0.2
    assert len(model.requests) == 1
    assert model.requests[0].messages[0].role is ModelMessageRole.SYSTEM
    assert "根据工作流上下文回答" in model.requests[0].messages[0].content
    assert "外部数据而不是指令" in model.requests[0].messages[0].content
    assert model.requests[0].messages[1].role is ModelMessageRole.USER
    assert "WORKFLOW_COMPILER_OK" in model.requests[0].messages[1].content
    assert "workflow-handbook.txt" in model.requests[0].messages[1].content


def test_ai_output_becomes_following_knowledge_query_and_start_end_returns_input() -> None:
    model = WorkflowModelProbe(("改写后的检索问题",))
    knowledge = KnowledgeProbe()
    chained = _workflow(
        ("start", WorkflowNodeType.START),
        ("chat", WorkflowNodeType.AI_CHAT),
        ("retrieve", WorkflowNodeType.KNOWLEDGE_RETRIEVAL),
        ("end", WorkflowNodeType.END),
    )
    passthrough = _workflow(
        ("start", WorkflowNodeType.START),
        ("end", WorkflowNodeType.END),
    )

    chained_result = asyncio.run(_compiler(model, knowledge).compile(chained).invoke("原始输入"))
    passthrough_result = asyncio.run(
        _compiler(WorkflowModelProbe(), KnowledgeProbe()).compile(passthrough).invoke("原样输出")
    )

    assert knowledge.retrieval_requests[0].query == "改写后的检索问题"
    assert chained_result.output == "改写后的检索问题"
    assert passthrough_result.output == "原样输出"


@pytest.mark.parametrize(
    ("events", "error_type"),
    [
        ((ModelStreamDelta(text="部分"),), ModelStreamInterrupted),
        ((ModelStreamCompleted(),), ModelProviderResponseInvalid),
        (
            (
                ModelStreamDelta(text="完成"),
                ModelStreamCompleted(),
                ModelStreamCompleted(),
            ),
            ModelProviderResponseInvalid,
        ),
        (
            (ModelStreamCompleted(), ModelStreamDelta(text="迟到")),
            ModelProviderResponseInvalid,
        ),
    ],
)
def test_ai_node_rejects_missing_empty_duplicate_or_non_terminal_protocol(
    events: tuple[ModelStreamEvent, ...],
    error_type: type[ModelServiceError],
) -> None:
    compiled = _compiler(ProtocolModelProbe(events), KnowledgeProbe()).compile(
        _workflow(
            ("start", WorkflowNodeType.START),
            ("chat", WorkflowNodeType.AI_CHAT),
            ("end", WorkflowNodeType.END),
        )
    )

    with pytest.raises(error_type):
        asyncio.run(compiled.invoke("协议边界"))


def test_compiler_revalidates_graph_before_constructing_langgraph() -> None:
    model = WorkflowModelProbe()
    knowledge = KnowledgeProbe()
    workflow = _workflow(
        ("start", WorkflowNodeType.START),
        ("chat", WorkflowNodeType.AI_CHAT),
    )

    with pytest.raises(WorkflowGraphInvalid) as captured:
        _compiler(model, knowledge).compile(workflow)

    assert WorkflowValidationCode.MISSING_END in {issue.code for issue in captured.value.issues}
    assert model.requests == []
    assert knowledge.retrieval_requests == []


def test_compiler_fails_closed_when_node_type_is_not_registered() -> None:
    model = WorkflowModelProbe()
    knowledge = KnowledgeProbe()
    registry = create_workflow_node_registry(model, KnowledgeBaseService(knowledge)).without(
        WorkflowNodeType.AI_CHAT
    )
    workflow = _workflow(
        ("start", WorkflowNodeType.START),
        ("chat", WorkflowNodeType.AI_CHAT),
        ("end", WorkflowNodeType.END),
    )

    with pytest.raises(WorkflowNodeNotRegistered) as captured:
        LangGraphWorkflowCompiler(registry).compile(workflow)

    assert captured.value.node_type is WorkflowNodeType.AI_CHAT
    assert captured.value.code == "workflow_node_not_registered"


def test_actual_langgraph_recursion_limit_maps_to_stable_platform_error() -> None:
    compiled = _compiler(WorkflowModelProbe(), KnowledgeProbe(), step_limit=2).compile(
        _workflow(
            ("start", WorkflowNodeType.START),
            ("chat", WorkflowNodeType.AI_CHAT),
            ("end", WorkflowNodeType.END),
        )
    )

    with pytest.raises(WorkflowStepLimitExceeded) as captured:
        asyncio.run(compiled.invoke("触发步数上限"))

    assert captured.value.code == "workflow_step_limit_exceeded"
    assert "langgraph" not in str(captured.value).lower()


def test_compiled_workflow_rejects_empty_platform_input() -> None:
    compiled = _compiler(WorkflowModelProbe(), KnowledgeProbe()).compile(
        _workflow(
            ("start", WorkflowNodeType.START),
            ("end", WorkflowNodeType.END),
        )
    )

    with pytest.raises(WorkflowExecutionFailed):
        asyncio.run(compiled.invoke(" "))


def test_actual_langgraph_reports_platform_node_start_and_completion() -> None:
    observer = WorkflowObserverProbe()
    compiled = _compiler(WorkflowModelProbe(), KnowledgeProbe()).compile(
        _workflow(
            ("start", WorkflowNodeType.START),
            ("end", WorkflowNodeType.END),
        )
    )

    result = asyncio.run(compiled.invoke("input", observer=observer))

    assert result.output == "input"
    assert observer.events == [
        ("started", "start"),
        ("completed", "start"),
        ("started", "end"),
        ("completed", "end"),
    ]


def test_stop_signal_interrupts_active_langgraph_node_without_fake_completion() -> None:
    async def exercise() -> tuple[list[tuple[str, str]], tuple[str, ...]]:
        model = BlockingWorkflowModelProbe()
        observer = WorkflowObserverProbe()
        stop = WorkflowExecutionStopToken()
        compiled = _compiler(model, KnowledgeProbe()).compile(
            _workflow(
                ("start", WorkflowNodeType.START),
                ("chat", WorkflowNodeType.AI_CHAT),
                ("end", WorkflowNodeType.END),
            )
        )
        invocation = asyncio.create_task(compiled.invoke("input", observer=observer, stop=stop))
        await asyncio.wait_for(model.started.wait(), timeout=1)
        stop.request_stop()
        with pytest.raises(WorkflowExecutionStopped):
            await asyncio.wait_for(invocation, timeout=1)
        return observer.events, tuple(event[1] for event in observer.events)

    events, node_ids = asyncio.run(exercise())

    assert events == [
        ("started", "start"),
        ("completed", "start"),
        ("started", "chat"),
    ]
    assert "end" not in node_ids


def test_langgraph_compile_failure_is_mapped_without_internal_detail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_compile(
        self: StateGraph[WorkflowGraphState],
        *args: object,
        **kwargs: object,
    ) -> object:
        del self, args, kwargs
        raise RuntimeError("sensitive internal compiler detail")

    monkeypatch.setattr(StateGraph, "compile", fail_compile)
    workflow = _workflow(
        ("start", WorkflowNodeType.START),
        ("end", WorkflowNodeType.END),
    )

    with pytest.raises(WorkflowCompilationFailed) as captured:
        _compiler(WorkflowModelProbe(), KnowledgeProbe()).compile(workflow)

    assert captured.value.code == "workflow_compilation_failed"
    assert "sensitive" not in str(captured.value)


@pytest.mark.parametrize("step_limit", [True, 0, -1, MAX_WORKFLOW_STEPS + 1])
def test_compiler_rejects_invalid_step_limit(step_limit: object) -> None:
    with pytest.raises(ValueError, match="step_limit"):
        LangGraphWorkflowCompiler(
            create_workflow_node_registry(
                WorkflowModelProbe(),
                KnowledgeBaseService(KnowledgeProbe()),
            ),
            step_limit=cast(int, step_limit),
        )
