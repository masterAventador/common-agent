from __future__ import annotations

import asyncio
import os

from tests.support.ragflow import cancel_document_parsing


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def main() -> None:
    asyncio.run(
        cancel_document_parsing(
            _required("RAGFLOW_BASE_URL"),
            _required("RAGFLOW_API_KEY"),
            _required("COMMON_AGENT_E2E_KNOWLEDGE_BASE_ID"),
            _required("COMMON_AGENT_E2E_DOCUMENT_ID"),
        )
    )
    print("已通过 RAGFlow 正式接口停止 K2-06 文档解析")


if __name__ == "__main__":
    main()
