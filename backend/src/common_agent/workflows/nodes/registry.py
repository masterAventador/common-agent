from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

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
from common_agent.models.base import ModelServiceError, ModelServiceUnavailable, StreamingChatModel
from common_agent.models.prompts import KNOWLEDGE_SAFETY_INSTRUCTION
from common_agent.runtimes.base import RuntimeKnowledgeChunk
from common_agent.workflows.errors import WorkflowNodeConfigurationInvalid
from common_agent.workflows.state import WorkflowGraphState, WorkflowStateUpdate

type WorkflowNodeRunner = Callable[[WorkflowGraphState], Awaitable[WorkflowStateUpdate]]
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
    model: StreamingChatModel,
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

    async def run(state: WorkflowGraphState) -> WorkflowStateUpdate:
        return _completed_update(state, node, output=state["input"])

    return run


def _ai_chat_factory(model: StreamingChatModel) -> WorkflowNodeFactory:
    def create(node: WorkflowNode) -> WorkflowNodeRunner:
        config = node.config
        if not isinstance(config, AiChatNodeConfig):
            raise WorkflowNodeConfigurationInvalid()

        async def run(state: WorkflowGraphState) -> WorkflowStateUpdate:
            messages = _model_messages(config.prompt, state)
            chunks: list[str] = []
            try:
                async for chunk in model.stream_text(messages):
                    chunks.append(chunk)
            except ModelServiceError:
                raise
            except Exception as error:
                try:
                    translated = model.translate_error(error, stream_started=bool(chunks))
                except Exception:
                    translated = None
                raise (translated or ModelServiceUnavailable()) from None
            output = "".join(chunks)
            if not output.strip():
                raise ModelServiceUnavailable()
            return _completed_update(state, node, output=output)

        return run

    return create


def _knowledge_retrieval_factory(
    knowledge_bases: KnowledgeBaseService,
) -> WorkflowNodeFactory:
    def create(node: WorkflowNode) -> WorkflowNodeRunner:
        config = node.config
        if not isinstance(config, KnowledgeRetrievalNodeConfig):
            raise WorkflowNodeConfigurationInvalid()

        async def run(state: WorkflowGraphState) -> WorkflowStateUpdate:
            query = state.get("output") or state["input"]
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
            return _completed_update(state, node, knowledge=knowledge)

        return run

    return create


def _end_factory(node: WorkflowNode) -> WorkflowNodeRunner:
    if not isinstance(node.config, EndNodeConfig):
        raise WorkflowNodeConfigurationInvalid()

    async def run(state: WorkflowGraphState) -> WorkflowStateUpdate:
        output = state.get("output")
        if not output:
            output = _knowledge_text(state.get("knowledge", ())) or state["input"]
        return _completed_update(state, node, output=output)

    return run


def _model_messages(prompt: str, state: WorkflowGraphState) -> tuple[BaseMessage, ...]:
    system_prompt = f"{prompt}\n\n{KNOWLEDGE_SAFETY_INSTRUCTION}"
    context = state.get("output") or state["input"]
    knowledge = _knowledge_text(state.get("knowledge", ()))
    if knowledge:
        context = f"用户输入:\n{context}\n\n检索到的知识片段:\n{knowledge}"
    return SystemMessage(content=system_prompt), HumanMessage(content=context)


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


def _completed_update(
    state: WorkflowGraphState,
    node: WorkflowNode,
    *,
    output: str | None = None,
    knowledge: tuple[RuntimeKnowledgeChunk, ...] | None = None,
) -> WorkflowStateUpdate:
    update: WorkflowStateUpdate = {
        "current_node_id": node.id,
        "completed_node_ids": (*state.get("completed_node_ids", ()), node.id),
        "step_count": state.get("step_count", 0) + 1,
    }
    if output is not None:
        update["output"] = output
    if knowledge is not None:
        update["knowledge"] = knowledge
    return update
