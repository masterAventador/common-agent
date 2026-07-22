from __future__ import annotations

from uuid import uuid4

import pytest

from common_agent.tools.managed_http import (
    ManagedHttpCapability,
    ManagedHttpParameterBinding,
    ManagedHttpParameterLocation,
    ManagedHttpValidationError,
    build_managed_http_request,
)
from common_agent.tools.models import ToolCapability


def _capability() -> ToolCapability:
    return ToolCapability.create(
        source_id=uuid4(),
        remote_name="orders.get",
        display_name="查询订单",
        description="按订单号查询订单。",
        input_schema={
            "type": "object",
            "properties": {
                "order_id": {"type": "string", "description": "订单编号"},
                "fields": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "返回字段",
                },
                "trace": {"type": "string", "description": "调用链标识"},
                "locale": {"type": "string", "description": "语言"},
                "detail": {"type": "boolean", "description": "是否返回详情"},
            },
            "required": ["order_id"],
            "additionalProperties": False,
        },
    )


def _managed() -> ManagedHttpCapability:
    capability = _capability()
    return ManagedHttpCapability(
        capability=capability,
        method="POST",
        path_template="/orders/{order_id}",
        parameter_bindings=(
            ManagedHttpParameterBinding(
                argument_name="order_id",
                location=ManagedHttpParameterLocation.PATH,
                target_name="order_id",
            ),
            ManagedHttpParameterBinding(
                argument_name="fields",
                location=ManagedHttpParameterLocation.QUERY,
                target_name="field",
            ),
            ManagedHttpParameterBinding(
                argument_name="trace",
                location=ManagedHttpParameterLocation.HEADER,
                target_name="X-Trace-ID",
            ),
            ManagedHttpParameterBinding(
                argument_name="locale",
                location=ManagedHttpParameterLocation.COOKIE,
                target_name="locale",
            ),
            ManagedHttpParameterBinding(
                argument_name="detail",
                location=ManagedHttpParameterLocation.BODY,
                target_name="include_detail",
            ),
        ),
        timeout_seconds=20,
        response_json_pointer="/data/order",
    )


def test_managed_http_mapping_builds_one_fixed_origin_request() -> None:
    managed = _managed()

    request = build_managed_http_request(
        "https://business.example/api/v1/",
        managed,
        {
            "order_id": "A/B 1",
            "fields": ["status", "owner"],
            "trace": "trace-1",
            "locale": "zh-CN",
            "detail": True,
        },
    )

    assert request.method == "POST"
    assert request.url == (
        "https://business.example/api/v1/orders/A%2FB%201?field=status&field=owner"
    )
    assert request.headers == {
        "Content-Type": "application/json",
        "Cookie": "locale=zh-CN",
        "X-Trace-ID": "trace-1",
    }
    assert request.body == b'{"include_detail":true}'
    assert "A/B 1" not in repr(request)


@pytest.mark.parametrize(
    ("changes", "field"),
    [
        ({"method": "TRACE"}, "method"),
        ({"path_template": "https://attacker.example/orders/{order_id}"}, "path_template"),
        ({"path_template": "/orders/../admin/{order_id}"}, "path_template"),
        ({"response_json_pointer": "data.order"}, "response_json_pointer"),
        ({"timeout_seconds": 0}, "timeout_seconds"),
    ],
)
def test_managed_http_configuration_rejects_unsafe_shapes(
    changes: dict[str, object],
    field: str,
) -> None:
    original = _managed()
    values: dict[str, object] = {
        "capability": original.capability,
        "method": original.method,
        "path_template": original.path_template,
        "parameter_bindings": original.parameter_bindings,
        "timeout_seconds": original.timeout_seconds,
        "response_json_pointer": original.response_json_pointer,
    }
    values.update(changes)

    with pytest.raises(ManagedHttpValidationError) as captured:
        ManagedHttpCapability(**values)  # type: ignore[arg-type]

    assert captured.value.field == field


def test_managed_http_configuration_requires_exact_safe_parameter_bindings() -> None:
    capability = _capability()
    invalid_bindings = (
        ManagedHttpParameterBinding(
            argument_name="order_id",
            location=ManagedHttpParameterLocation.PATH,
            target_name="order_id",
        ),
        ManagedHttpParameterBinding(
            argument_name="fields",
            location=ManagedHttpParameterLocation.HEADER,
            target_name="Authorization",
        ),
        ManagedHttpParameterBinding(
            argument_name="trace",
            location=ManagedHttpParameterLocation.QUERY,
            target_name="trace",
        ),
        ManagedHttpParameterBinding(
            argument_name="locale",
            location=ManagedHttpParameterLocation.COOKIE,
            target_name="locale",
        ),
        ManagedHttpParameterBinding(
            argument_name="detail",
            location=ManagedHttpParameterLocation.BODY,
            target_name="detail",
        ),
    )

    with pytest.raises(ManagedHttpValidationError, match="认证或传输 Header"):
        ManagedHttpCapability(
            capability=capability,
            method="GET",
            path_template="/orders/{order_id}",
            parameter_bindings=invalid_bindings,
            timeout_seconds=10,
        )


def test_managed_http_configuration_requires_described_object_schema() -> None:
    capability = ToolCapability.create(
        source_id=uuid4(),
        remote_name="orders.get",
        display_name="查询订单",
        description="查询订单。",
        input_schema={
            "type": "object",
            "properties": {"order_id": {"type": "string"}},
            "required": ["order_id"],
        },
    )

    with pytest.raises(ManagedHttpValidationError, match="参数含义"):
        ManagedHttpCapability(
            capability=capability,
            method="GET",
            path_template="/orders/{order_id}",
            parameter_bindings=(
                ManagedHttpParameterBinding(
                    argument_name="order_id",
                    location=ManagedHttpParameterLocation.PATH,
                    target_name="order_id",
                ),
            ),
            timeout_seconds=10,
        )


def test_managed_http_configuration_rejects_invalid_json_schema() -> None:
    capability = ToolCapability.create(
        source_id=uuid4(),
        remote_name="orders.get",
        display_name="查询订单",
        description="查询订单。",
        input_schema={
            "type": "object",
            "properties": {
                "order_id": {
                    "type": "not-a-json-schema-type",
                    "description": "订单编号",
                }
            },
            "required": ["order_id"],
        },
    )

    with pytest.raises(ManagedHttpValidationError, match="JSON Schema"):
        ManagedHttpCapability(
            capability=capability,
            method="GET",
            path_template="/orders/{order_id}",
            parameter_bindings=(
                ManagedHttpParameterBinding(
                    argument_name="order_id",
                    location=ManagedHttpParameterLocation.PATH,
                    target_name="order_id",
                ),
            ),
            timeout_seconds=10,
        )
