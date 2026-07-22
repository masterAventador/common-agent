import type { Locator, Page } from "@playwright/test";

import { expect, test } from "./fixtures/auth";
import { selectEmployeeDefaultModel, selectWorkflowAiTarget } from "./fixtures/models";
import path from "node:path";
import { fileURLToPath } from "node:url";

function requiredEnvironment(name: string): string {
  const value = process.env[name]?.trim();
  if (!value) throw new Error(`${name} is required`);
  return value;
}

const knowledgeBaseName = requiredEnvironment("COMMON_AGENT_E2E_MVP_KNOWLEDGE_NAME");
const employeeName = requiredEnvironment("COMMON_AGENT_E2E_MVP_EMPLOYEE_NAME");
const workflowName = requiredEnvironment("COMMON_AGENT_E2E_MVP_WORKFLOW_NAME");
const fixtureDirectory = path.join(path.dirname(fileURLToPath(import.meta.url)), "fixtures");

async function dragNodeTo(
  page: Page,
  accessibleName: string,
  targetPosition: { x: number; y: number },
) {
  const canvas = page.getByRole("region", { name: "工作流画布" });
  await page.getByRole("button", { name: accessibleName }).dragTo(canvas, { targetPosition });
}

async function connectNodes(page: Page, sourceId: string, targetId: string) {
  const source: Locator = page
    .locator(`.react-flow__node[data-id="${sourceId}"]`)
    .locator(".react-flow__handle.source");
  const target: Locator = page
    .locator(`.react-flow__node[data-id="${targetId}"]`)
    .locator(".react-flow__handle.target");
  const sourceBox = await source.boundingBox();
  const targetBox = await target.boundingBox();
  if (!sourceBox || !targetBox) throw new Error(`无法连接 ${sourceId} -> ${targetId}`);
  await page.mouse.move(sourceBox.x + sourceBox.width / 2, sourceBox.y + sourceBox.height / 2);
  await page.mouse.down();
  await page.mouse.move(targetBox.x + targetBox.width / 2, targetBox.y + targetBox.height / 2, {
    steps: 12,
  });
  await page.mouse.up();
}

async function sendMessage(page: Page, content: string) {
  await page.getByRole("textbox", { name: "消息输入" }).fill(content);
  const response = page.waitForResponse(
    (candidate) =>
      (candidate.url().endsWith("/api/v1/conversation-turns") ||
        candidate.url().includes("/messages")) &&
      candidate.request().method() === "POST",
  );
  await page.getByRole("button", { name: "发送消息" }).click();
  expect((await response).status()).toBe(202);
}

test("completes the whole MVP through one isolated real user journey", async ({
  page,
}) => {
  test.setTimeout(480_000);
  await page.setViewportSize({ width: 1720, height: 1000 });
  const directExternalRequests: string[] = [];
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (url.port === "19380" || url.hostname.endsWith("aliyuncs.com")) {
      directExternalRequests.push(request.url());
    }
  });

  await page.goto("/knowledge-bases");
  await expect(page.getByRole("heading", { name: "知识库" })).toBeVisible();
  await expect(page.getByText("后端正常")).toBeVisible();
  await expect(page.getByText("百炼已配置")).toBeVisible();
  await expect(page.getByText("RAGFlow 正常")).toBeVisible();
  await expect(page.getByRole("button", { name: "创建知识库" })).toBeVisible();

  await page.getByRole("button", { name: "创建知识库" }).click();
  const knowledgeDialog = page.getByRole("dialog", { name: "创建知识库" });
  await knowledgeDialog.getByRole("textbox", { name: "名称" }).fill(knowledgeBaseName);
  await knowledgeDialog
    .getByRole("textbox", { name: "描述" })
    .fill("Q6-04 从空业务数据开始的 MVP 总验收知识库");
  const knowledgeResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/v1/knowledge-bases") &&
      response.request().method() === "POST",
  );
  await knowledgeDialog.getByRole("button", { name: "确认创建" }).click();
  expect((await knowledgeResponse).status()).toBe(201);
  const createdKnowledgeBase = page
    .locator("button.knowledge-base-item")
    .filter({ hasText: knowledgeBaseName });
  await expect(createdKnowledgeBase).toBeVisible();
  await createdKnowledgeBase.click();
  await expect(createdKnowledgeBase).toHaveClass(/is-active/);

  await page
    .getByLabel("选择或拖拽文档")
    .setInputFiles(path.join(fixtureDirectory, "generic-knowledge.txt"));
  const uploadResponse = page.waitForResponse(
    (response) =>
      response.url().includes("/documents") && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "开始上传" }).click();
  expect((await uploadResponse).status()).toBe(202);
  const documentRow = page.getByRole("row").filter({ hasText: "generic-knowledge.txt" });
  await expect(documentRow.getByText("已完成")).toBeVisible({ timeout: 180_000 });

  await page.getByRole("link", { name: "数字员工" }).click();
  await expect(page.getByText(employeeName)).toHaveCount(0);
  await page.getByRole("button", { name: "创建数字员工" }).click();
  const employeeDialog = page.getByRole("dialog", { name: "创建数字员工" });
  await employeeDialog.getByRole("textbox", { name: "名称" }).fill(employeeName);
  await employeeDialog
    .getByRole("textbox", { name: "说明" })
    .fill("Q6-04 同时绑定知识库与工作流的通用数字员工");
  await employeeDialog
    .getByRole("textbox", { name: "系统指令" })
    .fill("只依据绑定知识库的可靠资料回答，并保留资料中的验收标记。");
  await selectEmployeeDefaultModel(page, employeeDialog);
  await employeeDialog.getByRole("combobox", { name: "知识库" }).click();
  await page.getByTitle(knowledgeBaseName).click();
  const employeeResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/v1/employees") && response.request().method() === "POST",
  );
  await employeeDialog.getByRole("button", { name: "确认创建" }).click();
  const createdEmployeeResponse = await employeeResponse;
  expect(createdEmployeeResponse.status()).toBe(201);
  const employee = (await createdEmployeeResponse.json()) as { id: string };
  const employeeCard = page.locator(".employee-card").filter({ hasText: employeeName });
  await expect(employeeCard).toContainText(knowledgeBaseName);
  await employeeCard.getByRole("button", { name: `与${employeeName}开始对话` }).click();

  await expect(page).toHaveURL(new RegExp(`/chat\\?employee_id=${employee.id}$`));
  await sendMessage(
    page,
    "第一轮：根据绑定知识库回答 Common Agent 是什么，并明确输出真实两轮验收标记。",
  );
  const assistantAnswers = page.locator(".chat-message.is-assistant .chat-message-content");
  await expect(assistantAnswers).toHaveCount(1);
  await expect(assistantAnswers.first()).toContainText("COMMON_AGENT_REAL_TWO_TURN_OK", {
    timeout: 180_000,
  });
  await expect(page.getByText("generic-knowledge.txt").first()).toBeVisible();

  await sendMessage(
    page,
    "第二轮：结合上一轮上下文和同一知识库，只输出真实两轮验收标记。",
  );
  await expect(assistantAnswers).toHaveCount(2);
  await expect(assistantAnswers.last()).toContainText("COMMON_AGENT_REAL_TWO_TURN_OK", {
    timeout: 180_000,
  });
  await expect(page.getByText("generic-knowledge.txt").last()).toBeVisible();
  await page.reload();
  await expect(assistantAnswers).toHaveCount(2);
  await expect(assistantAnswers.last()).toContainText("COMMON_AGENT_REAL_TWO_TURN_OK");

  await page.getByRole("link", { name: "工作流" }).click();
  await expect(page.getByText("还没有已保存工作流")).toBeVisible();
  await page.getByRole("textbox", { name: "工作流名称" }).fill(workflowName);
  await page
    .getByRole("textbox", { name: "工作流说明" })
    .fill("Q6-04 知识检索与 AI 对话工作流");
  await dragNodeTo(page, "添加开始节点", { x: 90, y: 180 });
  await dragNodeTo(page, "添加知识检索节点", { x: 300, y: 180 });
  await page.getByRole("combobox", { name: "节点知识库" }).click();
  await page.getByTitle(knowledgeBaseName).click();
  await dragNodeTo(page, "添加AI 对话节点", { x: 510, y: 180 });
  await page
    .getByRole("textbox", { name: "节点提示词" })
    .fill("只依据工作流检索到的可靠知识，只输出用户要求的验收标记。");
  await selectWorkflowAiTarget(page, "平台默认模型");
  await dragNodeTo(page, "添加结束节点", { x: 720, y: 180 });
  await expect(page.locator(".react-flow__node")).toHaveCount(4);
  await connectNodes(page, "start-1", "knowledge_retrieval-1");
  await connectNodes(page, "knowledge_retrieval-1", "ai_chat-1");
  await connectNodes(page, "ai_chat-1", "end-1");
  await expect(page.locator(".react-flow__edge")).toHaveCount(3);
  const workflowResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/v1/workflows") && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "保存工作流" }).click();
  const createdWorkflowResponse = await workflowResponse;
  expect(createdWorkflowResponse.status()).toBe(201);
  const workflow = (await createdWorkflowResponse.json()) as { id: string };
  await expect(page.getByText("已保存")).toBeVisible();

  const manualMarker = "查询并只输出 COMMON_AGENT_REAL_TWO_TURN_OK";
  await page.getByRole("textbox", { name: "工作流运行输入" }).fill(manualMarker);
  const manualRunResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/api/v1/workflows/${workflow.id}/runs`) &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "运行工作流" }).click();
  expect((await manualRunResponse).status()).toBe(202);
  await expect(page.getByText("运行完成")).toBeVisible({ timeout: 180_000 });
  await expect(page.locator(".workflow-run-output")).toContainText(
    "COMMON_AGENT_REAL_TWO_TURN_OK",
  );

  await page.getByRole("link", { name: "数字员工" }).click();
  await employeeCard.getByRole("button", { name: `编辑 ${employeeName}` }).click();
  const editDialog = page.getByRole("dialog", { name: "编辑数字员工" });
  await editDialog
    .getByRole("textbox", { name: "系统指令" })
    .fill(
      "用户要求执行工作流时，必须调用唯一授权工作流一次；把 input: 后文本原样作为 input，完成后只回答 output。",
    );
  await editDialog.getByRole("combobox", { name: "允许工作流" }).click();
  await page.getByTitle(workflowName).click();
  await page.keyboard.press("Escape");
  const updatedEmployeeResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/api/v1/employees/${employee.id}`) &&
      response.request().method() === "PUT",
  );
  await editDialog.getByRole("button", { name: "保存修改" }).click();
  expect((await updatedEmployeeResponse).status()).toBe(200);
  await expect(employeeCard).toContainText("已授权 1 个工作流");
  await expect(employeeCard).toContainText(knowledgeBaseName);
  await employeeCard.getByRole("button", { name: `与${employeeName}开始对话` }).click();
  await expect(assistantAnswers).toHaveCount(2);

  const employeeMarker = `COMMON_AGENT_Q6_04_WORKFLOW_${Date.now()}`;
  await sendMessage(page, `执行唯一授权工作流，input:${employeeMarker}`);
  const runCards = page.locator(".chat-workflow-runs");
  await expect(runCards.getByText(workflowName)).toBeVisible({ timeout: 180_000 });
  await runCards.getByText(workflowName).click();
  await expect(runCards).toContainText(employeeMarker);
  await expect(runCards.getByText("已完成")).toBeVisible();

  await page.reload();
  await expect(assistantAnswers).toHaveCount(3);
  await expect(runCards.getByText(workflowName)).toBeVisible();
  await runCards.getByText(workflowName).click();
  await expect(runCards).toContainText(employeeMarker);
  await runCards.getByRole("button", { name: "查看运行详情" }).click();
  await expect(page).toHaveURL(/\/workflows\?run_id=[0-9a-f-]{36}$/);
  await expect(page.getByText("运行完成")).toBeVisible();
  await expect(page.locator(".workflow-run-output")).toContainText(
    "COMMON_AGENT_REAL_TWO_TURN_OK",
  );
  expect(directExternalRequests).toEqual([]);
});
