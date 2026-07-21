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
const memberEmail = "viewer.e2e@example.com";
const memberPassword = "viewer e2e password is long enough";
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

  await page.getByRole("button", { name: "新建工作区" }).click();
  const workspaceDialog = page.getByRole("dialog", { name: "新建工作区" });
  await workspaceDialog.getByLabel("工作区名称").fill("浏览器隔离工作区");
  const workspaceResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/v1/tenants") &&
      response.request().method() === "POST",
  );
  await workspaceDialog.getByRole("button", { name: /创\s*建/ }).click();
  expect((await workspaceResponse).status()).toBe(201);
  await expect(page.getByText(/浏览器隔离工作区/)).toBeVisible();

  await page.getByRole("button", { name: "添加成员" }).click();
  const memberDialog = page.getByRole("dialog", { name: "添加工作区成员" });
  await memberDialog.getByLabel("邮箱").fill(memberEmail);
  await memberDialog.getByLabel("初始密码").fill(memberPassword);
  const memberResponse = page.waitForResponse(
    (response) =>
      response.url().includes("/api/v1/tenants/") &&
      response.url().endsWith("/members") &&
      response.request().method() === "POST",
  );
  await memberDialog.getByRole("button", { name: /创\s*建\s*账\s*号/ }).click();
  const provisioned = await memberResponse;
  expect(provisioned.status()).toBe(201);
  expect((await provisioned.json()) as { role: string }).toMatchObject({ role: "viewer" });
  const memberRecoveryDialog = page.getByRole("dialog", { name: "成员账号已创建" });
  await expect(memberRecoveryDialog).toContainText(memberEmail);
  await expect(memberRecoveryDialog).toContainText(/\w{8}-\w{8}/);
  await memberRecoveryDialog.getByRole("button", { name: "我已保存" }).click();

  await page.getByRole("button", { name: "退出登录" }).click();
  await page.getByRole("textbox", { name: "邮箱" }).fill(memberEmail);
  await page.getByLabel("密码").fill(memberPassword);
  await page.getByRole("button", { name: /登\s*录/ }).click();
  await expect(page.getByText("当前工作区为只读模式")).toBeVisible();
  await expect(page.getByText("访客", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "添加成员" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "创建数字员工" })).toBeDisabled();

  await page.getByRole("button", { name: "退出登录" }).click();
  await page.getByRole("textbox", { name: "邮箱" }).fill(email);
  await page.getByLabel("密码").fill(password);
  const ownerLoginResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/v1/auth/login") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: /登\s*录/ }).click();
  const ownerLogin = await ownerLoginResponse;
  expect(ownerLogin.status()).toBe(200);
  const ownerSession = (await ownerLogin.json()) as { csrf_token: string };
  await expect(page.getByRole("heading", { name: "数字员工" })).toBeVisible();

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
      "X-CSRF-Token": ownerSession.csrf_token,
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
