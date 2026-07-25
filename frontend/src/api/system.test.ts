import { AxiosError, type AxiosResponse } from "axios";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "./client";
import { toApiClientError } from "./errors";
import { fetchHealth, parseHealthResponse } from "./system";

vi.mock("./client", () => ({ apiClient: { get: vi.fn() } }));

describe("system API boundary", () => {
  beforeEach(() => vi.clearAllMocks());

  it("accepts the generated health contract", () => {
    expect(
      parseHealthResponse({
        status: "ok",
        service: "common-agent-api",
        version: "0.1.0",
        integration_mode: "demo",
      }),
    ).toEqual({
      status: "ok",
      service: "common-agent-api",
      version: "0.1.0",
      integration_mode: "demo",
    });
  });

  it("rejects response schema drift", () => {
    expect(() =>
      parseHealthResponse({
        status: "healthy",
        service: "common-agent-api",
        version: "0.1.0",
      }),
    ).toThrow();
  });

  it("maps a public backend envelope without exposing transport details", () => {
    const response = {
      data: {
        code: "service_unavailable",
        message: "服务尚未就绪",
        request_id: "request-1",
        retryable: true,
      },
      status: 503,
      statusText: "Service Unavailable",
      headers: {},
      config: { headers: {} },
    } as AxiosResponse;
    const transportError = new AxiosError("private transport details", "ERR_BAD_RESPONSE", undefined, undefined, response);

    const error = toApiClientError(transportError);

    expect(error.message).toBe("服务尚未就绪");
    expect(error.code).toBe("service_unavailable");
    expect(error.requestId).toBe("request-1");
    expect(error.retryable).toBe(true);
    expect(JSON.stringify(error)).not.toContain("private transport details");
  });

  it("fetches and validates the public health endpoint", async () => {
    const health = {
      status: "ok" as const,
      service: "common-agent-api" as const,
      version: "0.1.0",
      integration_mode: "real" as const,
    };
    vi.mocked(apiClient.get).mockResolvedValueOnce({ data: health });

    await expect(fetchHealth()).resolves.toEqual(health);
    expect(apiClient.get).toHaveBeenNthCalledWith(1, "/system/health");
  });

  it("normalizes health endpoint transport failures", async () => {
    vi.mocked(apiClient.get).mockRejectedValue(new Error("offline"));

    await expect(fetchHealth()).rejects.toBeDefined();
  });
});
