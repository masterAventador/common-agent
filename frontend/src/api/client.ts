import axios from "axios";

const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim();
export const apiBaseUrl = configuredBaseUrl || "http://127.0.0.1:18200/api/v1";
export const AUTHENTICATION_REQUIRED_EVENT = "common-agent:authentication-required";

const safeMethods = new Set(["GET", "HEAD", "OPTIONS"]);
const publicAuthWrites = new Set([
  "/auth/login",
  "/auth/register",
  "/auth/recovery/reset",
]);
let csrfToken = "";
let tenantId = "";

export function setCsrfToken(token: string): void {
  csrfToken = token;
}

export function clearCsrfToken(): void {
  csrfToken = "";
}

export function setTenantId(value: string): void {
  tenantId = value;
}

export function getTenantId(): string {
  return tenantId;
}

export function clearTenantId(): void {
  tenantId = "";
}

export const apiClient = axios.create({
  baseURL: apiBaseUrl,
  timeout: 10_000,
  withCredentials: true,
  headers: {
    Accept: "application/json",
  },
});

apiClient.interceptors.request.use((config) => {
  const method = config.method?.toUpperCase() ?? "GET";
  const path = config.url ?? "";
  if (csrfToken && !safeMethods.has(method) && !publicAuthWrites.has(path)) {
    config.headers.set("X-CSRF-Token", csrfToken);
  }
  if (tenantId && !path.startsWith("/auth/") && path !== "/tenants") {
    config.headers.set("X-Tenant-ID", tenantId);
  }
  return config;
});

apiClient.interceptors.response.use(undefined, (error: unknown) => {
  if (axios.isAxiosError(error) && error.response?.status === 401) {
    const path = error.config?.url ?? "";
    if (!publicAuthWrites.has(path)) {
      clearCsrfToken();
      clearTenantId();
      if (typeof window !== "undefined") {
        window.dispatchEvent(new Event(AUTHENTICATION_REQUIRED_EVENT));
      }
    }
  }
  return Promise.reject(error);
});
