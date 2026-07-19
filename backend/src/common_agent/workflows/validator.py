from __future__ import annotations

from collections import Counter, deque
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from common_agent.domain.workflow import WorkflowEdge, WorkflowNode, WorkflowNodeType

MAX_WORKFLOW_NODES = 100
MAX_WORKFLOW_EDGES = 200


class WorkflowValidationCode(StrEnum):
    NODE_LIMIT_EXCEEDED = "node_limit_exceeded"
    EDGE_LIMIT_EXCEEDED = "edge_limit_exceeded"
    DUPLICATE_NODE_ID = "duplicate_node_id"
    DUPLICATE_EDGE_ID = "duplicate_edge_id"
    MISSING_START = "missing_start"
    MULTIPLE_STARTS = "multiple_starts"
    MISSING_END = "missing_end"
    EDGE_SOURCE_MISSING = "edge_source_missing"
    EDGE_TARGET_MISSING = "edge_target_missing"
    SELF_LOOP = "self_loop"
    DUPLICATE_CONNECTION = "duplicate_connection"
    START_HAS_INCOMING_EDGE = "start_has_incoming_edge"
    END_HAS_OUTGOING_EDGE = "end_has_outgoing_edge"
    MULTIPLE_OUTGOING_EDGES = "multiple_outgoing_edges"
    ISOLATED_NODE = "isolated_node"
    UNREACHABLE_FROM_START = "unreachable_from_start"
    CANNOT_REACH_END = "cannot_reach_end"
    CYCLE_DETECTED = "cycle_detected"
    KNOWLEDGE_BASE_NOT_FOUND = "knowledge_base_not_found"


@dataclass(frozen=True, slots=True)
class WorkflowValidationIssue:
    code: WorkflowValidationCode
    message: str
    node_id: str | None = None
    edge_id: str | None = None


class WorkflowGraphInvalid(ValueError):
    def __init__(self, issues: tuple[WorkflowValidationIssue, ...]) -> None:
        self.issues = issues
        super().__init__("工作流图校验失败")


def validate_workflow_graph(
    nodes: Iterable[WorkflowNode],
    edges: Iterable[WorkflowEdge],
) -> tuple[WorkflowValidationIssue, ...]:
    graph_nodes = tuple(nodes)
    graph_edges = tuple(edges)
    issues: list[WorkflowValidationIssue] = []

    if len(graph_nodes) > MAX_WORKFLOW_NODES:
        issues.append(
            _issue(
                WorkflowValidationCode.NODE_LIMIT_EXCEEDED,
                f"节点数量不能超过 {MAX_WORKFLOW_NODES}",
            )
        )
    if len(graph_edges) > MAX_WORKFLOW_EDGES:
        issues.append(
            _issue(
                WorkflowValidationCode.EDGE_LIMIT_EXCEEDED,
                f"边数量不能超过 {MAX_WORKFLOW_EDGES}",
            )
        )

    node_id_counts = Counter(node.id for node in graph_nodes)
    duplicate_node_ids = {node_id for node_id, count in node_id_counts.items() if count > 1}
    for node_id in sorted(duplicate_node_ids):
        issues.append(
            _issue(
                WorkflowValidationCode.DUPLICATE_NODE_ID,
                "节点 ID 不能重复",
                node_id=node_id,
            )
        )

    edge_id_counts = Counter(edge.id for edge in graph_edges)
    for edge_id in sorted(edge_id for edge_id, count in edge_id_counts.items() if count > 1):
        issues.append(
            _issue(
                WorkflowValidationCode.DUPLICATE_EDGE_ID,
                "边 ID 不能重复",
                edge_id=edge_id,
            )
        )

    start_nodes = tuple(node for node in graph_nodes if node.type is WorkflowNodeType.START)
    end_nodes = tuple(node for node in graph_nodes if node.type is WorkflowNodeType.END)
    if not start_nodes:
        issues.append(_issue(WorkflowValidationCode.MISSING_START, "必须包含一个开始节点"))
    elif len(start_nodes) > 1:
        issues.append(_issue(WorkflowValidationCode.MULTIPLE_STARTS, "只能包含一个开始节点"))
    if not end_nodes:
        issues.append(_issue(WorkflowValidationCode.MISSING_END, "必须至少包含一个结束节点"))

    known_node_ids = set(node_id_counts)
    start_ids = {node.id for node in start_nodes}
    end_ids = {node.id for node in end_nodes}
    valid_connections: set[tuple[str, str]] = set()
    connection_counts: Counter[tuple[str, str]] = Counter()

    for edge in graph_edges:
        source_exists = edge.source in known_node_ids
        target_exists = edge.target in known_node_ids
        if not source_exists:
            issues.append(
                _issue(
                    WorkflowValidationCode.EDGE_SOURCE_MISSING,
                    "边的起点节点不存在",
                    edge_id=edge.id,
                )
            )
        if not target_exists:
            issues.append(
                _issue(
                    WorkflowValidationCode.EDGE_TARGET_MISSING,
                    "边的终点节点不存在",
                    edge_id=edge.id,
                )
            )
        if edge.source == edge.target:
            issues.append(
                _issue(
                    WorkflowValidationCode.SELF_LOOP,
                    "节点不能连接到自身",
                    node_id=edge.source if source_exists else None,
                    edge_id=edge.id,
                )
            )
        connection = (edge.source, edge.target)
        connection_counts[connection] += 1
        if connection_counts[connection] > 1:
            issues.append(
                _issue(
                    WorkflowValidationCode.DUPLICATE_CONNECTION,
                    "相同起点和终点之间不能重复连线",
                    edge_id=edge.id,
                )
            )
        if edge.target in start_ids:
            issues.append(
                _issue(
                    WorkflowValidationCode.START_HAS_INCOMING_EDGE,
                    "开始节点不能有入边",
                    node_id=edge.target,
                    edge_id=edge.id,
                )
            )
        if edge.source in end_ids:
            issues.append(
                _issue(
                    WorkflowValidationCode.END_HAS_OUTGOING_EDGE,
                    "结束节点不能有出边",
                    node_id=edge.source,
                    edge_id=edge.id,
                )
            )
        if source_exists and target_exists:
            valid_connections.add(connection)

    outgoing, incoming = _adjacency(known_node_ids, valid_connections)
    for node_id, targets in outgoing.items():
        if len(targets) > 1:
            issues.append(
                _issue(
                    WorkflowValidationCode.MULTIPLE_OUTGOING_EDGES,
                    "第一版不支持分支或并行且一个节点最多只能有一条出边",
                    node_id=node_id,
                )
            )

    for node in graph_nodes:
        if not outgoing[node.id] and not incoming[node.id]:
            issues.append(
                _issue(
                    WorkflowValidationCode.ISOLATED_NODE,
                    "节点不能孤立存在",
                    node_id=node.id,
                )
            )

    if not duplicate_node_ids:
        if len(start_nodes) == 1:
            reachable = _reachable_from((start_nodes[0].id,), outgoing)
            for node in graph_nodes:
                if node.id not in reachable:
                    issues.append(
                        _issue(
                            WorkflowValidationCode.UNREACHABLE_FROM_START,
                            "节点无法从开始节点到达",
                            node_id=node.id,
                        )
                    )
        if end_nodes:
            can_reach_end = _reachable_from((node.id for node in end_nodes), incoming)
            for node in graph_nodes:
                if node.id not in can_reach_end:
                    issues.append(
                        _issue(
                            WorkflowValidationCode.CANNOT_REACH_END,
                            "节点无法到达任一结束节点",
                            node_id=node.id,
                        )
                    )
        if _has_cycle(known_node_ids, outgoing, incoming):
            issues.append(_issue(WorkflowValidationCode.CYCLE_DETECTED, "第一版不支持环路"))

    return tuple(issues)


def ensure_workflow_graph_valid(
    nodes: Iterable[WorkflowNode],
    edges: Iterable[WorkflowEdge],
) -> None:
    issues = validate_workflow_graph(nodes, edges)
    if issues:
        raise WorkflowGraphInvalid(issues)


def _adjacency(
    node_ids: set[str],
    connections: set[tuple[str, str]],
) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    outgoing: dict[str, set[str]] = {node_id: set() for node_id in node_ids}
    incoming: dict[str, set[str]] = {node_id: set() for node_id in node_ids}
    for source, target in connections:
        outgoing[source].add(target)
        incoming[target].add(source)
    return outgoing, incoming


def _reachable_from(
    starting_ids: Iterable[str],
    adjacency: dict[str, set[str]],
) -> set[str]:
    pending = deque(starting_ids)
    visited: set[str] = set()
    while pending:
        node_id = pending.popleft()
        if node_id in visited:
            continue
        visited.add(node_id)
        pending.extend(adjacency[node_id] - visited)
    return visited


def _has_cycle(
    node_ids: set[str],
    outgoing: dict[str, set[str]],
    incoming: dict[str, set[str]],
) -> bool:
    remaining_incoming = {node_id: len(incoming[node_id]) for node_id in node_ids}
    pending = deque(node_id for node_id, count in remaining_incoming.items() if count == 0)
    visited_count = 0
    while pending:
        node_id = pending.popleft()
        visited_count += 1
        for target in outgoing[node_id]:
            remaining_incoming[target] -= 1
            if remaining_incoming[target] == 0:
                pending.append(target)
    return visited_count != len(node_ids)


def _issue(
    code: WorkflowValidationCode,
    message: str,
    *,
    node_id: str | None = None,
    edge_id: str | None = None,
) -> WorkflowValidationIssue:
    return WorkflowValidationIssue(
        code=code,
        message=message,
        node_id=node_id,
        edge_id=edge_id,
    )
