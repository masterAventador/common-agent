import type { Locator, Page } from "@playwright/test";

import { expect, test } from "./fixtures/auth";
import { selectWorkflowAiTarget } from "./fixtures/models";

function requiredEnvironment(name: string): string {
  const value = process.env[name]?.trim();
  if (!value) throw new Error(`${name} is required`);
  return value;
}

const workflowName = requiredEnvironment("COMMON_AGENT_E2E_WORKFLOW_NAME");
const knowledgeBaseName = requiredEnvironment("COMMON_AGENT_E2E_WORKFLOW_KNOWLEDGE_NAME");

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

test("builds, validates, persists, and reloads a workflow through the real designer", async ({
  page,
}) => {
  test.setTimeout(240_000);
  await page.setViewportSize({ width: 1720, height: 1000 });
  const directRagFlowRequests: string[] = [];
  let workflowWriteRequests = 0;
  page.on("request", (request) => {
    const requestUrl = new URL(request.url());
    if (requestUrl.port === "19380") directRagFlowRequests.push(request.url());
    if (
      (requestUrl.pathname === "/api/v1/workflows" && request.method() === "POST") ||
      (/^\/api\/v1\/workflows\/[^/]+$/.test(requestUrl.pathname) &&
        request.method() === "PUT")
    ) {
      workflowWriteRequests += 1;
    }
  });

  await page.goto("/workflows");
  await expect(page.getByRole("heading", { name: "工作流" })).toBeVisible();
  await expect(page.getByText("后端正常")).toBeVisible();

  const invalidValidationResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/v1/workflows/validate") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "保存工作流" }).click();
  const invalidValidation = await invalidValidationResponse;
  expect(invalidValidation.status()).toBe(200);
  await expect(page.getByText("服务端校验未通过")).toBeVisible();
  await expect(page.getByText("必须包含一个开始节点")).toBeVisible();
  expect(workflowWriteRequests).toBe(0);

  await page.getByRole("link", { name: "知识库" }).click();
  await page.getByRole("button", { name: "创建知识库" }).click();
  const knowledgeDialog = page.getByRole("dialog", { name: "创建知识库" });
  await knowledgeDialog.getByRole("textbox", { name: "名称" }).fill(knowledgeBaseName);
  await knowledgeDialog
    .getByRole("textbox", { name: "描述" })
    .fill("W5-05 工作流设计器真实知识引用验收");
  const knowledgeResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/v1/knowledge-bases") &&
      response.request().method() === "POST",
  );
  await knowledgeDialog.getByRole("button", { name: "确认创建" }).click();
  expect((await knowledgeResponse).status()).toBe(201);
  await expect(page.locator(".knowledge-base-item", { hasText: knowledgeBaseName })).toBeVisible();

  await page.getByRole("link", { name: "工作流" }).click();
  await expect(page.getByRole("heading", { name: "工作流" })).toBeVisible();
  await page.getByRole("textbox", { name: "工作流名称" }).fill(workflowName);
  await page
    .getByRole("textbox", { name: "工作流说明" })
    .fill("W5-05 React Flow 生产同路径验收");

  await dragNodeTo(page, "添加开始节点", { x: 90, y: 180 });
  await expect(page.locator(".react-flow__node")).toHaveCount(1, { timeout: 5_000 });
  await dragNodeTo(page, "添加知识检索节点", { x: 300, y: 180 });
  await expect(page.locator(".react-flow__node")).toHaveCount(2, { timeout: 5_000 });
  await page.getByRole("combobox", { name: "节点知识库" }).click();
  await page.getByTitle(knowledgeBaseName).click();
  await dragNodeTo(page, "添加AI 对话节点", { x: 510, y: 180 });
  await expect(page.locator(".react-flow__node")).toHaveCount(3, { timeout: 5_000 });
  await page
    .getByRole("textbox", { name: "节点提示词" })
    .fill("仅依据工作流中检索到的可靠知识回答用户输入。");
  await selectWorkflowAiTarget(page, "平台默认模型");
  await dragNodeTo(page, "添加结束节点", { x: 720, y: 180 });
  await expect(page.locator(".react-flow__node")).toHaveCount(4, { timeout: 5_000 });
  await connectNodes(page, "start-1", "knowledge_retrieval-1");
  await expect(page.locator(".react-flow__edge")).toHaveCount(1, { timeout: 5_000 });
  await connectNodes(page, "knowledge_retrieval-1", "ai_chat-1");
  await expect(page.locator(".react-flow__edge")).toHaveCount(2, { timeout: 5_000 });
  await connectNodes(page, "ai_chat-1", "end-1");
  await expect(page.locator(".react-flow__edge")).toHaveCount(3, { timeout: 5_000 });

  const validValidationResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/v1/workflows/validate") &&
      response.request().method() === "POST",
  );
  const createdWorkflowResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/v1/workflows") && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "保存工作流" }).click();
  const validationBody = (await (await validValidationResponse).json()) as { valid: boolean };
  expect(validationBody.valid).toBe(true);
  const createdResponse = await createdWorkflowResponse;
  expect(createdResponse.status()).toBe(201);
  const createdWorkflow = (await createdResponse.json()) as {
    id: string;
    nodes: unknown[];
    edges: unknown[];
  };
  expect(createdWorkflow.id).toEqual(expect.any(String));
  expect(createdWorkflow.nodes).toHaveLength(4);
  expect(createdWorkflow.edges).toHaveLength(3);
  await expect(page.getByText("已保存")).toBeVisible();
  await expect(page.getByRole("button", { name: `选择工作流 ${workflowName}` })).toBeVisible();

  await page.reload();
  await expect(page.getByRole("textbox", { name: "工作流名称" })).toHaveValue(workflowName);
  await expect(page.locator(".react-flow__node")).toHaveCount(4);
  await expect(page.locator(".react-flow__edge")).toHaveCount(3);
  await page.getByRole("button", { name: "选择节点 知识检索 knowledge_retrieval-1" }).click();
  await expect(page.getByText(knowledgeBaseName, { exact: true })).toBeVisible({
    timeout: 5_000,
  });

  await page.getByRole("button", { name: "选择节点 AI 对话 ai_chat-1" }).click();
  const updatedPrompt = "刷新后仍只依据可靠知识回答，并保持简洁。";
  await page.getByRole("textbox", { name: "节点提示词" }).fill(updatedPrompt);
  const updatedWorkflowResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/api/v1/workflows/${createdWorkflow.id}`) &&
      response.request().method() === "PUT",
  );
  await page.getByRole("button", { name: "保存工作流" }).click();
  expect((await updatedWorkflowResponse).status()).toBe(200);

  await page.reload();
  await page.getByRole("button", { name: "选择节点 AI 对话 ai_chat-1" }).click();
  await expect(page.getByRole("textbox", { name: "节点提示词" })).toHaveValue(updatedPrompt);
  expect(workflowWriteRequests).toBe(2);
  expect(directRagFlowRequests).toEqual([]);
});
