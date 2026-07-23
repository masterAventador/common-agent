from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import cast
from uuid import uuid4

import pytest

from common_agent.tools.managed_http import (
    MANAGED_HTTP_PARAMETER_MAX_ITEMS,
    ManagedHttpCapability,
    ManagedHttpCapabilityCommand,
    ManagedHttpParameterBinding,
    ManagedHttpParameterLocation,
    ManagedHttpRuntimeSnapshot,
    ManagedHttpSourceCommand,
    ManagedHttpValidationError,
    build_managed_http_request,
)
from common_agent.tools.models import (
    McpSource,
    McpSourceStatus,
    McpSourceType,
    ToolCapability,
    ToolValidationError,
)


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


def test_managed_http_commands_create_replace_and_snapshot_stable_ids() -> None:
    source_command = ManagedHttpSourceCommand(
        name="订单系统",
        description="订单业务",
        base_url="https://business.example/api/",
        enabled=True,
    )
    source = source_command.create()
    assert source_command.base_url == "https://business.example/api"
    assert source.status is McpSourceStatus.READY
    replaced_source = ManagedHttpSourceCommand(
        name="订单系统 V2",
        description="订单业务 V2",
        base_url="https://business.example/v2",
        enabled=False,
    ).replace(source)
    assert replaced_source.id == source.id
    assert replaced_source.created_at == source.created_at
    assert replaced_source.status is McpSourceStatus.DISABLED

    original = _managed()
    command = ManagedHttpCapabilityCommand(
        remote_name=original.capability.remote_name,
        display_name=original.capability.display_name,
        description=original.capability.description,
        input_schema=original.capability.input_schema,
        method=original.method,
        path_template=original.path_template,
        parameter_bindings=original.parameter_bindings,
        timeout_seconds=original.timeout_seconds,
        response_json_pointer=original.response_json_pointer,
        enabled=False,
    )
    created = command.create(source.id)
    updated = command.replace(created)
    assert created.capability.status.value == "disabled"
    assert updated.capability.id == created.capability.id
    assert updated.capability.created_at == created.capability.created_at
    assert ManagedHttpRuntimeSnapshot(source=source, capabilities=(created,)).capabilities == (
        created,
    )


@pytest.mark.parametrize(
    "factory",
    [
        lambda: ManagedHttpSourceCommand(
            name="订单系统",
            description="",
            base_url="https://business.example/api",
            enabled=cast(bool, "yes"),
        ),
        lambda: ManagedHttpCapabilityCommand(
            remote_name="orders.get",
            display_name="查询订单",
            description="查询订单。",
            input_schema={"type": "object", "properties": {}},
            method="GET",
            path_template="/orders",
            parameter_bindings=(),
            timeout_seconds=10,
            response_json_pointer=None,
            enabled=cast(bool, "yes"),
        ),
        lambda: ManagedHttpParameterBinding(
            argument_name="invalid-name",
            location=ManagedHttpParameterLocation.QUERY,
            target_name="query",
        ),
        lambda: ManagedHttpParameterBinding(
            argument_name="value",
            location=cast(ManagedHttpParameterLocation, "matrix"),
            target_name="value",
        ),
        lambda: ManagedHttpParameterBinding(
            argument_name="value",
            location=ManagedHttpParameterLocation.QUERY,
            target_name="bad target",
        ),
    ],
)
def test_managed_http_commands_and_bindings_reject_invalid_types(
    factory: Callable[[], object],
) -> None:
    with pytest.raises(ManagedHttpValidationError):
        factory()


@pytest.mark.parametrize(
    "changes",
    [
        {"capability": cast(ToolCapability, object())},
        {"parameter_bindings": (cast(ManagedHttpParameterBinding, object()),)},
        {
            "parameter_bindings": tuple(
                _managed().parameter_bindings[0]
                for _ in range(MANAGED_HTTP_PARAMETER_MAX_ITEMS + 1)
            )
        },
        {"timeout_seconds": cast(int, True)},
        {"response_json_pointer": "/bad~2escape"},
    ],
)
def test_managed_http_capability_rejects_remaining_invalid_shapes(
    changes: dict[str, object],
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
    with pytest.raises(ManagedHttpValidationError):
        ManagedHttpCapability(**values)  # type: ignore[arg-type]


def test_managed_http_capability_rejects_invalid_remote_tool_name() -> None:
    capability = _capability()
    object.__setattr__(capability, "remote_name", "bad name")
    with pytest.raises(ManagedHttpValidationError, match="MCP 工具名称"):
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


@pytest.mark.parametrize(
    "base_url",
    [
        1,
        "ftp://business.example/api",
        "https://user:password@business.example/api",
        "https://business.example/api?redirect=1",
        "https://business.example/api#fragment",
        "https://business.example/%2e%2e/admin",
    ],
)
def test_managed_http_source_rejects_unsafe_base_urls(base_url: object) -> None:
    with pytest.raises((ManagedHttpValidationError, ToolValidationError)):
        ManagedHttpSourceCommand(
            name="订单系统",
            description="",
            base_url=cast(str, base_url),
            enabled=True,
        )


def test_managed_http_snapshot_rejects_wrong_sources_capabilities_and_duplicates() -> None:
    managed_source = ManagedHttpSourceCommand(
        name="订单系统",
        description="",
        base_url="https://business.example/api",
        enabled=True,
    ).create()
    wrong_source = McpSource.create(
        name="外部 MCP",
        source_type=McpSourceType.EXTERNAL,
        endpoint_url="https://partner.example/mcp",
    )
    capability = ManagedHttpCapabilityCommand(
        remote_name="orders.get",
        display_name="查询订单",
        description="查询订单。",
        input_schema={"type": "object", "properties": {}},
        method="GET",
        path_template="/orders",
        parameter_bindings=(),
        timeout_seconds=10,
        response_json_pointer=None,
        enabled=True,
    ).create(managed_source.id)

    with pytest.raises(ManagedHttpValidationError, match="必须是 MCP 来源"):
        ManagedHttpRuntimeSnapshot(source=cast(McpSource, object()), capabilities=())
    with pytest.raises(ManagedHttpValidationError, match="必须是托管"):
        ManagedHttpRuntimeSnapshot(source=wrong_source, capabilities=())
    with pytest.raises(ManagedHttpValidationError, match="其他来源"):
        ManagedHttpRuntimeSnapshot(
            source=managed_source,
            capabilities=(
                replace(
                    capability,
                    capability=replace(capability.capability, source_id=uuid4()),
                ),
            ),
        )
    with pytest.raises(ManagedHttpValidationError, match="不能重复"):
        ManagedHttpRuntimeSnapshot(source=managed_source, capabilities=(capability, capability))


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ({"order_id": "A-1", "unknown": "value"}, "未映射"),
        ({}, "缺少必填"),
        ({"order_id": {"nested": True}}, "必须是标量"),
        ({"order_id": float("inf")}, "不是有限值"),
        ({"order_id": "A-1", "trace": "line\nbreak"}, "控制字符"),
    ],
)
def test_managed_http_request_rejects_invalid_runtime_arguments(
    arguments: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ManagedHttpValidationError, match=message):
        build_managed_http_request("https://business.example/api", _managed(), arguments)


def test_managed_http_request_rejects_non_json_body_and_unmapped_path() -> None:
    managed = _managed()
    with pytest.raises(ManagedHttpValidationError, match="请求体只能包含 JSON"):
        build_managed_http_request(
            "https://business.example/api",
            managed,
            {"order_id": "A-1", "detail": object()},
        )

    without_path_binding = _managed()
    object.__setattr__(without_path_binding, "path_template", "/orders/{other}")
    with pytest.raises(ManagedHttpValidationError, match="缺少路径参数"):
        build_managed_http_request(
            "https://business.example/api",
            without_path_binding,
            {"order_id": "A-1"},
        )
