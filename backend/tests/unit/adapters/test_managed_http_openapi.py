from __future__ import annotations

import json
from collections.abc import Callable

import pytest

from common_agent.adapters.openapi.managed_http import ManagedHttpOpenApiParser
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
