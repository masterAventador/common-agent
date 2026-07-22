from __future__ import annotations

from typing import Protocol, runtime_checkable

from common_agent.tools.openapi_import import ManagedHttpOpenApiPreview


@runtime_checkable
class ManagedHttpOpenApiParserPort(Protocol):
    def parse(self, content: bytes, filename: str) -> ManagedHttpOpenApiPreview: ...


__all__ = ["ManagedHttpOpenApiParserPort"]
