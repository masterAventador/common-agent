from __future__ import annotations

from uuid import UUID

from common_agent.application.resource_locks import (
    employee_resource,
    model_configuration_resource,
)
from common_agent.conversations.contracts import (
    GENERIC_SYSTEM_INSTRUCTION,
    ConversationExecutionTarget,
    ConversationModelDisabled,
    EmployeeDirectory,
    ModelConfigurationDirectory,
)
from common_agent.domain.conversation import Conversation, ConversationSource, Message
from common_agent.domain.employee import Employee


class ConversationExecutionTargetResolver:
    def __init__(
        self,
        *,
        employees: EmployeeDirectory,
        model_configurations: ModelConfigurationDirectory | None,
    ) -> None:
        self._employees = employees
        self._model_configurations = model_configurations

    async def for_selection(
        self,
        conversation: Conversation,
        *,
        model_configuration_id: UUID | None,
    ) -> ConversationExecutionTarget:
        employee = await self._employee(conversation)
        selected_id = _selected_model_id(
            conversation,
            employee=employee,
            requested_id=model_configuration_id,
        )
        model_identifier = await self._model_identifier(
            selected_id,
            employee=employee,
        )
        return _target(
            conversation,
            employee=employee,
            model_configuration_id=selected_id,
            model_identifier=model_identifier,
        )

    async def for_message(
        self,
        conversation: Conversation,
        message: Message,
    ) -> ConversationExecutionTarget:
        if message.model_configuration_id is None or message.model_identifier is None:
            return await self.for_selection(conversation, model_configuration_id=None)
        employee = await self._employee(conversation)
        return _target(
            conversation,
            employee=employee,
            model_configuration_id=message.model_configuration_id,
            model_identifier=message.model_identifier,
        )

    @staticmethod
    def resource_keys(
        conversation: Conversation,
        *,
        model_configuration_id: UUID | None,
    ) -> tuple[str, ...]:
        keys: list[str] = []
        if conversation.employee_id is not None:
            keys.append(employee_resource(conversation.employee_id))
        if model_configuration_id is not None:
            keys.append(model_configuration_resource(model_configuration_id))
        return tuple(keys)

    async def _employee(self, conversation: Conversation) -> Employee | None:
        if conversation.source is ConversationSource.GENERIC:
            return None
        if conversation.employee_id is None:
            raise RuntimeError("employee conversation is missing employee_id")
        return await self._employees.get(conversation.employee_id)

    async def _model_identifier(
        self,
        model_configuration_id: UUID,
        *,
        employee: Employee | None,
    ) -> str:
        if self._model_configurations is None:
            if employee is not None and (
                model_configuration_id == employee.default_model_configuration_id
            ):
                return employee.default_model_identifier
            raise RuntimeError("model configuration directory is not configured")
        configuration = await self._model_configurations.get(model_configuration_id)
        if not configuration.enabled and (
            employee is None or model_configuration_id != employee.default_model_configuration_id
        ):
            raise ConversationModelDisabled
        return configuration.model_identifier


def _selected_model_id(
    conversation: Conversation,
    *,
    employee: Employee | None,
    requested_id: UUID | None,
) -> UUID:
    if requested_id is not None:
        return requested_id
    if employee is not None:
        return employee.default_model_configuration_id
    if conversation.model_configuration_id is not None:
        return conversation.model_configuration_id
    raise RuntimeError("generic conversation is missing model configuration")


def _target(
    conversation: Conversation,
    *,
    employee: Employee | None,
    model_configuration_id: UUID,
    model_identifier: str,
) -> ConversationExecutionTarget:
    if employee is None:
        return ConversationExecutionTarget(
            subject_id=conversation.id,
            model_configuration_id=model_configuration_id,
            model_identifier=model_identifier,
            system_instruction=GENERIC_SYSTEM_INSTRUCTION,
            knowledge_base_id=None,
            allowed_workflow_ids=(),
        )
    return ConversationExecutionTarget(
        subject_id=employee.id,
        model_configuration_id=model_configuration_id,
        model_identifier=model_identifier,
        system_instruction=employee.system_prompt,
        knowledge_base_id=employee.knowledge_base_id,
        allowed_workflow_ids=employee.allowed_workflow_ids,
    )


__all__ = ["ConversationExecutionTargetResolver"]
