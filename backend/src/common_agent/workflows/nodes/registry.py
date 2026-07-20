from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass

from common_agent.domain.knowledge import (
    DEFAULT_KNOWLEDGE_SIMILARITY_THRESHOLD,
    DEFAULT_KNOWLEDGE_TOP_K,
    KnowledgeRetrievalRequest,
    KnowledgeRetrievalResult,
    RetrievedChunk,
)
from common_agent.domain.workflow import (
    AiChatNodeConfig,
    EndNodeConfig,
    KnowledgeRetrievalNodeConfig,
    StartNodeConfig,
    WorkflowNode,
    WorkflowNodeType,
)
from common_agent.knowledge.base import (
    KnowledgeProviderResponseInvalid,
    KnowledgeServiceError,
    KnowledgeServiceUnavailable,
)
from common_agent.knowledge.service import KnowledgeBaseService
from common_agent.models.base import (
    ModelMessage,
    ModelMessageRole,
    ModelProviderResponseInvalid,
    ModelRequest,
    ModelServiceError,
    ModelServiceUnavailable,
    ModelStreamCompleted,
    ModelStreamDelta,
    ModelStreamInterrupted,
    TextStreamingModel,
)
from common_agent.models.prompts import KNOWLEDGE_SAFETY_INSTRUCTION
from common_agent.runtimes.base import RuntimeKnowledgeChunk
from common_agent.workflows.errors import WorkflowNodeConfigurationInvalid
from common_agent.workflows.execution import (
    WorkflowNodeExecutionContext,
    WorkflowNodeExecutionResult,
)

type WorkflowNodeRunner = Callable[
    [WorkflowNodeExecutionContext], Awaitable[WorkflowNodeExecutionResult]
]
type WorkflowNodeFactory = Callable[[WorkflowNode], WorkflowNodeRunner]


@dataclass(frozen=True, slots=True)
class WorkflowNodeRegistry:
    _factories: Mapping[WorkflowNodeType, WorkflowNodeFactory]

    def create(self, node: WorkflowNode) -> WorkflowNodeRunner | None:
        factory = self._factories.get(node.type)
        return None if factory is None else factory(node)

    def without(self, node_type: WorkflowNodeType) -> WorkflowNodeRegistry:
        return WorkflowNodeRegistry(
            {key: value for key, value in self._factories.items() if key is not node_type}
        )


def create_workflow_node_registry(
    model: TextStreamingModel,
    knowledge_bases: KnowledgeBaseService,
) -> WorkflowNodeRegistry:
    return WorkflowNodeRegistry(
        {
            WorkflowNodeType.START: _start_factory,
            WorkflowNodeType.AI_CHAT: _ai_chat_factory(model),
            WorkflowNodeType.KNOWLEDGE_RETRIEVAL: _knowledge_retrieval_factory(knowledge_bases),
            WorkflowNodeType.END: _end_factory,
        }
    )


def _start_factory(node: WorkflowNode) -> WorkflowNodeRunner:
    if not isinstance(node.config, StartNodeConfig):
        raise WorkflowNodeConfigurationInvalid()

    async def run(state: WorkflowNodeExecutionContext) -> WorkflowNodeExecutionResult:
        return WorkflowNodeExecutionResult(output=state.user_input)

    return run


def _ai_chat_factory(model: TextStreamingModel) -> WorkflowNodeFactory:
    def create(node: WorkflowNode) -> WorkflowNodeRunner:
        config = node.config
        if not isinstance(config, AiChatNodeConfig):
            raise WorkflowNodeConfigurationInvalid()

        async def run(state: WorkflowNodeExecutionContext) -> WorkflowNodeExecutionResult:
            request = _model_request(config.prompt, state)
            chunks: list[str] = []
            completed = False
            try:
                async for event in model.stream(request):
                    if isinstance(event, ModelStreamDelta):
                        if completed:
                            raise ModelProviderResponseInvalid()
                        chunks.append(event.text)
                    elif isinstance(event, ModelStreamCompleted):
                        if completed:
                            raise ModelProviderResponseInvalid()
                        completed = True
                    else:
                        raise ModelProviderResponseInvalid()
            except ModelServiceError:
                raise
            except Exception as error:
                try:
                    translated = model.translate_error(error, stream_started=bool(chunks))
                except Exception:
                    translated = None
                raise (translated or ModelServiceUnavailable()) from None
            if not completed:
                if chunks:
                    raise ModelStreamInterrupted()
                raise ModelProviderResponseInvalid()
            output = "".join(chunks)
            if not output.strip():
                raise ModelProviderResponseInvalid()
            return WorkflowNodeExecutionResult(output=output)

        return run

    return create


def _knowledge_retrieval_factory(
    knowledge_bases: KnowledgeBaseService,
) -> WorkflowNodeFactory:
    def create(node: WorkflowNode) -> WorkflowNodeRunner:
        config = node.config
        if not isinstance(config, KnowledgeRetrievalNodeConfig):
            raise WorkflowNodeConfigurationInvalid()

        async def run(state: WorkflowNodeExecutionContext) -> WorkflowNodeExecutionResult:
            query = state.output or state.user_input
            try:
                result = await knowledge_bases.retrieve(
                    KnowledgeRetrievalRequest(
                        knowledge_base_id=config.knowledge_base_id,
                        query=query,
                        top_k=DEFAULT_KNOWLEDGE_TOP_K,
                        similarity_threshold=DEFAULT_KNOWLEDGE_SIMILARITY_THRESHOLD,
                    )
                )
                knowledge = _runtime_chunks(config.knowledge_base_id, result)
            except KnowledgeServiceError:
                raise
            except Exception:
                raise KnowledgeServiceUnavailable() from None
            return WorkflowNodeExecutionResult(knowledge=knowledge)

        return run

    return create


def _end_factory(node: WorkflowNode) -> WorkflowNodeRunner:
    if not isinstance(node.config, EndNodeConfig):
        raise WorkflowNodeConfigurationInvalid()

    async def run(state: WorkflowNodeExecutionContext) -> WorkflowNodeExecutionResult:
        output = state.output
        if not output:
            output = _knowledge_text(state.knowledge) or state.user_input
        return WorkflowNodeExecutionResult(output=output)

    return run


def _model_request(prompt: str, state: WorkflowNodeExecutionContext) -> ModelRequest:
    system_prompt = f"{prompt}\n\n{KNOWLEDGE_SAFETY_INSTRUCTION}"
    context = state.output or state.user_input
    knowledge = _knowledge_text(state.knowledge)
    if knowledge:
        context = f"用户输入:\n{context}\n\n检索到的知识片段:\n{knowledge}"
    return ModelRequest(
        messages=(
            ModelMessage(role=ModelMessageRole.SYSTEM, content=system_prompt),
            ModelMessage(role=ModelMessageRole.USER, content=context),
        )
    )


def _knowledge_text(chunks: Sequence[RuntimeKnowledgeChunk]) -> str:
    fragments = []
    for position, chunk in enumerate(chunks, start=1):
        fragments.append(
            "\n".join(
                (
                    f"[知识片段 {position}]",
                    f"文档名称: {chunk.document_name}",
                    f"相关度: {chunk.score}",
                    "片段正文:",
                    chunk.content,
                    f"[/知识片段 {position}]",
                )
            )
        )
    return "\n\n".join(fragments)


def _runtime_chunks(
    knowledge_base_id: str,
    result: KnowledgeRetrievalResult,
) -> tuple[RuntimeKnowledgeChunk, ...]:
    if not isinstance(result, KnowledgeRetrievalResult):
        raise KnowledgeProviderResponseInvalid()
    if len(result.chunks) > DEFAULT_KNOWLEDGE_TOP_K:
        raise KnowledgeProviderResponseInvalid()
    if any(not isinstance(chunk, RetrievedChunk) for chunk in result.chunks):
        raise KnowledgeProviderResponseInvalid()
    if len({chunk.id for chunk in result.chunks}) != len(result.chunks):
        raise KnowledgeProviderResponseInvalid()
    try:
        return tuple(
            RuntimeKnowledgeChunk(
                knowledge_base_id=knowledge_base_id,
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                document_name=chunk.document_name,
                content=chunk.content,
                score=chunk.score,
            )
            for chunk in result.chunks
        )
    except (AttributeError, TypeError, ValueError):
        raise KnowledgeProviderResponseInvalid() from None
