from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

from common_agent.conversations.events import ConversationEventBroker, ConversationEventKind
from common_agent.domain.conversation import Message
from common_agent.domain.workflow_run import WorkflowRun, WorkflowRunTrigger
from common_agent.tenancy import TenantAccess, TenantRole, bind_tenant, tenant_namespace
from common_agent.workflows.events import WorkflowEventBroker, WorkflowEventKind

TENANT_A = UUID("10000000-0000-4000-8000-000000000001")
TENANT_B = UUID("10000000-0000-4000-8000-000000000002")
USER_ID = UUID("20000000-0000-4000-8000-000000000001")


def test_conversation_and_workflow_event_state_is_namespaced_by_tenant() -> None:
    async def exercise() -> None:
        conversation_id = uuid4()
        assistant = Message.create_assistant(
            conversation_id=conversation_id,
            sequence_number=1,
        )
        running = WorkflowRun.create(
            workflow_id=uuid4(),
            trigger=WorkflowRunTrigger.MANUAL,
            input="租户事件隔离",
        ).start()
        conversations = ConversationEventBroker(
            key_namespace=lambda resource_id: tenant_namespace(f"conversation:{resource_id}")
        )
        workflows = WorkflowEventBroker(
            key_namespace=lambda resource_id: tenant_namespace(f"workflow-run:{resource_id}")
        )
        try:
            first = TenantAccess(TENANT_A, USER_ID, TenantRole.OWNER)
            second = TenantAccess(TENANT_B, USER_ID, TenantRole.OWNER)
            with bind_tenant(first):
                conversation_a = await conversations.publish(
                    turn_id=uuid4(),
                    message=assistant,
                    kind=ConversationEventKind.ASSISTANT_STARTED,
                )
                workflow_a = await workflows.publish(
                    run=running,
                    kind=WorkflowEventKind.RUN_STARTED,
                )
            with bind_tenant(second):
                conversation_b = await conversations.publish(
                    turn_id=uuid4(),
                    message=assistant,
                    kind=ConversationEventKind.ASSISTANT_STARTED,
                )
                workflow_b = await workflows.publish(
                    run=running,
                    kind=WorkflowEventKind.RUN_STARTED,
                )

            assert conversation_a.sequence == conversation_b.sequence == 1
            assert workflow_a.sequence == workflow_b.sequence == 1
            assert (await conversations.lifecycle_snapshot()).state_count == 2
            assert (await workflows.lifecycle_snapshot()).state_count == 2
        finally:
            await conversations.aclose()
            await workflows.aclose()

    asyncio.run(exercise())
