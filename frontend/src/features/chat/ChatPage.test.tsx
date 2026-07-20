import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { PropsWithChildren } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ChatPage } from "./ChatPage";

const employeeApi = vi.hoisted(() => ({
  fetchEmployees: vi.fn(),
}));
const chatApi = vi.hoisted(() => ({
  createConversation: vi.fn(),
  deleteConversation: vi.fn(),
  fetchConversationMessages: vi.fn(),
  fetchConversations: vi.fn(),
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
const workflowRunApi = vi.hoisted(() => ({
  fetchConversationWorkflowRuns: vi.fn(),
}));
const workflowApi = vi.hoisted(() => ({
  fetchWorkflows: vi.fn(),
}));

vi.mock("../../api/employees", () => employeeApi);
vi.mock("../../api/conversations", () => chatApi);
vi.mock("../../api/workflowRuns", () => workflowRunApi);
vi.mock("../../api/workflows", () => workflowApi);

const employee = {
  id: "6f3d43e0-6f6d-5a67-9f25-756a0b9ed2ab",
  name: "知识助理",
  description: "通用知识问答",
  system_prompt: "优先依据知识库回答。",
  knowledge_base_id: "kb-1",
  allowed_workflow_ids: [],
  created_at: "2026-07-20T02:00:00Z",
  updated_at: "2026-07-20T02:00:00Z",
};

const conversation = {
  id: "a0fcaad2-a53d-40c8-9f64-23298bfacf49",
  employee_id: employee.id,
  title: "知识问答",
  created_at: "2026-07-20T02:00:00Z",
  updated_at: "2026-07-20T02:00:00Z",
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
  created_at: "2026-07-20T02:00:01Z",
  updated_at: "2026-07-20T02:00:01Z",
};

const assistantMessage = {
  ...userMessage,
  id: "baeed6a2-d8cb-49ac-8999-393cf2153161",
  sequence_number: 2,
  role: "assistant" as const,
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

describe("ChatPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    chatApi.streamOptions = undefined;
    employeeApi.fetchEmployees.mockResolvedValue({ items: [employee], next_cursor: null });
    chatApi.fetchConversations.mockResolvedValue({ items: [conversation], next_cursor: null });
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

  it("renders conversation list, message history with citations, and employee details", async () => {
    renderPage();

    expect(await screen.findByRole("heading", { name: "AI 会话" })).toBeInTheDocument();
    const conversationList = screen.getByRole("region", { name: "会话列表" });
    const messageRegion = screen.getByRole("region", { name: "消息区域" });
    const employeeRegion = screen.getByRole("region", { name: "数字员工信息" });
    expect(
      await within(conversationList).findByRole("button", { name: "打开会话 知识问答" }),
    ).toBeEnabled();
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

  it("loads additional conversation and run pages while preserving remote search", async () => {
    const secondConversation = {
      ...conversation,
      id: "866c5d4d-1c64-4ff8-98df-778aa7569461",
      title: "第二个知识问答",
    };
    const secondRun = {
      ...employeeRun,
      id: "5262373b-10ea-4377-a75c-8242e90f3e63",
      input: "第二次执行",
      output: "第二次工作流已完成",
    };
    chatApi.fetchConversations.mockImplementation(
      (_employeeId: string, { cursor, search }: { cursor?: string; search?: string }) => {
        if (search) return Promise.resolve({ items: [conversation], next_cursor: null });
        if (cursor === "conversation-next") {
          return Promise.resolve({ items: [secondConversation], next_cursor: null });
        }
        return Promise.resolve({ items: [conversation], next_cursor: "conversation-next" });
      },
    );
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

    await user.click(await screen.findByRole("button", { name: "加载更多会话" }));
    expect(
      await screen.findByRole("button", { name: `打开会话 ${secondConversation.title}` }),
    ).toBeEnabled();
    await user.click(screen.getByRole("button", { name: "加载更多运行记录" }));
    await waitFor(() =>
      expect(workflowRunApi.fetchConversationWorkflowRuns).toHaveBeenCalledWith(conversation.id, {
        cursor: "run-next",
        limit: 50,
      }),
    );

    await user.type(screen.getByRole("searchbox", { name: "搜索会话" }), "知识");
    await waitFor(() =>
      expect(chatApi.fetchConversations).toHaveBeenCalledWith(employee.id, {
        cursor: undefined,
        limit: 20,
        search: "知识",
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

  it("creates a conversation from the selected employee", async () => {
    chatApi.fetchConversations
      .mockResolvedValueOnce({ items: [], next_cursor: null })
      .mockResolvedValue({ items: [conversation], next_cursor: null });
    chatApi.fetchConversationMessages.mockResolvedValue([]);
    chatApi.createConversation.mockResolvedValue(conversation);
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: "新建会话" }));

    await waitFor(() =>
      expect(chatApi.createConversation).toHaveBeenCalledWith({
        conversation_id: expect.any(String),
        employee_id: employee.id,
        title: "新会话",
      }),
    );
    expect(await screen.findByRole("heading", { name: "知识问答" })).toBeInTheDocument();
  });

  it("confirms conversation deletion and moves to the empty state after the server succeeds", async () => {
    chatApi.fetchConversations
      .mockResolvedValueOnce({ items: [conversation], next_cursor: null })
      .mockResolvedValue({ items: [], next_cursor: null });
    chatApi.deleteConversation.mockResolvedValue(undefined);
    const user = userEvent.setup();
    renderPage();

    await user.click(
      await screen.findByRole("button", { name: `删除会话 ${conversation.title}` }),
    );
    expect(screen.getAllByText(`删除会话“${conversation.title}”？`).length).toBeGreaterThan(0);
    expect(screen.getByText("消息、引用和由该会话触发的工作流运行都会被永久删除。")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: `确认删除会话 ${conversation.title}` }));

    await waitFor(() => expect(chatApi.deleteConversation).toHaveBeenCalledWith(conversation.id));
    expect(await screen.findByText(`会话“${conversation.title}”已删除`)).toBeInTheDocument();
    expect(await screen.findByText("还没有会话")).toBeInTheDocument();
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
        schema_version: "1",
        sequence: 3,
        conversation_id: conversation.id,
        turn_id: "3a64b792-d4a9-4296-a7fd-79013bb42c2b",
        message_id: stoppedAssistant.id,
        type: "assistant.stopped",
        delta: null,
        retry: false,
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
        schema_version: "1",
        sequence: 5,
        conversation_id: conversation.id,
        turn_id: "a8f4569b-2cff-46fa-b8ed-006068f60335",
        message_id: assistantMessage.id,
        type: "assistant.completed",
        delta: null,
        retry: true,
        message: assistantMessage,
        occurred_at: "2026-07-20T02:00:03Z",
      });
      chatApi.streamOptions?.onEvent({
        schema_version: "1",
        sequence: 4,
        conversation_id: conversation.id,
        turn_id: "a8f4569b-2cff-46fa-b8ed-006068f60335",
        message_id: assistantMessage.id,
        type: "assistant.delta",
        delta: "晚到内容",
        retry: true,
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
        schema_version: "1",
        sequence: 2,
        conversation_id: conversation.id,
        turn_id: "3a64b792-d4a9-4296-a7fd-79013bb42c2b",
        message_id: streamingAssistant.id,
        type: "assistant.delta",
        delta: streamingAssistant.content,
        retry: false,
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
