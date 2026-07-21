import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "./client";
import {
  createWorkflow,
  deleteWorkflow,
  fetchWorkflows,
  parseWorkflowResponse,
  parseWorkflowValidationResponse,
  updateWorkflow,
  validateWorkflow,
  type WorkflowConfigurationInput,
} from "./workflows";

vi.mock("./client", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}));

const configuration: WorkflowConfigurationInput = {
  name: "知识问答流程",
  description: "检索后回答",
  nodes: [
    { id: "start", type: "start", position: { x: 0, y: 80 }, config: {} },
    {
      id: "chat",
      type: "ai_chat",
      position: { x: 240, y: 80 },
      config: {
        prompt: "依据上下文回答",
        target: {
          type: "model",
          model_configuration_id: "67b23894-27bd-49dd-a023-d926905e7ea1",
        },
      },
    },
    { id: "end", type: "end", position: { x: 480, y: 80 }, config: {} },
  ],
  edges: [
    { id: "edge-1", source: "start", target: "chat" },
    { id: "edge-2", source: "chat", target: "end" },
  ],
};

const workflow = {
  id: "9a2f8cb8-7f5f-41f8-b101-9ed76f40d9c6",
  ...configuration,
  created_at: "2026-07-20T04:00:00Z",
  updated_at: "2026-07-20T04:00:00Z",
};

describe("workflow API boundary", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("accepts discriminated workflow snapshots and rejects schema drift", () => {
    expect(parseWorkflowResponse(workflow)).toEqual(workflow);
    expect(() =>
      parseWorkflowResponse({
        ...workflow,
        nodes: [{ ...workflow.nodes[0], type: "unknown" }],
      }),
    ).toThrow();
    expect(() => parseWorkflowResponse({ ...workflow, api_key: "secret" })).toThrow();
  });

  it("accepts only stable validation issue payloads", () => {
    const invalid = {
      valid: false,
      issues: [
        {
          code: "missing_end",
          message: "工作流至少需要一个结束节点",
          node_id: null,
          edge_id: null,
        },
      ],
    };

    expect(parseWorkflowValidationResponse(invalid)).toEqual(invalid);
    expect(() =>
      parseWorkflowValidationResponse({ ...invalid, issues: [{ ...invalid.issues[0], code: "x" }] }),
    ).toThrow();
  });

  it("uses only the platform workflow CRUD and validation endpoints", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      data: { items: [workflow], next_cursor: null },
    });
    vi.mocked(apiClient.post)
      .mockResolvedValueOnce({ data: { valid: true, issues: [] } })
      .mockResolvedValueOnce({ data: workflow });
    vi.mocked(apiClient.put).mockResolvedValue({ data: workflow });
    vi.mocked(apiClient.delete).mockResolvedValue({ data: undefined });

    await expect(fetchWorkflows()).resolves.toEqual({ items: [workflow], next_cursor: null });
    await expect(validateWorkflow(configuration)).resolves.toEqual({ valid: true, issues: [] });
    await expect(createWorkflow(configuration)).resolves.toEqual(workflow);
    await expect(updateWorkflow(workflow.id, configuration)).resolves.toEqual(workflow);
    await expect(deleteWorkflow(workflow.id)).resolves.toBeUndefined();

    expect(apiClient.get).toHaveBeenCalledWith("/workflows", { params: {} });
    expect(apiClient.post).toHaveBeenNthCalledWith(1, "/workflows/validate", configuration);
    expect(apiClient.post).toHaveBeenNthCalledWith(2, "/workflows", configuration);
    expect(apiClient.put).toHaveBeenCalledWith(`/workflows/${workflow.id}`, configuration);
    expect(apiClient.delete).toHaveBeenCalledWith(`/workflows/${workflow.id}`);
  });
});
