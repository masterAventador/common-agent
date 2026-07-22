import type { APIResponse } from "@playwright/test";

import {
  expect,
  platformApiUrl,
  platformHostHeaders,
  platformWriteHeaders,
  test,
} from "./fixtures/auth";

function requiredEnvironment(name: string): string {
  const value = process.env[name]?.trim();
  if (!value) throw new Error(`${name} is required`);
  return value;
}

const trustedOrigin = requiredEnvironment("COMMON_AGENT_E2E_TRUSTED_ORIGIN");
const frontendUrl = requiredEnvironment("COMMON_AGENT_E2E_FRONTEND_URL");
const defaultOrganizationId = "00000000-0000-4000-8000-000000000001";
const defaultTenantId = "00000000-0000-4000-8000-000000000002";
const otherTenantId = "00000000-0000-4000-8000-000000000003";
const missingModelId = "00000000-0000-4000-8000-000000000004";
const xssTenantName = '<img src=x onerror="window.__commonAgentXss=1">';
const viewerEmail = "production-security-viewer@example.com";
const viewerPassword = "Production-Security-Viewer-2026!";

async function expectError(response: APIResponse, status: number, code: string): Promise<void> {
  expect(response.status()).toBe(status);
  expect((await response.json()) as { code: string }).toMatchObject({ code });
}

function employeeBody(name: string) {
  return {
    name,
    description: "生产攻击矩阵请求",
    system_prompt: "该请求只用于验证正式入口安全边界。",
    default_model_configuration_id: missingModelId,
    knowledge_base_id: null,
    allowed_workflow_ids: [],
  };
}

test("rejects authentication, parser, query, and method attacks at the production edge", async ({
  page,
  request,
}) => {
  const unauthenticatedRead = await request.get(platformApiUrl("/employees"), {
    headers: platformHostHeaders(),
  });
  await expectError(unauthenticatedRead, 401, "authentication_required");

  const unauthenticatedWrite = await request.post(platformApiUrl("/employees"), {
    headers: platformHostHeaders({ Origin: trustedOrigin }),
    data: employeeBody("unauthenticated-write"),
  });
  await expectError(unauthenticatedWrite, 401, "authentication_required");

  const sessionCookie = (await page.context().cookies(trustedOrigin)).find(
    (cookie) => cookie.name === "__Host-common-agent-session",
  );
  expect(sessionCookie).toMatchObject({
    domain: "common-agent.test",
    path: "/",
    httpOnly: true,
    secure: true,
    sameSite: "Strict",
  });

  const ownerHeaders = await platformWriteHeaders(page);
  const missingCsrfHeaders = { ...ownerHeaders };
  delete missingCsrfHeaders["X-CSRF-Token"];
  const missingCsrf = await page.request.post(platformApiUrl("/employees"), {
    headers: missingCsrfHeaders,
    data: employeeBody("missing-csrf"),
  });
  await expectError(missingCsrf, 403, "csrf_validation_failed");

  const wrongCsrf = await page.request.post(platformApiUrl("/employees"), {
    headers: { ...ownerHeaders, "X-CSRF-Token": "wrong-token" },
    data: employeeBody("wrong-csrf"),
  });
  await expectError(wrongCsrf, 403, "csrf_validation_failed");

  const crossOrigin = await page.request.post(platformApiUrl("/employees"), {
    headers: {
      ...ownerHeaders,
      Origin: "https://attacker.example",
      "Sec-Fetch-Site": "cross-site",
    },
    data: employeeBody("cross-origin"),
  });
  await expectError(crossOrigin, 403, "origin_validation_failed");

  const wrongContentType = await request.post(platformApiUrl("/auth/login"), {
    headers: platformHostHeaders({
      Origin: trustedOrigin,
      "Content-Type": "text/plain",
    }),
    data: "{}",
  });
  await expectError(wrongContentType, 415, "unsupported_media_type");

  const malformedJson = await request.post(platformApiUrl("/auth/login"), {
    headers: platformHostHeaders({
      Origin: trustedOrigin,
      "Content-Type": "application/json",
    }),
    data: '{"email":',
  });
  await expectError(malformedJson, 422, "validation_error");

  const unknownField = await request.post(platformApiUrl("/auth/login"), {
    headers: platformHostHeaders({ Origin: trustedOrigin }),
    data: {
      email: "unknown-field@example.com",
      password: "Unknown-Field-Password-2026!",
      unexpected: true,
    },
  });
  await expectError(unknownField, 422, "validation_error");

  const tenantHeaders = platformHostHeaders({ "X-Tenant-ID": defaultTenantId });
  const oversizedSearch = await page.request.get(
    platformApiUrl(`/employees?search=${"a".repeat(129)}`),
    { headers: tenantHeaders },
  );
  await expectError(oversizedSearch, 422, "validation_error");

  for (let attempt = 0; attempt < 5; attempt += 1) {
    const invalidResourceId = await page.request.get(
      platformApiUrl("/employees/not-a-uuid"),
      { headers: tenantHeaders },
    );
    await expectError(invalidResourceId, 422, "validation_error");
  }

  const tenantConflict = await page.request.get(
    platformApiUrl(`/employees?tenant_id=${otherTenantId}`),
    { headers: tenantHeaders },
  );
  await expectError(tenantConflict, 422, "tenant_selection_conflict");

  const allModels = await page.request.get(platformApiUrl("/model-configurations"), {
    headers: tenantHeaders,
  });
  expect(allModels.status()).toBe(200);
  expect(((await allModels.json()) as { items: unknown[] }).items.length).toBeGreaterThan(0);
  const injection = encodeURIComponent("%' OR 1=1 --");
  const injectedSearch = await page.request.get(
    platformApiUrl(`/model-configurations?search=${injection}`),
    { headers: tenantHeaders },
  );
  expect(injectedSearch.status()).toBe(200);
  expect((await injectedSearch.json()) as { items: unknown[] }).toMatchObject({ items: [] });

  const trace = await page.request.fetch(platformApiUrl("/system/health"), {
    method: "TRACE",
    headers: ownerHeaders,
  });
  expect(trace.status()).toBe(405);
  expect(trace.headers()["content-type"]).toContain("text/html");
  expect(await trace.text()).not.toContain("Traceback");
});

test("renders stored hostile input as text and enforces viewer tenant isolation", async ({
  browser,
  page,
}) => {
  await page.goto("/employees");
  await expect(page.getByRole("heading", { name: "数字员工" })).toBeVisible();
  await page.getByRole("button", { name: "新建工作区" }).click();
  const workspaceDialog = page.getByRole("dialog", { name: "新建工作区" });
  await workspaceDialog.getByRole("textbox", { name: "工作区名称" }).fill(xssTenantName);
  const tenantResponsePromise = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/v1/tenants") && response.request().method() === "POST",
  );
  await workspaceDialog.getByRole("button", { name: /创\s*建/ }).click();
  const tenantResponse = await tenantResponsePromise;
  expect(tenantResponse.status()).toBe(201);
  const tenantId = ((await tenantResponse.json()) as { id: string }).id;
  await expect(page.getByText(`${xssTenantName} · 所有者`, { exact: true })).toBeVisible();
  await expect(page.locator('img[src="x"]')).toHaveCount(0);
  expect(
    await page.evaluate(
      () => (window as Window & { __commonAgentXss?: number }).__commonAgentXss ?? null,
    ),
  ).toBeNull();

  await page.getByRole("button", { name: "添加成员" }).click();
  const memberDialog = page.getByRole("dialog", { name: "添加工作区成员" });
  await memberDialog.getByRole("textbox", { name: "邮箱" }).fill(viewerEmail);
  await memberDialog.getByLabel("初始密码").fill(viewerPassword);
  const memberResponsePromise = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/api/v1/tenants/${tenantId}/members`) &&
      response.request().method() === "POST",
  );
  await memberDialog.getByRole("button", { name: "创建账号" }).click();
  const memberResponse = await memberResponsePromise;
  expect(memberResponse.status()).toBe(201);
  expect((await memberResponse.json()) as { role: string }).toMatchObject({ role: "viewer" });
  const recoveryDialog = page.getByRole("dialog", { name: "成员账号已创建" });
  await recoveryDialog.getByRole("button", { name: "我已保存" }).click();

  const viewerContext = await browser.newContext({
    baseURL: frontendUrl,
    ignoreHTTPSErrors: true,
  });
  try {
    const viewerPage = await viewerContext.newPage();
    await viewerPage.goto("/employees");
    await viewerPage.getByRole("textbox", { name: "邮箱" }).fill(viewerEmail);
    await viewerPage.getByLabel("密码").fill(viewerPassword);
    await viewerPage.getByRole("button", { name: /登\s*录/ }).click();
    await expect(viewerPage.getByRole("heading", { name: "数字员工" })).toBeVisible();
    await expect(viewerPage.getByText("当前工作区为只读模式")).toBeVisible();
    await expect(viewerPage.getByRole("button", { name: "创建数字员工" })).toBeDisabled();
    await expect(viewerPage.getByRole("button", { name: "新建工作区" })).toHaveCount(0);
    await expect(viewerPage.getByRole("button", { name: "添加成员" })).toHaveCount(0);

    const authorization = await viewerPage.evaluate(
      async ({ activeTenantId, forbiddenTenantId, modelId }) => {
        const sessionResponse = await fetch("/api/v1/auth/session");
        const session = (await sessionResponse.json()) as { csrf_token: string };
        const forbiddenWrite = await fetch("/api/v1/employees", {
          method: "POST",
          credentials: "same-origin",
          headers: {
            "Content-Type": "application/json",
            "X-CSRF-Token": session.csrf_token,
            "X-Tenant-ID": activeTenantId,
          },
          body: JSON.stringify({
            name: "viewer-forbidden-employee",
            description: "",
            system_prompt: "必须由正式后端拒绝。",
            default_model_configuration_id: modelId,
            knowledge_base_id: null,
            allowed_workflow_ids: [],
          }),
        });
        const crossTenantRead = await fetch("/api/v1/employees", {
          credentials: "same-origin",
          headers: { "X-Tenant-ID": forbiddenTenantId },
        });
        return {
          writeStatus: forbiddenWrite.status,
          writeBody: (await forbiddenWrite.json()) as { code: string },
          readStatus: crossTenantRead.status,
          readBody: (await crossTenantRead.json()) as { code: string },
        };
      },
      {
        activeTenantId: tenantId,
        forbiddenTenantId: defaultTenantId,
        modelId: missingModelId,
      },
    );
    expect(authorization.writeStatus).toBe(403);
    expect(authorization.writeBody).toMatchObject({ code: "tenant_write_forbidden" });
    expect(authorization.readStatus).toBe(403);
    expect(authorization.readBody).toMatchObject({ code: "tenant_access_denied" });
  } finally {
    await viewerContext.close();
  }

  const ownerHeaders = await platformWriteHeaders(page);
  const unknownOrganization = await page.request.post(platformApiUrl("/tenants"), {
    headers: ownerHeaders,
    data: {
      organization_id: "00000000-0000-4000-8000-ffffffffffff",
      name: "unauthorized-organization",
    },
  });
  await expectError(unknownOrganization, 403, "tenant_admin_forbidden");

  const tenantList = await page.request.get(platformApiUrl("/tenants"), {
    headers: platformHostHeaders(),
  });
  expect(tenantList.status()).toBe(200);
  expect((await tenantList.json()) as Array<{ id: string; organization_id: string }>).toEqual(
    expect.arrayContaining([
      expect.objectContaining({ id: tenantId, organization_id: defaultOrganizationId }),
    ]),
  );
});
