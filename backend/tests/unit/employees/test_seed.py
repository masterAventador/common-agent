from __future__ import annotations

import asyncio

from common_agent.domain.employee import EmployeeConfiguration
from common_agent.employees.seeds import (
    DEFAULT_KNOWLEDGE_ASSISTANT_ID,
    seed_default_employee,
)
from tests.unit.employees.support import employee_service_with_probes


def test_default_employee_seed_is_generic_and_idempotent() -> None:
    service, units, knowledge, workflows = employee_service_with_probes()

    first = asyncio.run(seed_default_employee(service))
    second = asyncio.run(seed_default_employee(service))

    assert first == second
    assert first.id == DEFAULT_KNOWLEDGE_ASSISTANT_ID
    assert first.name == "知识助理"
    assert first.knowledge_base_id is None
    assert first.allowed_workflow_ids == ()
    assert "automation-tool" not in first.description
    assert "业务" not in first.system_prompt
    assert len(units.repository.values) == 1
    assert units.commit_count == 1
    assert knowledge.requested_ids == []
    assert workflows.requested_ids == []


def test_default_employee_seed_never_overwrites_user_edits() -> None:
    service, units, _, _ = employee_service_with_probes()
    seeded = asyncio.run(seed_default_employee(service))
    edited = asyncio.run(
        service.update(
            seeded.id,
            EmployeeConfiguration(
                name="我的助理",
                description="用户修改后的说明",
                system_prompt="用户修改后的系统指令",
                knowledge_base_id=None,
            ),
        )
    )

    restored = asyncio.run(seed_default_employee(service))

    assert restored == edited
    assert restored.name == "我的助理"
    assert restored.system_prompt == "用户修改后的系统指令"
    assert len(units.repository.values) == 1
    assert units.commit_count == 2
