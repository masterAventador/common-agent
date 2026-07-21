import { expect, platformWriteHeaders, test } from "./fixtures/auth";

function requiredEnvironment(name: string): string {
  const value = process.env[name]?.trim();
  if (!value) throw new Error(`${name} is required`);
  return value;
}

const apiUrl = requiredEnvironment("COMMON_AGENT_E2E_API_URL").replace(/\/$/, "");
const frontendUrl = requiredEnvironment("COMMON_AGENT_E2E_FRONTEND_URL");
const tenantName = requiredEnvironment("COMMON_AGENT_E2E_TENANT_NAME");
const employeeName = requiredEnvironment("COMMON_AGENT_E2E_TENANT_EMPLOYEE_NAME");
const viewerEmail = requiredEnvironment("COMMON_AGENT_E2E_VIEWER_EMAIL");
const viewerPassword = requiredEnvironment("COMMON_AGENT_E2E_VIEWER_PASSWORD");
const defaultTenantId = "00000000-0000-4000-8000-000000000002";
const trustedOrigin = "http://127.0.0.1:18280";

test("creates an isolated workspace and enforces viewer read-only access", async ({
  browser,
  page,
}) => {
  await page.goto("/employees");
  await expect(page.getByRole("heading", { name: "数字员工" })).toBeVisible();
  await expect(page.getByText("默认工作区 · 所有者", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "新建工作区" }).click();
  const workspaceDialog = page.getByRole("dialog", { name: "新建工作区" });
  await workspaceDialog.getByRole("textbox", { name: "工作区名称" }).fill(tenantName);
  const createdTenantResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/v1/tenants") &&
      response.request().method() === "POST",
  );
  await workspaceDialog.getByRole("button", { name: "创建" }).click();
  const createdTenant = await createdTenantResponse;
  expect(createdTenant.status()).toBe(201);
  const tenantId = ((await createdTenant.json()) as { id: string }).id;
  await expect(page.getByText(`${tenantName} · 所有者`, { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "创建数字员工" }).click();
  const employeeDialog = page.getByRole("dialog", { name: "创建数字员工" });
  await employeeDialog.getByRole("textbox", { name: "名称" }).fill(employeeName);
  await employeeDialog
    .getByRole("textbox", { name: "说明" })
    .fill("S10-03 工作区隔离浏览器验收");
  await employeeDialog
    .getByRole("textbox", { name: "系统指令" })
    .fill("只处理当前工作区的数据。");
  const createdEmployeeResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/v1/employees") &&
      response.request().method() === "POST",
  );
  await employeeDialog.getByRole("button", { name: "确认创建" }).click();
  expect((await createdEmployeeResponse).status()).toBe(201);
  const employeeCard = page.locator(".employee-card", { hasText: employeeName });
  await expect(employeeCard).toBeVisible();

  const tenantSelector = page.getByRole("combobox", { name: "当前工作区" });
  await tenantSelector.click();
  await page.getByRole("option", { name: "默认工作区 · 所有者" }).click();
  await expect(employeeCard).toHaveCount(0);
  await tenantSelector.click();
  await page.getByRole("option", { name: `${tenantName} · 所有者` }).click();
  await expect(employeeCard).toBeVisible();

  await page.getByRole("button", { name: "添加成员" }).click();
  const memberDialog = page.getByRole("dialog", { name: "添加工作区成员" });
  await memberDialog.getByRole("textbox", { name: "邮箱" }).fill(viewerEmail);
  await memberDialog.getByLabel("初始密码").fill(viewerPassword);
  const memberResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/api/v1/tenants/${tenantId}/members`) &&
      response.request().method() === "POST",
  );
  await memberDialog.getByRole("button", { name: "创建账号" }).click();
  const provisioned = await memberResponse;
  expect(provisioned.status()).toBe(201);
  expect((await provisioned.json()) as { role: string }).toMatchObject({ role: "viewer" });
  const recoveryDialog = page.getByRole("dialog", { name: "成员账号已创建" });
  await expect(recoveryDialog).toContainText(viewerEmail);
  await recoveryDialog.getByRole("button", { name: "我已保存" }).click();

  const viewerContext = await browser.newContext({ baseURL: frontendUrl });
  try {
    const viewerPage = await viewerContext.newPage();
    await viewerPage.goto("/employees");
    await viewerPage.getByRole("textbox", { name: "邮箱" }).fill(viewerEmail);
    await viewerPage.getByLabel("密码").fill(viewerPassword);
    await viewerPage.getByRole("button", { name: /登\s*录/ }).click();
    await expect(viewerPage.getByRole("heading", { name: "数字员工" })).toBeVisible();
    await expect(viewerPage.getByText("当前工作区为只读模式")).toBeVisible();
    await expect(viewerPage.getByRole("button", { name: "创建数字员工" })).toBeDisabled();
    await expect(viewerPage.getByRole("button", { name: `编辑 ${employeeName}` })).toBeDisabled();
    await expect(viewerPage.getByRole("button", { name: `删除数字员工 ${employeeName}` })).toBeDisabled();
    await expect(viewerPage.getByRole("button", { name: "添加成员" })).toHaveCount(0);
    await expect(viewerPage.getByRole("button", { name: "新建工作区" })).toHaveCount(0);

    const sessionResponse = await viewerPage.request.get(`${apiUrl}/auth/session`);
    expect(sessionResponse.status()).toBe(200);
    const session = (await sessionResponse.json()) as { csrf_token: string };
    const forbiddenWrite = await viewerPage.request.post(`${apiUrl}/employees`, {
      headers: {
        Origin: trustedOrigin,
        "X-CSRF-Token": session.csrf_token,
        "X-Tenant-ID": tenantId,
      },
      data: {
        name: "viewer-forbidden-employee",
        description: "",
        system_prompt: "必须由后端拒绝。",
        knowledge_base_id: null,
        allowed_workflow_ids: [],
      },
    });
    expect(forbiddenWrite.status()).toBe(403);
    expect((await forbiddenWrite.json()) as { code: string }).toMatchObject({
      code: "tenant_write_forbidden",
    });

    const crossTenantRead = await viewerPage.request.get(`${apiUrl}/employees`, {
      headers: { "X-Tenant-ID": defaultTenantId },
    });
    expect(crossTenantRead.status()).toBe(403);
    expect((await crossTenantRead.json()) as { code: string }).toMatchObject({
      code: "tenant_access_denied",
    });
  } finally {
    await viewerContext.close();
  }

  const ownerHeaders = await platformWriteHeaders(page);
  const employeeId = ((await (await page.request.get(`${apiUrl}/employees`, {
    headers: { ...ownerHeaders, "X-Tenant-ID": tenantId },
  })).json()) as { items: Array<{ id: string; name: string }> }).items.find(
    (employee) => employee.name === employeeName,
  )?.id;
  expect(employeeId).toBeDefined();
  expect(
    (
      await page.request.delete(`${apiUrl}/employees/${employeeId}`, {
        headers: { ...ownerHeaders, "X-Tenant-ID": tenantId },
      })
    ).status(),
  ).toBe(204);
});
