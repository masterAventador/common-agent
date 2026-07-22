from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from common_agent import __version__
from common_agent.adapters.agent.deep_agents import DeepAgentsEmployeeRuntime
from common_agent.adapters.agent.workflow_tools import WorkflowToolRegistry
from common_agent.adapters.auth import Argon2PasswordHasher
from common_agent.adapters.demo import (
    DemoEmployeeRuntime,
    DemoKnowledgeService,
    DemoWorkflowModel,
)
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
    SqlAlchemyAuthStore,
    SqlAlchemyEventJournal,
    SqlAlchemyKnowledgeOwnershipStore,
    SqlAlchemyTaskQueue,
    SqlAlchemyTenancyStore,
    SqlAlchemyToolUnitOfWorkFactory,
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
from common_agent.adapters.persistence.resources import SqlAlchemyResourceDeletionStore
from common_agent.adapters.persistence.workflows import SqlAlchemyWorkflowUnitOfWorkFactory
from common_agent.adapters.workflow.langgraph import LangGraphWorkflowCompiler
from common_agent.api.audit import audit_http_request
from common_agent.api.authentication import enforce_request_security, require_authenticated
from common_agent.api.errors import ErrorEnvelope, error_handlers
from common_agent.api.observability import observe_http_request
from common_agent.api.routers import (
    audit_router,
    auth_router,
    conversation_router,
    employee_router,
    knowledge_router,
    model_configuration_router,
    system_router,
    tenant_router,
    tool_router,
    workflow_router,
    workflow_run_router,
)
from common_agent.api.tenancy import require_tenant_access
from common_agent.application.resource_deletion import ResourceDeletionService
from common_agent.application.resource_locks import ResourceMutationGuard
from common_agent.application.system_service import SystemService
from common_agent.application.workflow_service import WorkflowService
from common_agent.application.workflow_targets import WorkflowAiTargetDirectory
from common_agent.audit import AuditPolicy, AuditService
from common_agent.auth import AuthConfiguration, AuthenticationService
from common_agent.bootstrap import (
    AuditSettings,
    AuthSettings,
    CorsSettings,
    DatabaseSettings,
    IntegrationModeSettings,
    ModelSettings,
    RagFlowSettings,
    WorkerSettings,
)
from common_agent.conversations import ConversationEventBroker, ConversationService
from common_agent.employees import EmployeeService
from common_agent.employees.seeds import seed_default_employee
from common_agent.knowledge.retrieval import ConversationKnowledgeResolver
from common_agent.knowledge.service import KnowledgeBaseService
from common_agent.lifecycle import AsyncCleanup, run_cleanups
from common_agent.model_configurations import (
    ModelConfigurationService,
    ModelConfigurationVerifier,
)
from common_agent.model_configurations.defaults import (
    PLATFORM_DEFAULT_MODEL_IDENTIFIER,
)
from common_agent.models.base import TextStreamingModel
from common_agent.observability import MetricsRegistry, configure_json_logging
from common_agent.tenancy import (
    TenancyService,
    TenantAccess,
    TenantRole,
    bind_tenant,
    current_tenant,
)
from common_agent.tenancy.constants import DEFAULT_TENANT_ID
from common_agent.tools import ToolService
from common_agent.workflows.ai_targets import (
    StaticWorkflowModelResolver,
    WorkflowAiTargetExecutor,
    WorkflowModelResolver,
)
from common_agent.workflows.events import WorkflowEventBroker
from common_agent.workflows.nodes.registry import create_workflow_node_registry


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    database: Database = app.state.database
    database_started = False
    knowledge_adapter: RagFlowKnowledgeService | DemoKnowledgeService | None = None
    runtime: DeepAgentsEmployeeRuntime | DemoEmployeeRuntime | None = None
    conversations: ConversationService | None = None
    workflows: WorkflowService | None = None
    demo_workflow_model: DemoWorkflowModel | None = None
    conversation_events: ConversationEventBroker | None = None
    workflow_events: WorkflowEventBroker | None = None
    real_model: BailianChatModelAdapter | None = None
    deep_agent_model_resolver: BailianChatModelResolver | None = None
    try:
        await database.start()
        database_started = True
        audit_settings: AuditSettings = app.state.audit_settings
        app.state.audit = AuditService(
            SqlAlchemyAuditStore(database),
            AuditPolicy(
                retention_days=audit_settings.retention_days,
                max_events_per_scope=audit_settings.maximum_events_per_scope,
            ),
        )
        auth_settings: AuthSettings = app.state.auth_settings
        app.state.authentication = AuthenticationService(
            SqlAlchemyAuthStore(database),
            Argon2PasswordHasher(),
            AuthConfiguration(
                bootstrap_token=auth_settings.bootstrap_token.get_secret_value(),
                session_idle_seconds=auth_settings.session_idle_seconds,
                session_absolute_seconds=auth_settings.session_absolute_seconds,
                login_window_seconds=auth_settings.login_window_seconds,
                login_max_attempts=auth_settings.login_max_attempts,
            ),
        )
        tenancy_store = SqlAlchemyTenancyStore(database)
        app.state.tenancy = TenancyService(tenancy_store)

        def tenant_id_provider() -> UUID:
            return current_tenant().tenant_id

        def key_namespace(key: str) -> str:
            return f"tenant:{current_tenant().tenant_id}:{key}"

        app.state.tools = ToolService(SqlAlchemyToolUnitOfWorkFactory(database, tenant_id_provider))

        integration_mode: IntegrationModeSettings = app.state.integration_mode
        worker_settings: WorkerSettings = app.state.worker_settings
        task_queue = SqlAlchemyTaskQueue(database)
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
            ragflow_settings: RagFlowSettings = app.state.ragflow_settings
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
        resource_guard = ResourceMutationGuard(
            key_namespace,
            distributed=MySqlNamedLockProvider(database),
        )
        app.state.knowledge_bases = knowledge_bases
        model_configurations = ModelConfigurationService(
            SqlAlchemyModelConfigurationUnitOfWorkFactory(database, tenant_id_provider),
            verifier=model_configuration_verifier,
            guard=resource_guard,
        )
        app.state.model_configurations = model_configurations
        employee_units = SqlAlchemyEmployeeUnitOfWorkFactory(database, tenant_id_provider)
        ai_target_directory = WorkflowAiTargetDirectory(employee_units, model_configurations)
        if integration_mode.mode == "demo":
            workflow_model_resolver: WorkflowModelResolver = StaticWorkflowModelResolver(
                workflow_model
            )
        else:
            deep_agent_model_resolver = BailianChatModelResolver(
                model_settings,
                initial_model=real_model,
            )
            workflow_model_resolver = deep_agent_model_resolver
        workflow_ai_targets = WorkflowAiTargetExecutor(
            ai_target_directory,
            workflow_model_resolver,
            knowledge_bases,
            employee_runtime=runtime,
        )
        app.state.resource_deletions = ResourceDeletionService(
            SqlAlchemyResourceDeletionStore(database, tenant_id_provider),
            knowledge_bases,
            guard=resource_guard,
        )
        app.state.system = SystemService(
            integration_mode=integration_mode.mode,
            model_provider=workflow_model.provider_name,
            knowledge=knowledge_adapter,
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
            ai_targets=ai_target_directory,
            compiler=LangGraphWorkflowCompiler(
                create_workflow_node_registry(workflow_ai_targets, knowledge_bases)
            ),
            events=workflow_events,
            guard=resource_guard,
            tasks=task_queue,
            tenant_id_provider=tenant_id_provider,
            task_max_attempts=worker_settings.maximum_attempts,
        )
        app.state.workflow_events = workflow_events
        app.state.workflows = workflows
        if integration_mode.mode != "demo":
            if deep_agent_model_resolver is None:
                raise RuntimeError("百炼模型解析器尚未完成装配")
            runtime = DeepAgentsEmployeeRuntime(
                deep_agent_model_resolver,
                tools=WorkflowToolRegistry(workflows, audit=app.state.audit),
            )
            workflow_ai_targets.bind_employee_runtime(runtime)
        employees = EmployeeService(
            employee_units,
            knowledge_bases,
            workflows=workflows,
            model_configurations=model_configurations,
            guard=resource_guard,
        )
        app.state.employees = employees
        with bind_tenant(_system_tenant_access(DEFAULT_TENANT_ID)):
            platform_default_model = await model_configurations.get_by_identifier(
                PLATFORM_DEFAULT_MODEL_IDENTIFIER
            )
            await seed_default_employee(
                employees,
                default_model_configuration_id=platform_default_model.id,
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
        app.state.conversation_events = conversation_events
        app.state.conversations = conversations
        app.state.ready = True
        yield
    finally:
        app.state.ready = False
        app.state.authentication = None
        app.state.audit = None
        app.state.tenancy = None
        app.state.tools = None
        app.state.conversations = None
        app.state.conversation_events = None
        app.state.employees = None
        app.state.workflows = None
        app.state.workflow_events = None
        app.state.knowledge_bases = None
        app.state.model_configurations = None
        app.state.resource_deletions = None
        app.state.system = None
        cleanups: list[AsyncCleanup] = []
        if workflows is not None:
            cleanups.append(workflows.aclose)
        if conversations is not None:
            cleanups.append(conversations.aclose)
        elif runtime is not None:
            cleanups.append(runtime.aclose)
        elif deep_agent_model_resolver is not None:
            cleanups.append(deep_agent_model_resolver.aclose)
        elif real_model is not None:
            cleanups.append(real_model.aclose)
        if conversation_events is not None:
            cleanups.append(conversation_events.aclose)
        if workflow_events is not None:
            cleanups.append(workflow_events.aclose)
        if knowledge_adapter is not None:
            cleanups.append(knowledge_adapter.aclose)
        if demo_workflow_model is not None:
            cleanups.append(demo_workflow_model.aclose)
        if database_started:
            cleanups.append(database.stop)
        await run_cleanups(*cleanups)


def create_app() -> FastAPI:
    configure_json_logging()
    database = Database(DatabaseSettings.from_env().url)
    cors = CorsSettings.from_env()
    auth_settings = AuthSettings.from_env()
    audit_settings = AuditSettings.from_env()
    integration_mode = IntegrationModeSettings.from_env()
    app = FastAPI(
        title="common-agent API",
        version=__version__,
        lifespan=lifespan,
        exception_handlers=error_handlers(),
    )
    app.state.database = database
    app.state.metrics = MetricsRegistry()
    app.state.integration_mode = integration_mode
    app.state.auth_settings = auth_settings
    app.state.audit_settings = audit_settings
    app.state.worker_settings = WorkerSettings.from_env()
    app.state.audit = None
    app.state.cors_settings = cors
    app.state.authentication = None
    app.state.tenancy = None
    app.state.tools = None
    app.state.ragflow_settings = (
        RagFlowSettings.from_env() if integration_mode.mode == "real" else None
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(cors.origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.middleware("http")(enforce_request_security)
    app.middleware("http")(audit_http_request)
    app.middleware("http")(observe_http_request)

    app.include_router(system_router)
    app.include_router(auth_router)
    app.include_router(tenant_router)
    protected = [Depends(require_authenticated), Depends(require_tenant_access)]
    protected_responses: dict[int | str, dict[str, Any]] = {
        401: {"model": ErrorEnvelope},
        403: {"model": ErrorEnvelope},
    }
    app.include_router(
        audit_router,
        dependencies=protected,
        responses=protected_responses,
    )
    app.include_router(
        knowledge_router,
        dependencies=protected,
        responses=protected_responses,
    )
    app.include_router(
        model_configuration_router,
        dependencies=protected,
        responses=protected_responses,
    )
    app.include_router(
        employee_router,
        dependencies=protected,
        responses=protected_responses,
    )
    app.include_router(
        conversation_router,
        dependencies=protected,
        responses=protected_responses,
    )
    app.include_router(
        workflow_router,
        dependencies=protected,
        responses=protected_responses,
    )
    app.include_router(
        workflow_run_router,
        dependencies=protected,
        responses=protected_responses,
    )
    app.include_router(
        tool_router,
        dependencies=protected,
        responses=protected_responses,
    )
    return app


def _system_tenant_access(tenant_id: UUID) -> TenantAccess:
    return TenantAccess(
        tenant_id=tenant_id,
        user_id=UUID(int=0),
        role=TenantRole.OWNER,
    )
