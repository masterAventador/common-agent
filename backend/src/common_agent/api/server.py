from __future__ import annotations

import uvicorn

from common_agent.bootstrap import ApiSettings


def run_api() -> None:
    settings = ApiSettings.from_env()
    uvicorn.run(
        "common_agent.api.app:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
    )
