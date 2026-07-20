import { expect, test } from "@playwright/test";

const routes = [
  { path: "/chat", heading: "AI 会话", link: "AI 会话" },
  { path: "/employees", heading: "数字员工", link: "数字员工" },
  { path: "/knowledge-bases", heading: "知识库", link: "知识库" },
  { path: "/workflows", heading: "工作流", link: "工作流" },
] as const;

test("loads every production route within the local first-screen budget", async ({ page }) => {
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.name));

  for (const route of routes) {
    await page.goto(route.path);
    await expect(page.getByRole("heading", { name: route.heading })).toBeVisible();
    const loadedMilliseconds = await page.evaluate(() => {
      const navigation = performance.getEntriesByType("navigation")[0] as PerformanceNavigationTiming;
      return navigation.loadEventEnd || performance.now();
    });
    expect(loadedMilliseconds).toBeLessThan(10_000);
  }

  expect(pageErrors).toEqual([]);
});

test("reuses loaded route and vendor modules on repeated navigation", async ({ page }) => {
  const requestedScripts: string[] = [];
  page.on("request", (request) => {
    if (request.resourceType() === "script" && request.url().includes("/assets/")) {
      requestedScripts.push(request.url());
    }
  });

  await page.goto("/chat");
  await expect(page.getByRole("heading", { name: "AI 会话" })).toBeVisible();
  for (const route of routes.slice(1)) {
    await page.getByRole("link", { name: route.link }).click();
    await expect(page.getByRole("heading", { name: route.heading })).toBeVisible();
  }

  expect(requestedScripts.some((url) => url.includes("react-core"))).toBe(true);
  expect(requestedScripts.some((url) => url.includes("antd"))).toBe(true);
  expect(new Set(requestedScripts).size).toBe(requestedScripts.length);

  requestedScripts.length = 0;
  for (const route of routes) {
    await page.getByRole("link", { name: route.link }).click();
    await expect(page.getByRole("heading", { name: route.heading })).toBeVisible();
  }

  expect(requestedScripts).toEqual([]);
});
