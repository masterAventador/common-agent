import axios from "axios";
import { z } from "zod";

import type { ApiError, HealthResponse } from "./contracts";
import { apiClient } from "./client";

const healthResponseSchema = z.strictObject({
  status: z.literal("ok"),
  service: z.literal("common-agent-api"),
  version: z.string().min(1),
});

const apiErrorSchema = z.strictObject({
  code: z.string().min(1),
  message: z.string().min(1),
  request_id: z.string().min(1),
  retryable: z.boolean(),
});

export class ApiClientError extends Error {
  constructor(
    message: string,
    readonly code: string,
    readonly requestId: string | undefined,
    readonly retryable: boolean,
  ) {
    super(message);
    this.name = "ApiClientError";
  }

  toJSON() {
    return {
      code: this.code,
      message: this.message,
      requestId: this.requestId,
      retryable: this.retryable,
    };
  }
}

export function parseHealthResponse(data: unknown): HealthResponse {
  return healthResponseSchema.parse(data);
}

export function toApiClientError(error: unknown): ApiClientError {
  if (axios.isAxiosError(error)) {
    const parsed = apiErrorSchema.safeParse(error.response?.data);
    if (parsed.success) {
      const envelope: ApiError = parsed.data;
      return new ApiClientError(
        envelope.message,
        envelope.code,
        envelope.request_id,
        envelope.retryable,
      );
    }
  }

  return new ApiClientError("无法连接后端服务", "network_error", undefined, true);
}

export async function fetchHealth(): Promise<HealthResponse> {
  try {
    const response = await apiClient.get<unknown>("/system/health");
    return parseHealthResponse(response.data);
  } catch (error) {
    throw toApiClientError(error);
  }
}
