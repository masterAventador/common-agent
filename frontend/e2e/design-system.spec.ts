import { expect, test } from "./fixtures/auth";

const routes = [
  { path: "/chat", heading: "AI 会话" },
  { path: "/employees", heading: "数字员工" },
  { path: "/knowledge-bases", heading: "知识库" },
  { path: "/workflows", heading: "工作流" },
  { path: "/audit-events", heading: "审计与安全事件" },
] as const;

test("keeps the unified product shell on every production page", async ({ page }) => {
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  await page.setViewportSize({ width: 1440, height: 1000 });

  for (const route of routes) {
    await page.goto(route.path);
    await expect(page.getByRole("heading", { name: route.heading })).toBeVisible();
    await expect(page.getByRole("navigation", { name: "主导航" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Common Agent 首页" })).toBeVisible();
    await expect(page.getByTestId("brand-logo")).toBeVisible();
    await expect(page.getByText("PowerAI", { exact: false })).toHaveCount(0);
  }

  await expect
    .poll(() => page.locator("body").evaluate((element) => getComputedStyle(element).backgroundColor))
    .toBe("rgb(250, 250, 250)");
  await expect(page.locator(".app-sider")).toHaveCSS("width", "232px");
  expect(pageErrors).toEqual([]);
});

test("keeps the formal navigation and content usable on a narrow viewport", async ({ page }) => {
  await page.setViewportSize({ width: 760, height: 900 });
  await page.goto("/employees");

  await expect(page.getByRole("heading", { name: "数字员工" })).toBeVisible();
  await expect(page.getByRole("button", { name: "创建数字员工" })).toBeVisible();
  await expect(page.getByTestId("brand-logo")).toBeVisible();
  await expect(page.locator(".app-sider")).toHaveCSS("width", "72px");

  const layout = await page.evaluate(() => ({
    viewportWidth: window.innerWidth,
    documentWidth: document.documentElement.scrollWidth,
  }));
  expect(layout.documentWidth).toBeLessThanOrEqual(layout.viewportWidth);
});
