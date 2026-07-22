from __future__ import annotations

import copy
import json
import re
from urllib.parse import unquote

import yaml
from yaml.events import AliasEvent

from common_agent.tools.managed_http import (
    ManagedHttpParameterBinding,
    ManagedHttpParameterLocation,
)
from common_agent.tools.openapi_import import (
    OPENAPI_MAX_DOCUMENT_DEPTH,
    OPENAPI_MAX_DOCUMENT_NODES,
    OPENAPI_MAX_FILE_BYTES,
    OPENAPI_MAX_OPERATIONS,
    OPENAPI_MAX_REFERENCE_DEPTH,
    ManagedHttpOpenApiDraft,
    ManagedHttpOpenApiPreview,
    OpenApiDocumentError,
    openapi_draft_issues,
)

_HTTP_METHODS = ("get", "post", "put", "patch", "delete")
_PARAMETER_LOCATIONS = {
    "path": ManagedHttpParameterLocation.PATH,
    "query": ManagedHttpParameterLocation.QUERY,
    "header": ManagedHttpParameterLocation.HEADER,
    "cookie": ManagedHttpParameterLocation.COOKIE,
}
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
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_VERSION = re.compile(r"^3\.(?:0|1)\.\d+(?:[-+].*)?$")
_PATH_PARAMETER = re.compile(r"\{([^{}]+)\}")


class _UniqueKeySafeLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(
    loader: _UniqueKeySafeLoader,
    node: yaml.nodes.MappingNode,
    deep: bool = False,
) -> dict[object, object]:
    loader.flatten_mapping(node)
    values: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            if key in values:
                raise OpenApiDocumentError("openapi_format_invalid", "OpenAPI 包含重复字段")
        except TypeError:
            raise OpenApiDocumentError(
                "openapi_format_invalid",
                "OpenAPI YAML 字段名必须是标量",
            ) from None
        values[key] = loader.construct_object(value_node, deep=deep)
    return values


_UniqueKeySafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


class ManagedHttpOpenApiParser:
    def parse(self, content: bytes, filename: str) -> ManagedHttpOpenApiPreview:
        document = _load_document(content, filename)
        _validate_complexity(document)
        version = document.get("openapi")
        if not isinstance(version, str) or not _VERSION.fullmatch(version):
            raise OpenApiDocumentError(
                "openapi_version_unsupported",
                "只支持 OpenAPI 3.0.x 或 3.1.x",
            )
        paths = document.get("paths")
        if not isinstance(paths, dict):
            raise OpenApiDocumentError("openapi_no_operations", "OpenAPI 缺少 paths")

        resolver = _ReferenceResolver(document)
        drafts: list[ManagedHttpOpenApiDraft] = []
        operation_ids: set[str] = set()
        tool_names: set[str] = set()
        for path, raw_path_item in paths.items():
            if not isinstance(path, str) or not isinstance(raw_path_item, dict):
                raise OpenApiDocumentError(
                    "openapi_format_invalid",
                    "OpenAPI paths 必须使用字符串路径和对象定义",
                )
            path_item = resolver.resolve_object(raw_path_item)
            for method in _HTTP_METHODS:
                operation = path_item.get(method)
                if operation is None:
                    continue
                if not isinstance(operation, dict):
                    raise OpenApiDocumentError(
                        "openapi_format_invalid",
                        f"{method.upper()} {path} 定义必须是对象",
                    )
                if len(drafts) >= OPENAPI_MAX_OPERATIONS:
                    raise OpenApiDocumentError(
                        "openapi_document_too_complex",
                        f"OpenAPI 接口不能超过 {OPENAPI_MAX_OPERATIONS} 个",
                    )
                operation_id = operation.get("operationId")
                if operation_id is not None and (
                    not isinstance(operation_id, str) or not operation_id.strip()
                ):
                    raise OpenApiDocumentError(
                        "openapi_format_invalid",
                        f"{method.upper()} {path} 的 operationId 不合法",
                    )
                raw_tool_name = (
                    operation_id.strip()
                    if isinstance(operation_id, str)
                    else f"{method}_{path}"
                )
                if isinstance(operation_id, str) and operation_id in operation_ids:
                    raise OpenApiDocumentError(
                        "openapi_operation_conflict",
                        f"operationId 重复: {operation_id}",
                    )
                if isinstance(operation_id, str):
                    operation_ids.add(operation_id)
                tool_name = _tool_name(raw_tool_name, method, path)
                if tool_name in tool_names:
                    raise OpenApiDocumentError(
                        "openapi_operation_conflict",
                        f"规范化后的 MCP 工具名称重复: {tool_name}",
                    )
                tool_names.add(tool_name)
                drafts.append(
                    _operation_to_draft(
                        resolver,
                        path,
                        method,
                        path_item,
                        operation,
                        tool_name,
                    )
                )
        if not drafts:
            raise OpenApiDocumentError("openapi_no_operations", "OpenAPI 没有可导入的接口")
        info = document.get("info")
        title = filename
        document_version = ""
        if isinstance(info, dict):
            if isinstance(info.get("title"), str) and info["title"].strip():
                title = info["title"].strip()
            if isinstance(info.get("version"), str):
                document_version = info["version"].strip()
        return ManagedHttpOpenApiPreview(
            title=title[:256],
            version=document_version[:128],
            drafts=tuple(drafts),
        )


class _ReferenceResolver:
    def __init__(self, document: dict[str, object]) -> None:
        self._document = document

    def resolve_object(
        self,
        value: object,
        resolving: tuple[str, ...] = (),
    ) -> dict[str, object]:
        if not isinstance(value, dict):
            raise OpenApiDocumentError("openapi_reference_invalid", "OpenAPI 引用目标必须是对象")
        reference = value.get("$ref")
        if reference is None:
            return copy.deepcopy(value)
        if not isinstance(reference, str):
            raise OpenApiDocumentError("openapi_reference_invalid", "OpenAPI $ref 必须是字符串")
        if reference in resolving:
            raise OpenApiDocumentError(
                "openapi_reference_cycle",
                f"OpenAPI 引用存在循环: {reference}",
            )
        if len(resolving) >= OPENAPI_MAX_REFERENCE_DEPTH:
            raise OpenApiDocumentError(
                "openapi_document_too_complex",
                "OpenAPI 引用层级过深",
            )
        resolved = self._pointer(reference)
        merged = {
            **resolved,
            **{
                key: copy.deepcopy(item)
                for key, item in value.items()
                if key != "$ref"
            },
        }
        return self.resolve_object(merged, (*resolving, reference))

    def schema(
        self,
        value: object,
        resolving: tuple[str, ...] = (),
        depth: int = 0,
    ) -> dict[str, object]:
        if depth > OPENAPI_MAX_REFERENCE_DEPTH:
            raise OpenApiDocumentError(
                "openapi_document_too_complex",
                "OpenAPI Schema 层级过深",
            )
        if not isinstance(value, dict):
            raise OpenApiDocumentError(
                "openapi_operation_unsupported",
                "OpenAPI 参数 Schema 必须是对象",
            )
        reference = value.get("$ref")
        if reference is not None:
            if not isinstance(reference, str):
                raise OpenApiDocumentError(
                    "openapi_reference_invalid",
                    "OpenAPI $ref 必须是字符串",
                )
            if reference in resolving:
                raise OpenApiDocumentError(
                    "openapi_reference_cycle",
                    f"OpenAPI Schema 引用存在循环: {reference}",
                )
            if len(resolving) >= OPENAPI_MAX_REFERENCE_DEPTH:
                raise OpenApiDocumentError(
                    "openapi_document_too_complex",
                    "OpenAPI 引用层级过深",
                )
            resolved = self._pointer(reference)
            resolved.update(
                {key: copy.deepcopy(item) for key, item in value.items() if key != "$ref"}
            )
            return self.schema(resolved, (*resolving, reference), depth + 1)

        result = copy.deepcopy(value)
        all_of = result.pop("allOf", None)
        if all_of is not None:
            if not isinstance(all_of, list) or not all_of:
                raise OpenApiDocumentError(
                    "openapi_operation_unsupported",
                    "OpenAPI allOf 必须是非空数组",
                )
            result = _merge_all_of(
                [self.schema(item, resolving, depth + 1) for item in all_of],
                result,
            )
        properties = result.get("properties")
        if properties is not None:
            if not isinstance(properties, dict):
                raise OpenApiDocumentError(
                    "openapi_operation_unsupported",
                    "OpenAPI Schema properties 必须是对象",
                )
            normalized_properties: dict[str, object] = {}
            for name, schema in properties.items():
                if not isinstance(name, str):
                    raise OpenApiDocumentError(
                        "openapi_operation_unsupported",
                        "OpenAPI Schema 属性名必须是字符串",
                    )
                resolved = self.schema(schema, resolving, depth + 1)
                if resolved.get("readOnly") is True:
                    continue
                normalized_properties[name] = resolved
            result["properties"] = normalized_properties
            required = result.get("required")
            if required is not None:
                if not isinstance(required, list) or any(
                    not isinstance(name, str) for name in required
                ):
                    raise OpenApiDocumentError(
                        "openapi_operation_unsupported",
                        "OpenAPI Schema required 必须是字符串数组",
                    )
                result["required"] = [
                    name for name in required if name in normalized_properties
                ]
        if "items" in result:
            result["items"] = self.schema(result["items"], resolving, depth + 1)
        for keyword in ("oneOf", "anyOf"):
            alternatives = result.get(keyword)
            if alternatives is not None:
                if not isinstance(alternatives, list) or not alternatives:
                    raise OpenApiDocumentError(
                        "openapi_operation_unsupported",
                        f"OpenAPI {keyword} 必须是非空数组",
                    )
                result[keyword] = [
                    self.schema(item, resolving, depth + 1) for item in alternatives
                ]
        additional = result.get("additionalProperties")
        if isinstance(additional, dict):
            result["additionalProperties"] = self.schema(
                additional,
                resolving,
                depth + 1,
            )
        return result

    def _pointer(self, reference: str) -> dict[str, object]:
        decoded = unquote(reference)
        if not decoded.startswith("#/"):
            raise OpenApiDocumentError(
                "openapi_external_reference",
                "OpenAPI 不支持外部引用",
            )
        current: object = self._document
        for raw_part in decoded[2:].split("/"):
            part = raw_part.replace("~1", "/").replace("~0", "~")
            if not isinstance(current, dict) or part not in current:
                raise OpenApiDocumentError(
                    "openapi_reference_invalid",
                    f"OpenAPI 引用不存在: {reference}",
                )
            current = current[part]
        if not isinstance(current, dict):
            raise OpenApiDocumentError(
                "openapi_reference_invalid",
                f"OpenAPI 引用目标不是对象: {reference}",
            )
        return copy.deepcopy(current)


def _operation_to_draft(
    resolver: _ReferenceResolver,
    path: str,
    method: str,
    path_item: dict[str, object],
    operation: dict[str, object],
    tool_name: str,
) -> ManagedHttpOpenApiDraft:
    if not path.startswith("/") or "?" in path or "#" in path or "\\" in path:
        raise OpenApiDocumentError(
            "openapi_operation_unsupported",
            f"OpenAPI 接口路径不合法: {path}",
        )
    operation_key = f"{method.upper()} {path}"
    parameters = _parameters(
        resolver,
        path_item.get("parameters"),
        operation.get("parameters"),
    )
    input_properties: dict[str, object] = {}
    required: list[str] = []
    bindings: list[ManagedHttpParameterBinding] = []
    path_replacements: dict[str, str] = {}

    for parameter in parameters:
        raw_name = parameter.get("name")
        raw_location = parameter.get("in")
        if not isinstance(raw_name, str) or not raw_name.strip():
            raise OpenApiDocumentError(
                "openapi_operation_unsupported",
                f"{operation_key} 存在无名称参数",
            )
        if not isinstance(raw_location, str) or raw_location not in _PARAMETER_LOCATIONS:
            raise OpenApiDocumentError(
                "openapi_operation_unsupported",
                f"{operation_key} 包含不支持的参数位置",
            )
        raw_name = raw_name.strip()
        if raw_location == "header" and (
            raw_name.lower() in _PROTECTED_HEADERS or raw_name.lower().startswith("proxy-")
        ):
            raise OpenApiDocumentError(
                "openapi_operation_unsupported",
                f"{operation_key} 不能把认证或传输 Header 暴露为工具参数",
            )
        argument_name = _argument_name(raw_name)
        schema = resolver.schema(parameter.get("schema", {"type": "string"}))
        schema_type = schema.get("type")
        if raw_location != "query" and schema_type in {"array", "object"}:
            raise OpenApiDocumentError(
                "openapi_operation_unsupported",
                f"{operation_key} 的 {raw_location} 参数只支持标量",
            )
        if raw_location == "query" and schema_type == "object":
            raise OpenApiDocumentError(
                "openapi_operation_unsupported",
                f"{operation_key} 的 query 对象参数暂不支持",
            )
        description = parameter.get("description", schema.get("description", ""))
        schema["description"] = description if isinstance(description, str) else ""
        _add_argument(input_properties, bindings, argument_name, schema, raw_location, raw_name)
        if raw_location == "path":
            if parameter.get("required") is not True:
                raise OpenApiDocumentError(
                    "openapi_operation_unsupported",
                    f"{operation_key} 的 path 参数必须标记 required",
                )
            path_replacements[raw_name] = argument_name
        if parameter.get("required") is True:
            required.append(argument_name)

    path_parameter_names = set(_PATH_PARAMETER.findall(path))
    if path_parameter_names != set(path_replacements):
        raise OpenApiDocumentError(
            "openapi_operation_unsupported",
            f"{operation_key} 的路径占位符与 path 参数不一致",
        )
    path_template = path
    for raw_name, argument_name in path_replacements.items():
        path_template = path_template.replace("{" + raw_name + "}", "{" + argument_name + "}")

    request_body = operation.get("requestBody")
    if request_body is not None:
        body = resolver.resolve_object(request_body)
        body_schema = _request_body_schema(resolver, body, operation_key)
        properties = body_schema.get("properties")
        if body_schema.get("type") != "object" and not isinstance(properties, dict):
            raise OpenApiDocumentError(
                "openapi_operation_unsupported",
                f"{operation_key} 只支持 JSON 对象请求体",
            )
        if not isinstance(properties, dict):
            properties = {}
        body_required = body_schema.get("required", [])
        if not isinstance(body_required, list):
            raise OpenApiDocumentError(
                "openapi_operation_unsupported",
                f"{operation_key} 请求体 required 不合法",
            )
        for raw_name, schema in properties.items():
            if not isinstance(raw_name, str) or not isinstance(schema, dict):
                raise OpenApiDocumentError(
                    "openapi_operation_unsupported",
                    f"{operation_key} 请求体属性不合法",
                )
            argument_name = _argument_name(raw_name)
            _add_argument(
                input_properties,
                bindings,
                argument_name,
                schema,
                "body",
                raw_name,
            )
            if raw_name in body_required:
                required.append(argument_name)

    input_schema: dict[str, object] = {
        "type": "object",
        "properties": input_properties,
        "additionalProperties": False,
    }
    if required:
        input_schema["required"] = list(dict.fromkeys(required))
    summary = operation.get("summary")
    operation_id = operation.get("operationId")
    display_name = (
        summary.strip()
        if isinstance(summary, str) and summary.strip()
        else operation_id.strip()
        if isinstance(operation_id, str) and operation_id.strip()
        else operation_key
    )
    raw_description = operation.get("description")
    description = (
        raw_description.strip()
        if isinstance(raw_description, str) and raw_description.strip()
        else summary.strip()
        if isinstance(summary, str) and summary.strip()
        else ""
    )
    issues = list(openapi_draft_issues(description, input_schema))
    if len(display_name) > 128:
        issues.append("显示名称不能超过 128 个字符")
    return ManagedHttpOpenApiDraft(
        operation_key=operation_key,
        remote_name=tool_name,
        display_name=display_name,
        description=description,
        input_schema=input_schema,
        method=method.upper(),
        path_template=path_template,
        parameter_bindings=tuple(bindings),
        issues=tuple(issues),
    )


def _parameters(
    resolver: _ReferenceResolver,
    path_parameters: object,
    operation_parameters: object,
) -> tuple[dict[str, object], ...]:
    merged: dict[tuple[str, str], dict[str, object]] = {}
    for raw_collection in (path_parameters, operation_parameters):
        if raw_collection is None:
            continue
        if not isinstance(raw_collection, list):
            raise OpenApiDocumentError(
                "openapi_operation_unsupported",
                "OpenAPI parameters 必须是数组",
            )
        for raw_parameter in raw_collection:
            parameter = resolver.resolve_object(raw_parameter)
            name = parameter.get("name")
            location = parameter.get("in")
            if not isinstance(name, str) or not isinstance(location, str):
                raise OpenApiDocumentError(
                    "openapi_operation_unsupported",
                    "OpenAPI 参数缺少 name 或 in",
                )
            merged[(name, location)] = parameter
    return tuple(merged.values())


def _request_body_schema(
    resolver: _ReferenceResolver,
    request_body: dict[str, object],
    operation_key: str,
) -> dict[str, object]:
    content = request_body.get("content")
    if not isinstance(content, dict) or not content:
        raise OpenApiDocumentError(
            "openapi_operation_unsupported",
            f"{operation_key} 请求体缺少 content",
        )
    media = content.get("application/json")
    if not isinstance(media, dict):
        media = next(
            (
                value
                for name, value in sorted(content.items())
                if isinstance(name, str) and name.endswith("+json") and isinstance(value, dict)
            ),
            None,
        )
    if not isinstance(media, dict):
        raise OpenApiDocumentError(
            "openapi_operation_unsupported",
            f"{operation_key} 只支持 JSON 请求体",
        )
    return resolver.schema(media.get("schema", {"type": "object", "properties": {}}))


def _add_argument(
    properties: dict[str, object],
    bindings: list[ManagedHttpParameterBinding],
    argument_name: str,
    schema: dict[str, object],
    location: str,
    target_name: str,
) -> None:
    if argument_name in properties:
        raise OpenApiDocumentError(
            "openapi_operation_conflict",
            f"同一接口的参数名称冲突: {argument_name}",
        )
    properties[argument_name] = copy.deepcopy(schema)
    bindings.append(
        ManagedHttpParameterBinding(
            argument_name=argument_name,
            location=(
                ManagedHttpParameterLocation.BODY
                if location == "body"
                else _PARAMETER_LOCATIONS[location]
            ),
            target_name=target_name,
        )
    )


def _merge_all_of(
    parts: list[dict[str, object]],
    siblings: dict[str, object],
) -> dict[str, object]:
    merged: dict[str, object] = {"type": "object"}
    properties: dict[str, object] = {}
    required: list[str] = []
    for part in [*parts, siblings]:
        for key, value in part.items():
            if key not in {"properties", "required"}:
                merged[key] = copy.deepcopy(value)
        raw_properties = part.get("properties")
        if isinstance(raw_properties, dict):
            properties.update(copy.deepcopy(raw_properties))
        raw_required = part.get("required")
        if isinstance(raw_required, list):
            required.extend(
                name for name in raw_required if isinstance(name, str) and name not in required
            )
    if properties:
        merged["properties"] = properties
    if required:
        merged["required"] = required
    return merged


def _load_document(content: bytes, filename: str) -> dict[str, object]:
    if not content:
        raise OpenApiDocumentError("openapi_file_empty", "OpenAPI 文件不能为空")
    if len(content) > OPENAPI_MAX_FILE_BYTES:
        raise OpenApiDocumentError(
            "openapi_file_too_large",
            f"OpenAPI 文件不能超过 {OPENAPI_MAX_FILE_BYTES} 字节",
        )
    if not filename.lower().endswith((".json", ".yaml", ".yml")):
        raise OpenApiDocumentError(
            "openapi_media_type_unsupported",
            "OpenAPI 文件扩展名必须是 .json、.yaml 或 .yml",
        )
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise OpenApiDocumentError(
            "openapi_encoding_invalid",
            "OpenAPI 文件必须使用 UTF-8 编码",
        ) from None
    try:
        if filename.lower().endswith(".json") or text.lstrip().startswith(("{", "[")):
            loaded = json.loads(text, object_pairs_hook=_unique_json_object)
        else:
            for event in yaml.parse(text, Loader=_UniqueKeySafeLoader):
                if isinstance(event, AliasEvent):
                    raise OpenApiDocumentError(
                        "openapi_format_invalid",
                        "OpenAPI YAML 不支持别名",
                    )
            loaded = yaml.load(text, Loader=_UniqueKeySafeLoader)
    except OpenApiDocumentError:
        raise
    except (json.JSONDecodeError, yaml.YAMLError):
        raise OpenApiDocumentError(
            "openapi_format_invalid",
            "OpenAPI JSON/YAML 格式不合法",
        ) from None
    if not isinstance(loaded, dict) or any(not isinstance(key, str) for key in loaded):
        raise OpenApiDocumentError(
            "openapi_format_invalid",
            "OpenAPI 根节点必须是字符串键对象",
        )
    return loaded


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise OpenApiDocumentError("openapi_format_invalid", "OpenAPI 包含重复字段")
        result[key] = value
    return result


def _validate_complexity(document: dict[str, object]) -> None:
    count = 0
    stack: list[tuple[object, int]] = [(document, 1)]
    while stack:
        value, depth = stack.pop()
        count += 1
        if count > OPENAPI_MAX_DOCUMENT_NODES or depth > OPENAPI_MAX_DOCUMENT_DEPTH:
            raise OpenApiDocumentError(
                "openapi_document_too_complex",
                "OpenAPI 结构超过安全上限",
            )
        if isinstance(value, dict):
            if any(not isinstance(key, str) for key in value):
                raise OpenApiDocumentError(
                    "openapi_format_invalid",
                    "OpenAPI 对象字段名必须是字符串",
                )
            stack.extend((item, depth + 1) for item in value.values())
        elif isinstance(value, list):
            stack.extend((item, depth + 1) for item in value)


def _argument_name(raw: str) -> str:
    if _IDENTIFIER.fullmatch(raw):
        return raw
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", raw)
    value = re.sub(r"[^A-Za-z0-9_]+", "_", value).strip("_").lower()
    if not value or (not value[0].isalpha() and value[0] != "_"):
        value = f"parameter_{value}" if value else "parameter"
    return value[:128].rstrip("_")


def _tool_name(raw: str, method: str, path: str) -> str:
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", raw)
    value = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_.-").lower()
    if not value or not value[0].isalnum():
        value = re.sub(r"[^A-Za-z0-9]+", "_", f"{method}_{path}").strip("_").lower()
    if len(value) == 1:
        value = f"{value}_tool"
    return value[:128].rstrip("_.-")


__all__ = ["ManagedHttpOpenApiParser"]
