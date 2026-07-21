import { expect, test } from "./fixtures/auth";
import { selectEmployeeDefaultModel } from "./fixtures/models";
import path from "node:path";
import { fileURLToPath } from "node:url";

function requiredEnvironment(name: string): string {
  const value = process.env[name]?.trim();
  if (!value) throw new Error(`${name} is required`);
  return value;
}

const employeeName = requiredEnvironment("COMMON_AGENT_E2E_EMPLOYEE_NAME");
const knowledgeBaseName = requiredEnvironment(
  "COMMON_AGENT_E2E_EMPLOYEE_KNOWLEDGE_NAME",
);
const fixtureDirectory = path.join(path.dirname(fileURLToPath(import.meta.url)), "fixtures");

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
  await expect(page.locator(".knowledge-base-item", { hasText: knowledgeBaseName })).toBeVisible();

  await page
    .getByLabel("选择文档")
    .setInputFiles(path.join(fixtureDirectory, "generic-knowledge.txt"));
  const uploadedResponse = page.waitForResponse(
    (response) =>
      response.url().includes("/documents") && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "上传文档" }).click();
  expect((await uploadedResponse).status()).toBe(202);
  const documentRow = page.getByRole("row").filter({ hasText: "generic-knowledge.txt" });
  await expect(documentRow.getByText("已完成")).toBeVisible({ timeout: 180_000 });

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
  await selectEmployeeDefaultModel(page, employeeDialog);
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
  await expect(page.getByRole("region", { name: "会话列表" })).toBeVisible();
  await expect(page.getByRole("region", { name: "消息区域" })).toBeVisible();
  const employeeRegion = page.getByRole("region", { name: "数字员工信息" });
  await expect(employeeRegion).toContainText(employeeName);
  await expect(employeeRegion).toContainText("已绑定知识库");

  await expect(page.getByRole("heading", { name: "新会话" })).toBeVisible();

  const prompt =
    "根据已绑定知识库回答 Common Agent 是什么，明确写出真实两轮验收标记，然后从 1 数到 200，每个数字用逗号分隔。";
  await page.getByRole("textbox", { name: "消息输入" }).fill(prompt);
  const sentResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/v1/conversation-turns") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "发送消息" }).click();
  expect((await sentResponse).status()).toBe(202);
  await expect(page.locator(".chat-message.is-assistant .chat-message-content")).not.toBeEmpty();

  const stoppedResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/stop") && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "停止生成" }).click();
  expect((await stoppedResponse).status()).toBe(202);
  await expect(page.getByText("已停止")).toBeVisible();

  const retriedResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/retry") && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "重试回答" }).click();
  expect((await retriedResponse).status()).toBe(202);
  await expect(page.getByText("正在生成")).toHaveCount(0, { timeout: 180_000 });
  const completedAnswer = page.locator(".chat-message.is-assistant .chat-message-content");
  await expect(completedAnswer).not.toBeEmpty();
  await expect(completedAnswer).toContainText("COMMON_AGENT_REAL_TWO_TURN_OK");
  await expect(page.getByText("引用资料 1")).toBeVisible();
  await expect(page.getByText("generic-knowledge.txt")).toBeVisible();

  await page
    .getByRole("textbox", { name: "消息输入" })
    .fill("第二轮：根据上一轮上下文和知识库，只输出你上一轮回答过的真实两轮验收标记。");
  const secondTurnResponse = page.waitForResponse(
    (response) =>
      response.url().includes("/messages") && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "发送消息" }).click();
  expect((await secondTurnResponse).status()).toBe(202);
  const assistantAnswers = page.locator(".chat-message.is-assistant .chat-message-content");
  await expect(assistantAnswers).toHaveCount(2);
  await expect(assistantAnswers.last()).toContainText("COMMON_AGENT_REAL_TWO_TURN_OK", {
    timeout: 180_000,
  });
  await expect(page.getByText("generic-knowledge.txt").last()).toBeVisible();
  const persistedAnswer = (await assistantAnswers.last().textContent())?.trim();
  expect(persistedAnswer).toBeTruthy();

  await page.reload();
  await expect(page.getByRole("heading", { name: prompt })).toBeVisible();
  await expect(assistantAnswers.last()).toContainText(persistedAnswer!);
  await expect(page.getByText("generic-knowledge.txt").last()).toBeVisible();
  expect(directRagFlowRequests).toEqual([]);
});
