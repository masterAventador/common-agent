import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ToolsPage } from "./ToolsPage";

const toolsApi = vi.hoisted(() => ({
  fetchManagedMcpSources: vi.fn(),
  fetchExternalMcpSources: vi.fn(),
  fetchToolCatalog: vi.fn(),
  createManagedMcpSource: vi.fn(),
  createExternalMcpSource: vi.fn(),
  updateExternalMcpSource: vi.fn(),
  deleteExternalMcpSource: vi.fn(),
  syncExternalMcpSource: vi.fn(),
  testExternalMcpCapability: vi.fn(),
  createToolCollection: vi.fn(),
  updateToolCollection: vi.fn(),
  deleteToolCollection: vi.fn(),
  updateManagedMcpSource: vi.fn(),
  deleteManagedMcpSource: vi.fn(),
  addManagedMcpCapability: vi.fn(),
  updateManagedMcpCapability: vi.fn(),
  deleteManagedMcpCapability: vi.fn(),
  discoverManagedMcpSource: vi.fn(),
  previewManagedMcpOpenApi: vi.fn(),
  importManagedMcpOpenApi: vi.fn(),
  parseManagedMcpCapabilityInput: vi.fn(),
  testManagedMcpCapability: vi.fn(),
  fetchMcpCredential: vi.fn(),
  updateMcpCredential: vi.fn(),
}));

vi.mock("../../api/tools", () => toolsApi);

const source = {
  id: "10000000-0000-4000-8000-000000000001",
  name: "订单系统",
  description: "业务订单接口",
  base_url: "https://business.example/api",
  enabled: true,
  capabilities: [
    {
      id: "20000000-0000-4000-8000-000000000002",
      source_id: "10000000-0000-4000-8000-000000000001",
      remote_name: "orders.get",
      display_name: "查询订单",
      description: "按编号查询订单。",
      input_schema: {
        type: "object",
        properties: { order_id: { type: "string", description: "订单编号" } },
        required: ["order_id"],
        additionalProperties: false,
      },
      schema_fingerprint: "a".repeat(64),
      method: "GET",
      path_template: "/orders/{order_id}",
      parameter_bindings: [
        { argument_name: "order_id", location: "path", target_name: "order_id" },
      ],
      timeout_seconds: 10,
      response_json_pointer: "/data/order",
      enabled: true,
      created_at: "2026-07-22T02:00:00Z",
      updated_at: "2026-07-22T02:00:00Z",
    },
  ],
  created_at: "2026-07-22T02:00:00Z",
  updated_at: "2026-07-22T02:00:00Z",
};

const externalSource = {
  id: "30000000-0000-4000-8000-000000000003",
  name: "合作方 MCP",
  description: "第三方 Streamable HTTP 服务",
  endpoint_url: "https://mcp.partner.example/mcp",
  status: "ready",
  capabilities: [
    {
      id: "40000000-0000-4000-8000-000000000004",
      source_id: "30000000-0000-4000-8000-000000000003",
      remote_name: "partners.lookup",
      display_name: "查询合作方",
      description: "按编号查询合作方。",
      input_schema: { type: "object", properties: {}, additionalProperties: false },
      schema_fingerprint: "b".repeat(64),
      status: "unavailable",
      created_at: "2026-07-22T04:00:00Z",
      updated_at: "2026-07-22T04:00:00Z",
    },
  ],
  created_at: "2026-07-22T04:00:00Z",
  updated_at: "2026-07-22T04:00:00Z",
};

const collection = {
  id: "50000000-0000-4000-8000-000000000005",
  name: "订单与合作方",
  description: "聚合内部和外部 MCP",
  source_ids: [source.id, externalSource.id],
  created_at: "2026-07-22T05:00:00Z",
  updated_at: "2026-07-22T05:00:00Z",
};

const catalog = {
  sources: [
    {
      id: source.id,
      name: source.name,
      description: source.description,
      source_type: "managed_http",
      endpoint_url: source.base_url,
      status: "ready",
      created_at: source.created_at,
      updated_at: source.updated_at,
    },
    {
      id: externalSource.id,
      name: externalSource.name,
      description: externalSource.description,
      source_type: "external",
      endpoint_url: externalSource.endpoint_url,
      status: "ready",
      created_at: externalSource.created_at,
      updated_at: externalSource.updated_at,
    },
  ],
  capabilities: [
    {
      id: source.capabilities[0].id,
      source_id: source.id,
      remote_name: source.capabilities[0].remote_name,
      display_name: source.capabilities[0].display_name,
      description: source.capabilities[0].description,
      input_schema: source.capabilities[0].input_schema,
      schema_fingerprint: source.capabilities[0].schema_fingerprint,
      status: "active",
      created_at: source.capabilities[0].created_at,
      updated_at: source.capabilities[0].updated_at,
    },
    ...externalSource.capabilities,
  ],
  collections: [collection],
};

function renderPage(readOnly = false) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <ToolsPage readOnly={readOnly} />
    </QueryClientProvider>,
  );
}

describe("ToolsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    toolsApi.parseManagedMcpCapabilityInput.mockImplementation((value) => value);
    toolsApi.fetchManagedMcpSources.mockResolvedValue([source]);
    toolsApi.fetchExternalMcpSources.mockResolvedValue([externalSource]);
    toolsApi.fetchToolCatalog.mockResolvedValue(catalog);
    toolsApi.createManagedMcpSource.mockResolvedValue(source);
    toolsApi.discoverManagedMcpSource.mockResolvedValue({
      source_id: source.id,
      tools: source.capabilities.map((capability) => ({
        capability_id: capability.id,
        name: capability.remote_name,
        display_name: capability.display_name,
        description: capability.description,
        input_schema: capability.input_schema,
        schema_fingerprint: capability.schema_fingerprint,
      })),
    });
    toolsApi.fetchMcpCredential.mockResolvedValue({
      source_id: source.id,
      configured: true,
      credential: { kind: "bearer", bearer_token: "********", headers: {} },
      updated_at: "2026-07-22T02:00:00Z",
    });
    toolsApi.updateMcpCredential.mockResolvedValue({
      source_id: source.id,
      configured: true,
      credential: { kind: "bearer", bearer_token: "********", headers: {} },
      updated_at: "2026-07-22T03:00:00Z",
    });
    toolsApi.testManagedMcpCapability.mockResolvedValue({
      capability_id: source.capabilities[0].id,
      output: { id: "A-100" },
    });
    toolsApi.previewManagedMcpOpenApi.mockResolvedValue({
      title: "订单业务",
      version: "1.0.0",
      existing_remote_names: ["orders.get"],
      drafts: [
        {
          operation_key: "GET /orders/{order_id}",
          remote_name: "orders.get",
          display_name: "查询订单",
          description: "按编号查询订单。",
          input_schema: source.capabilities[0].input_schema,
          method: "GET",
          path_template: "/orders/{order_id}",
          parameter_bindings: source.capabilities[0].parameter_bindings,
          timeout_seconds: 30,
          response_json_pointer: null,
          enabled: true,
          issues: [],
        },
        {
          operation_key: "POST /orders",
          remote_name: "orders.create",
          display_name: "创建订单",
          description: "创建新订单。",
          input_schema: {
            type: "object",
            properties: { customer_id: { type: "string", description: "" } },
            required: ["customer_id"],
            additionalProperties: false,
          },
          method: "POST",
          path_template: "/orders",
          parameter_bindings: [
            { argument_name: "customer_id", location: "body", target_name: "customer_id" },
          ],
          timeout_seconds: 30,
          response_json_pointer: null,
          enabled: true,
          issues: ["参数 customer_id 缺少含义"],
        },
      ],
    });
    toolsApi.importManagedMcpOpenApi.mockResolvedValue([]);
    toolsApi.createExternalMcpSource.mockResolvedValue(externalSource);
    toolsApi.updateExternalMcpSource.mockResolvedValue({
      ...externalSource,
      endpoint_url: "https://partner-v2.example/mcp",
      status: "draft",
    });
    toolsApi.updateManagedMcpSource.mockResolvedValue({
      ...source,
      base_url: "https://business-v2.example/api",
    });
    toolsApi.syncExternalMcpSource.mockResolvedValue({
      source: externalSource,
      added: 0,
      updated: 0,
      schema_changed: 1,
      removed: 0,
      reactivated: 0,
    });
    toolsApi.createToolCollection.mockResolvedValue(collection);
  });

  it("shows managed sources, mappings and explicit discovery without credential values", async () => {
    const user = userEvent.setup();
    renderPage();

    expect(await screen.findByRole("heading", { name: "工具与 MCP" })).toBeInTheDocument();
    expect(screen.getByText("订单系统")).toBeInTheDocument();
    expect(screen.getByText("查询订单")).toBeInTheDocument();
    expect(screen.getByText("GET /orders/{order_id}")).toBeInTheDocument();
    expect(screen.queryByText("managed-http-formal-secret")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "发现能力 订单系统" }));
    expect(await screen.findByText("已通过 MCP 发现 1 项启用能力")).toBeInTheDocument();
    expect(toolsApi.discoverManagedMcpSource).toHaveBeenCalledWith(source.id);
  });

  it("creates a source and can replace a bearer credential without echoing it", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: "新建托管 MCP" }));
    const dialog = screen.getByRole("dialog", { name: "新建托管 MCP" });
    await user.type(within(dialog).getByLabelText("名称"), "客户系统");
    await user.type(within(dialog).getByLabelText("Base URL"), "https://crm.example/api");
    await user.click(within(dialog).getByRole("button", { name: /确认创建/ }));
    await waitFor(() =>
      expect(toolsApi.createManagedMcpSource).toHaveBeenCalledWith({
        name: "客户系统",
        description: "",
        base_url: "https://crm.example/api",
        enabled: true,
      }),
    );
    await user.click(screen.getByRole("button", { name: "配置鉴权 订单系统" }));
    expect(await screen.findByText("已配置 Bearer Token；平台不会回显原值。")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Bearer Token"), "new-secret");
    await user.click(screen.getByRole("button", { name: "保存鉴权" }));
    await waitFor(() =>
      expect(toolsApi.updateMcpCredential).toHaveBeenCalledWith(source.id, {
        action: "replace",
        kind: "bearer",
        bearer_token: "new-secret",
        headers: null,
      }),
    );
    expect(screen.queryByDisplayValue("new-secret")).not.toBeInTheDocument();
  });

  it("runs an explicit side-effect warning test call with JSON arguments", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: "测试调用 查询订单" }));
    expect(screen.getByText(/测试调用可能触发真实业务副作用/)).toBeInTheDocument();
    const dialog = screen.getByRole("dialog", { name: "测试调用 · 查询订单" });
    const editor = within(dialog).getByLabelText("调用参数 JSON");
    fireEvent.change(editor, { target: { value: '{"order_id":"A-100"}' } });
    await user.click(within(dialog).getByRole("button", { name: "确认调用" }));

    expect(await screen.findByText('{"id":"A-100"}')).toBeInTheDocument();
    expect(toolsApi.testManagedMcpCapability).toHaveBeenCalledWith(
      source.id,
      source.capabilities[0].id,
      { order_id: "A-100" },
    );
  });

  it("previews, selects, edits and atomically imports an OpenAPI file", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: "导入 OpenAPI 订单系统" }));
    const file = new File(["{}"], "orders.openapi.json", { type: "application/json" });
    await user.upload(screen.getByLabelText("选择 OpenAPI 文件"), file);
    await user.click(screen.getByRole("button", { name: "解析文件" }));

    await waitFor(() =>
      expect(toolsApi.previewManagedMcpOpenApi).toHaveBeenCalledWith(source.id, file),
    );
    expect(await screen.findByText("已解析 2 项接口")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "选择 查询订单" })).not.toBeChecked();
    expect(screen.getByRole("checkbox", { name: "选择 创建订单" })).toBeChecked();
    const schemaEditor = screen.getByLabelText("输入 Schema POST /orders");
    fireEvent.change(schemaEditor, {
      target: {
        value: JSON.stringify({
          type: "object",
          properties: {
            customer_id: { type: "string", description: "客户编号" },
          },
          required: ["customer_id"],
          additionalProperties: false,
        }),
      },
    });
    const importButton = screen.getByRole("button", { name: "导入选中能力" });
    await waitFor(() => expect(importButton).toBeEnabled());
    await user.click(importButton);

    await waitFor(() => expect(toolsApi.importManagedMcpOpenApi).toHaveBeenCalledTimes(1));
    expect(toolsApi.importManagedMcpOpenApi).toHaveBeenCalledWith(source.id, [
      expect.objectContaining({
        remote_name: "orders.create",
        input_schema: expect.objectContaining({
          properties: {
            customer_id: { type: "string", description: "客户编号" },
          },
        }),
      }),
    ]);
  });

  it("keeps every mutation disabled for viewers", async () => {
    renderPage(true);

    expect(await screen.findByRole("button", { name: "新建托管 MCP" })).toBeDisabled();
    expect(await screen.findByText("合作方 MCP")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "发现能力 订单系统" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "新增能力 订单系统" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "导入 OpenAPI 订单系统" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "配置鉴权 订单系统" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "测试调用 查询订单" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "新建外部 MCP" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "同步能力 合作方 MCP" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "新建业务工具集" })).toBeDisabled();
  }, 20_000);

  it("creates external MCP offline and syncs only after an explicit action", async () => {
    const user = userEvent.setup();
    renderPage();

    expect(await screen.findByText("合作方 MCP")).toBeInTheDocument();
    expect(screen.getByText("能力定义已变化，需再次同步确认")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "新建外部 MCP" }));
    const dialog = screen.getByRole("dialog", { name: "新建外部 MCP" });
    await user.type(within(dialog).getByLabelText("名称"), "财务 MCP");
    await user.type(
      within(dialog).getByLabelText("MCP Endpoint"),
      "https://finance.example/mcp",
    );
    await user.click(within(dialog).getByRole("button", { name: "确认创建" }));

    await waitFor(() =>
      expect(toolsApi.createExternalMcpSource).toHaveBeenCalledWith({
        name: "财务 MCP",
        description: "",
        endpoint_url: "https://finance.example/mcp",
      }),
    );
    expect(toolsApi.syncExternalMcpSource).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "同步能力 合作方 MCP" }));
    await waitFor(() =>
      expect(toolsApi.syncExternalMcpSource).toHaveBeenCalledWith(externalSource.id),
    );
    expect(await screen.findByText(/同步完成：新增 0，变化隔离 1/)).toBeInTheDocument();
  });

  it("warns that credentials are cleared when a source endpoint changes", async () => {
    const user = userEvent.setup();
    renderPage();

    await screen.findByText("合作方 MCP");
    await user.click(
      screen.getByRole("button", { name: "编辑外部来源 合作方 MCP" }),
    );
    const externalDialog = screen.getByRole("dialog", { name: "编辑外部 MCP" });
    const endpoint = within(externalDialog).getByLabelText("MCP Endpoint");
    await user.clear(endpoint);
    await user.type(endpoint, "https://partner-v2.example/mcp");
    await user.click(within(externalDialog).getByRole("button", { name: "保存修改" }));

    expect(
      await screen.findByText(/为防止旧凭据泄漏，原鉴权已清除/),
    ).toBeInTheDocument();
  });

  it("creates a collection from existing managed and external sources", async () => {
    const user = userEvent.setup();
    renderPage();

    expect(await screen.findByText("订单与合作方")).toBeInTheDocument();
    expect(screen.getByText("部分可用")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "新建业务工具集" }));
    const dialog = screen.getByRole("dialog", { name: "新建业务工具集" });
    await user.type(within(dialog).getByLabelText("名称"), "核心业务工具");
    await user.click(within(dialog).getByRole("combobox", { name: "MCP 来源" }));
    await user.click(await screen.findByText("订单系统 · 平台托管"));
    await user.click(within(dialog).getByRole("combobox", { name: "MCP 来源" }));
    await user.click(await screen.findByText("合作方 MCP · 外部 MCP"));
    await user.click(within(dialog).getByRole("button", { name: "确认创建" }));

    await waitFor(() =>
      expect(toolsApi.createToolCollection).toHaveBeenCalledWith({
        name: "核心业务工具",
        description: "",
        source_ids: expect.arrayContaining([source.id, externalSource.id]),
      }),
    );
  });
});
