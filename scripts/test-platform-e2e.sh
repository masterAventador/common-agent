#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BACKEND_ROOT="${REPOSITORY_ROOT}/backend"
FRONTEND_ROOT="${REPOSITORY_ROOT}/frontend"
API_PORT=18200
FRONTEND_PORT=18280
RAGFLOW_BASE_URL="http://127.0.0.1:19380"
RUN_ID="$(date -u +%Y%m%d%H%M%S)-$$"
COMMON_AGENT_E2E_KNOWLEDGE_NAME="common-agent-k2-06-${RUN_ID}"
COMMON_AGENT_E2E_EMPLOYEE_NAME="common-agent-e3-05-employee-${RUN_ID}"
COMMON_AGENT_E2E_EMPLOYEE_KNOWLEDGE_NAME="common-agent-e3-05-knowledge-${RUN_ID}"
ARTIFACT_ROOT="${REPOSITORY_ROOT}/.local/test-artifacts/platform-e2e/${RUN_ID}"
BACKEND_LOG="${ARTIFACT_ROOT}/backend.log"
FRONTEND_LOG="${ARTIFACT_ROOT}/frontend.log"
PLAYWRIGHT_PID=""
BACKEND_PID=""
FRONTEND_PID=""
RAGFLOW_API_KEY=""
COMMON_AGENT_DATABASE_URL="mysql+asyncmy://common_agent:common_agent_dev@127.0.0.1:19506/common_agent_test?charset=utf8mb4"

port_is_free() {
  ! lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
}

wait_for_url() {
  local url="$1"
  local deadline=$((SECONDS + 60))
  while ((SECONDS < deadline)); do
    if curl --fail --silent --show-error "${url}" >/dev/null 2>&1; then
      return
    fi
    sleep 1
  done
  echo "服务未在 60 秒内就绪：${url}" >&2
  return 1
}

stop_process() {
  local pid="$1"
  if [[ -n "${pid}" ]] && kill -0 "${pid}" >/dev/null 2>&1; then
    kill "${pid}" >/dev/null 2>&1 || true
    wait "${pid}" >/dev/null 2>&1 || true
  fi
}

cleanup() {
  local original_status=$?
  local cleanup_status=0
  trap - EXIT INT TERM

  stop_process "${PLAYWRIGHT_PID}"
  stop_process "${FRONTEND_PID}"
  stop_process "${BACKEND_PID}"

  if [[ -n "${RAGFLOW_API_KEY}" ]]; then
    if ! (
      cd "${BACKEND_ROOT}"
      RAGFLOW_BASE_URL="${RAGFLOW_BASE_URL}" \
      RAGFLOW_API_KEY="${RAGFLOW_API_KEY}" \
      COMMON_AGENT_DATABASE_URL="${COMMON_AGENT_DATABASE_URL}" \
      COMMON_AGENT_E2E_KNOWLEDGE_NAME="${COMMON_AGENT_E2E_KNOWLEDGE_NAME}" \
      COMMON_AGENT_E2E_EMPLOYEE_NAME="${COMMON_AGENT_E2E_EMPLOYEE_NAME}" \
      COMMON_AGENT_E2E_EMPLOYEE_KNOWLEDGE_NAME="${COMMON_AGENT_E2E_EMPLOYEE_KNOWLEDGE_NAME}" \
        uv run --frozen python -m tests.support.platform_e2e_cleanup
    ); then
      echo "平台 E2E 数据清理失败，保留验收产物：${ARTIFACT_ROOT}" >&2
      cleanup_status=1
    fi
  fi

  if ((original_status == 0 && cleanup_status == 0)); then
    case "${ARTIFACT_ROOT}" in
      "${REPOSITORY_ROOT}/.local/test-artifacts/platform-e2e/"*) rm -rf "${ARTIFACT_ROOT}" ;;
      *)
        echo "拒绝清理非平台 E2E 产物目录：${ARTIFACT_ROOT}" >&2
        cleanup_status=1
        ;;
    esac
  else
    echo "平台 E2E 验收失败，日志与 Trace 保留在：${ARTIFACT_ROOT}" >&2
  fi

  if ((original_status != 0)); then
    exit "${original_status}"
  fi
  exit "${cleanup_status}"
}

trap cleanup EXIT
trap 'exit 130' INT TERM

if ! port_is_free "${API_PORT}"; then
  echo "平台 E2E API 端口已被占用：127.0.0.1:${API_PORT}" >&2
  exit 1
fi
if ! port_is_free "${FRONTEND_PORT}"; then
  echo "平台 E2E 前端端口已被占用：127.0.0.1:${FRONTEND_PORT}" >&2
  exit 1
fi

mkdir -p "${ARTIFACT_ROOT}"
(
  cd "${FRONTEND_ROOT}"
  pnpm exec playwright install chromium-headless-shell
)
if [[ "$(docker --context colima-common-agent-dev inspect \
  --format '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' \
  common-agent-platform-mysql 2>/dev/null || true)" != "running healthy" ]]; then
  "${REPOSITORY_ROOT}/infra/platform/manage.sh" up
fi
if ! curl --fail --silent --show-error \
  "${RAGFLOW_BASE_URL}/api/v1/system/version" >/dev/null 2>&1; then
  "${REPOSITORY_ROOT}/infra/ragflow/manage.sh" up
fi

RAGFLOW_API_KEY="$(
  cd "${BACKEND_ROOT}"
  uv run --frozen python -c \
    'import asyncio; from tests.support.ragflow import provision_api_key; print(asyncio.run(provision_api_key("http://127.0.0.1:19380")))'
)"
export RAGFLOW_API_KEY
export RAGFLOW_BASE_URL
export RAGFLOW_EXPECTED_VERSION="v0.25.6"
export RAGFLOW_TIMEOUT_SECONDS="120"
export COMMON_AGENT_DATABASE_URL

(
  cd "${BACKEND_ROOT}"
  exec uv run --frozen python -m common_agent
) >"${BACKEND_LOG}" 2>&1 &
BACKEND_PID=$!
wait_for_url "http://127.0.0.1:${API_PORT}/api/v1/system/health"

(
  cd "${FRONTEND_ROOT}"
  unset RAGFLOW_API_KEY
  exec pnpm dev
) >"${FRONTEND_LOG}" 2>&1 &
FRONTEND_PID=$!
wait_for_url "http://127.0.0.1:${FRONTEND_PORT}/knowledge-bases"

(
  cd "${FRONTEND_ROOT}"
  COMMON_AGENT_E2E_KNOWLEDGE_NAME="${COMMON_AGENT_E2E_KNOWLEDGE_NAME}" \
  COMMON_AGENT_E2E_EMPLOYEE_NAME="${COMMON_AGENT_E2E_EMPLOYEE_NAME}" \
  COMMON_AGENT_E2E_EMPLOYEE_KNOWLEDGE_NAME="${COMMON_AGENT_E2E_EMPLOYEE_KNOWLEDGE_NAME}" \
  COMMON_AGENT_E2E_FRONTEND_URL="http://127.0.0.1:${FRONTEND_PORT}" \
  COMMON_AGENT_E2E_ARTIFACT_DIR="${ARTIFACT_ROOT}/playwright" \
    exec pnpm exec playwright test --config playwright.config.ts
) &
PLAYWRIGHT_PID=$!
wait "${PLAYWRIGHT_PID}"
PLAYWRIGHT_PID=""
