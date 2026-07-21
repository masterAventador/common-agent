import { expect, test } from "@playwright/test";
import { execFile } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";

const repositoryRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const execFileAsync = promisify(execFile);

function requiredEnvironment(name: string): string {
  const value = process.env[name]?.trim();
  if (!value) throw new Error(`${name} is required`);
  return value;
}

const apiUrl = requiredEnvironment("COMMON_AGENT_E2E_API_URL").replace(/\/$/, "");
const bootstrapToken = requiredEnvironment("COMMON_AGENT_E2E_AUTH_BOOTSTRAP_TOKEN");
const email = requiredEnvironment("COMMON_AGENT_E2E_AUTH_EMAIL");
const password = requiredEnvironment("COMMON_AGENT_E2E_AUTH_PASSWORD");
const replacementPassword = `${password}-replacement`;
const trustedOrigin = "http://127.0.0.1:18280";

test("bootstraps one owner and rejects session, CSRF, and cross-origin attacks", async ({
  page,
}) => {
  await page.goto("/employees");
  await expect(page.getByRole("heading", { name: "创建首位管理员" })).toBeVisible({
    timeout: 10_000,
  });

  const crossOriginBootstrap = await page.request.post(`${apiUrl}/auth/register`, {
    headers: {
      Origin: "https://attacker.example",
      "Sec-Fetch-Site": "cross-site",
    },
    data: { email, password, bootstrap_token: bootstrapToken },
  });
  expect(crossOriginBootstrap.status()).toBe(403);
  expect((await crossOriginBootstrap.json()) as { code: string }).toMatchObject({
    code: "origin_validation_failed",
  });

  await page.getByRole("textbox", { name: "邮箱" }).fill(email);
  await page.getByLabel("密码").fill(password);
  await page.getByLabel("站点引导凭据").fill(bootstrapToken);
  const registeredResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/v1/auth/register") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "创建管理员" }).click();
  const registration = await registeredResponse;
  expect(registration.status()).toBe(201);
  const registered = (await registration.json()) as {
    csrf_token: string;
    recovery_codes: string[];
    session_token?: string;
  };
  expect(registered.recovery_codes).toHaveLength(8);
  expect(registered.session_token).toBeUndefined();
  await expect(page.getByRole("dialog", { name: "请妥善保存恢复码" })).toBeVisible();
  await page.getByRole("button", { name: "我已保存" }).click();
  await expect(page.getByRole("heading", { name: "数字员工" })).toBeVisible();
  await expect(page.getByText(email, { exact: true })).toBeVisible();

  const missingCsrf = await page.request.post(`${apiUrl}/employees`, {
    headers: { Origin: trustedOrigin },
    data: { name: "forbidden-without-csrf" },
  });
  expect(missingCsrf.status()).toBe(403);
  expect((await missingCsrf.json()) as { code: string }).toMatchObject({
    code: "csrf_validation_failed",
  });

  const crossOriginWrite = await page.request.post(`${apiUrl}/employees`, {
    headers: {
      Origin: "https://attacker.example",
      "Sec-Fetch-Site": "cross-site",
      "X-CSRF-Token": registered.csrf_token,
    },
    data: { name: "forbidden-cross-origin" },
  });
  expect(crossOriginWrite.status()).toBe(403);
  expect((await crossOriginWrite.json()) as { code: string }).toMatchObject({
    code: "origin_validation_failed",
  });

  const secondBootstrap = await page.request.post(`${apiUrl}/auth/register`, {
    headers: { Origin: trustedOrigin },
    data: {
      email: "second-owner@example.com",
      password,
      bootstrap_token: bootstrapToken,
    },
  });
  expect(secondBootstrap.status()).toBe(409);

  const logoutResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/v1/auth/logout") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "退出登录" }).click();
  expect((await logoutResponse).status()).toBe(204);
  await expect(page.getByRole("heading", { name: "登录 Common Agent" })).toBeVisible();

  await page.getByRole("button", { name: "使用恢复码重置密码" }).click();
  await page.getByRole("textbox", { name: "邮箱" }).fill(email);
  await page.getByRole("textbox", { name: "恢复码" }).fill(registered.recovery_codes[0]);
  await page.getByLabel("新密码").fill(replacementPassword);
  const resetResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/v1/auth/recovery/reset") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "重置密码" }).click();
  expect((await resetResponse).status()).toBe(204);

  await page.getByRole("textbox", { name: "邮箱" }).fill(email);
  await page.getByLabel("密码").fill(replacementPassword);
  const loginResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/v1/auth/login") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: /登\s*录/ }).click();
  const login = await loginResponse;
  expect(login.status()).toBe(200);
  const loggedIn = (await login.json()) as { csrf_token: string; session_token?: string };
  expect(loggedIn.session_token).toBeUndefined();
  await expect(page.getByRole("heading", { name: "数字员工" })).toBeVisible();

  await execFileAsync(
    "uv",
    ["run", "--frozen", "python", "-m", "tests.support.auth_e2e_state", "expire"],
    { cwd: path.join(repositoryRoot, "backend"), env: process.env },
  );
  await page.reload();
  await expect(page.getByRole("heading", { name: "登录 Common Agent" })).toBeVisible();
  expect((await page.request.get(`${apiUrl}/auth/session`)).status()).toBe(401);

  await page.getByRole("textbox", { name: "邮箱" }).fill(email);
  await page.getByLabel("密码").fill(replacementPassword);
  await page.getByRole("button", { name: /登\s*录/ }).click();
  await expect(page.getByRole("heading", { name: "数字员工" })).toBeVisible();
  const renewed = (await (await page.request.get(`${apiUrl}/auth/session`)).json()) as {
    csrf_token: string;
  };

  const sessionCookie = (await page.context().cookies()).find(
    (cookie) => cookie.name === "common_agent_session",
  );
  expect(sessionCookie).toBeDefined();
  const revoked = await page.request.post(`${apiUrl}/auth/logout`, {
    headers: {
      Origin: trustedOrigin,
      "X-CSRF-Token": renewed.csrf_token,
    },
  });
  expect(revoked.status()).toBe(204);
  await page.context().addCookies([sessionCookie!]);
  await page.reload();
  await expect(page.getByRole("heading", { name: "登录 Common Agent" })).toBeVisible();
  expect((await page.request.get(`${apiUrl}/auth/session`)).status()).toBe(401);
});
