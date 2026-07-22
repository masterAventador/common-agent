import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ToolsPage } from "./ToolsPage";

const toolsApi = vi.hoisted(() => ({
  fetchManagedMcpSources: vi.fn(),
  createManagedMcpSource: vi.fn(),
  updateManagedMcpSource: vi.fn(),
  deleteManagedMcpSource: vi.fn(),
  addManagedMcpCapability: vi.fn(),
  updateManagedMcpCapability: vi.fn(),
  deleteManagedMcpCapability: vi.fn(),
  discoverManagedMcpSource: vi.fn(),
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
    toolsApi.fetchManagedMcpSources.mockResolvedValue([source]);
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

  it("keeps every mutation disabled for viewers", async () => {
    renderPage(true);

    expect(await screen.findByRole("button", { name: "新建托管 MCP" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "发现能力 订单系统" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "新增能力 订单系统" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "配置鉴权 订单系统" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "测试调用 查询订单" })).toBeDisabled();
  });
});
