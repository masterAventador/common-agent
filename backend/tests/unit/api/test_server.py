from __future__ import annotations

import pytest
import uvicorn

from common_agent.api.server import run_api


def test_run_api_keeps_uvicorn_inside_http_boundary(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def run(app: str, **kwargs: object) -> None:
        captured["app"] = app
        captured.update(kwargs)

    monkeypatch.setenv("COMMON_AGENT_API_HOST", "127.0.0.1")
    monkeypatch.setenv("COMMON_AGENT_API_PORT", "18200")
    monkeypatch.setattr(uvicorn, "run", run)

    run_api()

    assert captured == {
        "app": "common_agent.api.app:create_app",
        "factory": True,
        "host": "127.0.0.1",
        "port": 18200,
    }
