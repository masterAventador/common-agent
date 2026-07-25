from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from common_agent.domain.employee import (
    EMPLOYEE_DESCRIPTION_MAX_LENGTH,
    EMPLOYEE_KNOWLEDGE_BASE_ID_MAX_LENGTH,
    EMPLOYEE_NAME_MAX_LENGTH,
    EMPLOYEE_SYSTEM_PROMPT_MAX_LENGTH,
    Employee,
    EmployeeValidationError,
)

MODEL_CONFIGURATION_ID = UUID("5eb782ad-4fd6-40a6-8668-a9b729340ec9")
MODEL_IDENTIFIER = "qwen-plus"


def test_employee_create_normalizes_generic_configuration() -> None:
    workflow_id = uuid4()
    model_configuration_id = uuid4()
    before = datetime.now(UTC)

    employee = Employee.create(
        name="  通用知识助理  ",
        description="  面向任意领域的会话角色  ",
        system_prompt="  根据可用上下文回答问题。  ",
        default_model_configuration_id=model_configuration_id,
        default_model_identifier="qwen-plus",
        knowledge_base_id="  ragflow-dataset-id  ",
        allowed_workflow_ids=[workflow_id],
    )

    assert isinstance(employee.id, UUID)
    assert employee.name == "通用知识助理"
    assert employee.description == "面向任意领域的会话角色"
    assert employee.system_prompt == "根据可用上下文回答问题。"
    assert employee.default_model_configuration_id == model_configuration_id
    assert employee.default_model_identifier == "qwen-plus"
    assert employee.knowledge_base_id == "ragflow-dataset-id"
    assert employee.allowed_workflow_ids == (workflow_id,)
    assert before <= employee.created_at <= datetime.now(UTC)
    assert employee.updated_at == employee.created_at


def test_employee_reconfigure_preserves_identity_and_creation_time() -> None:
    employee = Employee.create(
        name="助理",
        system_prompt="原始指令",
        default_model_configuration_id=MODEL_CONFIGURATION_ID,
        default_model_identifier=MODEL_IDENTIFIER,
    )
    changed_at = employee.updated_at + timedelta(microseconds=1)

    changed = employee.reconfigure(
        name="新助理",
        description="新说明",
        system_prompt="新指令",
        default_model_configuration_id=MODEL_CONFIGURATION_ID,
        default_model_identifier=MODEL_IDENTIFIER,
        knowledge_base_id=None,
        allowed_workflow_ids=(),
        updated_at=changed_at,
    )

    assert changed.id == employee.id
    assert changed.created_at == employee.created_at
    assert changed.updated_at == changed_at
    assert changed.name == "新助理"
    assert changed.description == "新说明"
    assert changed.knowledge_base_id is None


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"employee_id": "not-a-uuid"}, "id"),
        ({"name": "   "}, "name"),
        ({"name": "x" * (EMPLOYEE_NAME_MAX_LENGTH + 1)}, "name"),
        ({"description": "x" * (EMPLOYEE_DESCRIPTION_MAX_LENGTH + 1)}, "description"),
        ({"system_prompt": "\n\t"}, "system_prompt"),
        (
            {"system_prompt": "x" * (EMPLOYEE_SYSTEM_PROMPT_MAX_LENGTH + 1)},
            "system_prompt",
        ),
        ({"knowledge_base_id": "   "}, "knowledge_base_id"),
        (
            {"knowledge_base_id": "x" * (EMPLOYEE_KNOWLEDGE_BASE_ID_MAX_LENGTH + 1)},
            "knowledge_base_id",
        ),
        ({"allowed_workflow_ids": [uuid4(), uuid4(), "not-a-uuid"]}, "allowed_workflow_ids"),
    ],
)
def test_employee_rejects_invalid_fields(overrides: dict[str, object], field: str) -> None:
    values: dict[str, object] = {
        "name": "助理",
        "system_prompt": "通用系统指令",
        "default_model_configuration_id": MODEL_CONFIGURATION_ID,
        "default_model_identifier": MODEL_IDENTIFIER,
    }
    values.update(overrides)

    with pytest.raises(EmployeeValidationError) as captured:
        Employee.create(**values)  # type: ignore[arg-type]

    assert captured.value.field == field


def test_employee_rejects_duplicate_workflow_allowlist_entries() -> None:
    workflow_id = uuid4()

    with pytest.raises(EmployeeValidationError) as captured:
        Employee.create(
            name="助理",
            system_prompt="通用系统指令",
            default_model_configuration_id=MODEL_CONFIGURATION_ID,
            default_model_identifier=MODEL_IDENTIFIER,
            allowed_workflow_ids=[workflow_id, workflow_id],
        )

    assert captured.value.field == "allowed_workflow_ids"


def test_employee_rejects_non_utc_or_reversed_timestamps() -> None:
    employee_id = uuid4()
    created_at = datetime.now(UTC)

    with pytest.raises(EmployeeValidationError) as naive_error:
        Employee(
            id=employee_id,
            name="助理",
            description="",
            system_prompt="通用系统指令",
            default_model_configuration_id=MODEL_CONFIGURATION_ID,
            default_model_identifier=MODEL_IDENTIFIER,
            knowledge_base_id=None,
            allowed_workflow_ids=(),
            created_at=created_at.replace(tzinfo=None),
            updated_at=created_at,
        )
    assert naive_error.value.field == "created_at"

    with pytest.raises(EmployeeValidationError) as ordering_error:
        Employee(
            id=employee_id,
            name="助理",
            description="",
            system_prompt="通用系统指令",
            default_model_configuration_id=MODEL_CONFIGURATION_ID,
            default_model_identifier=MODEL_IDENTIFIER,
            knowledge_base_id=None,
            allowed_workflow_ids=(),
            created_at=created_at,
            updated_at=created_at - timedelta(microseconds=1),
        )
    assert ordering_error.value.field == "updated_at"


def test_employee_keeps_deep_thinking_on_by_default() -> None:
    """默认开启, 保持现有行为: 会思考的模型继续思考。"""
    employee = Employee.create(
        name="默认员工",
        system_prompt="回答问题。",
        default_model_configuration_id=MODEL_CONFIGURATION_ID,
        default_model_identifier=MODEL_IDENTIFIER,
    )

    assert employee.deep_thinking_enabled is True


def test_employee_can_turn_deep_thinking_off_and_back_on() -> None:
    employee = Employee.create(
        name="快答员工",
        system_prompt="回答问题。",
        default_model_configuration_id=MODEL_CONFIGURATION_ID,
        default_model_identifier=MODEL_IDENTIFIER,
        deep_thinking_enabled=False,
    )

    assert employee.deep_thinking_enabled is False

    reconfigured = employee.reconfigure(
        name=employee.name,
        description=employee.description,
        system_prompt=employee.system_prompt,
        default_model_configuration_id=employee.default_model_configuration_id,
        default_model_identifier=employee.default_model_identifier,
        knowledge_base_id=employee.knowledge_base_id,
        allowed_workflow_ids=employee.allowed_workflow_ids,
        deep_thinking_enabled=True,
    )

    assert reconfigured.deep_thinking_enabled is True


def test_employee_rejects_a_non_boolean_deep_thinking_flag() -> None:
    with pytest.raises(EmployeeValidationError) as error:
        Employee.create(
            name="非法开关",
            system_prompt="回答问题。",
            default_model_configuration_id=MODEL_CONFIGURATION_ID,
            default_model_identifier=MODEL_IDENTIFIER,
            deep_thinking_enabled="yes",  # type: ignore[arg-type]
        )

    assert error.value.field == "deep_thinking_enabled"
