from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from contextlib import suppress
from typing import Any, Protocol, cast
from uuid import UUID

from deepagents import (
    GeneralPurposeSubagentProfile,
    HarnessProfile,
    create_deep_agent,
    register_harness_profile,
)
from deepagents.backends import StateBackend
from deepagents.middleware.filesystem import FilesystemPermission
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from langchain_core.tools import BaseTool

from common_agent.adapters.model.langchain import (
    LangChainChatModelProvider,
    LangChainChatModelResolver,
)
from common_agent.domain.conversation import MessageRole
from common_agent.domain.workflow_run import WorkflowRunOrigin
from common_agent.models.base import (
    ModelProviderResponseInvalid,
    ModelServiceError,
    ModelStreamInterrupted,
)
from common_agent.models.prompts import KNOWLEDGE_SAFETY_INSTRUCTION
from common_agent.runtimes.base import (
    EmployeeRuntimeRequest,
    RuntimeEvent,
    RuntimeEventEmitter,
    RuntimeStopSignal,
)

DEEP_AGENT_BUILTIN_TOOL_NAMES = frozenset(
    {
        "write_todos",
        "ls",
        "read_file",
        "write_file",
        "edit_file",
        "glob",
        "grep",
        "execute",
        "task",
    }
)
_DEEP_AGENT_EXECUTION_FAILED = "deep_agent_execution_failed"
_PLATFORM_SAFETY_INSTRUCTION = (
    "只能使用当前请求明确提供的工具;不得尝试访问本机文件、执行 Shell、创建子代理或修改待办。"
)
_HARNESS_BASE_PROMPT = "你是通用 Agent 中台中的聊天式数字员工。直接在当前会话中回答用户。"


class DeepAgentToolRegistryValidationError(ValueError):
    pass


class RuntimeCapabilityUnavailable(Exception):
    code = "runtime_capability_unavailable"
    retryable = False

    def __init__(self) -> None:
        super().__init__("数字员工请求了未注册或未授权的平台能力")


class DeepAgentToolResolver(Protocol):
    async def resolve(
        self,
        capability_ids: Sequence[UUID],
        *,
        origin: WorkflowRunOrigin | None,
    ) -> tuple[BaseTool, ...]: ...


class DeepAgentToolRegistry:
    def __init__(self, tools: Mapping[UUID, BaseTool] | None = None) -> None:
        registered = dict(tools or {})
        names: set[str] = set()
        for capability_id, registered_tool in registered.items():
            if not isinstance(capability_id, UUID):
                raise DeepAgentToolRegistryValidationError("能力 ID 必须是 UUID")
            if not isinstance(registered_tool, BaseTool):
                raise DeepAgentToolRegistryValidationError("能力必须注册为 LangChain BaseTool")
            if registered_tool.name in DEEP_AGENT_BUILTIN_TOOL_NAMES:
                raise DeepAgentToolRegistryValidationError("能力名称与 Deep Agents 保留工具冲突")
            if registered_tool.name in names:
                raise DeepAgentToolRegistryValidationError("能力名称不能重复")
            names.add(registered_tool.name)
        self._tools = registered

    async def resolve(
        self,
        capability_ids: Sequence[UUID],
        *,
        origin: WorkflowRunOrigin | None,
    ) -> tuple[BaseTool, ...]:
        del origin
        resolved: list[BaseTool] = []
        for capability_id in capability_ids:
            registered_tool = self._tools.get(capability_id)
            if registered_tool is None:
                raise RuntimeCapabilityUnavailable()
            resolved.append(registered_tool)
        return tuple(resolved)


class _AgentGraph(Protocol):
    def astream(
        self,
        input_data: Mapping[str, object],
        config: Mapping[str, object],
        *,
        stream_mode: str,
    ) -> AsyncIterator[object]: ...


AgentBuilder = Callable[..., object]


class _StaticModelResolver:
    def __init__(self, model: LangChainChatModelProvider) -> None:
        self._model = model

    async def resolve(self, model_identifier: str) -> LangChainChatModelProvider:
        del model_identifier
        return self._model

    async def aclose(self) -> None:
        await self._model.aclose()


class DeepAgentsEmployeeRuntime:
    def __init__(
        self,
        models: LangChainChatModelResolver | LangChainChatModelProvider,
        *,
        tools: DeepAgentToolResolver | None = None,
        harness_profile_key: str = "openai",
        agent_builder: AgentBuilder = create_deep_agent,
    ) -> None:
        self._models = (
            _StaticModelResolver(models)
            if isinstance(models, LangChainChatModelProvider)
            else models
        )
        self._tools = tools or DeepAgentToolRegistry()
        self._agent_builder = agent_builder
        self._closed = False
        register_harness_profile(
            harness_profile_key,
            HarnessProfile(
                base_system_prompt=_HARNESS_BASE_PROMPT,
                excluded_tools=DEEP_AGENT_BUILTIN_TOOL_NAMES,
                general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False),
            ),
        )

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self._models.aclose()

    async def stream(
        self,
        request: EmployeeRuntimeRequest,
        *,
        stop: RuntimeStopSignal,
    ) -> AsyncIterator[RuntimeEvent]:
        emitter = RuntimeEventEmitter(request.assistant_message_id)
        if stop.is_requested:
            yield emitter.stop()
            return

        model: LangChainChatModelProvider | None = None
        try:
            model = await self._models.resolve(request.model_identifier)
            allowed_tools = await self._tools.resolve(
                request.allowed_workflow_ids,
                origin=(
                    None
                    if request.workflow_run_id is not None
                    else WorkflowRunOrigin(
                        employee_id=request.employee_id,
                        conversation_id=request.conversation_id,
                        assistant_message_id=request.assistant_message_id,
                    )
                ),
            )
            graph = cast(
                "_AgentGraph",
                self._agent_builder(
                    model=model.langchain_chat_model,
                    tools=allowed_tools,
                    system_prompt=_system_prompt(request),
                    backend=StateBackend(),
                    permissions=[
                        FilesystemPermission(
                            operations=["read", "write"],
                            paths=["/**"],
                            mode="deny",
                        )
                    ],
                    skills=[],
                    memory=[],
                    subagents=[],
                ),
            )
        except RuntimeCapabilityUnavailable as error:
            yield emitter.fail(error.code)
            return
        except Exception:
            yield emitter.fail(_DEEP_AGENT_EXECUTION_FAILED)
            return

        upstream = graph.astream(
            {"messages": _history_messages(request)},
            {
                "configurable": {
                    "thread_id": str(request.workflow_run_id or request.conversation_id)
                },
                "metadata": {
                    "conversation_id": str(request.conversation_id),
                    "employee_id": str(request.employee_id),
                    "workflow_run_id": (
                        None if request.workflow_run_id is None else str(request.workflow_run_id)
                    ),
                },
            },
            stream_mode="messages",
        )
        next_task: asyncio.Task[object] | None = None
        stop_task: asyncio.Task[None] | None = None
        emitted_delta = False
        pending_text = ""
        try:
            while True:
                next_task = asyncio.create_task(_next_item(upstream))
                stop_task = asyncio.create_task(stop.wait())
                done, _ = await asyncio.wait(
                    {next_task, stop_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )

                if stop_task in done:
                    await _discard_task(next_task)
                    next_task = None
                    await _discard_task(stop_task)
                    stop_task = None
                    await _close_iterator(upstream)
                    yield emitter.stop()
                    return

                await _discard_task(stop_task)
                stop_task = None
                active_task = next_task
                next_task = None
                try:
                    item = active_task.result()
                except StopAsyncIteration:
                    if emitted_delta:
                        yield emitter.complete()
                    else:
                        yield emitter.fail(ModelProviderResponseInvalid.code)
                    return

                pending_text += _agent_text(item)
                if pending_text.strip():
                    emitted_delta = True
                    yield emitter.delta(pending_text)
                    pending_text = ""
        except asyncio.CancelledError:
            raise
        except Exception as error:
            if model is None:
                yield emitter.fail(_DEEP_AGENT_EXECUTION_FAILED)
            else:
                yield emitter.fail(_safe_error_code(model, error, emitted_delta=emitted_delta))
        finally:
            await _discard_task(next_task)
            await _discard_task(stop_task)
            await _close_iterator(upstream)


def _history_messages(request: EmployeeRuntimeRequest) -> list[HumanMessage | AIMessage]:
    messages: list[HumanMessage | AIMessage] = []
    for message in request.history:
        if message.role is MessageRole.USER:
            messages.append(HumanMessage(content=message.content))
        else:
            messages.append(AIMessage(content=message.content))
    return messages


def _system_prompt(request: EmployeeRuntimeRequest) -> str:
    sections = [
        request.system_instruction,
        _PLATFORM_SAFETY_INSTRUCTION,
        KNOWLEDGE_SAFETY_INSTRUCTION,
    ]
    if request.knowledge_base_id is None:
        sections.append("当前数字员工未绑定知识库。")
    elif not request.knowledge_context:
        sections.append("当前问题已检索绑定知识库,但没有命中相关知识片段。")
    else:
        fragments = []
        for position, chunk in enumerate(request.knowledge_context, start=1):
            fragments.append(
                "\n".join(
                    (
                        f"[知识片段 {position}]",
                        f"知识库 ID: {chunk.knowledge_base_id}",
                        f"文档 ID: {chunk.document_id}",
                        f"片段 ID: {chunk.chunk_id}",
                        f"文档名称: {chunk.document_name}",
                        f"相关度: {chunk.score}",
                        "片段正文:",
                        chunk.content,
                        f"[/知识片段 {position}]",
                    )
                )
            )
        sections.append("以下是本轮检索到的知识片段:\n\n" + "\n\n".join(fragments))
    return "\n\n".join(sections)


def _agent_text(item: object) -> str:
    if not isinstance(item, tuple) or len(item) != 2:
        return ""
    message, _metadata = item
    if not isinstance(message, (AIMessage, AIMessageChunk)):
        return ""
    return message.text


def _safe_error_code(
    model: LangChainChatModelProvider,
    error: Exception,
    *,
    emitted_delta: bool,
) -> str:
    if emitted_delta:
        return ModelStreamInterrupted.code
    if isinstance(error, ModelServiceError):
        return error.code
    try:
        translated = model.translate_error(error, stream_started=False)
    except Exception:
        return _DEEP_AGENT_EXECUTION_FAILED
    return translated.code if translated is not None else _DEEP_AGENT_EXECUTION_FAILED


async def _next_item(iterator: AsyncIterator[object]) -> object:
    return await anext(iterator)


async def _discard_task(task: asyncio.Task[Any] | None) -> None:
    if task is None:
        return
    if not task.done():
        task.cancel()
    with suppress(asyncio.CancelledError, Exception):
        await task


async def _close_iterator(iterator: AsyncIterator[object]) -> None:
    close = getattr(iterator, "aclose", None)
    if close is not None:
        await close()
