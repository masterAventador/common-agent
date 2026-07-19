import { defineConfig, devices } from "@playwright/test";

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
    actionTimeout: 15_000,
    headless: true,
    launchOptions: {
      channel: "chromium-headless-shell",
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
