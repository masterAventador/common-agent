import { expect, test } from "./fixtures/auth";
import { selectEmployeeDefaultModel } from "./fixtures/models";

function requiredEnvironment(name: string): string {
  const value = process.env[name]?.trim();
  if (!value) throw new Error(`${name} is required`);
  return value;
}

const modelName = requiredEnvironment("COMMON_AGENT_E2E_EMPLOYEE_MODEL_NAME");
const employeeName = requiredEnvironment("COMMON_AGENT_E2E_EMPLOYEE_MODEL_EMPLOYEE_NAME");

test("persists an employee model and routes its real reply through that model", async ({
  page,
}) => {
  test.setTimeout(240_000);
  const replyMarker = `COMMON_AGENT_EMPLOYEE_MODEL_${Date.now()}`;
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));

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
  expect((await modelResponse).status()).toBe(201);

  await page.getByRole("link", { name: "数字员工" }).click();
  await page.getByRole("button", { name: "创建数字员工" }).click();
  const employeeDialog = page.getByRole("dialog", { name: "创建数字员工" });
  await employeeDialog.getByRole("textbox", { name: "名称" }).fill(employeeName);
  await employeeDialog
    .getByRole("textbox", { name: "说明" })
    .fill("S10-07F 默认模型生产同路径验收");
  await employeeDialog
    .getByRole("textbox", { name: "系统指令" })
    .fill("严格按用户要求输出验收标记，不要添加其他文字。");
  await selectEmployeeDefaultModel(page, employeeDialog, "平台默认模型");
  const employeeResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/v1/employees") &&
      response.request().method() === "POST",
  );
  await employeeDialog.getByRole("button", { name: "确认创建" }).click();
  const createdEmployeeResponse = await employeeResponse;
  expect(createdEmployeeResponse.status()).toBe(201);
  const employee = (await createdEmployeeResponse.json()) as { id: string };

  let employeeCard = page.locator(".employee-card", { hasText: employeeName });
  await expect(employeeCard).toContainText("平台默认模型");
  await page.reload();
  employeeCard = page.locator(".employee-card", { hasText: employeeName });
  await expect(employeeCard).toContainText("平台默认模型");

  await employeeCard.getByRole("button", { name: `编辑 ${employeeName}` }).click();
  const editEmployeeDialog = page.getByRole("dialog", { name: "编辑数字员工" });
  await selectEmployeeDefaultModel(page, editEmployeeDialog, modelName);
  const updateEmployeeResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/api/v1/employees/${employee.id}`) &&
      response.request().method() === "PUT",
  );
  await editEmployeeDialog.getByRole("button", { name: "保存修改" }).click();
  expect((await updateEmployeeResponse).status()).toBe(200);
  await page.reload();
  employeeCard = page.locator(".employee-card", { hasText: employeeName });
  await expect(employeeCard).toContainText(modelName);

  await page.getByRole("link", { name: "模型管理" }).click();
  let modelCard = page.locator(".model-configuration-card", { hasText: modelName });
  await modelCard.getByRole("button", { name: `编辑 ${modelName}` }).click();
  const editModelDialog = page.getByRole("dialog", { name: "编辑模型" });
  await editModelDialog.getByRole("switch", { name: "启用状态" }).click();
  const disableModelResponse = page.waitForResponse(
    (response) =>
      response.url().includes("/api/v1/model-configurations/") &&
      response.request().method() === "PUT",
  );
  await editModelDialog.getByRole("button", { name: "保存修改" }).click();
  expect((await disableModelResponse).status()).toBe(200);
  await page.reload();
  modelCard = page.locator(".model-configuration-card", { hasText: modelName });
  await expect(modelCard).toContainText("停用");

  await page.getByRole("link", { name: "数字员工" }).click();
  employeeCard = page.locator(".employee-card", { hasText: employeeName });
  await expect(employeeCard).toContainText(`${modelName}（已停用）`);
  await employeeCard.getByRole("button", { name: `编辑 ${employeeName}` }).click();
  const preservedDialog = page.getByRole("dialog", { name: "编辑数字员工" });
  await preservedDialog
    .getByRole("textbox", { name: "说明" })
    .fill("停用后保留既有模型绑定");
  const preserveResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/api/v1/employees/${employee.id}`) &&
      response.request().method() === "PUT",
  );
  await preservedDialog.getByRole("button", { name: "保存修改" }).click();
  expect((await preserveResponse).status()).toBe(200);
  await expect(employeeCard).toContainText("停用后保留既有模型绑定");

  await page.getByRole("button", { name: "创建数字员工" }).click();
  const newEmployeeDialog = page.getByRole("dialog", { name: "创建数字员工" });
  await newEmployeeDialog.getByRole("combobox", { name: "默认模型" }).click();
  const openModelDropdown = page.locator(".ant-select-dropdown:visible");
  await expect(openModelDropdown.getByText("平台默认模型", { exact: false })).toBeVisible();
  await expect(openModelDropdown.getByText(modelName, { exact: false })).toHaveCount(0);
  await newEmployeeDialog.getByRole("button", { name: /取\s*消/ }).click();

  await page.getByRole("link", { name: "模型管理" }).click();
  modelCard = page.locator(".model-configuration-card", { hasText: modelName });
  await modelCard.getByRole("button", { name: `删除模型 ${modelName}` }).click();
  const blockedDeleteResponse = page.waitForResponse(
    (response) =>
      response.url().includes("/api/v1/model-configurations/") &&
      response.request().method() === "DELETE",
  );
  await page.getByRole("button", { name: `确认删除模型 ${modelName}` }).click();
  expect((await blockedDeleteResponse).status()).toBe(409);
  await expect(
    page.getByText("该模型仍被数字员工或工作流引用，请先解除引用。"),
  ).toBeVisible();

  await page.getByRole("link", { name: "数字员工" }).click();
  employeeCard = page.locator(".employee-card", { hasText: employeeName });
  await employeeCard.getByRole("button", { name: `与${employeeName}开始对话` }).click();
  const createConversationResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/v1/conversations") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "新建会话" }).click();
  expect((await createConversationResponse).status()).toBe(201);
  await page
    .getByRole("textbox", { name: "消息输入" })
    .fill(`只输出这个标记：${replyMarker}`);
  const sendResponse = page.waitForResponse(
    (response) =>
      response.url().includes("/messages") && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "发送消息" }).click();
  expect((await sendResponse).status()).toBe(202);
  const answer = page.locator(".chat-message.is-assistant .chat-message-content").last();
  await expect(answer).toContainText(replyMarker, { timeout: 180_000 });
  await expect(page.getByText("正在生成")).toHaveCount(0);
  expect(pageErrors).toEqual([]);
});
