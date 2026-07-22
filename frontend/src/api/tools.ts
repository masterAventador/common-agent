import { z } from "zod";

import { apiClient } from "./client";
import { toApiClientError } from "./errors";
import type { components } from "./generated/schema";

export type ManagedMcpSource = components["schemas"]["ManagedHttpSourceResponse"];
export type ManagedMcpSourceInput = components["schemas"]["ManagedHttpSourceBody"];
export type ManagedMcpCapability =
  components["schemas"]["ManagedHttpCapabilityResponse"];
export type ManagedMcpCapabilityInput =
  components["schemas"]["ManagedHttpCapabilityBody"];
export type ManagedMcpParameterBinding =
  components["schemas"]["ManagedHttpParameterBindingBody"];
export type ManagedMcpDiscovery =
  components["schemas"]["ManagedHttpDiscoveryResponse"];
export type ManagedMcpTestCall =
  components["schemas"]["ManagedHttpTestCallResponse"];
export type ManagedMcpOpenApiDraft =
  components["schemas"]["ManagedHttpOpenApiDraftResponse"];
export type ManagedMcpOpenApiPreview =
  components["schemas"]["ManagedHttpOpenApiPreviewResponse"];
export type McpCredentialSummary =
  components["schemas"]["McpCredentialSummaryResponse"];
export type McpCredentialUpdate = components["schemas"]["McpCredentialUpdateBody"];

const jsonObjectSchema = z.record(z.string(), z.unknown());
const parameterLocationSchema = z.enum(["path", "query", "header", "cookie", "body"]);
const bindingSchema = z.strictObject({
  argument_name: z.string().min(1).max(128),
  location: parameterLocationSchema,
  target_name: z.string().min(1).max(128),
});
const capabilitySchema = z.strictObject({
  id: z.uuid(),
  source_id: z.uuid(),
  remote_name: z.string().min(1).max(128),
  display_name: z.string().min(1).max(128),
  description: z.string().min(1).max(1_000),
  input_schema: jsonObjectSchema,
  schema_fingerprint: z.string().regex(/^[0-9a-f]{64}$/),
  method: z.enum(["GET", "POST", "PUT", "PATCH", "DELETE"]),
  path_template: z.string().startsWith("/").max(2_048),
  parameter_bindings: z.array(bindingSchema).max(256),
  timeout_seconds: z.number().int().min(1).max(300),
  response_json_pointer: z.string().startsWith("/").max(1_024).nullable(),
  enabled: z.boolean(),
  created_at: z.iso.datetime({ offset: true }),
  updated_at: z.iso.datetime({ offset: true }),
});
const capabilityInputSchema = z.strictObject({
  remote_name: z.string().min(1).max(128),
  display_name: z.string().min(1).max(128),
  description: z.string().min(1).max(1_000),
  input_schema: jsonObjectSchema,
  method: z.enum(["GET", "POST", "PUT", "PATCH", "DELETE"]),
  path_template: z.string().startsWith("/").max(2_048),
  parameter_bindings: z.array(bindingSchema).max(256),
  timeout_seconds: z.number().int().min(1).max(300),
  response_json_pointer: z.string().startsWith("/").max(1_024).nullable(),
  enabled: z.boolean(),
});
const sourceSchema = z.strictObject({
  id: z.uuid(),
  name: z.string().min(1).max(128),
  description: z.string().max(1_000),
  base_url: z.url({ protocol: /^https?$/ }),
  enabled: z.boolean(),
  capabilities: z.array(capabilitySchema),
  created_at: z.iso.datetime({ offset: true }),
  updated_at: z.iso.datetime({ offset: true }),
});
const sourceListSchema = z.strictObject({ items: z.array(sourceSchema) });
const discoveredToolSchema = z.strictObject({
  capability_id: z.uuid(),
  name: z.string().min(1),
  display_name: z.string().min(1),
  description: z.string(),
  input_schema: jsonObjectSchema,
  schema_fingerprint: z.string().regex(/^[0-9a-f]{64}$/),
});
const discoverySchema = z.strictObject({
  source_id: z.uuid(),
  tools: z.array(discoveredToolSchema),
});
const testCallSchema = z.strictObject({
  capability_id: z.uuid(),
  output: jsonObjectSchema,
});
const credentialSchema = z.strictObject({
  source_id: z.uuid(),
  configured: z.boolean(),
  credential: z
    .strictObject({
      kind: z.enum(["bearer", "custom_headers"]),
      bearer_token: z.string().nullable(),
      headers: z.record(z.string(), z.string()),
    })
    .nullable(),
  updated_at: z.iso.datetime({ offset: true }).nullable(),
});
const openApiDraftSchema = capabilityInputSchema.extend({
  operation_key: z.string().min(1).max(2_064),
  issues: z.array(z.string().min(1).max(1_000)),
});
const openApiPreviewSchema = z.strictObject({
  title: z.string().min(1).max(256),
  version: z.string().max(128),
  drafts: z.array(openApiDraftSchema).min(1).max(200),
  existing_remote_names: z.array(z.string().min(1).max(128)),
});
const openApiImportSchema = z.strictObject({ items: z.array(capabilitySchema).min(1).max(200) });

export function parseManagedMcpSource(data: unknown): ManagedMcpSource {
  return sourceSchema.parse(data);
}

export function parseManagedMcpCapabilityInput(
  data: unknown,
): ManagedMcpCapabilityInput {
  return capabilityInputSchema.parse(data);
}

export async function fetchManagedMcpSources(): Promise<ManagedMcpSource[]> {
  try {
    const response = await apiClient.get<unknown>("/managed-mcp-sources");
    return sourceListSchema.parse(response.data).items;
  } catch (error) {
    throw toApiClientError(error);
  }
}

export async function createManagedMcpSource(
  input: ManagedMcpSourceInput,
): Promise<ManagedMcpSource> {
  try {
    const response = await apiClient.post<unknown>("/managed-mcp-sources", input);
    return parseManagedMcpSource(response.data);
  } catch (error) {
    throw toApiClientError(error);
  }
}

export async function updateManagedMcpSource(
  sourceId: string,
  input: ManagedMcpSourceInput,
): Promise<ManagedMcpSource> {
  try {
    const response = await apiClient.put<unknown>(
      `/managed-mcp-sources/${encodeURIComponent(sourceId)}`,
      input,
    );
    return parseManagedMcpSource(response.data);
  } catch (error) {
    throw toApiClientError(error);
  }
}

export async function deleteManagedMcpSource(sourceId: string): Promise<void> {
  try {
    await apiClient.delete(`/managed-mcp-sources/${encodeURIComponent(sourceId)}`);
  } catch (error) {
    throw toApiClientError(error);
  }
}

export async function addManagedMcpCapability(
  sourceId: string,
  input: ManagedMcpCapabilityInput,
): Promise<ManagedMcpCapability> {
  try {
    const response = await apiClient.post<unknown>(
      `/managed-mcp-sources/${encodeURIComponent(sourceId)}/capabilities`,
      input,
    );
    return capabilitySchema.parse(response.data);
  } catch (error) {
    throw toApiClientError(error);
  }
}

export async function updateManagedMcpCapability(
  sourceId: string,
  capabilityId: string,
  input: ManagedMcpCapabilityInput,
): Promise<ManagedMcpCapability> {
  try {
    const response = await apiClient.put<unknown>(
      `/managed-mcp-sources/${encodeURIComponent(sourceId)}/capabilities/` +
        encodeURIComponent(capabilityId),
      input,
    );
    return capabilitySchema.parse(response.data);
  } catch (error) {
    throw toApiClientError(error);
  }
}

export async function deleteManagedMcpCapability(
  sourceId: string,
  capabilityId: string,
): Promise<void> {
  try {
    await apiClient.delete(
      `/managed-mcp-sources/${encodeURIComponent(sourceId)}/capabilities/` +
        encodeURIComponent(capabilityId),
    );
  } catch (error) {
    throw toApiClientError(error);
  }
}

export async function discoverManagedMcpSource(
  sourceId: string,
): Promise<ManagedMcpDiscovery> {
  try {
    const response = await apiClient.post<unknown>(
      `/managed-mcp-sources/${encodeURIComponent(sourceId)}/discover`,
    );
    return discoverySchema.parse(response.data);
  } catch (error) {
    throw toApiClientError(error);
  }
}

export async function testManagedMcpCapability(
  sourceId: string,
  capabilityId: string,
  argumentsValue: Record<string, unknown>,
): Promise<ManagedMcpTestCall> {
  try {
    const response = await apiClient.post<unknown>(
      `/managed-mcp-sources/${encodeURIComponent(sourceId)}/capabilities/` +
        `${encodeURIComponent(capabilityId)}/test-call`,
      { arguments: argumentsValue },
    );
    return testCallSchema.parse(response.data);
  } catch (error) {
    throw toApiClientError(error);
  }
}

export async function previewManagedMcpOpenApi(
  sourceId: string,
  file: File,
): Promise<ManagedMcpOpenApiPreview> {
  const body = new FormData();
  body.append("file", file);
  try {
    const response = await apiClient.post<unknown>(
      `/managed-mcp-sources/${encodeURIComponent(sourceId)}/openapi/preview`,
      body,
    );
    return openApiPreviewSchema.parse(response.data);
  } catch (error) {
    throw toApiClientError(error);
  }
}

export async function importManagedMcpOpenApi(
  sourceId: string,
  capabilities: ManagedMcpCapabilityInput[],
): Promise<ManagedMcpCapability[]> {
  try {
    const response = await apiClient.post<unknown>(
      `/managed-mcp-sources/${encodeURIComponent(sourceId)}/openapi/import`,
      { capabilities },
    );
    return openApiImportSchema.parse(response.data).items;
  } catch (error) {
    throw toApiClientError(error);
  }
}

export async function fetchMcpCredential(sourceId: string): Promise<McpCredentialSummary> {
  try {
    const response = await apiClient.get<unknown>(
      `/mcp-sources/${encodeURIComponent(sourceId)}/credentials`,
    );
    return credentialSchema.parse(response.data);
  } catch (error) {
    throw toApiClientError(error);
  }
}

export async function updateMcpCredential(
  sourceId: string,
  input: McpCredentialUpdate,
): Promise<McpCredentialSummary> {
  try {
    const response = await apiClient.put<unknown>(
      `/mcp-sources/${encodeURIComponent(sourceId)}/credentials`,
      input,
    );
    return credentialSchema.parse(response.data);
  } catch (error) {
    throw toApiClientError(error);
  }
}
