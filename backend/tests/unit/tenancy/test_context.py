from __future__ import annotations

from uuid import UUID

import pytest

from common_agent.tenancy.context import (
    TenantContextMissing,
    bind_tenant,
    current_tenant,
    tenant_namespace,
)
from common_agent.tenancy.models import TenantAccess, TenantRole

TENANT_ID = UUID("10000000-0000-4000-8000-000000000001")
USER_ID = UUID("20000000-0000-4000-8000-000000000001")


def test_tenant_context_must_be_explicitly_bound() -> None:
    with pytest.raises(TenantContextMissing):
        current_tenant()


def test_bound_context_namespaces_resources_and_resets_after_exit() -> None:
    access = TenantAccess(tenant_id=TENANT_ID, user_id=USER_ID, role=TenantRole.EDITOR)

    with bind_tenant(access):
        assert current_tenant() == access
        assert tenant_namespace("workflow:42") == f"tenant:{TENANT_ID}:workflow:42"

    with pytest.raises(TenantContextMissing):
        current_tenant()


@pytest.mark.parametrize(
    ("role", "can_write", "can_administer"),
    [
        (TenantRole.OWNER, True, True),
        (TenantRole.EDITOR, True, False),
        (TenantRole.VIEWER, False, False),
    ],
)
def test_role_capabilities(
    role: TenantRole,
    can_write: bool,
    can_administer: bool,
) -> None:
    assert role.can_read
    assert role.can_write is can_write
    assert role.can_administer is can_administer
