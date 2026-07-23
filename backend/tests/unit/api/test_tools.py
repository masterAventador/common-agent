from __future__ import annotations

import asyncio
from collections.abc import Callable
from io import BytesIO

import pytest
from fastapi import UploadFile
from starlette.applications import Starlette
from starlette.requests import Request

from common_agent.api.errors import AppError
from common_agent.api.routers.tools import (
    _credential_service,
    _error,
    _external_service,
    _managed_openapi_parser,
    _managed_runtime,
    _managed_service,
    _mcp_error,
    _read_openapi_upload,
    _service,
)
from common_agent.api.schemas.tools import ManagedHttpOpenApiDraftResponse
from common_agent.ports.mcp import McpToolCallError
from common_agent.tools.credential_service import (
    McpCredentialSourceNotFound,
    PlatformCredentialNotAllowed,
    ToolCredentialServiceError,
)
from common_agent.tools.credentials import ToolCredentialValidationError
from common_agent.tools.external_mcp import ExternalMcpValidationError
from common_agent.tools.external_mcp_service import (
    ExternalMcpCapabilityNotFound,
    ExternalMcpConflict,
    ExternalMcpServiceError,
    ExternalMcpSourceNotFound,
    ExternalMcpSyncFailed,
)
from common_agent.tools.managed_http import ManagedHttpValidationError
from common_agent.tools.managed_http_service import (
    ManagedHttpCapabilityNotFound,
    ManagedHttpConflict,
    ManagedHttpServiceError,
    ManagedHttpSourceNotFound,
)
from common_agent.tools.models import ToolValidationError
from common_agent.tools.openapi_import import OPENAPI_MAX_FILE_BYTES, OpenApiDocumentError
from common_agent.tools.service import (
    ToolCapabilityUnavailable,
    ToolCollectionConflict,
    ToolCollectionNotFound,
    ToolCollectionResourceNotFound,
    ToolCollectionSourceUnavailable,
    ToolGrantTargetNotFound,
    ToolServiceError,
)


class _ExternalFailure(ExternalMcpServiceError):
    code = "external_failure"
    message = "external failure"


class _ManagedFailure(ManagedHttpServiceError):
    code = "managed_failure"
    message = "managed failure"


class _CredentialFailure(ToolCredentialServiceError):
    code = "credential_failure"
    message = "credential failure"


class _ToolFailure(ToolServiceError):
    code = "tool_failure"
    message = "tool failure"


def _request() -> Request:
    return Request({"type": "http", "app": Starlette()})


@pytest.mark.parametrize(
    ("resolver", "code"),
    [
        (_service, "tool_service_unavailable"),
        (_credential_service, "tool_credential_service_unavailable"),
        (_managed_service, "managed_mcp_service_unavailable"),
        (_managed_runtime, "managed_mcp_runtime_unavailable"),
        (_managed_openapi_parser, "openapi_parser_unavailable"),
        (_external_service, "external_mcp_service_unavailable"),
    ],
)
def test_tool_router_dependencies_close_when_production_service_is_missing(
    resolver: Callable[[Request], object],
    code: str,
) -> None:
    with pytest.raises(AppError) as captured:
        resolver(_request())

    assert captured.value.code == code
    assert captured.value.status_code == 503
    assert captured.value.retryable is True


@pytest.mark.parametrize(
    ("error", "code", "status_code", "retryable"),
    [
        (
            OpenApiDocumentError("openapi_file_too_large", "large"),
            "openapi_file_too_large",
            413,
            False,
        ),
        (
            OpenApiDocumentError("openapi_media_type_unsupported", "media"),
            "openapi_media_type_unsupported",
            415,
            False,
        ),
        (
            OpenApiDocumentError("openapi_format_invalid", "format"),
            "openapi_format_invalid",
            422,
            False,
        ),
        (ExternalMcpSourceNotFound(), "external_mcp_source_not_found", 404, False),
        (ExternalMcpCapabilityNotFound(), "external_mcp_capability_not_found", 404, False),
        (ToolCollectionResourceNotFound(), "tool_collection_not_found", 404, False),
        (ExternalMcpSyncFailed("tool_timeout", retryable=True), "tool_timeout", 504, True),
        (
            ExternalMcpSyncFailed("tool_protocol_error", retryable=False),
            "tool_protocol_error",
            502,
            False,
        ),
        (ExternalMcpConflict(), "external_mcp_conflict", 409, False),
        (ToolCollectionConflict(), "tool_collection_conflict", 409, False),
        (ToolCollectionSourceUnavailable(), "tool_collection_source_unavailable", 409, False),
        (_ExternalFailure(), "external_failure", 409, False),
        (ExternalMcpValidationError("invalid"), "validation_error", 422, False),
        (ManagedHttpSourceNotFound(), "managed_mcp_source_not_found", 404, False),
        (ManagedHttpCapabilityNotFound(), "managed_mcp_capability_not_found", 404, False),
        (ManagedHttpConflict(), "managed_mcp_conflict", 409, False),
        (_ManagedFailure(), "managed_failure", 409, False),
        (ManagedHttpValidationError("path", "invalid"), "validation_error", 422, False),
        (McpCredentialSourceNotFound(), "mcp_credential_source_not_found", 404, False),
        (PlatformCredentialNotAllowed(), "platform_mcp_credential_not_allowed", 409, False),
        (ToolCredentialValidationError("invalid"), "validation_error", 422, False),
        (_CredentialFailure(), "credential_failure", 409, False),
        (ToolGrantTargetNotFound(), "tool_grant_target_not_found", 404, False),
        (ToolCollectionNotFound(), "tool_collection_not_found", 409, False),
        (ToolCapabilityUnavailable(), "tool_capability_unavailable", 409, False),
        (ToolValidationError("name", "invalid"), "validation_error", 422, False),
        (_ToolFailure(), "tool_failure", 409, False),
    ],
)
def test_tool_router_maps_each_application_failure_to_a_stable_http_error(
    error: Exception,
    code: str,
    status_code: int,
    retryable: bool,
) -> None:
    mapped = _error(error)

    assert mapped.code == code
    assert mapped.status_code == status_code
    assert mapped.retryable is retryable


def test_tool_router_rejects_unregistered_application_failure() -> None:
    with pytest.raises(TypeError, match="unsupported tool application error"):
        _error(RuntimeError("unexpected"))


@pytest.mark.parametrize(
    ("remote_code", "code", "status_code"),
    [
        ("tool_invalid_arguments", "tool_invalid_arguments", 422),
        ("tool_source_unavailable", "tool_source_unavailable", 409),
        ("tool_capability_unavailable", "tool_capability_unavailable", 409),
        ("tool_timeout", "tool_timeout", 504),
        ("tool_response_too_large", "tool_response_too_large", 502),
        ("tool_protocol_error", "tool_protocol_error", 502),
        ("tool_result_unknown", "tool_result_unknown", 502),
        ("tool_execution_failed", "tool_execution_failed", 502),
        ("upstream_private_code", "tool_execution_failed", 502),
    ],
)
def test_tool_router_maps_mcp_errors_without_leaking_unknown_codes(
    remote_code: str,
    code: str,
    status_code: int,
) -> None:
    mapped = _mcp_error(McpToolCallError(remote_code, retryable=True))

    assert mapped.code == code
    assert mapped.message == "工具调用失败"
    assert mapped.status_code == status_code
    assert mapped.retryable is True


def test_openapi_upload_reader_closes_framework_file_after_bounded_read() -> None:
    upload = UploadFile(file=BytesIO(b'{"openapi":"3.0.3"}'), filename="openapi.json")

    content = asyncio.run(_read_openapi_upload(upload))

    assert content == b'{"openapi":"3.0.3"}'
    assert upload.file.closed is True


def test_openapi_upload_reader_rejects_oversize_and_still_closes_file() -> None:
    upload = UploadFile(
        file=BytesIO(b"x" * (OPENAPI_MAX_FILE_BYTES + 1)),
        filename="large.yaml",
    )

    with pytest.raises(OpenApiDocumentError) as captured:
        asyncio.run(_read_openapi_upload(upload))

    assert captured.value.code == "openapi_file_too_large"
    assert upload.file.closed is True


def test_openapi_preview_response_keeps_missing_description_editable() -> None:
    draft = ManagedHttpOpenApiDraftResponse(
        operation_key="GET /orders/{order_id}",
        remote_name="orders.get",
        display_name="orders.get",
        description="",
        input_schema={"type": "object", "properties": {}},
        method="GET",
        path_template="/orders/{order_id}",
        parameter_bindings=[],
        timeout_seconds=30,
        response_json_pointer=None,
        enabled=True,
        issues=["能力缺少说明"],
    )

    assert draft.description == ""
    assert draft.issues == ["能力缺少说明"]
