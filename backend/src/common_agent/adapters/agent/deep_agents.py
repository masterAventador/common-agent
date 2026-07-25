from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, Protocol, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from deepagents import (
    GeneralPurposeSubagentProfile,
    HarnessProfile,
    create_deep_agent,
    register_harness_profile,
)
from deepagents.backends import StateBackend
from deepagents.middleware.filesystem import FilesystemPermission
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage
from langchain_core.tools import BaseTool

from common_agent.adapters.agent.tool_metadata import (
    TOOL_METADATA_CAPABILITY_ID,
    TOOL_METADATA_CAPABILITY_NAME,
)
from common_agent.adapters.model.bailian import REASONING_CONTENT_KEY
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
from common_agent.tools.models import ToolCallErrorCode, ToolGrantTarget

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
_LOGGER = logging.getLogger("common_agent.adapters.agent.deep_agents")
_DEEP_AGENT_EXECUTION_FAILED = "deep_agent_execution_failed"
_PLATFORM_SAFETY_INSTRUCTION = (
    "只能使用当前请求明确提供的工具;不得尝试访问本机文件、执行 Shell、创建子代理或修改待办。"
)
_HARNESS_BASE_PROMPT = "你是通用 Agent 中台中的聊天式数字员工。直接在当前会话中回答用户。"

# 这三段中间件会各自往系统提示词里注入一大段英文说明(待办清单、文件读写、子代理)。它们对应的
# 工具已经全部禁用, 说明留着有两个害处: 模型会对用户吹嘘自己能读写文件、管待办这些根本没有的
# 能力; 上万字符的英文上下文还会把中文提问的模型带成用英文思考。用库自己的公开开关排掉。
# 文件系统与子代理两段被库判定为必需骨架, 不允许排除; 待办清单可以。
_EXCLUDED_HARNESS_MIDDLEWARE = frozenset({"TodoListMiddleware"})

# 排掉待办后, Deep Agents 仍会注入约六千字符的英文骨架说明(文件读写、子代理), 这些工具在本平台
# 一律不可用。放在系统提示词末尾的收尾指令用于纠正两件事: 模型据此对用户吹嘘自己能读写文件,
# 以及被大段英文上下文带成用英文思考。末尾是提示词里最显著的位置。
_HARNESS_PROMPT_SUFFIX = (
    "以上英文段落来自底层框架的通用说明。其中提到的文件读写、待办清单、子代理等能力"
    "在本平台一律不可用, 不要使用, 也不要向用户声称自己具备这些能力。\n"
    "无论用户使用何种语言提问, 你的思考过程和最终回答都必须使用简体中文。"
)


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
        workflow_ids: Sequence[UUID],
        *,
        tool_capability_ids: Sequence[UUID] = (),
        tool_grant_target: ToolGrantTarget | None = None,
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
        workflow_ids: Sequence[UUID],
        *,
        tool_capability_ids: Sequence[UUID] = (),
        tool_grant_target: ToolGrantTarget | None = None,
        origin: WorkflowRunOrigin | None,
    ) -> tuple[BaseTool, ...]:
        del origin, tool_grant_target
        resolved: list[BaseTool] = []
        for capability_id in (*workflow_ids, *tool_capability_ids):
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


@dataclass(frozen=True, slots=True)
class _ToolMetadata:
    capability_id: UUID
    capability_name: str


@dataclass(frozen=True, slots=True)
class _ToolLifecycle:
    kind: str
    tool_call_id: UUID
    metadata: _ToolMetadata
    error_code: str | None = None


class _StaticModelResolver:
    def __init__(self, model: LangChainChatModelProvider) -> None:
        self._model = model

    async def resolve(
        self,
        model_identifier: str,
        *,
        disable_streaming_for_tool_calls: bool = False,
        deep_thinking: bool | None = None,
    ) -> LangChainChatModelProvider:
        del model_identifier
        del disable_streaming_for_tool_calls
        del deep_thinking
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
                excluded_middleware=_EXCLUDED_HARNESS_MIDDLEWARE,
                system_prompt_suffix=_HARNESS_PROMPT_SUFFIX,
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
        active_tool_calls: dict[str, _ToolMetadata] = {}
        finished_tool_calls: set[str] = set()
        tool_metadata: dict[str, _ToolMetadata] = {}
        try:
            allowed_tools = await self._tools.resolve(
                request.allowed_workflow_ids,
                tool_capability_ids=request.allowed_tool_capability_ids,
                tool_grant_target=request.tool_grant_target,
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
            model = await self._models.resolve(
                request.model_identifier,
                disable_streaming_for_tool_calls=(
                    request.streaming_breaks_tool_calls and bool(allowed_tools)
                ),
                deep_thinking=request.deep_thinking,
            )
            tool_metadata = _resolved_tool_metadata(allowed_tools)
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
            _LOGGER.exception("数字员工运行时装配失败")
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
        pending_reasoning = ""
        upstream_closed = False
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
                    upstream_closed = True
                    await _close_iterator(upstream)
                    for lifecycle in _unfinished_tool_calls(
                        active_tool_calls,
                        assistant_message_id=request.assistant_message_id,
                        error_code=ToolCallErrorCode.RESULT_UNKNOWN.value,
                    ):
                        yield emitter.tool_failed(
                            tool_call_id=lifecycle.tool_call_id,
                            capability_id=lifecycle.metadata.capability_id,
                            capability_name=lifecycle.metadata.capability_name,
                            error_code=(
                                lifecycle.error_code or ToolCallErrorCode.RESULT_UNKNOWN.value
                            ),
                        )
                    yield emitter.stop()
                    return

                await _discard_task(stop_task)
                stop_task = None
                active_task = next_task
                next_task = None
                try:
                    item = active_task.result()
                except StopAsyncIteration:
                    if active_tool_calls:
                        for lifecycle in _unfinished_tool_calls(
                            active_tool_calls,
                            assistant_message_id=request.assistant_message_id,
                            error_code=ToolCallErrorCode.PROTOCOL_ERROR.value,
                        ):
                            yield emitter.tool_failed(
                                tool_call_id=lifecycle.tool_call_id,
                                capability_id=lifecycle.metadata.capability_id,
                                capability_name=lifecycle.metadata.capability_name,
                                error_code=(
                                    lifecycle.error_code
                                    or ToolCallErrorCode.PROTOCOL_ERROR.value
                                ),
                            )
                        yield emitter.fail(ModelProviderResponseInvalid.code)
                        return
                    if emitted_delta:
                        yield emitter.complete()
                    else:
                        yield emitter.fail(ModelProviderResponseInvalid.code)
                    return

                for lifecycle in _tool_lifecycle(
                    item,
                    tool_metadata=tool_metadata,
                    active=active_tool_calls,
                    finished=finished_tool_calls,
                    assistant_message_id=request.assistant_message_id,
                ):
                    if lifecycle.kind == "started":
                        yield emitter.tool_started(
                            tool_call_id=lifecycle.tool_call_id,
                            capability_id=lifecycle.metadata.capability_id,
                            capability_name=lifecycle.metadata.capability_name,
                        )
                    elif lifecycle.kind == "completed":
                        yield emitter.tool_completed(
                            tool_call_id=lifecycle.tool_call_id,
                            capability_id=lifecycle.metadata.capability_id,
                            capability_name=lifecycle.metadata.capability_name,
                        )
                    else:
                        yield emitter.tool_failed(
                            tool_call_id=lifecycle.tool_call_id,
                            capability_id=lifecycle.metadata.capability_id,
                            capability_name=lifecycle.metadata.capability_name,
                            error_code=(
                                lifecycle.error_code or ToolCallErrorCode.EXECUTION_FAILED.value
                            ),
                        )
                # 思考内容与正文分开产出: 它不计入"是否给出了回复", 界面上单独折叠展示。
                # 思考流里会夹纯换行的分片, 运行时事件不收纯空白文本, 因此与正文一样先攒着,
                # 攒到有实际内容再一起发, 换行才不会丢。
                pending_reasoning += _agent_reasoning(item)
                if pending_reasoning.strip():
                    yield emitter.reasoning(pending_reasoning)
                    pending_reasoning = ""
                pending_text += _agent_text(item)
                if pending_text.strip():
                    emitted_delta = True
                    yield emitter.delta(pending_text)
                    pending_text = ""
        except asyncio.CancelledError:
            raise
        except Exception as error:
            for lifecycle in _unfinished_tool_calls(
                active_tool_calls,
                assistant_message_id=request.assistant_message_id,
                error_code=ToolCallErrorCode.RESULT_UNKNOWN.value,
            ):
                yield emitter.tool_failed(
                    tool_call_id=lifecycle.tool_call_id,
                    capability_id=lifecycle.metadata.capability_id,
                    capability_name=lifecycle.metadata.capability_name,
                    error_code=lifecycle.error_code or ToolCallErrorCode.RESULT_UNKNOWN.value,
                )
            _LOGGER.exception("数字员工运行时执行失败")
            if model is None:
                yield emitter.fail(_DEEP_AGENT_EXECUTION_FAILED)
            else:
                yield emitter.fail(_safe_error_code(model, error, emitted_delta=emitted_delta))
        finally:
            await _discard_task(next_task)
            await _discard_task(stop_task)
            if not upstream_closed:
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


def _agent_reasoning(item: object) -> str:
    """取出模型的思考增量。

    百炼 compatible-mode 会返回 reasoning_content, 由本项目的 ChatOpenAI 子类挂到
    additional_kwargs 上; 不返回思考内容的模型这里自然为空。
    """
    if not isinstance(item, tuple) or len(item) != 2:
        return ""
    message, _metadata = item
    if not isinstance(message, (AIMessage, AIMessageChunk)):
        return ""
    reasoning = message.additional_kwargs.get(REASONING_CONTENT_KEY)
    return reasoning if isinstance(reasoning, str) and reasoning else ""


def _resolved_tool_metadata(tools: Sequence[BaseTool]) -> dict[str, _ToolMetadata]:
    resolved: dict[str, _ToolMetadata] = {}
    for tool in tools:
        metadata = tool.metadata or {}
        raw_capability_id = metadata.get(TOOL_METADATA_CAPABILITY_ID)
        raw_capability_name = metadata.get(TOOL_METADATA_CAPABILITY_NAME)
        if raw_capability_id is None and raw_capability_name is None:
            continue
        try:
            capability_id = UUID(str(raw_capability_id))
        except (TypeError, ValueError):
            raise DeepAgentToolRegistryValidationError("工具能力元数据 ID 不合法") from None
        if (
            not isinstance(raw_capability_name, str)
            or not raw_capability_name.strip()
            or raw_capability_name != raw_capability_name.strip()
        ):
            raise DeepAgentToolRegistryValidationError("工具能力元数据名称不合法")
        resolved[tool.name] = _ToolMetadata(capability_id, raw_capability_name)
    return resolved


def _tool_lifecycle(
    item: object,
    *,
    tool_metadata: Mapping[str, _ToolMetadata],
    active: dict[str, _ToolMetadata],
    finished: set[str],
    assistant_message_id: UUID,
) -> tuple[_ToolLifecycle, ...]:
    if not isinstance(item, tuple) or len(item) != 2:
        return ()
    message, _metadata = item
    lifecycle: list[_ToolLifecycle] = []
    if isinstance(message, (AIMessage, AIMessageChunk)):
        raw_calls = cast(Sequence[Mapping[str, object]], message.tool_calls)
        if isinstance(message, AIMessageChunk):
            raw_calls = (
                *raw_calls,
                *cast(Sequence[Mapping[str, object]], message.tool_call_chunks),
            )
        for raw_call in raw_calls:
            raw_name = raw_call.get("name")
            raw_id = raw_call.get("id")
            if not isinstance(raw_name, str) or not isinstance(raw_id, str) or not raw_id:
                continue
            metadata = tool_metadata.get(raw_name)
            if metadata is None or raw_id in active or raw_id in finished:
                continue
            active[raw_id] = metadata
            lifecycle.append(
                _ToolLifecycle(
                    kind="started",
                    tool_call_id=_tool_call_id(assistant_message_id, raw_id),
                    metadata=metadata,
                )
            )
        return tuple(lifecycle)
    if not isinstance(message, ToolMessage):
        return ()
    raw_id = message.tool_call_id
    if not raw_id or raw_id in finished:
        return ()
    metadata = active.pop(raw_id, None)
    if metadata is None and isinstance(message.name, str):
        metadata = tool_metadata.get(message.name)
        if metadata is not None:
            lifecycle.append(
                _ToolLifecycle(
                    kind="started",
                    tool_call_id=_tool_call_id(assistant_message_id, raw_id),
                    metadata=metadata,
                )
            )
    if metadata is None:
        return ()
    finished.add(raw_id)
    status = getattr(message, "status", "success")
    lifecycle.append(
        _ToolLifecycle(
            kind="failed" if status == "error" else "completed",
            tool_call_id=_tool_call_id(assistant_message_id, raw_id),
            metadata=metadata,
            error_code=(_tool_error_code(message.content) if status == "error" else None),
        )
    )
    return tuple(lifecycle)


def _tool_error_code(content: object) -> str:
    rendered = content if isinstance(content, str) else ""
    for code in ToolCallErrorCode:
        if f"错误码:{code.value}" in rendered:
            return code.value
    return ToolCallErrorCode.EXECUTION_FAILED.value


def _unfinished_tool_calls(
    active: dict[str, _ToolMetadata],
    *,
    assistant_message_id: UUID,
    error_code: str,
) -> tuple[_ToolLifecycle, ...]:
    pending = tuple(
        _ToolLifecycle(
            kind="failed",
            tool_call_id=_tool_call_id(assistant_message_id, raw_id),
            metadata=metadata,
            error_code=error_code,
        )
        for raw_id, metadata in active.items()
    )
    active.clear()
    return pending


def _tool_call_id(assistant_message_id: UUID, provider_call_id: str) -> UUID:
    return uuid5(
        NAMESPACE_URL,
        f"common-agent:{assistant_message_id}:tool-call:{provider_call_id}",
    )


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
