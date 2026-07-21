from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

from common_agent.adapters.persistence.database import Database
from common_agent.adapters.persistence.events import SqlAlchemyEventJournal
from common_agent.conversations.events import ConversationEventBroker, ConversationEventKind
from common_agent.domain.conversation import Message
from common_agent.domain.workflow import AiChatTargetType
from common_agent.domain.workflow_run import (
    WorkflowAiTargetSummary,
    WorkflowRun,
    WorkflowRunTrigger,
)
from common_agent.tenancy.constants import DEFAULT_TENANT_ID
from common_agent.workflows.events import WorkflowEventBroker, WorkflowEventKind
from tests.support.settings import TEST_DATABASE_URL


def test_conversation_sse_history_and_live_events_cross_broker_instances() -> None:
    async def scenario() -> None:
        database = Database(TEST_DATABASE_URL)
        await database.start()
        journal = SqlAlchemyEventJournal(database)
        conversation_id = uuid4()
        turn_id = uuid4()
        now = datetime.now(UTC)
        pending = Message.create_assistant(
            conversation_id=conversation_id,
            sequence_number=2,
            now=now,
        )
        producer = ConversationEventBroker(
            journal=journal,
            tenant_id_provider=lambda: DEFAULT_TENANT_ID,
            persistent_poll_seconds=0.01,
        )
        consumer = ConversationEventBroker(
            journal=SqlAlchemyEventJournal(database),
            tenant_id_provider=lambda: DEFAULT_TENANT_ID,
            persistent_poll_seconds=0.01,
        )
        stream = consumer.stream(conversation_id)
        try:
            published = await producer.publish(
                turn_id=turn_id,
                message=pending,
                kind=ConversationEventKind.ASSISTANT_STARTED,
            )
            assert published.sequence == 1
            replayed = await asyncio.wait_for(anext(stream), timeout=1)
            assert replayed == published

            streaming = pending.append_delta("跨实例", updated_at=now)
            delta = await producer.publish(
                turn_id=turn_id,
                message=streaming,
                kind=ConversationEventKind.ASSISTANT_DELTA,
                delta="跨实例",
            )
            live = await asyncio.wait_for(anext(stream), timeout=1)
            assert live == delta

            reconstructed = ConversationEventBroker(
                journal=SqlAlchemyEventJournal(database),
                tenant_id_provider=lambda: DEFAULT_TENANT_ID,
                persistent_poll_seconds=0.01,
            )
            await reconstructed.validate_resume(conversation_id, after_sequence=1)
            resumed = reconstructed.stream(conversation_id, after_sequence=1)
            assert await asyncio.wait_for(anext(resumed), timeout=1) == delta
            await resumed.aclose()
            await reconstructed.aclose()
        finally:
            await stream.aclose()
            await producer.aclose()
            await consumer.aclose()
            await database.stop()

    asyncio.run(scenario())


def test_workflow_sse_history_survives_broker_reconstruction() -> None:
    async def scenario() -> None:
        database = Database(TEST_DATABASE_URL)
        await database.start()
        run = (
            WorkflowRun.create(
                workflow_id=uuid4(),
                trigger=WorkflowRunTrigger.MANUAL,
                input="持久工作流事件",
            )
            .start()
            .start_node("chat")
        )
        model_configuration_id = uuid4()
        run = run.record_ai_target(
            WorkflowAiTargetSummary(
                node_id="chat",
                target_type=AiChatTargetType.MODEL,
                target_id=model_configuration_id,
                target_name="持久模型",
                model_configuration_id=model_configuration_id,
                model_identifier="qwen-plus",
            )
        )
        producer = WorkflowEventBroker(
            journal=SqlAlchemyEventJournal(database),
            tenant_id_provider=lambda: DEFAULT_TENANT_ID,
            persistent_poll_seconds=0.01,
        )
        try:
            started = await producer.publish(
                run=run,
                kind=WorkflowEventKind.NODE_STARTED,
                node_id="chat",
            )
            reconstructed = WorkflowEventBroker(
                journal=SqlAlchemyEventJournal(database),
                tenant_id_provider=lambda: DEFAULT_TENANT_ID,
                persistent_poll_seconds=0.01,
            )
            await reconstructed.validate_resume(run.id)
            stream = reconstructed.stream(run.id)
            assert await asyncio.wait_for(anext(stream), timeout=1) == started
            await stream.aclose()
            await reconstructed.aclose()
        finally:
            await producer.aclose()
            await database.stop()

    asyncio.run(scenario())
