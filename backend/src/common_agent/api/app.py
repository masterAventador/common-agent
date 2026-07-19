from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import RequestResponseEndpoint

from common_agent import __version__
from common_agent.adapters.persistence import Database
from common_agent.api.errors import error_handlers
from common_agent.api.routers import system_router
from common_agent.bootstrap import DatabaseSettings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    database: Database = app.state.database
    await database.start()
    app.state.ready = True
    try:
        yield
    finally:
        app.state.ready = False
        await database.stop()


def create_app() -> FastAPI:
    database = Database(DatabaseSettings.from_env().url)
    app = FastAPI(
        title="common-agent API",
        version=__version__,
        lifespan=lifespan,
        exception_handlers=error_handlers(),
    )
    app.state.database = database

    @app.middleware("http")
    async def add_request_id(request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = str(uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    app.include_router(system_router)
    return app
