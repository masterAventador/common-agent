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
const trustedOrigin = "http://127.0.0.1:18280";

async function authenticate(page: Page): Promise<void> {
  const policyResponse = await page.request.get(`${apiUrl}/auth/policy`);
  expect(policyResponse.status()).toBe(200);
  const policy = (await policyResponse.json()) as { registration_available: boolean };
  const response = policy.registration_available
    ? await page.request.post(`${apiUrl}/auth/register`, {
        headers: { Origin: trustedOrigin },
        data: { email, password, bootstrap_token: bootstrapToken },
      })
    : await page.request.post(`${apiUrl}/auth/login`, {
        headers: { Origin: trustedOrigin },
        data: { email, password },
      });
  expect(response.status()).toBe(policy.registration_available ? 201 : 200);
}

export async function platformWriteHeaders(page: Page): Promise<Record<string, string>> {
  const response = await page.request.get(`${apiUrl}/auth/session`);
  expect(response.status()).toBe(200);
  const session = (await response.json()) as { csrf_token: string };
  return {
    Origin: trustedOrigin,
    "X-CSRF-Token": session.csrf_token,
  };
}

export const test = base.extend({
  page: async ({ page }, fixtureUse) => {
    await authenticate(page);
    await fixtureUse(page);
  },
});

export { expect };
