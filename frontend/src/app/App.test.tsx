import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AppProviders } from "./AppProviders";
import { App } from "./App";

vi.mock("../api/auth", () => ({
  fetchAuthPolicy: vi.fn().mockResolvedValue({ registration_available: false }),
  fetchCurrentSession: vi.fn().mockResolvedValue({
    user_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    email: "owner@example.com",
    csrf_token: "csrf-token",
    idle_expires_at: "2026-07-21T03:00:00Z",
    absolute_expires_at: "2026-07-22T02:00:00Z",
  }),
  login: vi.fn(),
  logout: vi.fn(),
  registerOwner: vi.fn(),
  resetPassword: vi.fn(),
}));

vi.mock("../api/system", () => ({
  fetchSystemStatus: vi.fn().mockResolvedValue({
    backend: "available",
    service: "common-agent-api",
    version: "0.1.0",
    integration_mode: "real",
    model: { provider: "bailian", status: "configured" },
    knowledge: {
      provider: "ragflow",
      availability: "available",
      version: "v0.25.6",
      error_code: null,
    },
  }),
}));

const tenantAccesses = vi.hoisted(() => [
  {
    id: "10000000-0000-4000-8000-000000000001",
    name: "默认工作区",
    organization_id: "00000000-0000-4000-8000-000000000001",
    organization_name: "默认组织",
    role: "owner" as const,
  },
  {
    id: "20000000-0000-4000-8000-000000000002",
    name: "只读工作区",
    organization_id: "00000000-0000-4000-8000-000000000001",
    organization_name: "默认组织",
    role: "viewer" as const,
  },
]);

const tenancyApi = vi.hoisted(() => ({
  fetchTenantAccesses: vi.fn(),
  createTenant: vi.fn(),
  provisionTenantMember: vi.fn(),
}));

vi.mock("../api/tenants", () => tenancyApi);

vi.mock("../api/knowledge", () => ({
  fetchKnowledgeBases: vi.fn().mockResolvedValue({ items: [], next_cursor: null }),
  fetchKnowledgeDocuments: vi.fn().mockResolvedValue([]),
  createKnowledgeBase: vi.fn(),
  uploadKnowledgeDocument: vi.fn(),
}));

vi.mock("../api/employees", () => ({
  fetchEmployees: vi.fn().mockResolvedValue({
    items: [{
      id: "6f3d43e0-6f6d-5a67-9f25-756a0b9ed2ab",
      name: "知识助理",
      description: "通用知识问答",
      system_prompt: "直接回答问题。",
      knowledge_base_id: null,
      allowed_workflow_ids: [],
      created_at: "2026-07-20T02:00:00Z",
      updated_at: "2026-07-20T02:00:00Z",
    }],
    next_cursor: null,
  }),
  createEmployee: vi.fn(),
  updateEmployee: vi.fn(),
}));

vi.mock("../api/conversations", () => ({
  createConversation: vi.fn(),
  fetchConversationMessages: vi.fn().mockResolvedValue([]),
  fetchConversations: vi.fn().mockResolvedValue({ items: [], next_cursor: null }),
  retryConversationMessage: vi.fn(),
  sendConversationMessage: vi.fn(),
  stopConversationGeneration: vi.fn(),
  subscribeToConversationEvents: vi.fn(() => ({ close: vi.fn() })),
}));

vi.mock("../api/workflows", () => ({
  createWorkflow: vi.fn(),
  fetchWorkflows: vi.fn().mockResolvedValue({ items: [], next_cursor: null }),
  updateWorkflow: vi.fn(),
  validateWorkflow: vi.fn(),
}));

const routes = [
  ["/chat", "AI 会话"],
  ["/employees", "数字员工"],
  ["/knowledge-bases", "知识库"],
  ["/workflows", "工作流"],
] as const;

describe("App shell", () => {
  beforeEach(() => {
    tenancyApi.fetchTenantAccesses.mockReset();
    tenancyApi.fetchTenantAccesses.mockResolvedValue(tenantAccesses);
    tenancyApi.createTenant.mockReset();
    tenancyApi.provisionTenantMember.mockReset();
  });

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
    expect(screen.getByRole("combobox", { name: "当前工作区" })).toBeInTheDocument();
    expect(screen.getByText(/默认工作区/)).toBeInTheDocument();
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

  it("selects an explicit workspace and exposes viewer mode before mounting business routes", async () => {
    const user = userEvent.setup();
    render(
      <AppProviders>
        <MemoryRouter initialEntries={["/chat"]}>
          <App />
        </MemoryRouter>
      </AppProviders>,
    );

    const selector = await screen.findByRole("combobox", { name: "当前工作区" });
    expect(screen.getByText(/默认工作区/)).toBeInTheDocument();
    expect(screen.getByText("所有者")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "添加成员" })).toBeEnabled();

    await user.click(selector);
    await user.click(await screen.findByText(/只读工作区/));

    expect(await screen.findByText("当前工作区为只读模式")).toBeInTheDocument();
    expect(screen.getByText("访客")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "新建会话" })).toBeDisabled();
  });

  it("creates and selects a workspace through the owner dialog", async () => {
    const created = {
      ...tenantAccesses[0],
      id: "30000000-0000-4000-8000-000000000003",
      name: "商业工作区",
    };
    tenancyApi.createTenant.mockResolvedValue(created);
    const user = userEvent.setup();
    render(
      <AppProviders>
        <MemoryRouter initialEntries={["/chat"]}>
          <App />
        </MemoryRouter>
      </AppProviders>,
    );

    await user.click(await screen.findByRole("button", { name: "新建工作区" }));
    await user.type(screen.getByLabelText("工作区名称"), created.name);
    await user.click(screen.getByRole("button", { name: /创\s*建/ }));

    await waitFor(() =>
      expect(tenancyApi.createTenant).toHaveBeenCalledWith({
        organization_id: created.organization_id,
        name: created.name,
      }),
    );
    expect(await screen.findByText(new RegExp(created.name))).toBeInTheDocument();
  });

  it("provisions a viewer and shows its one-time recovery codes", async () => {
    const provisioned = {
      user_id: "40000000-0000-4000-8000-000000000004",
      email: "viewer@example.com",
      role: "viewer" as const,
      recovery_codes: ["ABCDEFGH-JKLMNPQR"],
    };
    tenancyApi.provisionTenantMember.mockResolvedValue(provisioned);
    const user = userEvent.setup();
    render(
      <AppProviders>
        <MemoryRouter initialEntries={["/chat"]}>
          <App />
        </MemoryRouter>
      </AppProviders>,
    );

    await user.click(await screen.findByRole("button", { name: "添加成员" }));
    await user.type(screen.getByLabelText("邮箱"), provisioned.email);
    await user.type(screen.getByLabelText("初始密码"), "viewer initial password is secure");
    await user.click(screen.getByRole("button", { name: /创\s*建\s*账\s*号/ }));

    await waitFor(() =>
      expect(tenancyApi.provisionTenantMember).toHaveBeenCalledWith(
        tenantAccesses[0].id,
        {
          email: provisioned.email,
          password: "viewer initial password is secure",
          role: "viewer",
        },
      ),
    );
    expect(await screen.findByText("成员账号已创建")).toBeInTheDocument();
    expect(screen.getByText("ABCDEFGH-JKLMNPQR")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "我已保存" }));
  });
});
