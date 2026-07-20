#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANAGER="${SCRIPT_DIR}/manage.sh"

fail() {
  echo "$1" >&2
  exit 1
}

[[ -x "${MANAGER}" ]] || fail "缺少可执行的平台基础设施管理脚本"
[[ "$(tr -d '[:space:]' < "${SCRIPT_DIR}/MYSQL_VERSION")" == "8.4.10" ]] || fail "平台 MySQL 未锁定到 8.4.10 LTS"
rg --color=never --quiet 'PLATFORM_DOCKER_CONTEXT:-colima-common-agent-dev' "${MANAGER}"
rg --color=never --quiet '^wait_for_healthy\(\)' "${MANAGER}" || \
  fail "平台 MySQL 管理脚本缺少重启瞬态后的显式健康等待"
rg --color=never --quiet 'healthy_since' "${MANAGER}" || \
  fail "平台 MySQL 管理脚本没有要求健康状态稳定后再返回"
rg --color=never --quiet 'PLATFORM_HEALTH_TIMEOUT_SECONDS:-60' "${MANAGER}" || \
  fail "平台 MySQL 健康等待没有可故障注入的有限超时"
rg --color=never --fixed-strings --quiet 'check-health) wait_for_healthy' "${MANAGER}" || \
  fail "平台 MySQL 管理脚本缺少复用正式健康等待的诊断入口"
rg --color=never --quiet '^ensure_test_database\(\)' "${MANAGER}" || \
  fail "平台 MySQL 管理脚本缺少隔离测试数据库的幂等准备"
rg --color=never --quiet 'common_agent_test' "${MANAGER}" || \
  fail "平台 MySQL 管理脚本未固定隔离测试数据库名称"
if rg --color=never --quiet 'compose up -d --wait' "${MANAGER}"; then
  fail "平台 MySQL 不得依赖会被瞬态 unhealthy 提前打断的 Compose --wait"
fi

CONFIG="$(PLATFORM_DOCKER_CONTEXT=colima "${MANAGER}" config)"
rg --color=never --quiet '^name: common-agent-platform-dev$' <<< "${CONFIG}"
rg --color=never --quiet 'container_name: common-agent-platform-mysql' <<< "${CONFIG}"
rg --color=never --quiet 'image: mysql:8\.4\.10' <<< "${CONFIG}"
rg --color=never --quiet -- '--disable-log-bin' <<< "${CONFIG}" || \
  fail "本机平台 MySQL 未关闭会在 macOS bind mount 重启时失败的 binlog"
rg --color=never --quiet 'mem_limit: "2147483648"' <<< "${CONFIG}"
rg --color=never --quiet 'host_ip: 127\.0\.0\.1' <<< "${CONFIG}"
rg --color=never --quiet 'published: "19506"' <<< "${CONFIG}"
rg --color=never --quiet 'name: common-agent-platform-mysql-data' <<< "${CONFIG}"
rg --color=never --quiet 'device: .*\.local/dev/common-agent-dev/platform/mysql' <<< "${CONFIG}"
if rg --color=never --quiet 'image: .*:latest' <<< "${CONFIG}"; then
  fail "平台稳定栈不得使用 latest 镜像"
fi
if rg --color=never --quiet 'host_ip: 0\.0\.0\.0' <<< "${CONFIG}"; then
  fail "平台 MySQL 端口不得公开绑定"
fi

EXISTING_VOLUME_ROOT="$(mktemp -d)"
EXISTING_VOLUME_CONFIG="$(
  PATH="${SCRIPT_DIR}/../test-fixtures:${PATH}" \
  COMMON_AGENT_TEST_DOCKER_SCENARIO=platform-existing-volume \
  COMMON_AGENT_TEST_PLATFORM_VOLUME_DEVICE="${EXISTING_VOLUME_ROOT}" \
    "${MANAGER}" config
)"
rg --color=never --fixed-strings --quiet \
  "device: ${EXISTING_VOLUME_ROOT}" <<< "${EXISTING_VOLUME_CONFIG}" || {
  rm -rf "${EXISTING_VOLUME_ROOT}"
  fail "新克隆没有复用现有平台 MySQL Volume 的原始宿主目录"
}

MISMATCH_VOLUME_ROOT="$(mktemp -d)"
MISMATCH_VOLUME_OUTPUT="$(mktemp)"
if PATH="${SCRIPT_DIR}/../test-fixtures:${PATH}" \
  COMMON_AGENT_TEST_DOCKER_SCENARIO=platform-existing-volume \
  COMMON_AGENT_TEST_PLATFORM_VOLUME_DEVICE="${EXISTING_VOLUME_ROOT}" \
  PLATFORM_MYSQL_DATA_ROOT="${MISMATCH_VOLUME_ROOT}" \
    "${MANAGER}" config > "${MISMATCH_VOLUME_OUTPUT}" 2>&1; then
  rm -rf "${EXISTING_VOLUME_ROOT}" "${MISMATCH_VOLUME_ROOT}"
  rm -f "${MISMATCH_VOLUME_OUTPUT}"
  fail "显式平台数据目录与现有 Volume 冲突时仍被放行"
fi
rg --color=never --quiet '已绑定其他目录' "${MISMATCH_VOLUME_OUTPUT}"
rm -rf "${EXISTING_VOLUME_ROOT}" "${MISMATCH_VOLUME_ROOT}"
rm -f "${MISMATCH_VOLUME_OUTPUT}"

INVALID_PORT_OUTPUT="$(mktemp)"
if PLATFORM_MYSQL_PORT=abc "${MANAGER}" check-ports > "${INVALID_PORT_OUTPUT}" 2>&1; then
  rm -f "${INVALID_PORT_OUTPUT}"
  fail "非法平台 MySQL 端口仍然被放行"
fi
rg --color=never --quiet '1-65535' "${INVALID_PORT_OUTPUT}"
rm -f "${INVALID_PORT_OUTPUT}"

PORT_TEST_OUTPUT="$(mktemp)"
python3 -m http.server 29506 --bind 127.0.0.1 > /dev/null 2>&1 &
PORT_TEST_PID=$!
cleanup() {
  kill "${PORT_TEST_PID}" 2>/dev/null || true
  wait "${PORT_TEST_PID}" 2>/dev/null || true
  rm -f "${PORT_TEST_OUTPUT}"
}
trap cleanup EXIT
sleep 0.3

if PLATFORM_MYSQL_PORT=29506 "${MANAGER}" check-ports > "${PORT_TEST_OUTPUT}" 2>&1; then
  fail "平台 MySQL 端口冲突时管理脚本仍然放行"
fi
rg --color=never --quiet '29506' "${PORT_TEST_OUTPUT}"

HEALTH_TEST_ROOT="$(mktemp -d)"
HEALTH_TEST_OUTPUT="$(mktemp)"
if PATH="${SCRIPT_DIR}/../test-fixtures:${PATH}" \
  COMMON_AGENT_TEST_DOCKER_SCENARIO=platform-unhealthy \
  PLATFORM_MYSQL_DATA_ROOT="${HEALTH_TEST_ROOT}" \
  PLATFORM_HEALTH_TIMEOUT_SECONDS=1 \
  "${MANAGER}" check-health > "${HEALTH_TEST_OUTPUT}" 2>&1; then
  rm -rf "${HEALTH_TEST_ROOT}"
  rm -f "${HEALTH_TEST_OUTPUT}"
  fail "持续 unhealthy 的平台 MySQL 仍然被健康门禁放行"
fi
rg --color=never --quiet '未在 1 秒内恢复健康' "${HEALTH_TEST_OUTPUT}"
rm -rf "${HEALTH_TEST_ROOT}"
rm -f "${HEALTH_TEST_OUTPUT}"

echo "平台 MySQL 固定版本、context、端口、Volume 与资源门禁通过"
