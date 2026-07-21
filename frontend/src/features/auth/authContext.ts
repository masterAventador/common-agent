import { createContext, useContext } from "react";

import type {
  LoginInput,
  RegisterOwnerInput,
  ResetPasswordInput,
} from "../../api/auth";
import type { AuthSessionResponse } from "../../api/contracts";
import type { TenantAccess } from "../../api/tenants";

export type AuthPhase = "loading" | "anonymous" | "authenticated";
export type AuthMode = "login" | "register" | "recovery";

export interface AuthContextValue {
  phase: AuthPhase;
  mode: AuthMode;
  session: AuthSessionResponse | null;
  tenants: readonly TenantAccess[];
  selectedTenantId: string | null;
  registrationAvailable: boolean;
  busy: boolean;
  error: string | null;
  recoveryCodes: readonly string[];
  setMode: (mode: AuthMode) => void;
  login: (input: LoginInput) => Promise<void>;
  register: (input: RegisterOwnerInput) => Promise<void>;
  recover: (input: ResetPasswordInput) => Promise<void>;
  logout: () => Promise<void>;
  selectTenant: (tenantId: string) => void;
  createWorkspace: (name: string) => Promise<boolean>;
  dismissRecoveryCodes: () => void;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (context === null) {
    throw new Error("AuthProvider 尚未装配");
  }
  return context;
}
