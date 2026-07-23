from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import pytest

from common_agent.adapters.openapi.managed_http import (
    ManagedHttpOpenApiParser,
    _argument_name,
    _ReferenceResolver,
    _tool_name,
    _validate_complexity,
)
from common_agent.tools.openapi_import import (
    OPENAPI_MAX_FILE_BYTES,
    OpenApiDocumentError,
)


def _document() -> dict[str, object]:
    return {
        "openapi": "3.0.3",
        "info": {"title": "订单业务", "version": "1.2.0"},
        "paths": {
            "/orders/{orderId}": {
                "parameters": [
                    {
                        "name": "orderId",
                        "in": "path",
                        "required": True,
                        "description": "订单编号",
                        "schema": {"type": "string"},
                    }
                ],
                "post": {
                    "operationId": "createOrder",
                    "summary": "创建订单",
                    "description": "按请求内容创建订单。",
                    "parameters": [
                        {
                            "name": "page-size",
                            "in": "query",
                            "description": "分页大小",
                            "schema": {"type": "integer", "minimum": 1},
                        },
                        {
                            "name": "X-Trace-ID",
                            "in": "header",
                            "description": "调用链编号",
                            "schema": {"type": "string"},
                        },
                        {
                            "name": "locale",
                            "in": "cookie",
                            "description": "语言",
                            "schema": {"type": "string"},
                        },
                    ],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/CreateOrderRequest"}
                            }
                        },
                    },
                    "responses": {"200": {"description": "成功"}},
                },
            }
        },
        "components": {
            "schemas": {
                "OrderBase": {
                    "type": "object",
                    "required": ["customerId"],
                    "properties": {
                        "customerId": {"type": "string", "description": ""},
                        "serverValue": {
                            "type": "string",
                            "description": "服务端字段",
                            "readOnly": True,
                        },
                    },
                },
                "CreateOrderRequest": {
                    "allOf": [
                        {"$ref": "#/components/schemas/OrderBase"},
                        {
                            "type": "object",
                            "properties": {
                                "detail": {
                                    "type": "object",
                                    "description": "订单明细",
                                    "properties": {
                                        "sku": {"type": "string", "description": "商品编号"}
                                    },
                                }
                            },
                        },
                    ]
                },
            }
        },
    }


def test_parser_normalizes_json_operations_refs_parameters_and_editable_issues() -> None:
    preview = ManagedHttpOpenApiParser().parse(
        json.dumps(_document(), ensure_ascii=False).encode(),
        "orders.openapi.json",
    )

    assert preview.title == "订单业务"
    assert preview.version == "1.2.0"
    assert len(preview.drafts) == 1
    draft = preview.drafts[0]
    assert draft.operation_key == "POST /orders/{orderId}"
    assert draft.remote_name == "create_order"
    assert draft.display_name == "创建订单"
    assert draft.description == "按请求内容创建订单。"
    assert draft.method == "POST"
    assert draft.path_template == "/orders/{orderId}"
    assert tuple(
        (binding.argument_name, binding.location.value, binding.target_name)
        for binding in draft.parameter_bindings
    ) == (
        ("orderId", "path", "orderId"),
        ("page_size", "query", "page-size"),
        ("x_trace_id", "header", "X-Trace-ID"),
        ("locale", "cookie", "locale"),
        ("customerId", "body", "customerId"),
        ("detail", "body", "detail"),
    )
    assert draft.input_schema["required"] == ["orderId", "customerId"]
    properties = draft.input_schema["properties"]
    assert isinstance(properties, dict)
    assert "serverValue" not in properties
    assert properties["page_size"] == {
        "type": "integer",
        "minimum": 1,
        "description": "分页大小",
    }
    assert properties["detail"] == {
        "type": "object",
        "description": "订单明细",
        "properties": {"sku": {"type": "string", "description": "商品编号"}},
    }
    assert draft.issues == ("参数 customerId 缺少含义",)


def test_parser_accepts_restricted_yaml_31_and_decodes_local_json_pointer() -> None:
    content = b"""
openapi: 3.1.0
info:
  title: Inventory
  version: 2.0.0
paths:
  /items:
    post:
      operationId: saveItem
      summary: Save item
      requestBody:
        content:
          application/vnd.example+json:
            schema:
              $ref: '#/components/schemas/SaveItem%7E1Request'
      responses:
        '200': {description: ok}
components:
  schemas:
    SaveItem/Request:
      type: object
      properties:
        name: {type: string, description: Item name}
"""

    preview = ManagedHttpOpenApiParser().parse(content, "inventory.yaml")

    assert preview.drafts[0].remote_name == "save_item"
    assert tuple(
        (binding.argument_name, binding.location.value, binding.target_name)
        for binding in preview.drafts[0].parameter_bindings
    ) == (("name", "body", "name"),)
    assert preview.drafts[0].issues == ()


@pytest.mark.parametrize(
    ("mutate", "code"),
    [
        (
            lambda value: value["paths"]["/orders/{orderId}"]["post"]["requestBody"][
                "content"
            ]["application/json"].update(
                {"schema": {"$ref": "https://attacker.example/schema.json"}}
            ),
            "openapi_external_reference",
        ),
        (
            lambda value: value["components"]["schemas"].update(
                {
                    "CreateOrderRequest": {"$ref": "#/components/schemas/OrderBase"},
                    "OrderBase": {"$ref": "#/components/schemas/CreateOrderRequest"},
                }
            ),
            "openapi_reference_cycle",
        ),
        (
            lambda value: value["paths"].update(
                {
                    "/other": {
                        "get": {
                            "operationId": "createOrder",
                            "summary": "重复能力",
                            "responses": {"200": {"description": "ok"}},
                        }
                    }
                }
            ),
            "openapi_operation_conflict",
        ),
    ],
)
def test_parser_rejects_external_or_cyclic_refs_and_duplicate_operation_ids(
    mutate: Callable[[dict[str, object]], None],
    code: str,
) -> None:
    document = _document()
    mutate(document)

    with pytest.raises(OpenApiDocumentError) as captured:
        ManagedHttpOpenApiParser().parse(json.dumps(document).encode(), "unsafe.json")

    assert captured.value.code == code


@pytest.mark.parametrize(
    ("content", "filename", "code"),
    [
        (b'{"openapi":"2.0","paths":{}}', "swagger.json", "openapi_version_unsupported"),
        (b'{"openapi":"3.0.3","openapi":"3.1.0"}', "duplicate.json", "openapi_format_invalid"),
        (
            b"openapi: 3.0.3\ninfo: &info {title: A, version: 1}\npaths: {}\nx: *info\n",
            "alias.yaml",
            "openapi_format_invalid",
        ),
        (b"\xff\xfe", "encoding.yaml", "openapi_encoding_invalid"),
        (b'{"openapi":"3.0.3"}', "openapi.txt", "openapi_media_type_unsupported"),
        (b"", "empty.json", "openapi_file_empty"),
        (b"x" * (OPENAPI_MAX_FILE_BYTES + 1), "large.yaml", "openapi_file_too_large"),
    ],
)
def test_parser_rejects_ambiguous_or_unbounded_documents(
    content: bytes,
    filename: str,
    code: str,
) -> None:
    with pytest.raises(OpenApiDocumentError) as captured:
        ManagedHttpOpenApiParser().parse(content, filename)

    assert captured.value.code == code


def test_parser_rejects_documents_over_operation_or_structure_limits() -> None:
    too_many = {
        "openapi": "3.0.3",
        "info": {"title": "Many", "version": "1"},
        "paths": {
            f"/items/{index}": {
                "get": {
                    "operationId": f"getItem{index}",
                    "summary": f"Get item {index}",
                    "responses": {"200": {"description": "ok"}},
                }
            }
            for index in range(201)
        },
    }
    nested: object = {"value": "leaf"}
    for _ in range(70):
        nested = {"next": nested}
    too_deep = {
        "openapi": "3.0.3",
        "info": {"title": "Deep", "version": "1"},
        "paths": {},
        "x-deep": nested,
    }

    for document in (too_many, too_deep):
        with pytest.raises(OpenApiDocumentError) as captured:
            ManagedHttpOpenApiParser().parse(json.dumps(document).encode(), "bounded.json")
        assert captured.value.code == "openapi_document_too_complex"


def _minimal_document(operation: object = None) -> dict[str, Any]:
    return {
        "openapi": "3.0.3",
        "paths": {
            "/items": {
                "get": (
                    {
                        "operationId": "getItems",
                        "responses": {"200": {"description": "ok"}},
                    }
                    if operation is None
                    else operation
                )
            }
        },
    }


@pytest.mark.parametrize(
    ("document", "code"),
    [
        ({"openapi": "3.0.3"}, "openapi_no_operations"),
        ({"openapi": "3.0.3", "paths": []}, "openapi_no_operations"),
        ({"openapi": "3.0.3", "paths": {"/items": []}}, "openapi_format_invalid"),
        (_minimal_document("get"), "openapi_format_invalid"),
        (_minimal_document({"operationId": ""}), "openapi_format_invalid"),
        ({"openapi": "3.0.3", "paths": {}}, "openapi_no_operations"),
        (
            {
                "openapi": "3.0.3",
                "paths": {
                    "/a": {"get": {"operationId": "get item"}},
                    "/b": {"get": {"operationId": "get_item"}},
                },
            },
            "openapi_operation_conflict",
        ),
        (
            {
                "openapi": "3.0.3",
                "paths": {"items": {"get": {"operationId": "getItems"}}},
            },
            "openapi_operation_unsupported",
        ),
    ],
)
def test_parser_rejects_invalid_path_and_operation_shapes(
    document: dict[str, Any],
    code: str,
) -> None:
    with pytest.raises(OpenApiDocumentError) as captured:
        ManagedHttpOpenApiParser().parse(json.dumps(document).encode(), "invalid.json")

    assert captured.value.code == code


@pytest.mark.parametrize(
    ("parameter", "path", "code"),
    [
        ({"in": "query"}, "/items", "openapi_operation_unsupported"),
        ({"name": "value", "in": "formData"}, "/items", "openapi_operation_unsupported"),
        (
            {"name": "Authorization", "in": "header"},
            "/items",
            "openapi_operation_unsupported",
        ),
        (
            {"name": "value", "in": "header", "schema": {"type": "array"}},
            "/items",
            "openapi_operation_unsupported",
        ),
        (
            {"name": "value", "in": "query", "schema": {"type": "object"}},
            "/items",
            "openapi_operation_unsupported",
        ),
        (
            {"name": "itemId", "in": "path", "required": False},
            "/items/{itemId}",
            "openapi_operation_unsupported",
        ),
        (
            {"name": "otherId", "in": "path", "required": True},
            "/items/{itemId}",
            "openapi_operation_unsupported",
        ),
    ],
)
def test_parser_rejects_unsafe_or_unrepresentable_parameters(
    parameter: dict[str, Any],
    path: str,
    code: str,
) -> None:
    document = _minimal_document()
    operation = document["paths"].pop("/items")
    document["paths"][path] = operation
    operation["get"]["parameters"] = [parameter]

    with pytest.raises(OpenApiDocumentError) as captured:
        ManagedHttpOpenApiParser().parse(json.dumps(document).encode(), "invalid.json")

    assert captured.value.code == code


@pytest.mark.parametrize(
    "request_body",
    [
        {},
        {"content": {"text/plain": {"schema": {"type": "string"}}}},
        {"content": {"application/json": {"schema": {"type": "string"}}}},
        {
            "content": {
                "application/json": {
                    "schema": {"type": "object", "required": "name"}
                }
            }
        },
    ],
)
def test_parser_rejects_request_bodies_that_cannot_be_exposed_as_arguments(
    request_body: dict[str, Any],
) -> None:
    document = _minimal_document()
    document["paths"]["/items"]["get"]["requestBody"] = request_body

    with pytest.raises(OpenApiDocumentError) as captured:
        ManagedHttpOpenApiParser().parse(json.dumps(document).encode(), "invalid.json")

    assert captured.value.code == "openapi_operation_unsupported"


def test_parser_normalizes_default_names_and_schema_composition() -> None:
    document = {
        "openapi": "3.1.0",
        "info": {"title": "", "version": 3},
        "paths": {
            "/items": {
                "get": {
                    "summary": "x" * 129,
                    "parameters": [
                        {
                            "name": "9-page",
                            "in": "query",
                            "schema": {
                                "type": "array",
                                "items": {"type": "string"},
                                "oneOf": [{"type": "array"}],
                                "anyOf": [{"type": "array"}],
                                "additionalProperties": {"type": "string"},
                            },
                        }
                    ],
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    }

    preview = ManagedHttpOpenApiParser().parse(
        json.dumps(document).encode(),
        "fallback-name.json",
    )

    draft = preview.drafts[0]
    assert preview.title == "fallback-name.json"
    assert preview.version == ""
    assert draft.remote_name == "get__items"
    assert draft.parameter_bindings[0].argument_name == "parameter_9_page"
    assert "显示名称不能超过 128 个字符" in draft.issues


@pytest.mark.parametrize(
    "schema",
    [
        {"allOf": []},
        {"properties": []},
        {"properties": {"name": {"type": "string"}}, "required": "name"},
        {"oneOf": []},
        {"anyOf": "invalid"},
        {"items": "invalid"},
    ],
)
def test_reference_resolver_rejects_invalid_schema_shapes(schema: object) -> None:
    with pytest.raises(OpenApiDocumentError) as captured:
        _ReferenceResolver({}).schema(schema)

    assert captured.value.code == "openapi_operation_unsupported"


@pytest.mark.parametrize(
    "value",
    [
        "not-an-object",
        {"$ref": 1},
        {"$ref": "#/missing"},
    ],
)
def test_reference_resolver_rejects_invalid_object_references(value: object) -> None:
    with pytest.raises(OpenApiDocumentError) as captured:
        _ReferenceResolver({}).resolve_object(value)

    assert captured.value.code == "openapi_reference_invalid"


def test_reference_resolver_rejects_scalar_targets_and_excessive_depth() -> None:
    resolver = _ReferenceResolver({"value": "scalar", "object": {}})
    with pytest.raises(OpenApiDocumentError) as scalar:
        resolver.resolve_object({"$ref": "#/value"})
    with pytest.raises(OpenApiDocumentError) as object_depth:
        resolver.resolve_object({"$ref": "#/object"}, ("ref",) * 65)
    with pytest.raises(OpenApiDocumentError) as schema_depth:
        resolver.schema({}, depth=65)

    assert scalar.value.code == "openapi_reference_invalid"
    assert object_depth.value.code == "openapi_document_too_complex"
    assert schema_depth.value.code == "openapi_document_too_complex"


def test_yaml_and_complexity_validators_reject_ambiguous_keys() -> None:
    with pytest.raises(OpenApiDocumentError) as duplicate:
        ManagedHttpOpenApiParser().parse(
            b"openapi: 3.0.3\npaths: {}\npaths: {}\n",
            "duplicate.yaml",
        )
    with pytest.raises(OpenApiDocumentError) as malformed:
        ManagedHttpOpenApiParser().parse(b"openapi: [", "malformed.yaml")
    with pytest.raises(OpenApiDocumentError) as nested_key:
        _validate_complexity({"nested": {1: "value"}})

    assert duplicate.value.code == "openapi_format_invalid"
    assert malformed.value.code == "openapi_format_invalid"
    assert nested_key.value.code == "openapi_format_invalid"


def test_name_normalizers_handle_degenerate_values() -> None:
    assert _argument_name("---") == "parameter"
    assert _tool_name("_", "get", "/items") == "get_items"
    assert _tool_name("x", "get", "/items") == "x_tool"
