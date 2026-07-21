from __future__ import annotations

import asyncio
import os
import socket
from datetime import timedelta
from uuid import UUID

from common_agent.adapters.agent.deep_agents import DeepAgentsEmployeeRuntime
from common_agent.adapters.agent.workflow_tools import WorkflowToolRegistry
from common_agent.adapters.demo import DemoEmployeeRuntime, DemoKnowledgeService, DemoWorkflowModel
from common_agent.adapters.knowledge import RagFlowKnowledgeService
from common_agent.adapters.model.bailian import BailianChatModelAdapter
from common_agent.adapters.model.resolver import BailianChatModelResolver
from common_agent.adapters.model.verification import (
    BailianModelConfigurationVerifier,
    DemoModelConfigurationVerifier,
)
from common_agent.adapters.persistence import (
    Database,
    MySqlNamedLockProvider,
    SqlAlchemyAuditStore,
    SqlAlchemyEventJournal,
    SqlAlchemyKnowledgeOwnershipStore,
    SqlAlchemyTaskQueue,
)
from common_agent.adapters.persistence.conversations import (
    SqlAlchemyConversationUnitOfWorkFactory,
)
from common_agent.adapters.persistence.demo_knowledge import (
    SqlAlchemyDemoKnowledgeUnitOfWorkFactory,
)
from common_agent.adapters.persistence.employees import SqlAlchemyEmployeeUnitOfWorkFactory
from common_agent.adapters.persistence.model_configurations import (
    SqlAlchemyModelConfigurationUnitOfWorkFactory,
)
from common_agent.adapters.persistence.workflows import SqlAlchemyWorkflowUnitOfWorkFactory
from common_agent.adapters.workflow.langgraph import LangGraphWorkflowCompiler
from common_agent.application.resource_locks import ResourceMutationGuard
from common_agent.application.workflow_service import WorkflowService
from common_agent.audit import AuditPolicy, AuditService
from common_agent.bootstrap import (
    AuditSettings,
    DatabaseSettings,
    IntegrationModeSettings,
    ModelSettings,
    RagFlowSettings,
    WorkerSettings,
)
from common_agent.concurrency import CoordinatedLockPool
from common_agent.conversations import ConversationEventBroker, ConversationService
from common_agent.employees import EmployeeService
from common_agent.knowledge.retrieval import ConversationKnowledgeResolver
from common_agent.knowledge.service import KnowledgeBaseService
from common_agent.model_configurations import (
    ModelConfigurationService,
    ModelConfigurationVerifier,
)
from common_agent.models.base import TextStreamingModel
from common_agent.observability import configure_json_logging
from common_agent.tasks import TaskKind, TaskWorker, TaskWorkerPool
from common_agent.tenancy import TenantAccess, TenantRole, bind_tenant, current_tenant
from common_agent.workflows.events import WorkflowEventBroker
from common_agent.workflows.nodes.registry import create_workflow_node_registry


async def run_worker(stop: asyncio.Event) -> None:
    configure_json_logging()
    database = Database(DatabaseSettings.from_env().url)
    await database.start()
    worker_settings = WorkerSettings.from_env()
    integration_mode = IntegrationModeSettings.from_env()
    audit_settings = AuditSettings.from_env()

    def tenant_id_provider() -> UUID:
        return current_tenant().tenant_id

    def key_namespace(key: str) -> str:
        return f"tenant:{current_tenant().tenant_id}:{key}"

    knowledge_adapter: RagFlowKnowledgeService | DemoKnowledgeService | None = None
    runtime: DeepAgentsEmployeeRuntime | DemoEmployeeRuntime | None = None
    conversations: ConversationService | None = None
    workflows: WorkflowService | None = None
    workflow_events: WorkflowEventBroker | None = None
    conversation_events: ConversationEventBroker | None = None
    demo_workflow_model: DemoWorkflowModel | None = None
    real_model: BailianChatModelAdapter | None = None
    model_settings: ModelSettings | None = None
    try:
        workflow_model: TextStreamingModel
        model_configuration_verifier: ModelConfigurationVerifier
        if integration_mode.mode == "demo":
            knowledge_adapter = DemoKnowledgeService(
                SqlAlchemyDemoKnowledgeUnitOfWorkFactory(database, tenant_id_provider)
            )
            runtime = DemoEmployeeRuntime()
            demo_workflow_model = DemoWorkflowModel()
            workflow_model = demo_workflow_model
            model_configuration_verifier = DemoModelConfigurationVerifier()
        else:
            ragflow_settings = RagFlowSettings.from_env()
            knowledge_adapter = RagFlowKnowledgeService(
                base_url=ragflow_settings.base_url,
                api_key=ragflow_settings.api_key.get_secret_value(),
                expected_version=ragflow_settings.expected_version,
                embedding_model=ragflow_settings.embedding_model,
                rerank_model=ragflow_settings.rerank_model,
                timeout_seconds=ragflow_settings.timeout_seconds,
                ca_bundle_path=(
                    str(ragflow_settings.ca_bundle_path)
                    if ragflow_settings.ca_bundle_path is not None
                    else None
                ),
            )
            model_settings = ModelSettings.from_env()
            real_model = BailianChatModelAdapter(model_settings)
            workflow_model = real_model
            model_configuration_verifier = BailianModelConfigurationVerifier(model_settings)

        knowledge_bases = KnowledgeBaseService(
            knowledge_adapter,
            ownership=(
                SqlAlchemyKnowledgeOwnershipStore(database)
                if integration_mode.mode == "real"
                else None
            ),
            tenant_id_provider=tenant_id_provider,
        )
        task_queue = SqlAlchemyTaskQueue(database)
        distributed_locks = MySqlNamedLockProvider(database)
        resource_guard = ResourceMutationGuard(
            key_namespace,
            distributed=distributed_locks,
        )
        task_execution_guard = CoordinatedLockPool(distributed=distributed_locks)
        model_configurations = ModelConfigurationService(
            SqlAlchemyModelConfigurationUnitOfWorkFactory(database, tenant_id_provider),
            verifier=model_configuration_verifier,
            guard=resource_guard,
        )
        workflow_events = WorkflowEventBroker(
            key_namespace=lambda run_id: key_namespace(f"workflow-run:{run_id}"),
            journal=SqlAlchemyEventJournal(database),
            tenant_id_provider=tenant_id_provider,
            persistent_poll_seconds=worker_settings.poll_interval_seconds,
            retention_days=worker_settings.event_retention_days,
            maximum_events_per_stream=worker_settings.maximum_events_per_stream,
        )
        workflows = WorkflowService(
            SqlAlchemyWorkflowUnitOfWorkFactory(database, tenant_id_provider),
            knowledge_bases,
            compiler=LangGraphWorkflowCompiler(
                create_workflow_node_registry(workflow_model, knowledge_bases)
            ),
            events=workflow_events,
            guard=resource_guard,
            tasks=task_queue,
            tenant_id_provider=tenant_id_provider,
            task_max_attempts=worker_settings.maximum_attempts,
        )
        if integration_mode.mode != "demo":
            if real_model is None or model_settings is None:
                raise RuntimeError("百炼模型尚未完成装配")
            audit = AuditService(
                SqlAlchemyAuditStore(database),
                AuditPolicy(
                    retention_days=audit_settings.retention_days,
                    max_events_per_scope=audit_settings.maximum_events_per_scope,
                ),
            )
            runtime = DeepAgentsEmployeeRuntime(
                BailianChatModelResolver(
                    model_settings,
                    initial_model=real_model,
                ),
                tools=WorkflowToolRegistry(workflows, audit=audit),
            )
        employees = EmployeeService(
            SqlAlchemyEmployeeUnitOfWorkFactory(database, tenant_id_provider),
            knowledge_bases,
            workflows=workflows,
            model_configurations=model_configurations,
            guard=resource_guard,
        )
        conversation_events = ConversationEventBroker(
            key_namespace=lambda conversation_id: key_namespace(f"conversation:{conversation_id}"),
            journal=SqlAlchemyEventJournal(database),
            tenant_id_provider=tenant_id_provider,
            persistent_poll_seconds=worker_settings.poll_interval_seconds,
            retention_days=worker_settings.event_retention_days,
            maximum_events_per_stream=worker_settings.maximum_events_per_stream,
        )
        if runtime is None:
            raise RuntimeError("数字员工运行时未完成装配")
        conversations = ConversationService(
            SqlAlchemyConversationUnitOfWorkFactory(database, tenant_id_provider),
            employees=employees,
            knowledge=ConversationKnowledgeResolver(knowledge_adapter),
            runtime=runtime,
            events=conversation_events,
            model_configurations=model_configurations,
            guard=resource_guard,
            tasks=task_queue,
            tenant_id_provider=tenant_id_provider,
            task_max_attempts=worker_settings.maximum_attempts,
        )

        async def handle_conversation(task: object, context: object) -> None:
            from common_agent.tasks import DurableTask, TaskExecutionContext

            if not isinstance(task, DurableTask) or not isinstance(context, TaskExecutionContext):
                raise TypeError("invalid conversation task handler arguments")
            with bind_tenant(_system_tenant_access(task.request.tenant_id)):
                await conversations.execute_reply_task(task, context)

        async def handle_workflow(task: object, context: object) -> None:
            from common_agent.tasks import DurableTask, TaskExecutionContext

            if not isinstance(task, DurableTask) or not isinstance(context, TaskExecutionContext):
                raise TypeError("invalid workflow task handler arguments")
            with bind_tenant(_system_tenant_access(task.request.tenant_id)):
                await workflows.execute_workflow_task(task, context)

        worker_id = _worker_id()
        workflow_slot_count = worker_settings.claim_batch_size // 2
        conversation_slot_count = worker_settings.claim_batch_size - workflow_slot_count
        conversation_workers = tuple(
            TaskWorker(
                task_queue,
                handlers={TaskKind.CONVERSATION_REPLY: handle_conversation},
                worker_id=f"{worker_id}-conversation-{slot}",
                lease_for=timedelta(seconds=worker_settings.lease_seconds),
                heartbeat_interval=timedelta(seconds=worker_settings.heartbeat_seconds),
                execution_guard=task_execution_guard,
            )
            for slot in range(conversation_slot_count)
        )
        workflow_workers = tuple(
            TaskWorker(
                task_queue,
                handlers={TaskKind.WORKFLOW_RUN: handle_workflow},
                worker_id=f"{worker_id}-workflow-{slot}",
                lease_for=timedelta(seconds=worker_settings.lease_seconds),
                heartbeat_interval=timedelta(seconds=worker_settings.heartbeat_seconds),
                execution_guard=task_execution_guard,
            )
            for slot in range(workflow_slot_count)
        )
        await TaskWorkerPool(
            (*conversation_workers, *workflow_workers),
            poll_interval_seconds=worker_settings.poll_interval_seconds,
        ).run(stop)
    finally:
        if workflows is not None:
            await workflows.aclose()
        if conversations is not None:
            await conversations.aclose()
        elif runtime is not None:
            await runtime.aclose()
        if conversation_events is not None:
            await conversation_events.aclose()
        if workflow_events is not None:
            await workflow_events.aclose()
        if knowledge_adapter is not None:
            await knowledge_adapter.aclose()
        if demo_workflow_model is not None:
            await demo_workflow_model.aclose()
        await database.stop()


def _worker_id() -> str:
    hostname = socket.gethostname().strip() or "localhost"
    return f"{hostname[:80]}-{os.getpid()}"


def _system_tenant_access(tenant_id: UUID) -> TenantAccess:
    return TenantAccess(
        tenant_id=tenant_id,
        user_id=UUID(int=0),
        role=TenantRole.OWNER,
    )


__all__ = ["run_worker"]
