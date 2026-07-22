import { expect, test, type Page } from "./fixtures/auth";
import { selectEmployeeDefaultModel } from "./fixtures/models";
import { Buffer } from "node:buffer";
import { execFile } from "node:child_process";
import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";

function requiredEnvironment(name: string): string {
  const value = process.env[name]?.trim();
  if (!value) throw new Error(`${name} is required`);
  return value;
}

const execFileAsync = promisify(execFile);
const repositoryRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const corpusDirectory = path.join(repositoryRoot, "test-data/knowledge-base/corpus");
const knowledgeBaseName = requiredEnvironment("COMMON_AGENT_E2E_BATCH_KNOWLEDGE_NAME");
const employeeName = requiredEnvironment("COMMON_AGENT_E2E_BATCH_EMPLOYEE_NAME");

test("batch-drags the full corpus, retries parsing, and answers a cross-document question", async ({
  page,
}) => {
  test.setTimeout(900_000);
  const directRagFlowRequests: string[] = [];
  let activeUploads = 0;
  let maximumConcurrentUploads = 0;
  let completedUploads = 0;
  const isDocumentUpload = (url: string, method: string) =>
    method === "POST" && /\/api\/v1\/knowledge-bases\/[^/]+\/documents$/.test(url);
  page.on("request", (request) => {
    if (new URL(request.url()).port === "19380") directRagFlowRequests.push(request.url());
    if (isDocumentUpload(request.url(), request.method())) {
      activeUploads += 1;
      maximumConcurrentUploads = Math.max(maximumConcurrentUploads, activeUploads);
    }
  });
  const finishUpload = (request: { url(): string; method(): string }) => {
    if (!isDocumentUpload(request.url(), request.method())) return;
    activeUploads -= 1;
    completedUploads += 1;
  };
  page.on("requestfinished", finishUpload);
  page.on("requestfailed", finishUpload);

  await page.goto("/knowledge-bases");
  await expect(page.getByRole("heading", { name: "知识库" })).toBeVisible();
  await page.getByRole("button", { name: "创建知识库" }).click();
  const knowledgeDialog = page.getByRole("dialog", { name: "创建知识库" });
  await knowledgeDialog.getByRole("textbox", { name: "名称" }).fill(knowledgeBaseName);
  await knowledgeDialog
    .getByRole("textbox", { name: "描述" })
    .fill("S10-07J 批量拖拽、解析重试和跨文档召回生产同路径验收");
  const created = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/v1/knowledge-bases") &&
      response.request().method() === "POST",
  );
  await knowledgeDialog.getByRole("button", { name: "确认创建" }).click();
  expect((await created).status()).toBe(201);

  const corpusPaths = readdirSync(corpusDirectory)
    .filter((name) => /\.(docx|md|pdf|txt)$/i.test(name))
    .sort()
    .map((name) => path.join(corpusDirectory, name));
  expect(corpusPaths).toHaveLength(12);
  await dropFiles(page, corpusPaths);
  const queueItems = page.locator(".knowledge-upload-item");
  await expect(queueItems).toHaveCount(12);
  await expect(queueItems.getByText("等待上传")).toHaveCount(12);
  await page.getByRole("button", { name: "开始上传" }).click();

  await expect.poll(() => completedUploads, { timeout: 180_000 }).toBe(12);
  expect(maximumConcurrentUploads).toBeLessThanOrEqual(2);
  for (const corpusPath of corpusPaths) {
    const name = path.basename(corpusPath);
    await expect(queueItems.filter({ hasText: name }).getByText("已完成")).toBeVisible({
      timeout: 600_000,
    });
  }

  await dropFiles(page, [corpusPaths[0]!]);
  await expect(page.getByText(/已存在或已在队列中/)).toBeVisible();
  expect(completedUploads).toBe(12);

  const retryFile = {
    name: "s10-07j-retry.docx",
    mimeType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    buffer: readFileSync(path.join(corpusDirectory, "04-pilot-acceptance.docx")),
  };
  await page.getByLabel("选择或拖拽文档").setInputFiles(retryFile);
  const retryUploadResponse = page.waitForResponse(
    (response) =>
      response.url().includes("/documents") && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "开始上传" }).click();
  const retryUpload = await retryUploadResponse;
  expect(retryUpload.status()).toBe(202);
  const uploaded = (await retryUpload.json()) as { id: string; knowledge_base_id: string };
  await cancelDocument(uploaded);
  const retryQueueItem = queueItems.filter({ hasText: retryFile.name });
  await expect(retryQueueItem.getByText("失败")).toBeVisible({ timeout: 180_000 });
  const retryResponse = page.waitForResponse(
    (response) => response.url().endsWith(`/documents/${uploaded.id}/retry`),
  );
  await retryQueueItem.getByRole("button", { name: `重试 ${retryFile.name}` }).click();
  expect((await retryResponse).status()).toBe(202);
  await expect(retryQueueItem.getByText("已完成")).toBeVisible({ timeout: 600_000 });

  const fastFailureFile = {
    name: "s10-07m-fast-failure.docx",
    mimeType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    buffer: readFileSync(path.join(corpusDirectory, "04-pilot-acceptance.docx")),
  };
  await dropFilePayloads(page, [fastFailureFile]);
  const fastFailureQueueItem = queueItems.filter({ hasText: fastFailureFile.name });
  await expect(fastFailureQueueItem).toHaveCount(1);
  const fastFailureUploadResponse = page.waitForResponse(
    (response) =>
      response.url().includes("/documents") && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "开始上传" }).click();
  const fastFailureUpload = await fastFailureUploadResponse;
  expect(fastFailureUpload.status()).toBe(202);
  const fastFailureDocument = (await fastFailureUpload.json()) as {
    id: string;
    knowledge_base_id: string;
  };
  await cancelDocument(fastFailureDocument);
  await expect(fastFailureQueueItem.getByText("失败")).toBeVisible({ timeout: 180_000 });
  const fastFailureRetryResponse = page.waitForResponse((response) =>
    response.url().endsWith(`/documents/${fastFailureDocument.id}/retry`),
  );
  await fastFailureQueueItem
    .getByRole("button", { name: `重试 ${fastFailureFile.name}` })
    .click();
  expect((await fastFailureRetryResponse).status()).toBe(202);
  const fastFailureRetryButton = fastFailureQueueItem.getByRole("button", {
    name: `重试 ${fastFailureFile.name}`,
  });
  await expect(fastFailureRetryButton).toHaveCount(0);
  await cancelDocument(fastFailureDocument);
  await expect(fastFailureRetryButton).toBeVisible({ timeout: 180_000 });

  await page.getByRole("link", { name: "数字员工" }).click();
  await page.getByRole("button", { name: "创建数字员工" }).click();
  const employeeDialog = page.getByRole("dialog", { name: "创建数字员工" });
  await employeeDialog.getByRole("textbox", { name: "名称" }).fill(employeeName);
  await employeeDialog
    .getByRole("textbox", { name: "说明" })
    .fill("S10-07J 跨文档召回验收员工");
  await employeeDialog
    .getByRole("textbox", { name: "系统指令" })
    .fill("只根据知识库事实回答；涉及多个来源时必须综合并保留引用。");
  await selectEmployeeDefaultModel(page, employeeDialog);
  await employeeDialog.getByRole("combobox", { name: "知识库" }).click();
  await page.getByTitle(knowledgeBaseName).click();
  const employeeCreated = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/v1/employees") && response.request().method() === "POST",
  );
  await employeeDialog.getByRole("button", { name: "确认创建" }).click();
  const employeeResponse = await employeeCreated;
  expect(employeeResponse.status()).toBe(201);
  const employeeCard = page.locator(".employee-card").filter({ hasText: employeeName });
  await employeeCard.getByRole("button", { name: `与${employeeName}开始对话` }).click();

  const question = "产品蓝图和试点验收中分别出现了多少家门店，为什么数字不同？";
  await page.getByRole("textbox", { name: "消息输入" }).fill(question);
  const turnStarted = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/v1/conversation-turns") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "发送消息" }).click();
  expect((await turnStarted).status()).toBe(202);
  await expect(page.getByText("正在生成")).toHaveCount(0, { timeout: 240_000 });
  const answer = page.locator(".chat-message.is-assistant .chat-message-content").last();
  await expect(answer).toContainText("18");
  await expect(answer).toContainText("12");
  await expect(answer).toContainText("6");
  const citations = page
    .locator(".chat-message.is-assistant")
    .last()
    .locator(".chat-citations");
  await expect(
    citations.getByText("01-product-blueprint.md", { exact: true }).first(),
  ).toBeVisible();
  await expect(
    citations.getByText("04-pilot-acceptance.docx", { exact: true }).first(),
  ).toBeVisible();
  expect(directRagFlowRequests).toEqual([]);
});

async function dropFiles(page: Page, paths: string[]): Promise<void> {
  const files = paths.map((filePath) => ({
    name: path.basename(filePath),
    mimeType: mimeType(filePath),
    buffer: readFileSync(filePath),
  }));
  await dropFilePayloads(page, files);
}

async function cancelDocument(document: {
  id: string;
  knowledge_base_id: string;
}): Promise<void> {
  await execFileAsync(
    "uv",
    ["run", "--frozen", "python", "-m", "tests.support.knowledge_e2e_cancel"],
    {
      cwd: path.join(repositoryRoot, "backend"),
      env: {
        ...process.env,
        COMMON_AGENT_E2E_KNOWLEDGE_BASE_ID: document.knowledge_base_id,
        COMMON_AGENT_E2E_DOCUMENT_ID: document.id,
      },
    },
  );
}

async function dropFilePayloads(
  page: Page,
  files: { name: string; mimeType: string; buffer: Buffer }[],
): Promise<void> {
  const serialized = files.map((file) => ({
    name: file.name,
    mimeType: file.mimeType,
    base64: file.buffer.toString("base64"),
  }));
  const dataTransfer = await page.evaluateHandle((values) => {
    const transfer = new DataTransfer();
    for (const value of values) {
      const binary = atob(value.base64);
      const bytes = Uint8Array.from(binary, (character) => character.charCodeAt(0));
      transfer.items.add(new File([bytes], value.name, { type: value.mimeType }));
    }
    return transfer;
  }, serialized);
  await page.getByRole("button", { name: "拖拽上传区域" }).dispatchEvent("drop", {
    dataTransfer,
  });
  await dataTransfer.dispose();
}

function mimeType(filePath: string): string {
  const extension = path.extname(filePath).toLowerCase();
  if (extension === ".pdf") return "application/pdf";
  if (extension === ".docx") {
    return "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
  }
  return extension === ".txt" ? "text/plain" : "text/markdown";
}
