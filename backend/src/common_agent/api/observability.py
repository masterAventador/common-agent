from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from time import monotonic
from uuid import uuid4

from fastapi import Request, Response

from common_agent.api.errors import internal_error_handler
from common_agent.observability import (
    MetricsRegistry,
    bind_observation_context,
    log_event,
)

_LOGGER = logging.getLogger("common_agent.http")
_METRICS_PATH = "/api/v1/system/metrics"

RequestHandler = Callable[[Request], Awaitable[Response]]


async def observe_http_request(request: Request, call_next: RequestHandler) -> Response:
    request_id = str(uuid4())
    request.state.request_id = request_id
    registry = _metrics_registry(request)
    tracked = request.url.path != _METRICS_PATH
    started_at = registry.begin_request() if tracked else monotonic()

    with bind_observation_context(
        request_id=request_id,
        traceparent=request.headers.get("traceparent"),
    ) as context:
        try:
            response = await call_next(request)
        except Exception as error:
            duration_ms = _complete_request(
                registry,
                tracked=tracked,
                started_at=started_at,
                status_code=500,
                error_code="internal_error",
            )
            with bind_observation_context(**_business_identifiers(request)):
                log_event(
                    _LOGGER,
                    "http.request.completed",
                    level=logging.ERROR,
                    method=request.method,
                    route=_route_template(request),
                    status_code=500,
                    duration_ms=duration_ms,
                    error_code="internal_error",
                    exception_type=type(error).__name__,
                )
            response = await internal_error_handler(request, error)
            response.headers["X-Request-ID"] = request_id
            response.headers["traceparent"] = context.traceparent
            return response

        error_code = getattr(request.state, "error_code", None)
        normalized_error = error_code if isinstance(error_code, str) else None
        duration_ms = _complete_request(
            registry,
            tracked=tracked,
            started_at=started_at,
            status_code=response.status_code,
            error_code=normalized_error,
        )
        response.headers["X-Request-ID"] = request_id
        response.headers["traceparent"] = context.traceparent
        identifiers = _business_identifiers(request)
        with bind_observation_context(**identifiers):
            log_event(
                _LOGGER,
                "http.request.completed",
                level=_log_level(response.status_code),
                method=request.method,
                route=_route_template(request),
                status_code=response.status_code,
                duration_ms=duration_ms,
                error_code=normalized_error,
            )
        return response


def _metrics_registry(request: Request) -> MetricsRegistry:
    registry = getattr(request.app.state, "metrics", None)
    if not isinstance(registry, MetricsRegistry):
        raise RuntimeError("metrics registry is not configured")
    return registry


def _complete_request(
    registry: MetricsRegistry,
    *,
    tracked: bool,
    started_at: float,
    status_code: int,
    error_code: str | None,
) -> float:
    if tracked:
        return registry.complete_request(
            started_at,
            status_code=status_code,
            error_code=error_code,
        )
    return max(0.0, (monotonic() - started_at) * 1000)


def _route_template(request: Request) -> str:
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    if isinstance(path, str):
        return path
    return request.url.path


def _business_identifiers(request: Request) -> dict[str, str]:
    identifiers: dict[str, str] = {}
    for field in (
        "conversation_id",
        "message_id",
        "turn_id",
        "workflow_id",
        "run_id",
    ):
        value = request.path_params.get(field)
        if value is not None:
            identifiers[field] = str(value)
    return identifiers


def _log_level(status_code: int) -> int:
    if status_code >= 500:
        return logging.ERROR
    if status_code >= 400:
        return logging.WARNING
    return logging.INFO
