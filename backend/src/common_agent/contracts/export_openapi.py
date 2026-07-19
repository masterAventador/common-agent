from __future__ import annotations

import argparse
import json
from pathlib import Path

from common_agent.api import create_app


def export_openapi(output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(
        create_app().openapi(),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    output.write_text(f"{serialized}\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="导出 common-agent OpenAPI 契约")
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    export_openapi(arguments.output)


if __name__ == "__main__":
    main()
