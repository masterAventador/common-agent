import json
from pathlib import Path
from typing import Any

from common_agent.api import create_app
from common_agent.api.routers.conversations import ConversationEventResponse
from common_agent.api.routers.workflow_runs import WorkflowRunEventResponse

OPENAPI_SNAPSHOT = Path(__file__).resolve().parents[3] / "contracts" / "openapi" / "openapi.json"
CONVERSATION_EVENT_SNAPSHOT = (
    Path(__file__).resolve().parents[3] / "contracts" / "events" / "conversation-event.schema.json"
)
WORKFLOW_RUN_EVENT_SNAPSHOT = (
    Path(__file__).resolve().parents[3] / "contracts" / "events" / "workflow-run-event.schema.json"
)


def _schema() -> dict[str, Any]:
    return create_app().openapi()


def test_openapi_exposes_health_and_stable_error_envelope() -> None:
    schema = _schema()

    assert schema["info"]["version"] == "0.1.0"
    assert "get" in schema["paths"]["/api/v1/system/health"]
    assert "get" in schema["paths"]["/api/v1/system/status"]
    assert "get" in schema["paths"]["/api/v1/system/metrics"]
    error_schema = schema["components"]["schemas"]["ErrorEnvelope"]
    assert error_schema["additionalProperties"] is False
    assert set(error_schema["required"]) == {"code", "message", "request_id", "retryable"}


def test_openapi_exposes_tool_catalog_and_exact_grant_contracts() -> None:
    schema = _schema()
    paths = schema["paths"]

    assert set(paths["/api/v1/tool-catalog"]) == {"get"}
    assert set(paths["/api/v1/employees/{employee_id}/tool-grants"]) == {"get", "put"}
    assert set(paths["/api/v1/conversations/{conversation_id}/tool-grants"]) == {
        "get",
        "put",
    }
    body = schema["components"]["schemas"]["ToolGrantSelectionBody"]
    assert body["additionalProperties"] is False
    assert set(body["required"]) == {"capability_ids", "collection_ids"}
    response = schema["components"]["schemas"]["ToolGrantResponse"]
    assert set(response["required"]) == {
        "capability_ids",
        "collection_ids",
        "target_id",
        "target_type",
    }


def test_openapi_exposes_masked_mcp_credentials_without_account_login_fields() -> None:
    schema = _schema()
    path = schema["paths"]["/api/v1/mcp-sources/{source_id}/credentials"]

    assert set(path) == {"get", "put"}
    body = schema["components"]["schemas"]["McpCredentialUpdateBody"]
    response = schema["components"]["schemas"]["McpCredentialSummaryResponse"]
    serialized = json.dumps({"body": body, "response": response}, ensure_ascii=False)
    assert "username" not in body["properties"]
    assert "password" not in body["properties"]
    assert "username" not in response["properties"]
    assert "password" not in response["properties"]
    assert "bearer_token" in serialized
    assert "headers" in serialized
    assert "ciphertext" not in serialized
    assert "key_id" not in serialized


def test_openapi_exposes_cookie_session_contract_without_session_tokens() -> None:
    schema = _schema()
    paths = schema["paths"]
    auth_paths = {
        "/api/v1/auth/policy",
        "/api/v1/auth/register",
        "/api/v1/auth/login",
        "/api/v1/auth/session",
        "/api/v1/auth/logout",
        "/api/v1/auth/recovery/reset",
    }
    assert auth_paths <= paths.keys()

    session = schema["components"]["schemas"]["AuthSessionResponse"]
    registration = schema["components"]["schemas"]["RegistrationResponse"]
    assert set(session["required"]) == {
        "absolute_expires_at",
        "csrf_token",
        "email",
        "idle_expires_at",
        "user_id",
    }
    assert "session_token" not in session["properties"]
    assert set(registration["required"]) == {*session["required"], "recovery_codes"}
    assert "session_token" not in registration["properties"]

    register_password = schema["components"]["schemas"]["RegisterBody"]["properties"]["password"]
    assert register_password["format"] == "password"
    assert register_password["writeOnly"] is True
    assert register_password["minLength"] == 8
    reset_password = schema["components"]["schemas"]["RecoveryResetBody"]["properties"][
        "new_password"
    ]
    member_password = schema["components"]["schemas"]["CreateTenantMemberBody"]["properties"][
        "password"
    ]
    assert reset_password["minLength"] == 8
    assert member_password["minLength"] == 8


def test_openapi_documents_authentication_and_csrf_errors_on_protected_routes() -> None:
    schema = _schema()
    public_operations = {
        ("/api/v1/system/health", "get"),
        ("/api/v1/system/status", "get"),
        ("/api/v1/auth/policy", "get"),
        ("/api/v1/auth/register", "post"),
        ("/api/v1/auth/login", "post"),
        ("/api/v1/auth/recovery/reset", "post"),
    }
    error_ref = {"$ref": "#/components/schemas/ErrorEnvelope"}

    for path, operations in schema["paths"].items():
        for method, operation in operations.items():
            if method not in {"get", "post", "put", "delete", "patch"}:
                continue
            if (path, method) in public_operations:
                continue
            assert (
                operation["responses"]["401"]["content"]["application/json"]["schema"] == error_ref
            )
            if method in {"post", "put", "delete", "patch"}:
                assert (
                    operation["responses"]["403"]["content"]["application/json"]["schema"]
                    == error_ref
                )


def test_committed_openapi_snapshot_matches_formal_app() -> None:
    committed = json.loads(OPENAPI_SNAPSHOT.read_text(encoding="utf-8"))

    assert committed == _schema()


def test_openapi_exposes_knowledge_contract_and_stable_validation_errors() -> None:
    schema = _schema()
    paths = schema["paths"]
    knowledge = paths["/api/v1/knowledge-bases"]
    knowledge_detail = paths["/api/v1/knowledge-bases/{knowledge_base_id}"]
    documents = paths["/api/v1/knowledge-bases/{knowledge_base_id}/documents"]

    assert set(knowledge) == {"get", "post"}
    assert set(knowledge_detail) == {"delete"}
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
    assert set(detail) == {"delete", "get", "put"}
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
    assert properties["allowed_workflow_ids"]["maxItems"] == 100
    assert properties["allowed_workflow_ids"]["items"] == {
        "type": "string",
        "format": "uuid",
    }
    assert properties["default_model_configuration_id"] == {
        "type": "string",
        "format": "uuid",
        "title": "Default Model Configuration Id",
    }
    assert "default_model_configuration_id" in configuration["required"]

    response = schema["components"]["schemas"]["EmployeeResponse"]
    assert {
        "default_model_configuration_id",
        "default_model_identifier",
    } <= set(response["required"])


def test_openapi_exposes_conversation_send_stop_retry_and_sse_contracts() -> None:
    schema = _schema()
    paths = schema["paths"]

    assert set(paths["/api/v1/conversations"]) == {"get", "post"}
    assert set(paths["/api/v1/conversations/{conversation_id}"]) == {"delete", "get"}
    assert set(paths["/api/v1/conversations/{conversation_id}/messages"]) == {
        "get",
        "post",
    }
    assert set(paths["/api/v1/conversation-turns"]) == {"post"}
    assert set(paths["/api/v1/conversations/{conversation_id}/events"]) == {"get"}
    assert set(paths["/api/v1/conversations/{conversation_id}/stop"]) == {"post"}
    assert set(paths["/api/v1/messages/{message_id}/retry"]) == {"post"}

    create = paths["/api/v1/conversations"]["post"]
    create_first_turn = paths["/api/v1/conversation-turns"]["post"]
    send = paths["/api/v1/conversations/{conversation_id}/messages"]["post"]
    stop = paths["/api/v1/conversations/{conversation_id}/stop"]["post"]
    retry = paths["/api/v1/messages/{message_id}/retry"]["post"]
    events = paths["/api/v1/conversations/{conversation_id}/events"]["get"]

    assert create["responses"]["201"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ConversationResponse"
    }
    assert create_first_turn["responses"]["202"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ConversationTurnAcceptedResponse"
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
        == "2"
    )
    event = schema["components"]["schemas"]["ConversationEventResponse"]
    assert "tool_call" in event["required"]
    kinds = schema["components"]["schemas"]["ConversationEventKind"]["enum"]
    assert {
        "assistant.tool.started",
        "assistant.tool.completed",
        "assistant.tool.failed",
    } <= set(kinds)

    create_body = schema["components"]["schemas"]["CreateConversationBody"]
    first_turn_body = schema["components"]["schemas"]["CreateConversationTurnBody"]
    send_body = schema["components"]["schemas"]["SendMessageBody"]
    assert create_body["properties"]["title"]["maxLength"] == 200
    assert send_body["properties"]["content"]["maxLength"] == 200000
    assert set(send_body["required"]) == {"message_id", "content"}
    assert set(first_turn_body["required"]) == {
        "content",
        "conversation_id",
        "message_id",
        "model_configuration_id",
    }
    conversation = schema["components"]["schemas"]["ConversationResponse"]
    assert {"source", "employee_id", "model_configuration_id"} <= set(conversation["required"])
    history = schema["components"]["schemas"]["ConversationHistoryItemResponse"]
    assert "employee_name" in history["required"]
    message = schema["components"]["schemas"]["MessageResponse"]
    assert {"model_configuration_id", "model_identifier"} <= set(message["required"])


def test_openapi_exposes_discriminated_workflow_crud_and_validation_contracts() -> None:
    schema = _schema()
    paths = schema["paths"]

    assert set(paths["/api/v1/workflows"]) == {"get", "post"}
    assert set(paths["/api/v1/workflows/validate"]) == {"post"}
    assert set(paths["/api/v1/workflows/{workflow_id}"]) == {"delete", "get", "put"}
    assert paths["/api/v1/workflows"]["post"]["responses"]["201"]["content"]["application/json"][
        "schema"
    ] == {"$ref": "#/components/schemas/WorkflowResponse"}
    assert paths["/api/v1/workflows/validate"]["post"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"] == {"$ref": "#/components/schemas/WorkflowValidationResponse"}

    configuration = schema["components"]["schemas"]["WorkflowConfigurationBody"]
    assert configuration["properties"]["name"]["maxLength"] == 128
    node_items = configuration["properties"]["nodes"]["items"]
    assert node_items == {"$ref": "#/components/schemas/WorkflowNodeBody"}
    node_union = schema["components"]["schemas"]["WorkflowNodeBody"]
    assert set(node_union["discriminator"]["mapping"]) == {
        "start",
        "ai_chat",
        "knowledge_retrieval",
        "end",
    }
    assert schema["components"]["schemas"]["AiChatNodeConfigBody"]["additionalProperties"] is False
    assert (
        schema["components"]["schemas"]["AiChatNodeConfigBody"]["properties"]["prompt"]["maxLength"]
        == 12000
    )


def test_committed_conversation_event_schema_matches_sse_payload_model() -> None:
    committed = json.loads(CONVERSATION_EVENT_SNAPSHOT.read_text(encoding="utf-8"))

    assert committed == ConversationEventResponse.model_json_schema()


def test_openapi_exposes_workflow_run_start_summary_stop_and_sse() -> None:
    schema = _schema()
    paths = schema["paths"]
    start = paths["/api/v1/workflows/{workflow_id}/runs"]["post"]
    conversation_runs = paths["/api/v1/workflow-runs"]["get"]
    summary = paths["/api/v1/workflow-runs/{run_id}"]["get"]
    stop = paths["/api/v1/workflow-runs/{run_id}/stop"]["post"]
    events = paths["/api/v1/workflow-runs/{run_id}/events"]["get"]

    assert start["responses"]["202"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/WorkflowRunResponse"
    }
    assert summary["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/WorkflowRunResponse"
    }
    conversation_schema = conversation_runs["responses"]["200"]["content"]["application/json"][
        "schema"
    ]
    assert conversation_schema == {
        "$ref": "#/components/schemas/CursorPageResponse_WorkflowRunResponse_"
    }
    assert conversation_runs["parameters"][0]["name"] == "conversation_id"
    assert conversation_runs["parameters"][0]["required"] is True
    assert stop["responses"]["202"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/WorkflowRunStopAcceptedResponse"
    }
    assert events["responses"]["200"]["content"]["text/event-stream"]["schema"] == {
        "$ref": "#/components/schemas/WorkflowRunEventResponse"
    }
    body = schema["components"]["schemas"]["StartWorkflowRunBody"]
    assert body["properties"]["input"]["maxLength"] == 200000
    assert set(body["required"]) == {"run_id", "input"}
    run = schema["components"]["schemas"]["WorkflowRunResponse"]
    assert "origin" in run["required"]
    assert "WorkflowRunOriginResponse" in str(run["properties"]["origin"])


def test_openapi_exposes_one_bounded_cursor_contract_for_all_resource_lists() -> None:
    schema = _schema()
    collections = {
        "/api/v1/conversations": "ConversationHistoryItemResponse",
        "/api/v1/employees": "EmployeeResponse",
        "/api/v1/knowledge-bases": "KnowledgeBaseResponse",
        "/api/v1/workflows": "WorkflowResponse",
        "/api/v1/workflow-runs": "WorkflowRunResponse",
    }

    for path, item_schema in collections.items():
        operation = schema["paths"][path]["get"]
        response_schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
        assert response_schema == {
            "$ref": f"#/components/schemas/CursorPageResponse_{item_schema}_"
        }
        parameters = {parameter["name"]: parameter for parameter in operation["parameters"]}
        assert parameters["search"]["schema"]["maxLength"] == 128
        assert parameters["limit"]["schema"]["minimum"] == 1
        assert parameters["limit"]["schema"]["maximum"] == 100
        assert parameters["limit"]["schema"]["default"] == 20
        assert parameters["cursor"]["schema"]["anyOf"][0]["maxLength"] == 1024

        page_schema = schema["components"]["schemas"][f"CursorPageResponse_{item_schema}_"]
        assert set(page_schema["required"]) == {"items", "next_cursor"}
        assert page_schema["additionalProperties"] is False


def test_committed_workflow_run_event_schema_matches_sse_payload_model() -> None:
    committed = json.loads(WORKFLOW_RUN_EVENT_SNAPSHOT.read_text(encoding="utf-8"))

    assert committed == WorkflowRunEventResponse.model_json_schema()
