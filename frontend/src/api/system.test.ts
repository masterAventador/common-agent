import { AxiosError, type AxiosResponse } from "axios";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "./client";
import {
  fetchHealth,
  fetchSystemStatus,
  parseHealthResponse,
  parseSystemStatusResponse,
  toApiClientError,
} from "./system";

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

  it("accepts explicit model configuration and knowledge availability", () => {
    expect(
      parseSystemStatusResponse({
        backend: "available",
        service: "common-agent-api",
        version: "0.1.0",
        integration_mode: "real",
        model: { provider: "bailian", status: "configured" },
        knowledge: {
          provider: "ragflow",
          availability: "available",
          version: "v0.26.4",
          error_code: null,
        },
      }),
    ).toEqual(
      expect.objectContaining({
        model: { provider: "bailian", status: "configured" },
        knowledge: expect.objectContaining({ availability: "available" }),
      }),
    );
  });

  it("rejects a dependency status that claims an unknown state", () => {
    expect(() =>
      parseSystemStatusResponse({
        backend: "available",
        service: "common-agent-api",
        version: "0.1.0",
        integration_mode: "real",
        model: { provider: "bailian", status: "healthy" },
        knowledge: {
          provider: "ragflow",
          availability: "perfect",
          version: "v0.26.4",
          error_code: null,
        },
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

  it("fetches and validates both public system endpoints", async () => {
    const health = {
      status: "ok" as const,
      service: "common-agent-api" as const,
      version: "0.1.0",
      integration_mode: "real" as const,
    };
    const status = {
      backend: "available" as const,
      service: "common-agent-api" as const,
      version: "0.1.0",
      integration_mode: "real" as const,
      model: { provider: "bailian", status: "configured" as const },
      knowledge: {
        provider: "ragflow",
        availability: "available" as const,
        version: "v0.26.4",
        error_code: null,
      },
    };
    vi.mocked(apiClient.get)
      .mockResolvedValueOnce({ data: health })
      .mockResolvedValueOnce({ data: status });

    await expect(fetchHealth()).resolves.toEqual(health);
    await expect(fetchSystemStatus()).resolves.toEqual(status);
    expect(apiClient.get).toHaveBeenNthCalledWith(1, "/system/health");
    expect(apiClient.get).toHaveBeenNthCalledWith(2, "/system/status");
  });

  it("normalizes system endpoint transport failures", async () => {
    vi.mocked(apiClient.get).mockRejectedValue(new Error("offline"));

    await expect(fetchHealth()).rejects.toBeDefined();
    await expect(fetchSystemStatus()).rejects.toBeDefined();
  });
});
