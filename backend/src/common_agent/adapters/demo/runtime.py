from __future__ import annotations

from collections import defaultdict
from collections.abc import AsyncIterator
from uuid import UUID

from common_agent.domain.conversation import MessageRole
from common_agent.runtimes.base import (
    EmployeeRuntimeRequest,
    RuntimeEvent,
    RuntimeEventEmitter,
    RuntimeStopSignal,
)

_INTERRUPTION_TRIGGER = "演示一次断流后恢复"


class DemoEmployeeRuntime:
    def __init__(self) -> None:
        self._attempts: defaultdict[UUID, int] = defaultdict(int)
        self._closed = False

    async def stream(
        self,
        request: EmployeeRuntimeRequest,
        *,
        stop: RuntimeStopSignal,
    ) -> AsyncIterator[RuntimeEvent]:
        if self._closed:
            raise RuntimeError("demo employee runtime is closed")
        emitter = RuntimeEventEmitter(request.assistant_message_id)
        if stop.is_requested:
            yield emitter.stop()
            return

        self._attempts[request.assistant_message_id] += 1
        current_question = request.history[-1].content
        if (
            _INTERRUPTION_TRIGGER in current_question
            and self._attempts[request.assistant_message_id] == 1
        ):
            yield emitter.delta("这是断流前保留的演示内容。")
            return

        user_turn = sum(message.role is MessageRole.USER for message in request.history)
        answer = f"这是演示模式第 {user_turn} 轮固定回答。"
        if user_turn > 1:
            answer += "我记得上一轮对话,并继续回答当前问题。"
        if request.knowledge_context:
            document_names = "、".join(
                dict.fromkeys(chunk.document_name for chunk in request.knowledge_context)
            )
            answer += f"本轮依据知识库文档 {document_names}。"
        midpoint = max(1, len(answer) // 2)
        for part in (answer[:midpoint], answer[midpoint:]):
            if not part:
                continue
            if stop.is_requested:
                yield emitter.stop()
                return
            yield emitter.delta(part)
        if stop.is_requested:
            yield emitter.stop()
            return
        yield emitter.complete()

    async def aclose(self) -> None:
        self._closed = True
        self._attempts.clear()
