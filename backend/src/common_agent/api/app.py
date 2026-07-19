from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import RequestResponseEndpoint

from common_agent import __version__
from common_agent.adapters.agent.deep_agents import DeepAgentsEmployeeRuntime
from common_agent.adapters.knowledge import RagFlowKnowledgeService
from common_agent.adapters.model.bailian import BailianChatModelAdapter
from common_agent.adapters.persistence import Database
from common_agent.adapters.persistence.conversations import (
    SqlAlchemyConversationUnitOfWorkFactory,
)
from common_agent.adapters.persistence.employees import SqlAlchemyEmployeeUnitOfWorkFactory
from common_agent.api.errors import error_handlers
from common_agent.api.routers import (
    conversation_router,
    employee_router,
    knowledge_router,
    system_router,
)
from common_agent.bootstrap import CorsSettings, DatabaseSettings, ModelSettings, RagFlowSettings
from common_agent.conversations import ConversationEventBroker, ConversationService
from common_agent.employees import EmployeeService
from common_agent.employees.seeds import seed_default_employee
from common_agent.knowledge.retrieval import ConversationKnowledgeResolver
from common_agent.knowledge.service import KnowledgeBaseService


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    database: Database = app.state.database
    await database.start()
    knowledge_adapter: RagFlowKnowledgeService | None = None
    runtime: DeepAgentsEmployeeRuntime | None = None
    conversations: ConversationService | None = None
    try:
        ragflow_settings: RagFlowSettings = app.state.ragflow_settings
        knowledge_adapter = RagFlowKnowledgeService(
            base_url=ragflow_settings.base_url,
            api_key=ragflow_settings.api_key.get_secret_value(),
            expected_version=ragflow_settings.expected_version,
            timeout_seconds=ragflow_settings.timeout_seconds,
        )
        knowledge_bases = KnowledgeBaseService(knowledge_adapter)
        app.state.knowledge_bases = knowledge_bases
        employees = EmployeeService(
            SqlAlchemyEmployeeUnitOfWorkFactory(database),
            knowledge_bases,
        )
        app.state.employees = employees
        await seed_default_employee(employees)
        model = BailianChatModelAdapter(ModelSettings.from_env())
        runtime = DeepAgentsEmployeeRuntime(model)
        conversation_events = ConversationEventBroker()
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
        app.state.ready = True
        yield
    finally:
        app.state.ready = False
        app.state.conversations = None
        app.state.conversation_events = None
        app.state.employees = None
        app.state.knowledge_bases = None
        if conversations is not None:
            await conversations.aclose()
        elif runtime is not None:
            await runtime.aclose()
        if knowledge_adapter is not None:
            await knowledge_adapter.aclose()
        await database.stop()


def create_app() -> FastAPI:
    database = Database(DatabaseSettings.from_env().url)
    cors = CorsSettings.from_env()
    ragflow_settings = RagFlowSettings.from_env()
    app = FastAPI(
        title="common-agent API",
        version=__version__,
        lifespan=lifespan,
        exception_handlers=error_handlers(),
    )
    app.state.database = database
    app.state.ragflow_settings = ragflow_settings
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
    return app
