import { expect, platformWriteHeaders, test } from "./fixtures/auth";

function requiredEnvironment(name: string): string {
  const value = process.env[name]?.trim();
  if (!value) throw new Error(`${name} is required`);
  return value;
}

const apiUrl = requiredEnvironment("COMMON_AGENT_E2E_API_URL").replace(/\/$/, "");
const employeeName = requiredEnvironment("COMMON_AGENT_E2E_AUDIT_EMPLOYEE_NAME");

test("records and verifies an owner-visible metadata-only audit event", async ({ page }) => {
  await page.goto("/employees");
  await expect(page.getByRole("heading", { name: "数字员工" })).toBeVisible();

  await page.getByRole("button", { name: "创建数字员工" }).click();
  const dialog = page.getByRole("dialog", { name: "创建数字员工" });
  await dialog.getByRole("textbox", { name: "名称" }).fill(employeeName);
  await dialog.getByRole("textbox", { name: "说明" }).fill("S10-04 浏览器审计验收");
  await dialog
    .getByRole("textbox", { name: "系统指令" })
    .fill("请求正文和凭据绝不能进入审计记录。");
  const createResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/v1/employees") &&
      response.request().method() === "POST",
  );
  await dialog.getByRole("button", { name: "确认创建" }).click();
  const created = await createResponse;
  expect(created.status()).toBe(201);
  const employee = (await created.json()) as { id: string };

  await page.getByRole("link", { name: "审计与安全事件" }).click();
  await expect(page.getByRole("heading", { name: "审计与安全事件" })).toBeVisible();
  await expect(page.getByText("哈希链完整")).toBeVisible();
  await expect(page.getByText(/至少保留 365 天/)).toBeVisible();

  await page.getByRole("combobox", { name: "资源类型" }).click();
  await page.getByText("employee", { exact: true }).last().click();
  await page.getByRole("textbox", { name: "资源 ID" }).fill(employee.id);
  const filteredResponse = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return url.pathname.endsWith("/api/v1/audit-events") && url.searchParams.has("resource_id");
  });
  await page.getByRole("button", { name: /查\s*询/ }).click();
  expect((await filteredResponse).status()).toBe(200);
  await expect(page.getByText("数字员工创建")).toBeVisible();
  await expect(page.getByText(employee.id)).toBeVisible();
  await expect(page.getByText("请求正文和凭据绝不能进入审计记录。")).toHaveCount(0);

  const headers = await platformWriteHeaders(page);
  const deleted = await page.request.delete(`${apiUrl}/employees/${employee.id}`, { headers });
  expect(deleted.status()).toBe(204);
});
