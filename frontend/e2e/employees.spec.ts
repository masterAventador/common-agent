import { expect, test } from "@playwright/test";

function requiredEnvironment(name: string): string {
  const value = process.env[name]?.trim();
  if (!value) throw new Error(`${name} is required`);
  return value;
}

const employeeName = requiredEnvironment("COMMON_AGENT_E2E_EMPLOYEE_NAME");
const knowledgeBaseName = requiredEnvironment(
  "COMMON_AGENT_E2E_EMPLOYEE_KNOWLEDGE_NAME",
);

test("creates a generic employee, keeps its knowledge binding, and enters chat", async ({ page }) => {
  test.setTimeout(240_000);
  const directRagFlowRequests: string[] = [];
  page.on("request", (request) => {
    if (new URL(request.url()).port === "19380") directRagFlowRequests.push(request.url());
  });

  await page.goto("/knowledge-bases");
  await expect(page.getByRole("heading", { name: "知识库" })).toBeVisible();
  await expect(page.getByText("后端正常")).toBeVisible();

  await page.getByRole("button", { name: "创建知识库" }).click();
  const knowledgeDialog = page.getByRole("dialog", { name: "创建知识库" });
  await knowledgeDialog.getByRole("textbox", { name: "名称" }).fill(knowledgeBaseName);
  await knowledgeDialog
    .getByRole("textbox", { name: "描述" })
    .fill("E3-05 数字员工绑定的通用知识库");
  const knowledgeResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/v1/knowledge-bases") &&
      response.request().method() === "POST",
  );
  await knowledgeDialog.getByRole("button", { name: "确认创建" }).click();
  expect((await knowledgeResponse).status()).toBe(201);
  await expect(page.getByRole("button", { name: new RegExp(knowledgeBaseName) })).toBeVisible();

  await page.getByRole("link", { name: "数字员工" }).click();
  await expect(page.getByRole("heading", { name: "数字员工" })).toBeVisible();
  await page.getByRole("button", { name: "创建数字员工" }).click();
  const employeeDialog = page.getByRole("dialog", { name: "创建数字员工" });
  await employeeDialog.getByRole("textbox", { name: "名称" }).fill(employeeName);
  await employeeDialog
    .getByRole("textbox", { name: "说明" })
    .fill("E3-05 创建后的初始说明");
  await employeeDialog
    .getByRole("textbox", { name: "系统指令" })
    .fill("你是通用知识助理，只依据可靠资料回答。");
  await employeeDialog.getByRole("combobox", { name: "知识库" }).click();
  await page.getByTitle(knowledgeBaseName).click();

  const employeeResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/v1/employees") &&
      response.request().method() === "POST",
  );
  await employeeDialog.getByRole("button", { name: "确认创建" }).click();
  const createdResponse = await employeeResponse;
  expect(createdResponse.status()).toBe(201);
  const createdEmployee = (await createdResponse.json()) as { id: string };
  expect(createdEmployee.id).toEqual(expect.any(String));

  const employeeCard = page.locator(".employee-card").filter({ hasText: employeeName });
  await expect(employeeCard).toContainText(knowledgeBaseName);
  await expect(employeeCard).toContainText("E3-05 创建后的初始说明");

  await page.reload();
  await expect(employeeCard).toContainText(knowledgeBaseName);
  await employeeCard.getByRole("button", { name: `编辑 ${employeeName}` }).click();
  const editDialog = page.getByRole("dialog", { name: "编辑数字员工" });
  await expect(editDialog.getByText(knowledgeBaseName, { exact: true })).toBeVisible();
  await editDialog.getByRole("textbox", { name: "说明" }).fill("E3-05 刷新后更新的说明");
  const updatedResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/api/v1/employees/${createdEmployee.id}`) &&
      response.request().method() === "PUT",
  );
  await editDialog.getByRole("button", { name: "保存修改" }).click();
  expect((await updatedResponse).status()).toBe(200);
  await expect(employeeCard).toContainText("E3-05 刷新后更新的说明");
  await expect(employeeCard).toContainText(knowledgeBaseName);

  await page.reload();
  await expect(employeeCard).toContainText("E3-05 刷新后更新的说明");
  await expect(employeeCard).toContainText(knowledgeBaseName);
  await employeeCard.getByRole("button", { name: `与${employeeName}开始对话` }).click();

  await expect(page).toHaveURL(new RegExp(`/chat\\?employee_id=${createdEmployee.id}$`));
  await expect(page.getByRole("heading", { name: "AI 会话" })).toBeVisible();
  expect(directRagFlowRequests).toEqual([]);
});
