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
    ToolGrantDirectory,
)
from common_agent.domain.conversation import Conversation, ConversationSource, Message
from common_agent.domain.employee import Employee
from common_agent.tools.models import (
    ToolGrantSelection,
    ToolGrantSnapshot,
    ToolGrantTarget,
    ToolGrantTargetType,
    ToolValidationError,
)


class ConversationExecutionTargetResolver:
    def __init__(
        self,
        *,
        employees: EmployeeDirectory,
        model_configurations: ModelConfigurationDirectory | None,
        tools: ToolGrantDirectory | None = None,
    ) -> None:
        self._employees = employees
        self._model_configurations = model_configurations
        self._tools = tools

    async def for_selection(
        self,
        conversation: Conversation,
        *,
        model_configuration_id: UUID | None,
        initial_tool_grants: ToolGrantSnapshot | None = None,
    ) -> ConversationExecutionTarget:
        employee = await self._employee(conversation)
        selected_id = _selected_model_id(
            conversation,
            employee=employee,
            requested_id=model_configuration_id,
        )
        model_identifier, streaming_breaks_tool_calls = await self._model_runtime(
            selected_id,
            employee=employee,
        )
        grant_target, capability_ids = await self._tool_grants(
            conversation,
            employee=employee,
            initial_tool_grants=initial_tool_grants,
        )
        return _target(
            conversation,
            employee=employee,
            model_configuration_id=selected_id,
            model_identifier=model_identifier,
            streaming_breaks_tool_calls=streaming_breaks_tool_calls,
            tool_grant_target=grant_target,
            allowed_tool_capability_ids=capability_ids,
        )

    async def for_message(
        self,
        conversation: Conversation,
        message: Message,
    ) -> ConversationExecutionTarget:
        if message.model_configuration_id is None or message.model_identifier is None:
            return await self.for_selection(conversation, model_configuration_id=None)
        employee = await self._employee(conversation)
        grant_target, capability_ids = await self._tool_grants(
            conversation,
            employee=employee,
            initial_tool_grants=None,
        )
        streaming_breaks_tool_calls = await self._streaming_breaks_tool_calls(
            message.model_configuration_id
        )
        return _target(
            conversation,
            employee=employee,
            model_configuration_id=message.model_configuration_id,
            model_identifier=message.model_identifier,
            streaming_breaks_tool_calls=streaming_breaks_tool_calls,
            tool_grant_target=grant_target,
            allowed_tool_capability_ids=capability_ids,
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

    async def new_conversation_grants(
        self,
        conversation: Conversation,
        selection: ToolGrantSelection,
    ) -> ToolGrantSnapshot | None:
        if conversation.source is ConversationSource.EMPLOYEE:
            if selection.collection_ids or selection.capability_ids:
                raise ToolValidationError(
                    "tool_selection",
                    "数字员工会话不能覆盖员工工具授权",
                )
            return None
        if self._tools is None:
            if selection.collection_ids or selection.capability_ids:
                raise ToolValidationError("tool_selection", "工具授权服务不可用")
            return ToolGrantSnapshot(
                target_type=ToolGrantTargetType.CONVERSATION,
                target_id=conversation.id,
                collection_ids=(),
                capability_ids=(),
            )
        return await self._tools.prepare_conversation_grants(conversation.id, selection)

    async def _employee(self, conversation: Conversation) -> Employee | None:
        if conversation.source is ConversationSource.GENERIC:
            return None
        if conversation.employee_id is None:
            raise RuntimeError("employee conversation is missing employee_id")
        return await self._employees.get(conversation.employee_id)

    async def _model_runtime(
        self,
        model_configuration_id: UUID,
        *,
        employee: Employee | None,
    ) -> tuple[str, bool]:
        if self._model_configurations is None:
            if employee is not None and (
                model_configuration_id == employee.default_model_configuration_id
            ):
                return employee.default_model_identifier, False
            raise RuntimeError("model configuration directory is not configured")
        configuration = await self._model_configurations.get(model_configuration_id)
        if not configuration.enabled and (
            employee is None or model_configuration_id != employee.default_model_configuration_id
        ):
            raise ConversationModelDisabled
        return configuration.model_identifier, configuration.streaming_breaks_tool_calls

    async def _streaming_breaks_tool_calls(
        self,
        model_configuration_id: UUID,
    ) -> bool:
        if self._model_configurations is None:
            return False
        configuration = await self._model_configurations.get(model_configuration_id)
        return configuration.streaming_breaks_tool_calls

    async def _tool_grants(
        self,
        conversation: Conversation,
        *,
        employee: Employee | None,
        initial_tool_grants: ToolGrantSnapshot | None,
    ) -> tuple[ToolGrantTarget, tuple[UUID, ...]]:
        if employee is not None:
            target = ToolGrantTarget(ToolGrantTargetType.EMPLOYEE, employee.id)
            if self._tools is None:
                return target, ()
            snapshot = await self._tools.employee_grants(employee.id)
            return target, snapshot.capability_ids
        target = ToolGrantTarget(ToolGrantTargetType.CONVERSATION, conversation.id)
        if initial_tool_grants is not None:
            if (
                initial_tool_grants.target_type is not ToolGrantTargetType.CONVERSATION
                or initial_tool_grants.target_id != conversation.id
            ):
                raise ToolValidationError("tool_selection", "会话工具授权目标不匹配")
            return target, initial_tool_grants.capability_ids
        if self._tools is None:
            return target, ()
        snapshot = await self._tools.conversation_grants(conversation.id)
        return target, snapshot.capability_ids


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
    streaming_breaks_tool_calls: bool,
    tool_grant_target: ToolGrantTarget,
    allowed_tool_capability_ids: tuple[UUID, ...],
) -> ConversationExecutionTarget:
    if employee is None:
        return ConversationExecutionTarget(
            subject_id=conversation.id,
            model_configuration_id=model_configuration_id,
            model_identifier=model_identifier,
            streaming_breaks_tool_calls=streaming_breaks_tool_calls,
            system_instruction=GENERIC_SYSTEM_INSTRUCTION,
            knowledge_base_id=None,
            allowed_workflow_ids=(),
            allowed_tool_capability_ids=allowed_tool_capability_ids,
            tool_grant_target=tool_grant_target,
        )
    return ConversationExecutionTarget(
        subject_id=employee.id,
        model_configuration_id=model_configuration_id,
        model_identifier=model_identifier,
        streaming_breaks_tool_calls=streaming_breaks_tool_calls,
        system_instruction=employee.system_prompt,
        knowledge_base_id=employee.knowledge_base_id,
        allowed_workflow_ids=employee.allowed_workflow_ids,
        allowed_tool_capability_ids=allowed_tool_capability_ids,
        tool_grant_target=tool_grant_target,
    )


__all__ = ["ConversationExecutionTargetResolver"]
