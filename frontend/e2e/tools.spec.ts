import { createServer, type Server } from "node:http";
import type { AddressInfo } from "node:net";

import {
  expect,
  platformApiUrl,
  platformWriteHeaders,
  test,
} from "./fixtures/auth";

let businessServer: Server;
let businessPort = 0;
let sourceName = "";
const bearerToken = "e2e-managed-mcp-secret";

test.beforeAll(async () => {
  businessServer = createServer((request, response) => {
    if (request.headers.authorization !== `Bearer ${bearerToken}`) {
      response.writeHead(401).end();
      return;
    }
    const url = new URL(request.url ?? "/", "http://localhost");
    const orderId = url.pathname.split("/").at(-1);
    const body = JSON.stringify({ data: { order: { id: orderId } } });
    response.writeHead(200, {
      "Content-Type": "application/json",
      "Content-Length": Buffer.byteLength(body),
    });
    response.end(body);
  });
  await new Promise<void>((resolve) =>
    businessServer.listen(0, "127.0.0.1", resolve),
  );
  businessPort = (businessServer.address() as AddressInfo).port;
});

test.afterAll(async () => {
  await new Promise<void>((resolve, reject) =>
    businessServer.close((error) => (error ? reject(error) : resolve())),
  );
});

test.afterEach(async ({ page }) => {
  if (!sourceName) return;
  const response = await page.request.get(platformApiUrl("/managed-mcp-sources"));
  if (!response.ok()) return;
  const payload = (await response.json()) as { items: Array<{ id: string; name: string }> };
  const source = payload.items.find((item) => item.name === sourceName);
  if (!source) return;
  await page.request.delete(platformApiUrl(`/managed-mcp-sources/${source.id}`), {
    headers: await platformWriteHeaders(page),
  });
});

test("manages a business HTTP capability through the formal MCP page", async ({ page }) => {
  const marker = Date.now();
  sourceName = `订单系统-${marker}`;
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));

  await page.goto("/tools");
  await expect(page.getByRole("heading", { name: "工具与 MCP" })).toBeVisible();
  await page.getByRole("button", { name: "新建托管 MCP" }).click();
  const sourceDialog = page.getByRole("dialog", { name: "新建托管 MCP" });
  await sourceDialog.getByRole("textbox", { name: "名称" }).fill(sourceName);
  await sourceDialog
    .getByRole("textbox", { name: "Base URL" })
    .fill(`http://localhost:${businessPort}/api`);
  const sourceResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/v1/managed-mcp-sources") &&
      response.request().method() === "POST",
  );
  await sourceDialog.getByRole("button", { name: "确认创建" }).click();
  expect((await sourceResponse).status()).toBe(201);

  await page.getByRole("button", { name: `配置鉴权 ${sourceName}` }).click();
  const credentialDialog = page.getByRole("dialog", { name: "配置 MCP 鉴权" });
  await credentialDialog.getByRole("combobox", { name: "鉴权方式" }).click();
  await page.getByText("Bearer Token", { exact: true }).last().click();
  await credentialDialog.getByLabel("Bearer Token").fill(bearerToken);
  const credentialResponse = page.waitForResponse(
    (response) =>
      response.url().includes("/credentials") && response.request().method() === "PUT",
  );
  await credentialDialog.getByRole("button", { name: "保存鉴权" }).click();
  expect((await credentialResponse).status()).toBe(200);

  await page.getByRole("button", { name: `导入 OpenAPI ${sourceName}` }).click();
  const importDialog = page.getByRole("dialog", {
    name: `导入 OpenAPI · ${sourceName}`,
  });
  const openApiDocument = {
    openapi: "3.1.0",
    info: { title: "订单业务", version: "1.0.0" },
    paths: {
      "/orders/{order_id}": {
        get: {
          operationId: "orders.get",
          summary: "查询订单",
          description: "按编号查询订单。",
          parameters: [
            {
              name: "order_id",
              in: "path",
              required: true,
              schema: { type: "string" },
            },
          ],
          responses: { "200": { description: "查询成功" } },
        },
      },
    },
  };
  await importDialog.getByLabel("选择 OpenAPI 文件").setInputFiles({
    name: "orders.openapi.json",
    mimeType: "application/json",
    buffer: Buffer.from(JSON.stringify(openApiDocument)),
  });
  const previewResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/openapi/preview") && response.request().method() === "POST",
  );
  await importDialog.getByRole("button", { name: "解析文件" }).click();
  expect((await previewResponse).status()).toBe(200);
  await expect(importDialog.getByText("已解析 1 项接口")).toBeVisible();
  await expect(importDialog.getByText(/参数 order_id 缺少含义/)).toBeVisible();
  await importDialog
    .getByLabel("输入 Schema GET /orders/{order_id}")
    .fill(
      JSON.stringify({
        type: "object",
        properties: { order_id: { type: "string", description: "订单编号" } },
        required: ["order_id"],
        additionalProperties: false,
      }),
    );
  await importDialog
    .getByLabel("响应 JSON Pointer GET /orders/{order_id}")
    .fill("/data/order");
  const importResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/openapi/import") && response.request().method() === "POST",
  );
  await importDialog.getByRole("button", { name: "导入选中能力" }).click();
  expect((await importResponse).status()).toBe(201);
  await expect(importDialog).toBeHidden();

  const discoveryResponse = page.waitForResponse(
    (response) => response.url().endsWith("/discover") && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: `发现能力 ${sourceName}` }).click();
  expect((await discoveryResponse).status()).toBe(200);
  await expect(page.getByText("已通过 MCP 发现 1 项启用能力")).toBeVisible();

  await page.getByRole("button", { name: "测试调用 查询订单" }).click();
  const callDialog = page.getByRole("dialog", { name: "测试调用 · 查询订单" });
  await expect(callDialog.getByText(/真实业务副作用/)).toBeVisible();
  await callDialog
    .getByRole("textbox", { name: "调用参数 JSON" })
    .fill('{"order_id":"A-100"}');
  const callResponse = page.waitForResponse(
    (response) => response.url().endsWith("/test-call") && response.request().method() === "POST",
  );
  await callDialog.getByRole("button", { name: "确认调用" }).click();
  expect((await callResponse).status()).toBe(200);
  await expect(callDialog.getByText('{"id":"A-100"}')).toBeVisible();
  await callDialog.getByRole("button", { name: /关\s*闭/ }).click();

  await page.getByRole("button", { name: "删除工具能力 查询订单" }).click();
  await page.getByRole("button", { name: "确认删除工具能力 查询订单" }).click();
  await expect(page.getByText("查询订单")).toHaveCount(0);
  await page.getByRole("button", { name: `删除托管 MCP ${sourceName}` }).click();
  await page.getByRole("button", { name: `确认删除托管 MCP ${sourceName}` }).click();
  await expect(page.getByText(sourceName)).toHaveCount(0);
  expect(pageErrors).toEqual([]);
});
