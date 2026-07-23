from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from common_agent.contracts.export_event_schema import (
    export_conversation_event_schema,
    export_workflow_run_event_schema,
    main,
)


def test_event_schema_exporters_write_deterministic_json_contracts(tmp_path: Path) -> None:
    conversation_output = tmp_path / "contracts" / "conversation.json"
    workflow_output = tmp_path / "contracts" / "workflow.json"

    export_conversation_event_schema(conversation_output)
    export_workflow_run_event_schema(workflow_output)

    conversation = json.loads(conversation_output.read_text(encoding="utf-8"))
    workflow = json.loads(workflow_output.read_text(encoding="utf-8"))
    assert conversation["title"] == "ConversationEventResponse"
    assert workflow["title"] == "WorkflowRunEventResponse"
    assert conversation_output.read_bytes().endswith(b"\n")
    assert workflow_output.read_bytes().endswith(b"\n")


def test_event_schema_cli_exports_both_contracts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    conversation_output = tmp_path / "conversation.json"
    workflow_output = tmp_path / "workflow.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "export-event-schema",
            "--output",
            str(conversation_output),
            "--workflow-output",
            str(workflow_output),
        ],
    )

    main()

    assert conversation_output.is_file()
    assert workflow_output.is_file()
