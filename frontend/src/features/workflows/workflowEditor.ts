import {
  addEdge,
  applyEdgeChanges,
  applyNodeChanges,
  type Edge,
  type EdgeChange,
  type Node,
  type NodeChange,
  type XYPosition,
} from "@xyflow/react";

import type {
  Workflow,
  WorkflowConfigurationInput,
  WorkflowNodeInput,
  WorkflowNodeType,
  WorkflowValidationIssue,
} from "../../api/workflows";

export const WORKFLOW_NODE_LABELS: Record<WorkflowNodeType, string> = {
  start: "开始",
  ai_chat: "AI 对话",
  knowledge_retrieval: "知识检索",
  end: "结束",
};

export type WorkflowAiTarget = Extract<
  WorkflowNodeInput,
  { type: "ai_chat" }
>["config"]["target"];

type WorkflowEditorNodeData =
  | { nodeType: "start"; label: string; config: Record<string, never> }
  | {
      nodeType: "ai_chat";
      label: string;
      config: { prompt: string; target: WorkflowAiTarget | null };
    }
  | {
      nodeType: "knowledge_retrieval";
      label: string;
      config: { knowledge_base_id: string };
    }
  | { nodeType: "end"; label: string; config: Record<string, never> };

export type WorkflowEditorNode = Node<WorkflowEditorNodeData, "workflowNode">;
type WorkflowEditorNodeConfig = WorkflowEditorNodeData["config"];
export type WorkflowEditorEdge = Edge;

export interface WorkflowEditorState {
  workflowId: string | null;
  name: string;
  description: string;
  nodes: WorkflowEditorNode[];
  edges: WorkflowEditorEdge[];
  selectedNodeId: string | null;
  dirty: boolean;
  validationIssues: WorkflowValidationIssue[];
  invalidNodeIds: Set<string>;
  invalidEdgeIds: Set<string>;
}

export type WorkflowEditorAction =
  | { type: "new_workflow" }
  | { type: "workflow_loaded"; workflow: Workflow }
  | { type: "metadata_changed"; name: string; description: string }
  | { type: "node_added"; nodeType: WorkflowNodeType; position: XYPosition }
  | { type: "node_selected"; nodeId: string | null }
  | {
      type: "node_config_changed";
      nodeId: string;
      config: WorkflowEditorNodeConfig;
    }
  | { type: "nodes_connected"; source: string; target: string }
  | { type: "nodes_changed"; changes: NodeChange<WorkflowEditorNode>[] }
  | { type: "edges_changed"; changes: EdgeChange<WorkflowEditorEdge>[] }
  | { type: "validation_received"; issues: WorkflowValidationIssue[] }
  | { type: "saved"; workflow: Workflow };

export function createNewWorkflowEditorState(): WorkflowEditorState {
  return {
    workflowId: null,
    name: "未命名工作流",
    description: "",
    nodes: [],
    edges: [],
    selectedNodeId: null,
    dirty: false,
    validationIssues: [],
    invalidNodeIds: new Set(),
    invalidEdgeIds: new Set(),
  };
}

export function workflowToEditorState(workflow: Workflow): WorkflowEditorState {
  return {
    workflowId: workflow.id,
    name: workflow.name,
    description: workflow.description,
    nodes: workflow.nodes.map(nodeToEditorNode),
    edges: workflow.edges.map((edge) => ({ ...edge })),
    selectedNodeId: null,
    dirty: false,
    validationIssues: [],
    invalidNodeIds: new Set(),
    invalidEdgeIds: new Set(),
  };
}

export function editorStateToConfiguration(
  state: WorkflowEditorState,
): WorkflowConfigurationInput {
  return {
    name: state.name,
    description: state.description,
    nodes: state.nodes.map(editorNodeToNode),
    edges: state.edges.map(({ id, source, target }) => ({ id, source, target })),
  };
}

export function workflowEditorReducer(
  state: WorkflowEditorState,
  action: WorkflowEditorAction,
): WorkflowEditorState {
  switch (action.type) {
    case "new_workflow":
      return createNewWorkflowEditorState();
    case "workflow_loaded":
    case "saved":
      return workflowToEditorState(action.workflow);
    case "metadata_changed":
      return changed(state, { name: action.name, description: action.description });
    case "node_added": {
      const id = nextNodeId(action.nodeType, state.nodes);
      const node = createEditorNode(id, action.nodeType, action.position);
      return changed(state, {
        nodes: [...state.nodes, node],
        selectedNodeId: id,
      });
    }
    case "node_selected":
      return { ...state, selectedNodeId: action.nodeId };
    case "node_config_changed":
      return changed(state, {
        nodes: state.nodes.map((node) =>
          node.id === action.nodeId
            ? ({ ...node, data: { ...node.data, config: action.config } } as WorkflowEditorNode)
            : node,
        ),
        selectedNodeId: action.nodeId,
      });
    case "nodes_connected": {
      if (
        action.source === action.target ||
        !state.nodes.some((node) => node.id === action.source) ||
        !state.nodes.some((node) => node.id === action.target)
      ) {
        return state;
      }
      const edge: WorkflowEditorEdge = {
        id: `edge-${action.source}-${action.target}`,
        source: action.source,
        target: action.target,
      };
      const edges = addEdge(edge, state.edges);
      return edges === state.edges || edges.length === state.edges.length
        ? state
        : changed(state, { edges });
    }
    case "nodes_changed": {
      const removedIds = new Set(
        action.changes
          .filter((change) => change.type === "remove")
          .map((change) => change.id),
      );
      const nodes = applyNodeChanges(action.changes, state.nodes);
      const edges = removedIds.size
        ? state.edges.filter(
            (edge) => !removedIds.has(edge.source) && !removedIds.has(edge.target),
          )
        : state.edges;
      const graphChanged = action.changes.some((change) =>
        ["add", "remove", "replace", "position"].includes(change.type),
      );
      return graphChanged
        ? changed(state, {
            nodes,
            edges,
            selectedNodeId:
              state.selectedNodeId && removedIds.has(state.selectedNodeId)
                ? null
                : state.selectedNodeId,
          })
        : { ...state, nodes };
    }
    case "edges_changed": {
      const edges = applyEdgeChanges(action.changes, state.edges);
      const graphChanged = action.changes.some((change) =>
        ["add", "remove", "replace"].includes(change.type),
      );
      return graphChanged ? changed(state, { edges }) : { ...state, edges };
    }
    case "validation_received":
      return {
        ...state,
        validationIssues: action.issues,
        invalidNodeIds: new Set(
          action.issues.flatMap((issue) => (issue.node_id ? [issue.node_id] : [])),
        ),
        invalidEdgeIds: new Set(
          action.issues.flatMap((issue) => (issue.edge_id ? [issue.edge_id] : [])),
        ),
      };
  }
}

function changed(
  state: WorkflowEditorState,
  update: Partial<WorkflowEditorState>,
): WorkflowEditorState {
  return {
    ...state,
    ...update,
    dirty: true,
    validationIssues: [],
    invalidNodeIds: new Set(),
    invalidEdgeIds: new Set(),
  };
}

function nextNodeId(nodeType: WorkflowNodeType, nodes: WorkflowEditorNode[]): string {
  const prefix = `${nodeType}-`;
  const usedNumbers = nodes.flatMap((node) => {
    if (!node.id.startsWith(prefix)) return [];
    const value = Number(node.id.slice(prefix.length));
    return Number.isInteger(value) && value > 0 ? [value] : [];
  });
  return `${nodeType}-${Math.max(0, ...usedNumbers) + 1}`;
}

function createEditorNode(
  id: string,
  nodeType: WorkflowNodeType,
  position: XYPosition,
): WorkflowEditorNode {
  const label = WORKFLOW_NODE_LABELS[nodeType];
  switch (nodeType) {
    case "start":
    case "end":
      return { id, type: "workflowNode", position, data: { nodeType, label, config: {} } };
    case "ai_chat":
      return {
        id,
        type: "workflowNode",
        position,
        data: {
          nodeType,
          label,
          config: { prompt: "请根据工作流上下文回答用户输入。", target: null },
        },
      };
    case "knowledge_retrieval":
      return {
        id,
        type: "workflowNode",
        position,
        data: { nodeType, label, config: { knowledge_base_id: "" } },
      };
  }
}

function nodeToEditorNode(node: WorkflowNodeInput): WorkflowEditorNode {
  const label = WORKFLOW_NODE_LABELS[node.type];
  switch (node.type) {
    case "start":
    case "end":
      return {
        id: node.id,
        type: "workflowNode",
        position: { ...node.position },
        data: { nodeType: node.type, label, config: {} },
      };
    case "ai_chat":
      return {
        id: node.id,
        type: "workflowNode",
        position: { ...node.position },
        data: { nodeType: node.type, label, config: { ...node.config } },
      };
    case "knowledge_retrieval":
      return {
        id: node.id,
        type: "workflowNode",
        position: { ...node.position },
        data: { nodeType: node.type, label, config: { ...node.config } },
      };
  }
}

function editorNodeToNode(node: WorkflowEditorNode): WorkflowNodeInput {
  const base = { id: node.id, position: { ...node.position } };
  switch (node.data.nodeType) {
    case "start":
      return { ...base, type: "start", config: {} };
    case "ai_chat":
      if (node.data.config.target === null) {
        throw new Error(`AI 对话节点 ${node.id} 尚未选择执行目标`);
      }
      return {
        ...base,
        type: "ai_chat",
        config: { prompt: node.data.config.prompt, target: node.data.config.target },
      };
    case "knowledge_retrieval":
      return { ...base, type: "knowledge_retrieval", config: { ...node.data.config } };
    case "end":
      return { ...base, type: "end", config: {} };
  }
}
