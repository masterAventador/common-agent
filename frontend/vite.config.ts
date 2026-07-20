import react from "@vitejs/plugin-react";
import { configDefaults, defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  build: {
    manifest: true,
    rolldownOptions: {
      output: {
        codeSplitting: {
          groups: [
            {
              name: "react-core",
              test: /node_modules\/(?:react|react-dom|react-router|react-router-dom|scheduler)\//,
              priority: 50,
              entriesAware: true,
            },
            {
              name: "workflow-canvas",
              test: /node_modules\/(?:@xyflow|d3-|zustand)\//,
              priority: 40,
              entriesAware: true,
              entriesAwareMergeThreshold: 30_000,
              minSize: 50_000,
              maxSize: 400_000,
            },
            {
              name: "antd",
              test: /node_modules\/(?:antd|@ant-design|@rc-component|rc-)\//,
              priority: 30,
              entriesAware: true,
              entriesAwareMergeThreshold: 30_000,
              minSize: 50_000,
              maxSize: 400_000,
            },
            {
              name: "data-client",
              test: /node_modules\/(?:@tanstack|axios|zod)\//,
              priority: 20,
              entriesAware: true,
            },
            {
              name: "vendor",
              test: /node_modules\//,
              minSize: 50_000,
              maxSize: 400_000,
              priority: 10,
              entriesAware: true,
              entriesAwareMergeThreshold: 30_000,
            },
          ],
        },
      },
    },
  },
  server: {
    host: "127.0.0.1",
    port: 18280,
    strictPort: true,
  },
  test: {
    coverage: {
      provider: "v8",
      reportsDirectory: "coverage",
      reporter: ["text", "json-summary"],
      include: ["src/**/*.{ts,tsx}"],
      exclude: [
        "src/**/*.test.{ts,tsx}",
        "src/api/generated/**",
        "src/main.tsx",
        "src/test/**",
        "src/vite-env.d.ts",
      ],
      thresholds: {
        lines: 86.17,
        branches: 75,
      },
    },
    environment: "jsdom",
    exclude: [...configDefaults.exclude, "e2e/**"],
    setupFiles: ["./src/test/setup.ts"],
  },
});
