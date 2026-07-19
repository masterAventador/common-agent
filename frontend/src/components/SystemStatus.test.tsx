import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { fetchHealth } from "../api/system";
import { SystemStatus } from "./SystemStatus";

vi.mock("../api/system", () => ({
  fetchHealth: vi.fn(),
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
    vi.mocked(fetchHealth).mockReset();
  });

  it("shows the real backend as healthy", async () => {
    vi.mocked(fetchHealth).mockResolvedValue({
      status: "ok",
      service: "common-agent-api",
      version: "0.1.0",
      integration_mode: "real",
    });

    renderStatus();

    expect(await screen.findByText("后端正常")).toBeInTheDocument();
  });

  it("shows an explicit demo badge instead of presenting demo dependencies as real", async () => {
    vi.mocked(fetchHealth).mockResolvedValue({
      status: "ok",
      service: "common-agent-api",
      version: "0.1.0",
      integration_mode: "demo",
    });

    renderStatus();

    expect(await screen.findByText("演示模式")).toBeInTheDocument();
    expect(screen.queryByText("后端正常")).not.toBeInTheDocument();
  });

  it("shows an actionable unavailable state", async () => {
    vi.mocked(fetchHealth).mockRejectedValue(new Error("connection refused"));

    renderStatus();

    expect(await screen.findByText("后端不可用")).toBeInTheDocument();
  });
});
