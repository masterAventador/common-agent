import type { Page } from "@playwright/test";

import { expect, platformWriteHeaders, test } from "./fixtures/auth";

function requiredEnvironment(name: string): string {
  const value = process.env[name]?.trim();
  if (!value) throw new Error(`${name} is required`);
  return value;
}

const apiUrl = requiredEnvironment("COMMON_AGENT_E2E_API_URL").replace(/\/$/, "");
const ragFlowUrl = requiredEnvironment("RAGFLOW_BASE_URL").replace(/\/$/, "");
const ragFlowApiKey = requiredEnvironment("RAGFLOW_API_KEY");
const successWorkflowName = requiredEnvironment("COMMON_AGENT_E2E_WORKFLOW_RUN_NAME");
const stopWorkflowName = requiredEnvironment("COMMON_AGENT_E2E_WORKFLOW_STOP_NAME");
const failureWorkflowName = requiredEnvironment("COMMON_AGENT_E2E_WORKFLOW_FAILURE_NAME");
const failureKnowledgeName = requiredEnvironment(
  "COMMON_AGENT_E2E_WORKFLOW_FAILURE_KNOWLEDGE_NAME",
);

async function createAiWorkflow(
  page: Page,
  headers: Record<string, string>,
  name: string,
  prompt: string,
): Promise<string> {
  const response = await page.request.post(`${apiUrl}/workflows`, {
    headers,
    data: {
      name,
      description: "W5-06 手动运行 UI 生产同路径验收",
      nodes: [
        { id: "start", type: "start", position: { x: 40, y: 120 }, config: {} },
        {
          id: "chat",
          type: "ai_chat",
          position: { x: 300, y: 120 },
          config: { prompt },
        },
        { id: "end", type: "end", position: { x: 560, y: 120 }, config: {} },
      ],
      edges: [
        { id: "edge-start-chat", source: "start", target: "chat" },
        { id: "edge-chat-end", source: "chat", target: "end" },
      ],
    },
  });
  expect(response.status()).toBe(201);
  return ((await response.json()) as { id: string }).id;
}

async function createFailureWorkflow(
  page: Page,
  headers: Record<string, string>,
): Promise<string> {
  const knowledgeResponse = await page.request.post(`${apiUrl}/knowledge-bases`, {
    headers,
    data: {
      name: failureKnowledgeName,
      description: "W5-06 真实失效知识库",
    },
  });
  expect(knowledgeResponse.status()).toBe(201);
  const knowledgeBaseId = ((await knowledgeResponse.json()) as { id: string }).id;

  const workflowResponse = await page.request.post(`${apiUrl}/workflows`, {
    headers,
    data: {
      name: failureWorkflowName,
      description: "W5-06 失败节点展示验收",
      nodes: [
        { id: "start", type: "start", position: { x: 40, y: 120 }, config: {} },
        {
          id: "retrieve",
          type: "knowledge_retrieval",
          position: { x: 300, y: 120 },
          config: { knowledge_base_id: knowledgeBaseId },
        },
        { id: "end", type: "end", position: { x: 560, y: 120 }, config: {} },
      ],
      edges: [
        { id: "edge-start-retrieve", source: "start", target: "retrieve" },
        { id: "edge-retrieve-end", source: "retrieve", target: "end" },
      ],
    },
  });
  expect(workflowResponse.status()).toBe(201);

  const deleted = await page.request.delete(`${ragFlowUrl}/api/v1/datasets`, {
    headers: { Authorization: `Bearer ${ragFlowApiKey}` },
    data: { ids: [knowledgeBaseId] },
  });
  expect(deleted.status()).toBe(200);
  expect(((await deleted.json()) as { code: number }).code).toBe(0);
  return ((await workflowResponse.json()) as { id: string }).id;
}

async function runFromPage(page: Page, input: string): Promise<{ id: string }> {
  await page.getByRole("textbox", { name: "工作流运行输入" }).fill(input);
  const runResponse = page.waitForResponse(
    (response) =>
      /\/api\/v1\/workflows\/[^/]+\/runs$/.test(new URL(response.url()).pathname) &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "运行工作流" }).click();
  const response = await runResponse;
  expect(response.status()).toBe(202);
  return (await response.json()) as { id: string };
}

test("runs, stops, fails, and restores workflow summaries through the real UI", async ({ page }) => {
  test.setTimeout(300_000);
  await page.setViewportSize({ width: 1720, height: 1000 });
  const directRagFlowRequests: string[] = [];
  page.on("request", (browserRequest) => {
    if (new URL(browserRequest.url()).port === "19380") {
      directRagFlowRequests.push(browserRequest.url());
    }
  });

  const headers = await platformWriteHeaders(page);
  await createAiWorkflow(
    page,
    headers,
    successWorkflowName,
    "无论用户输入什么，只输出标记 COMMON_AGENT_WORKFLOW_UI_REAL_OK，不要输出其他内容。",
  );
  await createAiWorkflow(
    page,
    headers,
    stopWorkflowName,
    "从 1 开始逐个输出整数直到 10000，每个数字用逗号分隔，不得省略。",
  );
  await createFailureWorkflow(page, headers);

  await page.goto("/workflows");
  await expect(page.getByRole("heading", { name: "工作流" })).toBeVisible();
  await expect(page.getByText("后端正常")).toBeVisible();
  await page.getByRole("button", { name: `选择工作流 ${successWorkflowName}` }).click();

  const completedRun = await runFromPage(page, "执行真实工作流并返回唯一验收标记");
  await expect(page).toHaveURL(new RegExp(`run_id=${completedRun.id}`));
  await expect(page.getByRole("button", { name: "停止工作流" })).toBeVisible();
  await expect(page.getByRole("textbox", { name: "工作流名称" })).toBeDisabled();
  await expect(page.locator('.react-flow__node[data-id="chat"]')).toHaveClass(
    /is-run-active/,
    { timeout: 180_000 },
  );
  await expect(page.getByText("运行完成")).toBeVisible({ timeout: 180_000 });
  await expect(page.getByText("COMMON_AGENT_WORKFLOW_UI_REAL_OK", { exact: false })).toBeVisible();
  await expect(page.locator(".react-flow__node.is-run-completed")).toHaveCount(3);

  await page.reload();
  await expect(page).toHaveURL(new RegExp(`run_id=${completedRun.id}`));
  await expect(page.getByText("运行完成")).toBeVisible();
  await expect(page.getByText("COMMON_AGENT_WORKFLOW_UI_REAL_OK", { exact: false })).toBeVisible();

  await page.getByRole("button", { name: `选择工作流 ${stopWorkflowName}` }).click();
  const stoppedRun = await runFromPage(page, "生成足够长的内容以验收协作停止");
  await expect(page.locator('.react-flow__node[data-id="chat"]')).toHaveClass(
    /is-run-active/,
    { timeout: 180_000 },
  );
  const stopResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/api/v1/workflow-runs/${stoppedRun.id}/stop`) &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "停止工作流" }).click();
  expect((await stopResponse).status()).toBe(202);
  await expect(page.getByText("工作流已停止")).toBeVisible({ timeout: 180_000 });

  await page.reload();
  await expect(page).toHaveURL(new RegExp(`run_id=${stoppedRun.id}`));
  await expect(page.getByText("工作流已停止")).toBeVisible();

  await page.getByRole("button", { name: `选择工作流 ${failureWorkflowName}` }).click();
  await runFromPage(page, "检索已经失效的真实知识库");
  await expect(page.getByText("knowledge_base_not_found")).toBeVisible({ timeout: 180_000 });
  await expect(page.locator('.react-flow__node[data-id="retrieve"]')).toHaveClass(
    /is-run-failed/,
  );
  await page.reload();
  await expect(page.getByText("knowledge_base_not_found")).toBeVisible();
  expect(directRagFlowRequests).toEqual([]);
});
