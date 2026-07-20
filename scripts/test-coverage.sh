#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
RUNNER="${SCRIPT_DIR}/coverage.sh"
BACKEND_CONFIG="${REPOSITORY_ROOT}/backend/pyproject.toml"
FRONTEND_PACKAGE="${REPOSITORY_ROOT}/frontend/package.json"
FRONTEND_CONFIG="${REPOSITORY_ROOT}/frontend/vite.config.ts"
WORKFLOW="${REPOSITORY_ROOT}/.github/workflows/ci.yml"

fail() {
  echo "$1" >&2
  exit 1
}

[[ -x "${RUNNER}" ]] || fail "缺少可执行的本机权威覆盖率入口"

grep -Fq '"pytest-cov' "${BACKEND_CONFIG}" || fail "后端缺少冻结的 pytest-cov 依赖"
grep -Fq '[tool.coverage.run]' "${BACKEND_CONFIG}" || fail "后端缺少 coverage.py 运行配置"
grep -Fq 'branch = true' "${BACKEND_CONFIG}" || fail "后端没有生成分支覆盖率"
grep -Fq 'patch = ["subprocess"]' "${BACKEND_CONFIG}" || fail "后端没有采集正式子进程"
grep -Fq 'source = ["common_agent"]' "${BACKEND_CONFIG}" || fail "后端覆盖率没有限定生产包"
grep -Fq 'sigterm = true' "${BACKEND_CONFIG}" || fail "后端子进程停止时不会保存覆盖率"

grep -Fq '"@vitest/coverage-v8"' "${FRONTEND_PACKAGE}" || \
  fail "前端缺少冻结的 V8 覆盖率依赖"
grep -Fq '"test:coverage": "vitest run --coverage"' "${FRONTEND_PACKAGE}" || \
  fail "前端缺少覆盖率命令"
for expected in \
  'provider: "v8"' \
  'lines: 86.17' \
  'branches: 75' \
  'reportsDirectory: "coverage"'; do
  grep -Fq "${expected}" "${FRONTEND_CONFIG}" || fail "前端缺少覆盖率配置：${expected}"
done

for expected in \
  'OVERALL_LINE_MINIMUM=90.90' \
  'OVERALL_BRANCH_MINIMUM=72.20' \
  'CORE_LINE_MINIMUM=93.17' \
  'CORE_BRANCH_MINIMUM=74.26' \
  'coverage json' \
  'pnpm@11.9.0 test:coverage'; do
  grep -Fq "${expected}" "${RUNNER}" || fail "本机覆盖率入口缺少门禁：${expected}"
done

grep -Fq 'frontend/coverage/' "${REPOSITORY_ROOT}/.gitignore" || \
  fail "前端覆盖率报告没有被 Git 忽略"
grep -Fq '.local/' "${REPOSITORY_ROOT}/.gitignore" || \
  fail "后端覆盖率报告目录没有被 Git 忽略"
grep -Fq '.coverage.*' "${REPOSITORY_ROOT}/.gitignore" || \
  fail "中断的后端子进程覆盖率报告没有被 Git 忽略"
grep -Fq './scripts/coverage.sh backend' "${WORKFLOW}" || \
  fail "可选 CI 镜像没有复用本机后端覆盖率入口"
grep -Fq 'pnpm test:coverage' "${WORKFLOW}" || \
  fail "可选 CI 镜像没有执行前端覆盖率门禁"

echo "本机行/分支覆盖率与可选 CI 镜像契约通过"
