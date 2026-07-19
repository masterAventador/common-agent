import json
from pathlib import Path
from typing import Any

from common_agent.api import create_app

OPENAPI_SNAPSHOT = Path(__file__).resolve().parents[3] / "contracts" / "openapi" / "openapi.json"


def _schema() -> dict[str, Any]:
    return create_app().openapi()


def test_openapi_exposes_health_and_stable_error_envelope() -> None:
    schema = _schema()

    assert schema["info"]["version"] == "0.1.0"
    assert "get" in schema["paths"]["/api/v1/system/health"]
    error_schema = schema["components"]["schemas"]["ErrorEnvelope"]
    assert error_schema["additionalProperties"] is False
    assert set(error_schema["required"]) == {"code", "message", "request_id", "retryable"}


def test_committed_openapi_snapshot_matches_formal_app() -> None:
    committed = json.loads(OPENAPI_SNAPSHOT.read_text(encoding="utf-8"))

    assert committed == _schema()
