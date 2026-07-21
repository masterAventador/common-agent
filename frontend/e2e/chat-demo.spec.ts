import { expect, test } from "./fixtures/auth";
import path from "node:path";
import { fileURLToPath } from "node:url";

function requiredEnvironment(name: string): string {
  const value = process.env[name]?.trim();
  if (!value) throw new Error(`${name} is required`);
  return value;
}

const employeeName = requiredEnvironment("COMMON_AGENT_DEMO_E2E_EMPLOYEE_NAME");
const knowledgeBaseName = requiredEnvironment("COMMON_AGENT_DEMO_E2E_KNOWLEDGE_NAME");
const fixtureDirectory = path.join(path.dirname(fileURLToPath(import.meta.url)), "fixtures");

test("runs two cited turns and recovers an interrupted reply through the formal demo path", async ({
  page,
}) => {
  test.setTimeout(120_000);
  const directExternalRequests: string[] = [];
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (url.port === "19380" || url.hostname.endsWith("aliyuncs.com")) {
      directExternalRequests.push(request.url());
    }
  });

  await page.goto("/knowledge-bases");
  await expect(page.getByText("演示模式")).toBeVisible();
  await page.getByRole("button", { name: "创建知识库" }).click();
  const knowledgeDialog = page.getByRole("dialog", { name: "创建知识库" });
  await knowledgeDialog.getByRole("textbox", { name: "名称" }).fill(knowledgeBaseName);
  await knowledgeDialog.getByRole("textbox", { name: "描述" }).fill("A4-08 固定知识适配器");
  const createdKnowledge = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/v1/knowledge-bases") &&
      response.request().method() === "POST",
  );
  await knowledgeDialog.getByRole("button", { name: "确认创建" }).click();
  expect((await createdKnowledge).status()).toBe(201);

  await page
    .getByLabel("选择文档")
    .setInputFiles(path.join(fixtureDirectory, "demo-chat-knowledge.txt"));
  const uploadedDocument = page.waitForResponse(
    (response) =>
      response.url().includes("/documents") && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "上传文档" }).click();
  expect((await uploadedDocument).status()).toBe(202);
  const documentRow = page.getByRole("row").filter({ hasText: "demo-chat-knowledge.txt" });
  await expect(documentRow.getByText("已完成")).toBeVisible();

  await page.getByRole("link", { name: "数字员工" }).click();
  await page.getByRole("button", { name: "创建数字员工" }).click();
  const employeeDialog = page.getByRole("dialog", { name: "创建数字员工" });
  await employeeDialog.getByRole("textbox", { name: "名称" }).fill(employeeName);
  await employeeDialog.getByRole("textbox", { name: "说明" }).fill("A4-08 Demo 数字员工");
  await employeeDialog
    .getByRole("textbox", { name: "系统指令" })
    .fill("使用固定知识适配器回答，并保留连续会话上下文。");
  await employeeDialog.getByRole("combobox", { name: "知识库" }).click();
  await page.getByTitle(knowledgeBaseName).click();
  const createdEmployeeResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/v1/employees") && response.request().method() === "POST",
  );
  await employeeDialog.getByRole("button", { name: "确认创建" }).click();
  const createdEmployee = (await (await createdEmployeeResponse).json()) as { id: string };

  const employeeCard = page.locator(".employee-card").filter({ hasText: employeeName });
  await employeeCard.getByRole("button", { name: `与${employeeName}开始对话` }).click();
  await page.getByRole("button", { name: "新建会话" }).click();
  await expect(page.getByRole("heading", { name: "新会话" })).toBeVisible();

  const input = page.getByRole("textbox", { name: "消息输入" });
  await input.fill("第一轮：演示知识标记是什么？");
  await page.getByRole("button", { name: "发送消息" }).click();
  const assistantMessages = page.locator(".chat-message.is-assistant .chat-message-content");
  await expect(assistantMessages.last()).toContainText("第 1 轮");
  await expect(page.getByText("demo-chat-knowledge.txt").last()).toBeVisible();

  await input.fill("第二轮：你还记得上一轮吗？");
  await page.getByRole("button", { name: "发送消息" }).click();
  await expect(assistantMessages.last()).toContainText("第 2 轮");
  await expect(assistantMessages.last()).toContainText("上一轮");
  await expect(page.getByText("demo-chat-knowledge.txt").last()).toBeVisible();

  await input.fill("请演示一次断流后恢复");
  await page.getByRole("button", { name: "发送消息" }).click();
  await expect(assistantMessages.last()).toContainText("断流前保留的演示内容");
  await expect(page.getByText("生成失败")).toBeVisible();
  const retryResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/retry") && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "重试回答" }).click();
  expect((await retryResponse).status()).toBe(202);
  await expect(assistantMessages.last()).toContainText("第 3 轮");
  await expect(page.getByText("生成失败")).toHaveCount(0);
  await expect(page.getByText("demo-chat-knowledge.txt").last()).toBeVisible();

  const finalAnswer = (await assistantMessages.last().textContent())?.trim();
  expect(finalAnswer).toBeTruthy();
  await page.reload();
  await expect(page.getByText("演示模式")).toBeVisible();
  await expect(assistantMessages.last()).toContainText(finalAnswer!);
  await expect(page.getByText("demo-chat-knowledge.txt").last()).toBeVisible();
  expect(createdEmployee.id).toEqual(expect.any(String));
  expect(directExternalRequests).toEqual([]);
});
