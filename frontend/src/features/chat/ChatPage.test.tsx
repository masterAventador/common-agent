import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { PropsWithChildren } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ChatPage } from "./ChatPage";

const employeeApi = vi.hoisted(() => ({
  fetchEmployee: vi.fn(),
  fetchEmployees: vi.fn(),
}));
const chatApi = vi.hoisted(() => ({
  createConversationTurn: vi.fn(),
  fetchConversation: vi.fn(),
  fetchConversationMessages: vi.fn(),
  retryConversationMessage: vi.fn(),
  sendConversationMessage: vi.fn(),
  stopConversationGeneration: vi.fn(),
  subscribeToConversationEvents: vi.fn(),
  streamOptions: undefined as
    | {
        onEvent: (event: unknown) => void;
        onError: (error: Error) => void;
      }
    | undefined,
}));
const modelConfigurationApi = vi.hoisted(() => ({
  fetchModelConfiguration: vi.fn(),
  fetchModelConfigurations: vi.fn(),
}));
const workflowRunApi = vi.hoisted(() => ({
  fetchConversationWorkflowRuns: vi.fn(),
}));
const workflowApi = vi.hoisted(() => ({
  fetchWorkflows: vi.fn(),
}));

vi.mock("../../api/employees", () => employeeApi);
vi.mock("../../api/conversations", () => chatApi);
vi.mock("../../api/modelConfigurations", () => modelConfigurationApi);
vi.mock("../../api/workflowRuns", () => workflowRunApi);
vi.mock("../../api/workflows", () => workflowApi);

const employee = {
  id: "6f3d43e0-6f6d-5a67-9f25-756a0b9ed2ab",
  name: "知识助理",
  description: "通用知识问答",
  system_prompt: "优先依据知识库回答。",
  default_model_configuration_id: "0d4f38a5-bfd1-496f-b99d-fd768a2f3c30",
  default_model_identifier: "qwen-turbo",
  knowledge_base_id: "kb-1",
  allowed_workflow_ids: [],
  created_at: "2026-07-20T02:00:00Z",
  updated_at: "2026-07-20T02:00:00Z",
};

const conversation = {
  id: "a0fcaad2-a53d-40c8-9f64-23298bfacf49",
  source: "employee" as const,
  employee_id: employee.id,
  model_configuration_id: null,
  title: "知识问答",
  created_at: "2026-07-20T02:00:00Z",
  updated_at: "2026-07-20T02:00:00Z",
};

const modelConfiguration = {
  id: "0d4f38a5-bfd1-496f-b99d-fd768a2f3c30",
  display_name: "通用千问 Turbo",
  provider: "bailian" as const,
  model_identifier: "qwen-turbo",
  enabled: true,
  created_at: "2026-07-20T02:00:00Z",
  updated_at: "2026-07-20T02:00:00Z",
};

const alternateModelConfiguration = {
  ...modelConfiguration,
  id: "f58e6070-57af-4515-82e7-9b29be0c738b",
  display_name: "通用千问 Max",
  model_identifier: "qwen-max",
};

const genericConversation = {
  ...conversation,
  id: "c9798edb-d7b5-42d1-b2de-0afd6a83a459",
  source: "generic" as const,
  employee_id: null,
  model_configuration_id: modelConfiguration.id,
  title: "请介绍一下你自己",
};

const userMessage = {
  id: "52a34887-e32a-4709-aa32-6835502a8bc8",
  conversation_id: conversation.id,
  sequence_number: 1,
  role: "user" as const,
  content: "验收标记是什么？",
  status: "completed" as const,
  citations: [],
  error_code: null,
  model_configuration_id: null,
  model_identifier: null,
  created_at: "2026-07-20T02:00:01Z",
  updated_at: "2026-07-20T02:00:01Z",
};

const assistantMessage = {
  ...userMessage,
  id: "baeed6a2-d8cb-49ac-8999-393cf2153161",
  sequence_number: 2,
  role: "assistant" as const,
  model_configuration_id: modelConfiguration.id,
  model_identifier: modelConfiguration.model_identifier,
  content: "验收标记是 COMMON_AGENT_CHAT_OK。",
  citations: [
    {
      position: 1,
      knowledge_base_id: "kb-1",
      chunk_id: "chunk-1",
      document_id: "doc-1",
      document_name: "通用手册.txt",
      content: "可靠片段包含 COMMON_AGENT_CHAT_OK。",
      score: 0.96,
    },
  ],
};

const workflow = {
  id: "3f6dce37-b74c-449f-8e82-e75725889f25",
  name: "会话摘要工作流",
  description: "由数字员工触发",
  nodes: [
    { id: "start", type: "start" as const, position: { x: 0, y: 0 }, config: {} },
    { id: "end", type: "end" as const, position: { x: 240, y: 0 }, config: {} },
  ],
  edges: [{ id: "edge", source: "start", target: "end" }],
  created_at: "2026-07-20T02:00:00Z",
  updated_at: "2026-07-20T02:00:00Z",
};

const employeeRun = {
  id: "6b283c3f-b901-4cc4-945c-0131f3045403",
  workflow_id: workflow.id,
  trigger: "employee" as const,
  status: "completed" as const,
  input: "执行对话工作流",
  output: "工作流已完成",
  current_node_id: null,
  completed_node_ids: ["start", "end"],
  failed_node_id: null,
  error_code: null,
  origin: {
    employee_id: employee.id,
    conversation_id: conversation.id,
    assistant_message_id: assistantMessage.id,
  },
  created_at: "2026-07-20T02:00:02Z",
  started_at: "2026-07-20T02:00:02Z",
  finished_at: "2026-07-20T02:00:03Z",
  updated_at: "2026-07-20T02:00:03Z",
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
  return render(
    <MemoryRouter
      initialEntries={[
        `/chat?employee_id=${employee.id}&conversation_id=${conversation.id}`,
      ]}
    >
      <Routes>
        <Route path="/chat" element={<ChatPage />} />
        <Route path="/workflows" element={<div>运行详情页</div>} />
      </Routes>
    </MemoryRouter>,
    { wrapper: TestProviders },
  );
}

function renderGenericPage() {
  return render(
    <MemoryRouter initialEntries={["/chat"]}>
      <Routes>
        <Route path="/chat" element={<ChatPage />} />
      </Routes>
    </MemoryRouter>,
    { wrapper: TestProviders },
  );
}

function renderGenericHistoryPage() {
  return render(
    <MemoryRouter initialEntries={[`/chat?conversation_id=${genericConversation.id}`]}>
      <Routes>
        <Route path="/chat" element={<ChatPage />} />
      </Routes>
    </MemoryRouter>,
    { wrapper: TestProviders },
  );
}

describe("ChatPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    chatApi.streamOptions = undefined;
    chatApi.fetchConversation.mockResolvedValue({
      ...conversation,
      employee_name: employee.name,
    });
    employeeApi.fetchEmployee.mockResolvedValue(employee);
    employeeApi.fetchEmployees.mockResolvedValue({ items: [employee], next_cursor: null });
    modelConfigurationApi.fetchModelConfigurations.mockResolvedValue({
      items: [modelConfiguration],
      next_cursor: null,
    });
    modelConfigurationApi.fetchModelConfiguration.mockResolvedValue(modelConfiguration);
    chatApi.fetchConversationMessages.mockResolvedValue([userMessage, assistantMessage]);
    workflowRunApi.fetchConversationWorkflowRuns.mockResolvedValue({ items: [], next_cursor: null });
    workflowApi.fetchWorkflows.mockResolvedValue({ items: [workflow], next_cursor: null });
    chatApi.subscribeToConversationEvents.mockImplementation(
      (_conversationId: string, options: typeof chatApi.streamOptions) => {
        chatApi.streamOptions = options;
        return { close: vi.fn() };
      },
    );
  });

  it("closes chat when model configurations fail and recovers through the formal retry", async () => {
    modelConfigurationApi.fetchModelConfigurations
      .mockRejectedValueOnce(new Error("模型目录暂不可用"))
      .mockResolvedValue({ items: [modelConfiguration], next_cursor: null });
    const user = userEvent.setup();

    renderGenericPage();

    expect(await screen.findByText("模型配置加载失败")).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "消息输入" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "重试加载" }));
    expect(await screen.findByRole("textbox", { name: "消息输入" })).toBeEnabled();
  });

  it("keeps a generic draft closed when the workspace has no enabled model", async () => {
    modelConfigurationApi.fetchModelConfigurations.mockResolvedValue({
      items: [{ ...modelConfiguration, enabled: false }],
      next_cursor: null,
    });

    renderGenericPage();

    expect(
      await screen.findByText("还没有已启用的模型，请先到模型管理中创建并启用模型"),
    ).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "消息输入" })).not.toBeInTheDocument();
  });

  it("opens a blank generic chat and atomically creates the first turn with the selected model", async () => {
    chatApi.fetchConversationMessages.mockResolvedValue([]);
    chatApi.createConversationTurn.mockResolvedValue({
      conversation: genericConversation,
      turn: {
        turn_id: "ecb5103d-b7ca-4484-84e1-ad35ff0d8cad",
        user_message: {
          ...userMessage,
          conversation_id: genericConversation.id,
          content: "请介绍一下你自己",
        },
        assistant_message: {
          ...assistantMessage,
          conversation_id: genericConversation.id,
          content: "",
          status: "pending",
          citations: [],
          model_configuration_id: modelConfiguration.id,
          model_identifier: modelConfiguration.model_identifier,
        },
        retry: false,
      },
    });
    chatApi.fetchConversation.mockResolvedValue({
      ...genericConversation,
      employee_name: null,
    });
    const user = userEvent.setup();

    renderGenericPage();

    expect(await screen.findByRole("heading", { name: "通用 AI" })).toBeInTheDocument();
    expect(screen.getByTitle(modelConfiguration.display_name)).toBeInTheDocument();
    const input = screen.getByRole("textbox", { name: "消息输入" });
    expect(input).toBeEnabled();
    await user.type(input, "请介绍一下你自己");
    await user.click(screen.getByRole("button", { name: "发送消息" }));

    await waitFor(() =>
      expect(chatApi.createConversationTurn).toHaveBeenCalledWith(
        expect.objectContaining({
          employee_id: null,
          model_configuration_id: modelConfiguration.id,
          content: "请介绍一下你自己",
        }),
      ),
    );
  });

  it("lets an employee conversation switch the current turn model without changing its default", async () => {
    modelConfigurationApi.fetchModelConfigurations.mockResolvedValue({
      items: [modelConfiguration, alternateModelConfiguration],
      next_cursor: null,
    });
    chatApi.fetchConversationMessages.mockResolvedValue([]);
    chatApi.sendConversationMessage.mockResolvedValue({
      turn_id: "4dccb75c-6844-49de-a5a8-781416fab7e5",
      user_message: { ...userMessage, content: "使用 Max 回答" },
      assistant_message: {
        ...assistantMessage,
        content: "",
        status: "pending",
        citations: [],
        model_configuration_id: alternateModelConfiguration.id,
        model_identifier: alternateModelConfiguration.model_identifier,
      },
      retry: false,
    });
    const user = userEvent.setup();
    renderPage();

    const modelSelect = await screen.findByRole("combobox", { name: "选择模型" });
    expect(screen.getByTitle(modelConfiguration.display_name)).toBeInTheDocument();
    await user.click(modelSelect);
    await user.click(await screen.findByText(alternateModelConfiguration.display_name));
    await user.type(screen.getByRole("textbox", { name: "消息输入" }), "使用 Max 回答");
    await user.click(screen.getByRole("button", { name: "发送消息" }));

    await waitFor(() =>
      expect(chatApi.sendConversationMessage).toHaveBeenCalledWith(
        conversation.id,
        expect.objectContaining({
          content: "使用 Max 回答",
          model_configuration_id: alternateModelConfiguration.id,
        }),
      ),
    );
    expect(employee.default_model_configuration_id).toBe(modelConfiguration.id);
  });

  it("refreshes a generic conversation detail after persisting a per-turn model selection", async () => {
    modelConfigurationApi.fetchModelConfigurations.mockResolvedValue({
      items: [modelConfiguration, alternateModelConfiguration],
      next_cursor: null,
    });
    chatApi.fetchConversation
      .mockResolvedValueOnce({ ...genericConversation, employee_name: null })
      .mockResolvedValue({
        ...genericConversation,
        employee_name: null,
        model_configuration_id: alternateModelConfiguration.id,
      });
    chatApi.fetchConversationMessages.mockResolvedValue([]);
    chatApi.sendConversationMessage.mockResolvedValue({
      turn_id: "4dccb75c-6844-49de-a5a8-781416fab7e5",
      user_message: { ...userMessage, content: "保存 Max" },
      assistant_message: {
        ...assistantMessage,
        content: "",
        status: "pending",
        citations: [],
        model_configuration_id: alternateModelConfiguration.id,
        model_identifier: alternateModelConfiguration.model_identifier,
      },
      retry: false,
    });
    const user = userEvent.setup();

    renderGenericHistoryPage();
    await screen.findByRole("textbox", { name: "消息输入" });
    await user.click(screen.getByRole("combobox", { name: "选择模型" }));
    await user.click(await screen.findByText(alternateModelConfiguration.display_name));
    await user.type(screen.getByRole("textbox", { name: "消息输入" }), "保存 Max");
    await user.click(screen.getByRole("button", { name: "发送消息" }));

    await waitFor(() => expect(chatApi.fetchConversation).toHaveBeenCalledTimes(2));
    expect(
      screen.getByRole("combobox", { name: "选择模型" }).closest(".chat-model-select"),
    ).toHaveTextContent(alternateModelConfiguration.display_name);
  });

  it("does not request employee workflow data for a restored generic conversation", async () => {
    chatApi.fetchConversation.mockResolvedValue({
      ...genericConversation,
      employee_name: null,
    });

    renderGenericHistoryPage();

    expect(await screen.findByRole("heading", { name: "通用 AI" })).toBeInTheDocument();
    await waitFor(() => expect(chatApi.fetchConversationMessages).toHaveBeenCalled());
    expect(workflowRunApi.fetchConversationWorkflowRuns).not.toHaveBeenCalled();
    expect(workflowApi.fetchWorkflows).not.toHaveBeenCalled();
  });

  it("loads the referenced employee directly and restores its current default model", async () => {
    const currentEmployee = {
      ...employee,
      default_model_configuration_id: alternateModelConfiguration.id,
      default_model_identifier: alternateModelConfiguration.model_identifier,
    };
    employeeApi.fetchEmployees.mockResolvedValue({ items: [], next_cursor: null });
    employeeApi.fetchEmployee.mockResolvedValue(currentEmployee);
    modelConfigurationApi.fetchModelConfiguration.mockResolvedValue(
      alternateModelConfiguration,
    );
    modelConfigurationApi.fetchModelConfigurations.mockResolvedValue({
      items: [modelConfiguration, alternateModelConfiguration],
      next_cursor: null,
    });

    renderPage();

    await waitFor(() => expect(employeeApi.fetchEmployee).toHaveBeenCalledWith(employee.id));
    expect(await screen.findByRole("heading", { name: currentEmployee.name })).toBeInTheDocument();
    expect(screen.getByTitle(alternateModelConfiguration.display_name)).toBeInTheDocument();
  });

  it("restores an employee default model that is beyond the first model page", async () => {
    const currentEmployee = {
      ...employee,
      default_model_configuration_id: alternateModelConfiguration.id,
      default_model_identifier: alternateModelConfiguration.model_identifier,
    };
    employeeApi.fetchEmployee.mockResolvedValue(currentEmployee);
    modelConfigurationApi.fetchModelConfigurations.mockResolvedValue({
      items: [modelConfiguration],
      next_cursor: "next-model-page",
    });
    modelConfigurationApi.fetchModelConfiguration.mockResolvedValue(
      alternateModelConfiguration,
    );

    renderPage();

    await waitFor(() =>
      expect(modelConfigurationApi.fetchModelConfiguration).toHaveBeenCalledWith(
        alternateModelConfiguration.id,
      ),
    );
    expect(await screen.findByTitle(alternateModelConfiguration.display_name)).toBeInTheDocument();
  });

  it("blocks sending instead of silently falling back when the context model cannot load", async () => {
    modelConfigurationApi.fetchModelConfiguration
      .mockRejectedValueOnce(new Error("默认模型暂不可用"))
      .mockResolvedValue(modelConfiguration);
    const user = userEvent.setup();

    renderPage();

    expect(await screen.findByText("当前会话模型加载失败")).toBeInTheDocument();
    expect(screen.getByText("默认模型暂不可用")).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "消息输入" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "重试加载" }));
    expect(await screen.findByRole("textbox", { name: "消息输入" })).toBeEnabled();
  });

  it("blocks a restored employee conversation when its linked employee is unavailable", async () => {
    employeeApi.fetchEmployee.mockRejectedValue(new Error("数字员工已删除"));
    const user = userEvent.setup();

    renderPage();

    expect(await screen.findByText("会话关联的数字员工不可用")).toBeInTheDocument();
    expect(screen.getByText("数字员工已删除")).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "消息输入" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "返回通用 AI" }));
    expect(await screen.findByRole("heading", { name: "通用 AI" })).toBeInTheDocument();
  });

  it("renders restored message history with citations and employee details", async () => {
    renderPage();

    expect(await screen.findByRole("heading", { name: "AI 会话" })).toBeInTheDocument();
    const messageRegion = screen.getByRole("region", { name: "消息区域" });
    const employeeRegion = screen.getByRole("region", { name: "数字员工信息" });
    expect(await within(messageRegion).findByText("验收标记是什么？")).toBeInTheDocument();
    expect(
      await within(messageRegion).findByText("验收标记是 COMMON_AGENT_CHAT_OK。"),
    ).toBeInTheDocument();
    expect(within(messageRegion).getByText("通用手册.txt")).toBeInTheDocument();
    expect(
      within(messageRegion).getByText("可靠片段包含 COMMON_AGENT_CHAT_OK。"),
    ).toBeInTheDocument();
    expect(within(employeeRegion).getByText("知识助理")).toBeInTheDocument();
    expect(within(employeeRegion).getByText("已绑定知识库")).toBeInTheDocument();
  });

  it("loads additional conversation workflow run pages", async () => {
    const secondRun = {
      ...employeeRun,
      id: "5262373b-10ea-4377-a75c-8242e90f3e63",
      input: "第二次执行",
      output: "第二次工作流已完成",
    };
    workflowRunApi.fetchConversationWorkflowRuns.mockImplementation(
      (_conversationId: string, { cursor }: { cursor?: string }) =>
        Promise.resolve(
          cursor === "run-next"
            ? { items: [secondRun], next_cursor: null }
            : { items: [employeeRun], next_cursor: "run-next" },
        ),
    );
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: "加载更多运行记录" }));
    await waitFor(() =>
      expect(workflowRunApi.fetchConversationWorkflowRuns).toHaveBeenCalledWith(conversation.id, {
        cursor: "run-next",
        limit: 50,
      }),
    );
  });

  it("restores an expandable employee workflow summary and opens the formal run detail route", async () => {
    workflowRunApi.fetchConversationWorkflowRuns.mockResolvedValue({
      items: [employeeRun],
      next_cursor: null,
    });
    const user = userEvent.setup();
    renderPage();

    expect(await screen.findByText("会话摘要工作流")).toBeInTheDocument();
    expect(workflowRunApi.fetchConversationWorkflowRuns).toHaveBeenCalledWith(conversation.id, {
      cursor: undefined,
      limit: 50,
    });
    await user.click(screen.getByText("会话摘要工作流"));
    expect(await screen.findByText("工作流已完成")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "查看运行详情" }));
    expect(await screen.findByText("运行详情页")).toBeInTheDocument();
  });

  it("starts an employee draft without persisting an empty conversation and creates it on send", async () => {
    chatApi.fetchConversationMessages.mockResolvedValue([]);
    chatApi.createConversationTurn.mockResolvedValue({
      conversation,
      turn: {
        turn_id: "e0ad1544-ed1d-4099-a6f1-d6378082d35e",
        user_message: userMessage,
        assistant_message: {
          ...assistantMessage,
          content: "",
          citations: [],
          status: "pending",
        },
        retry: false,
      },
    });
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: "新建会话" }));
    await user.type(screen.getByRole("textbox", { name: "消息输入" }), userMessage.content);
    await user.click(screen.getByRole("button", { name: "发送消息" }));
    await waitFor(() =>
      expect(chatApi.createConversationTurn).toHaveBeenCalledWith({
        conversation_id: expect.any(String),
        message_id: expect.any(String),
        employee_id: employee.id,
        model_configuration_id: modelConfiguration.id,
        content: userMessage.content,
      }),
    );
  });

  it("sends, stops, retries, applies monotonic SSE snapshots, and ignores late duplicates", async () => {
    chatApi.fetchConversationMessages.mockResolvedValue([]);
    const pendingAssistant = {
      ...assistantMessage,
      content: "",
      citations: [],
      status: "pending" as const,
    };
    const stoppedAssistant = {
      ...pendingAssistant,
      content: "部分回答",
      status: "stopped" as const,
    };
    chatApi.sendConversationMessage.mockResolvedValue({
      turn_id: "3a64b792-d4a9-4296-a7fd-79013bb42c2b",
      user_message: userMessage,
      assistant_message: pendingAssistant,
      retry: false,
    });
    chatApi.stopConversationGeneration.mockResolvedValue({
      turn_id: "3a64b792-d4a9-4296-a7fd-79013bb42c2b",
      assistant_message_id: assistantMessage.id,
    });
    chatApi.retryConversationMessage.mockResolvedValue({
      turn_id: "a8f4569b-2cff-46fa-b8ed-006068f60335",
      user_message: userMessage,
      assistant_message: pendingAssistant,
      retry: true,
    });
    const user = userEvent.setup();
    renderPage();

    const input = await screen.findByRole("textbox", { name: "消息输入" });
    await screen.findByRole("heading", { name: "知识问答" });
    await user.type(input, "保留换行");
    await user.keyboard("{Shift>}{Enter}{/Shift}");
    expect(chatApi.sendConversationMessage).not.toHaveBeenCalled();
    await user.clear(input);
    await user.type(input, userMessage.content);
    await user.keyboard("{Enter}");
    await waitFor(() =>
      expect(chatApi.sendConversationMessage).toHaveBeenCalledWith(
        conversation.id,
        expect.objectContaining({ content: userMessage.content, message_id: expect.any(String) }),
      ),
    );
    expect(await screen.findByText("正在思考…")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "停止生成" }));
    expect(chatApi.stopConversationGeneration).toHaveBeenCalledWith(conversation.id);

    act(() => {
      chatApi.streamOptions?.onEvent({
        schema_version: "2",
        sequence: 3,
        conversation_id: conversation.id,
        turn_id: "3a64b792-d4a9-4296-a7fd-79013bb42c2b",
        message_id: stoppedAssistant.id,
        type: "assistant.stopped",
        delta: null,
        retry: false,
        tool_call: null,
        message: stoppedAssistant,
        occurred_at: "2026-07-20T02:00:02Z",
      });
    });
    expect(await screen.findByText("部分回答")).toBeInTheDocument();
    expect(screen.getByText("已停止")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "重试回答" }));
    expect(chatApi.retryConversationMessage).toHaveBeenCalledWith(assistantMessage.id);

    act(() => {
      chatApi.streamOptions?.onEvent({
        schema_version: "2",
        sequence: 5,
        conversation_id: conversation.id,
        turn_id: "a8f4569b-2cff-46fa-b8ed-006068f60335",
        message_id: assistantMessage.id,
        type: "assistant.completed",
        delta: null,
        retry: true,
        tool_call: null,
        message: assistantMessage,
        occurred_at: "2026-07-20T02:00:03Z",
      });
      chatApi.streamOptions?.onEvent({
        schema_version: "2",
        sequence: 4,
        conversation_id: conversation.id,
        turn_id: "a8f4569b-2cff-46fa-b8ed-006068f60335",
        message_id: assistantMessage.id,
        type: "assistant.delta",
        delta: "晚到内容",
        retry: true,
        tool_call: null,
        message: { ...assistantMessage, content: "晚到内容", status: "streaming" },
        occurred_at: "2026-07-20T02:00:04Z",
      });
    });

    expect(await screen.findByText("验收标记是 COMMON_AGENT_CHAT_OK。"))
      .toBeInTheDocument();
    expect(screen.queryByText("晚到内容")).not.toBeInTheDocument();
  });

  it("keeps a newer SSE snapshot when the accepted send response arrives later", async () => {
    chatApi.fetchConversationMessages.mockResolvedValue([]);
    const pendingAssistant = {
      ...assistantMessage,
      content: "",
      citations: [],
      status: "pending" as const,
    };
    const streamingAssistant = {
      ...pendingAssistant,
      content: "先到的流式内容",
      status: "streaming" as const,
      updated_at: "2026-07-20T02:00:03Z",
    };
    let acceptSend: ((turn: unknown) => void) | undefined;
    chatApi.sendConversationMessage.mockImplementation(
      () =>
        new Promise((resolve) => {
          acceptSend = resolve;
        }),
    );
    const user = userEvent.setup();
    renderPage();

    await screen.findByRole("heading", { name: "知识问答" });
    await user.type(screen.getByRole("textbox", { name: "消息输入" }), userMessage.content);
    await user.click(screen.getByRole("button", { name: "发送消息" }));
    await waitFor(() => expect(chatApi.streamOptions).toBeDefined());
    act(() => {
      chatApi.streamOptions?.onEvent({
        schema_version: "2",
        sequence: 2,
        conversation_id: conversation.id,
        turn_id: "3a64b792-d4a9-4296-a7fd-79013bb42c2b",
        message_id: streamingAssistant.id,
        type: "assistant.delta",
        delta: streamingAssistant.content,
        retry: false,
        tool_call: null,
        message: streamingAssistant,
        occurred_at: streamingAssistant.updated_at,
      });
    });
    expect(await screen.findByText(streamingAssistant.content)).toBeInTheDocument();

    act(() => {
      acceptSend?.({
        turn_id: "3a64b792-d4a9-4296-a7fd-79013bb42c2b",
        user_message: userMessage,
        assistant_message: pendingAssistant,
        retry: false,
      });
    });

    expect(await screen.findByText(streamingAssistant.content)).toBeInTheDocument();
    expect(screen.queryByText("正在思考…")).not.toBeInTheDocument();
  });

  it("refreshes authoritative history after an SSE connection error", async () => {
    const refreshed = { ...assistantMessage, content: "刷新恢复后的回答" };
    chatApi.fetchConversationMessages
      .mockResolvedValueOnce([userMessage])
      .mockResolvedValue([userMessage, refreshed]);
    renderPage();

    await screen.findByText("验收标记是什么？");
    act(() => chatApi.streamOptions?.onError(new Error("事件流连接中断")));

    expect(await screen.findByText("会话连接已中断，正在恢复消息历史")).toBeInTheDocument();
    expect(await screen.findByText("刷新恢复后的回答")).toBeInTheDocument();
    expect(chatApi.fetchConversationMessages).toHaveBeenCalledTimes(2);
  });
});
