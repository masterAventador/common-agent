from __future__ import annotations

import asyncio
import json
from typing import Any, cast

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from starlette.types import Scope

from common_agent.api.errors import (
    AppError,
    app_error_handler,
    internal_error_handler,
    validation_error_handler,
)

REQUEST_ID = "b72aa7d5-d8f5-4a18-b36c-9da8f6213bc1"


def _request() -> Request:
    scope = cast(
        Scope,
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [],
            "query_string": b"",
            "scheme": "http",
            "server": ("127.0.0.1", 80),
            "client": ("127.0.0.1", 12345),
            "state": {"request_id": REQUEST_ID},
        },
    )
    return Request(scope)


def _body(response_body: bytes | memoryview[int]) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(bytes(response_body)))


def test_app_error_preserves_stable_public_semantics() -> None:
    response = asyncio.run(
        app_error_handler(
            _request(),
            AppError(
                code="configuration_missing",
                message="缺少必要配置",
                status_code=503,
                retryable=True,
            ),
        )
    )

    assert response.status_code == 503
    assert _body(response.body) == {
        "code": "configuration_missing",
        "message": "缺少必要配置",
        "request_id": REQUEST_ID,
        "retryable": True,
    }


def test_validation_error_does_not_expose_invalid_input() -> None:
    error = RequestValidationError(
        [
            {
                "type": "string_type",
                "loc": ("body", "api_key"),
                "msg": "Input should be a valid string",
                "input": "secret-value",
            }
        ]
    )

    response = asyncio.run(validation_error_handler(_request(), error))

    assert response.status_code == 422
    assert "secret-value" not in bytes(response.body).decode("utf-8")
    assert _body(response.body) == {
        "code": "validation_error",
        "message": "请求参数不合法",
        "request_id": REQUEST_ID,
        "retryable": False,
    }


def test_internal_error_does_not_expose_exception_details() -> None:
    response = asyncio.run(internal_error_handler(_request(), RuntimeError("private path")))

    assert response.status_code == 500
    assert "private path" not in bytes(response.body).decode("utf-8")
    assert _body(response.body) == {
        "code": "internal_error",
        "message": "服务暂时不可用",
        "request_id": REQUEST_ID,
        "retryable": True,
    }
