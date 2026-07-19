from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence

from langchain_core.messages import BaseMessage, HumanMessage

from common_agent.models.base import ModelServiceError


class DemoWorkflowModel:
    provider_name = "demo"

    async def stream_text(self, messages: Sequence[BaseMessage]) -> AsyncIterator[str]:
        user_text = next(
            (message.text for message in reversed(messages) if isinstance(message, HumanMessage)),
            "",
        )
        response = f"演示工作流结果: {user_text}"
        for position in range(0, len(response), 4):
            await asyncio.sleep(0.01)
            yield response[position : position + 4]

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
