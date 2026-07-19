import { z } from "zod";

import type { HealthResponse } from "./contracts";
import { apiClient } from "./client";
import { toApiClientError } from "./errors";

export { ApiClientError, toApiClientError } from "./errors";

const healthResponseSchema = z.strictObject({
  status: z.literal("ok"),
  service: z.literal("common-agent-api"),
  version: z.string().min(1),
});

export function parseHealthResponse(data: unknown): HealthResponse {
  return healthResponseSchema.parse(data);
}

export async function fetchHealth(): Promise<HealthResponse> {
  try {
    const response = await apiClient.get<unknown>("/system/health");
    return parseHealthResponse(response.data);
  } catch (error) {
    throw toApiClientError(error);
  }
}
