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

const routes = [
  ["/chat", "AI 会话"],
  ["/employees", "数字员工"],
  ["/knowledge-bases", "知识库"],
  ["/workflows", "工作流"],
] as const;

describe("App shell", () => {
  it.each(routes)("renders %s as the %s entry", (path, heading) => {
    render(
      <AppProviders>
        <MemoryRouter initialEntries={[path]}>
          <App />
        </MemoryRouter>
      </AppProviders>,
    );

    expect(screen.getByRole("heading", { name: heading })).toBeInTheDocument();
    for (const [, label] of routes) {
      expect(screen.getByRole("link", { name: label })).toBeInTheDocument();
    }
  });

  it("redirects the root entry to chat", () => {
    render(
      <AppProviders>
        <MemoryRouter initialEntries={["/"]}>
          <App />
        </MemoryRouter>
      </AppProviders>,
    );

    expect(screen.getByRole("heading", { name: "AI 会话" })).toBeInTheDocument();
  });
});
