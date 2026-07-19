import { expect, test } from "@playwright/test";
import { Buffer } from "node:buffer";
import { execFile } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";

const fixtureDirectory = path.join(path.dirname(fileURLToPath(import.meta.url)), "fixtures");
const repositoryRoot = path.resolve(fixtureDirectory, "../../..");
const execFileAsync = promisify(execFile);
const knowledgeBaseName =
  process.env.COMMON_AGENT_E2E_KNOWLEDGE_NAME ?? "common-agent-k2-06-red";

test("creates a generic knowledge base and shows real completed and failed parsing states", async ({
  page,
}) => {
  test.setTimeout(240_000);
  const directRagFlowRequests: string[] = [];
  page.on("request", (request) => {
    if (new URL(request.url()).port === "19380") directRagFlowRequests.push(request.url());
  });

  await page.goto("/knowledge-bases");
  await expect(page.getByRole("heading", { name: "知识库" })).toBeVisible();
  await expect(page.getByText("后端正常")).toBeVisible();

  await page.getByRole("button", { name: "创建知识库" }).click();
  const dialog = page.getByRole("dialog", { name: "创建知识库" });
  await dialog.getByRole("textbox", { name: "名称" }).fill(knowledgeBaseName);
  await dialog
    .getByRole("textbox", { name: "描述" })
    .fill("K2-06 通用知识库 Playwright 生产同路径验收");

  const createdResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/v1/knowledge-bases") &&
      response.request().method() === "POST",
  );
  await dialog.getByRole("button", { name: "确认创建" }).click();
  expect((await createdResponse).status()).toBe(201);
  await expect(page.getByRole("button", { name: new RegExp(knowledgeBaseName) })).toBeVisible();

  await page
    .getByLabel("选择文档")
    .setInputFiles(path.join(fixtureDirectory, "generic-knowledge.txt"));
  const uploadedResponse = page.waitForResponse(
    (response) =>
      response.url().includes("/documents") && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "上传文档" }).click();
  expect((await uploadedResponse).status()).toBe(202);

  const completedRow = page.getByRole("row").filter({ hasText: "generic-knowledge.txt" });
  await expect(completedRow.getByText("已完成")).toBeVisible({ timeout: 180_000 });

  await page.reload();
  await expect(page.getByRole("button", { name: new RegExp(knowledgeBaseName) })).toBeVisible();
  await expect(completedRow.getByText("已完成")).toBeVisible();

  await page
    .getByLabel("选择文档")
    .setInputFiles({
      name: "cancelled-parsing.txt",
      mimeType: "text/plain",
      buffer: Buffer.from("用于验证真实解析取消状态的通用知识内容。\n".repeat(65_536)),
    });
  const failedUploadResponse = page.waitForResponse(
    (response) =>
      response.url().includes("/documents") && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "上传文档" }).click();
  const failedResponse = await failedUploadResponse;
  expect(failedResponse.status()).toBe(202);
  const failedUpload = (await failedResponse.json()) as {
    id: string;
    knowledge_base_id: string;
  };
  expect(failedUpload.id).toEqual(expect.any(String));
  expect(failedUpload.knowledge_base_id).toEqual(expect.any(String));
  await execFileAsync(
    "uv",
    ["run", "--frozen", "python", "-m", "tests.support.knowledge_e2e_cancel"],
    {
      cwd: path.join(repositoryRoot, "backend"),
      env: {
        ...process.env,
        COMMON_AGENT_E2E_KNOWLEDGE_BASE_ID: failedUpload.knowledge_base_id,
        COMMON_AGENT_E2E_DOCUMENT_ID: failedUpload.id,
      },
    },
  );
  const failedRow = page.getByRole("row").filter({ hasText: "cancelled-parsing.txt" });
  await expect(failedRow.getByText("解析失败")).toBeVisible({ timeout: 180_000 });
  await expect(failedRow.getByText("document_parsing_failed")).toBeVisible();

  expect(directRagFlowRequests).toEqual([]);
});
