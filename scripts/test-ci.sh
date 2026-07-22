#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
WORKFLOW="${REPOSITORY_ROOT}/.github/workflows/ci.yml"
UV_RUNNER="${SCRIPT_DIR}/uv.sh"
ARCHITECTURE_TEST="${REPOSITORY_ROOT}/backend/tests/architecture/test_dependency_boundaries.py"

fail() {
  echo "$1" >&2
  exit 1
}

[[ -f "${WORKFLOW}" ]] || fail "缺少 PR/main GitHub CI workflow"
[[ -f "${ARCHITECTURE_TEST}" ]] || fail "缺少第三方依赖边界架构测试"
grep -Fq 'test_third_party_imports_stay_at_declared_boundaries' "${ARCHITECTURE_TEST}" || \
  fail "第三方依赖边界架构测试入口漂移"
[[ -x "${UV_RUNNER}" ]] || fail "缺少可执行的项目固定 uv 入口"
grep -Fq 'UV_PROJECT_VERSION="0.11.16"' "${UV_RUNNER}" || \
  fail "项目 uv 入口未固定 0.11.16"
[[ "$("${UV_RUNNER}" --version)" == "uv 0.11.16"* ]] || fail "项目 uv 固定入口不可用"

for expected in \
  'pull_request:' \
  'push:' \
  'branches: [main]' \
  'contents: read' \
  'backend:' \
  'frontend:' \
  'demo-and-contracts:' \
  'uv sync --frozen' \
  './scripts/coverage.sh backend' \
  'uv run --frozen ruff check .' \
  'uv run --frozen mypy src tests' \
  'uv lock --check' \
  'uv audit --frozen --preview-features audit' \
  'pnpm install --frozen-lockfile' \
  'pnpm test:coverage' \
  'pnpm lint' \
  'pnpm typecheck' \
  'pnpm build' \
  'pnpm audit --audit-level=high' \
  'pnpm contracts:check' \
  'pnpm test:e2e:demo' \
  'COMMON_AGENT_E2E_DOCKER_CONTEXT: default' \
  'bash infra/ragflow/test-manage.sh' \
  'bash infra/ragflow/test-fork.sh' \
  'bash infra/ragflow/test-patchset.sh' \
  'bash infra/platform/test-manage.sh' \
  'bash infra/backup/test-manage.sh' \
  'bash infra/production/test-manage.sh' \
  './scripts/test-dev.sh' \
  './scripts/test-real.sh' \
  './scripts/test-ci.sh' \
  './scripts/test-coverage.sh' \
  './scripts/test-frontend-bundle.sh' \
  './scripts/test-security-scan.sh' \
  './scripts/test-secrets.sh' \
  'pnpm test:e2e:loading' \
  "rg --files -g '*.sh' -g '!third_party/**' | xargs shellcheck"; do
  grep -Fq "${expected}" "${WORKFLOW}" || fail "CI 缺少门禁：${expected}"
done

grep -Fq 'submodules: recursive' "${WORKFLOW}" || fail "CI 没有检出固定 RAGFlow submodule"
grep -Fq 'fetch-depth: 0' "${WORKFLOW}" || fail "Secret 门禁没有检出完整 Git 历史"
grep -Fq 'version: 0.11.16' "${WORKFLOW}" || fail "CI 没有固定 uv 版本"
grep -Fq 'version: 11.9.0' "${WORKFLOW}" || fail "CI 没有固定 pnpm 版本"
grep -Fq 'cache-dependency-glob: backend/uv.lock' "${WORKFLOW}" || \
  fail "uv 缓存没有绑定 uv.lock"
grep -Fq 'cache-dependency-path: frontend/pnpm-lock.yaml' "${WORKFLOW}" || \
  fail "pnpm 缓存没有绑定 pnpm-lock.yaml"
grep -Fq 'migrations/versions/20260720_0005_workflow_runs.py' "${WORKFLOW}" || \
  fail "CI 格式门禁没有保留已应用迁移不可变边界"

for immutable_action in \
  'actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd' \
  'astral-sh/setup-uv@08807647e7069bb48b6ef5acd8ec9567f424441b' \
  'pnpm/action-setup@0e279bb959325dab635dd2c09392533439d90093' \
  'actions/setup-node@6044e13b5dc448c55e2357c09f80417699197238'; do
  grep -Fq "${immutable_action}" "${WORKFLOW}" || fail "CI Action 未固定：${immutable_action}"
done

if grep -Eq 'continue-on-error:[[:space:]]*true|\|[[:space:]]*true' "${WORKFLOW}"; then
  fail "CI 存在吞掉失败的配置"
fi
if grep -Eq 'test:e2e:mvp|scripts/real\.sh[[:space:]]+up|TEST_BAILIAN_REAL=1' "${WORKFLOW}"; then
  fail "PR/main CI 不得自动运行会产生外部费用的 real 门禁"
fi

echo "GitHub CI 基线契约通过"
