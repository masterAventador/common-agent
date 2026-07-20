from __future__ import annotations

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any, cast
from uuid import uuid4

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response


class ErrorEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    request_id: str
    retryable: bool


@dataclass(frozen=True, slots=True)
class AppError(Exception):
    code: str
    message: str
    status_code: int
    retryable: bool = False


def _request_id(request: Request) -> str:
    request_id = getattr(request.state, "request_id", None)
    if isinstance(request_id, str):
        return request_id

    generated = str(uuid4())
    request.state.request_id = generated
    return generated


def _response(
    request: Request,
    *,
    code: str,
    message: str,
    status_code: int,
    retryable: bool,
) -> JSONResponse:
    request.state.error_code = code
    envelope = ErrorEnvelope(
        code=code,
        message=message,
        request_id=_request_id(request),
        retryable=retryable,
    )
    return JSONResponse(status_code=status_code, content=envelope.model_dump(mode="json"))


async def app_error_handler(request: Request, error: AppError) -> JSONResponse:
    return _response(
        request,
        code=error.code,
        message=error.message,
        status_code=error.status_code,
        retryable=error.retryable,
    )


async def validation_error_handler(request: Request, error: RequestValidationError) -> JSONResponse:
    del error
    return _response(
        request,
        code="validation_error",
        message="请求参数不合法",
        status_code=422,
        retryable=False,
    )


async def http_error_handler(request: Request, error: StarletteHTTPException) -> JSONResponse:
    if error.status_code == 404:
        return _response(
            request,
            code="resource_not_found",
            message="请求的资源不存在",
            status_code=404,
            retryable=False,
        )

    return _response(
        request,
        code="http_error",
        message="请求处理失败",
        status_code=error.status_code,
        retryable=error.status_code >= 500,
    )


async def internal_error_handler(request: Request, error: Exception) -> JSONResponse:
    del error
    return _response(
        request,
        code="internal_error",
        message="服务暂时不可用",
        status_code=500,
        retryable=True,
    )


ExceptionHandler = Callable[[Request, Any], Coroutine[Any, Any, Response]]


def error_handlers() -> dict[int | type[Exception], ExceptionHandler]:
    return {
        AppError: cast(ExceptionHandler, app_error_handler),
        RequestValidationError: cast(ExceptionHandler, validation_error_handler),
        StarletteHTTPException: cast(ExceptionHandler, http_error_handler),
        Exception: cast(ExceptionHandler, internal_error_handler),
    }
