#!/usr/bin/env bash
# shellcheck disable=SC2016 # 契约断言刻意匹配字面量 shell 表达式。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESOURCES="${SCRIPT_DIR}/resources.compose.yaml"
RAGFLOW_RESOURCES="${SCRIPT_DIR}/ragflow-resources.compose.yaml"
CONFIG_EXAMPLE="${SCRIPT_DIR}/config.env.example"

fail() {
  echo "$1" >&2
  exit 1
}

[[ -f "${RESOURCES}" ]] || fail "缺少单机业务资源覆盖"
[[ -f "${RAGFLOW_RESOURCES}" ]] || fail "缺少单机 RAGFlow 资源覆盖"
[[ -f "${CONFIG_EXAMPLE}" ]] || fail "缺少单机配置模板"

for expected in 'mem_limit: 2g' 'mem_limit: 1536m' 'mem_limit: 1g' 'mem_limit: 64m'; do
  grep -Fq "${expected}" "${RESOURCES}" || fail "业务资源覆盖缺少：${expected}"
done

# RAGFlow API 实测峰值 4.53 GiB，不得压到 5g 以下。
grep -Fq 'mem_limit: 5g' "${RAGFLOW_RESOURCES}" || fail "RAGFlow API 内存上限被压到实测峰值以下"
grep -Fq 'cpus: 2.0' "${RAGFLOW_RESOURCES}" || fail "RAGFlow API 没有 CPU 配额，解析会吃满整机"
for expected in 'MAX_CONCURRENT_TASKS: "2"' 'MAX_CONCURRENT_EMBEDDINGS: "4"' 'DOC_BULK_SIZE: "16"'; do
  grep -Fq "${expected}" "${RAGFLOW_RESOURCES}" || fail "RAGFlow 解析并发没有下调：${expected}"
done

grep -Fxq 'COMMON_AGENT_INTEGRATION_MODE=real' "${CONFIG_EXAMPLE}" || \
  fail "单机配置必须使用 real 集成模式"
grep -Fxq 'RAGFLOW_BASE_URL=https://common-agent-production-ragflow-edge:9443' "${CONFIG_EXAMPLE}" || \
  fail "单机配置没有指向本机 RAGFlow Edge 容器名"
grep -Eq '^COMMON_AGENT_CORS_ORIGINS=https://kb\.xuanbai\.tech$' "${CONFIG_EXAMPLE}" || \
  fail "单机配置没有使用正式公网域名"
grep -Fxq 'COMMON_AGENT_AUTH_COOKIE_SECURE=true' "${CONFIG_EXAMPLE}" || \
  fail "单机配置必须启用 Secure Cookie"

PRODUCTION_MANAGER="${SCRIPT_DIR}/../manage.sh"
RAGFLOW_MANAGER="${SCRIPT_DIR}/../../ragflow/manage.sh"

# 资源覆盖片段必须能真的叠加进去，否则这些文件只是摆设。
grep -Fq 'COMMON_AGENT_COMPOSE_OVERRIDE' "${PRODUCTION_MANAGER}" || \
  fail "业务发布入口不支持叠加资源覆盖，资源片段无法生效"
grep -Fq 'RAGFLOW_COMPOSE_OVERRIDE' "${RAGFLOW_MANAGER}" || \
  fail "RAGFlow 入口不支持叠加资源覆盖，资源片段无法生效"

# MACOS 开关会让 RAGFlow 跳过 update_progress 的分布式锁（见 upstream
# api/db/services/task_service.py），只适用于 macOS 开发机，不得硬编码到 Linux 部署。
RAGFLOW_OVERRIDE="${SCRIPT_DIR}/../../ragflow/compose.override.yaml"
if grep -Eq '^\s+MACOS=1 \\$' "${RAGFLOW_MANAGER}"; then
  fail "RAGFlow 入口硬编码 MACOS=1，Linux 部署会错误跳过任务进度锁"
fi
grep -Fq 'MACOS: "${RAGFLOW_MACOS:-}"' "${RAGFLOW_OVERRIDE}" || \
  fail "RAGFlow 容器仍硬编码 MACOS，Linux 部署会跳过任务进度锁"
grep -Fq 'uname -s' "${RAGFLOW_MANAGER}" || \
  fail "RAGFlow 入口没有按宿主机系统判定 MACOS"

echo "单机部署配置契约通过"
