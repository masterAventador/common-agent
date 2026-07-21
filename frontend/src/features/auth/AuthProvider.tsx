import { useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Card, Form, Input, Modal, Space, Spin, Typography } from "antd";
import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type PropsWithChildren,
  type ReactNode,
} from "react";

import {
  fetchAuthPolicy,
  fetchCurrentSession,
  login as loginRequest,
  logout as logoutRequest,
  registerOwner,
  resetPassword,
  type LoginInput,
  type RegisterOwnerInput,
  type ResetPasswordInput,
} from "../../api/auth";
import {
  AUTHENTICATION_REQUIRED_EVENT,
  clearCsrfToken,
  clearTenantId,
  setTenantId,
} from "../../api/client";
import type { AuthSessionResponse } from "../../api/contracts";
import { ApiClientError, getErrorMessage } from "../../api/errors";
import {
  createTenant,
  fetchTenantAccesses,
  type TenantAccess,
} from "../../api/tenants";
import {
  AuthContext,
  useAuth,
  type AuthContextValue,
  type AuthMode,
  type AuthPhase,
} from "./authContext";

function tenantStorageKey(userId: string): string {
  return `common-agent:selected-tenant:${userId}`;
}

function readRememberedTenant(userId: string): string | null {
  try {
    return window.localStorage.getItem(tenantStorageKey(userId));
  } catch {
    return null;
  }
}

function rememberTenant(userId: string, tenantId: string): void {
  try {
    window.localStorage.setItem(tenantStorageKey(userId), tenantId);
  } catch {
    // Browsers may disable storage; the in-memory tenant context remains authoritative.
  }
}

export function AuthProvider({ children }: PropsWithChildren) {
  const queryClient = useQueryClient();
  const [phase, setPhase] = useState<AuthPhase>("loading");
  const [mode, setMode] = useState<AuthMode>("login");
  const [session, setSession] = useState<AuthSessionResponse | null>(null);
  const [tenants, setTenants] = useState<readonly TenantAccess[]>([]);
  const [selectedTenantId, setSelectedTenantId] = useState<string | null>(null);
  const [registrationAvailable, setRegistrationAvailable] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [recoveryCodes, setRecoveryCodes] = useState<readonly string[]>([]);

  const loadAnonymousPolicy = useCallback(async () => {
    try {
      const policy = await fetchAuthPolicy();
      setRegistrationAvailable(policy.registration_available);
      setMode(policy.registration_available ? "register" : "login");
      setError(null);
    } catch (policyError) {
      setRegistrationAvailable(false);
      setMode("login");
      setError(getErrorMessage(policyError));
    } finally {
      setPhase("anonymous");
    }
  }, []);

  const completeAuthentication = useCallback(async (authenticated: AuthSessionResponse) => {
    const accesses = await fetchTenantAccesses();
    const rememberedId = readRememberedTenant(authenticated.user_id);
    const selected = accesses.find((access) => access.id === rememberedId) ?? accesses[0];
    if (!selected) {
      throw new Error("当前账号尚未加入任何工作区");
    }
    setTenantId(selected.id);
    rememberTenant(authenticated.user_id, selected.id);
    setTenants(accesses);
    setSelectedTenantId(selected.id);
    setSession(authenticated);
    setPhase("authenticated");
  }, []);

  useEffect(() => {
    let active = true;
    void fetchCurrentSession()
      .then(async (currentSession) => {
        if (!active) return;
        await completeAuthentication(currentSession);
      })
      .catch(async (sessionError: unknown) => {
        if (!active) return;
        if (
          sessionError instanceof ApiClientError &&
          sessionError.code !== "authentication_required"
        ) {
          setError(sessionError.message);
        }
        await loadAnonymousPolicy();
      });
    return () => {
      active = false;
    };
  }, [completeAuthentication, loadAnonymousPolicy]);

  useEffect(() => {
    const requireAuthentication = () => {
      clearCsrfToken();
      clearTenantId();
      setSession(null);
      setTenants([]);
      setSelectedTenantId(null);
      queryClient.clear();
      void loadAnonymousPolicy();
    };
    window.addEventListener(AUTHENTICATION_REQUIRED_EVENT, requireAuthentication);
    return () => {
      window.removeEventListener(AUTHENTICATION_REQUIRED_EVENT, requireAuthentication);
    };
  }, [loadAnonymousPolicy, queryClient]);

  const authenticate = useCallback(
    async (input: LoginInput) => {
      setBusy(true);
      setError(null);
      try {
        const authenticated = await loginRequest(input);
        await completeAuthentication(authenticated);
      } catch (loginError) {
        setError(getErrorMessage(loginError));
      } finally {
        setBusy(false);
      }
    },
    [completeAuthentication],
  );

  const register = useCallback(async (input: RegisterOwnerInput) => {
    setBusy(true);
    setError(null);
    try {
      const registered = await registerOwner(input);
      setRecoveryCodes(registered.recovery_codes);
      setRegistrationAvailable(false);
      await completeAuthentication(registered);
    } catch (registrationError) {
      setError(getErrorMessage(registrationError));
    } finally {
      setBusy(false);
    }
  }, [completeAuthentication]);

  const recover = useCallback(async (input: ResetPasswordInput) => {
    setBusy(true);
    setError(null);
    try {
      await resetPassword(input);
      setMode("login");
    } catch (recoveryError) {
      setError(getErrorMessage(recoveryError));
    } finally {
      setBusy(false);
    }
  }, []);

  const logout = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      await logoutRequest();
      clearTenantId();
      setSession(null);
      setTenants([]);
      setSelectedTenantId(null);
      queryClient.clear();
      await loadAnonymousPolicy();
    } catch (logoutError) {
      setError(getErrorMessage(logoutError));
    } finally {
      setBusy(false);
    }
  }, [loadAnonymousPolicy, queryClient]);

  const selectTenant = useCallback(
    (tenantId: string) => {
      if (!tenants.some((tenant) => tenant.id === tenantId)) return;
      setTenantId(tenantId);
      setSelectedTenantId(tenantId);
      if (session) {
        rememberTenant(session.user_id, tenantId);
      }
      queryClient.clear();
    },
    [queryClient, session, tenants],
  );

  const createWorkspace = useCallback(
    async (name: string): Promise<boolean> => {
      const selected = tenants.find((tenant) => tenant.id === selectedTenantId);
      if (!selected || selected.role !== "owner") return false;
      setBusy(true);
      setError(null);
      try {
        const created = await createTenant({
          organization_id: selected.organization_id,
          name,
        });
        setTenants((current) => [...current, created]);
        setTenantId(created.id);
        setSelectedTenantId(created.id);
        if (session) {
          rememberTenant(session.user_id, created.id);
        }
        queryClient.clear();
        return true;
      } catch (workspaceError) {
        setError(getErrorMessage(workspaceError));
        return false;
      } finally {
        setBusy(false);
      }
    },
    [queryClient, selectedTenantId, session, tenants],
  );

  const value = useMemo<AuthContextValue>(
    () => ({
      phase,
      mode,
      session,
      tenants,
      selectedTenantId,
      registrationAvailable,
      busy,
      error,
      recoveryCodes,
      setMode,
      login: authenticate,
      register,
      recover,
      logout,
      selectTenant,
      createWorkspace,
      dismissRecoveryCodes: () => setRecoveryCodes([]),
    }),
    [
      authenticate,
      busy,
      createWorkspace,
      error,
      logout,
      mode,
      phase,
      recover,
      recoveryCodes,
      register,
      registrationAvailable,
      session,
      selectedTenantId,
      selectTenant,
      tenants,
    ],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function AuthGate({ children }: { children: ReactNode }) {
  const auth = useAuth();
  if (auth.phase === "loading") {
    return (
      <main className="auth-loading" aria-label="正在恢复安全会话">
        <Spin size="large" />
      </main>
    );
  }
  if (auth.phase === "anonymous") {
    return <AuthPage />;
  }
  return (
    <>
      {children}
      <Modal
        open={auth.recoveryCodes.length > 0}
        title="请妥善保存恢复码"
        closable={false}
        mask={{ closable: false }}
        footer={
          <Button type="primary" onClick={auth.dismissRecoveryCodes}>
            我已保存
          </Button>
        }
      >
        <Alert
          type="warning"
          showIcon
          title="恢复码只显示一次；每个恢复码只能使用一次。"
        />
        <pre className="auth-recovery-codes">{auth.recoveryCodes.join("\n")}</pre>
      </Modal>
    </>
  );
}

function AuthPage() {
  const auth = useAuth();
  return (
    <main className="auth-page">
      <Card className="auth-card">
        <Space orientation="vertical" size={20} className="auth-card-content">
          <div className="auth-heading">
            <span className="brand-mark">CA</span>
            <div>
              <Typography.Title level={2}>
                {auth.mode === "register" ? "创建首位管理员" : "登录 Common Agent"}
              </Typography.Title>
              <Typography.Text type="secondary">
                使用服务端安全会话访问员工、知识库、会话和工作流
              </Typography.Text>
            </div>
          </div>
          {auth.error ? <Alert type="error" showIcon message={auth.error} /> : null}
          {auth.mode === "register" ? (
            <RegisterForm auth={auth} />
          ) : auth.mode === "recovery" ? (
            <RecoveryForm auth={auth} />
          ) : (
            <LoginForm auth={auth} />
          )}
        </Space>
      </Card>
    </main>
  );
}

function LoginForm({ auth }: { auth: AuthContextValue }) {
  return (
    <Form<LoginInput> layout="vertical" requiredMark={false} onFinish={auth.login}>
      <Form.Item label="邮箱" name="email" rules={[{ required: true, type: "email" }]}>
        <Input autoComplete="username" />
      </Form.Item>
      <Form.Item label="密码" name="password" rules={[{ required: true }]}>
        <Input.Password autoComplete="current-password" />
      </Form.Item>
      <Button block type="primary" htmlType="submit" loading={auth.busy}>
        登录
      </Button>
      <Button block type="link" onClick={() => auth.setMode("recovery")}>
        使用恢复码重置密码
      </Button>
    </Form>
  );
}

function RegisterForm({ auth }: { auth: AuthContextValue }) {
  return (
    <Form<RegisterOwnerInput> layout="vertical" requiredMark={false} onFinish={auth.register}>
      <Form.Item label="邮箱" name="email" rules={[{ required: true, type: "email" }]}>
        <Input autoComplete="username" />
      </Form.Item>
      <Form.Item
        label="密码"
        name="password"
        rules={[{ required: true, min: 8, max: 128 }]}
        extra="至少 8 个字符"
      >
        <Input.Password autoComplete="new-password" />
      </Form.Item>
      <Form.Item label="站点引导凭据" name="bootstrap_token" rules={[{ required: true }]}>
        <Input.Password autoComplete="off" />
      </Form.Item>
      <Button block type="primary" htmlType="submit" loading={auth.busy}>
        创建管理员
      </Button>
    </Form>
  );
}

function RecoveryForm({ auth }: { auth: AuthContextValue }) {
  return (
    <Form<ResetPasswordInput> layout="vertical" requiredMark={false} onFinish={auth.recover}>
      <Form.Item label="邮箱" name="email" rules={[{ required: true, type: "email" }]}>
        <Input autoComplete="username" />
      </Form.Item>
      <Form.Item label="恢复码" name="recovery_code" rules={[{ required: true, len: 17 }]}>
        <Input autoComplete="one-time-code" />
      </Form.Item>
      <Form.Item
        label="新密码"
        name="new_password"
        rules={[{ required: true, min: 8, max: 128 }]}
      >
        <Input.Password autoComplete="new-password" />
      </Form.Item>
      <Button block type="primary" htmlType="submit" loading={auth.busy}>
        重置密码
      </Button>
      <Button block type="link" onClick={() => auth.setMode("login")}>
        返回登录
      </Button>
    </Form>
  );
}
