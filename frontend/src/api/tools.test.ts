import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "./client";
import {
  createManagedMcpSource,
  deleteManagedMcpCapability,
  deleteManagedMcpSource,
  discoverManagedMcpSource,
  fetchManagedMcpSources,
  fetchMcpCredential,
  parseManagedMcpSource,
  testManagedMcpCapability,
  updateManagedMcpCapability,
  updateMcpCredential,
} from "./tools";

vi.mock("./client", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}));

const capability = {
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
    { argument_name: "order_id", location: "path" as const, target_name: "order_id" },
  ],
  timeout_seconds: 10,
  response_json_pointer: "/data/order",
  enabled: true,
  created_at: "2026-07-22T02:00:00Z",
  updated_at: "2026-07-22T02:00:00Z",
};

const source = {
  id: capability.source_id,
  name: "订单系统",
  description: "业务订单接口",
  base_url: "https://business.example/api",
  enabled: true,
  capabilities: [capability],
  created_at: "2026-07-22T02:00:00Z",
  updated_at: "2026-07-22T02:00:00Z",
};

describe("managed MCP API boundary", () => {
  beforeEach(() => vi.clearAllMocks());

  it("accepts strict managed source data and rejects credential leakage", () => {
    expect(parseManagedMcpSource(source)).toEqual(source);
    expect(() => parseManagedMcpSource({ ...source, bearer_token: "secret" })).toThrow();
    expect(() =>
      parseManagedMcpSource({
        ...source,
        capabilities: [{ ...capability, location: "formData" }],
      }),
    ).toThrow();
  });

  it("uses only formal CRUD, credential, discovery and test-call endpoints", async () => {
    const discovery = {
      source_id: source.id,
      tools: [
        {
          capability_id: capability.id,
          name: capability.remote_name,
          display_name: capability.display_name,
          description: capability.description,
          input_schema: capability.input_schema,
          schema_fingerprint: capability.schema_fingerprint,
        },
      ],
    };
    const credential = {
      source_id: source.id,
      configured: true,
      credential: { kind: "bearer", bearer_token: "********", headers: {} },
      updated_at: "2026-07-22T03:00:00Z",
    };
    vi.mocked(apiClient.get)
      .mockResolvedValueOnce({ data: { items: [source] } })
      .mockResolvedValueOnce({ data: credential });
    vi.mocked(apiClient.post)
      .mockResolvedValueOnce({ data: source })
      .mockResolvedValueOnce({ data: discovery })
      .mockResolvedValueOnce({ data: { capability_id: capability.id, output: { id: "A-100" } } });
    vi.mocked(apiClient.put)
      .mockResolvedValueOnce({ data: capability })
      .mockResolvedValueOnce({ data: credential });
    vi.mocked(apiClient.delete).mockResolvedValue({ data: undefined });

    await expect(fetchManagedMcpSources()).resolves.toEqual([source]);
    await expect(
      createManagedMcpSource({
        name: source.name,
        description: source.description,
        base_url: source.base_url,
        enabled: true,
      }),
    ).resolves.toEqual(source);
    await expect(
      updateManagedMcpCapability(source.id, capability.id, {
        remote_name: capability.remote_name,
        display_name: capability.display_name,
        description: capability.description,
        input_schema: capability.input_schema,
        method: capability.method,
        path_template: capability.path_template,
        parameter_bindings: capability.parameter_bindings,
        timeout_seconds: capability.timeout_seconds,
        response_json_pointer: capability.response_json_pointer,
        enabled: true,
      }),
    ).resolves.toEqual(capability);
    await expect(fetchMcpCredential(source.id)).resolves.toEqual(credential);
    await expect(
      updateMcpCredential(source.id, {
        action: "replace",
        kind: "bearer",
        bearer_token: "new-secret",
        headers: null,
      }),
    ).resolves.toEqual(credential);
    await expect(discoverManagedMcpSource(source.id)).resolves.toEqual(discovery);
    await expect(
      testManagedMcpCapability(source.id, capability.id, { order_id: "A-100" }),
    ).resolves.toEqual({ capability_id: capability.id, output: { id: "A-100" } });
    await deleteManagedMcpCapability(source.id, capability.id);
    await deleteManagedMcpSource(source.id);

    expect(apiClient.get).toHaveBeenNthCalledWith(1, "/managed-mcp-sources");
    expect(apiClient.get).toHaveBeenNthCalledWith(
      2,
      `/mcp-sources/${source.id}/credentials`,
    );
    expect(apiClient.post).toHaveBeenNthCalledWith(2, `/managed-mcp-sources/${source.id}/discover`);
    expect(apiClient.post).toHaveBeenNthCalledWith(
      3,
      `/managed-mcp-sources/${source.id}/capabilities/${capability.id}/test-call`,
      { arguments: { order_id: "A-100" } },
    );
  });
});
