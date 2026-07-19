from __future__ import annotations

import argparse
import json
from pathlib import Path

from common_agent.api.routers.conversations import ConversationEventResponse
from common_agent.api.routers.workflow_runs import WorkflowRunEventResponse


def _export_schema(output: Path, schema: dict[str, object]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(
        schema,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    output.write_text(f"{serialized}\n", encoding="utf-8")


def export_conversation_event_schema(output: Path) -> None:
    _export_schema(output, ConversationEventResponse.model_json_schema())


def export_workflow_run_event_schema(output: Path) -> None:
    _export_schema(output, WorkflowRunEventResponse.model_json_schema())


def main() -> None:
    parser = argparse.ArgumentParser(description="导出 common-agent SSE 事件契约")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workflow-output", type=Path)
    arguments = parser.parse_args()
    export_conversation_event_schema(arguments.output)
    if arguments.workflow_output is not None:
        export_workflow_run_event_schema(arguments.workflow_output)


if __name__ == "__main__":
    main()
