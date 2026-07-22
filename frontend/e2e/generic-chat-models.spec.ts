import type { Page } from "@playwright/test";

import { expect, test } from "./fixtures/auth";
import { expectRouteSearchParam } from "./fixtures/url";

function requiredEnvironment(name: string): string {
  const value = process.env[name]?.trim();
  if (!value) throw new Error(`${name} is required`);
  return value;
}

const modelName = requiredEnvironment("COMMON_AGENT_E2E_GENERIC_CHAT_MODEL_NAME");

async function selectChatModel(page: Page, name: string) {
  await page.getByRole("combobox", { name: "选择模型" }).click();
  const option = page
    .locator(".ant-select-dropdown:visible .ant-select-item-option")
    .filter({ hasText: name })
    .first();
  await expect(option).toBeVisible();
  await option.click();
}

test("creates a generic conversation on first send and switches real Bailian models per turn", async ({
  page,
}) => {
  test.setTimeout(240_000);
  const firstMarker = `COMMON_AGENT_GENERIC_TURBO_${Date.now()}`;
  const secondMarker = `COMMON_AGENT_GENERIC_PLUS_${Date.now()}`;
  const pageErrors: string[] = [];
  const employeeWorkflowRequests: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("request", (request) => {
    const pathname = new URL(request.url()).pathname;
    if (
      request.method() === "GET" &&
      ["/api/v1/workflow-runs", "/api/v1/workflows"].includes(pathname)
    ) {
      employeeWorkflowRequests.push(pathname);
    }
  });

  await page.goto("/model-configurations");
  await page.getByRole("button", { name: "创建模型" }).click();
  const modelDialog = page.getByRole("dialog", { name: "创建模型" });
  await modelDialog.getByRole("textbox", { name: "显示名称" }).fill(modelName);
  await modelDialog.getByRole("textbox", { name: "百炼模型标识" }).fill("qwen-turbo");
  const modelResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/v1/model-configurations") &&
      response.request().method() === "POST",
  );
  await modelDialog.getByRole("button", { name: "确认创建" }).click();
  const createdModelResponse = await modelResponse;
  expect(createdModelResponse.status()).toBe(201);
  const createdModel = (await createdModelResponse.json()) as { id: string };

  await page.getByRole("link", { name: "AI 会话" }).click();
  await expect(page.getByRole("heading", { name: "通用 AI" })).toBeVisible();
  await expect(page.getByText("发送第一条消息时会自动创建并保存会话")).toBeVisible();
  await selectChatModel(page, modelName);
  const firstPrompt = `${modelName} 只输出这个标记：${firstMarker}`;
  await page.getByRole("textbox", { name: "消息输入" }).fill(firstPrompt);
  const firstTurnResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/v1/conversation-turns") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "发送消息" }).click();
  const acceptedFirstTurn = await firstTurnResponse;
  expect(acceptedFirstTurn.status()).toBe(202);
  const firstTurn = (await acceptedFirstTurn.json()) as {
    conversation: { id: string; source: string; employee_id: string | null };
    turn: { assistant_message: { model_configuration_id: string; model_identifier: string } };
  };
  expect(firstTurn.conversation.source).toBe("generic");
  expect(firstTurn.conversation.employee_id).toBeNull();
  expect(firstTurn.turn.assistant_message.model_configuration_id).toBe(createdModel.id);
  expect(firstTurn.turn.assistant_message.model_identifier).toBe("qwen-turbo");
  await expectRouteSearchParam(page, "/chat", "conversation_id", firstTurn.conversation.id);
  await expect(page.locator(".chat-message.is-assistant .chat-message-content").last()).toContainText(
    firstMarker,
    { timeout: 180_000 },
  );
  await expect(page.getByText("正在生成")).toHaveCount(0);

  await page.reload();
  await expect(page.locator(".chat-model-select")).toContainText(modelName);
  await expect(
    page.locator(".chat-message.is-assistant .chat-message-content").last(),
  ).toContainText(firstMarker);
  await selectChatModel(page, "平台默认模型");
  await page
    .getByRole("textbox", { name: "消息输入" })
    .fill(`只输出这个标记：${secondMarker}`);
  const secondTurnResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/api/v1/conversations/${firstTurn.conversation.id}/messages`) &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "发送消息" }).click();
  const acceptedSecondTurn = await secondTurnResponse;
  expect(acceptedSecondTurn.status()).toBe(202);
  const secondTurn = (await acceptedSecondTurn.json()) as {
    assistant_message: { model_configuration_id: string; model_identifier: string };
  };
  expect(secondTurn.assistant_message.model_configuration_id).not.toBe(createdModel.id);
  expect(secondTurn.assistant_message.model_identifier).toBe("qwen-plus");
  await expect(page.locator(".chat-message.is-assistant .chat-message-content").last()).toContainText(
    secondMarker,
    { timeout: 180_000 },
  );
  await expect(page.getByText("正在生成")).toHaveCount(0);

  await page.getByRole("link", { name: "模型管理" }).click();
  const history = page.getByRole("region", { name: "历史会话" });
  await expect(history.getByText("通用 AI")).toBeVisible();
  await history
    .getByRole("link", { name: `打开会话 ${firstPrompt.slice(0, 200)}` })
    .click();
  await expectRouteSearchParam(page, "/chat", "conversation_id", firstTurn.conversation.id);
  await expect(page.locator(".chat-model-select")).toContainText("平台默认模型");
  await expect(page.locator(".chat-message.is-user .chat-message-content")).toHaveCount(2);
  await expect(
    page.locator(".chat-message.is-assistant .chat-message-content").last(),
  ).toContainText(secondMarker);

  await page.getByRole("button", { name: `删除会话 ${firstPrompt.slice(0, 200)}` }).click();
  const deleteConversationResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/api/v1/conversations/${firstTurn.conversation.id}`) &&
      response.request().method() === "DELETE",
  );
  await page
    .getByRole("button", { name: `确认删除会话 ${firstPrompt.slice(0, 200)}` })
    .click();
  expect((await deleteConversationResponse).status()).toBe(204);

  await page.getByRole("link", { name: "模型管理" }).click();
  const modelCard = page.locator(".model-configuration-card", { hasText: modelName });
  await modelCard.getByRole("button", { name: `删除模型 ${modelName}` }).click();
  const deleteModelResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/api/v1/model-configurations/${createdModel.id}`) &&
      response.request().method() === "DELETE",
  );
  await page.getByRole("button", { name: `确认删除模型 ${modelName}` }).click();
  expect((await deleteModelResponse).status()).toBe(204);
  expect(employeeWorkflowRequests).toEqual([]);
  expect(pageErrors).toEqual([]);
});
