#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BACKEND_ROOT="${REPOSITORY_ROOT}/backend"
FRONTEND_ROOT="${REPOSITORY_ROOT}/frontend"
REAL_MANAGER="${SCRIPT_DIR}/real.sh"
MONITOR="${SCRIPT_DIR}/real-resource-monitor.py"
UV_RUNNER="${SCRIPT_DIR}/uv.sh"
PROFILE_NAME="common-agent-dev"
SOAK_SECONDS="${COMMON_AGENT_RESOURCE_SOAK_SECONDS:-1800}"
RUN_ID="$(date -u +%Y%m%d%H%M%S)-$$"
REPORT_ROOT="${REPOSITORY_ROOT}/.local/soak/r8-04/${RUN_ID}"
TOKEN_FILE="${REPOSITORY_ROOT}/.local/dev/common-agent-dev/secrets/ragflow-api-token"
AUTH_BOOTSTRAP_TOKEN_FILE="${REPOSITORY_ROOT}/.local/dev/common-agent-dev/secrets/owner-bootstrap-token"
DATABASE_URL="mysql+aiomysql://common_agent:common_agent_dev@127.0.0.1:19506/common_agent_test?charset=utf8mb4"
RAGFLOW_BASE_URL="http://127.0.0.1:19380"
RAGFLOW_EXPECTED_VERSION="v0.26.4"
AUTH_EMAIL="common-agent-resource-soak@example.com"
AUTH_PASSWORD="common agent resource soak password"
MVP_KNOWLEDGE_NAME="common-agent-r8-04-knowledge-${RUN_ID}"
MVP_EMPLOYEE_NAME="common-agent-r8-04-employee-${RUN_ID}"
MVP_WORKFLOW_NAME="common-agent-r8-04-workflow-${RUN_ID}"
COLD_MONITOR_PID=""
SOAK_MONITOR_PID=""
RAGFLOW_API_KEY=""
DATA_CLEANED=0
AUTH_STATE_TOUCHED=0

if [[ ! "${SOAK_SECONDS}" =~ ^[0-9]+$ ]] || ((SOAK_SECONDS < 1800)); then
  echo "R8-04 正式 soak 至少需要 1800 秒" >&2
  exit 2
fi
if colima status --profile "${PROFILE_NAME}" >/dev/null 2>&1; then
  echo "R8-04 必须从已停止的项目专属 Colima 开始，才能记录冷启动" >&2
  exit 1
fi

stop_process() {
  local pid="$1"
  if [[ -n "${pid}" ]] && kill -0 "${pid}" >/dev/null 2>&1; then
    kill "${pid}" >/dev/null 2>&1 || true
    wait "${pid}" >/dev/null 2>&1 || true
  fi
}

cleanup_business_data() {
  if ((DATA_CLEANED != 0)) || [[ -z "${RAGFLOW_API_KEY}" ]]; then
    return
  fi
  (
    cd "${BACKEND_ROOT}"
    COMMON_AGENT_DATABASE_URL="${DATABASE_URL}" \
    RAGFLOW_BASE_URL="${RAGFLOW_BASE_URL}" \
    RAGFLOW_API_KEY="${RAGFLOW_API_KEY}" \
    COMMON_AGENT_E2E_MVP_KNOWLEDGE_NAME="${MVP_KNOWLEDGE_NAME}" \
    COMMON_AGENT_E2E_MVP_EMPLOYEE_NAME="${MVP_EMPLOYEE_NAME}" \
    COMMON_AGENT_E2E_MVP_WORKFLOW_NAME="${MVP_WORKFLOW_NAME}" \
      "${UV_RUNNER}" run --frozen python -m tests.support.mvp_acceptance_e2e_cleanup
  )
  DATA_CLEANED=1
}

reset_auth_state() {
  (
    cd "${BACKEND_ROOT}"
    COMMON_AGENT_DATABASE_URL="${DATABASE_URL}" \
      "${UV_RUNNER}" run --frozen python -m tests.support.auth_e2e_state reset
  )
}

cleanup_auth_state() {
  if ((AUTH_STATE_TOUCHED == 0)); then
    return
  fi
  reset_auth_state
  AUTH_STATE_TOUCHED=0
}

cleanup() {
  local original_status=$?
  trap - EXIT INT TERM
  stop_process "${SOAK_MONITOR_PID}"
  stop_process "${COLD_MONITOR_PID}"
  cleanup_business_data || original_status=1
  cleanup_auth_state || original_status=1
  COMMON_AGENT_REAL_DATABASE_NAME=common_agent_test \
    "${REAL_MANAGER}" stop || original_status=1
  if ((original_status == 0)); then
    echo "R8-04 资源报告：${REPORT_ROOT}"
  else
    echo "R8-04 验收失败，报告保留在：${REPORT_ROOT}" >&2
  fi
  exit "${original_status}"
}
trap cleanup EXIT
trap 'exit 130' INT TERM

mkdir -p "${REPORT_ROOT}"
python3 "${MONITOR}" cold-start \
  --duration-seconds 600 \
  --interval-seconds 1 \
  --output "${REPORT_ROOT}/cold-start.json" \
  >"${REPORT_ROOT}/cold-start.log" 2>&1 &
COLD_MONITOR_PID=$!

COMMON_AGENT_REAL_DATABASE_NAME=common_agent_test "${REAL_MANAGER}" up
wait "${COLD_MONITOR_PID}"
COLD_MONITOR_PID=""
COMMON_AGENT_REAL_DATABASE_NAME=common_agent_test "${REAL_MANAGER}" status
COMMON_AGENT_REAL_DATABASE_NAME=common_agent_test "${REAL_MANAGER}" cost

if [[ ! -f "${TOKEN_FILE}" || -L "${TOKEN_FILE}" ]]; then
  echo "RAGFlow 0600 Token 文件不存在或不安全" >&2
  exit 1
fi
IFS= read -r RAGFLOW_API_KEY <"${TOKEN_FILE}"
if [[ "${RAGFLOW_API_KEY}" != ragflow-* ]]; then
  echo "RAGFlow Token 文件无效" >&2
  exit 1
fi
if [[ ! -f "${AUTH_BOOTSTRAP_TOKEN_FILE}" || -L "${AUTH_BOOTSTRAP_TOKEN_FILE}" ]]; then
  echo "首位所有者引导凭据文件不存在或不安全" >&2
  exit 1
fi
IFS= read -r AUTH_BOOTSTRAP_TOKEN <"${AUTH_BOOTSTRAP_TOKEN_FILE}"
if ((${#AUTH_BOOTSTRAP_TOKEN} < 32 || ${#AUTH_BOOTSTRAP_TOKEN} > 256)); then
  echo "首位所有者引导凭据文件无效" >&2
  exit 1
fi

reset_auth_state
AUTH_STATE_TOUCHED=1

python3 "${MONITOR}" soak \
  --duration-seconds "${SOAK_SECONDS}" \
  --interval-seconds 10 \
  --output "${REPORT_ROOT}/soak.json" \
  >"${REPORT_ROOT}/soak.log" 2>&1 &
SOAK_MONITOR_PID=$!

(
  cd "${BACKEND_ROOT}"
  TEST_RAGFLOW_BASE_URL="${RAGFLOW_BASE_URL}" \
  TEST_RAGFLOW_API_KEY="${RAGFLOW_API_KEY}" \
  TEST_RAGFLOW_EXPECTED_VERSION="${RAGFLOW_EXPECTED_VERSION}" \
    "${UV_RUNNER}" run --frozen pytest -q \
      tests/integration/knowledge/test_real_ragflow.py::test_real_ragflow_adapter_lifecycle
)

(
  cd "${BACKEND_ROOT}"
  COMMON_AGENT_DATABASE_URL="${DATABASE_URL}" \
  RAGFLOW_BASE_URL="${RAGFLOW_BASE_URL}" \
  RAGFLOW_API_KEY="${RAGFLOW_API_KEY}" \
    "${UV_RUNNER}" run --frozen python -m tests.support.mvp_acceptance_empty
)

(
  cd "${FRONTEND_ROOT}"
  pnpm exec playwright install chromium-headless-shell
  COMMON_AGENT_E2E_MVP_KNOWLEDGE_NAME="${MVP_KNOWLEDGE_NAME}" \
  COMMON_AGENT_E2E_MVP_EMPLOYEE_NAME="${MVP_EMPLOYEE_NAME}" \
  COMMON_AGENT_E2E_MVP_WORKFLOW_NAME="${MVP_WORKFLOW_NAME}" \
  COMMON_AGENT_E2E_API_URL="http://127.0.0.1:18200/api/v1" \
  COMMON_AGENT_E2E_AUTH_BOOTSTRAP_TOKEN="${AUTH_BOOTSTRAP_TOKEN}" \
  COMMON_AGENT_E2E_AUTH_EMAIL="${AUTH_EMAIL}" \
  COMMON_AGENT_E2E_AUTH_PASSWORD="${AUTH_PASSWORD}" \
  COMMON_AGENT_E2E_FRONTEND_URL="http://127.0.0.1:18280" \
  COMMON_AGENT_E2E_ARTIFACT_DIR="${REPORT_ROOT}/playwright" \
    pnpm exec playwright test e2e/mvp-acceptance.spec.ts --config playwright.config.ts
)
cleanup_business_data

wait "${SOAK_MONITOR_PID}"
SOAK_MONITOR_PID=""
COMMON_AGENT_REAL_DATABASE_NAME=common_agent_test "${REAL_MANAGER}" status
sed -n '1,20p' "${REPORT_ROOT}/cold-start.log"
sed -n '1,20p' "${REPORT_ROOT}/soak.log"
echo "R8-04 32 GiB 冷启动、中文召回/重排、两轮会话、工作流与 30 分钟 soak 验收通过"
