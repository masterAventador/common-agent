from __future__ import annotations

from uuid import uuid4

import pytest

from common_agent.tools.models import (
    McpSource,
    McpSourceStatus,
    McpSourceType,
    ToolCallErrorCode,
    ToolCallRequest,
    ToolCallResult,
    ToolCallStatus,
    ToolCapability,
    ToolCapabilityStatus,
    ToolCollection,
    ToolGrantSelection,
    ToolValidationError,
)


def test_tool_domain_uses_stable_ids_and_canonical_schema_fingerprints() -> None:
    source = McpSource.create(
        name="订单系统",
        source_type=McpSourceType.MANAGED_HTTP,
        endpoint_url="https://business.example.com/api",
        status=McpSourceStatus.READY,
    )
    capability_id = uuid4()
    first = ToolCapability.create(
        source_id=source.id,
        remote_name="orders.get",
        display_name="查询订单",
        description="按订单号查询",
        input_schema={"type": "object", "properties": {"id": {"type": "string"}}},
        capability_id=capability_id,
    )
    reordered = ToolCapability.create(
        source_id=source.id,
        remote_name="orders.get",
        display_name="查询订单",
        description="按订单号查询",
        input_schema={"properties": {"id": {"type": "string"}}, "type": "object"},
        capability_id=capability_id,
    )

    assert first.id == capability_id
    assert first.status is ToolCapabilityStatus.ACTIVE
    assert first.schema_fingerprint == reordered.schema_fingerprint
    assert len(first.schema_fingerprint) == 64


def test_tool_domain_rejects_implicit_platform_endpoints_and_non_json_schema() -> None:
    with pytest.raises(ToolValidationError, match="endpoint_url"):
        McpSource.create(
            name="平台内置",
            source_type=McpSourceType.PLATFORM,
            endpoint_url="https://should-not-exist.example.com",
        )

    with pytest.raises(ToolValidationError, match="input_schema"):
        ToolCapability.create(
            source_id=uuid4(),
            remote_name="broken",
            display_name="非法能力",
            input_schema={"unsupported": object()},
        )

    with pytest.raises(ToolValidationError, match="endpoint_url"):
        McpSource.create(
            name="查询串带密钥",
            source_type=McpSourceType.EXTERNAL,
            endpoint_url="https://mcp.example.com/service?token=must-not-echo",
        )


def test_collection_and_grant_selection_reject_duplicate_or_mutable_authority() -> None:
    source_id = uuid4()
    capability_id = uuid4()
    collection = ToolCollection.create(name="订单工具集", source_ids=(source_id,))
    selection = ToolGrantSelection(
        collection_ids=(collection.id,),
        capability_ids=(capability_id,),
    )

    assert selection.collection_ids == (collection.id,)
    assert selection.capability_ids == (capability_id,)

    with pytest.raises(ToolValidationError, match="不能包含重复项"):
        ToolGrantSelection(capability_ids=(capability_id, capability_id))

    with pytest.raises(ToolValidationError, match="source_ids"):
        ToolCollection.create(name="重复来源", source_ids=(source_id, source_id))


def test_tool_call_contract_keeps_arguments_and_output_out_of_repr() -> None:
    tool_call_id = uuid4()
    capability_id = uuid4()
    request = ToolCallRequest(
        tool_call_id=tool_call_id,
        capability_id=capability_id,
        arguments={"order_id": "sensitive-business-value"},
    )
    completed = ToolCallResult(
        tool_call_id=tool_call_id,
        capability_id=capability_id,
        status=ToolCallStatus.COMPLETED,
        output={"text": "sensitive-result"},
    )
    failed = ToolCallResult(
        tool_call_id=tool_call_id,
        capability_id=capability_id,
        status=ToolCallStatus.FAILED,
        error_code=ToolCallErrorCode.TIMEOUT,
    )

    assert "sensitive-business-value" not in repr(request)
    assert "sensitive-result" not in repr(completed)
    assert failed.error_code is ToolCallErrorCode.TIMEOUT

    with pytest.raises(ToolValidationError, match="arguments"):
        ToolCallRequest(
            tool_call_id=tool_call_id,
            capability_id=capability_id,
            arguments={"invalid": object()},
        )
    with pytest.raises(ToolValidationError, match="error_code"):
        ToolCallResult(
            tool_call_id=tool_call_id,
            capability_id=capability_id,
            status=ToolCallStatus.FAILED,
            output={"must": "not coexist"},
        )
