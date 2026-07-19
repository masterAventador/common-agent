from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import RequestResponseEndpoint

from common_agent import __version__
from common_agent.adapters.agent.deep_agents import DeepAgentsEmployeeRuntime
from common_agent.adapters.agent.workflow_tools import WorkflowToolRegistry
from common_agent.adapters.demo import (
    DemoEmployeeRuntime,
    DemoKnowledgeService,
    DemoWorkflowModel,
)
from common_agent.adapters.knowledge import RagFlowKnowledgeService
from common_agent.adapters.model.bailian import BailianChatModelAdapter
from common_agent.adapters.persistence import Database
from common_agent.adapters.persistence.conversations import (
    SqlAlchemyConversationUnitOfWorkFactory,
)
from common_agent.adapters.persistence.employees import SqlAlchemyEmployeeUnitOfWorkFactory
from common_agent.adapters.persistence.workflows import SqlAlchemyWorkflowUnitOfWorkFactory
from common_agent.api.errors import error_handlers
from common_agent.api.routers import (
    conversation_router,
    employee_router,
    knowledge_router,
    system_router,
    workflow_router,
    workflow_run_router,
)
from common_agent.application.workflow_service import WorkflowService
from common_agent.bootstrap import (
    CorsSettings,
    DatabaseSettings,
    IntegrationModeSettings,
    ModelSettings,
    RagFlowSettings,
)
from common_agent.conversations import ConversationEventBroker, ConversationService
from common_agent.employees import EmployeeService
from common_agent.employees.seeds import seed_default_employee
from common_agent.knowledge.retrieval import ConversationKnowledgeResolver
from common_agent.knowledge.service import KnowledgeBaseService
from common_agent.models.base import TextStreamingModel
from common_agent.workflows.compiler import WorkflowCompiler
from common_agent.workflows.events import WorkflowEventBroker
from common_agent.workflows.nodes.registry import create_workflow_node_registry


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    database: Database = app.state.database
    await database.start()
    knowledge_adapter: RagFlowKnowledgeService | DemoKnowledgeService | None = None
    runtime: DeepAgentsEmployeeRuntime | DemoEmployeeRuntime | None = None
    conversations: ConversationService | None = None
    workflows: WorkflowService | None = None
    demo_workflow_model: DemoWorkflowModel | None = None
    try:
        integration_mode: IntegrationModeSettings = app.state.integration_mode
        workflow_model: TextStreamingModel
        if integration_mode.mode == "demo":
            knowledge_adapter = DemoKnowledgeService()
            runtime = DemoEmployeeRuntime()
            demo_workflow_model = DemoWorkflowModel()
            workflow_model = demo_workflow_model
        else:
            ragflow_settings: RagFlowSettings = app.state.ragflow_settings
            knowledge_adapter = RagFlowKnowledgeService(
                base_url=ragflow_settings.base_url,
                api_key=ragflow_settings.api_key.get_secret_value(),
                expected_version=ragflow_settings.expected_version,
                timeout_seconds=ragflow_settings.timeout_seconds,
            )
            model = BailianChatModelAdapter(ModelSettings.from_env())
            workflow_model = model
        knowledge_bases = KnowledgeBaseService(knowledge_adapter)
        app.state.knowledge_bases = knowledge_bases
        workflow_events = WorkflowEventBroker()
        workflows = WorkflowService(
            SqlAlchemyWorkflowUnitOfWorkFactory(database),
            knowledge_bases,
            compiler=WorkflowCompiler(
                create_workflow_node_registry(workflow_model, knowledge_bases)
            ),
            events=workflow_events,
        )
        app.state.workflow_events = workflow_events
        app.state.workflows = workflows
        if integration_mode.mode != "demo":
            runtime = DeepAgentsEmployeeRuntime(
                model,
                tools=WorkflowToolRegistry(workflows),
            )
        employees = EmployeeService(
            SqlAlchemyEmployeeUnitOfWorkFactory(database),
            knowledge_bases,
            workflows=workflows,
        )
        app.state.employees = employees
        await seed_default_employee(employees)
        conversation_events = ConversationEventBroker()
        if runtime is None:
            raise RuntimeError("数字员工运行时未完成装配")
        conversations = ConversationService(
            SqlAlchemyConversationUnitOfWorkFactory(database),
            employees=employees,
            knowledge=ConversationKnowledgeResolver(knowledge_adapter),
            runtime=runtime,
            events=conversation_events,
        )
        app.state.conversation_events = conversation_events
        app.state.conversations = conversations
        await conversations.recover_interrupted()
        await workflows.recover_interrupted()
        app.state.ready = True
        yield
    finally:
        app.state.ready = False
        app.state.conversations = None
        app.state.conversation_events = None
        app.state.employees = None
        app.state.workflows = None
        app.state.workflow_events = None
        app.state.knowledge_bases = None
        if workflows is not None:
            await workflows.aclose()
        if conversations is not None:
            await conversations.aclose()
        elif runtime is not None:
            await runtime.aclose()
        if knowledge_adapter is not None:
            await knowledge_adapter.aclose()
        if demo_workflow_model is not None:
            await demo_workflow_model.aclose()
        await database.stop()


def create_app() -> FastAPI:
    database = Database(DatabaseSettings.from_env().url)
    cors = CorsSettings.from_env()
    integration_mode = IntegrationModeSettings.from_env()
    app = FastAPI(
        title="common-agent API",
        version=__version__,
        lifespan=lifespan,
        exception_handlers=error_handlers(),
    )
    app.state.database = database
    app.state.integration_mode = integration_mode
    app.state.ragflow_settings = (
        RagFlowSettings.from_env() if integration_mode.mode == "real" else None
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(cors.origins),
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def add_request_id(request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = str(uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    app.include_router(system_router)
    app.include_router(knowledge_router)
    app.include_router(employee_router)
    app.include_router(conversation_router)
    app.include_router(workflow_router)
    app.include_router(workflow_run_router)
    return app
