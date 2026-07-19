import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { PropsWithChildren } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { WorkflowsPage } from "./WorkflowsPage";

const workflowApi = vi.hoisted(() => ({
  createWorkflow: vi.fn(),
  fetchWorkflows: vi.fn(),
  updateWorkflow: vi.fn(),
  validateWorkflow: vi.fn(),
}));
const knowledgeApi = vi.hoisted(() => ({
  fetchKnowledgeBases: vi.fn(),
}));

vi.mock("../../api/workflows", () => workflowApi);
vi.mock("../../api/knowledge", () => knowledgeApi);

const workflow = {
  id: "9a2f8cb8-7f5f-41f8-b101-9ed76f40d9c6",
  name: "知识问答流程",
  description: "检索后回答",
  nodes: [
    { id: "start", type: "start", position: { x: 0, y: 80 }, config: {} },
    {
      id: "chat",
      type: "ai_chat",
      position: { x: 240, y: 80 },
      config: { prompt: "依据上下文回答" },
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

function TestProviders({ children }: PropsWithChildren) {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

function renderPage() {
  return render(<WorkflowsPage />, { wrapper: TestProviders });
}

describe("WorkflowsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    workflowApi.fetchWorkflows.mockResolvedValue([workflow]);
    workflowApi.validateWorkflow.mockResolvedValue({ valid: true, issues: [] });
    workflowApi.updateWorkflow.mockResolvedValue(workflow);
    workflowApi.createWorkflow.mockResolvedValue(workflow);
    knowledgeApi.fetchKnowledgeBases.mockResolvedValue([
      {
        id: "kb-1",
        name: "通用产品手册",
        description: "公共资料",
        document_count: 1,
        parsing_count: 0,
      },
    ]);
  });

  it("loads the persisted graph into the workflow list, canvas, and inspector", async () => {
    renderPage();

    expect(await screen.findByRole("heading", { name: "工作流" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "选择工作流 知识问答流程" })).toBeEnabled();
    expect(screen.getByRole("region", { name: "工作流画布" })).toBeInTheDocument();
    expect(screen.getByText("开始", { selector: ".workflow-node-title" })).toBeInTheDocument();
    expect(screen.getByText("AI 对话", { selector: ".workflow-node-title" })).toBeInTheDocument();
    expect(screen.getByText("结束", { selector: ".workflow-node-title" })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "工作流名称" })).toHaveValue("知识问答流程");
  });

  it("edits node configuration and validates before updating", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: "选择节点 AI 对话 chat" }));
    const prompt = screen.getByRole("textbox", { name: "节点提示词" });
    await user.clear(prompt);
    await user.type(prompt, "根据可靠上下文简洁回答");
    await user.click(screen.getByRole("button", { name: "保存工作流" }));

    await waitFor(() => expect(workflowApi.validateWorkflow).toHaveBeenCalledTimes(1));
    const configuration = workflowApi.validateWorkflow.mock.calls[0]?.[0];
    expect(configuration.nodes[1].config).toEqual({ prompt: "根据可靠上下文简洁回答" });
    await waitFor(() =>
      expect(workflowApi.updateWorkflow).toHaveBeenCalledWith(workflow.id, configuration),
    );
  });

  it("shows exact server validation issues and never saves an invalid graph", async () => {
    workflowApi.validateWorkflow.mockResolvedValue({
      valid: false,
      issues: [
        {
          code: "missing_end",
          message: "工作流至少需要一个结束节点",
          node_id: null,
          edge_id: null,
        },
      ],
    });
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: "保存工作流" }));

    expect(await screen.findByText("工作流至少需要一个结束节点")).toBeInTheDocument();
    expect(workflowApi.updateWorkflow).not.toHaveBeenCalled();
    expect(workflowApi.createWorkflow).not.toHaveBeenCalled();
  });

  it("creates a keyboard-operable draft and adds every supported node type", async () => {
    workflowApi.fetchWorkflows.mockResolvedValue([]);
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: "新建工作流" }));
    const name = screen.getByRole("textbox", { name: "工作流名称" });
    await user.clear(name);
    await user.type(name, "键盘创建流程");
    await user.click(screen.getByRole("button", { name: "添加开始节点" }));
    await user.click(screen.getByRole("button", { name: "添加AI 对话节点" }));
    await user.click(screen.getByRole("button", { name: "添加知识检索节点" }));
    await user.click(screen.getByRole("button", { name: "添加结束节点" }));

    expect(screen.getByRole("button", { name: "选择节点 开始 start-1" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "选择节点 AI 对话 ai_chat-1" })).toBeEnabled();
    expect(
      screen.getByRole("button", { name: "选择节点 知识检索 knowledge_retrieval-1" }),
    ).toBeEnabled();
    expect(screen.getByRole("button", { name: "选择节点 结束 end-1" })).toBeEnabled();
  });

  it("shows a safe list failure and retries the formal query", async () => {
    workflowApi.fetchWorkflows
      .mockRejectedValueOnce(new Error("无法连接后端服务"))
      .mockResolvedValueOnce([workflow]);
    const user = userEvent.setup();
    renderPage();

    expect(await screen.findByText("工作流加载失败")).toBeInTheDocument();
    expect(screen.getByText("无法连接后端服务")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "重试加载工作流" }));

    expect(await screen.findByRole("button", { name: "选择工作流 知识问答流程" })).toBeEnabled();
    expect(workflowApi.fetchWorkflows).toHaveBeenCalledTimes(2);
  });
});
