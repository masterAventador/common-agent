from __future__ import annotations

import asyncio
import os

from tests.support.ragflow import delete_datasets_named


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def main() -> None:
    deleted = asyncio.run(
        delete_datasets_named(
            _required("RAGFLOW_BASE_URL"),
            _required("RAGFLOW_API_KEY"),
            _required("COMMON_AGENT_E2E_KNOWLEDGE_NAME"),
        )
    )
    print(f"已清理 K2-06 知识库: {deleted}")


if __name__ == "__main__":
    main()
