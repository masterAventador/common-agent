from __future__ import annotations

from common_agent.adapters.model.bailian import BailianChatModelAdapter
from common_agent.bootstrap.settings import ModelSettings
from common_agent.models.base import (
    ModelMessage,
    ModelMessageRole,
    ModelRequest,
    ModelStreamDelta,
)


class BailianModelConfigurationVerifier:
    def __init__(self, settings: ModelSettings) -> None:
        self._settings = settings

    async def verify(self, model_identifier: str) -> str:
        adapter = BailianChatModelAdapter(
            self._settings.model_copy(update={"model": model_identifier})
        )
        chunks: list[str] = []
        try:
            async for event in adapter.stream(
                ModelRequest(
                    messages=(
                        ModelMessage(
                            role=ModelMessageRole.USER,
                            content="请只回复：连接成功",  # noqa: RUF001
                        ),
                    )
                )
            ):
                if isinstance(event, ModelStreamDelta):
                    chunks.append(event.text)
        finally:
            await adapter.aclose()
        return "".join(chunks)


class DemoModelConfigurationVerifier:
    async def verify(self, model_identifier: str) -> str:
        del model_identifier
        return "演示模式模型连接正常"
