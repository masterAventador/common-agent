import { describe, expect, it, vi } from "vitest";

import { apiClient } from "./client";
import { createTenant, fetchTenantAccesses, provisionTenantMember } from "./tenants";

vi.mock("./client", () => ({
  apiClient: { get: vi.fn(), post: vi.fn() },
}));

describe("tenant API", () => {
  it("strictly parses tenant access and roles", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      data: [
        {
          id: "10000000-0000-4000-8000-000000000001",
          name: "默认工作区",
          organization_id: "00000000-0000-4000-8000-000000000001",
          organization_name: "默认组织",
          role: "owner",
        },
      ],
    });

    await expect(fetchTenantAccesses()).resolves.toHaveLength(1);
    vi.mocked(apiClient.get).mockResolvedValue({ data: [{ role: "root" }] });
    await expect(fetchTenantAccesses()).rejects.toBeDefined();
  });

  it("creates a workspace only through the formal tenant endpoint", async () => {
    const created = {
      id: "20000000-0000-4000-8000-000000000002",
      name: "商业工作区",
      organization_id: "00000000-0000-4000-8000-000000000001",
      organization_name: "默认组织",
      role: "owner" as const,
    };
    vi.mocked(apiClient.post).mockResolvedValue({ data: created });

    await expect(
      createTenant({ organization_id: created.organization_id, name: created.name }),
    ).resolves.toEqual(created);
    expect(apiClient.post).toHaveBeenCalledWith("/tenants", {
      organization_id: created.organization_id,
      name: created.name,
    });
  });

  it("provisions an explicit role without exposing password in the response", async () => {
    const tenantId = "10000000-0000-4000-8000-000000000001";
    const provisioned = {
      user_id: "30000000-0000-4000-8000-000000000003",
      email: "viewer@example.com",
      role: "viewer" as const,
      recovery_codes: ["ABCDEFGH-JKLMNPQR"],
    };
    vi.mocked(apiClient.post).mockResolvedValue({ data: provisioned });

    await expect(
      provisionTenantMember(tenantId, {
        email: provisioned.email,
        password: "viewer initial password is secure",
        role: provisioned.role,
      }),
    ).resolves.toEqual(provisioned);
    expect(apiClient.post).toHaveBeenCalledWith(`/tenants/${tenantId}/members`, {
      email: provisioned.email,
      password: "viewer initial password is secure",
      role: "viewer",
    });
  });
});
