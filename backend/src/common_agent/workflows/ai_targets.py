from __future__ import annotations

from typing import Protocol
from uuid import NAMESPACE_URL, UUID, uuid5

from common_agent.conversations.contracts import ToolGrantDirectory
from common_agent.domain.conversation import MessageRole
from common_agent.domain.employee import Employee
from common_agent.domain.knowledge import (
    DEFAULT_KNOWLEDGE_SIMILARITY_THRESHOLD,
    DEFAULT_KNOWLEDGE_TOP_K,
    KnowledgeRetrievalRequest,
)
from common_agent.domain.model_configuration import ModelConfiguration
from common_agent.domain.workflow import (
    AiChatNodeConfig,
    AiChatTargetType,
    EmployeeAiChatTarget,
    ModelAiChatTarget,
)
from common_agent.domain.workflow_run import WorkflowAiTargetSummary
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
from common_agent.runtimes.base import (
    EmployeeRuntime,
    EmployeeRuntimeRequest,
    RuntimeConversationMessage,
    RuntimeEvent,
    RuntimeEventKind,
    RuntimeKnowledgeChunk,
)
from common_agent.tools.models import ToolGrantTarget, ToolGrantTargetType
from common_agent.workflows.errors import (
    WorkflowExecutionError,
    WorkflowExecutionStopped,
    WorkflowNodeConfigurationInvalid,
)
from common_agent.workflows.execution import (
    WorkflowNodeExecutionContext,
    WorkflowNodeExecutionResult,
)


class WorkflowAiTargetDirectory(Protocol):
    async def get_employee(self, employee_id: UUID) -> Employee: ...

    async def get_model_configuration(
        self,
        model_configuration_id: UUID,
    ) -> ModelConfiguration: ...


class WorkflowModelResolver(Protocol):
    async def resolve(self, model_identifier: str) -> TextStreamingModel: ...


class WorkflowAiTargetExecutionFailed(WorkflowExecutionError):
    retryable = False

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class StaticWorkflowModelResolver:
    def __init__(self, model: TextStreamingModel) -> None:
        self._model = model

    async def resolve(self, model_identifier: str) -> TextStreamingModel:
        del model_identifier
        return self._model


class WorkflowAiTargetExecutor:
    def __init__(
        self,
        directory: WorkflowAiTargetDirectory,
        models: WorkflowModelResolver,
        knowledge_bases: KnowledgeBaseService,
        *,
        employee_runtime: EmployeeRuntime | None = None,
        tools: ToolGrantDirectory | None = None,
    ) -> None:
        self._directory = directory
        self._models = models
        self._knowledge_bases = knowledge_bases
        self._employee_runtime = employee_runtime
        self._tools = tools

    def bind_employee_runtime(self, runtime: EmployeeRuntime) -> None:
        if self._employee_runtime is not None and self._employee_runtime is not runtime:
            raise RuntimeError("工作流数字员工运行时不能重复绑定")
        self._employee_runtime = runtime

    async def execute(
        self,
        config: AiChatNodeConfig,
        state: WorkflowNodeExecutionContext,
    ) -> WorkflowNodeExecutionResult:
        if config.target is None or state.node_id is None or state.run_id is None:
            raise WorkflowNodeConfigurationInvalid
        if isinstance(config.target, ModelAiChatTarget):
            return await self._execute_model(config, state)
        return await self._execute_employee(config, state)

    async def _execute_model(
        self,
        config: AiChatNodeConfig,
        state: WorkflowNodeExecutionContext,
    ) -> WorkflowNodeExecutionResult:
        node_id = state.node_id
        if node_id is None:
            raise WorkflowNodeConfigurationInvalid
        target = config.target
        if not isinstance(target, ModelAiChatTarget):
            raise WorkflowNodeConfigurationInvalid
        model_configuration = await self._directory.get_model_configuration(
            target.model_configuration_id
        )
        if not model_configuration.enabled:
            raise WorkflowAiTargetExecutionFailed("workflow_model_configuration_disabled")
        model = await self._models.resolve(model_configuration.model_identifier)
        await state.report_ai_target(
            WorkflowAiTargetSummary(
                node_id=node_id,
                target_type=AiChatTargetType.MODEL,
                target_id=model_configuration.id,
                target_name=model_configuration.display_name,
                model_configuration_id=model_configuration.id,
                model_identifier=model_configuration.model_identifier,
            )
        )
        return WorkflowNodeExecutionResult(
            output=await _stream_model(model, _model_request(config.prompt, state))
        )

    async def _execute_employee(
        self,
        config: AiChatNodeConfig,
        state: WorkflowNodeExecutionContext,
    ) -> WorkflowNodeExecutionResult:
        node_id = state.node_id
        run_id = state.run_id
        if node_id is None or run_id is None:
            raise WorkflowNodeConfigurationInvalid
        target = config.target
        if not isinstance(target, EmployeeAiChatTarget):
            raise WorkflowNodeConfigurationInvalid
        runtime = self._employee_runtime
        if runtime is None or state.stop is None:
            raise WorkflowAiTargetExecutionFailed("workflow_employee_runtime_unavailable")
        employee = await self._directory.get_employee(target.employee_id)
        model_configuration = await self._directory.get_model_configuration(
            employee.default_model_configuration_id
        )
        if not model_configuration.enabled:
            raise WorkflowAiTargetExecutionFailed("workflow_model_configuration_disabled")
        context = state.output or state.user_input
        knowledge = await _retrieve_knowledge(
            self._knowledge_bases,
            employee.knowledge_base_id,
            context,
        )
        await state.report_ai_target(
            WorkflowAiTargetSummary(
                node_id=node_id,
                target_type=AiChatTargetType.EMPLOYEE,
                target_id=employee.id,
                target_name=employee.name,
                model_configuration_id=model_configuration.id,
                model_identifier=model_configuration.model_identifier,
            )
        )
        user_message_id = uuid5(
            NAMESPACE_URL,
            f"common-agent:workflow:{run_id}:{node_id}:user",
        )
        assistant_message_id = uuid5(
            NAMESPACE_URL,
            f"common-agent:workflow:{run_id}:{node_id}:assistant",
        )
        allowed_tool_capability_ids: tuple[UUID, ...] = ()
        if self._tools is not None:
            grants = await self._tools.employee_grants(employee.id)
            allowed_tool_capability_ids = grants.capability_ids
        request = EmployeeRuntimeRequest(
            conversation_id=run_id,
            employee_id=employee.id,
            assistant_message_id=assistant_message_id,
            assistant_sequence_number=2,
            model_identifier=model_configuration.model_identifier,
            streaming_breaks_tool_calls=model_configuration.streaming_breaks_tool_calls,
            system_instruction=(
                f"{employee.system_prompt}\n\n当前工作流节点指令:\n{config.prompt}"
            ),
            history=(
                RuntimeConversationMessage(
                    message_id=user_message_id,
                    sequence_number=1,
                    role=MessageRole.USER,
                    content=context,
                ),
            ),
            knowledge_base_id=employee.knowledge_base_id,
            knowledge_context=knowledge,
            allowed_workflow_ids=employee.allowed_workflow_ids,
            allowed_tool_capability_ids=allowed_tool_capability_ids,
            tool_grant_target=ToolGrantTarget(ToolGrantTargetType.EMPLOYEE, employee.id),
            workflow_run_id=run_id,
        )
        fragments: list[str] = []
        last_sequence = 0
        async for event in runtime.stream(request, stop=state.stop):
            if (
                not isinstance(event, RuntimeEvent)
                or event.assistant_message_id != assistant_message_id
                or event.sequence != last_sequence + 1
            ):
                raise WorkflowAiTargetExecutionFailed("runtime_response_invalid")
            last_sequence = event.sequence
            if event.kind is RuntimeEventKind.DELTA:
                if event.delta is None:
                    raise WorkflowAiTargetExecutionFailed("runtime_response_invalid")
                fragments.append(event.delta)
            elif event.kind in {
                # 思考过程不是节点的产出, 工具事件也不是; 跳过但不能判失败
                RuntimeEventKind.REASONING,
                RuntimeEventKind.TOOL_STARTED,
                RuntimeEventKind.TOOL_COMPLETED,
                RuntimeEventKind.TOOL_FAILED,
            }:
                continue
            elif event.kind is RuntimeEventKind.COMPLETED:
                output = "".join(fragments)
                if not output.strip():
                    raise WorkflowAiTargetExecutionFailed("runtime_response_invalid")
                return WorkflowNodeExecutionResult(output=output)
            elif event.kind is RuntimeEventKind.STOPPED:
                raise WorkflowExecutionStopped
            else:
                raise WorkflowAiTargetExecutionFailed(
                    event.error_code or "deep_agent_execution_failed"
                )
        raise WorkflowAiTargetExecutionFailed("model_stream_interrupted")


async def _stream_model(model: TextStreamingModel, request: ModelRequest) -> str:
    chunks: list[str] = []
    completed = False
    try:
        async for event in model.stream(request):
            if isinstance(event, ModelStreamDelta):
                if completed:
                    raise ModelProviderResponseInvalid
                chunks.append(event.text)
            elif isinstance(event, ModelStreamCompleted):
                if completed:
                    raise ModelProviderResponseInvalid
                completed = True
            else:
                raise ModelProviderResponseInvalid
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
            raise ModelStreamInterrupted
        raise ModelProviderResponseInvalid
    output = "".join(chunks)
    if not output.strip():
        raise ModelProviderResponseInvalid
    return output


def _model_request(prompt: str, state: WorkflowNodeExecutionContext) -> ModelRequest:
    context = state.output or state.user_input
    knowledge = _knowledge_text(state.knowledge)
    if knowledge:
        context = f"用户输入:\n{context}\n\n检索到的知识片段:\n{knowledge}"
    return ModelRequest(
        messages=(
            ModelMessage(
                role=ModelMessageRole.SYSTEM,
                content=f"{prompt}\n\n{KNOWLEDGE_SAFETY_INSTRUCTION}",
            ),
            ModelMessage(role=ModelMessageRole.USER, content=context),
        )
    )


async def _retrieve_knowledge(
    knowledge_bases: KnowledgeBaseService,
    knowledge_base_id: str | None,
    query: str,
) -> tuple[RuntimeKnowledgeChunk, ...]:
    if knowledge_base_id is None:
        return ()
    result = await knowledge_bases.retrieve(
        KnowledgeRetrievalRequest(
            knowledge_base_id=knowledge_base_id,
            query=query,
            top_k=DEFAULT_KNOWLEDGE_TOP_K,
            similarity_threshold=DEFAULT_KNOWLEDGE_SIMILARITY_THRESHOLD,
        )
    )
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


def _knowledge_text(chunks: tuple[RuntimeKnowledgeChunk, ...]) -> str:
    return "\n\n".join(
        f"[知识片段 {position}]\n文档名称: {chunk.document_name}\n"
        f"相关度: {chunk.score}\n片段正文:\n{chunk.content}\n[/知识片段 {position}]"
        for position, chunk in enumerate(chunks, start=1)
    )


__all__ = [
    "StaticWorkflowModelResolver",
    "WorkflowAiTargetExecutor",
    "WorkflowModelResolver",
]
