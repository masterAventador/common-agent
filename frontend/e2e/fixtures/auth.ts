import {
  expect,
  test as base,
  type Page,
} from "@playwright/test";

function requiredEnvironment(name: string): string {
  const value = process.env[name]?.trim();
  if (!value) throw new Error(`${name} is required`);
  return value;
}

const apiUrl = requiredEnvironment("COMMON_AGENT_E2E_API_URL").replace(/\/$/, "");
const bootstrapToken = requiredEnvironment("COMMON_AGENT_E2E_AUTH_BOOTSTRAP_TOKEN");
const email = requiredEnvironment("COMMON_AGENT_E2E_AUTH_EMAIL");
const password = requiredEnvironment("COMMON_AGENT_E2E_AUTH_PASSWORD");
const trustedOrigin =
  process.env.COMMON_AGENT_E2E_TRUSTED_ORIGIN?.trim() || "http://127.0.0.1:18280";
const apiHostHeader = process.env.COMMON_AGENT_E2E_API_HOST_HEADER?.trim();

function apiHostHeaders(headers: Record<string, string> = {}): Record<string, string> {
  return apiHostHeader ? { Host: apiHostHeader, ...headers } : headers;
}

export function platformApiUrl(path: string): string {
  return `${apiUrl}${path.startsWith("/") ? path : `/${path}`}`;
}

async function synchronizeLoopbackAuthCookies(page: Page): Promise<void> {
  if (!apiHostHeader) return;
  const cookies = await page.context().cookies(apiUrl);
  expect(cookies).not.toHaveLength(0);
  await page.context().addCookies(
    cookies.map(({ name, value, expires, httpOnly, secure, sameSite }) => ({
      name,
      value,
      url: trustedOrigin,
      expires,
      httpOnly,
      secure,
      sameSite,
    })),
  );
}

async function authenticate(page: Page): Promise<void> {
  const policyResponse = await page.request.get(`${apiUrl}/auth/policy`, {
    headers: apiHostHeaders(),
  });
  expect(policyResponse.status()).toBe(200);
  const policy = (await policyResponse.json()) as { registration_available: boolean };
  const response = policy.registration_available
    ? await page.request.post(`${apiUrl}/auth/register`, {
        headers: apiHostHeaders({ Origin: trustedOrigin }),
        data: { email, password, bootstrap_token: bootstrapToken },
      })
    : await page.request.post(`${apiUrl}/auth/login`, {
        headers: apiHostHeaders({ Origin: trustedOrigin }),
        data: { email, password },
      });
  expect(response.status()).toBe(policy.registration_available ? 201 : 200);
  await synchronizeLoopbackAuthCookies(page);
}

export async function platformWriteHeaders(page: Page): Promise<Record<string, string>> {
  const response = await page.request.get(`${apiUrl}/auth/session`, {
    headers: apiHostHeaders(),
  });
  expect(response.status()).toBe(200);
  const session = (await response.json()) as { csrf_token: string };
  return apiHostHeaders({
    Origin: trustedOrigin,
    "X-CSRF-Token": session.csrf_token,
  });
}

export const test = base.extend({
  page: async ({ page }, fixtureUse) => {
    await authenticate(page);
    await fixtureUse(page);
  },
});

export { expect };
