import type { Locator, Page } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test } from "./fixtures/auth";
import { selectEmployeeDefaultModel } from "./fixtures/models";

function requiredEnvironment(name: string): string {
  const value = process.env[name]?.trim();
  if (!value) throw new Error(`${name} is required`);
  return value;
}

const knowledgeBaseName = requiredEnvironment("COMMON_AGENT_E2E_DELETE_KNOWLEDGE_NAME");
const employeeName = requiredEnvironment("COMMON_AGENT_E2E_DELETE_EMPLOYEE_NAME");
const workflowName = requiredEnvironment("COMMON_AGENT_E2E_DELETE_WORKFLOW_NAME");
const fixtureDirectory = path.join(path.dirname(fileURLToPath(import.meta.url)), "fixtures");

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

async function deleteFromPage(
  page: Page,
  resourceKind: string,
  resourceName: string,
  responsePath: string,
) {
  await page.getByRole("button", { name: `删除${resourceKind} ${resourceName}` }).click();
  const dialog = page.getByRole("dialog", { name: `删除${resourceKind}“${resourceName}”？` });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText("此操作不可恢复。")).toBeVisible();
  const response = page.waitForResponse(
    (candidate) =>
      candidate.url().includes(responsePath) && candidate.request().method() === "DELETE",
  );
  await dialog
    .getByRole("button", { name: `确认删除${resourceKind} ${resourceName}` })
    .click();
  return response;
}

async function clearSelect(combobox: Locator) {
  const select = combobox.locator(
    "xpath=ancestor::*[contains(concat(' ', normalize-space(@class), ' '), ' ant-select ')][1]",
  );
  await select.hover();
  await select.locator(".ant-select-clear").click();
  await expect(select.locator(".ant-select-selection-item")).toHaveCount(0);
}

test("blocks live references, unbinds them, and deletes all four resources through the UI", async ({
  page,
}) => {
  test.setTimeout(360_000);
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
  await page.getByRole("button", { name: "创建知识库" }).click();
  const knowledgeDialog = page.getByRole("dialog", { name: "创建知识库" });
  await knowledgeDialog.getByRole("textbox", { name: "名称" }).fill(knowledgeBaseName);
  await knowledgeDialog
    .getByRole("textbox", { name: "描述" })
    .fill("U9-02 引用安全删除真实页面验收");
  const knowledgeResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/v1/knowledge-bases") &&
      response.request().method() === "POST",
  );
  await knowledgeDialog.getByRole("button", { name: "确认创建" }).click();
  const createdKnowledgeResponse = await knowledgeResponse;
  expect(createdKnowledgeResponse.status()).toBe(201);
  const knowledgeBase = (await createdKnowledgeResponse.json()) as { id: string };

  await page
    .getByLabel("选择文档")
    .setInputFiles(path.join(fixtureDirectory, "generic-knowledge.txt"));
  const uploadResponse = page.waitForResponse(
    (response) =>
      response.url().includes("/documents") && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "上传文档" }).click();
  expect((await uploadResponse).status()).toBe(202);
  await expect(
    page.getByRole("row").filter({ hasText: "generic-knowledge.txt" }).getByText("已完成"),
  ).toBeVisible({ timeout: 180_000 });

  await page.getByRole("link", { name: "工作流" }).click();
  await page.getByRole("button", { name: "新建工作流" }).click();
  await page.getByRole("textbox", { name: "工作流名称" }).fill(workflowName);
  await page.getByRole("textbox", { name: "工作流说明" }).fill("U9-02 知识库引用工作流");
  await page.getByRole("button", { name: "添加开始节点" }).click();
  await page.getByRole("button", { name: "添加知识检索节点" }).click();
  await page.getByRole("combobox", { name: "节点知识库" }).click();
  await page.getByTitle(knowledgeBaseName).click();
  await page.getByRole("button", { name: "添加结束节点" }).click();
  await connectNodes(page, "start-1", "knowledge_retrieval-1");
  await connectNodes(page, "knowledge_retrieval-1", "end-1");
  const workflowResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/v1/workflows") && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "保存工作流" }).click();
  const createdWorkflowResponse = await workflowResponse;
  expect(createdWorkflowResponse.status()).toBe(201);
  const workflow = (await createdWorkflowResponse.json()) as { id: string };
  await expect(page.getByText("已保存")).toBeVisible();

  await page.getByRole("link", { name: "数字员工" }).click();
  await page.getByRole("button", { name: "创建数字员工" }).click();
  const employeeDialog = page.getByRole("dialog", { name: "创建数字员工" });
  await employeeDialog.getByRole("textbox", { name: "名称" }).fill(employeeName);
  await employeeDialog.getByRole("textbox", { name: "说明" }).fill("U9-02 引用删除验收员工");
  await employeeDialog
    .getByRole("textbox", { name: "系统指令" })
    .fill("只用于资源删除引用验收。");
  await selectEmployeeDefaultModel(page, employeeDialog);
  await employeeDialog.getByRole("combobox", { name: "知识库" }).click();
  await page.getByTitle(knowledgeBaseName).click();
  await employeeDialog.getByRole("combobox", { name: "允许工作流" }).click();
  await page.getByTitle(workflowName).click();
  await page.keyboard.press("Escape");
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
  await expect(employeeCard).toContainText("已授权 1 个工作流");

  await employeeCard.getByRole("button", { name: `与${employeeName}开始对话` }).click();
  const conversationTitle = "建立资源引用并只回复已建立";
  await page.getByRole("textbox", { name: "消息输入" }).fill(conversationTitle);
  const conversationResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/v1/conversation-turns") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "发送消息" }).click();
  const createdConversationResponse = await conversationResponse;
  expect(createdConversationResponse.status()).toBe(202);
  const conversation = (await createdConversationResponse.json()) as {
    conversation: { id: string };
  };

  await page.getByRole("link", { name: "数字员工" }).click();
  const employeeBlocked = await deleteFromPage(
    page,
    "数字员工",
    employeeName,
    `/api/v1/employees/${employee.id}`,
  );
  expect((await employeeBlocked).status()).toBe(409);
  await expect(
    page.getByText("该数字员工仍被会话引用，请先在 AI 会话页删除相关会话。"),
  ).toBeVisible();

  await page.getByRole("link", { name: "工作流" }).click();
  await page.getByRole("button", { name: `选择工作流 ${workflowName}` }).click();
  const workflowBlocked = await deleteFromPage(
    page,
    "工作流",
    workflowName,
    `/api/v1/workflows/${workflow.id}`,
  );
  expect((await workflowBlocked).status()).toBe(409);
  await expect(
    page.getByText("该工作流仍在数字员工允许列表中，请先在数字员工页解除授权。"),
  ).toBeVisible();

  await page.getByRole("link", { name: "知识库" }).click();
  await page
    .locator(".knowledge-base-item", { hasText: knowledgeBaseName })
    .click();
  const employeeKnowledgeBlocked = await deleteFromPage(
    page,
    "知识库",
    knowledgeBaseName,
    `/api/v1/knowledge-bases/${knowledgeBase.id}`,
  );
  expect((await employeeKnowledgeBlocked).status()).toBe(409);
  await expect(
    page.getByText("该知识库仍被数字员工绑定，请先在数字员工页解除绑定。"),
  ).toBeVisible();

  await page.getByRole("link", { name: "数字员工" }).click();
  await employeeCard.getByRole("button", { name: `编辑 ${employeeName}` }).click();
  const editDialog = page.getByRole("dialog", { name: "编辑数字员工" });
  await clearSelect(editDialog.getByRole("combobox", { name: "知识库" }));
  await clearSelect(editDialog.getByRole("combobox", { name: "允许工作流" }));
  const updatedEmployeeResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/api/v1/employees/${employee.id}`) &&
      response.request().method() === "PUT",
  );
  await editDialog.getByRole("button", { name: "保存修改" }).click();
  expect((await updatedEmployeeResponse).status()).toBe(200);
  await expect(employeeCard).toContainText("未绑定知识库");
  await expect(employeeCard).toContainText("未授权工作流");

  await page.getByRole("link", { name: "知识库" }).click();
  await page
    .locator(".knowledge-base-item", { hasText: knowledgeBaseName })
    .click();
  const workflowKnowledgeBlocked = await deleteFromPage(
    page,
    "知识库",
    knowledgeBaseName,
    `/api/v1/knowledge-bases/${knowledgeBase.id}`,
  );
  expect((await workflowKnowledgeBlocked).status()).toBe(409);
  await expect(
    page.getByText("该知识库仍被工作流节点引用，请先修改或删除相关工作流。"),
  ).toBeVisible();

  await page.getByRole("link", { name: "工作流" }).click();
  await page.getByRole("button", { name: `选择工作流 ${workflowName}` }).click();
  const deletedWorkflow = await deleteFromPage(
    page,
    "工作流",
    workflowName,
    `/api/v1/workflows/${workflow.id}`,
  );
  expect((await deletedWorkflow).status()).toBe(204);
  await expect(page.getByText(`工作流“${workflowName}”已删除`)).toBeVisible();
  await page.reload();
  await expect(page.getByRole("button", { name: `选择工作流 ${workflowName}` })).toHaveCount(0);

  await page.getByRole("link", { name: "知识库" }).click();
  await page
    .locator(".knowledge-base-item", { hasText: knowledgeBaseName })
    .click();
  const deletedKnowledge = await deleteFromPage(
    page,
    "知识库",
    knowledgeBaseName,
    `/api/v1/knowledge-bases/${knowledgeBase.id}`,
  );
  expect((await deletedKnowledge).status()).toBe(204);
  await expect(page.getByText(`知识库“${knowledgeBaseName}”已删除`)).toBeVisible();
  await page.reload();
  await expect(page.locator(".knowledge-base-item", { hasText: knowledgeBaseName })).toHaveCount(
    0,
  );

  await page.goto(
    `/chat?employee_id=${employee.id}&conversation_id=${conversation.conversation.id}`,
  );
  await expect(page.getByRole("heading", { name: conversationTitle })).toBeVisible();
  const deletedConversation = await deleteFromPage(
    page,
    "会话",
    conversationTitle,
    `/api/v1/conversations/${conversation.conversation.id}`,
  );
  expect((await deletedConversation).status()).toBe(204);
  await expect(page.getByText(`会话“${conversationTitle}”已删除`)).toBeVisible();
  await expect(page.getByText("还没有会话")).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole("button", { name: `打开会话 ${conversationTitle}` }),
  ).toHaveCount(0);

  await page.getByRole("link", { name: "数字员工" }).click();
  const deletedEmployee = await deleteFromPage(
    page,
    "数字员工",
    employeeName,
    `/api/v1/employees/${employee.id}`,
  );
  expect((await deletedEmployee).status()).toBe(204);
  await expect(page.getByText(`数字员工“${employeeName}”已删除`)).toBeVisible();
  await page.reload();
  await expect(page.locator(".employee-card").filter({ hasText: employeeName })).toHaveCount(0);

  expect(directExternalRequests).toEqual([]);
});
