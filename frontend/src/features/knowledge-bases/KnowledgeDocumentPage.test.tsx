import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { PropsWithChildren } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ToastHost } from "../../components/ToastHost";
import { KnowledgeDocumentPage } from "./KnowledgeDocumentPage";

const knowledgeApi = vi.hoisted(() => ({
  fetchKnowledgeBase: vi.fn(),
  fetchKnowledgeDocuments: vi.fn(),
  fetchDocumentChunks: vi.fn(),
}));

vi.mock("../../api/knowledge", () => knowledgeApi);

const knowledgeBase = {
  id: "kb-1",
  name: "制度库",
  description: "内部制度",
  document_count: 1,
  parsing_count: 0,
};

const document = {
  id: "doc-1",
  knowledge_base_id: "kb-1",
  name: "住房租赁常识.docx",
  size_bytes: 7243,
  parsing_status: "completed" as const,
  error_code: null,
};

const chunks = [
  { id: "chunk-1", document_id: "doc-1", content: "第一段：押金与租金的约定。", position: 1 },
  { id: "chunk-2", document_id: "doc-1", content: "第二段：承租人的义务。", position: 2 },
];

function Providers({ children }: PropsWithChildren) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  return (
    <QueryClientProvider client={client}>
      {children}
      <ToastHost />
    </QueryClientProvider>
  );
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/knowledge-bases/kb-1/documents/doc-1"]}>
      <Routes>
        <Route
          path="/knowledge-bases/:knowledgeBaseId/documents/:documentId"
          element={<KnowledgeDocumentPage />}
        />
      </Routes>
    </MemoryRouter>,
    { wrapper: Providers },
  );
}

describe("KnowledgeDocumentPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    knowledgeApi.fetchKnowledgeBase.mockResolvedValue(knowledgeBase);
    knowledgeApi.fetchKnowledgeDocuments.mockResolvedValue([document]);
    knowledgeApi.fetchDocumentChunks.mockResolvedValue({ items: chunks, next_cursor: null });
  });

  it("shows the document text on the left and its chunks on the right", async () => {
    renderPage();

    expect(await screen.findByRole("heading", { name: document.name })).toBeInTheDocument();

    const preview = screen.getByRole("region", { name: "文档预览" });
    expect(within(preview).getByText(/押金与租金的约定/)).toBeInTheDocument();
    expect(within(preview).getByText(/承租人的义务/)).toBeInTheDocument();

    const list = screen.getByRole("region", { name: "切片列表" });
    expect(within(list).getByText("#1")).toBeInTheDocument();
    expect(within(list).getByText("#2")).toBeInTheDocument();
  });

  it("highlights the matching paragraph when a chunk is selected", async () => {
    const user = userEvent.setup();
    renderPage();

    const list = await screen.findByRole("region", { name: "切片列表" });
    await user.click(await within(list).findByRole("button", { name: /切片 2/ }));

    await waitFor(() => {
      const preview = screen.getByRole("region", { name: "文档预览" });
      const active = within(preview).getByText(/承租人的义务/).closest(".knowledge-preview-block");
      expect(active).toHaveClass("is-active");
    });
  });

  it("keeps a safe error and a way back when chunks fail to load", async () => {
    knowledgeApi.fetchDocumentChunks.mockRejectedValue(new Error("解析服务暂时不可用"));
    renderPage();

    expect(await screen.findByText("切片加载失败")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "返回知识库" })).toBeInTheDocument();
  });
});
