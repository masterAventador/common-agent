#!/usr/bin/env bash
# shellcheck disable=SC2016 # Container-side commands expand only in their target container.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
BACKEND_ROOT="${REPOSITORY_ROOT}/backend"
FRONTEND_ROOT="${REPOSITORY_ROOT}/frontend"
RAGFLOW_ROOT="${REPOSITORY_ROOT}/third_party/ragflow"
RAGFLOW_IMAGE_MANAGER="${REPOSITORY_ROOT}/infra/ragflow/image.sh"
RAGFLOW_IMAGE_METADATA="${REPOSITORY_ROOT}/infra/ragflow/image.env"
# shellcheck disable=SC1090
source "${RAGFLOW_IMAGE_METADATA}"
DOCKER_CONTEXT_NAME="${BACKUP_DOCKER_CONTEXT:-colima-common-agent-dev}"
RUN_ID="$(date -u '+%Y%m%d%H%M%S')-$$"
SOURCE_ID="s1006-source-${RUN_ID}"
RESTORE_ID="s1006-restored-${RUN_ID}"
ARTIFACT_ROOT="${REPOSITORY_ROOT}/.local/test-artifacts/backup-drill/${RUN_ID}"
BACKUP_ROOT="${ARTIFACT_ROOT}/backups"
BACKUP_KEY_FILE="${ARTIFACT_ROOT}/secrets/backup.key"
RAGFLOW_TOKEN_FILE="${ARTIFACT_ROOT}/secrets/ragflow-api-token"
SOURCE_MYSQL_CONTAINER="common-agent-recovery-${SOURCE_ID}-mysql"
RESTORE_MYSQL_CONTAINER="common-agent-recovery-${RESTORE_ID}-mysql"
SOURCE_MYSQL_VOLUME="common-agent-recovery-${SOURCE_ID}-platform-mysql-data"
RESTORE_MYSQL_VOLUME="common-agent-recovery-${RESTORE_ID}-platform-mysql-data"
MYSQL_PORT=28506
RAGFLOW_ES_PORT=28200
RAGFLOW_REDIS_PORT=28379
RAGFLOW_API_PORT=28380
RAGFLOW_WEB_PORT=28381
RAGFLOW_ADMIN_PORT=28382
RAGFLOW_MCP_PORT=28383
RAGFLOW_GO_ADMIN_PORT=28384
RAGFLOW_GO_HTTP_PORT=28385
RAGFLOW_WEB_HTTPS_PORT=28387
RAGFLOW_MYSQL_PORT=28432
RAGFLOW_MINIO_PORT=28900
RAGFLOW_MINIO_CONSOLE_PORT=28901
API_PORT=18200
FRONTEND_PORT=18280
MYSQL_ROOT_SECRET="REDACTED"
MYSQL_APP_SECRET="s1006-isolated-app-secret"
AUTH_BOOTSTRAP_TOKEN="s1006-isolated-bootstrap-token-at-least-32-characters"
AUTH_EMAIL="s1006-recovery-owner@example.com"
AUTH_PASSWORD="s1006 recovery password is deliberately isolated"
KNOWLEDGE_NAME="common-agent-s10-06-knowledge-${RUN_ID}"
EMPLOYEE_NAME="common-agent-s10-06-employee-${RUN_ID}"
PROFILE_STARTED=0
BACKEND_PID=""
WORKER_PID=""
FRONTEND_PID=""
RAGFLOW_NATIVE_BASE_URL=""

docker_cli() {
  docker --context "${DOCKER_CONTEXT_NAME}" "$@"
}

require_command() {
  if ! command -v "$1" > /dev/null 2>&1; then
    echo "灾难演练缺少工具：$1" >&2
    return 1
  fi
}

check_prerequisites() {
  local command_name
  for command_name in colima curl docker git jq lsof openssl pnpm; do
    require_command "${command_name}"
  done
  [[ -x "${BACKEND_ROOT}/.venv/bin/python" ]] || {
    echo "灾难演练要求已冻结的后端环境；先执行 scripts/real.sh setup" >&2
    return 1
  }
  [[ -x "${FRONTEND_ROOT}/node_modules/.bin/vite" ]] || {
    echo "灾难演练要求已冻结的前端依赖；先执行 scripts/real.sh setup" >&2
    return 1
  }
  if [[ -n "$(git -C "${RAGFLOW_ROOT}" status --short)" ]]; then
    echo "RAGFlow submodule 必须保持未修改" >&2
    return 1
  fi
  RAGFLOW_DOCKER_CONTEXT="${DOCKER_CONTEXT_NAME}" "${RAGFLOW_IMAGE_MANAGER}" verify
}

check_ports() {
  local port
  for port in \
    "${API_PORT}" "${FRONTEND_PORT}" "${MYSQL_PORT}" "${RAGFLOW_ES_PORT}" \
    "${RAGFLOW_REDIS_PORT}" "${RAGFLOW_API_PORT}" "${RAGFLOW_WEB_PORT}" \
    "${RAGFLOW_ADMIN_PORT}" "${RAGFLOW_MCP_PORT}" "${RAGFLOW_GO_ADMIN_PORT}" \
    "${RAGFLOW_GO_HTTP_PORT}" "${RAGFLOW_WEB_HTTPS_PORT}" "${RAGFLOW_MYSQL_PORT}" \
    "${RAGFLOW_MINIO_PORT}" "${RAGFLOW_MINIO_CONSOLE_PORT}"; do
    if lsof -nP -iTCP:"${port}" -sTCP:LISTEN > /dev/null 2>&1; then
      echo "灾难演练端口已被占用：${port}" >&2
      return 1
    fi
  done
}

ensure_colima() {
  local memory_bytes
  if colima status --profile common-agent-dev > /dev/null 2>&1; then
    memory_bytes="$(docker_cli info --format '{{.MemTotal}}')"
    if [[ ! "${memory_bytes}" =~ ^[0-9]+$ ]] || ((memory_bytes < 31 * 1024 * 1024 * 1024)); then
      echo "灾难演练要求项目专属 Colima 至少 31 GiB；当前 profile 正在运行且资源不足" >&2
      return 1
    fi
    return
  fi
  colima start common-agent-dev \
    --cpus 8 \
    --memory 32 \
    --disk 100 \
    --root-disk 20 \
    --runtime docker \
    --vm-type vz \
    --vz-rosetta \
    --activate=false
  PROFILE_STARTED=1
  docker_cli info > /dev/null
}

ragflow_volume() {
  local instance_id="$1"
  local component="$2"
  echo "common-agent-recovery-${instance_id}-ragflow-${component}"
}

create_ragflow_volumes() {
  local instance_id="$1"
  local component
  for component in esdata-v2 mysql-data-v3 minio-data-v2 valkey-data-v2; do
    docker_cli volume create "$(ragflow_volume "${instance_id}" "${component}")" > /dev/null
  done
}

ragflow_compose() {
  local instance_id="$1"
  shift
  local data_root="${ARTIFACT_ROOT}/${instance_id}/ragflow"
  mkdir -p "${data_root}/logs"
  (
    export BACKUP_RECOVERY_ID="${instance_id}"
    export RAGFLOW_RECOVERY_DATA_ROOT="${data_root}"
    export RAGFLOW_DASHSCOPE_HTTP_BASE_URL="${RAGFLOW_NATIVE_BASE_URL}"
    export RAGFLOW_IMAGE="${RAGFLOW_FORK_IMAGE}"
    export RAGFLOW_ELASTICSEARCH_IMAGE RAGFLOW_MYSQL_IMAGE RAGFLOW_MINIO_IMAGE RAGFLOW_VALKEY_IMAGE
    export ES_PORT="127.0.0.1:${RAGFLOW_ES_PORT}"
    export REDIS_PORT="127.0.0.1:${RAGFLOW_REDIS_PORT}"
    export SVR_HTTP_PORT="127.0.0.1:${RAGFLOW_API_PORT}"
    export SVR_WEB_HTTP_PORT="127.0.0.1:${RAGFLOW_WEB_PORT}"
    export SVR_WEB_HTTPS_PORT="127.0.0.1:${RAGFLOW_WEB_HTTPS_PORT}"
    export ADMIN_SVR_HTTP_PORT="127.0.0.1:${RAGFLOW_ADMIN_PORT}"
    export SVR_MCP_PORT="127.0.0.1:${RAGFLOW_MCP_PORT}"
    export GO_ADMIN_PORT="127.0.0.1:${RAGFLOW_GO_ADMIN_PORT}"
    export GO_HTTP_PORT="127.0.0.1:${RAGFLOW_GO_HTTP_PORT}"
    export EXPOSE_MYSQL_PORT="127.0.0.1:${RAGFLOW_MYSQL_PORT}"
    export MINIO_PORT="127.0.0.1:${RAGFLOW_MINIO_PORT}"
    export MINIO_CONSOLE_PORT="127.0.0.1:${RAGFLOW_MINIO_CONSOLE_PORT}"
    export COMPOSE_PROFILES="elasticsearch,cpu"
    export MACOS=1
    docker_cli compose \
      --project-name "common-agent-recovery-${instance_id}-ragflow" \
      --project-directory "${RAGFLOW_ROOT}/docker" \
      -f "${RAGFLOW_ROOT}/docker/docker-compose.yml" \
      -f "${SCRIPT_DIR}/recovery-ragflow.override.yaml" \
      "$@"
  )
}

wait_for_url() {
  local url="$1"
  local process_id="${2:-}"
  local deadline=$((SECONDS + 300))
  while ((SECONDS < deadline)); do
    if curl --fail --silent --show-error "${url}" > /dev/null 2>&1; then
      return
    fi
    if [[ -n "${process_id}" ]] && ! kill -0 "${process_id}" > /dev/null 2>&1; then
      echo "服务进程在就绪前退出：${url}" >&2
      return 1
    fi
    sleep 2
  done
  echo "服务未在 300 秒内就绪：${url}" >&2
  return 1
}

wait_for_mysql() {
  local container="$1"
  local database="$2"
  local deadline=$((SECONDS + 120))
  while ((SECONDS < deadline)); do
    if docker_cli exec "${container}" sh -ec \
      'MYSQL_PWD="${MYSQL_PASSWORD}" mysql --protocol=tcp -h127.0.0.1 \
        -u"${MYSQL_USER}" "$1" --execute="SELECT 1"' sh "${database}" \
      > /dev/null 2>&1; then
      return
    fi
    sleep 1
  done
  echo "隔离 MySQL 未在 120 秒内就绪：${container}" >&2
  return 1
}

start_platform_mysql() {
  local container="$1"
  local volume="$2"
  local database="$3"
  docker_cli volume create "${volume}" > /dev/null
  docker_cli run -d \
    --name "${container}" \
    --memory 2g \
    -e "MYSQL_ROOT_PASSWORD=${MYSQL_ROOT_SECRET}" \
    -e "MYSQL_DATABASE=${database}" \
    -e MYSQL_USER=common_agent \
    -e "MYSQL_PASSWORD=${MYSQL_APP_SECRET}" \
    -p "127.0.0.1:${MYSQL_PORT}:3306" \
    -v "${volume}:/var/lib/mysql" \
    mysql:8.4.10 \
    --disable-log-bin \
    --character-set-server=utf8mb4 \
    --collation-server=utf8mb4_0900_ai_ci \
    --max-connections=300 > /dev/null
  wait_for_mysql "${container}" "${database}"
}

configure_source_ragflow() {
  (
    cd "${BACKEND_ROOT}"
    RAGFLOW_BASE_URL="http://127.0.0.1:${RAGFLOW_API_PORT}" \
    RAGFLOW_TIMEOUT_SECONDS=120 \
      .venv/bin/python -m common_agent.adapters.knowledge.ragflow_models apply
    RAGFLOW_BASE_URL="http://127.0.0.1:${RAGFLOW_API_PORT}" \
    RAGFLOW_TIMEOUT_SECONDS=120 \
    RAGFLOW_TOKEN_FILE="${RAGFLOW_TOKEN_FILE}" \
      .venv/bin/python -m common_agent.adapters.knowledge.ragflow_models ensure-token
  )
}

check_restored_ragflow_token() {
  (
    cd "${BACKEND_ROOT}"
    RAGFLOW_BASE_URL="http://127.0.0.1:${RAGFLOW_API_PORT}" \
    RAGFLOW_TIMEOUT_SECONDS=120 \
    RAGFLOW_TOKEN_FILE="${RAGFLOW_TOKEN_FILE}" \
      .venv/bin/python -m common_agent.adapters.knowledge.ragflow_models check-token
  )
}

load_ragflow_token() {
  if [[ ! -f "${RAGFLOW_TOKEN_FILE}" || -L "${RAGFLOW_TOKEN_FILE}" ]]; then
    echo "隔离 RAGFlow Token 文件不存在或不安全" >&2
    return 1
  fi
  local token
  IFS= read -r token < "${RAGFLOW_TOKEN_FILE}"
  if [[ "${token}" != ragflow-* ]]; then
    echo "隔离 RAGFlow Token 格式无效" >&2
    return 1
  fi
  printf '%s\n' "${token}"
}

start_application() {
  local database="$1"
  local phase="$2"
  local database_url
  local ragflow_token
  database_url="mysql+aiomysql://common_agent:${MYSQL_APP_SECRET}@127.0.0.1:${MYSQL_PORT}/${database}?charset=utf8mb4"
  ragflow_token="$(load_ragflow_token)"
  mkdir -p "${ARTIFACT_ROOT}/${phase}"
  (
    cd "${BACKEND_ROOT}"
    exec env \
      COMMON_AGENT_INTEGRATION_MODE=real \
      COMMON_AGENT_DATABASE_URL="${database_url}" \
      COMMON_AGENT_API_HOST=127.0.0.1 \
      COMMON_AGENT_API_PORT="${API_PORT}" \
      COMMON_AGENT_CORS_ORIGINS="http://127.0.0.1:${FRONTEND_PORT}" \
      COMMON_AGENT_AUTH_BOOTSTRAP_TOKEN="${AUTH_BOOTSTRAP_TOKEN}" \
      RAGFLOW_BASE_URL="http://127.0.0.1:${RAGFLOW_API_PORT}" \
      RAGFLOW_API_KEY="${ragflow_token}" \
      RAGFLOW_EXPECTED_VERSION=v0.26.4 \
      RAGFLOW_TIMEOUT_SECONDS=120 \
      .venv/bin/python -m common_agent
  ) > "${ARTIFACT_ROOT}/${phase}/backend.log" 2>&1 &
  BACKEND_PID=$!
  wait_for_url "http://127.0.0.1:${API_PORT}/api/v1/system/health" "${BACKEND_PID}"
  (
    cd "${BACKEND_ROOT}"
    exec env \
      COMMON_AGENT_INTEGRATION_MODE=real \
      COMMON_AGENT_DATABASE_URL="${database_url}" \
      RAGFLOW_BASE_URL="http://127.0.0.1:${RAGFLOW_API_PORT}" \
      RAGFLOW_API_KEY="${ragflow_token}" \
      RAGFLOW_EXPECTED_VERSION=v0.26.4 \
      RAGFLOW_TIMEOUT_SECONDS=120 \
      .venv/bin/python -m common_agent.worker_main
  ) > "${ARTIFACT_ROOT}/${phase}/worker.log" 2>&1 &
  WORKER_PID=$!
  sleep 1
  if ! kill -0 "${WORKER_PID}" > /dev/null 2>&1; then
    echo "隔离 Worker 在启动后退出" >&2
    return 1
  fi
  (
    cd "${FRONTEND_ROOT}"
    exec ./node_modules/.bin/vite \
      --host 127.0.0.1 --port "${FRONTEND_PORT}" --strictPort
  ) > "${ARTIFACT_ROOT}/${phase}/frontend.log" 2>&1 &
  FRONTEND_PID=$!
  wait_for_url "http://127.0.0.1:${FRONTEND_PORT}/" "${FRONTEND_PID}"
}

stop_pid() {
  local pid="$1"
  [[ -n "${pid}" ]] || return
  if kill -0 "${pid}" > /dev/null 2>&1; then
    kill "${pid}" > /dev/null 2>&1 || true
    wait "${pid}" 2>/dev/null || true
  fi
}

stop_application() {
  stop_pid "${FRONTEND_PID}"
  stop_pid "${WORKER_PID}"
  stop_pid "${BACKEND_PID}"
  FRONTEND_PID=""
  WORKER_PID=""
  BACKEND_PID=""
}

run_browser_phase() {
  local spec="$1"
  local phase="$2"
  (
    cd "${FRONTEND_ROOT}"
    COMMON_AGENT_E2E_API_URL="http://127.0.0.1:${API_PORT}/api/v1" \
    COMMON_AGENT_E2E_FRONTEND_URL="http://127.0.0.1:${FRONTEND_PORT}" \
    COMMON_AGENT_E2E_ARTIFACT_DIR="${ARTIFACT_ROOT}/${phase}/playwright" \
    COMMON_AGENT_E2E_AUTH_BOOTSTRAP_TOKEN="${AUTH_BOOTSTRAP_TOKEN}" \
    COMMON_AGENT_E2E_AUTH_EMAIL="${AUTH_EMAIL}" \
    COMMON_AGENT_E2E_AUTH_PASSWORD="${AUTH_PASSWORD}" \
    COMMON_AGENT_E2E_RECOVERY_KNOWLEDGE_NAME="${KNOWLEDGE_NAME}" \
    COMMON_AGENT_E2E_RECOVERY_EMPLOYEE_NAME="${EMPLOYEE_NAME}" \
    COMMON_AGENT_E2E_RECOVERY_RAGFLOW_PORT="${RAGFLOW_API_PORT}" \
      pnpm exec playwright test "e2e/${spec}" --project=chromium
  )
}

remove_mysql_environment() {
  local container="$1"
  local volume="$2"
  docker_cli rm -f "${container}" > /dev/null 2>&1 || true
  docker_cli volume rm "${volume}" > /dev/null 2>&1 || true
}

remove_ragflow_environment() {
  local instance_id="$1"
  local component
  ragflow_compose "${instance_id}" down --remove-orphans > /dev/null 2>&1 || true
  for component in esdata-v2 mysql-data-v3 minio-data-v2 valkey-data-v2; do
    docker_cli volume rm "$(ragflow_volume "${instance_id}" "${component}")" \
      > /dev/null 2>&1 || true
  done
}

remove_local_tree() {
  local path="$1"
  [[ -n "${path}" && "${path}" == "${REPOSITORY_ROOT}/.local/"* ]] || return 1
  if [[ -d "${path}" ]]; then
    find "${path}" -depth -delete
  fi
}

cleanup() {
  local status=$?
  trap - EXIT INT TERM
  stop_application
  if colima status --profile common-agent-dev > /dev/null 2>&1; then
    remove_ragflow_environment "${SOURCE_ID}"
    remove_ragflow_environment "${RESTORE_ID}"
    remove_mysql_environment "${SOURCE_MYSQL_CONTAINER}" "${SOURCE_MYSQL_VOLUME}"
    remove_mysql_environment "${RESTORE_MYSQL_CONTAINER}" "${RESTORE_MYSQL_VOLUME}"
  fi
  remove_local_tree "${REPOSITORY_ROOT}/.local/recovery/${RESTORE_ID}" || true
  if ((status != 0)); then
    echo "S10-06 灾难演练失败；相关服务日志尾部如下" >&2
    tail -n 40 "${ARTIFACT_ROOT}"/*/*.log 2>/dev/null >&2 || true
  fi
  remove_local_tree "${ARTIFACT_ROOT}" || true
  if ((PROFILE_STARTED == 1)); then
    colima stop common-agent-dev > /dev/null 2>&1 || true
  fi
  exit "${status}"
}

trap cleanup EXIT INT TERM

check_prerequisites
check_ports
mkdir -p "${ARTIFACT_ROOT}/secrets" "${BACKUP_ROOT}"
chmod 0700 "${ARTIFACT_ROOT}" "${ARTIFACT_ROOT}/secrets" "${BACKUP_ROOT}"
ensure_colima
RAGFLOW_NATIVE_BASE_URL="$(
  cd "${BACKEND_ROOT}"
  .venv/bin/python -m common_agent.adapters.knowledge.ragflow_models native-base-url
)"

create_ragflow_volumes "${SOURCE_ID}"
ragflow_compose "${SOURCE_ID}" up -d
wait_for_url "http://127.0.0.1:${RAGFLOW_API_PORT}/api/v1/system/version"
configure_source_ragflow
start_platform_mysql "${SOURCE_MYSQL_CONTAINER}" "${SOURCE_MYSQL_VOLUME}" common_agent
start_application common_agent source
run_browser_phase backup-recovery-seed.spec.ts source
stop_application
ragflow_compose "${SOURCE_ID}" stop

BACKUP_ENCRYPTION_KEY_FILE="${BACKUP_KEY_FILE}" \
  BACKUP_ROOT="${BACKUP_ROOT}" \
  "${SCRIPT_DIR}/manage.sh" init-key > /dev/null
BACKUP_DOCKER_CONTEXT="${DOCKER_CONTEXT_NAME}" \
  BACKUP_ROOT="${BACKUP_ROOT}" \
  BACKUP_ENCRYPTION_KEY_FILE="${BACKUP_KEY_FILE}" \
  BACKUP_PLATFORM_CONTAINER="${SOURCE_MYSQL_CONTAINER}" \
  BACKUP_PLATFORM_DATABASE=common_agent \
  BACKUP_RAGFLOW_CONTAINER_PREFIX="common-agent-recovery-${SOURCE_ID}-ragflow" \
  BACKUP_RAGFLOW_VOLUME_PREFIX="common-agent-recovery-${SOURCE_ID}-ragflow" \
  COMMON_AGENT_API_PORT="${API_PORT}" \
  COMMON_AGENT_WEB_PORT="${FRONTEND_PORT}" \
  RAGFLOW_API_PORT="${RAGFLOW_API_PORT}" \
    "${SCRIPT_DIR}/manage.sh" backup

ARCHIVE_FILE="$(find "${BACKUP_ROOT}" -maxdepth 1 -type f -name 'common-agent-*.cab' -print)"
if [[ -z "${ARCHIVE_FILE}" || "$(printf '%s\n' "${ARCHIVE_FILE}" | wc -l | tr -d ' ')" != "1" ]]; then
  echo "灾难演练没有得到唯一备份归档" >&2
  exit 1
fi

remove_ragflow_environment "${SOURCE_ID}"
remove_mysql_environment "${SOURCE_MYSQL_CONTAINER}" "${SOURCE_MYSQL_VOLUME}"

start_platform_mysql \
  "${RESTORE_MYSQL_CONTAINER}" "${RESTORE_MYSQL_VOLUME}" common_agent_recovery
RESTORE_STARTED=$SECONDS
BACKUP_DOCKER_CONTEXT="${DOCKER_CONTEXT_NAME}" \
  BACKUP_ROOT="${BACKUP_ROOT}" \
  BACKUP_ENCRYPTION_KEY_FILE="${BACKUP_KEY_FILE}" \
  BACKUP_ARCHIVE_FILE="${ARCHIVE_FILE}" \
  BACKUP_RECOVERY_ID="${RESTORE_ID}" \
  BACKUP_RESTORE_CONFIRMATION=restore-to-empty-recovery-environment \
    "${SCRIPT_DIR}/manage.sh" restore

ragflow_compose "${RESTORE_ID}" up -d
wait_for_url "http://127.0.0.1:${RAGFLOW_API_PORT}/api/v1/system/version"
check_restored_ragflow_token
start_application common_agent_recovery restored
run_browser_phase backup-recovery-verify.spec.ts restored

RESTORE_SECONDS=$((SECONDS - RESTORE_STARTED))
if ((RESTORE_SECONDS > 7200)); then
  echo "恢复用时超过 120 分钟 RTO：${RESTORE_SECONDS}s" >&2
  exit 1
fi
REFERENCE_COUNT="$(docker_cli exec "${RESTORE_MYSQL_CONTAINER}" sh -ec \
  'MYSQL_PWD="${MYSQL_ROOT_PASSWORD}" mysql --protocol=socket -N -uroot common_agent_recovery \
    -e "SELECT COUNT(*) FROM ragflow_knowledge_base_ownerships"')"
if [[ ! "${REFERENCE_COUNT}" =~ ^[1-9][0-9]*$ ]]; then
  echo "恢复后的 RAGFlow 外部引用为空" >&2
  exit 1
fi

echo "S10-06 隔离灾难演练通过：恢复 ${RESTORE_SECONDS}s，外部引用 ${REFERENCE_COUNT} 条"
