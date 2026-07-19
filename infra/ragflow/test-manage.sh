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
