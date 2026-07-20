import { expect, test } from "@playwright/test";

function requiredEnvironment(name: string): string {
  const value = process.env[name]?.trim();
  if (!value) throw new Error(`${name} is required`);
  return value;
}

const apiURL = requiredEnvironment("COMMON_AGENT_E2E_API_URL");
const prefix = requiredEnvironment("COMMON_AGENT_E2E_LIST_PREFIX");

test("keeps a stable employee cursor chain while rows are inserted and deleted", async ({
  page,
  request,
}) => {
  const employeeIds: string[] = [];
  let newerId: string | undefined;
  try {
    for (let index = 0; index < 25; index += 1) {
      const response = await request.post(`${apiURL}/employees`, {
        data: {
          name: `${prefix}-${index.toString().padStart(2, "0")}`,
          description: "U9-03 大列表浏览器验收",
          system_prompt: "只用于分页浏览器验收。",
          knowledge_base_id: null,
          allowed_workflow_ids: [],
        },
      });
      expect(response.status()).toBe(201);
      employeeIds.push(((await response.json()) as { id: string }).id);
    }

    await page.goto("/employees");
    const firstPageResponse = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return (
        url.pathname === "/api/v1/employees" &&
        url.searchParams.get("search") === prefix &&
        !url.searchParams.has("cursor")
      );
    });
    await page.getByLabel("搜索数字员工").fill(prefix);
    expect((await firstPageResponse).status()).toBe(200);
    const cards = page.locator(".employee-card");
    await expect(cards).toHaveCount(20);
    await expect(page.getByRole("button", { name: "加载更多数字员工" })).toBeVisible();

    const anchorId = employeeIds[5];
    expect((await request.delete(`${apiURL}/employees/${anchorId}`)).status()).toBe(204);
    const newerName = `${prefix}-newer`;
    const newerResponse = await request.post(`${apiURL}/employees`, {
      data: {
        name: newerName,
        description: "首屏后并发新增",
        system_prompt: "只用于分页浏览器验收。",
        knowledge_base_id: null,
        allowed_workflow_ids: [],
      },
    });
    expect(newerResponse.status()).toBe(201);
    newerId = ((await newerResponse.json()) as { id: string }).id;

    const nextPageResponse = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return url.pathname === "/api/v1/employees" && url.searchParams.has("cursor");
    });
    await page.getByRole("button", { name: "加载更多数字员工" }).click();
    expect((await nextPageResponse).status()).toBe(200);
    await expect(cards).toHaveCount(25);
    const visibleNames = await cards.evaluateAll((elements) =>
      elements.map((element) => element.querySelector(".ant-card-head-title")?.textContent ?? ""),
    );
    expect(new Set(visibleNames).size).toBe(25);
    expect(visibleNames).not.toContain(newerName);
    await expect(page.getByRole("button", { name: "加载更多数字员工" })).toHaveCount(0);

    const refreshedSearch = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return url.pathname === "/api/v1/employees" && url.searchParams.get("search") === newerName;
    });
    await page.getByLabel("搜索数字员工").fill(newerName);
    expect((await refreshedSearch).status()).toBe(200);
    await expect(cards).toHaveCount(1);
    await expect(cards.first()).toContainText(newerName);
  } finally {
    for (const employeeId of [...employeeIds, ...(newerId ? [newerId] : [])]) {
      const response = await request.delete(`${apiURL}/employees/${employeeId}`);
      expect(response.status()).toBe(204);
    }
  }
});
