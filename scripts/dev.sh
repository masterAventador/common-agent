#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BACKEND_ROOT="${REPOSITORY_ROOT}/backend"
FRONTEND_ROOT="${REPOSITORY_ROOT}/frontend"
UV_RUNNER="${SCRIPT_DIR}/uv.sh"
RUNTIME_ROOT="${REPOSITORY_ROOT}/.local/dev/demo-light"
TOKEN_ROOT="${REPOSITORY_ROOT}/.local/dev/common-agent-dev/secrets"
AUTH_BOOTSTRAP_TOKEN_FILE="${TOKEN_ROOT}/owner-bootstrap-token"
LEGACY_RAGFLOW_CHECKOUT="${REPOSITORY_ROOT}/.local/dev/common-agent-dev/ragflow/upstream/v0.25.6"
BACKEND_LOG="${RUNTIME_ROOT}/backend.log"
FRONTEND_LOG="${RUNTIME_ROOT}/frontend.log"
BACKEND_LAUNCH_LABEL="com.masteraventador.common-agent.demo-light.backend"
FRONTEND_LAUNCH_LABEL="com.masteraventador.common-agent.demo-light.frontend"
PROFILE_NAME="common-agent-dev"
DOCKER_CONTEXT_NAME="colima-common-agent-dev"
PNPM_VERSION="11.9.0"
DEMO_MEMORY_GIB=12
DEMO_MIN_MEMORY_GIB=8
DEMO_CPUS=4
DEMO_DISK_GIB=100
API_PORT=18200
FRONTEND_PORT=18280
PLATFORM_MYSQL_PORT=19506
DATABASE_URL="mysql+aiomysql://common_agent:common_agent_dev@127.0.0.1:${PLATFORM_MYSQL_PORT}/common_agent?charset=utf8mb4"

usage() {
  echo "用法: scripts/dev.sh {doctor|setup|up|status|stop|clean}" >&2
}

require_command() {
  local command_name="$1"
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    echo "缺少开发工具：${command_name}" >&2
    return 1
  fi
}

require_tools() {
  local command_name
  for command_name in git uv node npm npx docker colima curl lsof launchctl openssl stat; do
    require_command "${command_name}"
  done
}

run_pnpm() {
  npx --yes "pnpm@${PNPM_VERSION}" "$@"
}

load_auth_bootstrap_token() {
  local auth_bootstrap_token file_mode
  if [[ -L "${AUTH_BOOTSTRAP_TOKEN_FILE}" ]]; then
    echo "首位管理员引导凭据文件不能是符号链接：${AUTH_BOOTSTRAP_TOKEN_FILE}" >&2
    return 1
  fi
  if [[ ! -f "${AUTH_BOOTSTRAP_TOKEN_FILE}" ]]; then
    mkdir -p "${TOKEN_ROOT}"
    chmod 700 "${TOKEN_ROOT}"
    (umask 077; openssl rand -hex 32 >"${AUTH_BOOTSTRAP_TOKEN_FILE}")
  fi
  file_mode="$(stat -f '%Lp' "${AUTH_BOOTSTRAP_TOKEN_FILE}")"
  if [[ "${file_mode}" != "600" ]]; then
    echo "首位管理员引导凭据文件权限必须是 0600：${AUTH_BOOTSTRAP_TOKEN_FILE}" >&2
    return 1
  fi
  IFS= read -r auth_bootstrap_token <"${AUTH_BOOTSTRAP_TOKEN_FILE}"
  if ((${#auth_bootstrap_token} < 32 || ${#auth_bootstrap_token} > 256)); then
    echo "首位管理员引导凭据必须是 32-256 字符：${AUTH_BOOTSTRAP_TOKEN_FILE}" >&2
    return 1
  fi
  printf '%s\n' "${auth_bootstrap_token}"
}

validate_tool_versions() {
  local node_major pnpm_version
  node_major="$(node --version | sed -E 's/^v([0-9]+).*/\1/')"
  if [[ ! "${node_major}" =~ ^[0-9]+$ ]] || ((node_major < 22)); then
    echo "Node.js 必须为 22 或更高版本" >&2
    return 1
  fi
  pnpm_version="$(run_pnpm --version)"
  if [[ "${pnpm_version}" != "${PNPM_VERSION}" ]]; then
    echo "无法使用项目锁定的 pnpm ${PNPM_VERSION}" >&2
    return 1
  fi
}

submodule_ready() {
  [[ -e "${REPOSITORY_ROOT}/third_party/ragflow/.git" ]] &&
    [[ "$(git -C "${REPOSITORY_ROOT}/third_party/ragflow" rev-parse HEAD 2>/dev/null)" == \
      "$(tr -d '[:space:]' < "${REPOSITORY_ROOT}/infra/ragflow/UPSTREAM_COMMIT")" ]]
}

profile_running() {
  colima status --profile "${PROFILE_NAME}" >/dev/null 2>&1
}

docker_memory_bytes() {
  docker --context "${DOCKER_CONTEXT_NAME}" info --format '{{.MemTotal}}'
}

memory_is_demo_light() {
  local total_bytes="$1"
  local minimum_bytes maximum_bytes
  [[ "${total_bytes}" =~ ^[0-9]+$ ]] || return 1
  minimum_bytes=$((DEMO_MIN_MEMORY_GIB * 1024 * 1024 * 1024))
  maximum_bytes=$((DEMO_MEMORY_GIB * 1024 * 1024 * 1024))
  ((total_bytes >= minimum_bytes && total_bytes <= maximum_bytes))
}

launch_job_running() {
  launchctl list "$1" >/dev/null 2>&1
}

remove_launch_job() {
  local label="$1"
  if launch_job_running "${label}"; then
    launchctl remove "${label}"
  fi
}

port_is_free() {
  ! lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
}

wait_for_url() {
  local url="$1"
  local timeout_seconds="${2:-60}"
  local deadline=$((SECONDS + timeout_seconds))
  while ((SECONDS < deadline)); do
    if curl --fail --silent --show-error "${url}" >/dev/null 2>&1; then
      return
    fi
    sleep 1
  done
  echo "服务未在 ${timeout_seconds} 秒内就绪：${url}" >&2
  return 1
}

doctor() {
  require_tools
  validate_tool_versions
  [[ -f "${BACKEND_ROOT}/uv.lock" ]] || {
    echo "缺少 backend/uv.lock" >&2
    return 1
  }
  [[ -f "${FRONTEND_ROOT}/pnpm-lock.yaml" ]] || {
    echo "缺少 frontend/pnpm-lock.yaml" >&2
    return 1
  }
  if ! submodule_ready; then
    echo "RAGFlow submodule 未初始化或版本漂移；执行 scripts/dev.sh setup" >&2
    return 1
  fi

  echo "工具链：ready"
  echo "冻结依赖：backend/uv.lock + frontend/pnpm-lock.yaml"
  echo "RAGFlow submodule：ready"
  if profile_running; then
    local total_bytes
    total_bytes="$(docker_memory_bytes)"
    if memory_is_demo_light "${total_bytes}"; then
      echo "Colima demo-light：ready (${total_bytes} bytes)"
    else
      echo "Colima 当前不是 8-12 GiB demo-light；scripts/dev.sh up 会停止本项目 real 栈并调整为 12 GiB"
    fi
  else
    echo "Colima：stopped；scripts/dev.sh up 会启动 12 GiB demo-light"
  fi
}

setup() {
  require_tools
  validate_tool_versions
  git -C "${REPOSITORY_ROOT}" submodule update --init --recursive third_party/ragflow
  (
    cd "${BACKEND_ROOT}"
    "${UV_RUNNER}" sync --frozen
  )
  (
    cd "${FRONTEND_ROOT}"
    run_pnpm install --frozen-lockfile
  )
  doctor
}

stop_ragflow_if_running() {
  if ! profile_running; then
    return
  fi
  if [[ -n "$(docker --context "${DOCKER_CONTEXT_NAME}" ps -q \
    --filter name=common-agent-ragflow 2>/dev/null)" ]]; then
    "${REPOSITORY_ROOT}/infra/ragflow/manage.sh" stop
  fi
}

stop_platform_if_running() {
  if ! profile_running; then
    return
  fi
  if [[ -n "$(docker --context "${DOCKER_CONTEXT_NAME}" ps -aq \
    --filter name=common-agent-platform-mysql 2>/dev/null)" ]]; then
    PLATFORM_DOCKER_CONTEXT="${DOCKER_CONTEXT_NAME}" \
      "${REPOSITORY_ROOT}/infra/platform/manage.sh" stop
  fi
}

down_platform_if_running() {
  if ! profile_running; then
    return
  fi
  if [[ -n "$(docker --context "${DOCKER_CONTEXT_NAME}" ps -aq \
    --filter name=common-agent-platform-mysql 2>/dev/null)" ]]; then
    PLATFORM_DOCKER_CONTEXT="${DOCKER_CONTEXT_NAME}" \
      "${REPOSITORY_ROOT}/infra/platform/manage.sh" down
  fi
}

ensure_demo_profile() {
  local total_bytes=""
  stop_ragflow_if_running
  if profile_running; then
    total_bytes="$(docker_memory_bytes)"
  fi
  if [[ -n "${total_bytes}" ]] && memory_is_demo_light "${total_bytes}"; then
    return
  fi

  if profile_running; then
    stop_platform_if_running
    colima stop "${PROFILE_NAME}"
  fi
  colima start "${PROFILE_NAME}" \
    --cpus "${DEMO_CPUS}" \
    --memory "${DEMO_MEMORY_GIB}" \
    --disk "${DEMO_DISK_GIB}" \
    --root-disk 20 \
    --runtime docker \
    --vm-type vz \
    --vz-rosetta \
    --activate=false

  total_bytes="$(docker_memory_bytes)"
  if ! memory_is_demo_light "${total_bytes}"; then
    echo "Colima demo-light 内存不在 ${DEMO_MIN_MEMORY_GIB}-${DEMO_MEMORY_GIB} GiB 范围：${total_bytes} bytes" >&2
    return 1
  fi
}

ensure_platform_mysql() {
  PLATFORM_DOCKER_CONTEXT="${DOCKER_CONTEXT_NAME}" \
    "${REPOSITORY_ROOT}/infra/platform/manage.sh" up
}

start_backend() {
  if launch_job_running "${BACKEND_LAUNCH_LABEL}" && \
    curl --fail --silent --show-error \
      "http://127.0.0.1:${API_PORT}/api/v1/system/health" >/dev/null 2>&1; then
    return
  fi
  remove_launch_job "${BACKEND_LAUNCH_LABEL}"
  if ! port_is_free "${API_PORT}"; then
    echo "FastAPI 端口被非本入口进程占用：127.0.0.1:${API_PORT}" >&2
    return 1
  fi

  rm -f "${BACKEND_LOG}"
  launchctl submit \
    -l "${BACKEND_LAUNCH_LABEL}" \
    -o "${BACKEND_LOG}" \
    -e "${BACKEND_LOG}" \
    -- /usr/bin/env "PATH=${PATH}" "${SCRIPT_DIR}/dev.sh" _serve-backend
  if ! wait_for_url "http://127.0.0.1:${API_PORT}/api/v1/system/health"; then
    echo "FastAPI 启动失败，日志：${BACKEND_LOG}" >&2
    remove_launch_job "${BACKEND_LAUNCH_LABEL}"
    return 1
  fi
}

start_frontend() {
  if launch_job_running "${FRONTEND_LAUNCH_LABEL}" && \
    curl --fail --silent --show-error \
      "http://127.0.0.1:${FRONTEND_PORT}/" >/dev/null 2>&1; then
    return
  fi
  remove_launch_job "${FRONTEND_LAUNCH_LABEL}"
  if ! port_is_free "${FRONTEND_PORT}"; then
    echo "Vite 端口被非本入口进程占用：127.0.0.1:${FRONTEND_PORT}" >&2
    return 1
  fi

  rm -f "${FRONTEND_LOG}"
  launchctl submit \
    -l "${FRONTEND_LAUNCH_LABEL}" \
    -o "${FRONTEND_LOG}" \
    -e "${FRONTEND_LOG}" \
    -- /usr/bin/env "PATH=${PATH}" "${SCRIPT_DIR}/dev.sh" _serve-frontend
  if ! wait_for_url "http://127.0.0.1:${FRONTEND_PORT}/"; then
    echo "Vite 启动失败，日志：${FRONTEND_LOG}" >&2
    remove_launch_job "${FRONTEND_LAUNCH_LABEL}"
    return 1
  fi
}

serve_backend() {
  local auth_bootstrap_token
  auth_bootstrap_token="$(load_auth_bootstrap_token)"
  cd "${BACKEND_ROOT}"
  exec env \
    COMMON_AGENT_INTEGRATION_MODE=demo \
    COMMON_AGENT_DATABASE_URL="${DATABASE_URL}" \
    COMMON_AGENT_API_HOST=127.0.0.1 \
    COMMON_AGENT_API_PORT="${API_PORT}" \
    COMMON_AGENT_CORS_ORIGINS="http://127.0.0.1:${FRONTEND_PORT}" \
    COMMON_AGENT_AUTH_BOOTSTRAP_TOKEN="${auth_bootstrap_token}" \
    .venv/bin/python -m common_agent
}

serve_frontend() {
  cd "${FRONTEND_ROOT}"
  exec ./node_modules/.bin/vite \
    --host 127.0.0.1 --port "${FRONTEND_PORT}" --strictPort
}

up() {
  mkdir -p "${RUNTIME_ROOT}"
  setup
  ensure_demo_profile
  ensure_platform_mysql
  if ! start_backend; then
    remove_launch_job "${BACKEND_LAUNCH_LABEL}"
    return 1
  fi
  if ! start_frontend; then
    remove_launch_job "${FRONTEND_LAUNCH_LABEL}"
    remove_launch_job "${BACKEND_LAUNCH_LABEL}"
    return 1
  fi
  echo "demo-light 已启动"
  echo "前端：http://127.0.0.1:${FRONTEND_PORT}"
  echo "后端：http://127.0.0.1:${API_PORT}/api/v1"
  echo "首次所有者引导凭据文件：${AUTH_BOOTSTRAP_TOKEN_FILE}"
}

status() {
  local failed=0 total_bytes=""
  if profile_running; then
    total_bytes="$(docker_memory_bytes)"
    if memory_is_demo_light "${total_bytes}"; then
      echo "Colima demo-light：running (${total_bytes} bytes)"
    else
      echo "Colima demo-light：wrong-memory (${total_bytes} bytes)"
      failed=1
    fi
    if [[ "$(docker --context "${DOCKER_CONTEXT_NAME}" inspect \
      --format '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' \
      common-agent-platform-mysql 2>/dev/null || true)" == "running healthy" ]]; then
      echo "平台 MySQL：healthy"
    else
      echo "平台 MySQL：stopped/unhealthy"
      failed=1
    fi
  else
    echo "Colima demo-light：stopped"
    echo "平台 MySQL：stopped"
    failed=1
  fi

  if launch_job_running "${BACKEND_LAUNCH_LABEL}" && \
    curl --fail --silent --show-error \
      "http://127.0.0.1:${API_PORT}/api/v1/system/health" >/dev/null 2>&1; then
    echo "FastAPI：healthy (http://127.0.0.1:${API_PORT}/api/v1)"
  else
    echo "FastAPI：stopped/unhealthy"
    failed=1
  fi
  if launch_job_running "${FRONTEND_LAUNCH_LABEL}" && \
    curl --fail --silent --show-error \
      "http://127.0.0.1:${FRONTEND_PORT}/" >/dev/null 2>&1; then
    echo "Vite：healthy (http://127.0.0.1:${FRONTEND_PORT})"
  else
    echo "Vite：stopped/unhealthy"
    failed=1
  fi
  return "${failed}"
}

stop() {
  remove_launch_job "${FRONTEND_LAUNCH_LABEL}"
  remove_launch_job "${BACKEND_LAUNCH_LABEL}"
  down_platform_if_running
  if profile_running; then
    colima stop "${PROFILE_NAME}"
  fi
  echo "demo-light 已停止"
}

clean() {
  local legacy_origin=""
  remove_launch_job "${FRONTEND_LAUNCH_LABEL}"
  remove_launch_job "${BACKEND_LAUNCH_LABEL}"
  if profile_running; then
    down_platform_if_running
    colima stop "${PROFILE_NAME}"
  fi
  case "${RUNTIME_ROOT}" in
    "${REPOSITORY_ROOT}/.local/dev/demo-light") rm -rf "${RUNTIME_ROOT}" ;;
    *)
      echo "拒绝清理非 demo-light 运行目录：${RUNTIME_ROOT}" >&2
      return 1
      ;;
  esac
  if [[ -d "${LEGACY_RAGFLOW_CHECKOUT}" ]]; then
    legacy_origin="$(git -C "${LEGACY_RAGFLOW_CHECKOUT}" remote get-url origin 2>/dev/null || true)"
    case "${legacy_origin}" in
      https://github.com/infiniflow/ragflow.git | git@github.com:infiniflow/ragflow.git)
        rm -rf "${LEGACY_RAGFLOW_CHECKOUT}"
        ;;
      *)
        echo "拒绝删除无法确认来源的旧 RAGFlow checkout：${LEGACY_RAGFLOW_CHECKOUT}" >&2
        return 1
        ;;
    esac
  fi
  echo "demo-light 运行进程、容器、日志和已被 submodule 取代的旧 RAGFlow checkout 已清理"
  echo "MySQL/RAGFlow 数据、冻结依赖和官方镜像保留"
}

case "${1:-}" in
  _serve-backend) serve_backend ;;
  _serve-frontend) serve_frontend ;;
  doctor) doctor ;;
  setup) setup ;;
  up) up ;;
  status) status ;;
  stop) stop ;;
  clean) clean ;;
  *) usage; exit 2 ;;
esac
