#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANAGER="${SCRIPT_DIR}/manage.sh"

fail() {
  echo "$1" >&2
  exit 1
}

[[ -x "${MANAGER}" ]] || fail "缺少可执行的 RAGFlow 管理脚本"
[[ "$(tr -d '[:space:]' < "${SCRIPT_DIR}/VERSION")" == "v0.25.6" ]] || fail "RAGFlow 版本未固定为 v0.25.6"
[[ "$(tr -d '[:space:]' < "${SCRIPT_DIR}/UPSTREAM_COMMIT")" == "8f0632c8d9efacbcd11aaf6e0f4cb634169bfea4" ]] || fail "RAGFlow 上游提交未固定"

CONFIG="$(${MANAGER} config)"

rg --color=never --quiet '^name: common-agent-dev$' <<< "${CONFIG}"
rg --color=never --quiet 'container_name: common-agent-ragflow-api' <<< "${CONFIG}"
rg --color=never --quiet 'image: infiniflow/ragflow:v0\.25\.6' <<< "${CONFIG}"
rg --color=never --quiet 'platform: linux/amd64' <<< "${CONFIG}"
rg --color=never --quiet 'TEI_MODEL: BAAI/bge-m3' <<< "${CONFIG}"
rg --color=never --quiet 'mem_limit: "25769803776"' <<< "${CONFIG}"
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

if RAGFLOW_API_PORT=29380 "${MANAGER}" check-ports > "${PORT_TEST_OUTPUT}" 2>&1; then
  fail "端口冲突时管理脚本仍然放行"
fi
rg --color=never --quiet '29380' "${PORT_TEST_OUTPUT}"

echo "RAGFlow 固定版本、隔离、资源与端口冲突门禁通过"
