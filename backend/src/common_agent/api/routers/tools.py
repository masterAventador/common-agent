from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Request, Response, UploadFile, status

from common_agent.api.audit import mark_audit_resource
from common_agent.api.errors import AppError, ErrorEnvelope
from common_agent.api.schemas.tools import (
    ExternalMcpSourceBody,
    ExternalMcpSourceListResponse,
    ExternalMcpSourceResponse,
    ExternalMcpSyncResponse,
    ManagedHttpCapabilityBody,
    ManagedHttpCapabilityResponse,
    ManagedHttpDiscoveredToolResponse,
    ManagedHttpDiscoveryResponse,
    ManagedHttpOpenApiImportBody,
    ManagedHttpOpenApiImportResponse,
    ManagedHttpOpenApiPreviewResponse,
    ManagedHttpSourceBody,
    ManagedHttpSourceListResponse,
    ManagedHttpSourceResponse,
    ManagedHttpTestCallBody,
    ManagedHttpTestCallResponse,
    McpCredentialSummaryResponse,
    McpCredentialUpdateBody,
    ToolCatalogResponse,
    ToolCollectionBody,
    ToolCollectionResponse,
    ToolGrantResponse,
    ToolGrantSelectionBody,
    external_mcp_source_command,
    external_mcp_source_response,
    external_mcp_sync_response,
    managed_http_capability_command,
    managed_http_capability_response,
    managed_http_openapi_preview_response,
    managed_http_source_command,
    managed_http_source_response,
    mcp_credential_command,
    mcp_credential_summary_response,
    tool_catalog_response,
    tool_collection_response,
    tool_grant_response,
    tool_grant_selection,
)
from common_agent.audit import AuditResourceType
from common_agent.ports.mcp import ManagedMcpToolClient, McpToolCallError
from common_agent.ports.openapi import ManagedHttpOpenApiParserPort
from common_agent.tools.credential_service import (
    McpCredentialSourceNotFound,
    PlatformCredentialNotAllowed,
    ToolCredentialService,
    ToolCredentialServiceError,
)
from common_agent.tools.credentials import ToolCredentialValidationError
from common_agent.tools.external_mcp import ExternalMcpValidationError
from common_agent.tools.external_mcp_service import (
    ExternalMcpCapabilityNotFound,
    ExternalMcpConflict,
    ExternalMcpService,
    ExternalMcpServiceError,
    ExternalMcpSourceNotFound,
    ExternalMcpSyncFailed,
)
from common_agent.tools.managed_http import ManagedHttpValidationError
from common_agent.tools.managed_http_service import (
    ManagedHttpCapabilityNotFound,
    ManagedHttpConflict,
    ManagedHttpService,
    ManagedHttpServiceError,
    ManagedHttpSourceNotFound,
)
from common_agent.tools.models import ToolValidationError, normalize_input_schema
from common_agent.tools.openapi_import import (
    OPENAPI_MAX_FILE_BYTES,
    OpenApiDocumentError,
)
from common_agent.tools.service import (
    ToolCapabilityUnavailable,
    ToolCollectionConflict,
    ToolCollectionNotFound,
    ToolCollectionResourceNotFound,
    ToolCollectionSourceUnavailable,
    ToolGrantTargetNotFound,
    ToolService,
    ToolServiceError,
)

router = APIRouter(tags=["tools"])


def _service(request: Request) -> ToolService:
    service = getattr(request.app.state, "tools", None)
    if not isinstance(service, ToolService):
        raise AppError("tool_service_unavailable", "工具服务暂时不可用", 503, True)
    return service


def _credential_service(request: Request) -> ToolCredentialService:
    service = getattr(request.app.state, "tool_credentials", None)
    if not isinstance(service, ToolCredentialService):
        raise AppError("tool_credential_service_unavailable", "MCP 凭据服务暂时不可用", 503, True)
    return service


def _managed_service(request: Request) -> ManagedHttpService:
    service = getattr(request.app.state, "managed_http", None)
    if not isinstance(service, ManagedHttpService):
        raise AppError("managed_mcp_service_unavailable", "托管 MCP 服务暂时不可用", 503, True)
    return service


def _managed_runtime(request: Request) -> ManagedMcpToolClient:
    runtime = getattr(request.app.state, "managed_mcp", None)
    if not isinstance(runtime, ManagedMcpToolClient):
        raise AppError("managed_mcp_runtime_unavailable", "托管 MCP 运行时暂时不可用", 503, True)
    return runtime


def _managed_openapi_parser(request: Request) -> ManagedHttpOpenApiParserPort:
    parser = getattr(request.app.state, "managed_openapi_parser", None)
    if not isinstance(parser, ManagedHttpOpenApiParserPort):
        raise AppError("openapi_parser_unavailable", "OpenAPI 解析服务暂时不可用", 503, True)
    return parser


def _external_service(request: Request) -> ExternalMcpService:
    service = getattr(request.app.state, "external_mcp", None)
    if not isinstance(service, ExternalMcpService):
        raise AppError("external_mcp_service_unavailable", "外部 MCP 服务暂时不可用", 503, True)
    return service


def _error(error: Exception) -> AppError:
    if isinstance(error, OpenApiDocumentError):
        status_code = {
            "openapi_file_too_large": 413,
            "openapi_media_type_unsupported": 415,
        }.get(error.code, 422)
        return AppError(error.code, error.message, status_code, False)
    if isinstance(
        error,
        (
            ExternalMcpSourceNotFound,
            ExternalMcpCapabilityNotFound,
            ToolCollectionResourceNotFound,
        ),
    ):
        return AppError(error.code, error.message, 404, error.retryable)
    if isinstance(error, ExternalMcpSyncFailed):
        status_code = 504 if error.code == "tool_timeout" else 502
        return AppError(error.code, error.message, status_code, error.retryable)
    if isinstance(error, (ExternalMcpConflict, ToolCollectionConflict)):
        return AppError(error.code, error.message, 409, error.retryable)
    if isinstance(error, ToolCollectionSourceUnavailable):
        return AppError(error.code, error.message, 409, error.retryable)
    if isinstance(error, ExternalMcpServiceError):
        return AppError(error.code, error.message, 409, error.retryable)
    if isinstance(error, ExternalMcpValidationError):
        return AppError("validation_error", "请求参数不合法", 422, False)
    if isinstance(error, (ManagedHttpSourceNotFound, ManagedHttpCapabilityNotFound)):
        return AppError(error.code, error.message, 404, error.retryable)
    if isinstance(error, ManagedHttpConflict):
        return AppError(error.code, error.message, 409, error.retryable)
    if isinstance(error, ManagedHttpServiceError):
        return AppError(error.code, error.message, 409, error.retryable)
    if isinstance(error, ManagedHttpValidationError):
        return AppError("validation_error", "请求参数不合法", 422, False)
    if isinstance(error, McpCredentialSourceNotFound):
        return AppError(error.code, error.message, 404, error.retryable)
    if isinstance(error, PlatformCredentialNotAllowed):
        return AppError(error.code, error.message, 409, error.retryable)
    if isinstance(error, ToolCredentialValidationError):
        return AppError("validation_error", "请求参数不合法", 422, False)
    if isinstance(error, ToolCredentialServiceError):
        return AppError(error.code, error.message, 409, error.retryable)
    if isinstance(error, ToolGrantTargetNotFound):
        return AppError(error.code, error.message, 404, error.retryable)
    if isinstance(error, (ToolCollectionNotFound, ToolCapabilityUnavailable)):
        return AppError(error.code, error.message, 409, error.retryable)
    if isinstance(error, ToolValidationError):
        return AppError("validation_error", "请求参数不合法", 422, False)
    if isinstance(error, ToolServiceError):
        return AppError(error.code, error.message, 409, error.retryable)
    raise TypeError("unsupported tool application error")


async def _read_openapi_upload(file: UploadFile) -> bytes:
    content = bytearray()
    try:
        while len(content) <= OPENAPI_MAX_FILE_BYTES:
            chunk = await file.read(
                min(1024 * 1024, OPENAPI_MAX_FILE_BYTES + 1 - len(content))
            )
            if not chunk:
                break
            content.extend(chunk)
    finally:
        await file.close()
    if len(content) > OPENAPI_MAX_FILE_BYTES:
        raise OpenApiDocumentError(
            "openapi_file_too_large",
            f"OpenAPI 文件不能超过 {OPENAPI_MAX_FILE_BYTES} 字节",
        )
    return bytes(content)


def _mcp_error(error: McpToolCallError) -> AppError:
    statuses = {
        "tool_invalid_arguments": 422,
        "tool_source_unavailable": 409,
        "tool_capability_unavailable": 409,
        "tool_timeout": 504,
        "tool_response_too_large": 502,
        "tool_protocol_error": 502,
        "tool_result_unknown": 502,
        "tool_execution_failed": 502,
    }
    return AppError(
        error.code if error.code in statuses else "tool_execution_failed",
        "工具调用失败",
        statuses.get(error.code, 502),
        error.retryable,
    )


@router.get(
    "/api/v1/external-mcp-sources",
    response_model=ExternalMcpSourceListResponse,
    responses={503: {"model": ErrorEnvelope}},
)
async def list_external_mcp_sources(request: Request) -> ExternalMcpSourceListResponse:
    snapshots = await _external_service(request).list_sources()
    return ExternalMcpSourceListResponse(
        items=[external_mcp_source_response(value) for value in snapshots]
    )


@router.post(
    "/api/v1/external-mcp-sources",
    response_model=ExternalMcpSourceResponse,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}},
)
async def create_external_mcp_source(
    request: Request,
    body: ExternalMcpSourceBody,
) -> ExternalMcpSourceResponse:
    try:
        snapshot = await _external_service(request).create_source(
            external_mcp_source_command(body)
        )
    except (ExternalMcpServiceError, ExternalMcpValidationError, ToolValidationError) as error:
        raise _error(error) from error
    mark_audit_resource(request, AuditResourceType.MCP_SOURCE, snapshot.source.id)
    return external_mcp_source_response(snapshot)


@router.get(
    "/api/v1/external-mcp-sources/{source_id}",
    response_model=ExternalMcpSourceResponse,
    responses={404: {"model": ErrorEnvelope}},
)
async def get_external_mcp_source(
    request: Request,
    source_id: UUID,
) -> ExternalMcpSourceResponse:
    try:
        snapshot = await _external_service(request).snapshot(source_id)
    except ExternalMcpServiceError as error:
        raise _error(error) from error
    return external_mcp_source_response(snapshot)


@router.put(
    "/api/v1/external-mcp-sources/{source_id}",
    response_model=ExternalMcpSourceResponse,
    responses={
        404: {"model": ErrorEnvelope},
        409: {"model": ErrorEnvelope},
        422: {"model": ErrorEnvelope},
    },
)
async def update_external_mcp_source(
    request: Request,
    source_id: UUID,
    body: ExternalMcpSourceBody,
) -> ExternalMcpSourceResponse:
    try:
        snapshot = await _external_service(request).update_source(
            source_id,
            external_mcp_source_command(body),
        )
    except (ExternalMcpServiceError, ExternalMcpValidationError, ToolValidationError) as error:
        raise _error(error) from error
    mark_audit_resource(request, AuditResourceType.MCP_SOURCE, source_id)
    return external_mcp_source_response(snapshot)


@router.delete(
    "/api/v1/external-mcp-sources/{source_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"model": ErrorEnvelope}, 409: {"model": ErrorEnvelope}},
)
async def delete_external_mcp_source(request: Request, source_id: UUID) -> Response:
    try:
        await _external_service(request).delete_source(source_id)
    except ExternalMcpServiceError as error:
        raise _error(error) from error
    mark_audit_resource(request, AuditResourceType.MCP_SOURCE, source_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/api/v1/external-mcp-sources/{source_id}/sync",
    response_model=ExternalMcpSyncResponse,
    responses={
        404: {"model": ErrorEnvelope},
        409: {"model": ErrorEnvelope},
        502: {"model": ErrorEnvelope},
        504: {"model": ErrorEnvelope},
    },
)
async def sync_external_mcp_source(
    request: Request,
    source_id: UUID,
) -> ExternalMcpSyncResponse:
    try:
        result = await _external_service(request).sync_source(source_id)
    except ExternalMcpServiceError as error:
        raise _error(error) from error
    mark_audit_resource(request, AuditResourceType.MCP_SOURCE, source_id)
    return external_mcp_sync_response(result)


@router.post(
    "/api/v1/external-mcp-sources/{source_id}/capabilities/{capability_id}/test-call",
    response_model=ManagedHttpTestCallResponse,
    responses={
        404: {"model": ErrorEnvelope},
        409: {"model": ErrorEnvelope},
        422: {"model": ErrorEnvelope},
        502: {"model": ErrorEnvelope},
        504: {"model": ErrorEnvelope},
    },
)
async def test_external_mcp_capability(
    request: Request,
    source_id: UUID,
    capability_id: UUID,
    body: ManagedHttpTestCallBody,
) -> ManagedHttpTestCallResponse:
    try:
        result = await _external_service(request).call_capability(
            source_id,
            capability_id,
            body.arguments,
        )
    except ExternalMcpServiceError as error:
        raise _error(error) from error
    except McpToolCallError as error:
        raise _mcp_error(error) from error
    mark_audit_resource(request, AuditResourceType.TOOL_CAPABILITY, capability_id)
    return ManagedHttpTestCallResponse(capability_id=capability_id, output=result.output)


@router.post(
    "/api/v1/tool-collections",
    response_model=ToolCollectionResponse,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}},
)
async def create_tool_collection(
    request: Request,
    body: ToolCollectionBody,
) -> ToolCollectionResponse:
    try:
        collection = await _service(request).create_collection(
            name=body.name,
            description=body.description,
            source_ids=tuple(body.source_ids),
        )
    except (ToolServiceError, ToolValidationError) as error:
        raise _error(error) from error
    mark_audit_resource(request, AuditResourceType.TOOL_COLLECTION, collection.id)
    return tool_collection_response(collection)


@router.put(
    "/api/v1/tool-collections/{collection_id}",
    response_model=ToolCollectionResponse,
    responses={
        404: {"model": ErrorEnvelope},
        409: {"model": ErrorEnvelope},
        422: {"model": ErrorEnvelope},
    },
)
async def update_tool_collection(
    request: Request,
    collection_id: UUID,
    body: ToolCollectionBody,
) -> ToolCollectionResponse:
    try:
        collection = await _service(request).update_collection(
            collection_id,
            name=body.name,
            description=body.description,
            source_ids=tuple(body.source_ids),
        )
    except (ToolServiceError, ToolValidationError) as error:
        raise _error(error) from error
    mark_audit_resource(request, AuditResourceType.TOOL_COLLECTION, collection_id)
    return tool_collection_response(collection)


@router.delete(
    "/api/v1/tool-collections/{collection_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"model": ErrorEnvelope}, 409: {"model": ErrorEnvelope}},
)
async def delete_tool_collection(request: Request, collection_id: UUID) -> Response:
    try:
        await _service(request).delete_collection(collection_id)
    except ToolServiceError as error:
        raise _error(error) from error
    mark_audit_resource(request, AuditResourceType.TOOL_COLLECTION, collection_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/api/v1/managed-mcp-sources",
    response_model=ManagedHttpSourceListResponse,
    responses={503: {"model": ErrorEnvelope}},
)
async def list_managed_mcp_sources(request: Request) -> ManagedHttpSourceListResponse:
    snapshots = await _managed_service(request).list_sources()
    return ManagedHttpSourceListResponse(
        items=[managed_http_source_response(value) for value in snapshots]
    )


@router.post(
    "/api/v1/managed-mcp-sources",
    response_model=ManagedHttpSourceResponse,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}},
)
async def create_managed_mcp_source(
    request: Request,
    body: ManagedHttpSourceBody,
) -> ManagedHttpSourceResponse:
    try:
        snapshot = await _managed_service(request).create_source(
            managed_http_source_command(body)
        )
    except (ManagedHttpServiceError, ManagedHttpValidationError) as error:
        raise _error(error) from error
    mark_audit_resource(request, AuditResourceType.MCP_SOURCE, snapshot.source.id)
    return managed_http_source_response(snapshot)


@router.get(
    "/api/v1/managed-mcp-sources/{source_id}",
    response_model=ManagedHttpSourceResponse,
    responses={404: {"model": ErrorEnvelope}},
)
async def get_managed_mcp_source(
    request: Request,
    source_id: UUID,
) -> ManagedHttpSourceResponse:
    try:
        snapshot = await _managed_service(request).snapshot(source_id)
    except ManagedHttpServiceError as error:
        raise _error(error) from error
    return managed_http_source_response(snapshot)


@router.put(
    "/api/v1/managed-mcp-sources/{source_id}",
    response_model=ManagedHttpSourceResponse,
    responses={404: {"model": ErrorEnvelope}, 409: {"model": ErrorEnvelope}},
)
async def update_managed_mcp_source(
    request: Request,
    source_id: UUID,
    body: ManagedHttpSourceBody,
) -> ManagedHttpSourceResponse:
    try:
        snapshot = await _managed_service(request).update_source(
            source_id,
            managed_http_source_command(body),
        )
    except (ManagedHttpServiceError, ManagedHttpValidationError) as error:
        raise _error(error) from error
    mark_audit_resource(request, AuditResourceType.MCP_SOURCE, source_id)
    return managed_http_source_response(snapshot)


@router.delete(
    "/api/v1/managed-mcp-sources/{source_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"model": ErrorEnvelope}, 409: {"model": ErrorEnvelope}},
)
async def delete_managed_mcp_source(request: Request, source_id: UUID) -> Response:
    try:
        await _managed_service(request).delete_source(source_id)
    except ManagedHttpServiceError as error:
        raise _error(error) from error
    mark_audit_resource(request, AuditResourceType.MCP_SOURCE, source_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/api/v1/managed-mcp-sources/{source_id}/capabilities",
    response_model=ManagedHttpCapabilityResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        404: {"model": ErrorEnvelope},
        409: {"model": ErrorEnvelope},
        422: {"model": ErrorEnvelope},
    },
)
async def add_managed_mcp_capability(
    request: Request,
    source_id: UUID,
    body: ManagedHttpCapabilityBody,
) -> ManagedHttpCapabilityResponse:
    try:
        capability = await _managed_service(request).add_capability(
            source_id,
            managed_http_capability_command(body),
        )
    except (ManagedHttpServiceError, ManagedHttpValidationError, ToolValidationError) as error:
        raise _error(error) from error
    mark_audit_resource(request, AuditResourceType.TOOL_CAPABILITY, capability.capability.id)
    return managed_http_capability_response(capability)


@router.put(
    "/api/v1/managed-mcp-sources/{source_id}/capabilities/{capability_id}",
    response_model=ManagedHttpCapabilityResponse,
    responses={
        404: {"model": ErrorEnvelope},
        409: {"model": ErrorEnvelope},
        422: {"model": ErrorEnvelope},
    },
)
async def update_managed_mcp_capability(
    request: Request,
    source_id: UUID,
    capability_id: UUID,
    body: ManagedHttpCapabilityBody,
) -> ManagedHttpCapabilityResponse:
    try:
        capability = await _managed_service(request).update_capability(
            source_id,
            capability_id,
            managed_http_capability_command(body),
        )
    except (ManagedHttpServiceError, ManagedHttpValidationError, ToolValidationError) as error:
        raise _error(error) from error
    mark_audit_resource(request, AuditResourceType.TOOL_CAPABILITY, capability_id)
    return managed_http_capability_response(capability)


@router.delete(
    "/api/v1/managed-mcp-sources/{source_id}/capabilities/{capability_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"model": ErrorEnvelope}, 409: {"model": ErrorEnvelope}},
)
async def delete_managed_mcp_capability(
    request: Request,
    source_id: UUID,
    capability_id: UUID,
) -> Response:
    try:
        await _managed_service(request).delete_capability(source_id, capability_id)
    except ManagedHttpServiceError as error:
        raise _error(error) from error
    mark_audit_resource(request, AuditResourceType.TOOL_CAPABILITY, capability_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/api/v1/managed-mcp-sources/{source_id}/openapi/preview",
    response_model=ManagedHttpOpenApiPreviewResponse,
    responses={
        404: {"model": ErrorEnvelope},
        413: {"model": ErrorEnvelope},
        415: {"model": ErrorEnvelope},
        422: {"model": ErrorEnvelope},
        503: {"model": ErrorEnvelope},
    },
)
async def preview_managed_mcp_openapi(
    request: Request,
    source_id: UUID,
    file: Annotated[
        UploadFile,
        File(description="OpenAPI 3.0/3.1 JSON 或 YAML, 最大 5 MiB"),
    ],
) -> ManagedHttpOpenApiPreviewResponse:
    try:
        snapshot = await _managed_service(request).snapshot(source_id)
        preview = _managed_openapi_parser(request).parse(
            await _read_openapi_upload(file),
            file.filename or "",
        )
    except (ManagedHttpServiceError, OpenApiDocumentError) as error:
        raise _error(error) from error
    return managed_http_openapi_preview_response(
        preview,
        sorted(item.capability.remote_name for item in snapshot.capabilities),
    )


@router.post(
    "/api/v1/managed-mcp-sources/{source_id}/openapi/import",
    response_model=ManagedHttpOpenApiImportResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        404: {"model": ErrorEnvelope},
        409: {"model": ErrorEnvelope},
        422: {"model": ErrorEnvelope},
    },
)
async def import_managed_mcp_openapi(
    request: Request,
    source_id: UUID,
    body: ManagedHttpOpenApiImportBody,
) -> ManagedHttpOpenApiImportResponse:
    try:
        imported = await _managed_service(request).import_capabilities(
            source_id,
            tuple(managed_http_capability_command(item) for item in body.capabilities),
        )
    except (ManagedHttpServiceError, ManagedHttpValidationError, ToolValidationError) as error:
        raise _error(error) from error
    mark_audit_resource(request, AuditResourceType.MCP_SOURCE, source_id)
    return ManagedHttpOpenApiImportResponse(
        items=[managed_http_capability_response(item) for item in imported]
    )


@router.post(
    "/api/v1/managed-mcp-sources/{source_id}/discover",
    response_model=ManagedHttpDiscoveryResponse,
    responses={404: {"model": ErrorEnvelope}, 409: {"model": ErrorEnvelope}},
)
async def discover_managed_mcp_source(
    request: Request,
    source_id: UUID,
) -> ManagedHttpDiscoveryResponse:
    try:
        snapshot = await _managed_service(request).snapshot(source_id)
        descriptors = await _managed_runtime(request).list_tools(source_id)
    except ManagedHttpServiceError as error:
        raise _error(error) from error
    except McpToolCallError as error:
        raise _mcp_error(error) from error
    by_name = {item.capability.remote_name: item.capability for item in snapshot.capabilities}
    tools: list[ManagedHttpDiscoveredToolResponse] = []
    for descriptor in descriptors:
        capability = by_name.get(descriptor.name)
        if capability is None:
            raise AppError("tool_protocol_error", "工具发现结果不一致", 502, False)
        _, fingerprint = normalize_input_schema(descriptor.input_schema)
        if fingerprint != capability.schema_fingerprint:
            raise AppError("tool_protocol_error", "工具发现结果不一致", 502, False)
        tools.append(
            ManagedHttpDiscoveredToolResponse(
                capability_id=capability.id,
                name=descriptor.name,
                display_name=descriptor.display_name,
                description=descriptor.description,
                input_schema=descriptor.input_schema,
                schema_fingerprint=fingerprint,
            )
        )
    mark_audit_resource(request, AuditResourceType.MCP_SOURCE, source_id)
    return ManagedHttpDiscoveryResponse(source_id=source_id, tools=tools)


@router.post(
    "/api/v1/managed-mcp-sources/{source_id}/capabilities/{capability_id}/test-call",
    response_model=ManagedHttpTestCallResponse,
    responses={
        404: {"model": ErrorEnvelope},
        409: {"model": ErrorEnvelope},
        422: {"model": ErrorEnvelope},
        502: {"model": ErrorEnvelope},
        504: {"model": ErrorEnvelope},
    },
)
async def test_managed_mcp_capability(
    request: Request,
    source_id: UUID,
    capability_id: UUID,
    body: ManagedHttpTestCallBody,
) -> ManagedHttpTestCallResponse:
    try:
        snapshot = await _managed_service(request).snapshot(source_id)
        capability = next(
            (
                item.capability
                for item in snapshot.capabilities
                if item.capability.id == capability_id
            ),
            None,
        )
        if capability is None:
            raise ManagedHttpCapabilityNotFound
        result = await _managed_runtime(request).call_tool(
            source_id,
            capability.remote_name,
            body.arguments,
        )
    except ManagedHttpServiceError as error:
        raise _error(error) from error
    except McpToolCallError as error:
        raise _mcp_error(error) from error
    mark_audit_resource(request, AuditResourceType.TOOL_CAPABILITY, capability_id)
    return ManagedHttpTestCallResponse(
        capability_id=capability_id,
        output=result.output,
    )


@router.get(
    "/api/v1/mcp-sources/{source_id}/credentials",
    response_model=McpCredentialSummaryResponse,
    responses={404: {"model": ErrorEnvelope}, 503: {"model": ErrorEnvelope}},
)
async def get_mcp_source_credentials(
    request: Request,
    source_id: UUID,
) -> McpCredentialSummaryResponse:
    try:
        summary = await _credential_service(request).get(source_id)
    except ToolCredentialServiceError as error:
        raise _error(error) from error
    return mcp_credential_summary_response(summary)


@router.put(
    "/api/v1/mcp-sources/{source_id}/credentials",
    response_model=McpCredentialSummaryResponse,
    responses={
        404: {"model": ErrorEnvelope},
        409: {"model": ErrorEnvelope},
        422: {"model": ErrorEnvelope},
        503: {"model": ErrorEnvelope},
    },
)
async def update_mcp_source_credentials(
    request: Request,
    source_id: UUID,
    body: McpCredentialUpdateBody,
) -> McpCredentialSummaryResponse:
    try:
        summary = await _credential_service(request).update(
            source_id,
            mcp_credential_command(body),
        )
    except (ToolCredentialServiceError, ToolCredentialValidationError) as error:
        raise _error(error) from error
    mark_audit_resource(request, AuditResourceType.MCP_SOURCE, source_id)
    return mcp_credential_summary_response(summary)


@router.get(
    "/api/v1/tool-catalog",
    response_model=ToolCatalogResponse,
    responses={503: {"model": ErrorEnvelope}},
)
async def get_tool_catalog(request: Request) -> ToolCatalogResponse:
    return tool_catalog_response(await _service(request).catalog())


@router.get(
    "/api/v1/employees/{employee_id}/tool-grants",
    response_model=ToolGrantResponse,
    responses={404: {"model": ErrorEnvelope}, 503: {"model": ErrorEnvelope}},
)
async def get_employee_tool_grants(request: Request, employee_id: UUID) -> ToolGrantResponse:
    try:
        snapshot = await _service(request).employee_grants(employee_id)
    except ToolGrantTargetNotFound as error:
        raise _error(error) from error
    return tool_grant_response(snapshot)


@router.put(
    "/api/v1/employees/{employee_id}/tool-grants",
    response_model=ToolGrantResponse,
    responses={
        404: {"model": ErrorEnvelope},
        409: {"model": ErrorEnvelope},
        422: {"model": ErrorEnvelope},
        503: {"model": ErrorEnvelope},
    },
)
async def replace_employee_tool_grants(
    request: Request,
    employee_id: UUID,
    body: ToolGrantSelectionBody,
) -> ToolGrantResponse:
    try:
        snapshot = await _service(request).replace_employee_grants(
            employee_id,
            tool_grant_selection(body),
        )
    except (ToolServiceError, ToolValidationError) as error:
        raise _error(error) from error
    mark_audit_resource(request, AuditResourceType.EMPLOYEE, employee_id)
    return tool_grant_response(snapshot)


@router.get(
    "/api/v1/conversations/{conversation_id}/tool-grants",
    response_model=ToolGrantResponse,
    responses={404: {"model": ErrorEnvelope}, 503: {"model": ErrorEnvelope}},
)
async def get_conversation_tool_grants(
    request: Request,
    conversation_id: UUID,
) -> ToolGrantResponse:
    try:
        snapshot = await _service(request).conversation_grants(conversation_id)
    except ToolGrantTargetNotFound as error:
        raise _error(error) from error
    return tool_grant_response(snapshot)


@router.put(
    "/api/v1/conversations/{conversation_id}/tool-grants",
    response_model=ToolGrantResponse,
    responses={
        404: {"model": ErrorEnvelope},
        409: {"model": ErrorEnvelope},
        422: {"model": ErrorEnvelope},
        503: {"model": ErrorEnvelope},
    },
)
async def replace_conversation_tool_grants(
    request: Request,
    conversation_id: UUID,
    body: ToolGrantSelectionBody,
) -> ToolGrantResponse:
    try:
        snapshot = await _service(request).replace_conversation_grants(
            conversation_id,
            tool_grant_selection(body),
        )
    except (ToolServiceError, ToolValidationError) as error:
        raise _error(error) from error
    mark_audit_resource(request, AuditResourceType.CONVERSATION, conversation_id)
    return tool_grant_response(snapshot)


__all__ = ["router"]
