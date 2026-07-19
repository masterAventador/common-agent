import { AxiosError, type AxiosResponse } from "axios";
import { describe, expect, it } from "vitest";

import { parseHealthResponse, toApiClientError } from "./system";

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
