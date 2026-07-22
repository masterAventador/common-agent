from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

from common_agent.tools.credentials import (
    McpCredential,
    McpCredentialAction,
    McpCredentialCommand,
    McpCredentialKind,
    McpCredentialSummary,
)
from common_agent.tools.managed_http import (
    MANAGED_HTTP_PARAMETER_MAX_ITEMS,
    MANAGED_HTTP_PATH_MAX_LENGTH,
    MANAGED_HTTP_RESPONSE_POINTER_MAX_LENGTH,
    MANAGED_HTTP_TIMEOUT_MAX_SECONDS,
    ManagedHttpCapability,
    ManagedHttpCapabilityCommand,
    ManagedHttpParameterBinding,
    ManagedHttpParameterLocation,
    ManagedHttpRuntimeSnapshot,
    ManagedHttpSourceCommand,
)
from common_agent.tools.models import (
    TOOL_GRANT_CAPABILITY_MAX_ITEMS,
    TOOL_GRANT_COLLECTION_MAX_ITEMS,
    McpSourceStatus,
    McpSourceType,
    ToolCapabilityStatus,
    ToolCatalog,
    ToolGrantSelection,
    ToolGrantSnapshot,
    ToolGrantTargetType,
)
from common_agent.tools.openapi_import import (
    OPENAPI_MAX_OPERATIONS,
    ManagedHttpOpenApiDraft,
    ManagedHttpOpenApiPreview,
)


class McpSourceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    name: str
    description: str
    source_type: McpSourceType
    endpoint_url: str | None
    status: McpSourceStatus
    created_at: datetime
    updated_at: datetime


class ToolCapabilityResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    source_id: UUID
    remote_name: str
    display_name: str
    description: str
    input_schema: dict[str, object]
    schema_fingerprint: str
    status: ToolCapabilityStatus
    created_at: datetime
    updated_at: datetime


class ToolCollectionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    name: str
    description: str
    source_ids: list[UUID]
    created_at: datetime
    updated_at: datetime


class ToolCatalogResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sources: list[McpSourceResponse]
    capabilities: list[ToolCapabilityResponse]
    collections: list[ToolCollectionResponse]


class ToolGrantSelectionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    collection_ids: list[UUID] = Field(max_length=TOOL_GRANT_COLLECTION_MAX_ITEMS)
    capability_ids: list[UUID] = Field(max_length=TOOL_GRANT_CAPABILITY_MAX_ITEMS)


class ToolGrantResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_type: ToolGrantTargetType
    target_id: UUID
    collection_ids: list[UUID]
    capability_ids: list[UUID]


class McpCredentialUpdateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: McpCredentialAction
    kind: McpCredentialKind | None = None
    bearer_token: SecretStr | None = None
    headers: dict[str, SecretStr] | None = None

    @model_validator(mode="after")
    def validate_shape(self) -> McpCredentialUpdateBody:
        if self.action is not McpCredentialAction.REPLACE:
            if self.kind is not None or self.bearer_token is not None or self.headers is not None:
                raise ValueError("保留或清空 MCP 凭据时不能提供新值")
            return self
        if self.kind is McpCredentialKind.BEARER:
            if self.bearer_token is None or self.headers is not None:
                raise ValueError("Bearer 凭据必须且只能提供 bearer_token")
            return self
        if self.kind is McpCredentialKind.CUSTOM_HEADERS:
            if self.headers is None or self.bearer_token is not None:
                raise ValueError("自定义 Header 凭据必须且只能提供 headers")
            return self
        raise ValueError("替换 MCP 凭据时必须提供 kind")


class MaskedMcpCredentialResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: McpCredentialKind
    bearer_token: str | None
    headers: dict[str, str]


class McpCredentialSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: UUID
    configured: bool
    credential: MaskedMcpCredentialResponse | None
    updated_at: datetime | None


class ManagedHttpSourceBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=1_000)
    base_url: str = Field(min_length=1, max_length=2_048)
    enabled: bool = True


class ManagedHttpParameterBindingBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    argument_name: str = Field(min_length=1, max_length=128)
    location: ManagedHttpParameterLocation
    target_name: str = Field(min_length=1, max_length=128)


class ManagedHttpCapabilityBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    remote_name: str = Field(min_length=1, max_length=128)
    display_name: str = Field(min_length=1, max_length=128)
    description: str = Field(min_length=1, max_length=1_000)
    input_schema: dict[str, object]
    method: str = Field(min_length=3, max_length=6)
    path_template: str = Field(min_length=1, max_length=MANAGED_HTTP_PATH_MAX_LENGTH)
    parameter_bindings: list[ManagedHttpParameterBindingBody] = Field(
        max_length=MANAGED_HTTP_PARAMETER_MAX_ITEMS
    )
    timeout_seconds: int = Field(ge=1, le=MANAGED_HTTP_TIMEOUT_MAX_SECONDS)
    response_json_pointer: str | None = Field(
        default=None,
        max_length=MANAGED_HTTP_RESPONSE_POINTER_MAX_LENGTH,
    )
    enabled: bool = True


class ManagedHttpCapabilityResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    source_id: UUID
    remote_name: str
    display_name: str
    description: str
    input_schema: dict[str, object]
    schema_fingerprint: str
    method: str
    path_template: str
    parameter_bindings: list[ManagedHttpParameterBindingBody]
    timeout_seconds: int
    response_json_pointer: str | None
    enabled: bool
    created_at: datetime
    updated_at: datetime


class ManagedHttpSourceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    name: str
    description: str
    base_url: str
    enabled: bool
    capabilities: list[ManagedHttpCapabilityResponse]
    created_at: datetime
    updated_at: datetime


class ManagedHttpSourceListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ManagedHttpSourceResponse]


class ManagedHttpDiscoveredToolResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capability_id: UUID
    name: str
    display_name: str
    description: str
    input_schema: dict[str, object]
    schema_fingerprint: str


class ManagedHttpDiscoveryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: UUID
    tools: list[ManagedHttpDiscoveredToolResponse]


class ManagedHttpTestCallBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    arguments: dict[str, object]


class ManagedHttpTestCallResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capability_id: UUID
    output: dict[str, object]


class ManagedHttpOpenApiDraftResponse(ManagedHttpCapabilityBody):
    description: str = Field(default="", max_length=1_000)
    operation_key: str
    issues: list[str]


class ManagedHttpOpenApiPreviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    version: str
    drafts: list[ManagedHttpOpenApiDraftResponse]
    existing_remote_names: list[str]


class ManagedHttpOpenApiImportBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capabilities: list[ManagedHttpCapabilityBody] = Field(
        min_length=1,
        max_length=OPENAPI_MAX_OPERATIONS,
    )


class ManagedHttpOpenApiImportResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ManagedHttpCapabilityResponse]


def tool_catalog_response(catalog: ToolCatalog) -> ToolCatalogResponse:
    return ToolCatalogResponse(
        sources=[McpSourceResponse.model_validate(value) for value in catalog.sources],
        capabilities=[
            ToolCapabilityResponse.model_validate(value) for value in catalog.capabilities
        ],
        collections=[
            ToolCollectionResponse(
                id=value.id,
                name=value.name,
                description=value.description,
                source_ids=list(value.source_ids),
                created_at=value.created_at,
                updated_at=value.updated_at,
            )
            for value in catalog.collections
        ],
    )


def tool_grant_selection(body: ToolGrantSelectionBody) -> ToolGrantSelection:
    return ToolGrantSelection(
        collection_ids=tuple(body.collection_ids),
        capability_ids=tuple(body.capability_ids),
    )


def tool_grant_response(snapshot: ToolGrantSnapshot) -> ToolGrantResponse:
    return ToolGrantResponse(
        target_type=snapshot.target_type,
        target_id=snapshot.target_id,
        collection_ids=list(snapshot.collection_ids),
        capability_ids=list(snapshot.capability_ids),
    )


def mcp_credential_command(body: McpCredentialUpdateBody) -> McpCredentialCommand:
    credential: McpCredential | None = None
    if body.action is McpCredentialAction.REPLACE:
        if body.kind is McpCredentialKind.BEARER and body.bearer_token is not None:
            credential = McpCredential.bearer(body.bearer_token.get_secret_value())
        elif body.kind is McpCredentialKind.CUSTOM_HEADERS and body.headers is not None:
            credential = McpCredential.custom_headers(
                {name: value.get_secret_value() for name, value in body.headers.items()}
            )
    return McpCredentialCommand(action=body.action, credential=credential)


def mcp_credential_summary_response(
    summary: McpCredentialSummary,
) -> McpCredentialSummaryResponse:
    credential = summary.credential
    return McpCredentialSummaryResponse(
        source_id=summary.source_id,
        configured=summary.configured,
        credential=(
            MaskedMcpCredentialResponse(
                kind=credential.kind,
                bearer_token=credential.bearer_token,
                headers=dict(credential.headers),
            )
            if credential is not None
            else None
        ),
        updated_at=summary.updated_at,
    )


def managed_http_source_command(body: ManagedHttpSourceBody) -> ManagedHttpSourceCommand:
    return ManagedHttpSourceCommand(
        name=body.name,
        description=body.description,
        base_url=body.base_url,
        enabled=body.enabled,
    )


def managed_http_capability_command(
    body: ManagedHttpCapabilityBody,
) -> ManagedHttpCapabilityCommand:
    return ManagedHttpCapabilityCommand(
        remote_name=body.remote_name,
        display_name=body.display_name,
        description=body.description,
        input_schema=body.input_schema,
        method=body.method,
        path_template=body.path_template,
        parameter_bindings=tuple(
            ManagedHttpParameterBinding(
                argument_name=value.argument_name,
                location=value.location,
                target_name=value.target_name,
            )
            for value in body.parameter_bindings
        ),
        timeout_seconds=body.timeout_seconds,
        response_json_pointer=body.response_json_pointer,
        enabled=body.enabled,
    )


def managed_http_capability_response(
    managed: ManagedHttpCapability,
) -> ManagedHttpCapabilityResponse:
    capability = managed.capability
    return ManagedHttpCapabilityResponse(
        id=capability.id,
        source_id=capability.source_id,
        remote_name=capability.remote_name,
        display_name=capability.display_name,
        description=capability.description,
        input_schema=capability.input_schema,
        schema_fingerprint=capability.schema_fingerprint,
        method=managed.method,
        path_template=managed.path_template,
        parameter_bindings=[
            ManagedHttpParameterBindingBody(
                argument_name=value.argument_name,
                location=value.location,
                target_name=value.target_name,
            )
            for value in managed.parameter_bindings
        ],
        timeout_seconds=managed.timeout_seconds,
        response_json_pointer=managed.response_json_pointer,
        enabled=capability.status is ToolCapabilityStatus.ACTIVE,
        created_at=capability.created_at,
        updated_at=capability.updated_at,
    )


def managed_http_source_response(
    snapshot: ManagedHttpRuntimeSnapshot,
) -> ManagedHttpSourceResponse:
    source = snapshot.source
    if source.endpoint_url is None:
        raise ValueError("托管 HTTP MCP 缺少 Base URL")
    return ManagedHttpSourceResponse(
        id=source.id,
        name=source.name,
        description=source.description,
        base_url=source.endpoint_url,
        enabled=source.status is McpSourceStatus.READY,
        capabilities=[
            managed_http_capability_response(value) for value in snapshot.capabilities
        ],
        created_at=source.created_at,
        updated_at=source.updated_at,
    )


def managed_http_openapi_preview_response(
    preview: ManagedHttpOpenApiPreview,
    existing_remote_names: list[str],
) -> ManagedHttpOpenApiPreviewResponse:
    return ManagedHttpOpenApiPreviewResponse(
        title=preview.title,
        version=preview.version,
        drafts=[managed_http_openapi_draft_response(draft) for draft in preview.drafts],
        existing_remote_names=existing_remote_names,
    )


def managed_http_openapi_draft_response(
    draft: ManagedHttpOpenApiDraft,
) -> ManagedHttpOpenApiDraftResponse:
    return ManagedHttpOpenApiDraftResponse(
        operation_key=draft.operation_key,
        remote_name=draft.remote_name,
        display_name=draft.display_name,
        description=draft.description,
        input_schema=draft.input_schema,
        method=draft.method,
        path_template=draft.path_template,
        parameter_bindings=[
            ManagedHttpParameterBindingBody(
                argument_name=binding.argument_name,
                location=binding.location,
                target_name=binding.target_name,
            )
            for binding in draft.parameter_bindings
        ],
        timeout_seconds=draft.timeout_seconds,
        response_json_pointer=draft.response_json_pointer,
        enabled=draft.enabled,
        issues=list(draft.issues),
    )


__all__ = [
    "ManagedHttpCapabilityBody",
    "ManagedHttpCapabilityResponse",
    "ManagedHttpDiscoveredToolResponse",
    "ManagedHttpDiscoveryResponse",
    "ManagedHttpOpenApiDraftResponse",
    "ManagedHttpOpenApiImportBody",
    "ManagedHttpOpenApiImportResponse",
    "ManagedHttpOpenApiPreviewResponse",
    "ManagedHttpParameterBindingBody",
    "ManagedHttpSourceBody",
    "ManagedHttpSourceListResponse",
    "ManagedHttpSourceResponse",
    "ManagedHttpTestCallBody",
    "ManagedHttpTestCallResponse",
    "MaskedMcpCredentialResponse",
    "McpCredentialSummaryResponse",
    "McpCredentialUpdateBody",
    "McpSourceResponse",
    "ToolCapabilityResponse",
    "ToolCatalogResponse",
    "ToolCollectionResponse",
    "ToolGrantResponse",
    "ToolGrantSelectionBody",
    "managed_http_capability_command",
    "managed_http_capability_response",
    "managed_http_openapi_preview_response",
    "managed_http_source_command",
    "managed_http_source_response",
    "mcp_credential_command",
    "mcp_credential_summary_response",
    "tool_catalog_response",
    "tool_grant_response",
    "tool_grant_selection",
]
