#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
VERSION="$(tr -d '[:space:]' < "${SCRIPT_DIR}/VERSION")"
EXPECTED_COMMIT="$(tr -d '[:space:]' < "${SCRIPT_DIR}/UPSTREAM_COMMIT")"
STACK_ROOT="${REPOSITORY_ROOT}/.local/dev/common-agent-dev/ragflow"
RUNTIME_ROOT="${RAGFLOW_RUNTIME_ROOT:-${REPOSITORY_ROOT}/third_party/ragflow}"
DATA_ROOT="${RAGFLOW_DATA_ROOT:-${STACK_ROOT}/data}"
UPSTREAM_URL="https://github.com/infiniflow/ragflow.git"
OFFICIAL_IMAGE="infiniflow/ragflow:${VERSION}"
PROJECT_NAME="common-agent-dev"
DOCKER_CONTEXT_NAME="${RAGFLOW_DOCKER_CONTEXT:-colima-common-agent-dev}"

docker_cli() {
  docker --context "${DOCKER_CONTEXT_NAME}" "$@"
}

port_value() {
  case "$1" in
    es) echo "${RAGFLOW_ES_PORT:-19200}" ;;
    redis) echo "${RAGFLOW_REDIS_PORT:-19379}" ;;
    api) echo "${RAGFLOW_API_PORT:-19380}" ;;
    web) echo "${RAGFLOW_WEB_PORT:-19381}" ;;
    web_https) echo "${RAGFLOW_WEB_HTTPS_PORT:-19387}" ;;
    admin) echo "${RAGFLOW_ADMIN_PORT:-19382}" ;;
    mcp) echo "${RAGFLOW_MCP_PORT:-19383}" ;;
    go_admin) echo "${RAGFLOW_GO_ADMIN_PORT:-19384}" ;;
    go_http) echo "${RAGFLOW_GO_HTTP_PORT:-19385}" ;;
    mysql) echo "${RAGFLOW_MYSQL_PORT:-19432}" ;;
    minio) echo "${RAGFLOW_MINIO_PORT:-19900}" ;;
    minio_console) echo "${RAGFLOW_MINIO_CONSOLE_PORT:-19901}" ;;
    *) echo "未知端口名称：$1" >&2; exit 2 ;;
  esac
}

validate_port() {
  local port="$1"
  if [[ ! "${port}" =~ ^[0-9]+$ ]] || ((port < 1 || port > 65535)); then
    echo "RAGFlow 端口必须是 1-65535 的整数：${port}" >&2
    exit 2
  fi
}

check_ports() {
  local name port
  for name in es redis api web web_https admin mcp go_admin go_http mysql minio minio_console; do
    port="$(port_value "${name}")"
    validate_port "${port}"
  done
  for name in es redis api web web_https admin mcp go_admin go_http mysql minio minio_console; do
    port="$(port_value "${name}")"
    if lsof -nP -iTCP:"${port}" -sTCP:LISTEN > /dev/null 2>&1; then
      echo "RAGFlow 端口已被占用：127.0.0.1:${port}（${name}）" >&2
      return 1
    fi
  done
}

check_resources() {
  local minimum_gib total_bytes required_bytes
  minimum_gib="${RAGFLOW_MIN_DOCKER_MEMORY_GIB:-24}"
  if [[ ! "${minimum_gib}" =~ ^[0-9]+$ ]] || ((minimum_gib < 1 || minimum_gib > 128)); then
    echo "RAGFlow 最低 Docker 内存必须是 1-128 的整数 GiB：${minimum_gib}" >&2
    exit 2
  fi
  if ! total_bytes="$(docker_cli info --format '{{.MemTotal}}')"; then
    echo "无法读取 common-agent Docker context 内存" >&2
    return 1
  fi
  if [[ ! "${total_bytes}" =~ ^[0-9]+$ ]]; then
    echo "Docker 返回了无法识别的内存值：${total_bytes}" >&2
    return 1
  fi
  required_bytes=$((minimum_gib * 1024 * 1024 * 1024))
  if ((total_bytes < required_bytes)); then
    echo "common-agent Docker context 内存不足：至少需要 ${minimum_gib} GiB；建议为 common-agent-dev 分配 32 GiB" >&2
    return 1
  fi
}

health_timeout() {
  local timeout_seconds="${RAGFLOW_HEALTH_TIMEOUT_SECONDS:-180}"
  if [[ ! "${timeout_seconds}" =~ ^[0-9]+$ ]] || ((timeout_seconds < 1 || timeout_seconds > 600)); then
    echo "RAGFlow 健康等待必须是 1-600 的整数秒：${timeout_seconds}" >&2
    exit 2
  fi
  echo "${timeout_seconds}"
}

ensure_data_directories() {
  mkdir -p \
    "${DATA_ROOT}/elasticsearch" \
    "${DATA_ROOT}/mysql" \
    "${DATA_ROOT}/minio" \
    "${DATA_ROOT}/redis" \
    "${DATA_ROOT}/logs"
}

prepare() {
  ensure_data_directories
  if ! git -C "${RUNTIME_ROOT}" rev-parse --is-inside-work-tree > /dev/null 2>&1; then
    echo "RAGFlow submodule 未初始化：${RUNTIME_ROOT}" >&2
    echo "请执行：git submodule update --init --recursive third_party/ragflow" >&2
    exit 1
  fi

  local actual_commit actual_tag origin worktree_status
  actual_commit="$(git -C "${RUNTIME_ROOT}" rev-parse HEAD)"
  actual_tag="$(git -C "${RUNTIME_ROOT}" describe --tags --exact-match HEAD)"
  origin="$(git -C "${RUNTIME_ROOT}" remote get-url origin)"
  [[ "${origin}" == "${UPSTREAM_URL}" ]] || {
    echo "RAGFlow 上游地址不匹配：${origin}" >&2
    exit 1
  }
  [[ "${actual_tag}" == "${VERSION}" ]] || {
    echo "RAGFlow 运行目录版本不匹配：期望 ${VERSION}，实际 ${actual_tag}" >&2
    exit 1
  }
  [[ "${actual_commit}" == "${EXPECTED_COMMIT}" ]] || {
    echo "RAGFlow 上游提交不匹配：期望 ${EXPECTED_COMMIT}，实际 ${actual_commit}" >&2
    exit 1
  }
  worktree_status="$(git -C "${RUNTIME_ROOT}" status --short)"
  [[ -z "${worktree_status}" ]] || {
    echo "RAGFlow submodule 必须保持未修改状态：${RUNTIME_ROOT}" >&2
    exit 1
  }
}

compose() {
  local dashscope_http_base_url
  prepare
  if [[ -n "${RAGFLOW_DASHSCOPE_HTTP_BASE_URL:-}" ]]; then
    dashscope_http_base_url="${RAGFLOW_DASHSCOPE_HTTP_BASE_URL}"
  elif ! dashscope_http_base_url="$(bailian_native_base_url 2>/dev/null)"; then
    dashscope_http_base_url="https://dashscope.aliyuncs.com/api/v1"
  fi
  RAGFLOW_DATA_ROOT="${DATA_ROOT}" \
  RAGFLOW_DASHSCOPE_HTTP_BASE_URL="${dashscope_http_base_url}" \
  RAGFLOW_IMAGE="${OFFICIAL_IMAGE}" \
  ES_PORT="127.0.0.1:$(port_value es)" \
  EXPOSE_MYSQL_PORT="127.0.0.1:$(port_value mysql)" \
  MINIO_PORT="127.0.0.1:$(port_value minio)" \
  MINIO_CONSOLE_PORT="127.0.0.1:$(port_value minio_console)" \
  REDIS_PORT="127.0.0.1:$(port_value redis)" \
  SVR_HTTP_PORT="127.0.0.1:$(port_value api)" \
  SVR_WEB_HTTP_PORT="127.0.0.1:$(port_value web)" \
  SVR_WEB_HTTPS_PORT="127.0.0.1:$(port_value web_https)" \
  ADMIN_SVR_HTTP_PORT="127.0.0.1:$(port_value admin)" \
  SVR_MCP_PORT="127.0.0.1:$(port_value mcp)" \
  GO_ADMIN_PORT="127.0.0.1:$(port_value go_admin)" \
  GO_HTTP_PORT="127.0.0.1:$(port_value go_http)" \
  COMPOSE_PROFILES="${RAGFLOW_COMPOSE_PROFILES:-elasticsearch,cpu}" \
  MACOS=1 \
    docker_cli compose \
      --project-name "${PROJECT_NAME}" \
      --project-directory "${RUNTIME_ROOT}/docker" \
      -f "${RUNTIME_ROOT}/docker/docker-compose.yml" \
      -f "${SCRIPT_DIR}/compose.override.yaml" \
      "$@"
}

stack_has_containers() {
  [[ -n "$(compose ps -aq)" ]]
}

pull_image() {
  prepare
  if docker_cli image inspect "${OFFICIAL_IMAGE}" > /dev/null 2>&1; then
    echo "复用本机 RAGFlow 镜像：${OFFICIAL_IMAGE}"
    return
  fi
  local source="${RAGFLOW_IMAGE_SOURCE:-${OFFICIAL_IMAGE}}"
  docker_cli pull --platform linux/amd64 "${source}"
  if [[ "${source}" != "${OFFICIAL_IMAGE}" ]]; then
    docker_cli tag "${source}" "${OFFICIAL_IMAGE}"
  fi
}

bailian_native_base_url() {
  local backend_python="${REPOSITORY_ROOT}/backend/.venv/bin/python"
  [[ -x "${backend_python}" ]] || return 1
  "${backend_python}" -m common_agent.adapters.knowledge.ragflow_models native-base-url
}

configure_bailian_models() {
  local action="$1"
  local backend_python="${REPOSITORY_ROOT}/backend/.venv/bin/python"
  if [[ ! -x "${backend_python}" ]]; then
    echo "缺少后端冻结环境；请先在 backend/ 执行 uv sync --frozen" >&2
    exit 1
  fi
  RAGFLOW_BASE_URL="${RAGFLOW_BASE_URL:-http://127.0.0.1:$(port_value api)}" \
    "${backend_python}" -m common_agent.adapters.knowledge.ragflow_models "${action}"
}

case "${1:-}" in
  prepare) prepare ;;
  check-resources) check_resources ;;
  pull-image) pull_image ;;
  check-ports) check_ports ;;
  configure-bailian) configure_bailian_models apply ;;
  check-bailian) configure_bailian_models status ;;
  plan-bailian-migration) configure_bailian_models plan-migration ;;
  migrate-bailian) configure_bailian_models migrate ;;
  up)
    bailian_base_url="$(bailian_native_base_url)" || {
      echo "缺少有效的百炼配置或后端冻结环境；请先在 backend/ 执行 uv sync --frozen" >&2
      exit 1
    }
    health_timeout_seconds="$(health_timeout)"
    check_resources
    if ! stack_has_containers; then
      check_ports
    fi
    RAGFLOW_DASHSCOPE_HTTP_BASE_URL="${bailian_base_url}" \
      compose up -d --wait --wait-timeout "${health_timeout_seconds}"
    ;;
  stop) compose stop ;;
  down) compose down ;;
  status) compose ps ;;
  config) compose config ;;
  logs) compose logs -f ragflow-cpu ;;
  *)
    echo "用法: $0 {prepare|pull-image|check-resources|check-ports|up|configure-bailian|check-bailian|plan-bailian-migration|migrate-bailian|stop|down|status|config|logs}" >&2
    exit 2
    ;;
esac
