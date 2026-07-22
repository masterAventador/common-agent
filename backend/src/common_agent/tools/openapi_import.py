from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass

from common_agent.tools.managed_http import (
    ManagedHttpCapabilityCommand,
    ManagedHttpParameterBinding,
)

OPENAPI_MAX_FILE_BYTES = 5 * 1024 * 1024
OPENAPI_MAX_DOCUMENT_DEPTH = 64
OPENAPI_MAX_DOCUMENT_NODES = 50_000
OPENAPI_MAX_OPERATIONS = 200
OPENAPI_MAX_REFERENCE_DEPTH = 32


class OpenApiDocumentError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class ManagedHttpOpenApiDraft:
    operation_key: str
    remote_name: str
    display_name: str
    description: str
    input_schema: dict[str, object]
    method: str
    path_template: str
    parameter_bindings: tuple[ManagedHttpParameterBinding, ...]
    timeout_seconds: int = 30
    response_json_pointer: str | None = None
    enabled: bool = True
    issues: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "input_schema", deepcopy(self.input_schema))
        object.__setattr__(self, "parameter_bindings", tuple(self.parameter_bindings))
        object.__setattr__(self, "issues", tuple(self.issues))

    def command(self) -> ManagedHttpCapabilityCommand:
        return ManagedHttpCapabilityCommand(
            remote_name=self.remote_name,
            display_name=self.display_name,
            description=self.description,
            input_schema=self.input_schema,
            method=self.method,
            path_template=self.path_template,
            parameter_bindings=self.parameter_bindings,
            timeout_seconds=self.timeout_seconds,
            response_json_pointer=self.response_json_pointer,
            enabled=self.enabled,
        )


@dataclass(frozen=True, slots=True)
class ManagedHttpOpenApiPreview:
    title: str
    version: str
    drafts: tuple[ManagedHttpOpenApiDraft, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "drafts", tuple(self.drafts))


def openapi_draft_issues(
    description: str,
    input_schema: dict[str, object],
) -> tuple[str, ...]:
    issues: list[str] = []
    if not description.strip():
        issues.append("能力缺少说明")

    def visit(schema: object, prefix: str) -> None:
        if not isinstance(schema, dict):
            return
        properties = schema.get("properties")
        if isinstance(properties, dict):
            for name, value in properties.items():
                if not isinstance(name, str) or not isinstance(value, dict):
                    continue
                path = f"{prefix}.{name}" if prefix else name
                value_description = value.get("description")
                if not isinstance(value_description, str) or not value_description.strip():
                    issues.append(f"参数 {path} 缺少含义")
                visit(value, path)
        items = schema.get("items")
        if isinstance(items, dict):
            visit(items, f"{prefix}[]")

    visit(input_schema, "")
    return tuple(issues)


__all__ = [
    "OPENAPI_MAX_DOCUMENT_DEPTH",
    "OPENAPI_MAX_DOCUMENT_NODES",
    "OPENAPI_MAX_FILE_BYTES",
    "OPENAPI_MAX_OPERATIONS",
    "OPENAPI_MAX_REFERENCE_DEPTH",
    "ManagedHttpOpenApiDraft",
    "ManagedHttpOpenApiPreview",
    "OpenApiDocumentError",
    "openapi_draft_issues",
]
