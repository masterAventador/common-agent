from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict

from common_agent import __version__
from common_agent.api.errors import AppError, ErrorEnvelope

router = APIRouter(prefix="/api/v1/system", tags=["system"])


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok"]
    service: Literal["common-agent-api"]
    version: str
    integration_mode: Literal["real", "demo"]


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
    if not getattr(request.app.state, "ready", False):
        raise AppError(
            code="service_unavailable",
            message="服务尚未就绪",
            status_code=503,
            retryable=True,
        )

    integration_mode = request.app.state.integration_mode.mode
    return HealthResponse(
        status="ok",
        service="common-agent-api",
        version=__version__,
        integration_mode=integration_mode,
    )
