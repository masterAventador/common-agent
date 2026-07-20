import { z } from "zod";

import type { HealthResponse, SystemStatusResponse } from "./contracts";
import { apiClient } from "./client";
import { toApiClientError } from "./errors";

export { ApiClientError, toApiClientError } from "./errors";

const healthResponseSchema = z.strictObject({
  status: z.literal("ok"),
  service: z.literal("common-agent-api"),
  version: z.string().min(1),
  integration_mode: z.enum(["real", "demo"]),
});

const systemStatusResponseSchema = z.strictObject({
  backend: z.literal("available"),
  service: z.literal("common-agent-api"),
  version: z.string().min(1),
  integration_mode: z.enum(["real", "demo"]),
  model: z.strictObject({
    provider: z.string().min(1),
    status: z.enum(["configured", "demo"]),
  }),
  knowledge: z.strictObject({
    provider: z.string().min(1),
    availability: z.enum(["not_configured", "available", "unavailable"]),
    version: z.string().min(1).nullable(),
    error_code: z.string().min(1).nullable(),
  }),
});

export function parseHealthResponse(data: unknown): HealthResponse {
  return healthResponseSchema.parse(data);
}

export function parseSystemStatusResponse(data: unknown): SystemStatusResponse {
  return systemStatusResponseSchema.parse(data);
}

export async function fetchHealth(): Promise<HealthResponse> {
  try {
    const response = await apiClient.get<unknown>("/system/health");
    return parseHealthResponse(response.data);
  } catch (error) {
    throw toApiClientError(error);
  }
}

export async function fetchSystemStatus(): Promise<SystemStatusResponse> {
  try {
    const response = await apiClient.get<unknown>("/system/status");
    return parseSystemStatusResponse(response.data);
  } catch (error) {
    throw toApiClientError(error);
  }
}
