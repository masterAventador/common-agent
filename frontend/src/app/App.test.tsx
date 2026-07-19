import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { AppProviders } from "./AppProviders";
import { App } from "./App";

vi.mock("../api/system", () => ({
  fetchHealth: vi.fn().mockResolvedValue({
    status: "ok",
    service: "common-agent-api",
    version: "0.1.0",
  }),
}));

vi.mock("../api/knowledge", () => ({
  fetchKnowledgeBases: vi.fn().mockResolvedValue([]),
  fetchKnowledgeDocuments: vi.fn().mockResolvedValue([]),
  createKnowledgeBase: vi.fn(),
  uploadKnowledgeDocument: vi.fn(),
}));

vi.mock("../api/employees", () => ({
  fetchEmployees: vi.fn().mockResolvedValue([
    {
      id: "6f3d43e0-6f6d-5a67-9f25-756a0b9ed2ab",
      name: "知识助理",
      description: "通用知识问答",
      system_prompt: "直接回答问题。",
      knowledge_base_id: null,
      allowed_workflow_ids: [],
      created_at: "2026-07-20T02:00:00Z",
      updated_at: "2026-07-20T02:00:00Z",
    },
  ]),
  createEmployee: vi.fn(),
  updateEmployee: vi.fn(),
}));

vi.mock("../api/conversations", () => ({
  createConversation: vi.fn(),
  fetchConversationMessages: vi.fn().mockResolvedValue([]),
  fetchConversations: vi.fn().mockResolvedValue([]),
  retryConversationMessage: vi.fn(),
  sendConversationMessage: vi.fn(),
  stopConversationGeneration: vi.fn(),
  subscribeToConversationEvents: vi.fn(() => ({ close: vi.fn() })),
}));

const routes = [
  ["/chat", "AI 会话"],
  ["/employees", "数字员工"],
  ["/knowledge-bases", "知识库"],
  ["/workflows", "工作流"],
] as const;

describe("App shell", () => {
  it.each(routes)("renders %s as the %s entry", async (path, heading) => {
    render(
      <AppProviders>
        <MemoryRouter initialEntries={[path]}>
          <App />
        </MemoryRouter>
      </AppProviders>,
    );

    expect(await screen.findByRole("heading", { name: heading })).toBeInTheDocument();
    for (const [, label] of routes) {
      expect(screen.getByRole("link", { name: label })).toBeInTheDocument();
    }
  });

  it("redirects the root entry to chat", async () => {
    render(
      <AppProviders>
        <MemoryRouter initialEntries={["/"]}>
          <App />
        </MemoryRouter>
      </AppProviders>,
    );

    expect(await screen.findByRole("heading", { name: "AI 会话" })).toBeInTheDocument();
  });
});
