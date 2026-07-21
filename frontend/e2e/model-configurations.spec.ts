import { execFileSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test } from "./fixtures/auth";

function requiredEnvironment(name: string): string {
  const value = process.env[name]?.trim();
  if (!value) throw new Error(`${name} is required`);
  return value;
}

const modelName = requiredEnvironment("COMMON_AGENT_E2E_MODEL_NAME");
const repositoryRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");

function setReference(action: "add-reference" | "remove-reference", id: string) {
  execFileSync(
    path.join(repositoryRoot, "scripts/uv.sh"),
    [
      "run",
      "--frozen",
      "python",
      "-m",
      "tests.support.model_configuration_e2e_state",
      action,
      id,
    ],
    {
      cwd: path.join(repositoryRoot, "backend"),
      env: process.env,
      stdio: "pipe",
    },
  );
}

test("manages and verifies a Bailian model through the formal production page", async ({
  page,
}) => {
  test.setTimeout(240_000);
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));

  await page.goto("/model-configurations");
  await expect(page.getByRole("heading", { name: "模型管理" })).toBeVisible();
  await page.getByRole("button", { name: "创建模型" }).click();
  const createDialog = page.getByRole("dialog", { name: "创建模型" });
  await createDialog.getByRole("textbox", { name: "显示名称" }).fill(modelName);
  await createDialog
    .getByRole("textbox", { name: "百炼模型标识" })
    .fill("qwen-plus");
  const createResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/v1/model-configurations") &&
      response.request().method() === "POST",
  );
  await createDialog.getByRole("button", { name: "确认创建" }).click();
  const created = await createResponse;
  expect(created.status()).toBe(201);
  const configuration = (await created.json()) as { id: string };

  let card = page.locator(".model-configuration-card").filter({ hasText: modelName });
  await expect(card).toContainText("qwen-plus");
  await expect(card).toContainText("阿里百炼");
  const verifyResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/api/v1/model-configurations/${configuration.id}/verify`) &&
      response.request().method() === "POST",
  );
  await card.getByRole("button", { name: `测试调用 ${modelName}` }).click();
  expect((await verifyResponse).status()).toBe(200);
  await expect(page.getByText("模型调用成功")).toBeVisible();

  await page.reload();
  card = page.locator(".model-configuration-card").filter({ hasText: modelName });
  await expect(card).toContainText("qwen-plus");
  await card.getByRole("button", { name: `编辑 ${modelName}` }).click();
  const editDialog = page.getByRole("dialog", { name: "编辑模型" });
  await editDialog
    .getByRole("textbox", { name: "显示名称" })
    .fill(`${modelName}-已停用`);
  await editDialog.getByRole("switch", { name: "启用状态" }).click();
  const updateResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/api/v1/model-configurations/${configuration.id}`) &&
      response.request().method() === "PUT",
  );
  await editDialog.getByRole("button", { name: "保存修改" }).click();
  expect((await updateResponse).status()).toBe(200);

  await page.reload();
  const updatedName = `${modelName}-已停用`;
  card = page.locator(".model-configuration-card").filter({ hasText: updatedName });
  await expect(card).toContainText("停用");

  setReference("add-reference", configuration.id);
  await card.getByRole("button", { name: `删除模型 ${updatedName}` }).click();
  const blockedResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/api/v1/model-configurations/${configuration.id}`) &&
      response.request().method() === "DELETE",
  );
  await page.getByRole("button", { name: `确认删除模型 ${updatedName}` }).click();
  expect((await blockedResponse).status()).toBe(409);
  await expect(
    page.getByText("该模型仍被数字员工或工作流引用，请先解除引用。"),
  ).toBeVisible();
  await expect(card).toBeVisible();

  setReference("remove-reference", configuration.id);
  await card.getByRole("button", { name: `删除模型 ${updatedName}` }).click();
  const deleteResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/api/v1/model-configurations/${configuration.id}`) &&
      response.request().method() === "DELETE",
  );
  await page.getByRole("button", { name: `确认删除模型 ${updatedName}` }).click();
  expect((await deleteResponse).status()).toBe(204);
  await expect(card).toHaveCount(0);
  expect(pageErrors).toEqual([]);
});
