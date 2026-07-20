#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
MYSQL_VERSION="$(tr -d '[:space:]' < "${SCRIPT_DIR}/MYSQL_VERSION")"
PROJECT_NAME="common-agent-platform-dev"
DOCKER_CONTEXT_NAME="${PLATFORM_DOCKER_CONTEXT:-colima-common-agent-dev}"
DATA_ROOT="${PLATFORM_MYSQL_DATA_ROOT:-${REPOSITORY_ROOT}/.local/dev/common-agent-dev/platform/mysql}"
DATA_ROOT_IS_EXPLICIT=0
VOLUME_NAME="common-agent-platform-mysql-data"
if [[ -n "${PLATFORM_MYSQL_DATA_ROOT+x}" ]]; then
  DATA_ROOT_IS_EXPLICIT=1
fi

docker_cli() {
  docker --context "${DOCKER_CONTEXT_NAME}" "$@"
}

mysql_port() {
  echo "${PLATFORM_MYSQL_PORT:-19506}"
}

validate_port() {
  local port="$1"
  if [[ ! "${port}" =~ ^[0-9]+$ ]] || ((port < 1 || port > 65535)); then
    echo "平台 MySQL 端口必须是 1-65535 的整数：${port}" >&2
    exit 2
  fi
}

check_ports() {
  local port
  port="$(mysql_port)"
  validate_port "${port}"
  if lsof -nP -iTCP:"${port}" -sTCP:LISTEN > /dev/null 2>&1; then
    echo "平台 MySQL 端口已被占用：127.0.0.1:${port}" >&2
    return 1
  fi
}

prepare() {
  mkdir -p "${DATA_ROOT}"
}

resolve_data_root() {
  local existing_data_root=""
  existing_data_root="$(
    docker_cli volume inspect "${VOLUME_NAME}" \
      --format '{{.Options.device}}' 2>/dev/null || true
  )"
  if [[ -z "${existing_data_root}" || "${existing_data_root}" == "<no value>" ]]; then
    return
  fi
  if ((DATA_ROOT_IS_EXPLICIT == 1)) && [[ "${DATA_ROOT}" != "${existing_data_root}" ]]; then
    echo "平台 MySQL Volume ${VOLUME_NAME} 已绑定其他目录：${existing_data_root}" >&2
    echo "拒绝自动重建或迁移；请复用该目录，或另行执行有备份的数据迁移任务" >&2
    return 1
  fi
  DATA_ROOT="${existing_data_root}"
}

compose() {
  resolve_data_root
  prepare
  PLATFORM_MYSQL_VERSION="${MYSQL_VERSION}" \
  PLATFORM_MYSQL_PORT="$(mysql_port)" \
  PLATFORM_MYSQL_DATA_ROOT="${DATA_ROOT}" \
  PLATFORM_MYSQL_DATABASE="${PLATFORM_MYSQL_DATABASE:-common_agent}" \
  PLATFORM_MYSQL_USER="${PLATFORM_MYSQL_USER:-common_agent}" \
  PLATFORM_MYSQL_PASSWORD="${PLATFORM_MYSQL_PASSWORD:-common_agent_dev}" \
  PLATFORM_MYSQL_ROOT_PASSWORD="${PLATFORM_MYSQL_ROOT_PASSWORD:-common_agent_root_dev}" \
    docker_cli compose \
      --project-name "${PROJECT_NAME}" \
      -f "${SCRIPT_DIR}/compose.yaml" \
      "$@"
}

stack_has_containers() {
  [[ -n "$(compose ps -aq)" ]]
}

wait_for_healthy() {
  local container_id
  local state
  local healthy_since=-1
  local timeout_seconds="${PLATFORM_HEALTH_TIMEOUT_SECONDS:-60}"
  local deadline

  if [[ ! "${timeout_seconds}" =~ ^[0-9]+$ ]] || ((timeout_seconds < 1 || timeout_seconds > 600)); then
    echo "平台 MySQL 健康等待必须是 1-600 的整数秒：${timeout_seconds}" >&2
    exit 2
  fi
  deadline=$((SECONDS + timeout_seconds))

  container_id="$(compose ps -q mysql)"
  if [[ -z "${container_id}" ]]; then
    echo "平台 MySQL 容器不存在" >&2
    return 1
  fi

  while ((SECONDS < deadline)); do
    state="$(docker_cli inspect \
      --format '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' \
      "${container_id}")"
    if [[ "${state}" == "running healthy" ]]; then
      if ((healthy_since < 0)); then
        healthy_since=${SECONDS}
      elif ((SECONDS - healthy_since >= 10)); then
        return
      fi
    else
      healthy_since=-1
    fi
    sleep 1
  done

  echo "平台 MySQL 未在 ${timeout_seconds} 秒内恢复健康" >&2
  compose ps >&2
  return 1
}

ensure_test_database() {
  docker_cli exec common-agent-platform-mysql sh -ec \
    "MYSQL_PWD=\"\${MYSQL_ROOT_PASSWORD}\" mysql --protocol=socket -uroot --execute=\"CREATE DATABASE IF NOT EXISTS common_agent_test CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci; GRANT ALL PRIVILEGES ON common_agent_test.* TO 'common_agent'@'%';\""
}

pull_image() {
  local image="mysql:${MYSQL_VERSION}"
  if docker_cli image inspect "${image}" > /dev/null 2>&1; then
    echo "复用本机平台 MySQL 镜像：${image}"
    return
  fi
  docker_cli pull "${image}"
}

case "${1:-}" in
  prepare) prepare ;;
  pull-image) pull_image ;;
  check-ports) check_ports ;;
  check-health) wait_for_healthy ;;
  up)
    if ! stack_has_containers; then
      check_ports
    fi
    compose up -d
    wait_for_healthy
    ensure_test_database
    ;;
  stop) compose stop ;;
  down) compose down ;;
  status) compose ps ;;
  config) compose config ;;
  logs) compose logs -f mysql ;;
  *)
    echo "用法: $0 {prepare|pull-image|check-ports|check-health|up|stop|down|status|config|logs}" >&2
    exit 2
    ;;
esac
