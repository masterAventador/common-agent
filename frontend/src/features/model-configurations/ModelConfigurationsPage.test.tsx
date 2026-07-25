import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { PropsWithChildren } from "react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiClientError } from "../../api/errors";
import { ModelConfigurationsPage } from "./ModelConfigurationsPage";

const modelApi = vi.hoisted(() => ({
  createModelConfiguration: vi.fn(),
  deleteModelConfiguration: vi.fn(),
  fetchModelConfigurations: vi.fn(),
  updateModelConfiguration: vi.fn(),
  verifyModelConfiguration: vi.fn(),
}));

vi.mock("../../api/modelConfigurations", () => modelApi);

const modelConfiguration = {
  id: "10000000-0000-4000-8000-000000000018",
  display_name: "Qwen Plus",
  provider: "bailian" as const,
  model_identifier: "qwen-plus",
  enabled: true,
  streaming_breaks_tool_calls: true,
  created_at: "2026-07-22T02:00:00Z",
  updated_at: "2026-07-22T02:00:00Z",
};

function Providers({ children }: PropsWithChildren) {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

function renderPage(readOnly = false) {
  return render(
    <MemoryRouter>
      <ModelConfigurationsPage readOnly={readOnly} />
    </MemoryRouter>,
    { wrapper: Providers },
  );
}

describe("ModelConfigurationsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    modelApi.fetchModelConfigurations.mockResolvedValue({
      items: [modelConfiguration],
      next_cursor: null,
    });
  });

  it("lists only user-created model configurations with explicit provider and state", async () => {
    renderPage();

    expect(await screen.findByRole("heading", { name: "模型管理" })).toBeInTheDocument();
    expect(screen.getByText("Qwen Plus")).toBeInTheDocument();
    expect(screen.getByText("qwen-plus")).toBeInTheDocument();
    expect(screen.getByText("启用")).toBeInTheDocument();
    // 卡片不再展示「工具调用流」这一行
    expect(screen.queryByText("工具调用流")).not.toBeInTheDocument();
    expect(screen.queryByText("工具调用自动非流式")).not.toBeInTheDocument();
    expect(screen.queryByText("正常流式")).not.toBeInTheDocument();
    expect(screen.queryByText("模型目录")).not.toBeInTheDocument();
  });

  it("guides the identifier field with callable frontier models only", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: "创建模型" }));
    const hint = screen.getByText(/常用/);
    // 引导里不能出现该端点上调不通的 qwen-max，也不能出现已排期下架的 deepseek-v3/r1
    expect(hint.textContent).not.toMatch(/qwen-max/);
    expect(hint.textContent).not.toMatch(/deepseek-v3\b/);
    expect(hint.textContent).not.toMatch(/deepseek-r1/);
    expect(hint.textContent).toMatch(/qwen3\.7-max/);
    expect(hint.textContent).toMatch(/deepseek-v4-pro/);
  });

  it("creates and disables a user model through the formal editor", async () => {
    const disabled = { ...modelConfiguration, enabled: false };
    modelApi.createModelConfiguration.mockResolvedValue(modelConfiguration);
    modelApi.updateModelConfiguration.mockResolvedValue(disabled);
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: "创建模型" }));
    await user.type(screen.getByRole("textbox", { name: "显示名称" }), "Qwen 3.7 Max");
    await user.type(screen.getByRole("textbox", { name: "模型标识" }), "qwen3.7-max");
    await user.click(screen.getByRole("button", { name: "确认创建" }));

    await waitFor(() =>
      expect(modelApi.createModelConfiguration).toHaveBeenCalledWith({
        display_name: "Qwen 3.7 Max",
        model_identifier: "qwen3.7-max",
        enabled: true,
      }),
    );

    await user.click(screen.getByRole("button", { name: "编辑 Qwen Plus" }));
    await user.click(screen.getByRole("switch", { name: "启用状态" }));
    await user.click(screen.getByRole("button", { name: "保存修改" }));
    await waitFor(() =>
      expect(modelApi.updateModelConfiguration).toHaveBeenCalledWith(
        modelConfiguration.id,
        {
          display_name: "Qwen Plus",
          model_identifier: "qwen-plus",
          enabled: false,
        },
      ),
    );
  });

  it("verifies the selected model through the platform-owned Bailian credential", async () => {
    modelApi.verifyModelConfiguration.mockResolvedValue({
      status: "available",
      model_identifier: "qwen-plus",
      response_preview: "连接成功",
    });
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: "测试调用 Qwen Plus" }));

    expect(modelApi.verifyModelConfiguration).toHaveBeenCalledWith(modelConfiguration.id);
    expect(await screen.findByText("模型调用成功")).toBeInTheDocument();
  });

  it("keeps an in-use configuration visible and explains the blocker", async () => {
    modelApi.deleteModelConfiguration.mockRejectedValue(
      new ApiClientError(
        "模型仍被数字员工或工作流引用。请先解除引用",
        "model_configuration_in_use",
        "request-1",
        false,
      ),
    );
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: "删除模型 Qwen Plus" }));
    await user.click(screen.getByRole("button", { name: "确认删除模型 Qwen Plus" }));

    expect(
      await screen.findByText("该模型仍被数字员工或工作流引用，请先解除引用。"),
    ).toBeInTheDocument();
    expect(screen.getByText("Qwen Plus")).toBeInTheDocument();
  });

  it("disables every POST or mutation entry for a viewer workspace", async () => {
    renderPage(true);

    expect(await screen.findByRole("button", { name: "创建模型" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "测试调用 Qwen Plus" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "编辑 Qwen Plus" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "删除模型 Qwen Plus" })).toBeDisabled();
  });
});
