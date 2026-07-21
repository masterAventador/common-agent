import { AxiosError, type AxiosAdapter, type InternalAxiosRequestConfig } from "axios";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  AUTHENTICATION_REQUIRED_EVENT,
  apiClient,
  clearCsrfToken,
  clearTenantId,
  setCsrfToken,
  setTenantId,
} from "./client";

function successfulAdapter(requests: InternalAxiosRequestConfig[]): AxiosAdapter {
  return async (config) => {
    requests.push(config);
    return {
      config,
      data: {},
      headers: {},
      status: 200,
      statusText: "OK",
    };
  };
}

afterEach(() => {
  clearCsrfToken();
  clearTenantId();
});

describe("authenticated API client", () => {
  it("always sends the server-side session cookie and adds CSRF only to unsafe requests", async () => {
    const requests: InternalAxiosRequestConfig[] = [];
    const adapter = successfulAdapter(requests);
    setCsrfToken("csrf-token-1");

    await apiClient.get("/employees", { adapter });
    await apiClient.post("/employees", {}, { adapter });

    expect(apiClient.defaults.withCredentials).toBe(true);
    expect(requests[0]?.headers.get("X-CSRF-Token")).toBeUndefined();
    expect(requests[1]?.headers.get("X-CSRF-Token")).toBe("csrf-token-1");
  });

  it("adds the selected tenant only to protected platform requests", async () => {
    const requests: InternalAxiosRequestConfig[] = [];
    const adapter = successfulAdapter(requests);
    setTenantId("10000000-0000-4000-8000-000000000001");

    await apiClient.get("/employees", { adapter });
    await apiClient.get("/tenants", { adapter });

    expect(requests[0]?.headers.get("X-Tenant-ID")).toBe(
      "10000000-0000-4000-8000-000000000001",
    );
    expect(requests[1]?.headers.get("X-Tenant-ID")).toBeUndefined();
  });

  it("clears CSRF state and notifies the auth gate when a protected request returns 401", async () => {
    const listener = vi.fn();
    window.addEventListener(AUTHENTICATION_REQUIRED_EVENT, listener, { once: true });
    setCsrfToken("csrf-token-2");

    await expect(
      apiClient.get("/employees", {
        adapter: async (config) =>
          Promise.reject(
            new AxiosError("unauthorized", "ERR_BAD_RESPONSE", config, undefined, {
              config,
              data: {},
              headers: {},
              status: 401,
              statusText: "Unauthorized",
            }),
          ),
      }),
    ).rejects.toBeInstanceOf(AxiosError);

    const requests: InternalAxiosRequestConfig[] = [];
    await apiClient.post("/employees", {}, { adapter: successfulAdapter(requests) });
    expect(requests[0]?.headers.get("X-CSRF-Token")).toBeUndefined();
    expect(listener).toHaveBeenCalledOnce();
  });
});
