from __future__ import annotations

from fastapi import Request

from common_agent.api.errors import AppError
from common_agent.application.resource_deletion import (
    ResourceDeletionError,
    ResourceDeletionService,
)


def resource_deletion_service(request: Request) -> ResourceDeletionService:
    application = getattr(request.app.state, "resource_deletions", None)
    if not isinstance(application, ResourceDeletionService):
        raise AppError(
            code="resource_deletion_service_unavailable",
            message="资源删除服务暂时不可用",
            status_code=503,
            retryable=True,
        )
    return application


def resource_deletion_error(error: ResourceDeletionError) -> AppError:
    return AppError(
        code=error.code,
        message=error.message,
        status_code=409,
        retryable=error.retryable,
    )


__all__ = ["resource_deletion_error", "resource_deletion_service"]
