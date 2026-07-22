import { defineConfig, devices } from "@playwright/test";

const hostResolverRules = process.env.COMMON_AGENT_E2E_HOST_RESOLVER_RULES?.trim();
const localDomainArgs = hostResolverRules
  ? [
      "--proxy-server=direct://",
      "--proxy-bypass-list=*",
      `--host-resolver-rules=${hostResolverRules}`,
    ]
  : [];

export default defineConfig({
  testDir: "./e2e",
  outputDir: process.env.COMMON_AGENT_E2E_ARTIFACT_DIR ?? "./test-results",
  fullyParallel: false,
  forbidOnly: true,
  retries: 0,
  workers: 1,
  reporter: "line",
  timeout: 240_000,
  expect: {
    timeout: 180_000,
  },
  use: {
    baseURL: process.env.COMMON_AGENT_E2E_FRONTEND_URL ?? "http://127.0.0.1:18280",
    ignoreHTTPSErrors: process.env.COMMON_AGENT_E2E_IGNORE_HTTPS_ERRORS === "true",
    actionTimeout: 15_000,
    headless: true,
    launchOptions: {
      channel: "chromium-headless-shell",
      args: [
        "--headless",
        "--no-startup-window",
        ...localDomainArgs,
      ],
    },
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
    video: "off",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
