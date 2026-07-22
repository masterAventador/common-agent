from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from urllib.parse import urlsplit
from uuid import UUID, uuid4

MCP_SOURCE_NAME_MAX_LENGTH = 128
MCP_SOURCE_DESCRIPTION_MAX_LENGTH = 1_000
MCP_SOURCE_ENDPOINT_MAX_LENGTH = 2_048
TOOL_CAPABILITY_REMOTE_NAME_MAX_LENGTH = 128
TOOL_CAPABILITY_DISPLAY_NAME_MAX_LENGTH = 128
TOOL_CAPABILITY_DESCRIPTION_MAX_LENGTH = 1_000
TOOL_CAPABILITY_SCHEMA_MAX_BYTES = 65_536
TOOL_COLLECTION_NAME_MAX_LENGTH = 128
TOOL_COLLECTION_DESCRIPTION_MAX_LENGTH = 1_000
TOOL_COLLECTION_SOURCE_MAX_ITEMS = 100
TOOL_GRANT_COLLECTION_MAX_ITEMS = 100
TOOL_GRANT_CAPABILITY_MAX_ITEMS = 500
TOOL_CALL_ARGUMENTS_MAX_BYTES = 65_536
TOOL_CALL_OUTPUT_MAX_BYTES = 1_000_000


class ToolValidationError(ValueError):
    def __init__(self, field: str, reason: str) -> None:
        self.field = field
        self.reason = reason
        super().__init__(f"工具字段 {field} {reason}")


class McpSourceType(StrEnum):
    PLATFORM = "platform"
    MANAGED_HTTP = "managed_http"
    EXTERNAL = "external"


class McpSourceStatus(StrEnum):
    DRAFT = "draft"
    READY = "ready"
    UNAVAILABLE = "unavailable"
    DISABLED = "disabled"


class ToolCapabilityStatus(StrEnum):
    ACTIVE = "active"
    UNAVAILABLE = "unavailable"
    DISABLED = "disabled"


class ToolGrantTargetType(StrEnum):
    EMPLOYEE = "employee"
    CONVERSATION = "conversation"


@dataclass(frozen=True, slots=True)
class ToolGrantTarget:
    target_type: ToolGrantTargetType
    target_id: UUID

    def __post_init__(self) -> None:
        if not isinstance(self.target_type, ToolGrantTargetType):
            raise ToolValidationError("target_type", "不是支持的授权目标")
        _uuid("target_id", self.target_id)


class ToolCallStatus(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"


class ToolCallErrorCode(StrEnum):
    UNAUTHORIZED = "tool_unauthorized"
    SOURCE_UNAVAILABLE = "tool_source_unavailable"
    CAPABILITY_UNAVAILABLE = "tool_capability_unavailable"
    INVALID_ARGUMENTS = "tool_invalid_arguments"
    TIMEOUT = "tool_timeout"
    RESPONSE_TOO_LARGE = "tool_response_too_large"
    PROTOCOL_ERROR = "tool_protocol_error"
    RESULT_UNKNOWN = "tool_result_unknown"
    EXECUTION_FAILED = "tool_execution_failed"


@dataclass(frozen=True, slots=True)
class McpSource:
    id: UUID
    name: str
    description: str
    source_type: McpSourceType
    endpoint_url: str | None
    status: McpSourceStatus
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        _uuid("id", self.id)
        object.__setattr__(
            self,
            "name",
            _required_text("name", self.name, MCP_SOURCE_NAME_MAX_LENGTH),
        )
        object.__setattr__(
            self,
            "description",
            _optional_text(
                "description",
                self.description,
                MCP_SOURCE_DESCRIPTION_MAX_LENGTH,
            ),
        )
        if not isinstance(self.source_type, McpSourceType):
            raise ToolValidationError("source_type", "不是支持的 MCP 来源类型")
        object.__setattr__(
            self,
            "endpoint_url",
            _endpoint(self.source_type, self.endpoint_url),
        )
        if not isinstance(self.status, McpSourceStatus):
            raise ToolValidationError("status", "不是支持的 MCP 来源状态")
        _timestamps(self.created_at, self.updated_at)

    @classmethod
    def create(
        cls,
        *,
        name: str,
        source_type: McpSourceType,
        endpoint_url: str | None = None,
        description: str = "",
        status: McpSourceStatus = McpSourceStatus.DRAFT,
        source_id: UUID | None = None,
        now: datetime | None = None,
    ) -> McpSource:
        created_at = now or datetime.now(UTC)
        return cls(
            id=source_id or uuid4(),
            name=name,
            description=description,
            source_type=source_type,
            endpoint_url=endpoint_url,
            status=status,
            created_at=created_at,
            updated_at=created_at,
        )


@dataclass(frozen=True, slots=True)
class ToolCapability:
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

    def __post_init__(self) -> None:
        _uuid("id", self.id)
        _uuid("source_id", self.source_id)
        object.__setattr__(
            self,
            "remote_name",
            _required_text(
                "remote_name",
                self.remote_name,
                TOOL_CAPABILITY_REMOTE_NAME_MAX_LENGTH,
            ),
        )
        object.__setattr__(
            self,
            "display_name",
            _required_text(
                "display_name",
                self.display_name,
                TOOL_CAPABILITY_DISPLAY_NAME_MAX_LENGTH,
            ),
        )
        object.__setattr__(
            self,
            "description",
            _optional_text(
                "description",
                self.description,
                TOOL_CAPABILITY_DESCRIPTION_MAX_LENGTH,
            ),
        )
        schema, fingerprint = normalize_input_schema(self.input_schema)
        if self.schema_fingerprint != fingerprint:
            raise ToolValidationError("schema_fingerprint", "与输入 Schema 不匹配")
        object.__setattr__(self, "input_schema", schema)
        if not isinstance(self.status, ToolCapabilityStatus):
            raise ToolValidationError("status", "不是支持的工具能力状态")
        _timestamps(self.created_at, self.updated_at)

    @classmethod
    def create(
        cls,
        *,
        source_id: UUID,
        remote_name: str,
        display_name: str,
        input_schema: dict[str, object],
        description: str = "",
        status: ToolCapabilityStatus = ToolCapabilityStatus.ACTIVE,
        capability_id: UUID | None = None,
        now: datetime | None = None,
    ) -> ToolCapability:
        created_at = now or datetime.now(UTC)
        normalized_schema, fingerprint = normalize_input_schema(input_schema)
        return cls(
            id=capability_id or uuid4(),
            source_id=source_id,
            remote_name=remote_name,
            display_name=display_name,
            description=description,
            input_schema=normalized_schema,
            schema_fingerprint=fingerprint,
            status=status,
            created_at=created_at,
            updated_at=created_at,
        )


@dataclass(frozen=True, slots=True)
class ToolCollection:
    id: UUID
    name: str
    description: str
    source_ids: tuple[UUID, ...]
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        _uuid("id", self.id)
        object.__setattr__(
            self,
            "name",
            _required_text("name", self.name, TOOL_COLLECTION_NAME_MAX_LENGTH),
        )
        object.__setattr__(
            self,
            "description",
            _optional_text(
                "description",
                self.description,
                TOOL_COLLECTION_DESCRIPTION_MAX_LENGTH,
            ),
        )
        object.__setattr__(
            self,
            "source_ids",
            _uuid_tuple(
                "source_ids",
                self.source_ids,
                maximum=TOOL_COLLECTION_SOURCE_MAX_ITEMS,
            ),
        )
        _timestamps(self.created_at, self.updated_at)

    @classmethod
    def create(
        cls,
        *,
        name: str,
        source_ids: Iterable[UUID],
        description: str = "",
        collection_id: UUID | None = None,
        now: datetime | None = None,
    ) -> ToolCollection:
        created_at = now or datetime.now(UTC)
        return cls(
            id=collection_id or uuid4(),
            name=name,
            description=description,
            source_ids=tuple(source_ids),
            created_at=created_at,
            updated_at=created_at,
        )


@dataclass(frozen=True, slots=True)
class ToolCatalog:
    sources: tuple[McpSource, ...] = ()
    capabilities: tuple[ToolCapability, ...] = ()
    collections: tuple[ToolCollection, ...] = ()


@dataclass(frozen=True, slots=True)
class ToolRuntimeCapability:
    source: McpSource
    capability: ToolCapability

    def __post_init__(self) -> None:
        if self.capability.source_id != self.source.id:
            raise ToolValidationError("source_id", "运行时能力与 MCP 来源不匹配")


@dataclass(frozen=True, slots=True)
class ToolGrantSelection:
    collection_ids: tuple[UUID, ...] = ()
    capability_ids: tuple[UUID, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "collection_ids",
            _uuid_tuple(
                "collection_ids",
                self.collection_ids,
                maximum=TOOL_GRANT_COLLECTION_MAX_ITEMS,
            ),
        )
        object.__setattr__(
            self,
            "capability_ids",
            _uuid_tuple(
                "capability_ids",
                self.capability_ids,
                maximum=TOOL_GRANT_CAPABILITY_MAX_ITEMS,
            ),
        )


@dataclass(frozen=True, slots=True)
class ToolGrantSnapshot:
    target_type: ToolGrantTargetType
    target_id: UUID
    collection_ids: tuple[UUID, ...] = ()
    capability_ids: tuple[UUID, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.target_type, ToolGrantTargetType):
            raise ToolValidationError("target_type", "不是支持的授权目标")
        _uuid("target_id", self.target_id)
        selection = ToolGrantSelection(
            collection_ids=self.collection_ids,
            capability_ids=self.capability_ids,
        )
        object.__setattr__(self, "collection_ids", selection.collection_ids)
        object.__setattr__(self, "capability_ids", selection.capability_ids)


@dataclass(frozen=True, slots=True)
class ToolCallRequest:
    tool_call_id: UUID
    capability_id: UUID
    arguments: dict[str, object] = field(repr=False)

    def __post_init__(self) -> None:
        _uuid("tool_call_id", self.tool_call_id)
        _uuid("capability_id", self.capability_id)
        object.__setattr__(
            self,
            "arguments",
            _json_object(
                "arguments",
                self.arguments,
                maximum_bytes=TOOL_CALL_ARGUMENTS_MAX_BYTES,
            ),
        )


@dataclass(frozen=True, slots=True)
class ToolCallResult:
    tool_call_id: UUID
    capability_id: UUID
    status: ToolCallStatus
    output: dict[str, object] | None = field(default=None, repr=False)
    error_code: ToolCallErrorCode | None = None

    def __post_init__(self) -> None:
        _uuid("tool_call_id", self.tool_call_id)
        _uuid("capability_id", self.capability_id)
        if not isinstance(self.status, ToolCallStatus):
            raise ToolValidationError("status", "不是支持的工具调用状态")
        if self.status is ToolCallStatus.COMPLETED:
            if self.error_code is not None:
                raise ToolValidationError("error_code", "成功结果不能包含错误码")
            if self.output is None:
                raise ToolValidationError("output", "成功结果必须包含输出对象")
            object.__setattr__(
                self,
                "output",
                _json_object(
                    "output",
                    self.output,
                    maximum_bytes=TOOL_CALL_OUTPUT_MAX_BYTES,
                ),
            )
            return
        if not isinstance(self.error_code, ToolCallErrorCode):
            raise ToolValidationError("error_code", "失败结果必须包含稳定错误码")
        if self.output is not None:
            raise ToolValidationError("error_code", "失败结果不能携带上游输出")


def normalize_input_schema(value: object) -> tuple[dict[str, object], str]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ToolValidationError("input_schema", "必须是 JSON 对象")
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise ToolValidationError("input_schema", "只能包含 JSON 值") from error
    if len(encoded) > TOOL_CAPABILITY_SCHEMA_MAX_BYTES:
        raise ToolValidationError(
            "input_schema",
            f"不能超过 {TOOL_CAPABILITY_SCHEMA_MAX_BYTES} 字节",
        )
    return deepcopy(value), hashlib.sha256(encoded).hexdigest()


def _json_object(
    field_name: str,
    value: object,
    *,
    maximum_bytes: int,
) -> dict[str, object]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ToolValidationError(field_name, "必须是 JSON 对象")
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise ToolValidationError(field_name, "只能包含 JSON 值") from error
    if len(encoded) > maximum_bytes:
        raise ToolValidationError(field_name, f"不能超过 {maximum_bytes} 字节")
    return deepcopy(value)


def _endpoint(source_type: McpSourceType, value: object) -> str | None:
    if source_type is McpSourceType.PLATFORM:
        if value is not None:
            raise ToolValidationError("endpoint_url", "平台来源不能设置网络地址")
        return None
    endpoint = _required_text("endpoint_url", value, MCP_SOURCE_ENDPOINT_MAX_LENGTH)
    parsed = urlsplit(endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ToolValidationError("endpoint_url", "必须是绝对 HTTP(S) URL")
    if (
        parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ToolValidationError("endpoint_url", "不能包含用户信息、查询串或片段")
    return endpoint


def _uuid_tuple(field: str, values: Iterable[UUID], *, maximum: int) -> tuple[UUID, ...]:
    result = tuple(values)
    if any(not isinstance(value, UUID) for value in result):
        raise ToolValidationError(field, "必须只包含 UUID")
    if len(set(result)) != len(result):
        raise ToolValidationError(field, "不能包含重复项")
    if len(result) > maximum:
        raise ToolValidationError(field, f"不能超过 {maximum} 项")
    return result


def _uuid(field: str, value: object) -> None:
    if not isinstance(value, UUID):
        raise ToolValidationError(field, "必须是 UUID")


def _required_text(field: str, value: object, maximum: int) -> str:
    if not isinstance(value, str):
        raise ToolValidationError(field, "必须是字符串")
    normalized = value.strip()
    if not normalized:
        raise ToolValidationError(field, "不能为空")
    if len(normalized) > maximum:
        raise ToolValidationError(field, f"不能超过 {maximum} 个字符")
    if any(character in normalized for character in "\r\n\0"):
        raise ToolValidationError(field, "不能包含控制字符")
    return normalized


def _optional_text(field: str, value: object, maximum: int) -> str:
    if not isinstance(value, str):
        raise ToolValidationError(field, "必须是字符串")
    normalized = value.strip()
    if len(normalized) > maximum:
        raise ToolValidationError(field, f"不能超过 {maximum} 个字符")
    if any(character in normalized for character in "\r\n\0"):
        raise ToolValidationError(field, "不能包含控制字符")
    return normalized


def _timestamps(created_at: object, updated_at: object) -> None:
    if (
        not isinstance(created_at, datetime)
        or created_at.tzinfo is None
        or created_at.utcoffset() != UTC.utcoffset(None)
    ):
        raise ToolValidationError("created_at", "必须使用 UTC 时间")
    if (
        not isinstance(updated_at, datetime)
        or updated_at.tzinfo is None
        or updated_at.utcoffset() != UTC.utcoffset(None)
    ):
        raise ToolValidationError("updated_at", "必须使用 UTC 时间")
    if updated_at < created_at:
        raise ToolValidationError("updated_at", "不能早于创建时间")


__all__ = [
    "MCP_SOURCE_DESCRIPTION_MAX_LENGTH",
    "MCP_SOURCE_ENDPOINT_MAX_LENGTH",
    "MCP_SOURCE_NAME_MAX_LENGTH",
    "TOOL_CALL_ARGUMENTS_MAX_BYTES",
    "TOOL_CALL_OUTPUT_MAX_BYTES",
    "TOOL_CAPABILITY_DESCRIPTION_MAX_LENGTH",
    "TOOL_CAPABILITY_DISPLAY_NAME_MAX_LENGTH",
    "TOOL_CAPABILITY_REMOTE_NAME_MAX_LENGTH",
    "TOOL_COLLECTION_DESCRIPTION_MAX_LENGTH",
    "TOOL_COLLECTION_NAME_MAX_LENGTH",
    "TOOL_COLLECTION_SOURCE_MAX_ITEMS",
    "TOOL_GRANT_CAPABILITY_MAX_ITEMS",
    "TOOL_GRANT_COLLECTION_MAX_ITEMS",
    "McpSource",
    "McpSourceStatus",
    "McpSourceType",
    "ToolCallErrorCode",
    "ToolCallRequest",
    "ToolCallResult",
    "ToolCallStatus",
    "ToolCapability",
    "ToolCapabilityStatus",
    "ToolCatalog",
    "ToolCollection",
    "ToolGrantSelection",
    "ToolGrantSnapshot",
    "ToolGrantTarget",
    "ToolGrantTargetType",
    "ToolRuntimeCapability",
    "ToolValidationError",
    "normalize_input_schema",
]
