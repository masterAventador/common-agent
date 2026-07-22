from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

import pytest

from common_agent.adapters.agent.platform_tools import PlatformMcpToolRegistry
from common_agent.adapters.mcp.platform import PlatformMcpRuntime
from common_agent.audit import (
    AuditAction,
    AuditEntry,
    AuditEvent,
    AuditIntegrity,
    AuditOutcome,
    AuditPage,
    AuditQuery,
    AuditResourceType,
    AuditService,
)
from common_agent.tenancy import TenantAccess, TenantRole, bind_tenant
from common_agent.tools import (
    ToolCapabilityUnavailable,
    ToolGrantTarget,
    ToolGrantTargetType,
    ToolRuntimeCapability,
    platform_tool_catalog_seed,
)

_TENANT_ID = UUID("10000000-0000-4000-8000-000000000001")
_USER_ID = UUID("20000000-0000-4000-8000-000000000001")
_NOW = datetime(2026, 7, 22, 8, 9, 10, tzinfo=UTC)


class _RuntimeDirectory:
    def __init__(self, target: ToolGrantTarget) -> None:
        seed = platform_tool_catalog_seed(_TENANT_ID)
        self.target = target
        self.capability = ToolRuntimeCapability(seed.source, seed.current_time)
        self.enabled = True
        self.calls: list[tuple[ToolGrantTarget, tuple[UUID, ...]]] = []

    async def authorized_runtime_capabilities(
        self,
        target: ToolGrantTarget,
        capability_ids: tuple[UUID, ...],
    ) -> tuple[ToolRuntimeCapability, ...]:
        self.calls.append((target, capability_ids))
        if (
            not self.enabled
            or target != self.target
            or capability_ids != (self.capability.capability.id,)
        ):
            raise ToolCapabilityUnavailable
        return (self.capability,)


class _AuditStore:
    def __init__(self) -> None:
        self.entries: list[AuditEntry] = []

    async def append(
        self,
        entry: AuditEntry,
        *,
        retention_until: datetime,
        max_events_per_scope: int,
    ) -> AuditEvent:
        del retention_until, max_events_per_scope
        self.entries.append(entry)
        return cast(AuditEvent, object())

    async def page(self, query: AuditQuery) -> AuditPage:
        del query
        return AuditPage()

    async def verify(self, tenant_id: UUID | None) -> AuditIntegrity:
        del tenant_id
        return cast(AuditIntegrity, object())


@pytest.mark.parametrize(
    "target_type",
    [ToolGrantTargetType.EMPLOYEE, ToolGrantTargetType.CONVERSATION],
)
def test_platform_tool_uses_real_mcp_and_rechecks_exact_grant(
    target_type: ToolGrantTargetType,
) -> None:
    target = ToolGrantTarget(target_type, uuid4())
    directory = _RuntimeDirectory(target)
    audit = _AuditStore()
    registry = PlatformMcpToolRegistry(
        directory,
        PlatformMcpRuntime(clock=lambda: _NOW),
        audit=AuditService(audit),
    )

    async def exercise() -> str:
        tools = await registry.resolve(
            (directory.capability.capability.id,),
            target=target,
        )
        assert len(tools) == 1
        return cast(str, await tools[0].ainvoke({"utc_offset": "+08:00"}))

    with bind_tenant(TenantAccess(_TENANT_ID, _USER_ID, TenantRole.EDITOR)):
        result = asyncio.run(exercise())

    assert result == (
        '{"iso8601":"2026-07-22T16:09:10+08:00",'
        '"unix_timestamp":1784707750,"utc_offset":"+08:00"}'
    )
    assert directory.calls == [
        (target, (directory.capability.capability.id,)),
        (target, (directory.capability.capability.id,)),
    ]
    assert [entry.action for entry in audit.entries] == [
        AuditAction.TOOL_CALLED,
        AuditAction.TOOL_CALLED,
    ]
    assert [entry.outcome for entry in audit.entries] == [
        AuditOutcome.STARTED,
        AuditOutcome.SUCCEEDED,
    ]
    assert all(entry.resource_type is AuditResourceType.TOOL_CAPABILITY for entry in audit.entries)
    assert all(
        entry.resource_id == str(directory.capability.capability.id) for entry in audit.entries
    )


def test_platform_tool_denies_a_grant_removed_after_resolution() -> None:
    target = ToolGrantTarget(ToolGrantTargetType.EMPLOYEE, uuid4())
    directory = _RuntimeDirectory(target)
    audit = _AuditStore()
    registry = PlatformMcpToolRegistry(
        directory,
        PlatformMcpRuntime(clock=lambda: _NOW),
        audit=AuditService(audit),
    )

    async def exercise() -> str:
        tools = await registry.resolve(
            (directory.capability.capability.id,),
            target=target,
        )
        directory.enabled = False
        return cast(str, await tools[0].ainvoke({"utc_offset": "+08:00"}))

    with bind_tenant(TenantAccess(_TENANT_ID, _USER_ID, TenantRole.EDITOR)):
        result = asyncio.run(exercise())

    assert result == "工具调用失败,错误码:tool_unauthorized"
    assert [entry.outcome for entry in audit.entries] == [
        AuditOutcome.STARTED,
        AuditOutcome.DENIED,
    ]
    assert audit.entries[-1].error_code == "tool_unauthorized"
