import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiClientError } from "../../api/errors";
import { WorkflowsPage } from "./WorkflowsPage";

const workflowApi = vi.hoisted(() => ({
  createWorkflow: vi.fn(),
  deleteWorkflow: vi.fn(),
  fetchWorkflows: vi.fn(),
  updateWorkflow: vi.fn(),
  validateWorkflow: vi.fn(),
}));
const knowledgeApi = vi.hoisted(() => ({
  fetchKnowledgeBases: vi.fn(),
}));
const workflowRunApi = vi.hoisted(() => ({
  fetchWorkflowRun: vi.fn(),
  startWorkflowRun: vi.fn(),
  stopWorkflowRun: vi.fn(),
  subscribeToWorkflowRunEvents: vi.fn(),
  streamOptions: undefined as
    | {
        onEvent: (event: unknown) => void;
        onError: (error: Error) => void;
      }
    | undefined,
  streamClose: vi.fn(),
}));

vi.mock("../../api/workflows", () => workflowApi);
vi.mock("../../api/knowledge", () => knowledgeApi);
vi.mock("../../api/workflowRuns", () => workflowRunApi);

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

const runningRun = {
  id: "a69b7bd1-7d4e-44f2-8c70-9ecfc38dad08",
  workflow_id: workflow.id,
  trigger: "manual" as const,
  status: "running" as const,
  input: "执行知识问答流程",
  output: "",
  current_node_id: "chat",
  completed_node_ids: ["start"],
  failed_node_id: null,
  error_code: null,
  created_at: "2026-07-20T06:00:00Z",
  started_at: "2026-07-20T06:00:00Z",
  finished_at: null,
  updated_at: "2026-07-20T06:00:01Z",
};

const completedRun = {
  ...runningRun,
  status: "completed" as const,
  output: "工作流最终回答",
  current_node_id: null,
  completed_node_ids: ["start", "chat", "end"],
  finished_at: "2026-07-20T06:00:03Z",
  updated_at: "2026-07-20T06:00:03Z",
};

function renderPage(initialEntry = "/workflows") {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path="/workflows" element={<WorkflowsPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("WorkflowsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    workflowRunApi.streamOptions = undefined;
    workflowRunApi.streamClose = vi.fn();
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
    workflowRunApi.fetchWorkflowRun.mockResolvedValue(completedRun);
    workflowRunApi.startWorkflowRun.mockResolvedValue(runningRun);
    workflowRunApi.stopWorkflowRun.mockResolvedValue({ run_id: runningRun.id });
    workflowRunApi.subscribeToWorkflowRunEvents.mockImplementation(
      (_runId: string, options: typeof workflowRunApi.streamOptions) => {
        workflowRunApi.streamOptions = options;
        return { close: workflowRunApi.streamClose };
      },
    );
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

  it("starts a saved workflow, highlights event snapshots, stops, and shows final output", async () => {
    const user = userEvent.setup();
    const { container } = renderPage();

    await screen.findByRole("button", { name: "选择工作流 知识问答流程" });
    await user.type(screen.getByRole("textbox", { name: "工作流运行输入" }), runningRun.input);
    await user.click(screen.getByRole("button", { name: "运行工作流" }));

    await waitFor(() =>
      expect(workflowRunApi.startWorkflowRun).toHaveBeenCalledWith(workflow.id, {
        run_id: expect.any(String),
        input: runningRun.input,
      }),
    );
    await waitFor(() =>
      expect(workflowRunApi.subscribeToWorkflowRunEvents).toHaveBeenCalledWith(
        runningRun.id,
        expect.objectContaining({ afterSequence: 0 }),
      ),
    );
    expect(container.querySelector('.react-flow__node[data-id="chat"]')).toHaveClass(
      "is-run-active",
    );
    expect(screen.getByRole("textbox", { name: "工作流名称" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "保存工作流" })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "停止工作流" }));
    expect(workflowRunApi.stopWorkflowRun).toHaveBeenCalledWith(runningRun.id);

    act(() => {
      workflowRunApi.streamOptions?.onEvent({
        schema_version: "1",
        sequence: 5,
        run_id: runningRun.id,
        workflow_id: workflow.id,
        type: "workflow.run.completed",
        node_id: null,
        run: completedRun,
        occurred_at: completedRun.updated_at,
      });
    });

    expect(await screen.findByText("运行完成")).toBeInTheDocument();
    expect(screen.getByText(completedRun.output)).toBeInTheDocument();
    expect(container.querySelector('.react-flow__node[data-id="chat"]')).toHaveClass(
      "is-run-completed",
    );
    expect(workflowRunApi.streamClose).toHaveBeenCalled();

    act(() => {
      workflowRunApi.streamOptions?.onEvent({
        schema_version: "1",
        sequence: 4,
        run_id: runningRun.id,
        workflow_id: workflow.id,
        type: "workflow.node.started",
        node_id: "chat",
        run: runningRun,
        occurred_at: "2026-07-20T06:00:04Z",
      });
    });
    expect(screen.getByText(completedRun.output)).toBeInTheDocument();
    expect(container.querySelector('.react-flow__node[data-id="chat"]')).toHaveClass(
      "is-run-completed",
    );
  });

  it("shows a failed node and stable error code from a terminal event", async () => {
    const user = userEvent.setup();
    const { container } = renderPage();
    const failedRun = {
      ...runningRun,
      status: "failed" as const,
      current_node_id: "chat",
      failed_node_id: "chat",
      error_code: "model_service_unavailable",
      finished_at: "2026-07-20T06:00:02Z",
      updated_at: "2026-07-20T06:00:02Z",
    };

    await screen.findByRole("button", { name: "选择工作流 知识问答流程" });
    await user.type(screen.getByRole("textbox", { name: "工作流运行输入" }), runningRun.input);
    await user.click(screen.getByRole("button", { name: "运行工作流" }));
    await waitFor(() => expect(workflowRunApi.streamOptions).toBeDefined());
    act(() => {
      workflowRunApi.streamOptions?.onEvent({
        schema_version: "1",
        sequence: 4,
        run_id: runningRun.id,
        workflow_id: workflow.id,
        type: "workflow.node.failed",
        node_id: "chat",
        run: failedRun,
        occurred_at: failedRun.updated_at,
      });
    });

    expect(await screen.findAllByText("运行失败")).toHaveLength(2);
    expect(screen.getByText("model_service_unavailable")).toBeInTheDocument();
    expect(container.querySelector('.react-flow__node[data-id="chat"]')).toHaveClass(
      "is-run-failed",
    );
  });

  it("recovers the authoritative summary after an SSE connection error", async () => {
    const user = userEvent.setup();
    renderPage();

    await screen.findByRole("button", { name: "选择工作流 知识问答流程" });
    await user.type(screen.getByRole("textbox", { name: "工作流运行输入" }), runningRun.input);
    await user.click(screen.getByRole("button", { name: "运行工作流" }));
    await waitFor(() => expect(workflowRunApi.streamOptions).toBeDefined());
    act(() => workflowRunApi.streamOptions?.onError(new Error("断流")));

    await waitFor(() => expect(workflowRunApi.fetchWorkflowRun).toHaveBeenCalledWith(runningRun.id));
    expect(await screen.findByText("事件连接已中断，已同步权威运行摘要")).toBeInTheDocument();
    expect(screen.getByText(completedRun.output)).toBeInTheDocument();
  });

  it("restores a persisted run summary from the formal URL after refresh", async () => {
    renderPage(`/workflows?run_id=${completedRun.id}`);

    await waitFor(() => expect(workflowRunApi.fetchWorkflowRun).toHaveBeenCalledWith(completedRun.id));
    expect(await screen.findByText("运行完成")).toBeInTheDocument();
    expect(screen.getByText(completedRun.output)).toBeInTheDocument();
    expect(workflowRunApi.subscribeToWorkflowRunEvents).not.toHaveBeenCalled();
  });

  it("keeps a user workflow selection after restoring a terminal run", async () => {
    const otherWorkflow = {
      ...workflow,
      id: "77e15fa0-7e51-47c1-9458-547c9f53a4ae",
      name: "第二个工作流",
    };
    workflowApi.fetchWorkflows.mockResolvedValue([workflow, otherWorkflow]);
    const user = userEvent.setup();
    renderPage(`/workflows?run_id=${completedRun.id}`);

    expect(await screen.findByText(completedRun.output)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "选择工作流 第二个工作流" }));

    expect(screen.getByRole("textbox", { name: "工作流名称" })).toHaveValue("第二个工作流");
    expect(screen.queryByText(completedRun.output)).not.toBeInTheDocument();
  });

  it("does not run an unsaved workflow draft", async () => {
    workflowApi.fetchWorkflows.mockResolvedValue([]);
    renderPage();

    expect(await screen.findByText("请先保存工作流，再从正式定义启动运行。")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "运行工作流" })).toBeDisabled();
    expect(workflowRunApi.startWorkflowRun).not.toHaveBeenCalled();
  });

  it("keeps the workflow and explains active-run deletion blocking", async () => {
    workflowApi.deleteWorkflow.mockRejectedValue(
      new ApiClientError(
        "工作流仍有运行中的执行。请等待完成或停止后重试",
        "workflow_has_active_runs",
        "request-2",
        true,
      ),
    );
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: `删除工作流 ${workflow.name}` }));
    await user.click(screen.getByRole("button", { name: `确认删除工作流 ${workflow.name}` }));

    expect(
      await screen.findByText("该工作流仍有活跃运行，请等待运行完成或停止后再重试。"),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: `选择工作流 ${workflow.name}` })).toBeEnabled();
  });

  it("clears the selected workflow only after deletion succeeds", async () => {
    workflowApi.fetchWorkflows.mockResolvedValueOnce([workflow]).mockResolvedValue([]);
    workflowApi.deleteWorkflow.mockResolvedValue(undefined);
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: `删除工作流 ${workflow.name}` }));
    await user.click(screen.getByRole("button", { name: `确认删除工作流 ${workflow.name}` }));

    await waitFor(() => expect(workflowApi.deleteWorkflow).toHaveBeenCalledWith(workflow.id));
    expect(await screen.findByText(`工作流“${workflow.name}”已删除`)).toBeInTheDocument();
    expect(await screen.findByText("还没有已保存工作流")).toBeInTheDocument();
  });
});
