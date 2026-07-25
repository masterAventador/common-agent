import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { PropsWithChildren } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ToastHost } from "../../components/ToastHost";
import { KnowledgeBasesPage } from "./KnowledgeBasesPage";

const knowledgeApi = vi.hoisted(() => ({
  createKnowledgeBase: vi.fn(),
  deleteKnowledgeBase: vi.fn(),
  fetchKnowledgeBases: vi.fn(),
  fetchKnowledgeDocuments: vi.fn(),
  uploadKnowledgeDocument: vi.fn(),
}));

vi.mock("../../api/knowledge", () => knowledgeApi);

const knowledgeBase = {
  id: "kb-1",
  name: "通用产品手册",
  description: "与业务无关的公共资料",
  document_count: 4,
  parsing_count: 1,
};

const documents = [
  {
    id: "doc-uploaded",
    knowledge_base_id: "kb-1",
    name: "uploaded.txt",
    size_bytes: 10,
    parsing_status: "uploaded",
    error_code: null,
  },
  {
    id: "doc-parsing",
    knowledge_base_id: "kb-1",
    name: "parsing.md",
    size_bytes: 20,
    parsing_status: "parsing",
    error_code: null,
  },
  {
    id: "doc-completed",
    knowledge_base_id: "kb-1",
    name: "completed.pdf",
    size_bytes: 30,
    parsing_status: "completed",
    error_code: null,
  },
  {
    id: "doc-failed",
    knowledge_base_id: "kb-1",
    name: "failed.docx",
    size_bytes: 40,
    parsing_status: "failed",
    error_code: "parser_failed",
  },
] as const;

function TestProviders({ children }: PropsWithChildren) {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return <QueryClientProvider client={client}>{children}<ToastHost /></QueryClientProvider>;
}

describe("KnowledgeBasesPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    knowledgeApi.fetchKnowledgeBases.mockResolvedValue({ items: [], next_cursor: null });
    knowledgeApi.fetchKnowledgeDocuments.mockResolvedValue([]);
  });

  it("renders an actionable empty state", async () => {
    render(<KnowledgeBasesPage />, { wrapper: TestProviders });

    expect(await screen.findByText("还没有知识库")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "创建知识库" })).toBeEnabled();
    expect(knowledgeApi.fetchKnowledgeDocuments).not.toHaveBeenCalled();
  });

  it("keeps the cursor chain, loads another page, and removes cross-page duplicates", async () => {
    const second = { ...knowledgeBase, id: "kb-2", name: "第二个知识库" };
    knowledgeApi.fetchKnowledgeBases.mockImplementation(
      async ({ cursor, search }: { cursor?: string; search?: string }) => {
        if (search === "第二个") return { items: [second], next_cursor: null };
        if (cursor === "cursor-2") {
          return { items: [knowledgeBase, second], next_cursor: null };
        }
        return { items: [knowledgeBase], next_cursor: "cursor-2" };
      },
    );
    const user = userEvent.setup();
    render(<KnowledgeBasesPage />, { wrapper: TestProviders });

    expect(await screen.findByText(knowledgeBase.name)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "加载更多知识库" }));
    expect(await screen.findByText(second.name)).toBeInTheDocument();
    expect(screen.getAllByText(knowledgeBase.name)).toHaveLength(1);
    expect(knowledgeApi.fetchKnowledgeBases).toHaveBeenCalledWith({
      cursor: "cursor-2",
      limit: 20,
      search: "",
    });

    await user.type(screen.getByRole("searchbox", { name: "搜索知识库" }), "第二个");
    await waitFor(() =>
      expect(knowledgeApi.fetchKnowledgeBases).toHaveBeenCalledWith({
        cursor: undefined,
        limit: 20,
        search: "第二个",
      }),
    );
  });

  it("creates a generic knowledge base and refreshes the list", async () => {
    knowledgeApi.fetchKnowledgeBases
      .mockResolvedValueOnce({ items: [], next_cursor: null })
      .mockResolvedValue({ items: [knowledgeBase], next_cursor: null });
    knowledgeApi.createKnowledgeBase.mockResolvedValue(knowledgeBase);
    const user = userEvent.setup();
    render(<KnowledgeBasesPage />, { wrapper: TestProviders });

    await screen.findByText("还没有知识库");
    await user.click(screen.getByRole("button", { name: "创建知识库" }));
    await user.type(screen.getByRole("textbox", { name: "名称" }), "通用产品手册");
    await user.type(screen.getByRole("textbox", { name: "描述" }), "与业务无关的公共资料");
    await user.click(screen.getByRole("button", { name: "确认创建" }));

    await waitFor(() =>
      expect(knowledgeApi.createKnowledgeBase).toHaveBeenCalledWith({
        name: "通用产品手册",
        description: "与业务无关的公共资料",
      }),
    );
    expect(await screen.findByText("通用产品手册")).toBeInTheDocument();
  });

  it("shows all real parsing states and uploads an allowed document", async () => {
    knowledgeApi.fetchKnowledgeBases.mockResolvedValue({
      items: [knowledgeBase],
      next_cursor: null,
    });
    knowledgeApi.fetchKnowledgeDocuments.mockResolvedValue(documents);
    knowledgeApi.uploadKnowledgeDocument.mockResolvedValue(documents[1]);
    const user = userEvent.setup();
    render(<KnowledgeBasesPage />, { wrapper: TestProviders });

    expect(await screen.findByText("已上传")).toBeInTheDocument();
    expect(screen.getByText("解析中")).toBeInTheDocument();
    expect(screen.getByText("已完成")).toBeInTheDocument();
    expect(screen.getByText("解析失败")).toBeInTheDocument();
    expect(screen.getByText("parser_failed")).toBeInTheDocument();

    const file = new File(["shared knowledge"], "shared.txt", { type: "text/plain" });
    await user.upload(screen.getByLabelText("选择或拖拽文档"), file);
    await user.click(screen.getByRole("button", { name: "开始上传" }));

    await waitFor(() =>
      expect(knowledgeApi.uploadKnowledgeDocument).toHaveBeenCalledWith("kb-1", file),
    );
  });

  it("shows a safe list error and retries through the same query", async () => {
    knowledgeApi.fetchKnowledgeBases
      .mockRejectedValueOnce(new Error("知识库服务暂时不可用"))
      .mockResolvedValueOnce({ items: [], next_cursor: null });
    const user = userEvent.setup();
    render(<KnowledgeBasesPage />, { wrapper: TestProviders });

    expect(await screen.findByText("知识库加载失败")).toBeInTheDocument();
    expect(screen.getByText("知识库服务暂时不可用")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "重试加载" }));

    expect(await screen.findByText("还没有知识库")).toBeInTheDocument();
    expect(knowledgeApi.fetchKnowledgeBases).toHaveBeenCalledTimes(2);
  });

  it("confirms knowledge-base deletion and clears its documents only after success", async () => {
    knowledgeApi.fetchKnowledgeBases
      .mockResolvedValueOnce({ items: [knowledgeBase], next_cursor: null })
      .mockResolvedValue({ items: [], next_cursor: null });
    knowledgeApi.fetchKnowledgeDocuments.mockResolvedValue(documents);
    knowledgeApi.deleteKnowledgeBase.mockResolvedValue(undefined);
    const user = userEvent.setup();
    render(<KnowledgeBasesPage />, { wrapper: TestProviders });

    await user.click(
      await screen.findByRole("button", { name: `删除知识库 ${knowledgeBase.name}` }),
    );
    expect(screen.getByText("知识库中的文档、切片和索引都会被永久删除。")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: `确认删除知识库 ${knowledgeBase.name}` }));

    await waitFor(() =>
      expect(knowledgeApi.deleteKnowledgeBase).toHaveBeenCalledWith(knowledgeBase.id),
    );
    const removalToast = await screen.findByText(`知识库“${knowledgeBase.name}”已删除`);
    expect(removalToast.closest(".toast-item")).toHaveAttribute("role", "status");
    expect(await screen.findByText("还没有知识库")).toBeInTheDocument();
  });
});
