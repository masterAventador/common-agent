import { createServer, type Server } from "node:http";
import type { AddressInfo } from "node:net";
import type { Locator, Page } from "@playwright/test";

import {
  expect,
  platformApiUrl,
  platformWriteHeaders,
  test,
} from "./fixtures/auth";
import { selectEmployeeDefaultModel } from "./fixtures/models";
import { expectRouteSearchParam } from "./fixtures/url";

function requiredEnvironment(name: string): string {
  const value = process.env[name]?.trim();
  if (!value) throw new Error(`${name} is required`);
  return value;
}

const employeeName = requiredEnvironment("COMMON_AGENT_E2E_TOOL_EMPLOYEE_NAME");
const genericPrefix = requiredEnvironment("COMMON_AGENT_E2E_TOOL_GENERIC_PREFIX");
const modelName = requiredEnvironment("COMMON_AGENT_E2E_TOOL_MODEL_NAME");
const managedSourceName = requiredEnvironment(
  "COMMON_AGENT_E2E_TOOL_MANAGED_SOURCE_NAME",
);
const externalSourceName = requiredEnvironment(
  "COMMON_AGENT_E2E_TOOL_EXTERNAL_SOURCE_NAME",
);
const managedCapabilityName = "创建不确定订单";
const externalCapabilityName = "查询外部订单 T2-09";
const managedBearerToken = "t2-09-managed-side-effect-secret";
const externalBearerToken = "t2-09-external-mcp-secret";
let businessServer: Server;
let businessPort = 0;
let managedSideEffectCount = 0;
let externalMcpServer: Server;
let externalMcpPort = 0;
let externalToolCallCount = 0;

test.beforeAll(async () => {
  businessServer = createServer((request, response) => {
    if (request.headers.authorization !== `Bearer ${managedBearerToken}`) {
      response.writeHead(401).end();
      return;
    }
    if (request.method === "POST" && request.url === "/api/orders") {
      managedSideEffectCount += 1;
      request.socket.destroy();
      return;
    }
    response.writeHead(404).end();
  });
  await new Promise<void>((resolve) =>
    businessServer.listen(0, "127.0.0.1", resolve),
  );
  businessPort = (businessServer.address() as AddressInfo).port;

  externalMcpServer = createServer(async (request, response) => {
    if (request.headers.authorization !== `Bearer ${externalBearerToken}`) {
      response.writeHead(401).end();
      return;
    }
    let rawBody = "";
    for await (const chunk of request) rawBody += chunk.toString();
    const message = JSON.parse(rawBody) as {
      id?: string | number;
      method?: string;
      params?: { name?: string; arguments?: Record<string, unknown> };
    };
    if (message.method === "notifications/initialized") {
      response.writeHead(202).end();
      return;
    }
    let result: Record<string, unknown>;
    if (message.method === "initialize") {
      result = {
        protocolVersion: "2025-11-25",
        capabilities: { tools: {} },
        serverInfo: { name: "t2-09-external-orders", version: "1.0.0" },
      };
    } else if (message.method === "tools/list") {
      result = {
        tools: [
          {
            name: "external_orders_get",
            title: externalCapabilityName,
            description: "查询外部订单，必须使用 order_id。",
            inputSchema: {
              type: "object",
              properties: {
                order_id: { type: "string", description: "订单编号" },
              },
              required: ["order_id"],
              additionalProperties: false,
            },
          },
        ],
      };
    } else if (
      message.method === "tools/call" &&
      message.params?.name === "external_orders_get"
    ) {
      externalToolCallCount += 1;
      const output = {
        id: message.params.arguments?.order_id,
        source: "external-mcp-worker",
      };
      result = {
        content: [{ type: "text", text: JSON.stringify(output) }],
        structuredContent: output,
        isError: false,
      };
    } else {
      const body = JSON.stringify({
        jsonrpc: "2.0",
        id: message.id,
        error: { code: -32601, message: "Method not found" },
      });
      response.writeHead(200, {
        "Content-Type": "application/json",
        "Content-Length": Buffer.byteLength(body),
      });
      response.end(body);
      return;
    }
    const body = JSON.stringify({ jsonrpc: "2.0", id: message.id, result });
    response.writeHead(200, {
      "Content-Type": "application/json",
      "Content-Length": Buffer.byteLength(body),
    });
    response.end(body);
  });
  await new Promise<void>((resolve) =>
    externalMcpServer.listen(0, "127.0.0.1", resolve),
  );
  externalMcpPort = (externalMcpServer.address() as AddressInfo).port;
});

test.afterAll(async () => {
  await new Promise<void>((resolve, reject) =>
    businessServer.close((error) => (error ? reject(error) : resolve())),
  );
  await new Promise<void>((resolve, reject) =>
    externalMcpServer.close((error) => (error ? reject(error) : resolve())),
  );
});

async function selectCurrentTime(page: Page, scope: Locator): Promise<void> {
  await selectCapability(page, scope, "当前时间");
}

async function selectCapability(
  page: Page,
  scope: Locator,
  capabilityName: string,
): Promise<void> {
  await scope.getByRole("combobox", { name: "单项工具能力" }).click();
  const option = page
    .locator(".ant-select-dropdown:visible .ant-select-item-option")
    .filter({ hasText: capabilityName })
    .first();
  await expect(option).toBeVisible();
  await option.click();
  await page.keyboard.press("Escape");
}

async function createWorkerToolSources(page: Page): Promise<{
  managedCapabilityId: string;
  externalCapabilityId: string;
}> {
  const headers = await platformWriteHeaders(page);
  const managed = await page.request.post(platformApiUrl("/managed-mcp-sources"), {
    headers,
    data: {
      name: managedSourceName,
      description: "T2-09 结果未知防重放正式验收",
      base_url: `http://localhost:${businessPort}/api`,
      enabled: true,
    },
  });
  expect(managed.status()).toBe(201);
  const managedSource = (await managed.json()) as { id: string };
  const managedCredential = await page.request.put(
    platformApiUrl(`/mcp-sources/${managedSource.id}/credentials`),
    {
      headers,
      data: {
        action: "replace",
        kind: "bearer",
        bearer_token: managedBearerToken,
      },
    },
  );
  expect(managedCredential.status()).toBe(200);
  const managedCapability = await page.request.post(
    platformApiUrl(`/managed-mcp-sources/${managedSource.id}/capabilities`),
    {
      headers,
      data: {
        remote_name: "orders_create_uncertain",
        display_name: managedCapabilityName,
        description: "创建订单；远端断线时结果未知，禁止自动重试。",
        input_schema: {
          type: "object",
          properties: {
            order_id: { type: "string", description: "订单编号" },
          },
          required: ["order_id"],
          additionalProperties: false,
        },
        method: "POST",
        path_template: "/orders",
        parameter_bindings: [
          { argument_name: "order_id", location: "body", target_name: "order_id" },
        ],
        timeout_seconds: 10,
        response_json_pointer: null,
        enabled: true,
      },
    },
  );
  expect(managedCapability.status()).toBe(201);
  const managedCapabilityBody = (await managedCapability.json()) as { id: string };

  const external = await page.request.post(platformApiUrl("/external-mcp-sources"), {
    headers,
    data: {
      name: externalSourceName,
      description: "T2-09 Worker 外部 MCP 正式验收",
      endpoint_url: `http://localhost:${externalMcpPort}/mcp`,
    },
  });
  expect(external.status()).toBe(201);
  const externalSource = (await external.json()) as { id: string };
  const externalCredential = await page.request.put(
    platformApiUrl(`/mcp-sources/${externalSource.id}/credentials`),
    {
      headers,
      data: {
        action: "replace",
        kind: "bearer",
        bearer_token: externalBearerToken,
        headers: null,
      },
    },
  );
  expect(externalCredential.status()).toBe(200);
  const sync = await page.request.post(
    platformApiUrl(`/external-mcp-sources/${externalSource.id}/sync`),
    { headers },
  );
  expect(sync.status()).toBe(200);
  const syncBody = (await sync.json()) as {
    source: { capabilities: Array<{ id: string; display_name: string }> };
  };
  const externalCapability = syncBody.source.capabilities.find(
    (item) => item.display_name === externalCapabilityName,
  );
  expect(externalCapability).toBeDefined();
  return {
    managedCapabilityId: managedCapabilityBody.id,
    externalCapabilityId: externalCapability!.id,
  };
}

async function expectToolLifecycle(
  page: Page,
  capabilityName: string,
  status: string,
  errorCode?: string,
): Promise<void> {
  const lifecycle = page
    .getByLabel(/工具调用 \d+/)
    .filter({ hasText: capabilityName })
    .last();
  await expect(lifecycle).toContainText(status, { timeout: 180_000 });
  if (errorCode) await expect(lifecycle).toContainText(errorCode);
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
  test.setTimeout(720_000);
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));

  await page.goto("/model-configurations");
  await page.getByRole("button", { name: "创建模型" }).click();
  const modelDialog = page.getByRole("dialog", { name: "创建模型" });
  await modelDialog.getByRole("textbox", { name: "显示名称" }).fill(modelName);
  await modelDialog
    .getByRole("textbox", { name: "百炼模型标识" })
    .fill("deepseek-v4-pro");
  const modelResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/v1/model-configurations") &&
      response.request().method() === "POST",
  );
  await modelDialog.getByRole("button", { name: "确认创建" }).click();
  const createdModelResponse = await modelResponse;
  expect(createdModelResponse.status()).toBe(201);
  const model = (await createdModelResponse.json()) as {
    id: string;
    streaming_breaks_tool_calls: boolean;
  };
  expect(model.streaming_breaks_tool_calls).toBe(true);
  const modelCard = page.locator(".model-configuration-card", { hasText: modelName });
  await expect(modelCard).toContainText("deepseek-v4-pro");
  await expect(modelCard).toContainText("工具调用自动非流式");

  await page.goto("/chat");
  await expect(page.getByRole("heading", { name: "通用 AI" })).toBeVisible();
  await page.getByRole("combobox", { name: "选择模型" }).click();
  const genericModelOption = page
    .locator(".ant-select-dropdown:visible .ant-select-item-option")
    .filter({ hasText: modelName })
    .first();
  await expect(genericModelOption).toBeVisible();
  await genericModelOption.click();
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
  await page.getByRole("textbox", { name: "消息输入" }).press("Enter");
  const acceptedGenericTurn = await genericTurnResponse;
  expect(acceptedGenericTurn.status()).toBe(202);
  const genericBody = acceptedGenericTurn.request().postDataJSON() as {
    employee_id: string | null;
    model_configuration_id: string;
    tool_collection_ids: string[];
    tool_capability_ids: string[];
  };
  expect(genericBody.employee_id).toBeNull();
  expect(genericBody.model_configuration_id).toBe(model.id);
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
  await selectEmployeeDefaultModel(page, createDialog, modelName);
  const employeeResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/v1/employees") &&
      response.request().method() === "POST",
  );
  await createDialog.getByRole("button", { name: "确认创建" }).click();
  const createdEmployeeResponse = await employeeResponse;
  expect(createdEmployeeResponse.status()).toBe(201);
  const employee = (await createdEmployeeResponse.json()) as {
    id: string;
    default_model_configuration_id: string;
  };
  expect(employee.default_model_configuration_id).toBe(model.id);

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
  await page.getByRole("textbox", { name: "消息输入" }).press("Enter");
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

  const workerTools = await createWorkerToolSources(page);

  await page.goto("/chat");
  await page.getByRole("combobox", { name: "选择模型" }).click();
  const managedModelOption = page
    .locator(".ant-select-dropdown:visible .ant-select-item-option")
    .filter({ hasText: modelName })
    .first();
  await expect(managedModelOption).toBeVisible();
  await managedModelOption.click();
  const managedPanel = page.getByRole("region", { name: "数字员工信息" });
  await selectCapability(page, managedPanel, managedCapabilityName);
  const managedPrompt =
    `${genericPrefix}-result-unknown：必须调用 orders_create_uncertain 创建订单 ` +
    "T2-09-ORDER；即使工具返回结果未知也禁止再次调用，只说明真实状态。";
  await page.getByRole("textbox", { name: "消息输入" }).fill(managedPrompt);
  const managedTurnResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/v1/conversation-turns") &&
      response.request().method() === "POST",
  );
  await page.getByRole("textbox", { name: "消息输入" }).press("Enter");
  const acceptedManagedTurn = await managedTurnResponse;
  expect(acceptedManagedTurn.status()).toBe(202);
  const managedTurnBody = acceptedManagedTurn.request().postDataJSON() as {
    tool_capability_ids: string[];
  };
  expect(managedTurnBody.tool_capability_ids).toEqual([
    workerTools.managedCapabilityId,
  ]);
  await expectToolLifecycle(
    page,
    managedCapabilityName,
    "失败",
    "tool_result_unknown",
  );
  await expect
    .poll(() => managedSideEffectCount, { timeout: 180_000 })
    .toBe(1);
  await expect(
    page.locator(".chat-message.is-assistant .chat-message-content").last(),
  ).not.toBeEmpty();

  await page.getByRole("link", { name: "数字员工" }).click();
  const workerEmployeeCard = page.locator(".employee-card", { hasText: employeeName });
  await workerEmployeeCard.getByRole("button", { name: `编辑 ${employeeName}` }).click();
  const workerEditDialog = page.getByRole("dialog", { name: "编辑数字员工" });
  await selectCapability(page, workerEditDialog, externalCapabilityName);
  const workerGrantResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/api/v1/employees/${employee.id}/tool-grants`) &&
      response.request().method() === "PUT",
  );
  await workerEditDialog.getByRole("button", { name: "保存修改" }).click();
  const workerGrant = await workerGrantResponse;
  expect(workerGrant.status()).toBe(200);
  const workerGrantBody = (await workerGrant.json()) as {
    capability_ids: string[];
  };
  expect(workerGrantBody.capability_ids).toContain(workerTools.externalCapabilityId);

  await workerEmployeeCard
    .getByRole("button", { name: `与${employeeName}开始对话` })
    .click();
  await page
    .getByRole("textbox", { name: "消息输入" })
    .fill(
      "必须调用 external_orders_get 查询订单 EXT-T2-09，并依据工具返回的 id 和 source 回答；禁止猜测。",
    );
  const externalTurnResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/v1/conversation-turns") &&
      response.request().method() === "POST",
  );
  await page.getByRole("textbox", { name: "消息输入" }).press("Enter");
  expect((await externalTurnResponse).status()).toBe(202);
  await expectToolLifecycle(page, externalCapabilityName, "已完成");
  await expect.poll(() => externalToolCallCount, { timeout: 180_000 }).toBe(1);
  await expect(
    page.locator(".chat-message.is-assistant .chat-message-content").last(),
  ).toContainText(/EXT-T2-09|external-mcp-worker/);

  expect(pageErrors).toEqual([]);
});
