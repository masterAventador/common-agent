#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANAGER="${SCRIPT_DIR}/dev.sh"

fail() {
  echo "$1" >&2
  exit 1
}

[[ -x "${MANAGER}" ]] || fail "缺少统一的 demo-light 开发入口"

for action in doctor setup up status stop clean; do
  rg --color=never --fixed-strings --quiet "${action})" "${MANAGER}" || \
    fail "统一开发入口缺少 ${action} 动作"
done

rg --color=never --fixed-strings --quiet 'COMMON_AGENT_INTEGRATION_MODE=demo' "${MANAGER}" || \
  fail "demo-light 后端没有显式使用 demo 适配器"
rg --color=never --fixed-strings --quiet 'DEMO_MEMORY_GIB=12' "${MANAGER}" || \
  fail "demo-light 没有固定 12 GiB Colima 预算"
rg --color=never --fixed-strings --quiet 'PNPM_VERSION="11.9.0"' "${MANAGER}" || \
  fail "统一入口没有使用 packageManager 锁定的 pnpm 版本"
rg --color=never --fixed-strings --quiet 'npx --yes "pnpm@${PNPM_VERSION}"' "${MANAGER}" || \
  fail "统一入口仍依赖全局 pnpm"
rg --color=never --fixed-strings --quiet 'infra/ragflow/manage.sh" stop' "${MANAGER}" || \
  fail "demo-light 切换前没有停止本项目 RAGFlow"
if rg --color=never --fixed-strings --quiet 'infra/ragflow/manage.sh" up' "${MANAGER}"; then
  fail "demo-light 不得启动 RAGFlow"
fi
rg --color=never --fixed-strings --quiet \
  'BACKEND_LAUNCH_LABEL="com.masteraventador.common-agent.demo-light.backend"' \
  "${MANAGER}" || fail "demo-light 后端没有项目专属进程标签"
rg --color=never --fixed-strings --quiet \
  'FRONTEND_LAUNCH_LABEL="com.masteraventador.common-agent.demo-light.frontend"' \
  "${MANAGER}" || fail "demo-light 前端没有项目专属进程标签"
rg --color=never --fixed-strings --quiet \
  'LEGACY_RAGFLOW_CHECKOUT="${REPOSITORY_ROOT}/.local/dev/common-agent-dev/ragflow/upstream/v0.25.6"' \
  "${MANAGER}" || fail "统一清理没有精确收回被 submodule 取代的旧 checkout"
rg --color=never --fixed-strings --quiet 'infra/platform/manage.sh" down' "${MANAGER}" || \
  fail "demo-light 停止后没有精确删除平台容器与网络"

INVALID_OUTPUT="$(mktemp)"
if "${MANAGER}" invalid >"${INVALID_OUTPUT}" 2>&1; then
  rm -f "${INVALID_OUTPUT}"
  fail "未知开发动作仍被放行"
fi
rg --color=never --fixed-strings --quiet \
  '用法: scripts/dev.sh {doctor|setup|up|status|stop|clean}' \
  "${INVALID_OUTPUT}" || fail "未知动作没有返回稳定用法"
rm -f "${INVALID_OUTPUT}"

if rg --color=never --quiet '(^|[[:space:]])rm[[:space:]]+-rf[[:space:]]+(~|/|\$HOME|"\$\{HOME\}")' "${MANAGER}"; then
  fail "统一开发入口包含宽泛破坏性清理"
fi

echo "demo-light 统一开发入口契约通过"
