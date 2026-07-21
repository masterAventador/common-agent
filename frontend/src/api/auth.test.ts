import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient, clearCsrfToken, setCsrfToken } from "./client";
import {
  fetchAuthPolicy,
  fetchCurrentSession,
  login,
  logout,
  parseAuthSession,
  registerOwner,
  resetPassword,
} from "./auth";

vi.mock("./client", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
  },
  clearCsrfToken: vi.fn(),
  setCsrfToken: vi.fn(),
}));

const session = {
  user_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
  email: "owner@example.com",
  csrf_token: "csrf-token",
  idle_expires_at: "2026-07-21T03:00:00Z",
  absolute_expires_at: "2026-07-22T02:00:00Z",
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe("authentication API boundary", () => {
  it("strictly parses a session and rejects any browser-visible session token", () => {
    expect(parseAuthSession(session)).toEqual(session);
    expect(() => parseAuthSession({ ...session, session_token: "must-not-be-visible" })).toThrow();
  });

  it("loads policy/session and keeps only the CSRF token in process memory", async () => {
    vi.mocked(apiClient.get)
      .mockResolvedValueOnce({ data: { registration_available: false } })
      .mockResolvedValueOnce({ data: session });

    await expect(fetchAuthPolicy()).resolves.toEqual({ registration_available: false });
    await expect(fetchCurrentSession()).resolves.toEqual(session);
    expect(setCsrfToken).toHaveBeenCalledWith("csrf-token");
  });

  it("logs in, registers, resets credentials and logs out through the platform API", async () => {
    vi.mocked(apiClient.post)
      .mockResolvedValueOnce({ data: session })
      .mockResolvedValueOnce({
        data: { ...session, recovery_codes: ["AAAA-BBBB-CCCC-DDDD"] },
      })
      .mockResolvedValueOnce({ data: undefined })
      .mockResolvedValueOnce({ data: undefined });

    await expect(login({ email: session.email, password: "password-password" })).resolves.toEqual(
      session,
    );
    await expect(
      registerOwner({
        email: session.email,
        password: "password-password",
        bootstrap_token: "bootstrap-token",
      }),
    ).resolves.toEqual({ ...session, recovery_codes: ["AAAA-BBBB-CCCC-DDDD"] });
    await expect(
      resetPassword({
        email: session.email,
        recovery_code: "AAAA-BBBB-CCCC-DDDD",
        new_password: "new-password-password",
      }),
    ).resolves.toBeUndefined();
    await expect(logout()).resolves.toBeUndefined();

    expect(apiClient.post).toHaveBeenNthCalledWith(1, "/auth/login", {
      email: session.email,
      password: "password-password",
    });
    expect(apiClient.post).toHaveBeenNthCalledWith(4, "/auth/logout");
    expect(clearCsrfToken).toHaveBeenCalledOnce();
  });
});
