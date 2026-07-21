import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { PropsWithChildren } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AuditEventsPage } from "./AuditEventsPage";

const auditApi = vi.hoisted(() => ({
  fetchAuditEvents: vi.fn(),
  fetchAuditIntegrity: vi.fn(),
  fetchAuditPolicy: vi.fn(),
}));

vi.mock("../../api/audit", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/audit")>()),
  ...auditApi,
}));

const event = {
  sequence: 2,
  event_id: "10000000-0000-4000-8000-000000000001",
  tenant_id: "20000000-0000-4000-8000-000000000002",
  actor_user_id: "30000000-0000-4000-8000-000000000003",
  action: "employee.configuration_and_bindings.updated",
  outcome: "succeeded",
  request_id: "40000000-0000-4000-8000-000000000004",
  trace_id: "1234567890abcdef1234567890abcdef",
  resource_type: "employee",
  resource_id: "50000000-0000-4000-8000-000000000005",
  error_code: null,
  occurred_at: "2026-07-21T05:00:00Z",
  retention_until: "2027-07-21T05:00:00Z",
  previous_hash: "0".repeat(64),
  event_hash: "a".repeat(64),
};

function Providers({ children }: PropsWithChildren) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("AuditEventsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    auditApi.fetchAuditEvents.mockResolvedValue({ items: [event], next_cursor: "2" });
    auditApi.fetchAuditIntegrity.mockResolvedValue({
      event_count: 2,
      first_sequence: 1,
      last_sequence: 2,
      last_hash: event.event_hash,
      verified: true,
      broken_sequence: null,
    });
    auditApi.fetchAuditPolicy.mockResolvedValue({
      retention_days: 365,
      max_events_per_scope: 1_000_000,
      automatic_deletion: false,
    });
  });

  it("shows integrity, policy and metadata without request bodies", async () => {
    render(<AuditEventsPage />, { wrapper: Providers });

    expect(await screen.findByRole("heading", { name: "审计与安全事件" })).toBeInTheDocument();
    expect(await screen.findByText("哈希链完整")).toBeInTheDocument();
    expect(screen.getByText(/至少保留 365 天/)).toBeInTheDocument();
    expect(screen.getByText("数字员工配置与绑定已更新")).toBeInTheDocument();
    expect(screen.getByText(event.resource_id)).toBeInTheDocument();
    expect(screen.queryByText("forbidden request body")).not.toBeInTheDocument();
  });

  it("continues through the append-only sequence cursor", async () => {
    const older = { ...event, sequence: 1, event_id: "60000000-0000-4000-8000-000000000006" };
    auditApi.fetchAuditEvents
      .mockResolvedValueOnce({ items: [event], next_cursor: "2" })
      .mockResolvedValueOnce({ items: [older], next_cursor: null });
    const user = userEvent.setup();
    render(<AuditEventsPage />, { wrapper: Providers });

    await user.click(await screen.findByRole("button", { name: "加载更早事件" }));

    expect(await screen.findByText("#1")).toBeInTheDocument();
    expect(auditApi.fetchAuditEvents).toHaveBeenLastCalledWith({
      cursor: "2",
      limit: 50,
    });
  });

  it("labels an unmatched durable intent for operator reconciliation", async () => {
    auditApi.fetchAuditEvents.mockResolvedValue({
      items: [{ ...event, outcome: "started" }],
      next_cursor: null,
    });
    render(<AuditEventsPage />, { wrapper: Providers });

    expect(await screen.findByText("待核对")).toBeInTheDocument();
  });

  it("queries platform credential events within an explicit time range", async () => {
    const user = userEvent.setup();
    render(<AuditEventsPage />, { wrapper: Providers });

    await user.click(await screen.findByRole("combobox", { name: "审计范围" }));
    await user.click(await screen.findByText("平台安全事件"));
    await user.type(screen.getByLabelText("开始时间"), "2026-07-21T10:00");
    await user.type(screen.getByLabelText("结束时间"), "2026-07-21T11:00");
    await user.click(screen.getByRole("button", { name: /查\s*询/ }));

    expect(auditApi.fetchAuditEvents).toHaveBeenLastCalledWith({
      scope: "platform",
      occurred_from: new Date("2026-07-21T10:00").toISOString(),
      occurred_to: new Date("2026-07-21T11:00").toISOString(),
      cursor: undefined,
      limit: 50,
    });
    expect(auditApi.fetchAuditIntegrity).toHaveBeenLastCalledWith("platform");
  });
});
