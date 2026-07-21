import { expect, platformWriteHeaders, test } from "./fixtures/auth";

function requiredEnvironment(name: string): string {
  const value = process.env[name]?.trim();
  if (!value) throw new Error(`${name} is required`);
  return value;
}

const apiURL = requiredEnvironment("COMMON_AGENT_E2E_API_URL");
const prefix = requiredEnvironment("COMMON_AGENT_E2E_KNOWLEDGE_PAGE_PREFIX");

test("lists more than one hundred tenant knowledge bases through real RAGFlow", async ({ page }) => {
  test.setTimeout(600_000);
  const createdIds: string[] = [];
  const headers = await platformWriteHeaders(page);
  try {
    for (let start = 0; start < 105; start += 5) {
      const responses = await Promise.all(
        Array.from({ length: Math.min(5, 105 - start) }, async (_, offset) => {
          const index = start + offset;
          return page.request.post(`${apiURL}/knowledge-bases`, {
            headers,
            data: {
              name: `${prefix}-${index.toString().padStart(3, "0")}`,
              description: "真实 RAGFlow 大列表分页验收",
            },
          });
        }),
      );
      for (const response of responses) {
        expect(response.status()).toBe(201);
        createdIds.push(((await response.json()) as { id: string }).id);
      }
    }

    await page.goto("/knowledge-bases");
    const firstPage = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return (
        url.pathname === "/api/v1/knowledge-bases" &&
        url.searchParams.get("search") === prefix &&
        !url.searchParams.has("cursor")
      );
    });
    await page.getByLabel("搜索知识库").fill(prefix);
    expect((await firstPage).status()).toBe(200);

    const items = page.locator(".knowledge-base-item");
    await expect(items).toHaveCount(20);
    for (const expectedCount of [40, 60, 80, 100, 105]) {
      const nextPage = page.waitForResponse((response) => {
        const url = new URL(response.url());
        return url.pathname === "/api/v1/knowledge-bases" && url.searchParams.has("cursor");
      });
      await page.getByRole("button", { name: "加载更多知识库" }).click();
      expect((await nextPage).status()).toBe(200);
      await expect(items).toHaveCount(expectedCount);
    }
    await expect(page.getByRole("button", { name: "加载更多知识库" })).toHaveCount(0);
    await expect(
      page.locator(".knowledge-base-item", { hasText: `${prefix}-104` }),
    ).toBeVisible();
  } finally {
    for (const knowledgeBaseId of createdIds) {
      const response = await page.request.delete(
        `${apiURL}/knowledge-bases/${knowledgeBaseId}`,
        { headers },
      );
      expect(response.status()).toBe(204);
    }
  }
});
