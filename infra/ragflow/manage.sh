#!/usr/bin/env bash
# shellcheck disable=SC2016 # Inner-container scripts intentionally expand in their own shell.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
VERSION="$(tr -d '[:space:]' < "${SCRIPT_DIR}/VERSION")"
UPSTREAM_COMMIT="$(tr -d '[:space:]' < "${SCRIPT_DIR}/UPSTREAM_COMMIT")"
FORK_METADATA="${SCRIPT_DIR}/fork.env"
PATCHSET_METADATA="${SCRIPT_DIR}/patchset.env"
IMAGE_METADATA="${SCRIPT_DIR}/image.env"
IMAGE_MANAGER="${SCRIPT_DIR}/image.sh"
# shellcheck disable=SC1090
source "${FORK_METADATA}"
# shellcheck disable=SC1090
source "${PATCHSET_METADATA}"
# shellcheck disable=SC1090
source "${IMAGE_METADATA}"
EXPECTED_COMMIT="${RAGFLOW_PATCH_HEAD}"
STACK_ROOT="${REPOSITORY_ROOT}/.local/dev/common-agent-dev/ragflow"
RUNTIME_ROOT="${RAGFLOW_RUNTIME_ROOT:-${REPOSITORY_ROOT}/third_party/ragflow}"
DATA_ROOT="${RAGFLOW_DATA_ROOT:-${STACK_ROOT}/data}"
VOLUME_MIGRATION_IMAGE="mysql:8.0.39"
VOLUME_MARKER=".common-agent-native-volume-ready"
MYSQL_MIGRATION_SOURCE_CONTAINER="common-agent-ragflow-mysql-migration-source"
MYSQL_MIGRATION_TARGET_CONTAINER="common-agent-ragflow-mysql-migration-target"
MYSQL_MIGRATION_PASSWORD="${RAGFLOW_MYSQL_MIGRATION_PASSWORD:-infini_rag_flow}"
MYSQL_MIGRATION_SNAPSHOT_ROOT="${RAGFLOW_MYSQL_MIGRATION_SNAPSHOT_ROOT:-${STACK_ROOT}/migration/mysql-source-snapshot}"
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

  [[ "${VERSION}" == "${RAGFLOW_UPSTREAM_VERSION}" ]] || {
    echo "RAGFlow 版本元数据不一致：${VERSION}" >&2
    exit 1
  }
  [[ "${UPSTREAM_COMMIT}" == "${RAGFLOW_UPSTREAM_COMMIT}" && \
      "${RAGFLOW_PATCH_BASE}" == "${RAGFLOW_UPSTREAM_COMMIT}" ]] || {
    echo "RAGFlow 官方基线元数据不一致" >&2
    exit 1
  }
  [[ "${RAGFLOW_FORK_IMAGE_REVISION}" == "${EXPECTED_COMMIT}" ]] || {
    echo "RAGFlow 镜像 revision 与补丁提交不一致" >&2
    exit 1
  }
  "${IMAGE_MANAGER}" verify-source >/dev/null
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
  RAGFLOW_IMAGE="${RAGFLOW_FORK_IMAGE}" \
  RAGFLOW_ELASTICSEARCH_IMAGE="${RAGFLOW_ELASTICSEARCH_IMAGE}" \
  RAGFLOW_MYSQL_IMAGE="${RAGFLOW_MYSQL_IMAGE}" \
  RAGFLOW_MINIO_IMAGE="${RAGFLOW_MINIO_IMAGE}" \
  RAGFLOW_VALKEY_IMAGE="${RAGFLOW_VALKEY_IMAGE}" \
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
  "${IMAGE_MANAGER}" ensure
}

volume_exists() {
  docker_cli volume inspect "$1" > /dev/null 2>&1
}

volume_has_entries() {
  docker_cli run --rm \
    --entrypoint sh \
    -v "$1:/volume:ro" \
    "${VOLUME_MIGRATION_IMAGE}" \
    -c 'test -n "$(ls -A /volume)"'
}

volume_has_marker() {
  docker_cli run --rm \
    --entrypoint sh \
    -v "$1:/volume:ro" \
    "${VOLUME_MIGRATION_IMAGE}" \
    -c "test -f /volume/${VOLUME_MARKER}"
}

native_volumes_ready() {
  local volume_name
  for volume_name in \
    common-agent-ragflow-esdata-v2 \
    common-agent-ragflow-mysql-data-v3 \
    common-agent-ragflow-minio-data-v2 \
    common-agent-ragflow-valkey-data-v2; do
    volume_exists "${volume_name}" && volume_has_marker "${volume_name}" || return 1
  done
}

migrate_native_volume() {
  local legacy_volume="$1"
  local native_volume="$2"
  local owner="$3"
  if volume_exists "${native_volume}" && volume_has_entries "${native_volume}"; then
    if volume_has_marker "${native_volume}"; then
      echo "复用 RAGFlow 原生数据卷：${native_volume}"
      return
    fi
    docker_cli volume rm "${native_volume}" > /dev/null
  fi

  docker_cli volume create "${native_volume}" > /dev/null
  if ! volume_exists "${legacy_volume}" || ! volume_has_entries "${legacy_volume}"; then
    docker_cli run --rm \
      --entrypoint sh \
      -v "${native_volume}:/target" \
      "${VOLUME_MIGRATION_IMAGE}" \
      -c "touch /target/${VOLUME_MARKER}"
    echo "创建 RAGFlow 原生数据卷：${native_volume}"
    return
  fi

  docker_cli run --rm \
    --user 0 \
    --entrypoint sh \
    -v "${legacy_volume}:/source:ro" \
    -v "${native_volume}:/target" \
    "${VOLUME_MIGRATION_IMAGE}" \
    -c 'test -z "$(ls -A /target)"; cp -a /source/. /target/; touch "/target/$1"; chown -R "$2" /target' \
    sh "${VOLUME_MARKER}" "${owner}"
  echo "RAGFlow 数据已只读复制到原生卷：${legacy_volume} -> ${native_volume}"
}

wait_for_mysql_container() {
  local container_name="$1"
  local socket_option="${2:-}"
  local deadline=$((SECONDS + 120))
  while ((SECONDS < deadline)); do
    if docker_cli exec "${container_name}" \
      mysqladmin ${socket_option:+"${socket_option}"} ping \
      -uroot "-p${MYSQL_MIGRATION_PASSWORD}" --silent > /dev/null 2>&1; then
      return
    fi
    if [[ "$(docker_cli inspect --format '{{.State.Status}}' "${container_name}" 2>/dev/null || true)" == "exited" ]]; then
      docker_cli logs --tail 80 "${container_name}" >&2
      return 1
    fi
    sleep 1
  done
  echo "RAGFlow MySQL 数据迁移容器未在 120 秒内就绪：${container_name}" >&2
  return 1
}

cleanup_mysql_migration_containers() {
  docker_cli rm -f \
    "${MYSQL_MIGRATION_SOURCE_CONTAINER}" \
    "${MYSQL_MIGRATION_TARGET_CONTAINER}" > /dev/null 2>&1 || true
}

prepare_mysql_source_snapshot() {
  local legacy_volume="$1"
  local snapshot_marker="${MYSQL_MIGRATION_SNAPSHOT_ROOT}/.common-agent-source-snapshot-ready"
  mkdir -p "${MYSQL_MIGRATION_SNAPSHOT_ROOT}"
  if [[ -f "${snapshot_marker}" ]]; then
    return
  fi
  if [[ -n "$(find "${MYSQL_MIGRATION_SNAPSHOT_ROOT}" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
    echo "RAGFlow MySQL 迁移快照目录非空且缺少就绪标记：${MYSQL_MIGRATION_SNAPSHOT_ROOT}" >&2
    return 1
  fi
  docker_cli run --rm \
    --user 0 \
    --entrypoint sh \
    -v "${legacy_volume}:/source:ro" \
    -v "${MYSQL_MIGRATION_SNAPSHOT_ROOT}:/target" \
    "${VOLUME_MIGRATION_IMAGE}" \
    -c 'test -z "$(ls -A /target)"; cp -a /source/. /target/; touch /target/.common-agent-source-snapshot-ready'
  echo "RAGFlow MySQL 旧卷已只读复制到迁移快照：${MYSQL_MIGRATION_SNAPSHOT_ROOT}"
}

migrate_mysql_native_volume() {
  local legacy_volume="common-agent-ragflow-mysql-data"
  local native_volume="common-agent-ragflow-mysql-data-v3"
  local table_count
  if volume_exists "${native_volume}" && volume_has_marker "${native_volume}"; then
    echo "复用 RAGFlow 原生数据卷：${native_volume}"
    return
  fi
  cleanup_mysql_migration_containers
  if volume_exists "${native_volume}"; then
    docker_cli volume rm "${native_volume}" > /dev/null
  fi
  docker_cli volume create "${native_volume}" > /dev/null
  if ! volume_exists "${legacy_volume}" || ! volume_has_entries "${legacy_volume}"; then
    docker_cli run --rm \
      --entrypoint sh \
      -v "${native_volume}:/target" \
      "${VOLUME_MIGRATION_IMAGE}" \
      -c "touch /target/${VOLUME_MARKER}; chown -R 999:999 /target"
    echo "创建 RAGFlow 原生数据卷：${native_volume}"
    return
  fi
  prepare_mysql_source_snapshot "${legacy_volume}"

  docker_cli run -d \
    --name "${MYSQL_MIGRATION_SOURCE_CONTAINER}" \
    --entrypoint mysqld \
    -v "${MYSQL_MIGRATION_SNAPSHOT_ROOT}:/var/lib/mysql" \
    "${VOLUME_MIGRATION_IMAGE}" \
    --no-defaults \
    --user=root \
    --datadir=/var/lib/mysql \
    --lower-case-table-names=2 \
    --skip-networking \
    --socket=/tmp/mysql.sock \
    --pid-file=/tmp/mysql.pid > /dev/null
  docker_cli run -d \
    --name "${MYSQL_MIGRATION_TARGET_CONTAINER}" \
    -e "MYSQL_ROOT_PASSWORD=${MYSQL_MIGRATION_PASSWORD}" \
    -e MYSQL_DATABASE=rag_flow \
    -v "${native_volume}:/var/lib/mysql" \
    "${VOLUME_MIGRATION_IMAGE}" > /dev/null

  if ! wait_for_mysql_container "${MYSQL_MIGRATION_SOURCE_CONTAINER}" "--socket=/tmp/mysql.sock" || \
    ! wait_for_mysql_container "${MYSQL_MIGRATION_TARGET_CONTAINER}"; then
    cleanup_mysql_migration_containers
    return 1
  fi
  if ! docker_cli exec "${MYSQL_MIGRATION_SOURCE_CONTAINER}" \
    mysqldump --socket=/tmp/mysql.sock \
      -uroot "-p${MYSQL_MIGRATION_PASSWORD}" \
      --single-transaction --routines --events --triggers --set-gtid-purged=OFF rag_flow | \
    docker_cli exec -i "${MYSQL_MIGRATION_TARGET_CONTAINER}" \
      mysql -uroot "-p${MYSQL_MIGRATION_PASSWORD}" rag_flow; then
    cleanup_mysql_migration_containers
    return 1
  fi
  table_count="$(
    docker_cli exec "${MYSQL_MIGRATION_TARGET_CONTAINER}" \
      mysql -N -uroot "-p${MYSQL_MIGRATION_PASSWORD}" \
      -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='rag_flow';"
  )"
  if [[ ! "${table_count}" =~ ^[1-9][0-9]*$ ]]; then
    echo "RAGFlow MySQL 逻辑迁移未产生业务表" >&2
    cleanup_mysql_migration_containers
    return 1
  fi
  docker_cli exec "${MYSQL_MIGRATION_TARGET_CONTAINER}" \
    sh -c "touch /var/lib/mysql/${VOLUME_MARKER}; chown mysql:mysql /var/lib/mysql/${VOLUME_MARKER}"
  cleanup_mysql_migration_containers
  echo "RAGFlow MySQL 已从 macOS 数据字典逻辑迁移到原生卷：${legacy_volume} -> ${native_volume}"
}

migrate_native_volumes() {
  prepare
  if native_volumes_ready; then
    echo "RAGFlow 原生数据卷：ready"
    return
  fi
  if [[ -n "$(docker_cli ps -aq --filter name=common-agent-ragflow)" ]]; then
    compose down
  fi
  if ! docker_cli image inspect "${VOLUME_MIGRATION_IMAGE}" > /dev/null 2>&1; then
    docker_cli pull "${VOLUME_MIGRATION_IMAGE}"
  fi
  migrate_native_volume \
    common-agent-ragflow-esdata common-agent-ragflow-esdata-v2 1000:0
  migrate_mysql_native_volume
  migrate_native_volume \
    common-agent-ragflow-minio-data common-agent-ragflow-minio-data-v2 0:0
  migrate_native_volume \
    common-agent-ragflow-valkey-data common-agent-ragflow-valkey-data-v2 999:999
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
  build-image) prepare; "${IMAGE_MANAGER}" build ;;
  verify-image) prepare; "${IMAGE_MANAGER}" verify ;;
  scan-image) prepare; "${IMAGE_MANAGER}" scan ;;
  migrate-native-volumes) migrate_native_volumes ;;
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
    pull_image
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
    echo "用法: $0 {prepare|pull-image|build-image|verify-image|scan-image|migrate-native-volumes|check-resources|check-ports|up|configure-bailian|check-bailian|plan-bailian-migration|migrate-bailian|stop|down|status|config|logs}" >&2
    exit 2
    ;;
esac
