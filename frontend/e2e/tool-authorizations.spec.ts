import type { Locator, Page } from "@playwright/test";

import { expect, test } from "./fixtures/auth";
import { selectEmployeeDefaultModel } from "./fixtures/models";
import { expectRouteSearchParam } from "./fixtures/url";

function requiredEnvironment(name: string): string {
  const value = process.env[name]?.trim();
  if (!value) throw new Error(`${name} is required`);
  return value;
}

const employeeName = requiredEnvironment("COMMON_AGENT_E2E_TOOL_EMPLOYEE_NAME");
const genericPrefix = requiredEnvironment("COMMON_AGENT_E2E_TOOL_GENERIC_PREFIX");

async function selectCurrentTime(page: Page, scope: Locator): Promise<void> {
  await scope.getByRole("combobox", { name: "单项工具能力" }).click();
  const option = page
    .locator(".ant-select-dropdown:visible .ant-select-item-option")
    .filter({ hasText: "当前时间" })
    .first();
  await expect(option).toBeVisible();
  await option.click();
  await page.keyboard.press("Escape");
}

async function expectCompletedCurrentTime(page: Page): Promise<void> {
  const lifecycle = page.getByLabel("工具调用 1").last();
  await expect(lifecycle).toContainText("当前时间", { timeout: 180_000 });
  await expect(lifecycle).toContainText("已完成", { timeout: 180_000 });
  await expect(lifecycle).not.toContainText("arguments");
  await expect(lifecycle).not.toContainText("result");
}

test("authorizes and calls current time from generic and employee chats", async ({
  page,
}) => {
  test.setTimeout(420_000);
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));

  await page.goto("/chat");
  await expect(page.getByRole("heading", { name: "通用 AI" })).toBeVisible();
  const genericPanel = page.getByRole("region", { name: "数字员工信息" });
  await selectCurrentTime(page, genericPanel);
  const genericPrompt =
    `${genericPrefix}：必须调用 current_time，使用 +08:00，` +
    "然后依据工具返回值回答当前日期时间；禁止猜测。";
  await page.getByRole("textbox", { name: "消息输入" }).fill(genericPrompt);
  const genericTurnResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/v1/conversation-turns") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "发送消息" }).click();
  const acceptedGenericTurn = await genericTurnResponse;
  expect(acceptedGenericTurn.status()).toBe(202);
  const genericBody = acceptedGenericTurn.request().postDataJSON() as {
    employee_id: string | null;
    tool_collection_ids: string[];
    tool_capability_ids: string[];
  };
  expect(genericBody.employee_id).toBeNull();
  expect(genericBody.tool_collection_ids).toEqual([]);
  expect(genericBody.tool_capability_ids).toHaveLength(1);
  const genericTurn = (await acceptedGenericTurn.json()) as {
    conversation: { id: string };
  };
  await expectRouteSearchParam(page, "/chat", "conversation_id", genericTurn.conversation.id);
  await expectCompletedCurrentTime(page);
  await expect(page.locator(".chat-message.is-assistant .chat-message-content").last()).not.toBeEmpty();

  await page.reload();
  await expectCompletedCurrentTime(page);
  await expect(
    genericPanel.locator(".ant-select-selection-item").filter({ hasText: "当前时间" }),
  ).toBeVisible();

  await page.getByRole("link", { name: "数字员工" }).click();
  await page.getByRole("button", { name: "创建数字员工" }).click();
  const createDialog = page.getByRole("dialog", { name: "创建数字员工" });
  await createDialog.getByRole("textbox", { name: "名称" }).fill(employeeName);
  await createDialog
    .getByRole("textbox", { name: "说明" })
    .fill("T2-07 工具授权生产同路径验收");
  await createDialog
    .getByRole("textbox", { name: "系统指令" })
    .fill("必须调用用户要求且已授权的工具，再依据工具结果回答；禁止猜测工具结果。");
  await selectEmployeeDefaultModel(page, createDialog);
  const employeeResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/v1/employees") &&
      response.request().method() === "POST",
  );
  await createDialog.getByRole("button", { name: "确认创建" }).click();
  const createdEmployeeResponse = await employeeResponse;
  expect(createdEmployeeResponse.status()).toBe(201);
  const employee = (await createdEmployeeResponse.json()) as { id: string };

  const employeeCard = page.locator(".employee-card", { hasText: employeeName });
  await employeeCard.getByRole("button", { name: `编辑 ${employeeName}` }).click();
  const editDialog = page.getByRole("dialog", { name: "编辑数字员工" });
  await selectCurrentTime(page, editDialog);
  const grantResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/api/v1/employees/${employee.id}/tool-grants`) &&
      response.request().method() === "PUT",
  );
  const updateResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/api/v1/employees/${employee.id}`) &&
      response.request().method() === "PUT",
  );
  await editDialog.getByRole("button", { name: "保存修改" }).click();
  expect((await grantResponse).status()).toBe(200);
  expect((await updateResponse).status()).toBe(200);

  await employeeCard.getByRole("button", { name: `与${employeeName}开始对话` }).click();
  await expectRouteSearchParam(page, "/chat", "employee_id", employee.id);
  const employeePanel = page.getByRole("region", { name: "数字员工信息" });
  await expect(employeePanel).toContainText("1 个工具权限");
  const employeePrompt =
    "必须调用 current_time，使用 +08:00，然后依据工具返回值回答当前日期时间；禁止猜测。";
  await page.getByRole("textbox", { name: "消息输入" }).fill(employeePrompt);
  const employeeTurnResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/v1/conversation-turns") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "发送消息" }).click();
  const acceptedEmployeeTurn = await employeeTurnResponse;
  expect(acceptedEmployeeTurn.status()).toBe(202);
  const employeeBody = acceptedEmployeeTurn.request().postDataJSON() as {
    employee_id: string | null;
    tool_collection_ids: string[];
    tool_capability_ids: string[];
  };
  expect(employeeBody.employee_id).toBe(employee.id);
  expect(employeeBody.tool_collection_ids).toEqual([]);
  expect(employeeBody.tool_capability_ids).toEqual([]);
  await expectCompletedCurrentTime(page);
  await expect(page.locator(".chat-message.is-assistant .chat-message-content").last()).not.toBeEmpty();

  await page.reload();
  await expectCompletedCurrentTime(page);
  expect(pageErrors).toEqual([]);
});
