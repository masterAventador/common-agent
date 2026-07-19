import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { PropsWithChildren } from "react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { EmployeesPage } from "./EmployeesPage";

const employeeApi = vi.hoisted(() => ({
  createEmployee: vi.fn(),
  fetchEmployees: vi.fn(),
  updateEmployee: vi.fn(),
}));
const knowledgeApi = vi.hoisted(() => ({
  fetchKnowledgeBases: vi.fn(),
}));

vi.mock("../../api/employees", () => employeeApi);
vi.mock("../../api/knowledge", () => knowledgeApi);

const knowledgeBase = {
  id: "kb-1",
  name: "通用产品手册",
  description: "公共资料",
  document_count: 2,
  parsing_count: 0,
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
    expect(screen.getAllByText("通用产品手册").length).toBeGreaterThan(1);
    await user.click(screen.getByRole("button", { name: "确认创建" }));

    await waitFor(() =>
      expect(employeeApi.createEmployee).toHaveBeenCalledWith({
        name: "制度问答助理",
        description: "回答内部制度问题",
        system_prompt: "只依据可靠资料回答。",
        knowledge_base_id: "kb-1",
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
});
