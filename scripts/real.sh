#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BACKEND_ROOT="${REPOSITORY_ROOT}/backend"
FRONTEND_ROOT="${REPOSITORY_ROOT}/frontend"
RUNTIME_ROOT="${REPOSITORY_ROOT}/.local/dev/real"
TOKEN_ROOT="${REPOSITORY_ROOT}/.local/dev/common-agent-dev/secrets"
RAGFLOW_TOKEN_FILE="${TOKEN_ROOT}/ragflow-api-token"
BACKEND_LOG="${RUNTIME_ROOT}/backend.log"
FRONTEND_LOG="${RUNTIME_ROOT}/frontend.log"
BACKEND_LAUNCH_LABEL="com.masteraventador.common-agent.real.backend"
FRONTEND_LAUNCH_LABEL="com.masteraventador.common-agent.real.frontend"
DEMO_BACKEND_LAUNCH_LABEL="com.masteraventador.common-agent.demo-light.backend"
DEMO_FRONTEND_LAUNCH_LABEL="com.masteraventador.common-agent.demo-light.frontend"
PROFILE_NAME="common-agent-dev"
DOCKER_CONTEXT_NAME="colima-common-agent-dev"
PNPM_VERSION="11.9.0"
REAL_MEMORY_GIB=32
REAL_MIN_MEMORY_GIB=24
REAL_CPUS=8
REAL_DISK_GIB=100
REAL_MIN_FREE_DISK_GIB=20
API_PORT=18200
FRONTEND_PORT=18280
PLATFORM_MYSQL_PORT=19506
RAGFLOW_API_PORT=19380
DATABASE_URL="mysql+aiomysql://common_agent:common_agent_dev@127.0.0.1:${PLATFORM_MYSQL_PORT}/common_agent?charset=utf8mb4"
BACKEND_PYTHON="${BACKEND_ROOT}/.venv/bin/python"
RAGFLOW_MANAGER="${REPOSITORY_ROOT}/infra/ragflow/manage.sh"
PLATFORM_MANAGER="${REPOSITORY_ROOT}/infra/platform/manage.sh"
RAGFLOW_CONTAINERS=(
  common-agent-ragflow-api
  common-agent-ragflow-elasticsearch
  common-agent-ragflow-mysql
  common-agent-ragflow-minio
  common-agent-ragflow-valkey
)

usage() {
  echo "用法: scripts/real.sh {doctor|setup|up|status|cost|stop}" >&2
}

require_command() {
  local command_name="$1"
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    echo "缺少 real 开发工具：${command_name}" >&2
    return 1
  fi
}

require_tools() {
  local command_name
  for command_name in git uv node npm npx docker colima curl lsof launchctl df awk; do
    require_command "${command_name}"
  done
}

run_pnpm() {
  npx --yes "pnpm@${PNPM_VERSION}" "$@"
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

profile_running() {
  colima status --profile "${PROFILE_NAME}" >/dev/null 2>&1
}

docker_memory_bytes() {
  docker --context "${DOCKER_CONTEXT_NAME}" info --format '{{.MemTotal}}'
}

memory_is_real() {
  local total_bytes="$1"
  local minimum_bytes maximum_bytes
  [[ "${total_bytes}" =~ ^[0-9]+$ ]] || return 1
  minimum_bytes=$((REAL_MIN_MEMORY_GIB * 1024 * 1024 * 1024))
  maximum_bytes=$((REAL_MEMORY_GIB * 1024 * 1024 * 1024))
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

stop_application_jobs() {
  remove_launch_job "${FRONTEND_LAUNCH_LABEL}"
  remove_launch_job "${BACKEND_LAUNCH_LABEL}"
  remove_launch_job "${DEMO_FRONTEND_LAUNCH_LABEL}"
  remove_launch_job "${DEMO_BACKEND_LAUNCH_LABEL}"
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

backend_is_real() {
  local payload
  if ! payload="$(curl --fail --silent --show-error \
    "http://127.0.0.1:${API_PORT}/api/v1/system/health" 2>/dev/null)"; then
    return 1
  fi
  [[ "${payload}" == *'"integration_mode":"real"'* ]]
}

project_container_owns_port() {
  local port="$1"
  if ! profile_running; then
    return 1
  fi
  docker --context "${DOCKER_CONTEXT_NAME}" ps \
    --filter name=common-agent \
    --format '{{.Ports}}' 2>/dev/null | grep -Fq "127.0.0.1:${port}->"
}

check_port() {
  local port="$1"
  local owner="$2"
  if ! lsof -nP -iTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1; then
    return
  fi
  case "${owner}" in
    backend) launch_job_running "${BACKEND_LAUNCH_LABEL}" && return ;;
    frontend) launch_job_running "${FRONTEND_LAUNCH_LABEL}" && return ;;
    container) project_container_owns_port "${port}" && return ;;
  esac
  echo "real 端口被非本项目服务占用：127.0.0.1:${port}" >&2
  return 1
}

check_ports() {
  local failed=0 port
  check_port "${API_PORT}" backend || failed=1
  check_port "${FRONTEND_PORT}" frontend || failed=1
  check_port "${PLATFORM_MYSQL_PORT}" container || failed=1
  for port in 19200 19379 19380 19381 19382 19383 19384 19385 19387 19432 19900 19901; do
    check_port "${port}" container || failed=1
  done
  if ((failed != 0)); then
    return 1
  fi
  echo "端口：ready（全部为 loopback 或本项目稳定栈占用）"
}

check_disk() {
  local available_kib required_kib available_gib
  available_kib="$(LC_ALL=C df -Pk "${REPOSITORY_ROOT}" | awk 'NR == 2 {print $4}')"
  if [[ ! "${available_kib}" =~ ^[0-9]+$ ]]; then
    echo "无法读取项目磁盘可用空间" >&2
    return 1
  fi
  required_kib=$((REAL_MIN_FREE_DISK_GIB * 1024 * 1024))
  available_gib=$((available_kib / 1024 / 1024))
  if ((available_kib < required_kib)); then
    echo "real 磁盘空间不足：可用 ${available_gib} GiB，至少需要 ${REAL_MIN_FREE_DISK_GIB} GiB" >&2
    return 1
  fi
  echo "磁盘：ready（可用 ${available_gib} GiB，Colima 上限 ${REAL_DISK_GIB} GiB）"
}

diagnose_bailian() {
  if [[ ! -x "${BACKEND_PYTHON}" ]]; then
    echo "缺少后端冻结环境；执行 scripts/real.sh setup" >&2
    return 1
  fi
  "${BACKEND_PYTHON}" -m common_agent.adapters.knowledge.ragflow_models diagnose
}

ragflow_reachable() {
  curl --fail --silent --show-error \
    "http://127.0.0.1:${RAGFLOW_API_PORT}/api/v1/system/version" >/dev/null 2>&1
}

ensure_ragflow_token() {
  mkdir -p "${TOKEN_ROOT}"
  chmod 700 "${TOKEN_ROOT}"
  RAGFLOW_TOKEN_FILE="${RAGFLOW_TOKEN_FILE}" \
    "${BACKEND_PYTHON}" -m common_agent.adapters.knowledge.ragflow_models ensure-token
}

configure_bailian_with_retry() {
  local deadline=$((SECONDS + 60)) output=""
  while ((SECONDS < deadline)); do
    if output="$("${RAGFLOW_MANAGER}" configure-bailian 2>&1)"; then
      echo "${output}"
      "${RAGFLOW_MANAGER}" check-bailian
      return
    fi
    sleep 2
  done
  echo "RAGFlow 已通过容器健康检查，但百炼模型配置未在 60 秒内就绪" >&2
  echo "${output}" >&2
  return 1
}

check_ragflow_token() {
  RAGFLOW_TOKEN_FILE="${RAGFLOW_TOKEN_FILE}" \
    "${BACKEND_PYTHON}" -m common_agent.adapters.knowledge.ragflow_models check-token
}

doctor() {
  local failed=0 total_bytes
  require_tools || failed=1
  validate_tool_versions || failed=1
  [[ -f "${BACKEND_ROOT}/uv.lock" ]] || {
    echo "缺少 backend/uv.lock" >&2
    failed=1
  }
  [[ -f "${FRONTEND_ROOT}/pnpm-lock.yaml" ]] || {
    echo "缺少 frontend/pnpm-lock.yaml" >&2
    failed=1
  }
  if ! "${RAGFLOW_MANAGER}" prepare; then
    failed=1
  else
    echo "RAGFlow 官方源码：ready（固定 tag/commit、工作区未修改）"
  fi
  diagnose_bailian || failed=1
  check_disk || failed=1
  check_ports || failed=1

  if profile_running; then
    total_bytes="$(docker_memory_bytes)"
    if memory_is_real "${total_bytes}"; then
      echo "Colima real：ready (${total_bytes} bytes)"
    else
      echo "Colima 当前不是 ${REAL_MIN_MEMORY_GIB}-${REAL_MEMORY_GIB} GiB real；up 会先停止本项目栈并调整为 ${REAL_MEMORY_GIB} GiB"
    fi
    if ragflow_reachable; then
      "${RAGFLOW_MANAGER}" check-bailian || failed=1
      if [[ -f "${RAGFLOW_TOKEN_FILE}" ]]; then
        check_ragflow_token || failed=1
      else
        echo "RAGFlow API Token：missing；up 会创建权限 0600 的本地文件"
      fi
    else
      echo "RAGFlow：stopped；模型绑定与 Token 在线检查延后到 up"
    fi
  else
    echo "Colima real：stopped；up 会按需启动暂定 ${REAL_MEMORY_GIB} GiB profile"
    echo "MySQL/RAGFlow：stopped；稳定数据、容器和镜像可复用"
  fi
  echo "本地模型：absent（real 不启动本地 embedding/rerank）"
  return "${failed}"
}

setup() {
  require_tools
  validate_tool_versions
  git -C "${REPOSITORY_ROOT}" submodule update --init --recursive third_party/ragflow
  (
    cd "${BACKEND_ROOT}"
    uv sync --frozen
  )
  (
    cd "${FRONTEND_ROOT}"
    run_pnpm install --frozen-lockfile
  )
  "${RAGFLOW_MANAGER}" prepare
  diagnose_bailian
  check_disk
}

ragflow_stack_exists() {
  [[ -n "$(docker --context "${DOCKER_CONTEXT_NAME}" ps -aq \
    --filter name=common-agent-ragflow 2>/dev/null)" ]]
}

platform_stack_exists() {
  [[ -n "$(docker --context "${DOCKER_CONTEXT_NAME}" ps -aq \
    --filter name=common-agent-platform-mysql 2>/dev/null)" ]]
}

stop_infrastructure_if_running() {
  if ! profile_running; then
    return
  fi
  if ragflow_stack_exists; then
    "${RAGFLOW_MANAGER}" stop
  fi
  if platform_stack_exists; then
    PLATFORM_DOCKER_CONTEXT="${DOCKER_CONTEXT_NAME}" "${PLATFORM_MANAGER}" stop
  fi
}

ensure_real_profile() {
  local total_bytes=""
  stop_application_jobs
  if profile_running; then
    total_bytes="$(docker_memory_bytes)"
    if memory_is_real "${total_bytes}"; then
      echo "复用 ${REAL_MEMORY_GIB} GiB 项目专属 Colima profile"
      return
    fi
    stop_infrastructure_if_running
    colima stop "${PROFILE_NAME}"
  fi

  colima start "${PROFILE_NAME}" \
    --cpus "${REAL_CPUS}" \
    --memory "${REAL_MEMORY_GIB}" \
    --disk "${REAL_DISK_GIB}" \
    --root-disk 20 \
    --runtime docker \
    --vm-type vz \
    --vz-rosetta \
    --activate=false

  total_bytes="$(docker_memory_bytes)"
  if ! memory_is_real "${total_bytes}"; then
    echo "Colima real 内存不在 ${REAL_MIN_MEMORY_GIB}-${REAL_MEMORY_GIB} GiB 范围：${total_bytes} bytes" >&2
    return 1
  fi
}

ensure_infrastructure() {
  PLATFORM_DOCKER_CONTEXT="${DOCKER_CONTEXT_NAME}" "${PLATFORM_MANAGER}" up
  "${RAGFLOW_MANAGER}" pull-image
  "${RAGFLOW_MANAGER}" migrate-native-volumes
  "${RAGFLOW_MANAGER}" up
  configure_bailian_with_retry
  ensure_ragflow_token
  check_ragflow_token
}

start_backend() {
  if launch_job_running "${BACKEND_LAUNCH_LABEL}" && backend_is_real; then
    return
  fi
  remove_launch_job "${BACKEND_LAUNCH_LABEL}"
  check_port "${API_PORT}" backend
  rm -f "${BACKEND_LOG}"
  launchctl submit \
    -l "${BACKEND_LAUNCH_LABEL}" \
    -o "${BACKEND_LOG}" \
    -e "${BACKEND_LOG}" \
    -- /usr/bin/env "PATH=${PATH}" "${SCRIPT_DIR}/real.sh" _serve-backend
  if ! wait_for_url "http://127.0.0.1:${API_PORT}/api/v1/system/health"; then
    echo "FastAPI real 启动失败，日志：${BACKEND_LOG}" >&2
    remove_launch_job "${BACKEND_LAUNCH_LABEL}"
    return 1
  fi
  if ! backend_is_real; then
    echo "FastAPI 启动后未报告 real 模式" >&2
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
  check_port "${FRONTEND_PORT}" frontend
  rm -f "${FRONTEND_LOG}"
  launchctl submit \
    -l "${FRONTEND_LAUNCH_LABEL}" \
    -o "${FRONTEND_LOG}" \
    -e "${FRONTEND_LOG}" \
    -- /usr/bin/env "PATH=${PATH}" "${SCRIPT_DIR}/real.sh" _serve-frontend
  if ! wait_for_url "http://127.0.0.1:${FRONTEND_PORT}/"; then
    echo "Vite real 启动失败，日志：${FRONTEND_LOG}" >&2
    remove_launch_job "${FRONTEND_LAUNCH_LABEL}"
    return 1
  fi
}

serve_backend() {
  local ragflow_api_key
  if [[ ! -f "${RAGFLOW_TOKEN_FILE}" || -L "${RAGFLOW_TOKEN_FILE}" ]]; then
    echo "RAGFlow Token 文件不存在或不安全" >&2
    return 1
  fi
  IFS= read -r ragflow_api_key <"${RAGFLOW_TOKEN_FILE}"
  if [[ "${ragflow_api_key}" != ragflow-* ]]; then
    echo "RAGFlow Token 文件无效" >&2
    return 1
  fi
  cd "${BACKEND_ROOT}"
  exec env \
    COMMON_AGENT_INTEGRATION_MODE=real \
    COMMON_AGENT_DATABASE_URL="${DATABASE_URL}" \
    COMMON_AGENT_API_HOST=127.0.0.1 \
    COMMON_AGENT_API_PORT="${API_PORT}" \
    COMMON_AGENT_CORS_ORIGINS="http://127.0.0.1:${FRONTEND_PORT}" \
    RAGFLOW_BASE_URL="http://127.0.0.1:${RAGFLOW_API_PORT}" \
    RAGFLOW_API_KEY="${ragflow_api_key}" \
    RAGFLOW_EXPECTED_VERSION=v0.25.6 \
    RAGFLOW_TIMEOUT_SECONDS=120 \
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
  ensure_real_profile
  check_ports
  ensure_infrastructure
  if ! start_backend; then
    remove_launch_job "${BACKEND_LAUNCH_LABEL}"
    return 1
  fi
  if ! start_frontend; then
    remove_launch_job "${FRONTEND_LAUNCH_LABEL}"
    remove_launch_job "${BACKEND_LAUNCH_LABEL}"
    return 1
  fi
  echo "real 已启动（不启动本地 embedding/rerank）"
  echo "前端：http://127.0.0.1:${FRONTEND_PORT}"
  echo "后端：http://127.0.0.1:${API_PORT}/api/v1"
  echo "RAGFlow：http://127.0.0.1:19381"
}

inspect_ragflow_container() {
  local container_name="$1"
  local state
  state="$(docker --context "${DOCKER_CONTEXT_NAME}" inspect \
    --format '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}} restarts={{.RestartCount}} oom={{.State.OOMKilled}}' \
    "${container_name}" 2>/dev/null || true)"
  if [[ "${state}" == running\ healthy\ * || "${state}" == running\ none\ * ]]; then
    echo "${container_name}：${state}"
    return
  fi
  echo "${container_name}：stopped/unhealthy (${state:-missing})" >&2
  return 1
}

status() {
  local failed=0 total_bytes container_name payload
  if ! profile_running; then
    echo "Colima real：stopped"
    return 1
  fi
  total_bytes="$(docker_memory_bytes)"
  if memory_is_real "${total_bytes}"; then
    echo "Colima real：running (${total_bytes} bytes)"
  else
    echo "Colima real：wrong-memory (${total_bytes} bytes)"
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
  for container_name in "${RAGFLOW_CONTAINERS[@]}"; do
    inspect_ragflow_container "${container_name}" || failed=1
  done
  if ragflow_reachable; then
    "${RAGFLOW_MANAGER}" prepare || failed=1
    "${RAGFLOW_MANAGER}" check-bailian || failed=1
    check_ragflow_token || failed=1
  else
    echo "RAGFlow API：stopped/unhealthy"
    failed=1
  fi
  if launch_job_running "${BACKEND_LAUNCH_LABEL}" && backend_is_real; then
    payload="$(curl --fail --silent --show-error \
      "http://127.0.0.1:${API_PORT}/api/v1/system/status" 2>/dev/null || true)"
    if [[ "${payload}" == *'"integration_mode":"real"'* && \
      "${payload}" == *'"availability":"available"'* ]]; then
      echo "FastAPI：healthy/real，RAGFlow available"
    else
      echo "FastAPI：real 依赖状态异常"
      failed=1
    fi
  else
    echo "FastAPI：stopped/unhealthy/not-real"
    failed=1
  fi
  if launch_job_running "${FRONTEND_LAUNCH_LABEL}" && \
    curl --fail --silent --show-error \
      "http://127.0.0.1:${FRONTEND_PORT}/" >/dev/null 2>&1; then
    echo "Vite：healthy"
  else
    echo "Vite：stopped/unhealthy"
    failed=1
  fi
  check_disk || failed=1
  return "${failed}"
}

cost() {
  local failed=0
  diagnose_bailian || failed=1
  echo "费用边界：聊天、文档 embedding、检索 rerank 均调用百炼业务空间并按账号实时计费"
  echo "重试边界：平台聊天最多重试配置值；RAGFlow 解析/检索遇限流、超时或上游失败返回可恢复错误"
  echo "价格边界：金额以执行时百炼控制台单价与账单为准，本地不缓存易漂移价格"
  echo "数据边界：知识文档片段和检索查询会发送到配置的百炼区域；不启动本地 embedding/rerank"
  if profile_running && ragflow_reachable; then
    "${RAGFLOW_MANAGER}" check-bailian || failed=1
    "${RAGFLOW_MANAGER}" plan-bailian-migration || failed=1
    docker --context "${DOCKER_CONTEXT_NAME}" stats --no-stream \
      --format '{{.Name}}: {{.MemUsage}}' \
      "${RAGFLOW_CONTAINERS[@]}" common-agent-platform-mysql || failed=1
  else
    echo "当前稳定栈未运行：知识库/文档数量与容器内存诊断延后到 up 后执行"
  fi
  return "${failed}"
}

stop() {
  stop_application_jobs
  if profile_running; then
    stop_infrastructure_if_running
    colima stop "${PROFILE_NAME}"
  fi
  echo "real 已停止；稳定容器、数据、0600 Token 文件与官方镜像保留"
}

case "${1:-}" in
  _serve-backend) serve_backend ;;
  _serve-frontend) serve_frontend ;;
  doctor) doctor ;;
  setup) setup ;;
  up) up ;;
  status) status ;;
  cost) cost ;;
  stop) stop ;;
  *) usage; exit 2 ;;
esac
