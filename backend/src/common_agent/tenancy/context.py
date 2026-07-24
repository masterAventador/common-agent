from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from uuid import UUID

from common_agent.tenancy.models import TenantAccess, TenantRole

_CURRENT_TENANT: ContextVar[TenantAccess | None] = ContextVar(
    "common_agent_current_tenant",
    default=None,
)


class TenantContextMissing(RuntimeError):
    """Raised when tenant-owned data is accessed without a verified tenant scope."""


@contextmanager
def bind_tenant(access: TenantAccess) -> Iterator[None]:
    token: Token[TenantAccess | None] = _CURRENT_TENANT.set(access)
    try:
        yield
    finally:
        _CURRENT_TENANT.reset(token)


def current_tenant() -> TenantAccess:
    access = _CURRENT_TENANT.get()
    if access is None:
        raise TenantContextMissing("租户上下文尚未绑定")
    return access


def activate_tenant(access: TenantAccess) -> None:
    """Bind a verified tenant for the lifetime of the current request task."""
    _CURRENT_TENANT.set(access)


def tenant_namespace(key: str) -> str:
    return f"tenant:{current_tenant().tenant_id}:{key}"


def system_tenant_access(tenant_id: UUID) -> TenantAccess:
    """构造平台系统执行者对指定工作区的 OWNER 访问上下文。

    用于启动 seed、新建工作区初始化等无请求用户的平台内部操作: 以固定系统
    用户 (UUID(int=0)) 的所有者身份绑定目标租户, 让按租户隔离的服务能写入
    正确的 tenant_id。
    """
    return TenantAccess(
        tenant_id=tenant_id,
        user_id=UUID(int=0),
        role=TenantRole.OWNER,
    )


__all__ = [
    "TenantContextMissing",
    "activate_tenant",
    "bind_tenant",
    "current_tenant",
    "system_tenant_access",
    "tenant_namespace",
]
