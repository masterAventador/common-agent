import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "./client";
import {
  addManagedMcpCapability,
  createExternalMcpSource,
  createManagedMcpSource,
  createToolCollection,
  deleteExternalMcpSource,
  deleteManagedMcpCapability,
  deleteManagedMcpSource,
  deleteToolCollection,
  discoverManagedMcpSource,
  fetchExternalMcpSources,
  fetchConversationToolGrants,
  fetchEmployeeToolGrants,
  fetchManagedMcpSources,
  fetchMcpCredential,
  fetchToolCatalog,
  importManagedMcpOpenApi,
  parseManagedMcpCapabilityInput,
  parseManagedMcpSource,
  previewManagedMcpOpenApi,
  syncExternalMcpSource,
  testExternalMcpCapability,
  testManagedMcpCapability,
  updateExternalMcpSource,
  replaceConversationToolGrants,
  replaceEmployeeToolGrants,
  updateManagedMcpSource,
  updateManagedMcpCapability,
  updateMcpCredential,
  updateToolCollection,
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

const externalCapability = {
  id: "30000000-0000-4000-8000-000000000003",
  source_id: "40000000-0000-4000-8000-000000000004",
  remote_name: "partners.lookup",
  display_name: "查询合作方",
  description: "按编号查询合作方。",
  input_schema: { type: "object", properties: {}, additionalProperties: false },
  schema_fingerprint: "b".repeat(64),
  status: "active" as const,
  created_at: "2026-07-22T04:00:00Z",
  updated_at: "2026-07-22T04:00:00Z",
};

const externalSource = {
  id: externalCapability.source_id,
  name: "合作方 MCP",
  description: "第三方 Streamable HTTP 服务",
  endpoint_url: "https://mcp.partner.example/mcp",
  status: "ready" as const,
  capabilities: [externalCapability],
  created_at: "2026-07-22T04:00:00Z",
  updated_at: "2026-07-22T04:00:00Z",
};

const collection = {
  id: "50000000-0000-4000-8000-000000000005",
  name: "订单与合作方",
  description: "聚合两个 MCP 来源",
  source_ids: [source.id, externalSource.id],
  created_at: "2026-07-22T05:00:00Z",
  updated_at: "2026-07-22T05:00:00Z",
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

  it("uploads OpenAPI as multipart and strictly parses preview and batch import results", async () => {
    const draft = {
      operation_key: "GET /orders/{order_id}",
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
      issues: [],
    };
    const preview = {
      title: "订单业务",
      version: "1.0.0",
      drafts: [draft],
      existing_remote_names: [],
    };
    vi.mocked(apiClient.post)
      .mockResolvedValueOnce({ data: preview })
      .mockResolvedValueOnce({ data: { items: [capability] } });
    const file = new File(["{}"], "orders.openapi.json", { type: "application/json" });

    await expect(previewManagedMcpOpenApi(source.id, file)).resolves.toEqual(preview);
    await expect(
      importManagedMcpOpenApi(source.id, [
        {
          remote_name: draft.remote_name,
          display_name: draft.display_name,
          description: draft.description,
          input_schema: draft.input_schema,
          method: draft.method,
          path_template: draft.path_template,
          parameter_bindings: draft.parameter_bindings,
          timeout_seconds: draft.timeout_seconds,
          response_json_pointer: draft.response_json_pointer,
          enabled: draft.enabled,
        },
      ]),
    ).resolves.toEqual([capability]);

    expect(apiClient.post).toHaveBeenNthCalledWith(
      1,
      `/managed-mcp-sources/${source.id}/openapi/preview`,
      expect.any(FormData),
    );
    const form = vi.mocked(apiClient.post).mock.calls[0][1];
    expect(form).toBeInstanceOf(FormData);
    expect((form as FormData).get("file")).toBe(file);
    expect(apiClient.post).toHaveBeenNthCalledWith(
      2,
      `/managed-mcp-sources/${source.id}/openapi/import`,
      { capabilities: [expect.objectContaining({ remote_name: capability.remote_name })] },
    );
  });

  it("validates capability input and encodes remaining managed CRUD paths", async () => {
    const input = {
      remote_name: capability.remote_name,
      display_name: capability.display_name,
      description: capability.description,
      input_schema: capability.input_schema,
      method: capability.method,
      path_template: capability.path_template,
      parameter_bindings: capability.parameter_bindings,
      timeout_seconds: capability.timeout_seconds,
      response_json_pointer: capability.response_json_pointer,
      enabled: capability.enabled,
    };
    vi.mocked(apiClient.put).mockResolvedValueOnce({ data: source });
    vi.mocked(apiClient.post).mockResolvedValueOnce({ data: capability });

    expect(parseManagedMcpCapabilityInput(input)).toEqual(input);
    expect(() => parseManagedMcpCapabilityInput({ ...input, authorization: "secret" })).toThrow();
    await expect(
      updateManagedMcpSource("source/id", {
        name: source.name,
        description: source.description,
        base_url: source.base_url,
        enabled: source.enabled,
      }),
    ).resolves.toEqual(source);
    await expect(addManagedMcpCapability("source/id", input)).resolves.toEqual(capability);

    expect(apiClient.put).toHaveBeenCalledWith("/managed-mcp-sources/source%2Fid", {
      name: source.name,
      description: source.description,
      base_url: source.base_url,
      enabled: source.enabled,
    });
    expect(apiClient.post).toHaveBeenCalledWith(
      "/managed-mcp-sources/source%2Fid/capabilities",
      input,
    );
  });
});

describe("external MCP and tool collection API boundary", () => {
  beforeEach(() => vi.clearAllMocks());

  it("uses explicit external sync and stable catalog endpoints", async () => {
    const sync = {
      source: externalSource,
      added: 1,
      updated: 0,
      schema_changed: 0,
      removed: 0,
      reactivated: 0,
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
      capabilities: [externalCapability],
      collections: [collection],
    };
    vi.mocked(apiClient.get)
      .mockResolvedValueOnce({ data: { items: [externalSource] } })
      .mockResolvedValueOnce({ data: catalog });
    vi.mocked(apiClient.post)
      .mockResolvedValueOnce({ data: externalSource })
      .mockResolvedValueOnce({ data: sync })
      .mockResolvedValueOnce({
        data: { capability_id: externalCapability.id, output: { id: "P-1" } },
      })
      .mockResolvedValueOnce({ data: collection });
    vi.mocked(apiClient.put)
      .mockResolvedValueOnce({ data: externalSource })
      .mockResolvedValueOnce({ data: collection });
    vi.mocked(apiClient.delete).mockResolvedValue({ data: undefined });

    const sourceInput = {
      name: externalSource.name,
      description: externalSource.description,
      endpoint_url: externalSource.endpoint_url,
    };
    const collectionInput = {
      name: collection.name,
      description: collection.description,
      source_ids: collection.source_ids,
    };
    await expect(fetchExternalMcpSources()).resolves.toEqual([externalSource]);
    await expect(createExternalMcpSource(sourceInput)).resolves.toEqual(externalSource);
    await expect(updateExternalMcpSource(externalSource.id, sourceInput)).resolves.toEqual(
      externalSource,
    );
    await expect(syncExternalMcpSource(externalSource.id)).resolves.toEqual(sync);
    await expect(
      testExternalMcpCapability(externalSource.id, externalCapability.id, { id: "P-1" }),
    ).resolves.toEqual({ capability_id: externalCapability.id, output: { id: "P-1" } });
    await expect(fetchToolCatalog()).resolves.toEqual(catalog);
    await expect(createToolCollection(collectionInput)).resolves.toEqual(collection);
    await expect(updateToolCollection(collection.id, collectionInput)).resolves.toEqual(
      collection,
    );
    await deleteToolCollection(collection.id);
    await deleteExternalMcpSource(externalSource.id);

    expect(apiClient.post).toHaveBeenNthCalledWith(
      2,
      `/external-mcp-sources/${externalSource.id}/sync`,
    );
    expect(apiClient.post).toHaveBeenNthCalledWith(
      3,
      `/external-mcp-sources/${externalSource.id}/capabilities/${externalCapability.id}/test-call`,
      { arguments: { id: "P-1" } },
    );
    expect(apiClient.get).toHaveBeenNthCalledWith(2, "/tool-catalog");
    expect(apiClient.delete).toHaveBeenNthCalledWith(
      1,
      `/tool-collections/${collection.id}`,
    );
  });

  it("rejects leaked external credentials and unknown catalog fields", async () => {
    vi.mocked(apiClient.get)
      .mockResolvedValueOnce({
        data: { items: [{ ...externalSource, bearer_token: "secret" }] },
      })
      .mockResolvedValueOnce({
        data: { sources: [], capabilities: [], collections: [], unexpected: true },
      });

    await expect(fetchExternalMcpSources()).rejects.toBeDefined();
    await expect(fetchToolCatalog()).rejects.toBeDefined();
  });

  it("reads and replaces strict employee and conversation grant snapshots", async () => {
    const employeeId = "60000000-0000-4000-8000-000000000006";
    const conversationId = "70000000-0000-4000-8000-000000000007";
    const selection = {
      collection_ids: [collection.id],
      capability_ids: [externalCapability.id],
    };
    const employeeGrant = {
      target_type: "employee" as const,
      target_id: employeeId,
      ...selection,
    };
    const conversationGrant = {
      target_type: "conversation" as const,
      target_id: conversationId,
      ...selection,
    };
    vi.mocked(apiClient.get)
      .mockResolvedValueOnce({ data: employeeGrant })
      .mockResolvedValueOnce({ data: conversationGrant });
    vi.mocked(apiClient.put)
      .mockResolvedValueOnce({ data: employeeGrant })
      .mockResolvedValueOnce({ data: conversationGrant });

    await expect(fetchEmployeeToolGrants(employeeId)).resolves.toEqual(employeeGrant);
    await expect(replaceEmployeeToolGrants(employeeId, selection)).resolves.toEqual(
      employeeGrant,
    );
    await expect(fetchConversationToolGrants(conversationId)).resolves.toEqual(
      conversationGrant,
    );
    await expect(
      replaceConversationToolGrants(conversationId, selection),
    ).resolves.toEqual(conversationGrant);

    expect(apiClient.put).toHaveBeenNthCalledWith(
      1,
      `/employees/${employeeId}/tool-grants`,
      selection,
    );
    expect(apiClient.put).toHaveBeenNthCalledWith(
      2,
      `/conversations/${conversationId}/tool-grants`,
      selection,
    );
  });

  it("normalizes transport failures for every tool API operation", async () => {
    const failure = new Error("offline");
    vi.mocked(apiClient.get).mockRejectedValue(failure);
    vi.mocked(apiClient.post).mockRejectedValue(failure);
    vi.mocked(apiClient.put).mockRejectedValue(failure);
    vi.mocked(apiClient.delete).mockRejectedValue(failure);
    const managedInput = {
      name: source.name,
      description: source.description,
      base_url: source.base_url,
      enabled: source.enabled,
    };
    const capabilityInput = {
      remote_name: capability.remote_name,
      display_name: capability.display_name,
      description: capability.description,
      input_schema: capability.input_schema,
      method: capability.method,
      path_template: capability.path_template,
      parameter_bindings: capability.parameter_bindings,
      timeout_seconds: capability.timeout_seconds,
      response_json_pointer: capability.response_json_pointer,
      enabled: capability.enabled,
    };
    const externalInput = {
      name: externalSource.name,
      description: externalSource.description,
      endpoint_url: externalSource.endpoint_url,
    };
    const collectionInput = {
      name: collection.name,
      description: collection.description,
      source_ids: collection.source_ids,
    };
    const selection = {
      collection_ids: [collection.id],
      capability_ids: [externalCapability.id],
    };
    const file = new File(["{}"], "api.json", { type: "application/json" });
    const operations = [
      () => fetchManagedMcpSources(),
      () => createManagedMcpSource(managedInput),
      () => updateManagedMcpSource(source.id, managedInput),
      () => deleteManagedMcpSource(source.id),
      () => addManagedMcpCapability(source.id, capabilityInput),
      () => updateManagedMcpCapability(source.id, capability.id, capabilityInput),
      () => deleteManagedMcpCapability(source.id, capability.id),
      () => discoverManagedMcpSource(source.id),
      () => testManagedMcpCapability(source.id, capability.id, {}),
      () => previewManagedMcpOpenApi(source.id, file),
      () => importManagedMcpOpenApi(source.id, [capabilityInput]),
      () => fetchMcpCredential(source.id),
      () => updateMcpCredential(source.id, { action: "clear" }),
      () => fetchExternalMcpSources(),
      () => createExternalMcpSource(externalInput),
      () => updateExternalMcpSource(externalSource.id, externalInput),
      () => deleteExternalMcpSource(externalSource.id),
      () => syncExternalMcpSource(externalSource.id),
      () => testExternalMcpCapability(externalSource.id, externalCapability.id, {}),
      () => fetchToolCatalog(),
      () => createToolCollection(collectionInput),
      () => updateToolCollection(collection.id, collectionInput),
      () => deleteToolCollection(collection.id),
      () => fetchEmployeeToolGrants("employee/id"),
      () => replaceEmployeeToolGrants("employee/id", selection),
      () => fetchConversationToolGrants("conversation/id"),
      () => replaceConversationToolGrants("conversation/id", selection),
    ];

    for (const operation of operations) {
      await expect(operation()).rejects.toBeDefined();
    }
  });
});
