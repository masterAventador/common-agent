from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict

from common_agent import __version__
from common_agent.api.errors import AppError, ErrorEnvelope
from common_agent.application.system_service import (
    ModelConfigurationStatus,
    SystemService,
)
from common_agent.domain.knowledge import KnowledgeServiceAvailability

router = APIRouter(prefix="/api/v1/system", tags=["system"])


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok"]
    service: Literal["common-agent-api"]
    version: str
    integration_mode: Literal["real", "demo"]


class ModelStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    status: ModelConfigurationStatus


class KnowledgeStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    availability: KnowledgeServiceAvailability
    version: str | None
    error_code: str | None


class SystemStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    backend: Literal["available"]
    service: Literal["common-agent-api"]
    version: str
    integration_mode: Literal["real", "demo"]
    model: ModelStatusResponse
    knowledge: KnowledgeStatusResponse


def _ensure_ready(request: Request) -> None:
    if getattr(request.app.state, "ready", False):
        return
    raise AppError(
        code="service_unavailable",
        message="服务尚未就绪",
        status_code=503,
        retryable=True,
    )


@router.get(
    "/health",
    response_model=HealthResponse,
    responses={
        503: {
            "model": ErrorEnvelope,
            "description": "API 或正式依赖尚未就绪",
        }
    },
)
async def health(request: Request) -> HealthResponse:
    _ensure_ready(request)

    integration_mode = request.app.state.integration_mode.mode
    return HealthResponse(
        status="ok",
        service="common-agent-api",
        version=__version__,
        integration_mode=integration_mode,
    )


@router.get(
    "/status",
    response_model=SystemStatusResponse,
    responses={
        503: {
            "model": ErrorEnvelope,
            "description": "API 或正式依赖尚未装配",
        }
    },
)
async def status(request: Request) -> SystemStatusResponse:
    _ensure_ready(request)
    application = getattr(request.app.state, "system", None)
    if not isinstance(application, SystemService):
        raise AppError(
            code="service_unavailable",
            message="系统状态服务尚未就绪",
            status_code=503,
            retryable=True,
        )
    snapshot = await application.status()
    return SystemStatusResponse(
        backend="available",
        service="common-agent-api",
        version=__version__,
        integration_mode=snapshot.integration_mode,
        model=ModelStatusResponse.model_validate(snapshot.model, from_attributes=True),
        knowledge=KnowledgeStatusResponse.model_validate(
            snapshot.knowledge,
            from_attributes=True,
        ),
    )
