import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiClientError } from "../../api/errors";
import { AuthGate, AuthProvider } from "./AuthProvider";
import { useAuth } from "./authContext";

const authApi = vi.hoisted(() => ({
  fetchAuthPolicy: vi.fn(),
  fetchCurrentSession: vi.fn(),
  login: vi.fn(),
  logout: vi.fn(),
  registerOwner: vi.fn(),
  resetPassword: vi.fn(),
}));
const tenancyApi = vi.hoisted(() => ({
  fetchTenantAccesses: vi.fn(),
}));

vi.mock("../../api/auth", () => authApi);
vi.mock("../../api/tenants", () => tenancyApi);

const session = {
  user_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
  email: "owner@example.com",
  csrf_token: "csrf-token",
  idle_expires_at: "2026-07-21T03:00:00Z",
  absolute_expires_at: "2026-07-22T02:00:00Z",
};
const tenant = {
  id: "10000000-0000-4000-8000-000000000001",
  name: "默认工作区",
  organization_id: "00000000-0000-4000-8000-000000000001",
  organization_name: "默认组织",
  role: "owner" as const,
};

function authenticationRequired() {
  return new ApiClientError("请先登录", "authentication_required", "request-1", false);
}

function renderGate() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <AuthGate>
          <div>受保护内容</div>
        </AuthGate>
      </AuthProvider>
    </QueryClientProvider>,
  );
}

function AuthenticatedActions() {
  const auth = useAuth();
  return (
    <div>
      受保护内容
      <button type="button" onClick={() => void auth.logout()}>
        测试退出
      </button>
    </div>
  );
}

function renderActions() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <AuthGate>
          <AuthenticatedActions />
        </AuthGate>
      </AuthProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  authApi.fetchAuthPolicy.mockReset();
  authApi.fetchCurrentSession.mockReset();
  authApi.login.mockReset();
  authApi.logout.mockReset();
  authApi.registerOwner.mockReset();
  authApi.resetPassword.mockReset();
  tenancyApi.fetchTenantAccesses.mockReset();
  tenancyApi.fetchTenantAccesses.mockResolvedValue([tenant]);
});

describe("authentication gate", () => {
  it("restores a valid server session without showing a login form", async () => {
    authApi.fetchCurrentSession.mockResolvedValue(session);

    renderGate();

    expect(await screen.findByText("受保护内容")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "登录 Common Agent" })).not.toBeInTheDocument();
  });

  it("logs in through the public form before rendering protected content", async () => {
    authApi.fetchCurrentSession.mockRejectedValue(authenticationRequired());
    authApi.fetchAuthPolicy.mockResolvedValue({ registration_available: false });
    authApi.login.mockResolvedValue(session);
    const user = userEvent.setup();
    renderGate();

    await user.type(await screen.findByLabelText("邮箱"), "owner@example.com");
    await user.type(screen.getByLabelText("密码"), "correct horse battery staple");
    await user.click(screen.getByRole("button", { name: /登\s*录/ }));

    await waitFor(() =>
      expect(authApi.login).toHaveBeenCalledWith({
        email: "owner@example.com",
        password: "correct horse battery staple",
      }),
    );
    expect(await screen.findByText("受保护内容")).toBeInTheDocument();
  });

  it("creates the first owner with a bootstrap token and shows one-time recovery codes", async () => {
    authApi.fetchCurrentSession.mockRejectedValue(authenticationRequired());
    authApi.fetchAuthPolicy.mockResolvedValue({ registration_available: true });
    authApi.registerOwner.mockResolvedValue({
      ...session,
      recovery_codes: ["AAAA-BBBB-CCCC-DDDD", "EEEE-FFFF-GGGG-HHHH"],
    });
    const user = userEvent.setup();
    renderGate();

    await user.type(await screen.findByLabelText("邮箱"), "owner@example.com");
    await user.type(screen.getByLabelText("密码"), "correct horse battery staple");
    await user.type(screen.getByLabelText("站点引导凭据"), "bootstrap-token");
    await user.click(screen.getByRole("button", { name: "创建管理员" }));

    expect(await screen.findByText("请妥善保存恢复码")).toBeInTheDocument();
    expect(screen.getByText(/AAAA-BBBB-CCCC-DDDD/)).toBeInTheDocument();
    expect(await screen.findByText("受保护内容")).toBeInTheDocument();
  });

  it("returns to the login gate when the server reports an expired or revoked session", async () => {
    authApi.fetchCurrentSession.mockResolvedValue(session);
    authApi.fetchAuthPolicy.mockResolvedValue({ registration_available: false });
    renderGate();
    expect(await screen.findByText("受保护内容")).toBeInTheDocument();

    window.dispatchEvent(new Event("common-agent:authentication-required"));

    expect(await screen.findByRole("heading", { name: "登录 Common Agent" })).toBeInTheDocument();
    expect(screen.queryByText("受保护内容")).not.toBeInTheDocument();
  });

  it("resets a password with a one-time recovery code before returning to login", async () => {
    authApi.fetchCurrentSession.mockRejectedValue(authenticationRequired());
    authApi.fetchAuthPolicy.mockResolvedValue({ registration_available: false });
    authApi.resetPassword.mockResolvedValue(undefined);
    const user = userEvent.setup();
    renderGate();

    await user.click(
      await screen.findByRole("button", { name: "使用恢复码重置密码" }),
    );
    await user.type(screen.getByLabelText("邮箱"), "owner@example.com");
    await user.type(screen.getByLabelText("恢复码"), "ABCDEFGH-JKLMNPQR");
    await user.type(screen.getByLabelText("新密码"), "replacement horse battery password");
    await user.click(screen.getByRole("button", { name: "重置密码" }));

    await waitFor(() =>
      expect(authApi.resetPassword).toHaveBeenCalledWith({
        email: "owner@example.com",
        recovery_code: "ABCDEFGH-JKLMNPQR",
        new_password: "replacement horse battery password",
      }),
    );
    expect(
      await screen.findByRole("heading", { name: "登录 Common Agent" }),
    ).toBeInTheDocument();
  });

  it("logs out through the server and clears the authenticated surface", async () => {
    authApi.fetchCurrentSession.mockResolvedValue(session);
    authApi.logout.mockResolvedValue(undefined);
    authApi.fetchAuthPolicy.mockResolvedValue({ registration_available: false });
    const user = userEvent.setup();
    renderActions();

    await user.click(await screen.findByRole("button", { name: "测试退出" }));

    expect(authApi.logout).toHaveBeenCalledOnce();
    expect(
      await screen.findByRole("heading", { name: "登录 Common Agent" }),
    ).toBeInTheDocument();
    expect(screen.queryByText("受保护内容")).not.toBeInTheDocument();
  });

  it("keeps the gate closed and reports login failures", async () => {
    authApi.fetchCurrentSession.mockRejectedValue(authenticationRequired());
    authApi.fetchAuthPolicy.mockResolvedValue({ registration_available: false });
    authApi.login.mockRejectedValue(
      new ApiClientError("邮箱或密码不正确", "invalid_credentials", "request-2", false),
    );
    const user = userEvent.setup();
    renderGate();

    await user.type(await screen.findByLabelText("邮箱"), "owner@example.com");
    await user.type(screen.getByLabelText("密码"), "wrong password value");
    await user.click(screen.getByRole("button", { name: /登\s*录/ }));

    expect(await screen.findByText("邮箱或密码不正确")).toBeInTheDocument();
    expect(screen.queryByText("受保护内容")).not.toBeInTheDocument();
  });
});
