from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from common_agent.domain.knowledge import (
    KnowledgeServiceAvailability,
    KnowledgeServiceStatus,
)
from common_agent.knowledge.base import KnowledgeService


class ModelConfigurationStatus(StrEnum):
    CONFIGURED = "configured"
    DEMO = "demo"


@dataclass(frozen=True, slots=True)
class ModelDependencyStatus:
    provider: str
    status: ModelConfigurationStatus


@dataclass(frozen=True, slots=True)
class SystemStatusSnapshot:
    integration_mode: Literal["real", "demo"]
    model: ModelDependencyStatus
    knowledge: KnowledgeServiceStatus


class SystemService:
    def __init__(
        self,
        *,
        integration_mode: Literal["real", "demo"],
        model_provider: str,
        knowledge: KnowledgeService,
    ) -> None:
        self._integration_mode = integration_mode
        self._model_provider = model_provider
        self._knowledge = knowledge

    async def status(self) -> SystemStatusSnapshot:
        try:
            knowledge_status = await self._knowledge.status()
        except Exception:
            knowledge_status = KnowledgeServiceStatus(
                provider=self._knowledge.provider_name,
                availability=KnowledgeServiceAvailability.UNAVAILABLE,
                version=None,
                error_code="knowledge_service_unavailable",
            )
        model_status = (
            ModelConfigurationStatus.DEMO
            if self._integration_mode == "demo"
            else ModelConfigurationStatus.CONFIGURED
        )
        return SystemStatusSnapshot(
            integration_mode=self._integration_mode,
            model=ModelDependencyStatus(
                provider=self._model_provider,
                status=model_status,
            ),
            knowledge=knowledge_status,
        )
