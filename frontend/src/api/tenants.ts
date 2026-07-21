import { z } from "zod";

import { apiClient } from "./client";
import { toApiClientError } from "./errors";

const tenantAccessSchema = z.strictObject({
  id: z.uuid(),
  name: z.string().min(1),
  organization_id: z.uuid(),
  organization_name: z.string().min(1),
  role: z.enum(["owner", "editor", "viewer"]),
});

const tenantAccessesSchema = z.array(tenantAccessSchema);
const tenantRoleSchema = z.enum(["owner", "editor", "viewer"]);
const provisionedTenantMemberSchema = z.strictObject({
  user_id: z.uuid(),
  email: z.email(),
  role: tenantRoleSchema,
  recovery_codes: z.array(z.string().min(1)),
});

export type TenantAccess = z.infer<typeof tenantAccessSchema>;

export interface CreateTenantInput {
  organization_id: string;
  name: string;
}

export type TenantRole = z.infer<typeof tenantRoleSchema>;
export type ProvisionedTenantMember = z.infer<typeof provisionedTenantMemberSchema>;
export interface ProvisionTenantMemberInput {
  email: string;
  password: string;
  role: TenantRole;
}

export async function fetchTenantAccesses(): Promise<readonly TenantAccess[]> {
  try {
    const response = await apiClient.get<unknown>("/tenants");
    return tenantAccessesSchema.parse(response.data);
  } catch (error) {
    throw toApiClientError(error);
  }
}

export async function createTenant(input: CreateTenantInput): Promise<TenantAccess> {
  try {
    const response = await apiClient.post<unknown>("/tenants", input);
    return tenantAccessSchema.parse(response.data);
  } catch (error) {
    throw toApiClientError(error);
  }
}

export async function provisionTenantMember(
  tenantId: string,
  input: ProvisionTenantMemberInput,
): Promise<ProvisionedTenantMember> {
  try {
    const response = await apiClient.post<unknown>(
      `/tenants/${encodeURIComponent(tenantId)}/members`,
      input,
    );
    return provisionedTenantMemberSchema.parse(response.data);
  } catch (error) {
    throw toApiClientError(error);
  }
}
