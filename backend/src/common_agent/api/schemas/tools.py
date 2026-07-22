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


__all__ = [
    "MaskedMcpCredentialResponse",
    "McpCredentialSummaryResponse",
    "McpCredentialUpdateBody",
    "McpSourceResponse",
    "ToolCapabilityResponse",
    "ToolCatalogResponse",
    "ToolCollectionResponse",
    "ToolGrantResponse",
    "ToolGrantSelectionBody",
    "mcp_credential_command",
    "mcp_credential_summary_response",
    "tool_catalog_response",
    "tool_grant_response",
    "tool_grant_selection",
]
