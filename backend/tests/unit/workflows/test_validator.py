from __future__ import annotations

from dataclasses import replace

import pytest

from common_agent.domain.workflow import (
    AiChatNodeConfig,
    EndNodeConfig,
    StartNodeConfig,
    WorkflowEdge,
    WorkflowNode,
    WorkflowNodePosition,
    WorkflowNodeType,
)
from common_agent.workflows.validator import (
    MAX_WORKFLOW_EDGES,
    MAX_WORKFLOW_NODES,
    WorkflowGraphInvalid,
    WorkflowValidationCode,
    ensure_workflow_graph_valid,
    validate_workflow_graph,
)


def _node(node_id: str, node_type: WorkflowNodeType) -> WorkflowNode:
    configs = {
        WorkflowNodeType.START: StartNodeConfig(),
        WorkflowNodeType.AI_CHAT: AiChatNodeConfig(prompt="回答输入"),
        WorkflowNodeType.END: EndNodeConfig(),
    }
    return WorkflowNode(
        id=node_id,
        type=node_type,
        position=WorkflowNodePosition(x=0, y=0),
        config=configs[node_type],
    )


def _valid_graph() -> tuple[tuple[WorkflowNode, ...], tuple[WorkflowEdge, ...]]:
    return (
        (
            _node("start", WorkflowNodeType.START),
            _node("chat", WorkflowNodeType.AI_CHAT),
            _node("end", WorkflowNodeType.END),
        ),
        (
            WorkflowEdge(id="edge-1", source="start", target="chat"),
            WorkflowEdge(id="edge-2", source="chat", target="end"),
        ),
    )


def _codes(
    nodes: tuple[WorkflowNode, ...], edges: tuple[WorkflowEdge, ...]
) -> set[WorkflowValidationCode]:
    return {issue.code for issue in validate_workflow_graph(nodes, edges)}


def test_valid_linear_graph_has_no_issues() -> None:
    nodes, edges = _valid_graph()

    assert validate_workflow_graph(nodes, edges) == ()
    ensure_workflow_graph_valid(nodes, edges)


def test_validator_rejects_missing_or_multiple_boundary_nodes() -> None:
    nodes, edges = _valid_graph()

    missing_start = tuple(node for node in nodes if node.type is not WorkflowNodeType.START)
    missing_end = tuple(node for node in nodes if node.type is not WorkflowNodeType.END)
    multiple_start = (*nodes, replace(nodes[0], id="start-2"))

    assert WorkflowValidationCode.MISSING_START in _codes(missing_start, edges[1:])
    assert WorkflowValidationCode.MISSING_END in _codes(missing_end, edges[:1])
    assert WorkflowValidationCode.MULTIPLE_STARTS in _codes(multiple_start, edges)


def test_validator_rejects_duplicate_node_and_edge_ids() -> None:
    nodes, edges = _valid_graph()
    duplicate_nodes = (*nodes, replace(nodes[1]))
    duplicate_edges = (*edges, WorkflowEdge(id="edge-1", source="start", target="end"))

    assert WorkflowValidationCode.DUPLICATE_NODE_ID in _codes(duplicate_nodes, edges)
    assert WorkflowValidationCode.DUPLICATE_EDGE_ID in _codes(nodes, duplicate_edges)


def test_validator_enforces_node_and_edge_limits() -> None:
    nodes, _ = _valid_graph()
    too_many_nodes = tuple(
        replace(nodes[1], id=f"chat-{index}") for index in range(MAX_WORKFLOW_NODES + 1)
    )
    too_many_edges = tuple(
        WorkflowEdge(id=f"edge-{index}", source="start", target="end")
        for index in range(MAX_WORKFLOW_EDGES + 1)
    )

    assert len(too_many_nodes) == MAX_WORKFLOW_NODES + 1
    assert len(too_many_edges) == MAX_WORKFLOW_EDGES + 1
    assert WorkflowValidationCode.NODE_LIMIT_EXCEEDED in _codes(too_many_nodes, ())
    assert WorkflowValidationCode.EDGE_LIMIT_EXCEEDED in _codes(nodes, too_many_edges)


def test_validator_rejects_missing_endpoints_self_loops_and_duplicate_connections() -> None:
    nodes, edges = _valid_graph()
    invalid_edges = (
        *edges,
        WorkflowEdge(id="missing-source", source="unknown", target="end"),
        WorkflowEdge(id="missing-target", source="start", target="unknown"),
        WorkflowEdge(id="self", source="chat", target="chat"),
        WorkflowEdge(id="duplicate", source="start", target="chat"),
    )

    codes = _codes(nodes, invalid_edges)

    assert WorkflowValidationCode.EDGE_SOURCE_MISSING in codes
    assert WorkflowValidationCode.EDGE_TARGET_MISSING in codes
    assert WorkflowValidationCode.SELF_LOOP in codes
    assert WorkflowValidationCode.DUPLICATE_CONNECTION in codes


def test_validator_rejects_incoming_start_and_outgoing_end_edges() -> None:
    nodes, edges = _valid_graph()
    invalid_edges = (
        *edges,
        WorkflowEdge(id="into-start", source="chat", target="start"),
        WorkflowEdge(id="out-of-end", source="end", target="chat"),
    )

    codes = _codes(nodes, invalid_edges)

    assert WorkflowValidationCode.START_HAS_INCOMING_EDGE in codes
    assert WorkflowValidationCode.END_HAS_OUTGOING_EDGE in codes


def test_validator_rejects_isolated_and_unreachable_nodes() -> None:
    nodes, edges = _valid_graph()
    isolated = _node("isolated", WorkflowNodeType.AI_CHAT)
    unreachable = _node("unreachable", WorkflowNodeType.AI_CHAT)
    graph_nodes = (*nodes, isolated, unreachable)
    graph_edges = (*edges, WorkflowEdge(id="dead-end", source="unreachable", target="end"))

    issues = validate_workflow_graph(graph_nodes, graph_edges)

    assert any(
        issue.code is WorkflowValidationCode.ISOLATED_NODE and issue.node_id == "isolated"
        for issue in issues
    )
    assert any(
        issue.code is WorkflowValidationCode.UNREACHABLE_FROM_START
        and issue.node_id == "unreachable"
        for issue in issues
    )
    assert any(
        issue.code is WorkflowValidationCode.CANNOT_REACH_END and issue.node_id == "isolated"
        for issue in issues
    )


def test_validator_rejects_cycles() -> None:
    nodes, _ = _valid_graph()
    cyclic_edges = (
        WorkflowEdge(id="edge-1", source="start", target="chat"),
        WorkflowEdge(id="edge-2", source="chat", target="end"),
        WorkflowEdge(id="edge-3", source="end", target="chat"),
    )

    assert WorkflowValidationCode.CYCLE_DETECTED in _codes(nodes, cyclic_edges)


def test_validator_rejects_multiple_outgoing_edges_as_unsupported_parallel_branch() -> None:
    nodes, edges = _valid_graph()
    second_chat = _node("chat-2", WorkflowNodeType.AI_CHAT)
    branched_edges = (
        *edges,
        WorkflowEdge(id="branch", source="start", target="chat-2"),
        WorkflowEdge(id="branch-end", source="chat-2", target="end"),
    )

    assert WorkflowValidationCode.MULTIPLE_OUTGOING_EDGES in _codes(
        (*nodes, second_chat), branched_edges
    )


def test_ensure_valid_raises_one_error_with_complete_issue_list() -> None:
    nodes, _ = _valid_graph()
    invalid_edges = (
        WorkflowEdge(id="self", source="chat", target="chat"),
        WorkflowEdge(id="missing", source="chat", target="unknown"),
    )

    with pytest.raises(WorkflowGraphInvalid) as captured:
        ensure_workflow_graph_valid(nodes, invalid_edges)

    codes = {issue.code for issue in captured.value.issues}
    assert WorkflowValidationCode.SELF_LOOP in codes
    assert WorkflowValidationCode.EDGE_TARGET_MISSING in codes
    assert WorkflowValidationCode.UNREACHABLE_FROM_START in codes
