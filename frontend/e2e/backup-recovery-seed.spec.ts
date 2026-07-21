import { expect, test } from "./fixtures/auth";
import { selectEmployeeDefaultModel } from "./fixtures/models";
import path from "node:path";
import { fileURLToPath } from "node:url";

function requiredEnvironment(name: string): string {
  const value = process.env[name]?.trim();
  if (!value) throw new Error(`${name} is required`);
  return value;
}

const knowledgeBaseName = requiredEnvironment("COMMON_AGENT_E2E_RECOVERY_KNOWLEDGE_NAME");
const employeeName = requiredEnvironment("COMMON_AGENT_E2E_RECOVERY_EMPLOYEE_NAME");
const fixtureDirectory = path.join(path.dirname(fileURLToPath(import.meta.url)), "fixtures");

test("seeds the isolated disaster-recovery source through the formal UI", async ({ page }) => {
  test.setTimeout(240_000);
  await page.goto("/knowledge-bases");
  await expect(page.getByRole("heading", { name: "知识库" })).toBeVisible();
  await expect(page.getByText("后端正常")).toBeVisible();

  await page.getByRole("button", { name: "创建知识库" }).click();
  const knowledgeDialog = page.getByRole("dialog", { name: "创建知识库" });
  await knowledgeDialog.getByRole("textbox", { name: "名称" }).fill(knowledgeBaseName);
  await knowledgeDialog
    .getByRole("textbox", { name: "描述" })
    .fill("S10-06 独立备份恢复灾难演练");
  const createKnowledge = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/v1/knowledge-bases") &&
      response.request().method() === "POST",
  );
  await knowledgeDialog.getByRole("button", { name: "确认创建" }).click();
  expect((await createKnowledge).status()).toBe(201);

  await page
    .getByLabel("选择文档")
    .setInputFiles(path.join(fixtureDirectory, "generic-knowledge.txt"));
  const upload = page.waitForResponse(
    (response) =>
      response.url().includes("/documents") && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "上传文档" }).click();
  expect((await upload).status()).toBe(202);
  await expect(
    page.getByRole("row").filter({ hasText: "generic-knowledge.txt" }).getByText("已完成"),
  ).toBeVisible({ timeout: 180_000 });

  await page.getByRole("link", { name: "数字员工" }).click();
  await page.getByRole("button", { name: "创建数字员工" }).click();
  const employeeDialog = page.getByRole("dialog", { name: "创建数字员工" });
  await employeeDialog.getByRole("textbox", { name: "名称" }).fill(employeeName);
  await employeeDialog
    .getByRole("textbox", { name: "说明" })
    .fill("S10-06 恢复后必须保留的核心员工数据");
  await employeeDialog
    .getByRole("textbox", { name: "系统指令" })
    .fill("只依据已恢复的知识库回答。 ");
  await selectEmployeeDefaultModel(page, employeeDialog);
  await employeeDialog.getByRole("combobox", { name: "知识库" }).click();
  await page.getByTitle(knowledgeBaseName).click();
  const createEmployee = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/v1/employees") && response.request().method() === "POST",
  );
  await employeeDialog.getByRole("button", { name: "确认创建" }).click();
  expect((await createEmployee).status()).toBe(201);
  const employeeCard = page.locator(".employee-card").filter({ hasText: employeeName });
  await expect(employeeCard).toContainText(knowledgeBaseName);
});
