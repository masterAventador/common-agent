from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from types import MappingProxyType
from typing import cast
from urllib.parse import SplitResult, quote, unquote, urlencode, urlsplit, urlunsplit
from uuid import UUID

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from common_agent.tools.models import (
    McpSource,
    McpSourceStatus,
    McpSourceType,
    ToolCapability,
    ToolCapabilityStatus,
)

MANAGED_HTTP_PATH_MAX_LENGTH = 2_048
MANAGED_HTTP_TIMEOUT_MAX_SECONDS = 300
MANAGED_HTTP_PARAMETER_MAX_ITEMS = 256
MANAGED_HTTP_RESPONSE_POINTER_MAX_LENGTH = 1_024

_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE"})
_TOOL_NAME = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,126}[A-Za-z0-9])?$")
_TOKEN = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")
_PATH_PARAMETER = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
_PROTECTED_HEADERS = frozenset(
    {
        "authorization",
        "connection",
        "content-length",
        "content-type",
        "cookie",
        "host",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
    }
)


class ManagedHttpValidationError(ValueError):
    def __init__(self, field: str, reason: str) -> None:
        self.field = field
        self.reason = reason
        super().__init__(f"托管 HTTP 字段 {field} {reason}")


class ManagedHttpParameterLocation(StrEnum):
    PATH = "path"
    QUERY = "query"
    HEADER = "header"
    COOKIE = "cookie"
    BODY = "body"


@dataclass(frozen=True, slots=True)
class ManagedHttpParameterBinding:
    argument_name: str
    location: ManagedHttpParameterLocation
    target_name: str

    def __post_init__(self) -> None:
        _name("argument_name", self.argument_name)
        if not isinstance(self.location, ManagedHttpParameterLocation):
            raise ManagedHttpValidationError("parameter_bindings", "包含不支持的参数位置")
        _name(
            "target_name",
            self.target_name,
            token=self.location is not ManagedHttpParameterLocation.PATH,
        )


@dataclass(frozen=True, slots=True)
class ManagedHttpCapability:
    capability: ToolCapability
    method: str
    path_template: str
    parameter_bindings: tuple[ManagedHttpParameterBinding, ...]
    timeout_seconds: int
    response_json_pointer: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.capability, ToolCapability):
            raise ManagedHttpValidationError("capability", "必须是工具能力")
        if not _TOOL_NAME.fullmatch(self.capability.remote_name):
            raise ManagedHttpValidationError("remote_name", "不是合法的 MCP 工具名称")
        method = self.method.strip().upper() if isinstance(self.method, str) else ""
        if method not in _METHODS:
            raise ManagedHttpValidationError("method", "只支持 GET、POST、PUT、PATCH、DELETE")
        object.__setattr__(self, "method", method)
        path_parameters = _path_template(self.path_template)
        bindings = tuple(self.parameter_bindings)
        if len(bindings) > MANAGED_HTTP_PARAMETER_MAX_ITEMS:
            raise ManagedHttpValidationError(
                "parameter_bindings",
                f"不能超过 {MANAGED_HTTP_PARAMETER_MAX_ITEMS} 项",
            )
        if any(not isinstance(binding, ManagedHttpParameterBinding) for binding in bindings):
            raise ManagedHttpValidationError("parameter_bindings", "包含不合法的参数映射")
        object.__setattr__(self, "parameter_bindings", bindings)
        _validate_schema_and_bindings(self.capability, bindings, path_parameters)
        if (
            not isinstance(self.timeout_seconds, int)
            or isinstance(self.timeout_seconds, bool)
            or not 1 <= self.timeout_seconds <= MANAGED_HTTP_TIMEOUT_MAX_SECONDS
        ):
            raise ManagedHttpValidationError(
                "timeout_seconds",
                f"必须在 1 到 {MANAGED_HTTP_TIMEOUT_MAX_SECONDS} 秒之间",
            )
        object.__setattr__(
            self,
            "response_json_pointer",
            _response_pointer(self.response_json_pointer),
        )


@dataclass(frozen=True, slots=True)
class ManagedHttpSourceCommand:
    name: str
    description: str
    base_url: str
    enabled: bool

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise ManagedHttpValidationError("enabled", "必须是布尔值")
        source = McpSource.create(
            name=self.name,
            description=self.description,
            source_type=McpSourceType.MANAGED_HTTP,
            endpoint_url=self.base_url,
            status=(McpSourceStatus.READY if self.enabled else McpSourceStatus.DISABLED),
        )
        parsed = _base_url(cast(str, source.endpoint_url))
        normalized_path = parsed.path.rstrip("/")
        object.__setattr__(
            self,
            "base_url",
            urlunsplit((parsed.scheme, parsed.netloc, normalized_path, "", "")),
        )

    def create(self, *, now: datetime | None = None) -> McpSource:
        return McpSource.create(
            name=self.name,
            description=self.description,
            source_type=McpSourceType.MANAGED_HTTP,
            endpoint_url=self.base_url,
            status=(McpSourceStatus.READY if self.enabled else McpSourceStatus.DISABLED),
            now=now,
        )

    def replace(self, source: McpSource, *, now: datetime | None = None) -> McpSource:
        return McpSource(
            id=source.id,
            name=self.name,
            description=self.description,
            source_type=McpSourceType.MANAGED_HTTP,
            endpoint_url=self.base_url,
            status=(McpSourceStatus.READY if self.enabled else McpSourceStatus.DISABLED),
            created_at=source.created_at,
            updated_at=now or datetime.now(UTC),
        )


@dataclass(frozen=True, slots=True)
class ManagedHttpCapabilityCommand:
    remote_name: str
    display_name: str
    description: str
    input_schema: dict[str, object]
    method: str
    path_template: str
    parameter_bindings: tuple[ManagedHttpParameterBinding, ...]
    timeout_seconds: int
    response_json_pointer: str | None
    enabled: bool

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise ManagedHttpValidationError("enabled", "必须是布尔值")

    def create(
        self,
        source_id: UUID,
        *,
        now: datetime | None = None,
    ) -> ManagedHttpCapability:
        return self._build(source_id, now=now)

    def replace(
        self,
        existing: ManagedHttpCapability,
        *,
        now: datetime | None = None,
    ) -> ManagedHttpCapability:
        return self._build(
            existing.capability.source_id,
            capability_id=existing.capability.id,
            created_at=existing.capability.created_at,
            now=now,
        )

    def _build(
        self,
        source_id: UUID,
        *,
        capability_id: UUID | None = None,
        created_at: datetime | None = None,
        now: datetime | None = None,
    ) -> ManagedHttpCapability:
        timestamp = now or datetime.now(UTC)
        capability = ToolCapability.create(
            source_id=source_id,
            remote_name=self.remote_name,
            display_name=self.display_name,
            description=self.description,
            input_schema=self.input_schema,
            status=(
                ToolCapabilityStatus.ACTIVE
                if self.enabled
                else ToolCapabilityStatus.DISABLED
            ),
            capability_id=capability_id,
            now=created_at or timestamp,
        )
        if created_at is not None:
            capability = ToolCapability(
                id=capability.id,
                source_id=capability.source_id,
                remote_name=capability.remote_name,
                display_name=capability.display_name,
                description=capability.description,
                input_schema=capability.input_schema,
                schema_fingerprint=capability.schema_fingerprint,
                status=capability.status,
                created_at=created_at,
                updated_at=timestamp,
            )
        return ManagedHttpCapability(
            capability=capability,
            method=self.method,
            path_template=self.path_template,
            parameter_bindings=self.parameter_bindings,
            timeout_seconds=self.timeout_seconds,
            response_json_pointer=self.response_json_pointer,
        )


@dataclass(frozen=True, slots=True)
class ManagedHttpRequest:
    method: str
    url: str = field(repr=False)
    headers: dict[str, str] = field(repr=False)
    body: bytes | None = field(repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "headers", MappingProxyType(dict(self.headers)))


@dataclass(frozen=True, slots=True)
class ManagedHttpRuntimeSnapshot:
    source: McpSource
    capabilities: tuple[ManagedHttpCapability, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.source, McpSource):
            raise ManagedHttpValidationError("source", "必须是 MCP 来源")
        if self.source.source_type is not McpSourceType.MANAGED_HTTP:
            raise ManagedHttpValidationError("source", "必须是托管 HTTP MCP 来源")
        capabilities = tuple(self.capabilities)
        if any(
            not isinstance(item, ManagedHttpCapability)
            or item.capability.source_id != self.source.id
            for item in capabilities
        ):
            raise ManagedHttpValidationError("capabilities", "包含其他来源或不合法的能力")
        names = [item.capability.remote_name for item in capabilities]
        if len(names) != len(set(names)):
            raise ManagedHttpValidationError("capabilities", "能力名称不能重复")
        object.__setattr__(self, "capabilities", capabilities)


def build_managed_http_request(
    base_url: str,
    managed: ManagedHttpCapability,
    arguments: dict[str, object],
) -> ManagedHttpRequest:
    parsed = _base_url(base_url)
    if not isinstance(arguments, dict) or any(not isinstance(key, str) for key in arguments):
        raise ManagedHttpValidationError("arguments", "必须是 JSON 对象")
    bindings = {binding.argument_name: binding for binding in managed.parameter_bindings}
    unknown = set(arguments) - set(bindings)
    if unknown:
        raise ManagedHttpValidationError("arguments", "包含未映射参数")
    required = managed.capability.input_schema.get("required", [])
    if not isinstance(required, list):
        raise ManagedHttpValidationError("input_schema", "required 必须是数组")
    if any(name not in arguments for name in required):
        raise ManagedHttpValidationError("arguments", "缺少必填参数")

    rendered_path = managed.path_template
    query: list[tuple[str, str]] = []
    headers: dict[str, str] = {}
    cookies: list[tuple[str, str]] = []
    body_values: dict[str, object] = {}
    for argument_name, value in arguments.items():
        binding = bindings[argument_name]
        if binding.location is ManagedHttpParameterLocation.PATH:
            rendered_path = rendered_path.replace(
                "{" + binding.target_name + "}",
                quote(_scalar(value, argument_name), safe=""),
            )
        elif binding.location is ManagedHttpParameterLocation.QUERY:
            values = value if isinstance(value, list) else [value]
            for item in values:
                query.append((binding.target_name, _scalar(item, argument_name)))
        elif binding.location is ManagedHttpParameterLocation.HEADER:
            headers[binding.target_name] = _header_value(value, argument_name)
        elif binding.location is ManagedHttpParameterLocation.COOKIE:
            cookies.append((binding.target_name, quote(_scalar(value, argument_name), safe="")))
        else:
            body_values[binding.target_name] = value
    if "{" in rendered_path or "}" in rendered_path:
        raise ManagedHttpValidationError("arguments", "缺少路径参数")
    _safe_path("arguments", rendered_path)
    if cookies:
        headers["Cookie"] = "; ".join(f"{name}={value}" for name, value in cookies)
    body: bytes | None = None
    if body_values:
        try:
            body = json.dumps(
                body_values,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            ).encode("utf-8")
        except (TypeError, ValueError) as error:
            raise ManagedHttpValidationError("arguments", "请求体只能包含 JSON 值") from error
        headers["Content-Type"] = "application/json"

    base_path = parsed.path.rstrip("/")
    target_path = f"{base_path}{rendered_path}"
    url = urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            target_path,
            urlencode(query, doseq=True),
            "",
        )
    )
    return ManagedHttpRequest(
        method=managed.method,
        url=url,
        headers=dict(sorted(headers.items(), key=lambda item: item[0].lower())),
        body=body,
    )


def _validate_schema_and_bindings(
    capability: ToolCapability,
    bindings: tuple[ManagedHttpParameterBinding, ...],
    path_parameters: frozenset[str],
) -> None:
    schema = capability.input_schema
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError:
        raise ManagedHttpValidationError("input_schema", "必须是合法的 JSON Schema") from None
    properties = schema.get("properties")
    if schema.get("type") != "object" or not isinstance(properties, dict):
        raise ManagedHttpValidationError("input_schema", "必须是带 properties 的对象 Schema")
    if any(
        not isinstance(name, str) or not isinstance(value, dict)
        for name, value in properties.items()
    ):
        raise ManagedHttpValidationError("input_schema", "properties 不合法")
    missing_descriptions = sorted(
        name
        for name, value in properties.items()
        if not isinstance(value.get("description"), str) or not value["description"].strip()
    )
    if missing_descriptions:
        raise ManagedHttpValidationError(
            "input_schema",
            f"缺少参数含义: {', '.join(missing_descriptions)}",
        )
    argument_names = [binding.argument_name for binding in bindings]
    if len(argument_names) != len(set(argument_names)) or set(argument_names) != set(properties):
        raise ManagedHttpValidationError("parameter_bindings", "必须与 Schema 参数一一对应")
    target_keys = [(binding.location, binding.target_name.lower()) for binding in bindings]
    if len(target_keys) != len(set(target_keys)):
        raise ManagedHttpValidationError("parameter_bindings", "目标位置和名称不能重复")
    for binding in bindings:
        if (
            binding.location is ManagedHttpParameterLocation.HEADER
            and (
                binding.target_name.lower() in _PROTECTED_HEADERS
                or binding.target_name.lower().startswith("proxy-")
            )
        ):
            raise ManagedHttpValidationError("parameter_bindings", "不能覆盖认证或传输 Header")
    mapped_path = {
        binding.target_name
        for binding in bindings
        if binding.location is ManagedHttpParameterLocation.PATH
    }
    if mapped_path != path_parameters:
        raise ManagedHttpValidationError("parameter_bindings", "路径占位符必须精确映射")
    required = schema.get("required", [])
    if not isinstance(required, list) or any(not isinstance(name, str) for name in required):
        raise ManagedHttpValidationError("input_schema", "required 必须是字符串数组")
    if not mapped_path.issubset(set(required)):
        raise ManagedHttpValidationError("input_schema", "路径参数必须是必填参数")


def _base_url(value: object) -> SplitResult:
    if not isinstance(value, str) or len(value) > 2_048:
        raise ManagedHttpValidationError("base_url", "必须是绝对 HTTP(S) URL")
    parsed = urlsplit(value.strip())
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ManagedHttpValidationError("base_url", "必须是无用户信息、查询串和片段的绝对 URL")
    _safe_path("base_url", parsed.path or "/")
    return parsed


def _path_template(value: object) -> frozenset[str]:
    if (
        not isinstance(value, str)
        or not value.startswith("/")
        or len(value) > MANAGED_HTTP_PATH_MAX_LENGTH
    ):
        raise ManagedHttpValidationError("path_template", "必须是以 / 开头的相对业务路径")
    if "?" in value or "#" in value or "\\" in value or value.startswith("//"):
        raise ManagedHttpValidationError("path_template", "不能包含来源、查询串或片段")
    _safe_path("path_template", value)
    parameters = _PATH_PARAMETER.findall(value)
    if len(parameters) != len(set(parameters)):
        raise ManagedHttpValidationError("path_template", "路径占位符不能重复")
    remainder = _PATH_PARAMETER.sub("", value)
    if "{" in remainder or "}" in remainder:
        raise ManagedHttpValidationError("path_template", "路径占位符格式不合法")
    return frozenset(parameters)


def _safe_path(field_name: str, path: str) -> None:
    decoded = unquote(path)
    if any(segment in {".", ".."} for segment in decoded.split("/")) or "\0" in decoded:
        raise ManagedHttpValidationError(field_name, "不能包含路径穿越片段")


def _response_pointer(value: object) -> str | None:
    if value is None or value == "":
        return None
    if (
        not isinstance(value, str)
        or not value.startswith("/")
        or len(value) > MANAGED_HTTP_RESPONSE_POINTER_MAX_LENGTH
    ):
        raise ManagedHttpValidationError("response_json_pointer", "必须是 RFC 6901 JSON Pointer")
    for token in value.split("/")[1:]:
        if re.search(r"~(?![01])", token):
            raise ManagedHttpValidationError("response_json_pointer", "包含不合法的转义")
    return value


def _name(field_name: str, value: object, *, token: bool = False) -> str:
    if not isinstance(value, str) or not value or len(value) > 128:
        raise ManagedHttpValidationError("parameter_bindings", f"{field_name} 不合法")
    if token and not _TOKEN.fullmatch(value):
        raise ManagedHttpValidationError("parameter_bindings", f"{field_name} 不是合法令牌")
    if not token and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ManagedHttpValidationError("parameter_bindings", f"{field_name} 不合法")
    return value


def _scalar(value: object, argument_name: str) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (str, int, float)) and not isinstance(value, bool):
        if isinstance(value, float) and not (-float("inf") < value < float("inf")):
            raise ManagedHttpValidationError("arguments", f"参数 {argument_name} 不是有限值")
        return str(value)
    raise ManagedHttpValidationError("arguments", f"参数 {argument_name} 必须是标量")


def _header_value(value: object, argument_name: str) -> str:
    result = _scalar(value, argument_name)
    if any(ord(character) < 32 or ord(character) == 127 for character in result):
        raise ManagedHttpValidationError("arguments", f"参数 {argument_name} 不能包含控制字符")
    return result


__all__ = [
    "MANAGED_HTTP_PARAMETER_MAX_ITEMS",
    "MANAGED_HTTP_PATH_MAX_LENGTH",
    "MANAGED_HTTP_RESPONSE_POINTER_MAX_LENGTH",
    "MANAGED_HTTP_TIMEOUT_MAX_SECONDS",
    "ManagedHttpCapability",
    "ManagedHttpParameterBinding",
    "ManagedHttpParameterLocation",
    "ManagedHttpRequest",
    "ManagedHttpRuntimeSnapshot",
    "ManagedHttpValidationError",
    "build_managed_http_request",
]
