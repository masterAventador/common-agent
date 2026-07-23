from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from uuid import UUID

import pytest

from common_agent.domain.conversation import MessageRole
from common_agent.runtimes.base import (
    RUNTIME_HISTORY_MAX_CHARACTERS,
    RUNTIME_HISTORY_MAX_MESSAGES,
    RUNTIME_KNOWLEDGE_MAX_CHUNKS,
    EmployeeRuntime,
    EmployeeRuntimeRequest,
    RuntimeConversationMessage,
    RuntimeEvent,
    RuntimeEventEmitter,
    RuntimeEventKind,
    RuntimeEventTransitionError,
    RuntimeKnowledgeChunk,
    RuntimeStopSignal,
    RuntimeStopToken,
    RuntimeValidationError,
)

_CONVERSATION_ID = UUID("d255c038-1a66-4a85-9f8f-bc202666fab9")
_EMPLOYEE_ID = UUID("57f047c7-6422-4fe8-a77d-bc277c9b6e97")
_USER_MESSAGE_ID = UUID("53e3a7db-c964-4380-b6a4-53e62e290126")
_ASSISTANT_MESSAGE_ID = UUID("30c4824a-869f-4488-a546-e979e99f8f65")
_WORKFLOW_ID = UUID("6c6d0acc-0e34-4c3c-844a-c25381fdb1cf")
_CAPABILITY_ID = UUID("f9bf82c8-fbe1-4ed3-a5c3-f5c74fb35c89")
_TOOL_CALL_ID = UUID("ba307689-eb5d-4ea3-a967-636461af1f2c")


def _history_message(
    *,
    sequence_number: int = 1,
    role: MessageRole = MessageRole.USER,
    content: str = "当前问题",
    message_id: UUID = _USER_MESSAGE_ID,
) -> RuntimeConversationMessage:
    return RuntimeConversationMessage(
        message_id=message_id,
        sequence_number=sequence_number,
        role=role,
        content=content,
    )


def _chunk(
    *,
    knowledge_base_id: str = "kb-1",
    chunk_id: str = "chunk-1",
) -> RuntimeKnowledgeChunk:
    return RuntimeKnowledgeChunk(
        knowledge_base_id=knowledge_base_id,
        chunk_id=chunk_id,
        document_id="document-1",
        document_name="handbook.md",
        content="退款需要在七天内申请。",
        score=0.92,
    )


def _request(**overrides: object) -> EmployeeRuntimeRequest:
    values: dict[str, object] = {
        "conversation_id": _CONVERSATION_ID,
        "employee_id": _EMPLOYEE_ID,
        "assistant_message_id": _ASSISTANT_MESSAGE_ID,
        "assistant_sequence_number": 2,
        "model_identifier": "qwen-plus",
        "system_instruction": "根据上下文准确回答。",
        "history": (_history_message(),),
        "knowledge_base_id": "kb-1",
        "knowledge_context": (_chunk(),),
        "allowed_workflow_ids": (_WORKFLOW_ID,),
    }
    values.update(overrides)
    return EmployeeRuntimeRequest(**values)  # type: ignore[arg-type]


def test_request_keeps_chat_history_instruction_knowledge_and_capabilities_separate() -> None:
    request = _request(streaming_breaks_tool_calls=True)

    assert request.conversation_id == _CONVERSATION_ID
    assert request.employee_id == _EMPLOYEE_ID
    assert request.assistant_message_id == _ASSISTANT_MESSAGE_ID
    assert request.assistant_sequence_number == 2
    assert request.model_identifier == "qwen-plus"
    assert request.system_instruction == "根据上下文准确回答。"
    assert request.history[-1].role is MessageRole.USER
    assert request.history[-1].content == "当前问题"
    assert request.knowledge_base_id == "kb-1"
    assert request.knowledge_context[0].chunk_id == "chunk-1"
    assert request.allowed_workflow_ids == (_WORKFLOW_ID,)
    assert request.streaming_breaks_tool_calls is True


def test_runtime_request_repr_does_not_expose_prompt_history_or_knowledge_content() -> None:
    request = _request()

    rendered = repr(request)
    assert "根据上下文准确回答" not in rendered
    assert "当前问题" not in rendered
    assert "退款需要在七天内申请" not in rendered

    event = RuntimeEventEmitter(_ASSISTANT_MESSAGE_ID).delta("模型敏感输出")
    assert "模型敏感输出" not in repr(event)


@pytest.mark.parametrize(
    "overrides",
    [
        {"conversation_id": "not-a-uuid"},
        {"employee_id": "not-a-uuid"},
        {"assistant_message_id": "not-a-uuid"},
        {"assistant_sequence_number": 0},
        {"model_identifier": "   "},
        {"model_identifier": "qwen plus"},
        {"system_instruction": "   "},
        {"system_instruction": "x" * 12_001},
        {"history": ()},
        {"history": (_history_message(role=MessageRole.ASSISTANT),)},
        {"assistant_sequence_number": 3},
        {"assistant_message_id": _USER_MESSAGE_ID},
        {"history": ("not-a-runtime-message",)},
        {"allowed_workflow_ids": (_WORKFLOW_ID, _WORKFLOW_ID)},
        {"allowed_workflow_ids": ("not-a-uuid",)},
        {"allowed_workflow_ids": tuple(UUID(int=index + 1) for index in range(101))},
        {"streaming_breaks_tool_calls": 1},
        {"allowed_tool_capability_ids": (_CAPABILITY_ID,)},
        {
            "allowed_tool_capability_ids": (_CAPABILITY_ID,),
            "tool_grant_target": "invalid",
        },
        {
            "allowed_tool_capability_ids": tuple(
                UUID(int=index + 1_000) for index in range(501)
            )
        },
        {"allowed_tool_capability_ids": ("not-a-uuid",)},
        {"allowed_tool_capability_ids": (_CAPABILITY_ID, _CAPABILITY_ID)},
    ],
)
def test_request_rejects_invalid_identity_instruction_history_or_capabilities(
    overrides: dict[str, object],
) -> None:
    with pytest.raises(RuntimeValidationError):
        _request(**overrides)


def test_request_requires_strictly_increasing_unique_history() -> None:
    first = _history_message(
        sequence_number=1,
        role=MessageRole.USER,
        content="第一问",
        message_id=UUID("ba0f43a2-a247-454b-9ca1-7437eb75ff61"),
    )
    second = _history_message(
        sequence_number=2,
        role=MessageRole.ASSISTANT,
        content="第一答",
        message_id=UUID("a0aa82a4-f72d-4b7a-aa70-73cb75dfa810"),
    )
    current = _history_message(sequence_number=3)

    request = _request(
        history=(first, second, current),
        assistant_sequence_number=4,
    )
    assert tuple(message.sequence_number for message in request.history) == (1, 2, 3)

    with pytest.raises(RuntimeValidationError, match="history"):
        _request(history=(second, first, current), assistant_sequence_number=4)
    with pytest.raises(RuntimeValidationError, match="history"):
        _request(
            history=(first, _history_message(sequence_number=1)),
            assistant_sequence_number=2,
        )
    with pytest.raises(RuntimeValidationError, match="history"):
        _request(
            history=(first, _history_message(sequence_number=3, message_id=first.message_id)),
            assistant_sequence_number=4,
        )


def test_request_bounds_history_count_and_total_content() -> None:
    too_many = tuple(
        _history_message(
            sequence_number=index,
            content=f"消息 {index}",
            message_id=UUID(int=index),
        )
        for index in range(1, RUNTIME_HISTORY_MAX_MESSAGES + 2)
    )
    with pytest.raises(RuntimeValidationError, match="history"):
        _request(
            history=too_many,
            assistant_sequence_number=RUNTIME_HISTORY_MAX_MESSAGES + 2,
        )

    part_length = RUNTIME_HISTORY_MAX_CHARACTERS // 3 + 1
    oversized = tuple(
        _history_message(
            sequence_number=index,
            content="x" * part_length,
            message_id=UUID(int=index + 1_000),
        )
        for index in range(1, 4)
    )
    with pytest.raises(RuntimeValidationError, match="history"):
        _request(history=oversized, assistant_sequence_number=4)


def test_request_distinguishes_unbound_empty_result_and_retrieved_context() -> None:
    unbound = _request(knowledge_base_id=None, knowledge_context=())
    empty_result = _request(knowledge_context=())

    assert unbound.knowledge_base_id is None
    assert empty_result.knowledge_base_id == "kb-1"
    assert empty_result.knowledge_context == ()

    with pytest.raises(RuntimeValidationError, match="knowledge_context"):
        _request(knowledge_base_id=None, knowledge_context=(_chunk(),))
    with pytest.raises(RuntimeValidationError, match="knowledge_context"):
        _request(knowledge_context=(_chunk(knowledge_base_id="kb-2"),))
    with pytest.raises(RuntimeValidationError, match="knowledge_context"):
        _request(knowledge_context=(_chunk(), _chunk()))
    with pytest.raises(RuntimeValidationError, match="knowledge_context"):
        _request(knowledge_context=("not-a-knowledge-chunk",))


@pytest.mark.parametrize(
    ("role", "content"),
    [("user", "valid"), (MessageRole.USER, 1)],
)
def test_runtime_message_rejects_invalid_role_or_content(
    role: object,
    content: object,
) -> None:
    with pytest.raises(RuntimeValidationError):
        RuntimeConversationMessage(
            message_id=_USER_MESSAGE_ID,
            sequence_number=1,
            role=role,  # type: ignore[arg-type]
            content=content,  # type: ignore[arg-type]
        )


def test_request_bounds_knowledge_context() -> None:
    chunks = tuple(
        _chunk(chunk_id=f"chunk-{index}") for index in range(RUNTIME_KNOWLEDGE_MAX_CHUNKS + 1)
    )

    with pytest.raises(RuntimeValidationError, match="knowledge_context"):
        _request(knowledge_context=chunks)


@pytest.mark.parametrize(
    "values",
    [
        {"sequence": 0, "kind": RuntimeEventKind.DELTA, "delta": "内容"},
        {"sequence": 1, "kind": "delta", "delta": "内容"},
        {"sequence": 1, "kind": RuntimeEventKind.DELTA, "delta": None},
        {"sequence": 1, "kind": RuntimeEventKind.DELTA, "delta": ""},
        {
            "sequence": 1,
            "kind": RuntimeEventKind.DELTA,
            "delta": "内容",
            "error_code": "wrong",
        },
        {
            "sequence": 1,
            "kind": RuntimeEventKind.DELTA,
            "delta": "内容",
            "tool_call_id": _TOOL_CALL_ID,
        },
        {
            "sequence": 1,
            "kind": RuntimeEventKind.TOOL_STARTED,
            "delta": "wrong",
            "tool_call_id": _TOOL_CALL_ID,
            "capability_id": _CAPABILITY_ID,
            "capability_name": "当前时间",
        },
        {
            "sequence": 1,
            "kind": RuntimeEventKind.TOOL_STARTED,
            "error_code": "wrong",
            "tool_call_id": _TOOL_CALL_ID,
            "capability_id": _CAPABILITY_ID,
            "capability_name": "当前时间",
        },
        {"sequence": 1, "kind": RuntimeEventKind.COMPLETED, "delta": "多余"},
        {"sequence": 1, "kind": RuntimeEventKind.FAILED, "error_code": None},
        {"sequence": 1, "kind": RuntimeEventKind.STOPPED, "error_code": "wrong"},
    ],
)
def test_runtime_event_rejects_invalid_payload_combinations(values: dict[str, object]) -> None:
    with pytest.raises(RuntimeValidationError):
        RuntimeEvent(assistant_message_id=_ASSISTANT_MESSAGE_ID, **values)  # type: ignore[arg-type]


def test_event_emitter_produces_monotonic_stream_with_exactly_one_terminal_event() -> None:
    emitter = RuntimeEventEmitter(_ASSISTANT_MESSAGE_ID)

    first = emitter.delta("你")
    second = emitter.delta("好")
    completed = emitter.complete()

    assert [first.sequence, second.sequence, completed.sequence] == [1, 2, 3]
    assert [first.kind, second.kind, completed.kind] == [
        RuntimeEventKind.DELTA,
        RuntimeEventKind.DELTA,
        RuntimeEventKind.COMPLETED,
    ]
    assert emitter.is_terminal is True
    with pytest.raises(RuntimeEventTransitionError):
        emitter.delta("晚到内容")
    with pytest.raises(RuntimeEventTransitionError):
        emitter.stop()


def test_event_emitter_keeps_tool_lifecycle_metadata_only_and_non_terminal() -> None:
    emitter = RuntimeEventEmitter(_ASSISTANT_MESSAGE_ID)

    started = emitter.tool_started(
        tool_call_id=_TOOL_CALL_ID,
        capability_id=_CAPABILITY_ID,
        capability_name="当前时间",
    )
    completed = emitter.tool_completed(
        tool_call_id=_TOOL_CALL_ID,
        capability_id=_CAPABILITY_ID,
        capability_name="当前时间",
    )
    failed = emitter.tool_failed(
        tool_call_id=UUID(int=99),
        capability_id=_CAPABILITY_ID,
        capability_name="当前时间",
        error_code="tool_execution_failed",
    )
    terminal = emitter.complete()

    assert [event.sequence for event in (started, completed, failed, terminal)] == [1, 2, 3, 4]
    assert [event.kind for event in (started, completed, failed)] == [
        RuntimeEventKind.TOOL_STARTED,
        RuntimeEventKind.TOOL_COMPLETED,
        RuntimeEventKind.TOOL_FAILED,
    ]
    assert started.capability_id == _CAPABILITY_ID
    assert started.capability_name == "当前时间"
    assert started.tool_call_id == _TOOL_CALL_ID
    assert failed.error_code == "tool_execution_failed"
    assert not hasattr(started, "arguments")
    assert not hasattr(completed, "output")


def test_event_emitter_failed_and_stopped_are_distinct_terminal_states() -> None:
    failed = RuntimeEventEmitter(_ASSISTANT_MESSAGE_ID).fail("model_unavailable")
    stopped = RuntimeEventEmitter(_ASSISTANT_MESSAGE_ID).stop()

    assert failed.kind is RuntimeEventKind.FAILED
    assert failed.error_code == "model_unavailable"
    assert stopped.kind is RuntimeEventKind.STOPPED
    assert stopped.error_code is None


def test_stop_token_is_idempotent_and_wakes_waiters() -> None:
    async def exercise() -> None:
        token = RuntimeStopToken()
        assert isinstance(token, RuntimeStopSignal)
        assert token.is_requested is False
        waiter = asyncio.create_task(token.wait())
        await asyncio.sleep(0)

        assert token.request_stop() is True
        assert token.request_stop() is False
        await asyncio.wait_for(waiter, timeout=0.1)
        assert token.is_requested is True

    asyncio.run(exercise())


def test_employee_runtime_protocol_is_one_chat_response_not_a_task_api() -> None:
    class _Runtime:
        async def aclose(self) -> None:
            return None

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
            yield emitter.delta("回复")
            yield emitter.complete()

    runtime = _Runtime()
    assert isinstance(runtime, EmployeeRuntime)
    assert not hasattr(runtime, "start")
    assert not hasattr(runtime, "approve")

    async def exercise() -> None:
        events = [event async for event in runtime.stream(_request(), stop=RuntimeStopToken())]
        assert [event.kind for event in events] == [
            RuntimeEventKind.DELTA,
            RuntimeEventKind.COMPLETED,
        ]

    asyncio.run(exercise())
