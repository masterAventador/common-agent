#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BACKEND_ROOT="${REPOSITORY_ROOT}/backend"
FRONTEND_ROOT="${REPOSITORY_ROOT}/frontend"
API_PORT=18200
FRONTEND_PORT=18280
RAGFLOW_BASE_URL="http://127.0.0.1:19380"
E2E_SUITE="${COMMON_AGENT_E2E_SUITE:-platform}"
RUN_ID="$(date -u +%Y%m%d%H%M%S)-$$"
COMMON_AGENT_E2E_KNOWLEDGE_NAME="common-agent-k2-06-${RUN_ID}"
COMMON_AGENT_E2E_EMPLOYEE_NAME="common-agent-e3-05-employee-${RUN_ID}"
COMMON_AGENT_E2E_EMPLOYEE_KNOWLEDGE_NAME="common-agent-e3-05-knowledge-${RUN_ID}"
COMMON_AGENT_E2E_WORKFLOW_NAME="common-agent-w5-05-workflow-${RUN_ID}"
COMMON_AGENT_E2E_WORKFLOW_KNOWLEDGE_NAME="common-agent-w5-05-knowledge-${RUN_ID}"
COMMON_AGENT_E2E_WORKFLOW_RUN_NAME="common-agent-w5-06-run-${RUN_ID}"
COMMON_AGENT_E2E_WORKFLOW_STOP_NAME="common-agent-w5-06-stop-${RUN_ID}"
COMMON_AGENT_E2E_WORKFLOW_FAILURE_NAME="common-agent-w5-06-failure-${RUN_ID}"
COMMON_AGENT_E2E_WORKFLOW_FAILURE_KNOWLEDGE_NAME="common-agent-w5-06-knowledge-${RUN_ID}"
COMMON_AGENT_E2E_WORKFLOW_CHAT_NAME="common-agent-w5-08-workflow-${RUN_ID}"
COMMON_AGENT_E2E_WORKFLOW_CHAT_EMPLOYEE_NAME="common-agent-w5-08-employee-${RUN_ID}"
COMMON_AGENT_E2E_MVP_KNOWLEDGE_NAME="common-agent-q6-04-knowledge-${RUN_ID}"
COMMON_AGENT_E2E_MVP_EMPLOYEE_NAME="common-agent-q6-04-employee-${RUN_ID}"
COMMON_AGENT_E2E_MVP_WORKFLOW_NAME="common-agent-q6-04-workflow-${RUN_ID}"
COMMON_AGENT_DEMO_E2E_EMPLOYEE_NAME="common-agent-a4-08-employee-${RUN_ID}"
COMMON_AGENT_DEMO_E2E_KNOWLEDGE_NAME="common-agent-a4-08-knowledge-${RUN_ID}"
ARTIFACT_ROOT="${REPOSITORY_ROOT}/.local/test-artifacts/platform-e2e/${E2E_SUITE}-${RUN_ID}"
BACKEND_LOG="${ARTIFACT_ROOT}/backend.log"
FRONTEND_LOG="${ARTIFACT_ROOT}/frontend.log"
PLAYWRIGHT_PID=""
BACKEND_PID=""
FRONTEND_PID=""
RAGFLOW_API_KEY=""
COMMON_AGENT_DATABASE_URL="mysql+aiomysql://common_agent:common_agent_dev@127.0.0.1:19506/common_agent_test?charset=utf8mb4"

if [[ "${E2E_SUITE}" != "platform" && "${E2E_SUITE}" != "demo-chat" && "${E2E_SUITE}" != "workflow-designer" && "${E2E_SUITE}" != "workflow-run-ui" && "${E2E_SUITE}" != "workflow-chat-e2e" && "${E2E_SUITE}" != "mvp-acceptance" ]]; then
  echo "不支持的 E2E suite：${E2E_SUITE}" >&2
  exit 2
fi

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

  if [[ "${E2E_SUITE}" == "demo-chat" ]]; then
    if ! (
      cd "${BACKEND_ROOT}"
      COMMON_AGENT_DATABASE_URL="${COMMON_AGENT_DATABASE_URL}" \
      COMMON_AGENT_DEMO_E2E_EMPLOYEE_NAME="${COMMON_AGENT_DEMO_E2E_EMPLOYEE_NAME}" \
        uv run --frozen python -m tests.support.demo_chat_e2e_cleanup
    ); then
      echo "Demo 聊天 E2E 数据清理失败，保留验收产物：${ARTIFACT_ROOT}" >&2
      cleanup_status=1
    fi
  elif [[ "${E2E_SUITE}" == "workflow-designer" && -n "${RAGFLOW_API_KEY}" ]]; then
    if ! (
      cd "${BACKEND_ROOT}"
      RAGFLOW_BASE_URL="${RAGFLOW_BASE_URL}" \
      RAGFLOW_API_KEY="${RAGFLOW_API_KEY}" \
      COMMON_AGENT_DATABASE_URL="${COMMON_AGENT_DATABASE_URL}" \
      COMMON_AGENT_E2E_WORKFLOW_NAME="${COMMON_AGENT_E2E_WORKFLOW_NAME}" \
      COMMON_AGENT_E2E_WORKFLOW_KNOWLEDGE_NAME="${COMMON_AGENT_E2E_WORKFLOW_KNOWLEDGE_NAME}" \
        uv run --frozen python -m tests.support.workflow_designer_e2e_cleanup
    ); then
      echo "工作流设计器 E2E 数据清理失败，保留验收产物：${ARTIFACT_ROOT}" >&2
      cleanup_status=1
    fi
  elif [[ "${E2E_SUITE}" == "workflow-run-ui" && -n "${RAGFLOW_API_KEY}" ]]; then
    if ! (
      cd "${BACKEND_ROOT}"
      RAGFLOW_BASE_URL="${RAGFLOW_BASE_URL}" \
      RAGFLOW_API_KEY="${RAGFLOW_API_KEY}" \
      COMMON_AGENT_DATABASE_URL="${COMMON_AGENT_DATABASE_URL}" \
      COMMON_AGENT_E2E_WORKFLOW_RUN_NAME="${COMMON_AGENT_E2E_WORKFLOW_RUN_NAME}" \
      COMMON_AGENT_E2E_WORKFLOW_STOP_NAME="${COMMON_AGENT_E2E_WORKFLOW_STOP_NAME}" \
      COMMON_AGENT_E2E_WORKFLOW_FAILURE_NAME="${COMMON_AGENT_E2E_WORKFLOW_FAILURE_NAME}" \
      COMMON_AGENT_E2E_WORKFLOW_FAILURE_KNOWLEDGE_NAME="${COMMON_AGENT_E2E_WORKFLOW_FAILURE_KNOWLEDGE_NAME}" \
        uv run --frozen python -m tests.support.workflow_run_ui_e2e_cleanup
    ); then
      echo "手动运行 UI E2E 数据清理失败，保留验收产物：${ARTIFACT_ROOT}" >&2
      cleanup_status=1
    fi
  elif [[ "${E2E_SUITE}" == "workflow-chat-e2e" ]]; then
    if ! (
      cd "${BACKEND_ROOT}"
      COMMON_AGENT_DATABASE_URL="${COMMON_AGENT_DATABASE_URL}" \
      COMMON_AGENT_E2E_WORKFLOW_CHAT_NAME="${COMMON_AGENT_E2E_WORKFLOW_CHAT_NAME}" \
      COMMON_AGENT_E2E_WORKFLOW_CHAT_EMPLOYEE_NAME="${COMMON_AGENT_E2E_WORKFLOW_CHAT_EMPLOYEE_NAME}" \
        uv run --frozen python -m tests.support.workflow_chat_e2e_cleanup
    ); then
      echo "工作流对话 E2E 数据清理失败，保留验收产物：${ARTIFACT_ROOT}" >&2
      cleanup_status=1
    fi
  elif [[ "${E2E_SUITE}" == "mvp-acceptance" && -n "${RAGFLOW_API_KEY}" ]]; then
    if ! (
      cd "${BACKEND_ROOT}"
      RAGFLOW_BASE_URL="${RAGFLOW_BASE_URL}" \
      RAGFLOW_API_KEY="${RAGFLOW_API_KEY}" \
      COMMON_AGENT_DATABASE_URL="${COMMON_AGENT_DATABASE_URL}" \
      COMMON_AGENT_E2E_MVP_KNOWLEDGE_NAME="${COMMON_AGENT_E2E_MVP_KNOWLEDGE_NAME}" \
      COMMON_AGENT_E2E_MVP_EMPLOYEE_NAME="${COMMON_AGENT_E2E_MVP_EMPLOYEE_NAME}" \
      COMMON_AGENT_E2E_MVP_WORKFLOW_NAME="${COMMON_AGENT_E2E_MVP_WORKFLOW_NAME}" \
        uv run --frozen python -m tests.support.mvp_acceptance_e2e_cleanup
    ); then
      echo "MVP 总验收数据清理失败，保留验收产物：${ARTIFACT_ROOT}" >&2
      cleanup_status=1
    fi
  elif [[ -n "${RAGFLOW_API_KEY}" ]]; then
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
export COMMON_AGENT_DATABASE_URL
if [[ "${E2E_SUITE}" != "demo-chat" ]]; then
  export COMMON_AGENT_INTEGRATION_MODE="real"
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
  if [[ "${E2E_SUITE}" == "mvp-acceptance" ]]; then
    (
      cd "${BACKEND_ROOT}"
      COMMON_AGENT_DATABASE_URL="${COMMON_AGENT_DATABASE_URL}" \
      RAGFLOW_BASE_URL="${RAGFLOW_BASE_URL}" \
      RAGFLOW_API_KEY="${RAGFLOW_API_KEY}" \
        uv run --frozen python -m tests.support.mvp_acceptance_empty
    )
  fi
else
  export COMMON_AGENT_INTEGRATION_MODE="demo"
fi

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
  if [[ "${E2E_SUITE}" == "platform" ]]; then
    COMMON_AGENT_E2E_KNOWLEDGE_NAME="${COMMON_AGENT_E2E_KNOWLEDGE_NAME}" \
    COMMON_AGENT_E2E_EMPLOYEE_NAME="${COMMON_AGENT_E2E_EMPLOYEE_NAME}" \
    COMMON_AGENT_E2E_EMPLOYEE_KNOWLEDGE_NAME="${COMMON_AGENT_E2E_EMPLOYEE_KNOWLEDGE_NAME}" \
    COMMON_AGENT_E2E_FRONTEND_URL="http://127.0.0.1:${FRONTEND_PORT}" \
    COMMON_AGENT_E2E_ARTIFACT_DIR="${ARTIFACT_ROOT}/playwright" \
      exec pnpm exec playwright test \
        e2e/employees.spec.ts e2e/knowledge-bases.spec.ts \
        --config playwright.config.ts
  elif [[ "${E2E_SUITE}" == "workflow-designer" ]]; then
    COMMON_AGENT_E2E_WORKFLOW_NAME="${COMMON_AGENT_E2E_WORKFLOW_NAME}" \
    COMMON_AGENT_E2E_WORKFLOW_KNOWLEDGE_NAME="${COMMON_AGENT_E2E_WORKFLOW_KNOWLEDGE_NAME}" \
    COMMON_AGENT_E2E_FRONTEND_URL="http://127.0.0.1:${FRONTEND_PORT}" \
    COMMON_AGENT_E2E_ARTIFACT_DIR="${ARTIFACT_ROOT}/playwright" \
      exec pnpm exec playwright test e2e/workflows.spec.ts --config playwright.config.ts
  elif [[ "${E2E_SUITE}" == "workflow-run-ui" ]]; then
    COMMON_AGENT_E2E_WORKFLOW_RUN_NAME="${COMMON_AGENT_E2E_WORKFLOW_RUN_NAME}" \
    COMMON_AGENT_E2E_WORKFLOW_STOP_NAME="${COMMON_AGENT_E2E_WORKFLOW_STOP_NAME}" \
    COMMON_AGENT_E2E_WORKFLOW_FAILURE_NAME="${COMMON_AGENT_E2E_WORKFLOW_FAILURE_NAME}" \
    COMMON_AGENT_E2E_WORKFLOW_FAILURE_KNOWLEDGE_NAME="${COMMON_AGENT_E2E_WORKFLOW_FAILURE_KNOWLEDGE_NAME}" \
    COMMON_AGENT_E2E_API_URL="http://127.0.0.1:${API_PORT}/api/v1" \
    COMMON_AGENT_E2E_FRONTEND_URL="http://127.0.0.1:${FRONTEND_PORT}" \
    COMMON_AGENT_E2E_ARTIFACT_DIR="${ARTIFACT_ROOT}/playwright" \
      exec pnpm exec playwright test e2e/workflow-runs.spec.ts --config playwright.config.ts
  elif [[ "${E2E_SUITE}" == "workflow-chat-e2e" ]]; then
    COMMON_AGENT_E2E_WORKFLOW_CHAT_NAME="${COMMON_AGENT_E2E_WORKFLOW_CHAT_NAME}" \
    COMMON_AGENT_E2E_WORKFLOW_CHAT_EMPLOYEE_NAME="${COMMON_AGENT_E2E_WORKFLOW_CHAT_EMPLOYEE_NAME}" \
    COMMON_AGENT_E2E_FRONTEND_URL="http://127.0.0.1:${FRONTEND_PORT}" \
    COMMON_AGENT_E2E_ARTIFACT_DIR="${ARTIFACT_ROOT}/playwright" \
      exec pnpm exec playwright test e2e/workflow-chat-e2e.spec.ts --config playwright.config.ts
  elif [[ "${E2E_SUITE}" == "mvp-acceptance" ]]; then
    COMMON_AGENT_E2E_MVP_KNOWLEDGE_NAME="${COMMON_AGENT_E2E_MVP_KNOWLEDGE_NAME}" \
    COMMON_AGENT_E2E_MVP_EMPLOYEE_NAME="${COMMON_AGENT_E2E_MVP_EMPLOYEE_NAME}" \
    COMMON_AGENT_E2E_MVP_WORKFLOW_NAME="${COMMON_AGENT_E2E_MVP_WORKFLOW_NAME}" \
    COMMON_AGENT_E2E_FRONTEND_URL="http://127.0.0.1:${FRONTEND_PORT}" \
    COMMON_AGENT_E2E_ARTIFACT_DIR="${ARTIFACT_ROOT}/playwright" \
      exec pnpm exec playwright test e2e/mvp-acceptance.spec.ts --config playwright.config.ts
  else
    COMMON_AGENT_DEMO_E2E_EMPLOYEE_NAME="${COMMON_AGENT_DEMO_E2E_EMPLOYEE_NAME}" \
    COMMON_AGENT_DEMO_E2E_KNOWLEDGE_NAME="${COMMON_AGENT_DEMO_E2E_KNOWLEDGE_NAME}" \
    COMMON_AGENT_E2E_FRONTEND_URL="http://127.0.0.1:${FRONTEND_PORT}" \
    COMMON_AGENT_E2E_ARTIFACT_DIR="${ARTIFACT_ROOT}/playwright" \
      exec pnpm exec playwright test e2e/chat-demo.spec.ts --config playwright.config.ts
  fi
) &
PLAYWRIGHT_PID=$!
wait "${PLAYWRIGHT_PID}"
PLAYWRIGHT_PID=""
