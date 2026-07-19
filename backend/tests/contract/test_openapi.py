import json
from pathlib import Path
from typing import Any

from common_agent.api import create_app
from common_agent.api.routers.conversations import ConversationEventResponse

OPENAPI_SNAPSHOT = Path(__file__).resolve().parents[3] / "contracts" / "openapi" / "openapi.json"
CONVERSATION_EVENT_SNAPSHOT = (
    Path(__file__).resolve().parents[3] / "contracts" / "events" / "conversation-event.schema.json"
)


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


def test_openapi_exposes_knowledge_contract_and_stable_validation_errors() -> None:
    schema = _schema()
    paths = schema["paths"]
    knowledge = paths["/api/v1/knowledge-bases"]
    documents = paths["/api/v1/knowledge-bases/{knowledge_base_id}/documents"]

    assert set(knowledge) == {"get", "post"}
    assert set(documents) == {"get", "post"}
    assert knowledge["post"]["responses"]["201"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/KnowledgeBaseResponse"
    }
    assert documents["post"]["requestBody"]["content"]["multipart/form-data"]["schema"]
    for operation in (knowledge["post"], documents["get"], documents["post"]):
        assert operation["responses"]["422"]["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/ErrorEnvelope"
        }

    create_schema = schema["components"]["schemas"]["CreateKnowledgeBaseBody"]
    assert create_schema["properties"]["name"]["minLength"] == 1
    assert create_schema["properties"]["name"]["maxLength"] == 128
    assert create_schema["properties"]["description"]["maxLength"] == 1024
    assert schema["components"]["schemas"]["DocumentParsingStatus"]["enum"] == [
        "uploaded",
        "parsing",
        "completed",
        "failed",
    ]


def test_openapi_exposes_generic_employee_crud_contract() -> None:
    schema = _schema()
    collection = schema["paths"]["/api/v1/employees"]
    detail = schema["paths"]["/api/v1/employees/{employee_id}"]

    assert set(collection) == {"get", "post"}
    assert set(detail) == {"get", "put"}
    assert collection["post"]["responses"]["201"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/EmployeeResponse"
    }
    for operation in (collection["post"], detail["get"], detail["put"]):
        assert operation["responses"]["422"]["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/ErrorEnvelope"
        }

    configuration = schema["components"]["schemas"]["EmployeeConfigurationBody"]
    properties = configuration["properties"]
    assert properties["name"]["maxLength"] == 128
    assert properties["description"]["maxLength"] == 1000
    assert properties["system_prompt"]["maxLength"] == 12000
    assert properties["knowledge_base_id"]["anyOf"][0]["maxLength"] == 128
    assert "allowed_workflow_ids" not in properties


def test_openapi_exposes_conversation_send_stop_retry_and_sse_contracts() -> None:
    schema = _schema()
    paths = schema["paths"]

    assert set(paths["/api/v1/conversations"]) == {"get", "post"}
    assert set(paths["/api/v1/conversations/{conversation_id}/messages"]) == {
        "get",
        "post",
    }
    assert set(paths["/api/v1/conversations/{conversation_id}/events"]) == {"get"}
    assert set(paths["/api/v1/conversations/{conversation_id}/stop"]) == {"post"}
    assert set(paths["/api/v1/messages/{message_id}/retry"]) == {"post"}

    create = paths["/api/v1/conversations"]["post"]
    send = paths["/api/v1/conversations/{conversation_id}/messages"]["post"]
    stop = paths["/api/v1/conversations/{conversation_id}/stop"]["post"]
    retry = paths["/api/v1/messages/{message_id}/retry"]["post"]
    events = paths["/api/v1/conversations/{conversation_id}/events"]["get"]

    assert create["responses"]["201"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ConversationResponse"
    }
    for operation in (send, retry):
        assert operation["responses"]["202"]["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/TurnAcceptedResponse"
        }
    assert stop["responses"]["202"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/StopAcceptedResponse"
    }
    assert events["responses"]["200"]["content"]["text/event-stream"]["schema"] == {
        "$ref": "#/components/schemas/ConversationEventResponse"
    }
    assert (
        schema["components"]["schemas"]["ConversationEventResponse"]["properties"][
            "schema_version"
        ]["const"]
        == "1"
    )

    create_body = schema["components"]["schemas"]["CreateConversationBody"]
    send_body = schema["components"]["schemas"]["SendMessageBody"]
    assert create_body["properties"]["title"]["maxLength"] == 200
    assert send_body["properties"]["content"]["maxLength"] == 200000
    assert set(send_body["required"]) == {"message_id", "content"}


def test_committed_conversation_event_schema_matches_sse_payload_model() -> None:
    committed = json.loads(CONVERSATION_EVENT_SNAPSHOT.read_text(encoding="utf-8"))

    assert committed == ConversationEventResponse.model_json_schema()
