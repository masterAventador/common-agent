#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
VERSION="$(tr -d '[:space:]' < "${SCRIPT_DIR}/VERSION")"
EXPECTED_COMMIT="$(tr -d '[:space:]' < "${SCRIPT_DIR}/UPSTREAM_COMMIT")"
STACK_ROOT="${REPOSITORY_ROOT}/.local/dev/common-agent-dev/ragflow"
RUNTIME_ROOT="${RAGFLOW_RUNTIME_ROOT:-${STACK_ROOT}/upstream/${VERSION}}"
DATA_ROOT="${RAGFLOW_DATA_ROOT:-${STACK_ROOT}/data}"
MODEL_ROOT="${RAGFLOW_MODEL_ROOT:-${STACK_ROOT}/models}"
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
    tei) echo "${RAGFLOW_TEI_PORT:-19386}" ;;
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
  for name in es redis api web web_https admin mcp go_admin go_http tei mysql minio minio_console; do
    port="$(port_value "${name}")"
    validate_port "${port}"
  done
  for name in es redis api web web_https admin mcp go_admin go_http tei mysql minio minio_console; do
    port="$(port_value "${name}")"
    if lsof -nP -iTCP:"${port}" -sTCP:LISTEN > /dev/null 2>&1; then
      echo "RAGFlow 端口已被占用：127.0.0.1:${port}（${name}）" >&2
      return 1
    fi
  done
}

check_resources() {
  local minimum_gib total_bytes required_bytes
  minimum_gib="${RAGFLOW_MIN_DOCKER_MEMORY_GIB:-40}"
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
    echo "common-agent Docker context 内存不足：至少需要 ${minimum_gib} GiB；建议为 common-agent-dev 分配 48 GiB" >&2
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

check_model() {
  local profiles model model_path
  profiles="${RAGFLOW_COMPOSE_PROFILES:-elasticsearch,cpu,tei-cpu}"
  if [[ ",${profiles}," != *",tei-cpu,"* ]]; then
    return
  fi
  model="${RAGFLOW_TEI_MODEL:-BAAI/bge-m3}"
  model_path="${MODEL_ROOT}/${model}"
  [[ -f "${model_path}/config.json" ]] || {
    echo "缺少 RAGFlow embedding 模型配置：${model_path}/config.json" >&2
    exit 1
  }
  if [[ ! -f "${model_path}/model.safetensors" && ! -f "${model_path}/pytorch_model.bin" ]]; then
    echo "缺少 RAGFlow embedding 模型权重：${model_path}" >&2
    exit 1
  fi
}

prepare() {
  ensure_data_directories
  if [[ -e "${RUNTIME_ROOT}" && ! -d "${RUNTIME_ROOT}/.git" ]]; then
    echo "RAGFlow 运行目录存在但不是 Git checkout：${RUNTIME_ROOT}" >&2
    exit 1
  fi
  if [[ ! -d "${RUNTIME_ROOT}/.git" ]]; then
    mkdir -p "$(dirname "${RUNTIME_ROOT}")"
    git clone --depth 1 --branch "${VERSION}" "${UPSTREAM_URL}" "${RUNTIME_ROOT}"
  fi

  local actual_commit actual_tag origin
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
  git -C "${RUNTIME_ROOT}" diff --quiet
  git -C "${RUNTIME_ROOT}" diff --cached --quiet
}

compose() {
  prepare
  RAGFLOW_DATA_ROOT="${DATA_ROOT}" \
  RAGFLOW_MODEL_ROOT="${MODEL_ROOT}" \
  RAGFLOW_IMAGE="${OFFICIAL_IMAGE}" \
  TEI_IMAGE_CPU="ghcr.io/huggingface/text-embeddings-inference:cpu-1.8" \
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
  TEI_PORT="127.0.0.1:$(port_value tei)" \
  COMPOSE_PROFILES="${RAGFLOW_COMPOSE_PROFILES:-elasticsearch,cpu,tei-cpu}" \
  TEI_MODEL="${RAGFLOW_TEI_MODEL:-BAAI/bge-m3}" \
  MACOS=1 \
  DOCKER_DEFAULT_PLATFORM=linux/amd64 \
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

case "${1:-}" in
  prepare) prepare ;;
  check-model) check_model ;;
  check-resources) check_resources ;;
  pull-image) pull_image ;;
  check-ports) check_ports ;;
  up)
    health_timeout_seconds="$(health_timeout)"
    check_resources
    check_model
    if ! stack_has_containers; then
      check_ports
    fi
    compose up -d --wait --wait-timeout "${health_timeout_seconds}"
    ;;
  stop) compose stop ;;
  down) compose down ;;
  status) compose ps ;;
  config) compose config ;;
  logs) compose logs -f ragflow-cpu ;;
  *)
    echo "用法: $0 {prepare|pull-image|check-model|check-resources|check-ports|up|stop|down|status|config|logs}" >&2
    exit 2
    ;;
esac
