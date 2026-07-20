#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
MANAGER="${SCRIPT_DIR}/manage.sh"
VERSION="$(tr -d '[:space:]' < "${SCRIPT_DIR}/VERSION")"

fail() {
  echo "$1" >&2
  exit 1
}

[[ -x "${MANAGER}" ]] || fail "缺少可执行的 RAGFlow 管理脚本"
[[ "${VERSION}" == "v0.25.6" ]] || fail "RAGFlow 版本未固定为 v0.25.6"
[[ "$(tr -d '[:space:]' < "${SCRIPT_DIR}/UPSTREAM_COMMIT")" == "8f0632c8d9efacbcd11aaf6e0f4cb634169bfea4" ]] || fail "RAGFlow 上游提交未固定"
ENV_VERSION_LINE="$(rg --color=never --only-matching '^RAGFLOW_EXPECTED_VERSION=.*' "${REPOSITORY_ROOT}/.env.example" || true)"
[[ "${ENV_VERSION_LINE#*=}" == "${VERSION}" ]] || fail "后端期望的 RAGFlow 版本与基础设施版本不一致"

rg --color=never --quiet 'RAGFLOW_DOCKER_CONTEXT:-colima-common-agent-dev' "${MANAGER}"
rg --color=never --quiet '^check_resources\(\)' "${MANAGER}" || \
  fail "RAGFlow 管理脚本缺少 Docker 内存预检"
rg --color=never --quiet 'RAGFLOW_MIN_DOCKER_MEMORY_GIB:-40' "${MANAGER}" || \
  fail "RAGFlow 管理脚本没有拒绝低于 40 GiB 的 Docker profile"
rg --color=never --quiet '建议为 common-agent-dev 分配 48 GiB' "${MANAGER}" || \
  fail "RAGFlow 内存不足错误没有给出项目独立 48 GiB profile 建议"
rg --color=never --quiet 'RAGFLOW_HEALTH_TIMEOUT_SECONDS:-180' "${MANAGER}" || \
  fail "RAGFlow 正式 up 入口缺少可故障注入的有限健康超时"
rg --color=never --fixed-strings --quiet -- '--wait-timeout "${health_timeout_seconds}"' "${MANAGER}" || \
  fail "RAGFlow 正式 up 入口没有把健康超时交给 Docker Compose"
CONFIG="$(RAGFLOW_DOCKER_CONTEXT=colima ${MANAGER} config)"

rg --color=never --quiet '^name: common-agent-dev$' <<< "${CONFIG}"
rg --color=never --quiet 'container_name: common-agent-ragflow-api' <<< "${CONFIG}"
rg --color=never --quiet 'image: infiniflow/ragflow:v0\.25\.6' <<< "${CONFIG}"
rg --color=never --quiet 'image: ghcr\.io/huggingface/text-embeddings-inference:cpu-1\.8' <<< "${CONFIG}"
rg --color=never --quiet 'platform: linux/amd64' <<< "${CONFIG}"
rg --color=never --quiet 'TEI_MODEL: BAAI/bge-m3' <<< "${CONFIG}"
rg --color=never --quiet 'mem_limit: "25769803776"' <<< "${CONFIG}"
rg --color=never --quiet 'target: /data' <<< "${CONFIG}"
rg --color=never --quiet 'read_only: true' <<< "${CONFIG}"
rg --color=never --quiet 'name: common-agent-ragflow-esdata' <<< "${CONFIG}"
rg --color=never --quiet 'host_ip: 127\.0\.0\.1' <<< "${CONFIG}"
rg --color=never --quiet 'published: "19380"' <<< "${CONFIG}"
rg --color=never --quiet 'published: "19387"' <<< "${CONFIG}"
if rg --color=never --quiet 'image: .*:latest' <<< "${CONFIG}"; then
  fail "活动栈不得使用 latest 镜像"
fi
if rg --color=never --quiet 'host_ip: 0\.0\.0\.0' <<< "${CONFIG}"; then
  fail "RAGFlow 端口不得公开绑定"
fi

INVALID_PORT_OUTPUT="$(mktemp)"
if RAGFLOW_API_PORT=abc "${MANAGER}" check-ports > "${INVALID_PORT_OUTPUT}" 2>&1; then
  rm -f "${INVALID_PORT_OUTPUT}"
  fail "非法端口值仍然被放行"
fi
rg --color=never --quiet '1-65535' "${INVALID_PORT_OUTPUT}"
rm -f "${INVALID_PORT_OUTPUT}"

MODEL_TEST_ROOT="$(mktemp -d)"
if RAGFLOW_MODEL_ROOT="${MODEL_TEST_ROOT}" "${MANAGER}" check-model > /dev/null 2>&1; then
  rm -rf "${MODEL_TEST_ROOT}"
  fail "缺失 embedding 模型时管理脚本仍然放行"
fi
mkdir -p "${MODEL_TEST_ROOT}/BAAI/bge-m3"
touch "${MODEL_TEST_ROOT}/BAAI/bge-m3/config.json"
touch "${MODEL_TEST_ROOT}/BAAI/bge-m3/model.safetensors"
RAGFLOW_MODEL_ROOT="${MODEL_TEST_ROOT}" "${MANAGER}" check-model
rm -rf "${MODEL_TEST_ROOT}"

FAKE_DOCKER_PATH="${REPOSITORY_ROOT}/infra/test-fixtures:${PATH}"
LOW_MEMORY_OUTPUT="$(mktemp)"
if PATH="${FAKE_DOCKER_PATH}" \
  COMMON_AGENT_TEST_DOCKER_MEMORY_BYTES="$((32 * 1024 * 1024 * 1024))" \
  "${MANAGER}" check-resources > "${LOW_MEMORY_OUTPUT}" 2>&1; then
  rm -f "${LOW_MEMORY_OUTPUT}"
  fail "32 GiB Docker profile 仍然被 RAGFlow 资源预检放行"
fi
rg --color=never --quiet '内存不足' "${LOW_MEMORY_OUTPUT}"
rg --color=never --quiet '48 GiB' "${LOW_MEMORY_OUTPUT}"
rm -f "${LOW_MEMORY_OUTPUT}"

PATH="${FAKE_DOCKER_PATH}" \
COMMON_AGENT_TEST_DOCKER_MEMORY_BYTES="$((48 * 1024 * 1024 * 1024))" \
  "${MANAGER}" check-resources

INVALID_MEMORY_OUTPUT="$(mktemp)"
if PATH="${FAKE_DOCKER_PATH}" \
  RAGFLOW_MIN_DOCKER_MEMORY_GIB=invalid \
  COMMON_AGENT_TEST_DOCKER_MEMORY_BYTES="$((48 * 1024 * 1024 * 1024))" \
  "${MANAGER}" check-resources > "${INVALID_MEMORY_OUTPUT}" 2>&1; then
  rm -f "${INVALID_MEMORY_OUTPUT}"
  fail "非法最低内存值仍然被 RAGFlow 资源预检放行"
fi
rg --color=never --quiet '1-128' "${INVALID_MEMORY_OUTPUT}"
rm -f "${INVALID_MEMORY_OUTPUT}"

HEALTH_MODEL_ROOT="$(mktemp -d)"
HEALTH_TEST_OUTPUT="$(mktemp)"
mkdir -p "${HEALTH_MODEL_ROOT}/BAAI/bge-m3"
touch "${HEALTH_MODEL_ROOT}/BAAI/bge-m3/config.json"
touch "${HEALTH_MODEL_ROOT}/BAAI/bge-m3/model.safetensors"
if PATH="${FAKE_DOCKER_PATH}" \
  COMMON_AGENT_TEST_DOCKER_SCENARIO=ragflow-unhealthy \
  COMMON_AGENT_TEST_DOCKER_MEMORY_BYTES="$((48 * 1024 * 1024 * 1024))" \
  RAGFLOW_MODEL_ROOT="${HEALTH_MODEL_ROOT}" \
  RAGFLOW_HEALTH_TIMEOUT_SECONDS=1 \
  "${MANAGER}" up > "${HEALTH_TEST_OUTPUT}" 2>&1; then
  rm -rf "${HEALTH_MODEL_ROOT}"
  rm -f "${HEALTH_TEST_OUTPUT}"
  fail "RAGFlow 健康失败时正式 up 入口仍然成功返回"
fi
rg --color=never --quiet '模拟 RAGFlow 健康检查失败' "${HEALTH_TEST_OUTPUT}"
rm -rf "${HEALTH_MODEL_ROOT}"
rm -f "${HEALTH_TEST_OUTPUT}"

PORT_TEST_OUTPUT="$(mktemp)"
python3 -m http.server 29380 --bind 127.0.0.1 > /dev/null 2>&1 &
PORT_TEST_PID=$!
cleanup() {
  kill "${PORT_TEST_PID}" 2>/dev/null || true
  wait "${PORT_TEST_PID}" 2>/dev/null || true
  rm -f "${PORT_TEST_OUTPUT}"
}
trap cleanup EXIT
sleep 0.3

if RAGFLOW_ES_PORT=29200 \
  RAGFLOW_REDIS_PORT=29379 \
  RAGFLOW_API_PORT=29380 \
  "${MANAGER}" check-ports > "${PORT_TEST_OUTPUT}" 2>&1; then
  fail "端口冲突时管理脚本仍然放行"
fi
rg --color=never --quiet '29380' "${PORT_TEST_OUTPUT}"

echo "RAGFlow 固定版本、隔离、资源与端口冲突门禁通过"
