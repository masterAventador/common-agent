import { expect, test } from "./fixtures/auth";

function requiredEnvironment(name: string): string {
  const value = process.env[name]?.trim();
  if (!value) throw new Error(`${name} is required`);
  return value;
}

const knowledgeBaseName = requiredEnvironment("COMMON_AGENT_E2E_RECOVERY_KNOWLEDGE_NAME");
const employeeName = requiredEnvironment("COMMON_AGENT_E2E_RECOVERY_EMPLOYEE_NAME");
const ragflowPort = requiredEnvironment("COMMON_AGENT_E2E_RECOVERY_RAGFLOW_PORT");

test("verifies restored core data and RAGFlow references through the formal UI", async ({
  page,
}) => {
  const directRagFlowRequests: string[] = [];
  page.on("request", (request) => {
    if (new URL(request.url()).port === ragflowPort) directRagFlowRequests.push(request.url());
  });

  await page.goto("/knowledge-bases");
  await expect(page.getByRole("heading", { name: "知识库" })).toBeVisible();
  await expect(page.getByText("后端正常")).toBeVisible();
  await expect(page.locator(".knowledge-base-item", { hasText: knowledgeBaseName })).toBeVisible();
  await expect(page.getByRole("row").filter({ hasText: "generic-knowledge.txt" })).toContainText(
    "已完成",
  );

  await page.getByRole("link", { name: "数字员工" }).click();
  const employeeCard = page.locator(".employee-card").filter({ hasText: employeeName });
  await expect(employeeCard).toContainText("S10-06 恢复后必须保留的核心员工数据");
  await expect(employeeCard).toContainText(knowledgeBaseName);

  await page.getByRole("link", { name: "审计" }).click();
  await expect(page.getByRole("heading", { name: "审计与安全事件" })).toBeVisible();
  await expect(page.getByText("哈希链完整")).toBeVisible();
  expect(directRagFlowRequests).toEqual([]);
});
