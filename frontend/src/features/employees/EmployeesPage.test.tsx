import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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
const modelApi = vi.hoisted(() => ({
  fetchModelConfigurations: vi.fn(),
}));
const toolApi = vi.hoisted(() => ({
  fetchEmployeeToolGrants: vi.fn(),
  fetchToolCatalog: vi.fn(),
  replaceEmployeeToolGrants: vi.fn(),
}));

vi.mock("../../api/employees", () => employeeApi);
vi.mock("../../api/knowledge", () => knowledgeApi);
vi.mock("../../api/workflows", () => workflowApi);
vi.mock("../../api/modelConfigurations", () => modelApi);
vi.mock("../../api/tools", () => toolApi);

const modelConfiguration = {
  id: "0d4f38a5-bfd1-496f-b99d-fd768a2f3c30",
  display_name: "Qwen Plus",
  provider: "bailian",
  model_identifier: "qwen-plus",
  enabled: true,
  created_at: "2026-07-22T04:00:00Z",
  updated_at: "2026-07-22T04:00:00Z",
};

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
  default_model_configuration_id: modelConfiguration.id,
  default_model_identifier: modelConfiguration.model_identifier,
  knowledge_base_id: "kb-1",
  allowed_workflow_ids: [],
  created_at: "2026-07-19T08:00:00Z",
  updated_at: "2026-07-19T08:00:00Z",
};

const toolCapability = {
  id: "10000000-0000-4000-8000-000000000001",
  source_id: "20000000-0000-4000-8000-000000000002",
  remote_name: "current_time",
  display_name: "当前时间",
  description: "读取指定时区的当前时间。",
  input_schema: { type: "object", properties: {}, additionalProperties: false },
  schema_fingerprint: "a".repeat(64),
  status: "active",
  created_at: "2026-07-22T02:00:00Z",
  updated_at: "2026-07-22T02:00:00Z",
};
const externalToolCapability = {
  ...toolCapability,
  id: "30000000-0000-4000-8000-000000000003",
  source_id: "40000000-0000-4000-8000-000000000004",
  remote_name: "partners.lookup",
  display_name: "查询合作方",
  schema_fingerprint: "b".repeat(64),
};
const toolCollection = {
  id: "50000000-0000-4000-8000-000000000005",
  name: "基础工具集",
  description: "平台基础能力",
  source_ids: [toolCapability.source_id],
  created_at: "2026-07-22T02:00:00Z",
  updated_at: "2026-07-22T02:00:00Z",
};
const toolCatalog = {
  sources: [
    {
      id: toolCapability.source_id,
      name: "平台工具",
      description: "零费用能力",
      source_type: "platform",
      endpoint_url: null,
      status: "ready",
      created_at: "2026-07-22T02:00:00Z",
      updated_at: "2026-07-22T02:00:00Z",
    },
    {
      id: externalToolCapability.source_id,
      name: "合作方 MCP",
      description: "外部能力",
      source_type: "external",
      endpoint_url: "https://partner.example/mcp",
      status: "ready",
      created_at: "2026-07-22T02:00:00Z",
      updated_at: "2026-07-22T02:00:00Z",
    },
  ],
  capabilities: [toolCapability, externalToolCapability],
  collections: [toolCollection],
};

function createTestClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
}

function LocationProbe() {
  const location = useLocation();
  return <div>{`${location.pathname}${location.search}`}</div>;
}

function renderPage(readOnly = false) {
  const client = createTestClient();
  const result = render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/employees"]}>
        <Routes>
          <Route path="/employees" element={<EmployeesPage readOnly={readOnly} />} />
          <Route path="/chat" element={<LocationProbe />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { ...result, client };
}

describe("EmployeesPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    employeeApi.fetchEmployees.mockResolvedValue({ items: [employee], next_cursor: null });
    knowledgeApi.fetchKnowledgeBases.mockResolvedValue({
      items: [knowledgeBase],
      next_cursor: null,
    });
    workflowApi.fetchWorkflows.mockResolvedValue({ items: [workflow], next_cursor: null });
    modelApi.fetchModelConfigurations.mockResolvedValue({
      items: [modelConfiguration],
      next_cursor: null,
    });
    toolApi.fetchToolCatalog.mockResolvedValue(toolCatalog);
    toolApi.fetchEmployeeToolGrants.mockResolvedValue({
      target_type: "employee",
      target_id: employee.id,
      collection_ids: [],
      capability_ids: [],
    });
    toolApi.replaceEmployeeToolGrants.mockResolvedValue({
      target_type: "employee",
      target_id: employee.id,
      collection_ids: [toolCollection.id],
      capability_ids: [toolCapability.id, externalToolCapability.id],
    });
  });

  it("lists generic employees and resolves their bound knowledge base names", async () => {
    renderPage();

    expect(await screen.findByRole("heading", { name: "数字员工" })).toBeInTheDocument();
    expect(screen.getByText("知识助理")).toBeInTheDocument();
    expect(screen.getByText("通用知识问答")).toBeInTheDocument();
    expect(await screen.findByText("通用产品手册")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "编辑 知识助理" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "与知识助理开始对话" })).toBeEnabled();
  });

  it("keeps the employee card compact like the design prototype", async () => {
    renderPage();

    expect(await screen.findByText("知识助理")).toBeInTheDocument();
    // 卡片收敛为「图标 + 名称 + 描述 + 底部状态栏」，系统指令只在编辑弹窗里出现
    expect(screen.queryByText("系统指令")).not.toBeInTheDocument();
    expect(screen.queryByText("默认模型")).not.toBeInTheDocument();
    expect(screen.queryByText("工作流权限")).not.toBeInTheDocument();
    // 底部状态栏仍然承载关键信息：工作流授权与所用模型
    expect(await screen.findByText("未授权工作流")).toBeInTheDocument();
    expect(await screen.findByText(modelConfiguration.display_name)).toBeInTheDocument();
  });

  it("loads reference options only when employees or the editor need them", async () => {
    employeeApi.fetchEmployees.mockResolvedValue({ items: [], next_cursor: null });
    const user = userEvent.setup();

    renderPage();

    expect(await screen.findByText("还没有数字员工")).toBeInTheDocument();
    expect(knowledgeApi.fetchKnowledgeBases).not.toHaveBeenCalled();
    expect(workflowApi.fetchWorkflows).not.toHaveBeenCalled();
    expect(modelApi.fetchModelConfigurations).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "创建数字员工" }));
    await waitFor(() => expect(knowledgeApi.fetchKnowledgeBases).toHaveBeenCalledTimes(1));
    expect(workflowApi.fetchWorkflows).toHaveBeenCalledTimes(1);
    expect(modelApi.fetchModelConfigurations).toHaveBeenCalledTimes(1);
  });

  it("keeps search in the query key and loads the next employee cursor page", async () => {
    const second = {
      ...employee,
      id: "f48cbd21-0b4e-4d76-b0c2-f7bb26ef62bf",
      name: "知识助理二号",
    };
    employeeApi.fetchEmployees.mockImplementation(
      ({ cursor, search }: { cursor?: string; search?: string }) => {
        if (search) return Promise.resolve({ items: [employee], next_cursor: null });
        if (cursor === "employee-next") {
          return Promise.resolve({ items: [second], next_cursor: null });
        }
        return Promise.resolve({ items: [employee], next_cursor: "employee-next" });
      },
    );
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: "加载更多数字员工" }));
    expect(await screen.findByText(second.name)).toBeInTheDocument();
    expect(employeeApi.fetchEmployees).toHaveBeenCalledWith({
      cursor: "employee-next",
      limit: 20,
      search: "",
    });

    await user.type(screen.getByRole("searchbox", { name: "搜索数字员工" }), "知识");
    await waitFor(() =>
      expect(employeeApi.fetchEmployees).toHaveBeenCalledWith({
        cursor: undefined,
        limit: 20,
        search: "知识",
      }),
    );
  });

  it("creates an employee with an optional knowledge-base binding", async () => {
    const created = {
      ...employee,
      id: "9c016293-e654-43cd-bb45-f903dbdc35ba",
      name: "制度问答助理",
    };
    employeeApi.fetchEmployees
      .mockResolvedValueOnce({ items: [employee], next_cursor: null })
      .mockResolvedValue({ items: [employee, created], next_cursor: null });
    employeeApi.createEmployee.mockResolvedValue(created);
    const user = userEvent.setup();
    renderPage();

    await screen.findByText("知识助理");
    await user.click(screen.getByRole("button", { name: "创建数字员工" }));
    await user.type(screen.getByRole("textbox", { name: "名称" }), "制度问答助理");
    await user.type(screen.getByRole("textbox", { name: "说明" }), "回答内部制度问题");
    await user.type(screen.getByRole("textbox", { name: "系统指令" }), "只依据可靠资料回答。");
    fireEvent.mouseDown(screen.getByRole("combobox", { name: "默认模型" }));
    fireEvent.click(await screen.findByTitle("Qwen Plus · qwen-plus"));
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
        default_model_configuration_id: modelConfiguration.id,
        knowledge_base_id: "kb-1",
        allowed_workflow_ids: [workflow.id],
      }),
    );
    expect(await screen.findByText("制度问答助理")).toBeInTheDocument();
  });

  it("edits an existing employee without losing the knowledge-base binding", async () => {
    const updated = { ...employee, description: "更新后的说明" };
    employeeApi.fetchEmployees
      .mockResolvedValueOnce({ items: [employee], next_cursor: null })
      .mockResolvedValue({ items: [updated], next_cursor: null });
    employeeApi.updateEmployee.mockResolvedValue(updated);
    const user = userEvent.setup();
    const { client } = renderPage();
    client.setQueryDefaults(["employee"], { gcTime: Infinity });
    client.setQueryData(["employee", employee.id], employee);

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
        default_model_configuration_id: modelConfiguration.id,
        knowledge_base_id: "kb-1",
        allowed_workflow_ids: [],
      }),
    );
    expect(await screen.findByText("更新后的说明")).toBeInTheDocument();
    expect(client.getQueryData(["employee", employee.id])).toEqual(updated);
  });

  it("edits exact employee grants from collections and individual capabilities", async () => {
    employeeApi.updateEmployee.mockResolvedValue(employee);
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: "编辑 知识助理" }));
    fireEvent.mouseDown(await screen.findByRole("combobox", { name: "业务工具集" }));
    fireEvent.click(await screen.findByTitle("基础工具集"));
    fireEvent.mouseDown(screen.getByRole("combobox", { name: "单项工具能力" }));
    fireEvent.click(await screen.findByTitle("查询合作方 · 合作方 MCP"));
    await user.click(screen.getByRole("button", { name: "保存修改" }));

    await waitFor(() =>
      expect(toolApi.replaceEmployeeToolGrants).toHaveBeenCalledWith(employee.id, {
        collection_ids: [toolCollection.id],
        capability_ids: [externalToolCapability.id],
      }),
    );
    expect(employeeApi.updateEmployee).toHaveBeenCalled();
  });

  it("keeps all employee mutation entry points disabled for viewers", async () => {
    renderPage(true);

    expect(await screen.findByRole("button", { name: "编辑 知识助理" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "创建数字员工" })).toBeDisabled();
  });

  it("keeps employees usable when the knowledge-base list is unavailable", async () => {
    knowledgeApi.fetchKnowledgeBases.mockRejectedValue(new Error("知识库服务暂时不可用"));
    const user = userEvent.setup();
    renderPage();

    expect(await screen.findByText("知识助理")).toBeInTheDocument();
    expect(await screen.findByText("知识库选项加载失败")).toBeInTheDocument();
    expect(screen.getByText("知识库服务暂时不可用")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "创建数字员工" }));
    expect(screen.getByRole("combobox", { name: "知识库" })).toBeDisabled();
  });

  it("fails closed when model options cannot be loaded", async () => {
    modelApi.fetchModelConfigurations.mockRejectedValue(
      new Error("模型配置服务暂时不可用"),
    );
    const user = userEvent.setup();
    renderPage();

    expect(await screen.findByText("模型选项加载失败")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "创建数字员工" }));
    expect(screen.getByRole("combobox", { name: "默认模型" })).toBeDisabled();
  });

  it("shows existing workflow permissions and disables only that field when workflows fail", async () => {
    employeeApi.fetchEmployees.mockResolvedValue({
      items: [{ ...employee, allowed_workflow_ids: [workflow.id] }],
      next_cursor: null,
    });
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
      .mockResolvedValueOnce({ items: [employee], next_cursor: null });
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
    employeeApi.fetchEmployees
      .mockResolvedValueOnce({ items: [employee], next_cursor: null })
      .mockResolvedValue({ items: [], next_cursor: null });
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
