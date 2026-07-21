import { readdir, readFile, stat } from "node:fs/promises";
import { resolve } from "node:path";

const MAX_CHUNK_BYTES = 500_000;
const MAX_ROUTE_BYTES = 1_500_000;
const ROUTES = new Map([
  ["/chat", "src/features/chat/ChatPage.tsx"],
  ["/employees", "src/features/employees/EmployeesPage.tsx"],
  ["/knowledge-bases", "src/features/knowledge-bases/KnowledgeBasesPage.tsx"],
  ["/workflows", "src/features/workflows/WorkflowsPage.tsx"],
  ["/audit-events", "src/features/audit/AuditEventsPage.tsx"],
]);

const outputRoot = resolve(process.argv[2] ?? "dist");
const manifestPath = resolve(outputRoot, ".vite", "manifest.json");

try {
  const manifest = JSON.parse(await readFile(manifestPath, "utf8"));
  const chunks = await listJavaScriptChunks(resolve(outputRoot, "assets"));
  if (chunks.length === 0) {
    throw new Error(`bundle 分析没有在 ${outputRoot} 找到 JS chunk`);
  }

  const oversized = chunks.filter((chunk) => chunk.bytes > MAX_CHUNK_BYTES);
  if (oversized.length > 0) {
    const details = oversized
      .map((chunk) => `${chunk.file}: ${chunk.bytes} bytes`)
      .join("\n");
    throw new Error(`JS chunk 超过固定预算 ${MAX_CHUNK_BYTES} bytes:\n${details}`);
  }

  const largest = chunks.toSorted((left, right) => right.bytes - left.bytes)[0];
  console.log(`Bundle 预算: ${MAX_CHUNK_BYTES} bytes`);
  console.log(`单路由首次 JS 图预算: ${MAX_ROUTE_BYTES} bytes`);
  console.log(`最大 JS chunk: ${largest.file} (${largest.bytes} bytes)`);
  for (const [route, source] of ROUTES) {
    const entry = manifest[source];
    if (!entry?.isDynamicEntry) {
      throw new Error(`bundle manifest 缺少异步路由入口 ${route}: ${source}`);
    }
    const routeFiles = collectRouteFiles(source, manifest);
    const routeBytes = [...routeFiles].reduce(
      (total, file) => total + (chunks.find((chunk) => chunk.file === file)?.bytes ?? 0),
      0,
    );
    if (routeBytes > MAX_ROUTE_BYTES) {
      throw new Error(
        `路由 ${route} 首次 JS 图 ${routeBytes} bytes 超过固定预算 ${MAX_ROUTE_BYTES} bytes`,
      );
    }
    console.log(`${route}: ${entry.file}, 首次 JS 图 ${routeBytes} bytes`);
  }
} catch (error) {
  const message = error instanceof Error ? error.message : String(error);
  console.error(`bundle 分析失败: ${message}`);
  process.exitCode = 1;
}

async function listJavaScriptChunks(assetsRoot) {
  const entries = await readdir(assetsRoot, { recursive: true, withFileTypes: true });
  return Promise.all(
    entries
      .filter((entry) => entry.isFile() && entry.name.endsWith(".js"))
      .map(async (entry) => {
        const path = resolve(entry.parentPath, entry.name);
        return {
          file: path.slice(outputRoot.length + 1),
          bytes: (await stat(path)).size,
        };
      }),
  );
}

function collectRouteFiles(entryKey, manifest) {
  const files = new Set();
  const visited = new Set();

  function visit(key) {
    if (visited.has(key)) {
      return;
    }
    visited.add(key);
    const chunk = manifest[key];
    if (!chunk) {
      throw new Error(`bundle manifest 引用了不存在的 chunk: ${key}`);
    }
    if (chunk.file.endsWith(".js")) {
      files.add(chunk.file);
    }
    for (const importedKey of chunk.imports ?? []) {
      visit(importedKey);
    }
  }

  visit(entryKey);
  return files;
}
