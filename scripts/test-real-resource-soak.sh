#!/usr/bin/env bash
# shellcheck disable=SC2016 # Contract assertions intentionally match literal shell expressions.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MONITOR="${SCRIPT_DIR}/real-resource-monitor.py"
RUNNER="${SCRIPT_DIR}/real-resource-soak.sh"
OUTPUT="$(mktemp)"
REPORT="$(mktemp)"

cleanup() {
  rm -f "${OUTPUT}"
  rm -f "${REPORT}"
}
trap cleanup EXIT

fail() {
  echo "$1" >&2
  exit 1
}

[[ -f "${MONITOR}" ]] || fail "缺少 32 GiB real 资源监视器"
[[ -x "${RUNNER}" ]] || fail "缺少可执行的 32 GiB real soak 入口"

python3 "${MONITOR}" --self-test
if python3 "${MONITOR}" soak --duration-seconds 1799 --output "${REPORT}" \
  >"${OUTPUT}" 2>&1; then
  fail "少于 30 分钟的 real soak 仍被正式入口放行"
fi
grep -Fq '至少 1800 秒' "${OUTPUT}" || fail "短 soak 没有返回明确的 30 分钟边界"

for expected in \
  'MAX_VM_USED_BYTES = 25 * GIB' \
  'MAX_SWAP_USED_BYTES = 512 * MIB' \
  'RestartCount' \
  'OOMKilled' \
  '/api/v1/system/status'; do
  grep -Fq "${expected}" "${MONITOR}" || fail "资源监视器缺少门禁：${expected}"
done

for expected in \
  'test_real_ragflow_adapter_lifecycle' \
  'mvp-acceptance.spec.ts' \
  'COMMON_AGENT_RESOURCE_SOAK_SECONDS:-1800' \
  'COMMON_AGENT_REAL_DATABASE_NAME=common_agent_test' \
  'COMMON_AGENT_E2E_API_URL="http://127.0.0.1:18200/api/v1"' \
  'COMMON_AGENT_E2E_AUTH_BOOTSTRAP_TOKEN=' \
  'tests.support.auth_e2e_state reset' \
  '"${REAL_MANAGER}" stop' \
  'mvp_acceptance_e2e_cleanup'; do
  grep -Fq "${expected}" "${RUNNER}" || fail "real soak 入口缺少链路：${expected}"
done

echo "32 GiB real 冷启动、资源、质量、30 分钟 soak 与清理契约通过"
