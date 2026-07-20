from __future__ import annotations

import asyncio
from typing import cast

from common_agent.application.system_service import (
    ModelConfigurationStatus,
    SystemService,
)
from common_agent.domain.knowledge import (
    KnowledgeServiceAvailability,
    KnowledgeServiceStatus,
)
from common_agent.knowledge.base import KnowledgeService


class _KnowledgeProbe:
    provider_name = "ragflow"

    def __init__(
        self,
        status: KnowledgeServiceStatus | None = None,
        error: Exception | None = None,
    ) -> None:
        self._status = status
        self._error = error

    async def status(self) -> KnowledgeServiceStatus:
        if self._error is not None:
            raise self._error
        assert self._status is not None
        return self._status


def test_system_status_preserves_real_dependency_truth() -> None:
    service = SystemService(
        integration_mode="real",
        model_provider="bailian",
        knowledge=cast(
            KnowledgeService,
            _KnowledgeProbe(
                KnowledgeServiceStatus(
                    provider="ragflow",
                    availability=KnowledgeServiceAvailability.AVAILABLE,
                    version="v0.25.6",
                )
            ),
        ),
    )

    snapshot = asyncio.run(service.status())

    assert snapshot.model.provider == "bailian"
    assert snapshot.model.status is ModelConfigurationStatus.CONFIGURED
    assert snapshot.knowledge.availability is KnowledgeServiceAvailability.AVAILABLE
    assert snapshot.knowledge.version == "v0.25.6"


def test_system_status_safely_marks_unknown_knowledge_failure_unavailable() -> None:
    service = SystemService(
        integration_mode="real",
        model_provider="bailian",
        knowledge=cast(KnowledgeService, _KnowledgeProbe(error=RuntimeError("private detail"))),
    )

    snapshot = asyncio.run(service.status())

    assert snapshot.knowledge == KnowledgeServiceStatus(
        provider="ragflow",
        availability=KnowledgeServiceAvailability.UNAVAILABLE,
        version=None,
        error_code="knowledge_service_unavailable",
    )
    assert "private detail" not in repr(snapshot)
