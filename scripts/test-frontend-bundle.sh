#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
CHECKER="${REPOSITORY_ROOT}/frontend/scripts/check-bundle-budget.mjs"
FIXTURE_ROOT="$(mktemp -d)"
OUTPUT="$(mktemp)"

cleanup() {
  rm -rf "${FIXTURE_ROOT}"
  rm -f "${OUTPUT}"
}
trap cleanup EXIT

fail() {
  echo "$1" >&2
  exit 1
}

[[ -f "${CHECKER}" ]] || fail "缺少前端 bundle 预算检查器"

mkdir -p "${FIXTURE_ROOT}/assets" "${FIXTURE_ROOT}/.vite"
for route in ChatPage EmployeesPage KnowledgeBasesPage ModelConfigurationsPage ToolsPage WorkflowsPage AuditEventsPage; do
  route_file="${route}.js"
  printf 'export const route = true;\n' > "${FIXTURE_ROOT}/assets/${route_file}"
done
cat > "${FIXTURE_ROOT}/.vite/manifest.json" <<'JSON'
{
  "src/features/chat/ChatPage.tsx": {"file":"assets/ChatPage.js","isDynamicEntry":true},
  "src/features/employees/EmployeesPage.tsx": {"file":"assets/EmployeesPage.js","isDynamicEntry":true},
  "src/features/knowledge-bases/KnowledgeBasesPage.tsx": {"file":"assets/KnowledgeBasesPage.js","isDynamicEntry":true},
  "src/features/model-configurations/ModelConfigurationsPage.tsx": {"file":"assets/ModelConfigurationsPage.js","isDynamicEntry":true},
  "src/features/tools/ToolsPage.tsx": {"file":"assets/ToolsPage.js","isDynamicEntry":true},
  "src/features/workflows/WorkflowsPage.tsx": {"file":"assets/WorkflowsPage.js","isDynamicEntry":true},
  "src/features/audit/AuditEventsPage.tsx": {"file":"assets/AuditEventsPage.js","isDynamicEntry":true}
}
JSON

node "${CHECKER}" "${FIXTURE_ROOT}" > "${OUTPUT}"
grep -Fq '最大 JS chunk' "${OUTPUT}" || fail "bundle 分析没有报告最大 chunk"
for route in /chat /employees /knowledge-bases /model-configurations /tools /workflows /audit-events; do
  grep -Fq "${route}" "${OUTPUT}" || fail "bundle 分析缺少路由 ${route}"
done

python3 - "${FIXTURE_ROOT}/.vite/manifest.json" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
manifest = json.loads(path.read_text())
del manifest["src/features/audit/AuditEventsPage.tsx"]
path.write_text(json.dumps(manifest))
PY
if node "${CHECKER}" "${FIXTURE_ROOT}" > "${OUTPUT}" 2>&1; then
  fail "缺少审计异步路由时 bundle 分析仍被放行"
fi
grep -Fq '/audit-events' "${OUTPUT}" || fail "缺少审计路由时没有可操作错误"

cat > "${FIXTURE_ROOT}/.vite/manifest.json" <<'JSON'
{
  "src/features/chat/ChatPage.tsx": {"file":"assets/ChatPage.js","isDynamicEntry":true},
  "src/features/employees/EmployeesPage.tsx": {"file":"assets/EmployeesPage.js","isDynamicEntry":true},
  "src/features/knowledge-bases/KnowledgeBasesPage.tsx": {"file":"assets/KnowledgeBasesPage.js","isDynamicEntry":true},
  "src/features/model-configurations/ModelConfigurationsPage.tsx": {"file":"assets/ModelConfigurationsPage.js","isDynamicEntry":true},
  "src/features/tools/ToolsPage.tsx": {"file":"assets/ToolsPage.js","isDynamicEntry":true},
  "src/features/workflows/WorkflowsPage.tsx": {"file":"assets/WorkflowsPage.js","isDynamicEntry":true},
  "src/features/audit/AuditEventsPage.tsx": {"file":"assets/AuditEventsPage.js","isDynamicEntry":true}
}
JSON

truncate -s 500001 "${FIXTURE_ROOT}/assets/too-large.js"
if node "${CHECKER}" "${FIXTURE_ROOT}" > "${OUTPUT}" 2>&1; then
  fail "超过 500 kB 的异步 chunk 仍被预算放行"
fi
grep -Fq 'too-large.js' "${OUTPUT}" || fail "bundle 超限错误没有指出具体 chunk"
grep -Fq '500000 bytes' "${OUTPUT}" || fail "bundle 超限错误没有报告固定预算"
rm -f "${FIXTURE_ROOT}/assets/too-large.js"

for index in 1 2 3 4; do
  truncate -s 400000 "${FIXTURE_ROOT}/assets/shared-${index}.js"
done
cat > "${FIXTURE_ROOT}/.vite/manifest.json" <<'JSON'
{
  "src/features/chat/ChatPage.tsx": {"file":"assets/ChatPage.js","isDynamicEntry":true,"imports":["_shared-1","_shared-2","_shared-3","_shared-4"]},
  "src/features/employees/EmployeesPage.tsx": {"file":"assets/EmployeesPage.js","isDynamicEntry":true},
  "src/features/knowledge-bases/KnowledgeBasesPage.tsx": {"file":"assets/KnowledgeBasesPage.js","isDynamicEntry":true},
  "src/features/model-configurations/ModelConfigurationsPage.tsx": {"file":"assets/ModelConfigurationsPage.js","isDynamicEntry":true},
  "src/features/tools/ToolsPage.tsx": {"file":"assets/ToolsPage.js","isDynamicEntry":true},
  "src/features/workflows/WorkflowsPage.tsx": {"file":"assets/WorkflowsPage.js","isDynamicEntry":true},
  "_shared-1": {"file":"assets/shared-1.js"},
  "_shared-2": {"file":"assets/shared-2.js"},
  "_shared-3": {"file":"assets/shared-3.js"},
  "_shared-4": {"file":"assets/shared-4.js"}
}
JSON
if node "${CHECKER}" "${FIXTURE_ROOT}" > "${OUTPUT}" 2>&1; then
  fail "超过 1.5 MB 的单路由首次 JS 图仍被预算放行"
fi
grep -Fq '路由 /chat' "${OUTPUT}" || fail "路由图超限错误没有指出具体入口"
grep -Fq '1500000 bytes' "${OUTPUT}" || fail "路由图超限错误没有报告固定预算"

rm -f "${FIXTURE_ROOT}/.vite/manifest.json"
if node "${CHECKER}" "${FIXTURE_ROOT}" > "${OUTPUT}" 2>&1; then
  fail "缺少 manifest 时 bundle 分析仍被放行"
fi
grep -Fq 'manifest' "${OUTPUT}" || fail "缺少 manifest 时没有可操作错误"

echo "前端 bundle 分析、七路由与 500 kB 预算契约通过"
