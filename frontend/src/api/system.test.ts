import { AxiosError, type AxiosResponse } from "axios";
import { describe, expect, it } from "vitest";

import { parseHealthResponse, parseSystemStatusResponse, toApiClientError } from "./system";

describe("system API boundary", () => {
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
});
