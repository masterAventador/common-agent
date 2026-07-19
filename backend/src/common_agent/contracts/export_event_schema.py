from __future__ import annotations

import argparse
import json
from pathlib import Path

from common_agent.api.routers.conversations import ConversationEventResponse


def export_conversation_event_schema(output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(
        ConversationEventResponse.model_json_schema(),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    output.write_text(f"{serialized}\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="导出 common-agent 会话 SSE 事件契约")
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    export_conversation_event_schema(arguments.output)


if __name__ == "__main__":
    main()
