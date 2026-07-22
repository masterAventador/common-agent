import type { APIResponse } from "@playwright/test";

import { expect, platformApiUrl, platformWriteHeaders, test } from "./fixtures/auth";

function expectSecurityHeaders(response: APIResponse): void {
  const headers = response.headers();
  expect(headers["strict-transport-security"]).toBe(
    "max-age=31536000; includeSubDomains",
  );
  expect(headers["x-content-type-options"]).toBe("nosniff");
  expect(headers["x-frame-options"]).toBe("DENY");
  expect(headers["referrer-policy"]).toBe("no-referrer");
  expect(headers["permissions-policy"]).toBe("camera=(), microphone=(), geolocation=()");
  expect(headers["content-security-policy"]).toContain("default-src 'self'");
  expect(headers["content-security-policy"]).toContain("object-src 'none'");
  expect(headers["content-security-policy"]).toContain("frame-ancestors 'none'");
}

test("serves browser security headers without breaking the production React entry", async ({
  page,
}) => {
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.name));

  const navigation = await page.goto("/chat");
  expect(navigation).not.toBeNull();
  expectSecurityHeaders(navigation!);
  await expect(page.getByRole("heading", { name: "AI 会话" })).toBeVisible();

  const apiResponse = await page.request.get(platformApiUrl("/system/health"), {
    headers: await platformWriteHeaders(page),
  });
  expect(apiResponse.status()).toBe(200);
  expectSecurityHeaders(apiResponse);
  expect(pageErrors).toEqual([]);
});
