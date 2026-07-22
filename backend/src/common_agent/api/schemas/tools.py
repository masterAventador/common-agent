from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

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


__all__ = [
    "McpSourceResponse",
    "ToolCapabilityResponse",
    "ToolCatalogResponse",
    "ToolCollectionResponse",
    "ToolGrantResponse",
    "ToolGrantSelectionBody",
    "tool_catalog_response",
    "tool_grant_response",
    "tool_grant_selection",
]
