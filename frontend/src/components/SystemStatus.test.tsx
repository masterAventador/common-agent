import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { fetchSystemStatus } from "../api/system";
import { SystemStatus } from "./SystemStatus";

vi.mock("../api/system", () => ({
  fetchSystemStatus: vi.fn(),
}));

function renderStatus() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <SystemStatus />
    </QueryClientProvider>,
  );
}

describe("SystemStatus", () => {
  beforeEach(() => {
    vi.mocked(fetchSystemStatus).mockReset();
  });

  it("shows backend, configured Bailian and live RAGFlow separately", async () => {
    vi.mocked(fetchSystemStatus).mockResolvedValue({
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
    });

    renderStatus();

    expect(await screen.findByText("后端正常")).toBeInTheDocument();
    expect(screen.getByText("百炼已配置")).toBeInTheDocument();
    expect(screen.getByText("RAGFlow 正常")).toBeInTheDocument();
  });

  it("shows an explicit demo badge instead of presenting demo dependencies as real", async () => {
    vi.mocked(fetchSystemStatus).mockResolvedValue({
      backend: "available",
      service: "common-agent-api",
      version: "0.1.0",
      integration_mode: "demo",
      model: { provider: "demo", status: "demo" },
      knowledge: {
        provider: "demo",
        availability: "available",
        version: "demo-1",
        error_code: null,
      },
    });

    renderStatus();

    expect(await screen.findByText("演示模式")).toBeInTheDocument();
    expect(screen.getByText("模型演示")).toBeInTheDocument();
    expect(screen.getByText("知识库演示")).toBeInTheDocument();
  });

  it("shows RAGFlow unavailable without marking the configured model unavailable", async () => {
    vi.mocked(fetchSystemStatus).mockResolvedValue({
      backend: "available",
      service: "common-agent-api",
      version: "0.1.0",
      integration_mode: "real",
      model: { provider: "bailian", status: "configured" },
      knowledge: {
        provider: "ragflow",
        availability: "unavailable",
        version: null,
        error_code: "knowledge_service_unavailable",
      },
    });

    renderStatus();

    expect(await screen.findByText("RAGFlow 不可用")).toBeInTheDocument();
    expect(screen.getByText("百炼已配置")).toBeInTheDocument();
  });

  it("shows an actionable unavailable state", async () => {
    vi.mocked(fetchSystemStatus).mockRejectedValue(new Error("connection refused"));

    renderStatus();

    expect(await screen.findByText("后端不可用")).toBeInTheDocument();
  });
});
