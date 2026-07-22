import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "./client";
import { fetchAuditEvents, fetchAuditIntegrity, fetchAuditPolicy } from "./audit";

vi.mock("./client", () => ({
  apiClient: { get: vi.fn() },
}));

const event = {
  sequence: 7,
  event_id: "10000000-0000-4000-8000-000000000001",
  tenant_id: "20000000-0000-4000-8000-000000000002",
  actor_user_id: "30000000-0000-4000-8000-000000000003",
  action: "tool.grants.updated",
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
} as const;

describe("audit API", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("strictly parses metadata-only events and forwards bounded filters", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      data: { items: [event], next_cursor: "7" },
    });

    await expect(
      fetchAuditEvents({
        scope: "platform",
        actor_user_id: event.actor_user_id,
        resource_type: "employee",
        resource_id: event.resource_id,
        action: event.action,
        limit: 20,
      }),
    ).resolves.toEqual({ items: [event], next_cursor: "7" });
    expect(apiClient.get).toHaveBeenCalledWith("/audit-events", {
      params: {
        scope: "platform",
        actor_user_id: event.actor_user_id,
        resource_type: "employee",
        resource_id: event.resource_id,
        action: event.action,
        limit: 20,
      },
    });

    vi.mocked(apiClient.get).mockResolvedValue({
      data: { items: [{ ...event, body: "forbidden" }], next_cursor: null },
    });
    await expect(fetchAuditEvents()).rejects.toBeDefined();
  });

  it("accepts a durable started intent when completion has not been recorded", async () => {
    const started = { ...event, outcome: "started" };
    vi.mocked(apiClient.get).mockResolvedValue({
      data: { items: [started], next_cursor: null },
    });

    await expect(fetchAuditEvents()).resolves.toEqual({
      items: [started],
      next_cursor: null,
    });
  });

  it("accepts metadata-only MCP credential audit events", async () => {
    const credentialEvent = {
      ...event,
      action: "tool.credentials.updated",
      resource_type: "mcp_source",
    } as const;
    vi.mocked(apiClient.get).mockResolvedValue({
      data: { items: [credentialEvent], next_cursor: null },
    });

    await expect(fetchAuditEvents()).resolves.toEqual({
      items: [credentialEvent],
      next_cursor: null,
    });
  });

  it("loads integrity and the explicit retention/capacity policy", async () => {
    vi.mocked(apiClient.get)
      .mockResolvedValueOnce({
        data: {
          event_count: 7,
          first_sequence: 1,
          last_sequence: 7,
          last_hash: "a".repeat(64),
          verified: true,
          broken_sequence: null,
        },
      })
      .mockResolvedValueOnce({
        data: {
          retention_days: 365,
          max_events_per_scope: 1_000_000,
          automatic_deletion: false,
        },
      });

    await expect(fetchAuditIntegrity("platform")).resolves.toMatchObject({ verified: true });
    expect(apiClient.get).toHaveBeenNthCalledWith(1, "/audit-events/integrity", {
      params: { scope: "platform" },
    });
    await expect(fetchAuditPolicy()).resolves.toEqual({
      retention_days: 365,
      max_events_per_scope: 1_000_000,
      automatic_deletion: false,
    });
  });
});
