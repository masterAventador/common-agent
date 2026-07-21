import { z } from "zod";

import type {
  AuthPolicyResponse,
  AuthSessionResponse,
  RegistrationResponse,
} from "./contracts";
import { apiClient, clearCsrfToken, setCsrfToken } from "./client";
import { toApiClientError } from "./errors";

const authPolicySchema = z.strictObject({
  registration_available: z.boolean(),
});

const authSessionSchema = z.strictObject({
  user_id: z.uuid(),
  email: z.email(),
  csrf_token: z.string().min(1),
  idle_expires_at: z.iso.datetime({ offset: true }),
  absolute_expires_at: z.iso.datetime({ offset: true }),
});

const registrationSchema = authSessionSchema.extend({
  recovery_codes: z.array(z.string().min(1)),
});

export interface LoginInput {
  email: string;
  password: string;
}

export interface RegisterOwnerInput extends LoginInput {
  bootstrap_token: string;
}

export interface ResetPasswordInput {
  email: string;
  recovery_code: string;
  new_password: string;
}

export function parseAuthSession(data: unknown): AuthSessionResponse {
  return authSessionSchema.parse(data);
}

function parseRegistration(data: unknown): RegistrationResponse {
  return registrationSchema.parse(data);
}

function rememberSession(session: AuthSessionResponse): AuthSessionResponse {
  setCsrfToken(session.csrf_token);
  return session;
}

export async function fetchAuthPolicy(): Promise<AuthPolicyResponse> {
  try {
    const response = await apiClient.get<unknown>("/auth/policy");
    return authPolicySchema.parse(response.data);
  } catch (error) {
    throw toApiClientError(error);
  }
}

export async function fetchCurrentSession(): Promise<AuthSessionResponse> {
  try {
    const response = await apiClient.get<unknown>("/auth/session");
    return rememberSession(parseAuthSession(response.data));
  } catch (error) {
    throw toApiClientError(error);
  }
}

export async function login(input: LoginInput): Promise<AuthSessionResponse> {
  try {
    const response = await apiClient.post<unknown>("/auth/login", input);
    return rememberSession(parseAuthSession(response.data));
  } catch (error) {
    throw toApiClientError(error);
  }
}

export async function registerOwner(
  input: RegisterOwnerInput,
): Promise<RegistrationResponse> {
  try {
    const response = await apiClient.post<unknown>("/auth/register", input);
    const registration = parseRegistration(response.data);
    rememberSession(registration);
    return registration;
  } catch (error) {
    throw toApiClientError(error);
  }
}

export async function resetPassword(input: ResetPasswordInput): Promise<void> {
  try {
    await apiClient.post("/auth/recovery/reset", input);
  } catch (error) {
    throw toApiClientError(error);
  }
}

export async function logout(): Promise<void> {
  try {
    await apiClient.post("/auth/logout");
    clearCsrfToken();
  } catch (error) {
    throw toApiClientError(error);
  }
}
