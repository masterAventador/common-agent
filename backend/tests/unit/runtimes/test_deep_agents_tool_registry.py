from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from langchain_core.tools import tool

from common_agent.adapters.agent.deep_agents import (
    DeepAgentToolRegistry,
    DeepAgentToolRegistryValidationError,
    RuntimeCapabilityUnavailable,
)
from common_agent.domain.workflow_run import WorkflowRunOrigin
from tests.support.runtime import OTHER_WORKFLOW_ID, WORKFLOW_ID

ORIGIN = WorkflowRunOrigin(
    employee_id=uuid4(),
    conversation_id=uuid4(),
    assistant_message_id=uuid4(),
)


@tool
def first_workflow(value: str) -> str:
    """运行第一个测试工作流。"""

    return value


@tool
def second_workflow(value: str) -> str:
    """运行第二个测试工作流。"""

    return value


def test_registry_resolves_only_explicitly_allowed_tools_in_request_order() -> None:
    registry = DeepAgentToolRegistry(
        {
            WORKFLOW_ID: first_workflow,
            OTHER_WORKFLOW_ID: second_workflow,
        }
    )

    assert asyncio.run(registry.resolve((), origin=ORIGIN)) == ()
    assert asyncio.run(registry.resolve((OTHER_WORKFLOW_ID,), origin=ORIGIN)) == (second_workflow,)
    assert asyncio.run(registry.resolve((WORKFLOW_ID, OTHER_WORKFLOW_ID), origin=ORIGIN)) == (
        first_workflow,
        second_workflow,
    )


def test_registry_fails_closed_for_an_unregistered_capability() -> None:
    registry = DeepAgentToolRegistry({WORKFLOW_ID: first_workflow})

    with pytest.raises(RuntimeCapabilityUnavailable) as captured:
        asyncio.run(registry.resolve((uuid4(),), origin=ORIGIN))

    assert captured.value.code == "runtime_capability_unavailable"
    assert captured.value.retryable is False


@pytest.mark.parametrize(
    "reserved_name",
    ["execute", "ls", "read_file", "write_file", "edit_file", "glob", "grep", "task"],
)
def test_registry_rejects_tools_that_shadow_deep_agents_privileged_builtins(
    reserved_name: str,
) -> None:
    @tool(reserved_name)
    def reserved_tool(value: str) -> str:
        """不允许注册的保留工具。"""

        return value

    with pytest.raises(DeepAgentToolRegistryValidationError):
        DeepAgentToolRegistry({WORKFLOW_ID: reserved_tool})


def test_registry_rejects_duplicate_tool_names() -> None:
    @tool("same_name")
    def duplicate(value: str) -> str:
        """与已有工具重名。"""

        return value

    @tool("same_name")
    def another_duplicate(value: str) -> str:
        """与已有工具重名。"""

        return value

    with pytest.raises(DeepAgentToolRegistryValidationError):
        DeepAgentToolRegistry(
            {
                WORKFLOW_ID: duplicate,
                OTHER_WORKFLOW_ID: another_duplicate,
            }
        )
