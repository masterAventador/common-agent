import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { PropsWithChildren } from "react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiClientError } from "../../api/errors";
import { EmployeesPage } from "./EmployeesPage";

const employeeApi = vi.hoisted(() => ({
  createEmployee: vi.fn(),
  deleteEmployee: vi.fn(),
  fetchEmployees: vi.fn(),
  updateEmployee: vi.fn(),
}));
const knowledgeApi = vi.hoisted(() => ({
  fetchKnowledgeBases: vi.fn(),
}));
const workflowApi = vi.hoisted(() => ({
  fetchWorkflows: vi.fn(),
}));

vi.mock("../../api/employees", () => employeeApi);
vi.mock("../../api/knowledge", () => knowledgeApi);
vi.mock("../../api/workflows", () => workflowApi);

const knowledgeBase = {
  id: "kb-1",
  name: "通用产品手册",
  description: "公共资料",
  document_count: 2,
  parsing_count: 0,
};

const workflow = {
  id: "9a2f8cb8-7f5f-41f8-b101-9ed76f40d9c6",
  name: "产品问答流程",
  description: "受控工作流",
  nodes: [],
  edges: [],
  created_at: "2026-07-20T04:00:00Z",
  updated_at: "2026-07-20T04:00:00Z",
};

const employee = {
  id: "6f3d43e0-6f6d-5a67-9f25-756a0b9ed2ab",
  name: "知识助理",
  description: "通用知识问答",
  system_prompt: "优先依据知识库回答。",
  knowledge_base_id: "kb-1",
  allowed_workflow_ids: [],
  created_at: "2026-07-19T08:00:00Z",
  updated_at: "2026-07-19T08:00:00Z",
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

function LocationProbe() {
  const location = useLocation();
  return <div>{`${location.pathname}${location.search}`}</div>;
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/employees"]}>
      <Routes>
        <Route path="/employees" element={<EmployeesPage />} />
        <Route path="/chat" element={<LocationProbe />} />
      </Routes>
    </MemoryRouter>,
    { wrapper: TestProviders },
  );
}

describe("EmployeesPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    employeeApi.fetchEmployees.mockResolvedValue([employee]);
    knowledgeApi.fetchKnowledgeBases.mockResolvedValue([knowledgeBase]);
    workflowApi.fetchWorkflows.mockResolvedValue([workflow]);
  });

  it("lists generic employees and resolves their bound knowledge base names", async () => {
    renderPage();

    expect(await screen.findByRole("heading", { name: "数字员工" })).toBeInTheDocument();
    expect(screen.getByText("知识助理")).toBeInTheDocument();
    expect(screen.getByText("通用知识问答")).toBeInTheDocument();
    expect(screen.getByText("通用产品手册")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "编辑 知识助理" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "与知识助理开始对话" })).toBeEnabled();
  });

  it("creates an employee with an optional knowledge-base binding", async () => {
    const created = {
      ...employee,
      id: "9c016293-e654-43cd-bb45-f903dbdc35ba",
      name: "制度问答助理",
    };
    employeeApi.fetchEmployees
      .mockResolvedValueOnce([employee])
      .mockResolvedValue([employee, created]);
    employeeApi.createEmployee.mockResolvedValue(created);
    const user = userEvent.setup();
    renderPage();

    await screen.findByText("知识助理");
    await user.click(screen.getByRole("button", { name: "创建数字员工" }));
    await user.type(screen.getByRole("textbox", { name: "名称" }), "制度问答助理");
    await user.type(screen.getByRole("textbox", { name: "说明" }), "回答内部制度问题");
    await user.type(screen.getByRole("textbox", { name: "系统指令" }), "只依据可靠资料回答。");
    fireEvent.mouseDown(screen.getByRole("combobox", { name: "知识库" }));
    await screen.findByRole("option", { name: "通用产品手册" });
    fireEvent.click(await screen.findByTitle("通用产品手册"));
    fireEvent.mouseDown(screen.getByRole("combobox", { name: "允许工作流" }));
    fireEvent.click(await screen.findByTitle("产品问答流程"));
    expect(screen.getAllByText("通用产品手册").length).toBeGreaterThan(1);
    await user.click(screen.getByRole("button", { name: "确认创建" }));

    await waitFor(() =>
      expect(employeeApi.createEmployee).toHaveBeenCalledWith({
        name: "制度问答助理",
        description: "回答内部制度问题",
        system_prompt: "只依据可靠资料回答。",
        knowledge_base_id: "kb-1",
        allowed_workflow_ids: [workflow.id],
      }),
    );
    expect(await screen.findByText("制度问答助理")).toBeInTheDocument();
  });

  it("edits an existing employee without losing the knowledge-base binding", async () => {
    const updated = { ...employee, description: "更新后的说明" };
    employeeApi.fetchEmployees.mockResolvedValueOnce([employee]).mockResolvedValue([updated]);
    employeeApi.updateEmployee.mockResolvedValue(updated);
    const user = userEvent.setup();
    renderPage();

    await screen.findByText("知识助理");
    await user.click(screen.getByRole("button", { name: "编辑 知识助理" }));
    const description = screen.getByRole("textbox", { name: "说明" });
    expect(screen.getByRole("textbox", { name: "名称" })).toHaveValue("知识助理");
    expect(screen.getByRole("textbox", { name: "系统指令" })).toHaveValue(
      "优先依据知识库回答。",
    );
    await user.clear(description);
    await user.type(description, "更新后的说明");
    await user.click(screen.getByRole("button", { name: "保存修改" }));

    await waitFor(() =>
      expect(employeeApi.updateEmployee).toHaveBeenCalledWith(employee.id, {
        name: "知识助理",
        description: "更新后的说明",
        system_prompt: "优先依据知识库回答。",
        knowledge_base_id: "kb-1",
        allowed_workflow_ids: [],
      }),
    );
    expect(await screen.findByText("更新后的说明")).toBeInTheDocument();
  });

  it("keeps employees usable when the knowledge-base list is unavailable", async () => {
    knowledgeApi.fetchKnowledgeBases.mockRejectedValue(new Error("知识库服务暂时不可用"));
    const user = userEvent.setup();
    renderPage();

    expect(await screen.findByText("知识助理")).toBeInTheDocument();
    expect(screen.getByText("知识库选项加载失败")).toBeInTheDocument();
    expect(screen.getByText("知识库服务暂时不可用")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "创建数字员工" }));
    expect(screen.getByRole("combobox", { name: "知识库" })).toBeDisabled();
  });

  it("shows existing workflow permissions and disables only that field when workflows fail", async () => {
    employeeApi.fetchEmployees.mockResolvedValue([{ ...employee, allowed_workflow_ids: [workflow.id] }]);
    workflowApi.fetchWorkflows.mockRejectedValue(new Error("工作流服务暂时不可用"));
    const user = userEvent.setup();
    renderPage();

    expect(await screen.findByText("工作流选项加载失败")).toBeInTheDocument();
    expect(screen.getByText("已授权 1 个工作流")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "编辑 知识助理" }));
    expect(screen.getByRole("combobox", { name: "允许工作流" })).toBeDisabled();
    expect(screen.getByRole("combobox", { name: "知识库" })).toBeEnabled();
  });

  it("keeps the modal footer reachable on short desktop viewports", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: "创建数字员工" }));

    const body = document.querySelector(".ant-modal-body");
    expect(body).not.toBeNull();
    expect(body).toHaveStyle({
      maxHeight: "calc(100vh - 280px)",
      overflowY: "auto",
    });
    expect(screen.getByRole("button", { name: "确认创建" })).toBeEnabled();
  });

  it("shows a safe employee-list error and retries the same query", async () => {
    employeeApi.fetchEmployees
      .mockRejectedValueOnce(new Error("无法连接后端服务"))
      .mockResolvedValueOnce([employee]);
    const user = userEvent.setup();
    renderPage();

    expect(await screen.findByText("数字员工加载失败")).toBeInTheDocument();
    expect(screen.getByText("无法连接后端服务")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "重试加载" }));

    expect(await screen.findByText("知识助理")).toBeInTheDocument();
    expect(employeeApi.fetchEmployees).toHaveBeenCalledTimes(2);
  });

  it("enters chat through the public route with the selected employee", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: "与知识助理开始对话" }));

    expect(screen.getByText(`/chat?employee_id=${employee.id}`)).toBeInTheDocument();
  });

  it("keeps an employee visible and explains the conversation reference blocker", async () => {
    employeeApi.deleteEmployee.mockRejectedValue(
      new ApiClientError(
        "数字员工仍被会话引用。请先删除相关会话",
        "employee_in_use_by_conversations",
        "request-1",
        false,
      ),
    );
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: `删除数字员工 ${employee.name}` }));
    await user.click(screen.getByRole("button", { name: `确认删除数字员工 ${employee.name}` }));

    expect(
      await screen.findByText("该数字员工仍被会话引用，请先在 AI 会话页删除相关会话。"),
    ).toBeInTheDocument();
    expect(screen.getByText(employee.name)).toBeInTheDocument();
  });

  it("removes an employee from the list only after deletion succeeds", async () => {
    employeeApi.fetchEmployees.mockResolvedValueOnce([employee]).mockResolvedValue([]);
    employeeApi.deleteEmployee.mockResolvedValue(undefined);
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: `删除数字员工 ${employee.name}` }));
    await user.click(screen.getByRole("button", { name: `确认删除数字员工 ${employee.name}` }));

    await waitFor(() => expect(employeeApi.deleteEmployee).toHaveBeenCalledWith(employee.id));
    expect(await screen.findByText(`数字员工“${employee.name}”已删除`)).toBeInTheDocument();
    expect(await screen.findByText("还没有数字员工")).toBeInTheDocument();
  });
});
