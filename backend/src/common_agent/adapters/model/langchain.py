from __future__ import annotations

from typing import Protocol, runtime_checkable

from langchain_core.language_models.chat_models import BaseChatModel

from common_agent.models.base import TextStreamingModel


@runtime_checkable
class LangChainChatModelProvider(TextStreamingModel, Protocol):
    """Adapter-only bridge required by Deep Agents.

    Platform consumers must depend on ``TextStreamingModel`` instead. This bridge keeps the
    LangChain object inside the adapter layer while Deep Agents still requires its native model.
    """

    @property
    def langchain_chat_model(self) -> BaseChatModel: ...


class LangChainChatModelResolver(Protocol):
    async def resolve(self, model_identifier: str) -> LangChainChatModelProvider: ...

    async def aclose(self) -> None: ...
