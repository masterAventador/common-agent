from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from common_agent.models.base import (
    ModelMessageRole,
    ModelRequest,
    ModelServiceError,
    ModelStreamCompleted,
    ModelStreamDelta,
    ModelStreamEvent,
)


class DemoWorkflowModel:
    provider_name = "demo"

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamEvent]:
        user_text = next(
            (
                message.content
                for message in reversed(request.messages)
                if message.role is ModelMessageRole.USER
            ),
            "",
        )
        response = f"演示工作流结果: {user_text}"
        for position in range(0, len(response), 4):
            await asyncio.sleep(0.01)
            yield ModelStreamDelta(text=response[position : position + 4])
        yield ModelStreamCompleted()

    @staticmethod
    def translate_error(
        error: Exception,
        *,
        stream_started: bool,
    ) -> ModelServiceError | None:
        del error, stream_started
        return None

    async def aclose(self) -> None:
        pass
