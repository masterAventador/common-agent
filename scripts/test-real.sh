#!/usr/bin/env bash
# shellcheck disable=SC2016 # Contract assertions intentionally match literal shell expressions.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
MANAGER="${SCRIPT_DIR}/real.sh"

fail() {
  echo "$1" >&2
  exit 1
}

[[ -x "${MANAGER}" ]] || fail "缺少统一的 real 开发入口"

for action in doctor setup up status cost stop; do
  grep -Fq "${action})" "${MANAGER}" || fail "统一 real 入口缺少 ${action} 动作"
done

grep -Fq 'COMMON_AGENT_INTEGRATION_MODE=real' "${MANAGER}" || \
  fail "real 后端没有显式使用 real 适配器"
grep -Fq 'REAL_MEMORY_GIB=32' "${MANAGER}" || \
  fail "real 入口没有固定暂定 32 GiB Colima 预算"
grep -Fq 'COMMON_AGENT_REAL_DATABASE_NAME:-common_agent' "${MANAGER}" || \
  fail "real 入口缺少资源验收使用隔离测试库的受控覆盖点"
grep -Fq 'COMMON_AGENT_REAL_DATABASE_NAME=${DATABASE_NAME}' "${MANAGER}" || \
  fail "real 子进程没有继承受控数据库名称"
grep -Fq 'AUTH_BOOTSTRAP_TOKEN_FILE="${TOKEN_ROOT}/owner-bootstrap-token"' "${MANAGER}" || \
  fail "real 入口没有复用 Git 忽略的项目专属引导凭据文件"
grep -Fq 'openssl rand -hex 32' "${MANAGER}" || \
  fail "real 入口没有安全生成首位管理员引导凭据"
grep -Fq "stat -f '%Lp'" "${MANAGER}" || \
  fail "real 入口没有检查首位管理员引导凭据文件权限"
if grep -Eq '^COMMON_AGENT_AUTH_BOOTSTRAP_TOKEN=' \
  "${REPOSITORY_ROOT}/backend/.env.demo"; then
  fail "首位管理员引导凭据不得在私有仓库中版本化"
fi
grep -Fq 'DOCKER_CONTEXT_NAME="colima-common-agent-dev"' "${MANAGER}" || \
  fail "real 入口没有使用项目专属 Docker context"
grep -Fq 'WORKER_LAUNCH_LABEL="com.masteraventador.common-agent.real.worker"' "${MANAGER}" || \
  fail "real Worker 没有项目专属进程标签"
grep -Fq '.venv/bin/python -m common_agent.worker_main' "${MANAGER}" || \
  fail "real 入口没有启动独立持久 Worker"
grep -Fq '"${RAGFLOW_MANAGER}" up' "${MANAGER}" || \
  fail "real 入口没有启动官方 RAGFlow 栈"
grep -Fq '"${RAGFLOW_MANAGER}" migrate-native-volumes' "${MANAGER}" || \
  fail "real 入口没有迁移或复用可跨 Colima 重启的原生数据卷"
grep -Fq '"${RAGFLOW_MANAGER}" configure-bailian' "${MANAGER}" || \
  fail "real 入口没有配置百炼 embedding/rerank"
grep -Fq '"${RAGFLOW_MANAGER}" check-bailian' "${MANAGER}" || \
  fail "real 入口没有验证百炼 embedding/rerank"
grep -Fq 'ragflow_models ensure-token' "${MANAGER}" || \
  fail "real 入口没有安全创建或复用 RAGFlow Token"
grep -Fq 'ragflow_models check-token' "${MANAGER}" || \
  fail "real 入口没有验证 RAGFlow Token"
grep -Fq 'RAGFLOW_TOKEN_FILE=' "${MANAGER}" || \
  fail "real 入口没有通过受控文件传递 RAGFlow Token"
grep -Fq 'ragflow_models diagnose' "${MANAGER}" || \
  fail "real 费用诊断没有调用脱敏百炼配置诊断"
grep -Fq '不启动本地 embedding/rerank' "${MANAGER}" || \
  fail "real 入口没有声明本地模型退场边界"
if grep -Eq 'BAILIAN_API_KEY[[:space:]]*=[[:space:]]*sk-' "${MANAGER}"; then
  fail "real 入口疑似硬编码百炼凭据"
fi

INVALID_OUTPUT="$(mktemp)"
if "${MANAGER}" invalid >"${INVALID_OUTPUT}" 2>&1; then
  rm -f "${INVALID_OUTPUT}"
  fail "未知 real 动作仍被放行"
fi
grep -Fq '用法: scripts/real.sh {doctor|setup|up|status|cost|stop}' \
  "${INVALID_OUTPUT}" || fail "未知动作没有返回稳定用法"
rm -f "${INVALID_OUTPUT}"

if grep -Eq '(^|[[:space:]])rm[[:space:]]+-rf[[:space:]]+(~|/|\$HOME|"\$\{HOME\}")' \
  "${MANAGER}"; then
  fail "统一 real 入口包含宽泛破坏性清理"
fi

echo "real 统一开发入口契约通过"
