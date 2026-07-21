from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token

from common_agent.tenancy.models import TenantAccess

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


__all__ = [
    "TenantContextMissing",
    "activate_tenant",
    "bind_tenant",
    "current_tenant",
    "tenant_namespace",
]
