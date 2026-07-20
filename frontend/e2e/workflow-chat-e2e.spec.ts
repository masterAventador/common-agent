import { expect, type Locator, type Page, test } from "@playwright/test";

function requiredEnvironment(name: string): string {
  const value = process.env[name]?.trim();
  if (!value) throw new Error(`${name} is required`);
  return value;
}

const workflowName = requiredEnvironment("COMMON_AGENT_E2E_WORKFLOW_CHAT_NAME");
const employeeName = requiredEnvironment("COMMON_AGENT_E2E_WORKFLOW_CHAT_EMPLOYEE_NAME");

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

test("designs, runs, triggers, and restores an employee workflow through the real UI", async ({
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

  await page.goto("/workflows");
  await expect(page.getByRole("heading", { name: "工作流" })).toBeVisible();
  await page.getByRole("textbox", { name: "工作流名称" }).fill(workflowName);
  await page
    .getByRole("textbox", { name: "工作流说明" })
    .fill("W5-08 设计、手动运行和员工触发的生产同路径验收");
  await dragNodeTo(page, "添加开始节点", { x: 120, y: 180 });
  await expect(page.locator(".react-flow__node")).toHaveCount(1);
  await dragNodeTo(page, "添加结束节点", { x: 420, y: 180 });
  await expect(page.locator(".react-flow__node")).toHaveCount(2);
  await connectNodes(page, "start-1", "end-1");
  await expect(page.locator(".react-flow__edge")).toHaveCount(1);

  const createdWorkflowResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/v1/workflows") && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "保存工作流" }).click();
  const createdWorkflow = (await (await createdWorkflowResponse).json()) as { id: string };
  await expect(page.getByText("已保存")).toBeVisible();

  const manualMarker = `COMMON_AGENT_W5_08_MANUAL_${Date.now()}`;
  await page.getByRole("textbox", { name: "工作流运行输入" }).fill(manualMarker);
  const manualRunResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/api/v1/workflows/${createdWorkflow.id}/runs`) &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "运行工作流" }).click();
  expect((await manualRunResponse).status()).toBe(202);
  await expect(page.getByText("运行完成")).toBeVisible({ timeout: 180_000 });
  await expect(page.locator(".workflow-run-output")).toContainText(manualMarker);

  await page.getByRole("link", { name: "数字员工" }).click();
  await page.getByRole("button", { name: "创建数字员工" }).click();
  const employeeDialog = page.getByRole("dialog", { name: "创建数字员工" });
  await employeeDialog.getByRole("textbox", { name: "名称" }).fill(employeeName);
  await employeeDialog
    .getByRole("textbox", { name: "说明" })
    .fill("W5-08 对话式工作流触发员工");
  await employeeDialog
    .getByRole("textbox", { name: "系统指令" })
    .fill(
      "用户要求执行工作流时，必须调用唯一可用的工作流工具一次；把 input: 后的文本原样作为 input。工具完成后只回答 output。",
    );
  await employeeDialog.getByRole("combobox", { name: "允许工作流" }).click();
  await page.getByTitle(workflowName).click();
  const createdEmployeeResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/v1/employees") && response.request().method() === "POST",
  );
  await employeeDialog.getByRole("button", { name: "确认创建" }).click();
  const createdEmployee = (await (await createdEmployeeResponse).json()) as { id: string };
  const employeeCard = page.locator(".employee-card").filter({ hasText: employeeName });
  await expect(employeeCard).toContainText("已授权 1 个工作流");
  await employeeCard.getByRole("button", { name: `与${employeeName}开始对话` }).click();

  await expect(page).toHaveURL(new RegExp(`/chat\\?employee_id=${createdEmployee.id}$`));
  const createdConversationResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/v1/conversations") && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "新建会话" }).click();
  expect((await createdConversationResponse).status()).toBe(201);

  const employeeMarker = `COMMON_AGENT_W5_08_EMPLOYEE_${Date.now()}`;
  await page
    .getByRole("textbox", { name: "消息输入" })
    .fill(`执行唯一授权工作流，input:${employeeMarker}`);
  const sentResponse = page.waitForResponse(
    (response) => response.url().includes("/messages") && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "发送消息" }).click();
  expect((await sentResponse).status()).toBe(202);
  await expect(page.getByText("正在生成")).toHaveCount(0, { timeout: 180_000 });

  const runCards = page.locator(".chat-workflow-runs");
  await expect(runCards.getByText(workflowName)).toBeVisible({ timeout: 180_000 });
  await runCards.getByText(workflowName).click();
  await expect(runCards).toContainText(employeeMarker);
  await expect(runCards.getByText("已完成")).toBeVisible();

  await page.reload();
  await expect(page.getByRole("heading", { name: "新会话" })).toBeVisible();
  await expect(runCards.getByText(workflowName)).toBeVisible();
  await runCards.getByText(workflowName).click();
  await expect(runCards).toContainText(employeeMarker);
  await runCards.getByRole("button", { name: "查看运行详情" }).click();
  await expect(page).toHaveURL(/\/workflows\?run_id=[0-9a-f-]{36}$/);
  await expect(page.getByText("运行完成")).toBeVisible();
  await expect(page.locator(".workflow-run-output")).toContainText(employeeMarker);
  expect(directExternalRequests).toEqual([]);
});
