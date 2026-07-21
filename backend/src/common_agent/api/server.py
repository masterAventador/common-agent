from __future__ import annotations

import uvicorn

from common_agent.bootstrap import ApiSettings, ProxySettings


def run_api() -> None:
    settings = ApiSettings.from_env()
    proxy = ProxySettings.from_env()
    uvicorn.run(
        "common_agent.api.app:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        forwarded_allow_ips=proxy.forwarded_allow_ips,
    )
