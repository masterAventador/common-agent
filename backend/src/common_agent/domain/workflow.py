from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from math import isfinite
from uuid import UUID, uuid4

WORKFLOW_NAME_MAX_LENGTH = 128
WORKFLOW_DESCRIPTION_MAX_LENGTH = 1_000
WORKFLOW_NODE_ID_MAX_LENGTH = 128
WORKFLOW_EDGE_ID_MAX_LENGTH = 128
AI_CHAT_PROMPT_MAX_LENGTH = 12_000
WORKFLOW_KNOWLEDGE_BASE_ID_MAX_LENGTH = 128


class WorkflowValidationError(ValueError):
    def __init__(self, field: str, reason: str) -> None:
        self.field = field
        self.reason = reason
        super().__init__(f"工作流字段 {field} {reason}")


class WorkflowNodeType(StrEnum):
    START = "start"
    AI_CHAT = "ai_chat"
    KNOWLEDGE_RETRIEVAL = "knowledge_retrieval"
    END = "end"


@dataclass(frozen=True, slots=True)
class WorkflowNodePosition:
    x: float
    y: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "x", _coordinate("position.x", self.x))
        object.__setattr__(self, "y", _coordinate("position.y", self.y))


@dataclass(frozen=True, slots=True)
class StartNodeConfig:
    pass


@dataclass(frozen=True, slots=True)
class AiChatNodeConfig:
    prompt: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "prompt",
            _required_text("prompt", self.prompt, AI_CHAT_PROMPT_MAX_LENGTH),
        )


@dataclass(frozen=True, slots=True)
class KnowledgeRetrievalNodeConfig:
    knowledge_base_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "knowledge_base_id",
            _required_text(
                "knowledge_base_id",
                self.knowledge_base_id,
                WORKFLOW_KNOWLEDGE_BASE_ID_MAX_LENGTH,
            ),
        )


@dataclass(frozen=True, slots=True)
class EndNodeConfig:
    pass


type WorkflowNodeConfig = (
    StartNodeConfig | AiChatNodeConfig | KnowledgeRetrievalNodeConfig | EndNodeConfig
)

_CONFIG_TYPES: dict[WorkflowNodeType, type[WorkflowNodeConfig]] = {
    WorkflowNodeType.START: StartNodeConfig,
    WorkflowNodeType.AI_CHAT: AiChatNodeConfig,
    WorkflowNodeType.KNOWLEDGE_RETRIEVAL: KnowledgeRetrievalNodeConfig,
    WorkflowNodeType.END: EndNodeConfig,
}


@dataclass(frozen=True, slots=True)
class WorkflowNode:
    id: str
    type: WorkflowNodeType
    position: WorkflowNodePosition
    config: WorkflowNodeConfig

    def __post_init__(self) -> None:
        node_id = _required_text("id", self.id, WORKFLOW_NODE_ID_MAX_LENGTH)
        if not isinstance(self.type, WorkflowNodeType):
            raise WorkflowValidationError("type", "不是支持的节点类型")
        if not isinstance(self.position, WorkflowNodePosition):
            raise WorkflowValidationError("position", "必须是 WorkflowNodePosition")
        if not isinstance(self.config, _CONFIG_TYPES[self.type]):
            raise WorkflowValidationError("config", f"与 {self.type.value} 节点类型不匹配")
        object.__setattr__(self, "id", node_id)


@dataclass(frozen=True, slots=True)
class WorkflowEdge:
    id: str
    source: str
    target: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "id",
            _required_text("id", self.id, WORKFLOW_EDGE_ID_MAX_LENGTH),
        )
        object.__setattr__(
            self,
            "source",
            _required_text("source", self.source, WORKFLOW_NODE_ID_MAX_LENGTH),
        )
        object.__setattr__(
            self,
            "target",
            _required_text("target", self.target, WORKFLOW_NODE_ID_MAX_LENGTH),
        )


@dataclass(frozen=True, slots=True)
class WorkflowDefinition:
    id: UUID
    name: str
    description: str
    nodes: tuple[WorkflowNode, ...]
    edges: tuple[WorkflowEdge, ...]
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.id, UUID):
            raise WorkflowValidationError("id", "必须是 UUID")
        name = _required_text("name", self.name, WORKFLOW_NAME_MAX_LENGTH)
        description = _optional_text(
            "description",
            self.description,
            WORKFLOW_DESCRIPTION_MAX_LENGTH,
        )
        nodes = _nodes(self.nodes)
        edges = _edges(self.edges)
        _utc_timestamp("created_at", self.created_at)
        _utc_timestamp("updated_at", self.updated_at)
        if self.updated_at < self.created_at:
            raise WorkflowValidationError("updated_at", "不能早于创建时间")

        object.__setattr__(self, "name", name)
        object.__setattr__(self, "description", description)
        object.__setattr__(self, "nodes", nodes)
        object.__setattr__(self, "edges", edges)

    @classmethod
    def create(
        cls,
        *,
        name: str,
        nodes: Iterable[WorkflowNode],
        edges: Iterable[WorkflowEdge],
        description: str = "",
        workflow_id: UUID | None = None,
        now: datetime | None = None,
    ) -> WorkflowDefinition:
        created_at = now or datetime.now(UTC)
        return cls(
            id=workflow_id or uuid4(),
            name=name,
            description=description,
            nodes=tuple(nodes),
            edges=tuple(edges),
            created_at=created_at,
            updated_at=created_at,
        )

    def reconfigure(
        self,
        *,
        name: str,
        description: str,
        nodes: Iterable[WorkflowNode],
        edges: Iterable[WorkflowEdge],
        updated_at: datetime | None = None,
    ) -> WorkflowDefinition:
        changed_at = updated_at or datetime.now(UTC)
        _utc_timestamp("updated_at", changed_at)
        if changed_at < self.updated_at:
            raise WorkflowValidationError("updated_at", "不能早于当前更新时间")
        return replace(
            self,
            name=name,
            description=description,
            nodes=tuple(nodes),
            edges=tuple(edges),
            updated_at=changed_at,
        )


def _nodes(values: Iterable[WorkflowNode]) -> tuple[WorkflowNode, ...]:
    result = tuple(values)
    if any(not isinstance(value, WorkflowNode) for value in result):
        raise WorkflowValidationError("nodes", "必须只包含 WorkflowNode")
    return result


def _edges(values: Iterable[WorkflowEdge]) -> tuple[WorkflowEdge, ...]:
    result = tuple(values)
    if any(not isinstance(value, WorkflowEdge) for value in result):
        raise WorkflowValidationError("edges", "必须只包含 WorkflowEdge")
    return result


def _required_text(field: str, value: object, max_length: int) -> str:
    if not isinstance(value, str):
        raise WorkflowValidationError(field, "必须是字符串")
    normalized = value.strip()
    if not normalized:
        raise WorkflowValidationError(field, "不能为空")
    if len(normalized) > max_length:
        raise WorkflowValidationError(field, f"不能超过 {max_length} 个字符")
    return normalized


def _optional_text(field: str, value: object, max_length: int) -> str:
    if not isinstance(value, str):
        raise WorkflowValidationError(field, "必须是字符串")
    normalized = value.strip()
    if len(normalized) > max_length:
        raise WorkflowValidationError(field, f"不能超过 {max_length} 个字符")
    return normalized


def _coordinate(field: str, value: object) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not isfinite(value):
        raise WorkflowValidationError(field, "必须是有限数值")
    return float(value)


def _utc_timestamp(field: str, value: object) -> datetime:
    if not isinstance(value, datetime):
        raise WorkflowValidationError(field, "必须是时间")
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise WorkflowValidationError(field, "必须使用 UTC 时区")
    return value
