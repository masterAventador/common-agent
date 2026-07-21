from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

from common_agent.domain.model_configuration import (
    ModelConfigurationValidationError,
    normalize_model_identifier,
)

EMPLOYEE_NAME_MAX_LENGTH = 128
EMPLOYEE_DESCRIPTION_MAX_LENGTH = 1_000
EMPLOYEE_SYSTEM_PROMPT_MAX_LENGTH = 12_000
EMPLOYEE_KNOWLEDGE_BASE_ID_MAX_LENGTH = 128
EMPLOYEE_ALLOWED_WORKFLOWS_MAX_ITEMS = 100


class EmployeeValidationError(ValueError):
    def __init__(self, field: str, reason: str) -> None:
        self.field = field
        self.reason = reason
        super().__init__(f"数字员工字段 {field} {reason}")


@dataclass(frozen=True, slots=True)
class EmployeeConfiguration:
    name: str
    description: str
    system_prompt: str
    default_model_configuration_id: UUID
    knowledge_base_id: str | None
    allowed_workflow_ids: tuple[UUID, ...] = ()

    def __post_init__(self) -> None:
        _uuid("default_model_configuration_id", self.default_model_configuration_id)
        object.__setattr__(
            self,
            "allowed_workflow_ids",
            _workflow_ids(self.allowed_workflow_ids),
        )


@dataclass(frozen=True, slots=True)
class Employee:
    id: UUID
    name: str
    description: str
    system_prompt: str
    default_model_configuration_id: UUID
    default_model_identifier: str
    knowledge_base_id: str | None
    allowed_workflow_ids: tuple[UUID, ...]
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.id, UUID):
            raise EmployeeValidationError("id", "必须是 UUID")
        name = _required_text("name", self.name, EMPLOYEE_NAME_MAX_LENGTH)
        description = _optional_text(
            "description", self.description, EMPLOYEE_DESCRIPTION_MAX_LENGTH
        )
        system_prompt = _required_text(
            "system_prompt", self.system_prompt, EMPLOYEE_SYSTEM_PROMPT_MAX_LENGTH
        )
        default_model_configuration_id = _uuid(
            "default_model_configuration_id",
            self.default_model_configuration_id,
        )
        try:
            default_model_identifier = normalize_model_identifier(self.default_model_identifier)
        except ModelConfigurationValidationError as error:
            raise EmployeeValidationError(
                "default_model_identifier",
                error.reason,
            ) from error
        knowledge_base_id = _optional_reference(
            "knowledge_base_id",
            self.knowledge_base_id,
            EMPLOYEE_KNOWLEDGE_BASE_ID_MAX_LENGTH,
        )
        workflow_ids = _workflow_ids(self.allowed_workflow_ids)
        _utc_timestamp("created_at", self.created_at)
        _utc_timestamp("updated_at", self.updated_at)
        if self.updated_at < self.created_at:
            raise EmployeeValidationError("updated_at", "不能早于创建时间")

        object.__setattr__(self, "name", name)
        object.__setattr__(self, "description", description)
        object.__setattr__(self, "system_prompt", system_prompt)
        object.__setattr__(
            self,
            "default_model_configuration_id",
            default_model_configuration_id,
        )
        object.__setattr__(self, "default_model_identifier", default_model_identifier)
        object.__setattr__(self, "knowledge_base_id", knowledge_base_id)
        object.__setattr__(self, "allowed_workflow_ids", workflow_ids)

    @classmethod
    def create(
        cls,
        *,
        name: str,
        system_prompt: str,
        default_model_configuration_id: UUID,
        default_model_identifier: str,
        description: str = "",
        knowledge_base_id: str | None = None,
        allowed_workflow_ids: Iterable[UUID] = (),
        employee_id: UUID | None = None,
        now: datetime | None = None,
    ) -> Employee:
        created_at = now or datetime.now(UTC)
        return cls(
            id=employee_id or uuid4(),
            name=name,
            description=description,
            system_prompt=system_prompt,
            default_model_configuration_id=default_model_configuration_id,
            default_model_identifier=default_model_identifier,
            knowledge_base_id=knowledge_base_id,
            allowed_workflow_ids=tuple(allowed_workflow_ids),
            created_at=created_at,
            updated_at=created_at,
        )

    def reconfigure(
        self,
        *,
        name: str,
        description: str,
        system_prompt: str,
        default_model_configuration_id: UUID,
        default_model_identifier: str,
        knowledge_base_id: str | None,
        allowed_workflow_ids: Iterable[UUID],
        updated_at: datetime | None = None,
    ) -> Employee:
        changed_at = updated_at or datetime.now(UTC)
        return replace(
            self,
            name=name,
            description=description,
            system_prompt=system_prompt,
            default_model_configuration_id=default_model_configuration_id,
            default_model_identifier=default_model_identifier,
            knowledge_base_id=knowledge_base_id,
            allowed_workflow_ids=tuple(allowed_workflow_ids),
            updated_at=changed_at,
        )


def _required_text(field: str, value: str, max_length: int) -> str:
    normalized = _text(field, value).strip()
    if not normalized:
        raise EmployeeValidationError(field, "不能为空")
    if len(normalized) > max_length:
        raise EmployeeValidationError(field, f"不能超过 {max_length} 个字符")
    return normalized


def _optional_text(field: str, value: str, max_length: int) -> str:
    normalized = _text(field, value).strip()
    if len(normalized) > max_length:
        raise EmployeeValidationError(field, f"不能超过 {max_length} 个字符")
    return normalized


def _optional_reference(field: str, value: str | None, max_length: int) -> str | None:
    if value is None:
        return None
    return _required_text(field, value, max_length)


def _text(field: str, value: object) -> str:
    if not isinstance(value, str):
        raise EmployeeValidationError(field, "必须是字符串")
    return value


def _workflow_ids(values: Iterable[UUID]) -> tuple[UUID, ...]:
    result = tuple(values)
    if any(not isinstance(value, UUID) for value in result):
        raise EmployeeValidationError("allowed_workflow_ids", "必须只包含 UUID")
    if len(set(result)) != len(result):
        raise EmployeeValidationError("allowed_workflow_ids", "不能包含重复项")
    if len(result) > EMPLOYEE_ALLOWED_WORKFLOWS_MAX_ITEMS:
        raise EmployeeValidationError(
            "allowed_workflow_ids",
            f"不能超过 {EMPLOYEE_ALLOWED_WORKFLOWS_MAX_ITEMS} 项",
        )
    return result


def _utc_timestamp(field: str, value: datetime) -> None:
    if not isinstance(value, datetime):
        raise EmployeeValidationError(field, "必须是时间")
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise EmployeeValidationError(field, "必须使用 UTC 时区")


def _uuid(field: str, value: object) -> UUID:
    if not isinstance(value, UUID):
        raise EmployeeValidationError(field, "必须是 UUID")
    return value
