import {
  Background,
  BackgroundVariant,
  Controls,
  MarkerType,
  MiniMap,
  ReactFlow,
  useReactFlow,
  type Connection,
  type NodeTypes,
} from "@xyflow/react";
import { useCallback, useMemo, type Dispatch, type DragEvent } from "react";

import type { WorkflowRun } from "../../api/workflowRuns";
import { WorkflowNodeCard } from "./WorkflowNodeCard";
import {
  type WorkflowEditorAction,
  type WorkflowEditorEdge,
  type WorkflowEditorState,
} from "./workflowEditor";
import { WORKFLOW_NODE_MIME } from "./workflowDnd";
import { isWorkflowRunActive } from "./useWorkflowRun";

const nodeTypes: NodeTypes = { workflowNode: WorkflowNodeCard };

export function WorkflowCanvas({
  state,
  run,
  editingLocked,
  dispatch,
}: {
  state: WorkflowEditorState;
  run?: WorkflowRun;
  editingLocked: boolean;
  dispatch: Dispatch<WorkflowEditorAction>;
}) {
  const flow = useReactFlow();
  const renderedNodes = useMemo(
    () =>
      state.nodes.map((node) => ({
        ...node,
        className: [
          node.className,
          state.invalidNodeIds.has(node.id) ? "is-invalid" : undefined,
          workflowNodeRunClass(run, node.id),
        ]
          .filter(Boolean)
          .join(" "),
      })),
    [run, state.invalidNodeIds, state.nodes],
  );
  const renderedEdges = useMemo(
    () =>
      state.edges.map((edge) => ({
        ...edge,
        className: state.invalidEdgeIds.has(edge.id) ? "is-invalid" : edge.className,
      })),
    [state.edges, state.invalidEdgeIds],
  );

  const onConnect = useCallback(
    (connection: Connection) => {
      if (editingLocked || !connection.source || !connection.target) return;
      dispatch({
        type: "nodes_connected",
        source: connection.source,
        target: connection.target,
      });
    },
    [dispatch, editingLocked],
  );

  const isValidConnection = useCallback(
    (connection: Connection | WorkflowEditorEdge) => {
      if (editingLocked) return false;
      if (!connection.source || !connection.target || connection.source === connection.target) {
        return false;
      }
      const source = state.nodes.find((node) => node.id === connection.source);
      const target = state.nodes.find((node) => node.id === connection.target);
      if (!source || !target || source.data.nodeType === "end" || target.data.nodeType === "start") {
        return false;
      }
      return (
        !state.edges.some((edge) => edge.source === connection.source) &&
        !state.edges.some(
          (edge) => edge.source === connection.source && edge.target === connection.target,
        )
      );
    },
    [editingLocked, state.edges, state.nodes],
  );

  const onDrop = useCallback(
    (event: DragEvent<HTMLDivElement>) => {
      event.preventDefault();
      if (editingLocked) return;
      const nodeType = event.dataTransfer.getData(WORKFLOW_NODE_MIME);
      if (!isWorkflowNodeType(nodeType)) return;
      dispatch({
        type: "node_added",
        nodeType,
        position: flow.screenToFlowPosition({ x: event.clientX, y: event.clientY }),
      });
    },
    [dispatch, editingLocked, flow],
  );

  return (
    <section
      className="workflow-canvas"
      role="region"
      aria-label="工作流画布"
      onDragOver={(event) => {
        event.preventDefault();
        event.dataTransfer.dropEffect = "move";
      }}
      onDrop={onDrop}
    >
      <ReactFlow
        nodes={renderedNodes}
        edges={renderedEdges}
        nodeTypes={nodeTypes}
        onNodesChange={(changes) => dispatch({ type: "nodes_changed", changes })}
        onEdgesChange={(changes) => dispatch({ type: "edges_changed", changes })}
        onConnect={onConnect}
        onNodeClick={(_, node) => dispatch({ type: "node_selected", nodeId: node.id })}
        onPaneClick={() => dispatch({ type: "node_selected", nodeId: null })}
        isValidConnection={isValidConnection}
        nodesDraggable={!editingLocked}
        nodesConnectable={!editingLocked}
        defaultEdgeOptions={{ markerEnd: { type: MarkerType.ArrowClosed }, type: "smoothstep" }}
        deleteKeyCode={editingLocked ? null : ["Backspace", "Delete"]}
        fitView
        fitViewOptions={{ maxZoom: 1 }}
        minZoom={0.35}
        maxZoom={1.8}
      >
        <Background variant={BackgroundVariant.Dots} gap={20} size={1.2} />
        <MiniMap pannable zoomable />
        <Controls showInteractive={false} />
      </ReactFlow>
    </section>
  );
}

function workflowNodeRunClass(
  run: WorkflowRun | undefined,
  nodeId: string,
): string | undefined {
  if (!run) return undefined;
  if (run.failed_node_id === nodeId) return "is-run-failed";
  if (run.current_node_id === nodeId && isWorkflowRunActive(run)) return "is-run-active";
  if (run.completed_node_ids.includes(nodeId)) return "is-run-completed";
  return undefined;
}

function isWorkflowNodeType(value: string): value is "start" | "ai_chat" | "knowledge_retrieval" | "end" {
  return ["start", "ai_chat", "knowledge_retrieval", "end"].includes(value);
}
