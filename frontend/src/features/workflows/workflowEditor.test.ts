import { describe, expect, it } from "vitest";

import type { Workflow } from "../../api/workflows";
import {
  createNewWorkflowEditorState,
  editorStateToConfiguration,
  workflowEditorReducer,
  workflowToEditorState,
} from "./workflowEditor";

const workflow: Workflow = {
  id: "9a2f8cb8-7f5f-41f8-b101-9ed76f40d9c6",
  name: "已有流程",
  description: "原说明",
  nodes: [
    { id: "start", type: "start", position: { x: 0, y: 80 }, config: {} },
    {
      id: "chat",
      type: "ai_chat",
      position: { x: 240, y: 80 },
      config: { prompt: "原提示词" },
    },
    { id: "end", type: "end", position: { x: 480, y: 80 }, config: {} },
  ],
  edges: [
    { id: "edge-1", source: "start", target: "chat" },
    { id: "edge-2", source: "chat", target: "end" },
  ],
  created_at: "2026-07-20T04:00:00Z",
  updated_at: "2026-07-20T04:00:00Z",
};

describe("workflow editor reducer", () => {
  it("loads a persisted graph without mixing configuration into positions", () => {
    const state = workflowToEditorState(workflow);

    expect(state.workflowId).toBe(workflow.id);
    expect(state.dirty).toBe(false);
    expect(state.nodes.map((node) => [node.id, node.position, node.data.config])).toEqual([
      ["start", { x: 0, y: 80 }, {}],
      ["chat", { x: 240, y: 80 }, { prompt: "原提示词" }],
      ["end", { x: 480, y: 80 }, {}],
    ]);
    expect(editorStateToConfiguration(state)).toEqual({
      name: workflow.name,
      description: workflow.description,
      nodes: workflow.nodes,
      edges: workflow.edges,
    });
  });

  it("adds stable nodes, connects them, edits config, and marks the draft dirty", () => {
    let state = createNewWorkflowEditorState();
    state = workflowEditorReducer(state, {
      type: "metadata_changed",
      name: "新流程",
      description: "新说明",
    });
    state = workflowEditorReducer(state, {
      type: "node_added",
      nodeType: "start",
      position: { x: 10, y: 20 },
    });
    state = workflowEditorReducer(state, {
      type: "node_added",
      nodeType: "ai_chat",
      position: { x: 210, y: 20 },
    });
    state = workflowEditorReducer(state, {
      type: "node_added",
      nodeType: "end",
      position: { x: 410, y: 20 },
    });
    state = workflowEditorReducer(state, {
      type: "nodes_connected",
      source: "start-1",
      target: "ai_chat-1",
    });
    state = workflowEditorReducer(state, {
      type: "nodes_connected",
      source: "ai_chat-1",
      target: "end-1",
    });
    state = workflowEditorReducer(state, {
      type: "node_config_changed",
      nodeId: "ai_chat-1",
      config: { prompt: "根据输入直接回答" },
    });

    expect(state.selectedNodeId).toBe("ai_chat-1");
    expect(state.dirty).toBe(true);
    expect(editorStateToConfiguration(state)).toEqual({
      name: "新流程",
      description: "新说明",
      nodes: [
        { id: "start-1", type: "start", position: { x: 10, y: 20 }, config: {} },
        {
          id: "ai_chat-1",
          type: "ai_chat",
          position: { x: 210, y: 20 },
          config: { prompt: "根据输入直接回答" },
        },
        { id: "end-1", type: "end", position: { x: 410, y: 20 }, config: {} },
      ],
      edges: [
        { id: "edge-start-1-ai_chat-1", source: "start-1", target: "ai_chat-1" },
        { id: "edge-ai_chat-1-end-1", source: "ai_chat-1", target: "end-1" },
      ],
    });
  });

  it("removes incident edges and maps server issues to their exact graph items", () => {
    let state = workflowToEditorState(workflow);
    state = workflowEditorReducer(state, {
      type: "nodes_changed",
      changes: [{ id: "chat", type: "remove" }],
    });
    state = workflowEditorReducer(state, {
      type: "validation_received",
      issues: [
        {
          code: "unreachable_from_start",
          message: "节点无法从开始节点到达",
          node_id: "end",
          edge_id: null,
        },
        {
          code: "edge_target_missing",
          message: "边的终点不存在",
          node_id: null,
          edge_id: "edge-2",
        },
      ],
    });

    expect(state.nodes.map((node) => node.id)).toEqual(["start", "end"]);
    expect(state.edges).toEqual([]);
    expect(state.validationIssues).toHaveLength(2);
    expect(state.invalidNodeIds).toEqual(new Set(["end"]));
    expect(state.invalidEdgeIds).toEqual(new Set(["edge-2"]));
  });
});
