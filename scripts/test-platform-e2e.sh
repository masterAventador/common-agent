#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BACKEND_ROOT="${REPOSITORY_ROOT}/backend"
FRONTEND_ROOT="${REPOSITORY_ROOT}/frontend"
UV_RUNNER="${SCRIPT_DIR}/uv.sh"
API_PORT="${COMMON_AGENT_E2E_API_PORT:-18200}"
FRONTEND_PORT="${COMMON_AGENT_E2E_FRONTEND_PORT:-18280}"
RAGFLOW_BASE_URL="http://127.0.0.1:19380"
E2E_SUITE="${COMMON_AGENT_E2E_SUITE:-platform}"
DOCKER_CONTEXT_NAME="${COMMON_AGENT_E2E_DOCKER_CONTEXT:-colima-common-agent-dev}"
RUN_ID="$(date -u +%Y%m%d%H%M%S)-$$"
COMMON_AGENT_E2E_KNOWLEDGE_NAME="common-agent-k2-06-${RUN_ID}"
COMMON_AGENT_E2E_BATCH_KNOWLEDGE_NAME="common-agent-s10-07j-knowledge-${RUN_ID}"
COMMON_AGENT_E2E_BATCH_EMPLOYEE_NAME="common-agent-s10-07j-employee-${RUN_ID}"
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
COMMON_AGENT_E2E_DELETE_KNOWLEDGE_NAME="common-agent-u9-02-knowledge-${RUN_ID}"
COMMON_AGENT_E2E_DELETE_EMPLOYEE_NAME="common-agent-u9-02-employee-${RUN_ID}"
COMMON_AGENT_E2E_DELETE_WORKFLOW_NAME="common-agent-u9-02-workflow-${RUN_ID}"
COMMON_AGENT_E2E_LIST_PREFIX="common-agent-u9-03-${RUN_ID}"
COMMON_AGENT_E2E_KNOWLEDGE_PAGE_PREFIX="common-agent-s10-07b-${RUN_ID}"
COMMON_AGENT_DEMO_E2E_EMPLOYEE_NAME="common-agent-a4-08-employee-${RUN_ID}"
COMMON_AGENT_DEMO_E2E_KNOWLEDGE_NAME="common-agent-a4-08-knowledge-${RUN_ID}"
COMMON_AGENT_E2E_AUTH_BOOTSTRAP_TOKEN="e2e-bootstrap-token-at-least-32-characters"
COMMON_AGENT_E2E_AUTH_EMAIL="e2e-owner@example.com"
COMMON_AGENT_E2E_AUTH_PASSWORD="correct horse battery staple"
COMMON_AGENT_E2E_TENANT_NAME="common-agent-s10-03-${RUN_ID}"
COMMON_AGENT_E2E_TENANT_EMPLOYEE_NAME="common-agent-s10-03-employee-${RUN_ID}"
COMMON_AGENT_E2E_VIEWER_EMAIL="viewer-s10-03-${RUN_ID}@example.com"
COMMON_AGENT_E2E_VIEWER_PASSWORD="viewer initial password is secure"
COMMON_AGENT_E2E_AUDIT_EMPLOYEE_NAME="common-agent-s10-04-audit-${RUN_ID}"
COMMON_AGENT_E2E_MODEL_NAME="common-agent-s10-07e-model-${RUN_ID}"
COMMON_AGENT_E2E_EMPLOYEE_MODEL_NAME="common-agent-s10-07f-model-${RUN_ID}"
COMMON_AGENT_E2E_EMPLOYEE_MODEL_EMPLOYEE_NAME="common-agent-s10-07f-employee-${RUN_ID}"
COMMON_AGENT_E2E_GENERIC_CHAT_MODEL_NAME="common-agent-s10-07g-model-${RUN_ID}"
LIGHT_E2E_MEMORY_GIB=12
REAL_E2E_MEMORY_GIB=32
ARTIFACT_ROOT="${REPOSITORY_ROOT}/.local/test-artifacts/platform-e2e/${E2E_SUITE}-${RUN_ID}"
BACKEND_LOG="${ARTIFACT_ROOT}/backend.log"
WORKER_LOG="${ARTIFACT_ROOT}/worker.log"
FRONTEND_LOG="${ARTIFACT_ROOT}/frontend.log"
RAGFLOW_PROVISION_LOG="${ARTIFACT_ROOT}/ragflow-provision.log"
PLAYWRIGHT_PID=""
BACKEND_PID=""
WORKER_PID=""
FRONTEND_PID=""
RAGFLOW_API_KEY=""
COMMON_AGENT_DATABASE_URL="mysql+aiomysql://common_agent:common_agent_dev@127.0.0.1:19506/common_agent_test?charset=utf8mb4"

if [[ "${E2E_SUITE}" != "platform" && "${E2E_SUITE}" != "auth" && "${E2E_SUITE}" != "tenant-rbac" && "${E2E_SUITE}" != "audit" && "${E2E_SUITE}" != "demo-chat" && "${E2E_SUITE}" != "frontend-loading" && "${E2E_SUITE}" != "design-system" && "${E2E_SUITE}" != "managed-tools" && "${E2E_SUITE}" != "workflow-designer" && "${E2E_SUITE}" != "workflow-run-ui" && "${E2E_SUITE}" != "workflow-chat-e2e" && "${E2E_SUITE}" != "mvp-acceptance" && "${E2E_SUITE}" != "resource-deletion" && "${E2E_SUITE}" != "list-pagination" && "${E2E_SUITE}" != "knowledge-pagination" && "${E2E_SUITE}" != "knowledge-batch" && "${E2E_SUITE}" != "model-configurations" && "${E2E_SUITE}" != "employee-default-model" && "${E2E_SUITE}" != "generic-chat-models" ]]; then
  echo "不支持的 E2E suite：${E2E_SUITE}" >&2
  exit 2
fi

port_is_free() {
  ! lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
}

ensure_colima_profile() {
  local cpus=8
  local memory_gib="${REAL_E2E_MEMORY_GIB}"
  local current_memory_bytes=""
  local current_memory_gib=0
  if [[ "${E2E_SUITE}" == "auth" || "${E2E_SUITE}" == "tenant-rbac" || "${E2E_SUITE}" == "audit" || "${E2E_SUITE}" == "demo-chat" || "${E2E_SUITE}" == "frontend-loading" || "${E2E_SUITE}" == "design-system" || "${E2E_SUITE}" == "managed-tools" || "${E2E_SUITE}" == "list-pagination" ]]; then
    cpus=4
    memory_gib="${LIGHT_E2E_MEMORY_GIB}"
  fi
  if colima status --profile common-agent-dev >/dev/null 2>&1; then
    if current_memory_bytes="$(
      docker --context "${DOCKER_CONTEXT_NAME}" info --format '{{.MemTotal}}' 2>/dev/null
    )" && [[ "${current_memory_bytes}" =~ ^[0-9]+$ ]]; then
      current_memory_gib=$(((current_memory_bytes + 1073741823) / 1073741824))
      if ((current_memory_gib >= memory_gib)); then
        return
      fi
    fi
    RAGFLOW_DOCKER_CONTEXT="${DOCKER_CONTEXT_NAME}" \
      "${REPOSITORY_ROOT}/infra/ragflow/manage.sh" stop
    PLATFORM_DOCKER_CONTEXT="${DOCKER_CONTEXT_NAME}" \
      "${REPOSITORY_ROOT}/infra/platform/manage.sh" down
    colima stop common-agent-dev
  fi
  colima start common-agent-dev \
    --cpus "${cpus}" \
    --memory "${memory_gib}" \
    --disk 100 \
    --root-disk 20 \
    --runtime docker \
    --vm-type vz \
    --vz-rosetta \
    --activate=false
  docker --context "${DOCKER_CONTEXT_NAME}" info >/dev/null
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

provision_ragflow_api_key() {
  local api_key=""
  local deadline=$((SECONDS + 60))
  while ((SECONDS < deadline)); do
    if api_key="$(
      cd "${BACKEND_ROOT}"
      "${UV_RUNNER}" run --frozen python -c \
        'import asyncio; from tests.support.ragflow import provision_api_key; print(asyncio.run(provision_api_key("http://127.0.0.1:19380")))' \
        2>>"${RAGFLOW_PROVISION_LOG}"
    )"; then
      printf '%s\n' "${api_key}"
      return
    fi
    sleep 2
  done
  echo "RAGFlow 测试 Token 未在 60 秒内申请成功" >&2
  return 1
}

stop_process() {
  local pid="$1"
  if [[ -n "${pid}" ]] && kill -0 "${pid}" >/dev/null 2>&1; then
    kill "${pid}" >/dev/null 2>&1 || true
    local deadline=$((SECONDS + 15))
    while kill -0 "${pid}" >/dev/null 2>&1 && ((SECONDS < deadline)); do
      sleep 1
    done
    if kill -0 "${pid}" >/dev/null 2>&1; then
      kill -KILL "${pid}" >/dev/null 2>&1 || true
    fi
    wait "${pid}" >/dev/null 2>&1 || true
  fi
}

cleanup() {
  local original_status=$?
  local cleanup_status=0
  trap - EXIT INT TERM

  stop_process "${PLAYWRIGHT_PID}"
  stop_process "${FRONTEND_PID}"
  stop_process "${WORKER_PID}"
  stop_process "${BACKEND_PID}"

  if [[ "${E2E_SUITE}" == "tenant-rbac" ]]; then
    if ! (
      cd "${BACKEND_ROOT}"
      COMMON_AGENT_DATABASE_URL="${COMMON_AGENT_DATABASE_URL}" \
      COMMON_AGENT_E2E_TENANT_NAME="${COMMON_AGENT_E2E_TENANT_NAME}" \
      COMMON_AGENT_E2E_VIEWER_EMAIL="${COMMON_AGENT_E2E_VIEWER_EMAIL}" \
        "${UV_RUNNER}" run --frozen python -m tests.support.tenant_rbac_e2e_cleanup
    ); then
      echo "租户/RBAC E2E 数据清理失败，保留验收产物：${ARTIFACT_ROOT}" >&2
      cleanup_status=1
    fi
  elif [[ "${E2E_SUITE}" == "audit" ]]; then
    if ! (
      cd "${BACKEND_ROOT}"
      COMMON_AGENT_DATABASE_URL="${COMMON_AGENT_DATABASE_URL}" \
      COMMON_AGENT_E2E_AUDIT_EMPLOYEE_NAME="${COMMON_AGENT_E2E_AUDIT_EMPLOYEE_NAME}" \
        "${UV_RUNNER}" run --frozen python -m tests.support.audit_e2e_cleanup
    ); then
      echo "审计 E2E 数据清理失败，保留验收产物：${ARTIFACT_ROOT}" >&2
      cleanup_status=1
    fi
  elif [[ "${E2E_SUITE}" == "model-configurations" ]]; then
    if ! (
      cd "${BACKEND_ROOT}"
      COMMON_AGENT_DATABASE_URL="${COMMON_AGENT_DATABASE_URL}" \
      COMMON_AGENT_E2E_MODEL_NAME="${COMMON_AGENT_E2E_MODEL_NAME}" \
        "${UV_RUNNER}" run --frozen python -m tests.support.model_configuration_e2e_state cleanup
    ); then
      echo "模型管理 E2E 数据清理失败，保留验收产物：${ARTIFACT_ROOT}" >&2
      cleanup_status=1
    fi
  elif [[ "${E2E_SUITE}" == "employee-default-model" ]]; then
    if ! (
      cd "${BACKEND_ROOT}"
      COMMON_AGENT_DATABASE_URL="${COMMON_AGENT_DATABASE_URL}" \
      COMMON_AGENT_E2E_EMPLOYEE_MODEL_NAME="${COMMON_AGENT_E2E_EMPLOYEE_MODEL_NAME}" \
      COMMON_AGENT_E2E_EMPLOYEE_MODEL_EMPLOYEE_NAME="${COMMON_AGENT_E2E_EMPLOYEE_MODEL_EMPLOYEE_NAME}" \
        "${UV_RUNNER}" run --frozen python -m tests.support.employee_default_model_e2e_cleanup
    ); then
      echo "员工默认模型 E2E 数据清理失败，保留验收产物：${ARTIFACT_ROOT}" >&2
      cleanup_status=1
    fi
  elif [[ "${E2E_SUITE}" == "generic-chat-models" ]]; then
    if ! (
      cd "${BACKEND_ROOT}"
      COMMON_AGENT_DATABASE_URL="${COMMON_AGENT_DATABASE_URL}" \
      COMMON_AGENT_E2E_GENERIC_CHAT_MODEL_NAME="${COMMON_AGENT_E2E_GENERIC_CHAT_MODEL_NAME}" \
        "${UV_RUNNER}" run --frozen python -m tests.support.generic_chat_models_e2e_cleanup
    ); then
      echo "通用会话切模 E2E 数据清理失败，保留验收产物：${ARTIFACT_ROOT}" >&2
      cleanup_status=1
    fi
  elif [[ "${E2E_SUITE}" == "demo-chat" ]]; then
    if ! (
      cd "${BACKEND_ROOT}"
      COMMON_AGENT_DATABASE_URL="${COMMON_AGENT_DATABASE_URL}" \
      COMMON_AGENT_DEMO_E2E_EMPLOYEE_NAME="${COMMON_AGENT_DEMO_E2E_EMPLOYEE_NAME}" \
      COMMON_AGENT_DEMO_E2E_KNOWLEDGE_NAME="${COMMON_AGENT_DEMO_E2E_KNOWLEDGE_NAME}" \
        "${UV_RUNNER}" run --frozen python -m tests.support.demo_chat_e2e_cleanup
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
        "${UV_RUNNER}" run --frozen python -m tests.support.workflow_designer_e2e_cleanup
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
        "${UV_RUNNER}" run --frozen python -m tests.support.workflow_run_ui_e2e_cleanup
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
        "${UV_RUNNER}" run --frozen python -m tests.support.workflow_chat_e2e_cleanup
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
        "${UV_RUNNER}" run --frozen python -m tests.support.mvp_acceptance_e2e_cleanup
    ); then
      echo "MVP 总验收数据清理失败，保留验收产物：${ARTIFACT_ROOT}" >&2
      cleanup_status=1
    fi
  elif [[ "${E2E_SUITE}" == "resource-deletion" && -n "${RAGFLOW_API_KEY}" ]]; then
    if ! (
      cd "${BACKEND_ROOT}"
      RAGFLOW_BASE_URL="${RAGFLOW_BASE_URL}" \
      RAGFLOW_API_KEY="${RAGFLOW_API_KEY}" \
      COMMON_AGENT_DATABASE_URL="${COMMON_AGENT_DATABASE_URL}" \
      COMMON_AGENT_E2E_DELETE_KNOWLEDGE_NAME="${COMMON_AGENT_E2E_DELETE_KNOWLEDGE_NAME}" \
      COMMON_AGENT_E2E_DELETE_EMPLOYEE_NAME="${COMMON_AGENT_E2E_DELETE_EMPLOYEE_NAME}" \
      COMMON_AGENT_E2E_DELETE_WORKFLOW_NAME="${COMMON_AGENT_E2E_DELETE_WORKFLOW_NAME}" \
        "${UV_RUNNER}" run --frozen python -m tests.support.resource_deletion_e2e_cleanup
    ); then
      echo "资源删除 E2E 兜底清理失败，保留验收产物：${ARTIFACT_ROOT}" >&2
      cleanup_status=1
    fi
  elif [[ "${E2E_SUITE}" == "knowledge-pagination" && -n "${RAGFLOW_API_KEY}" ]]; then
    if ! (
      cd "${BACKEND_ROOT}"
      RAGFLOW_BASE_URL="${RAGFLOW_BASE_URL}" \
      RAGFLOW_API_KEY="${RAGFLOW_API_KEY}" \
      COMMON_AGENT_DATABASE_URL="${COMMON_AGENT_DATABASE_URL}" \
      COMMON_AGENT_E2E_KNOWLEDGE_PAGE_PREFIX="${COMMON_AGENT_E2E_KNOWLEDGE_PAGE_PREFIX}" \
        "${UV_RUNNER}" run --frozen python -m tests.support.knowledge_pagination_e2e_cleanup
    ); then
      echo "知识库大分页 E2E 数据清理失败，保留验收产物：${ARTIFACT_ROOT}" >&2
      cleanup_status=1
    fi
  elif [[ "${E2E_SUITE}" == "knowledge-batch" && -n "${RAGFLOW_API_KEY}" ]]; then
    if ! (
      cd "${BACKEND_ROOT}"
      RAGFLOW_BASE_URL="${RAGFLOW_BASE_URL}" \
      RAGFLOW_API_KEY="${RAGFLOW_API_KEY}" \
      COMMON_AGENT_DATABASE_URL="${COMMON_AGENT_DATABASE_URL}" \
      COMMON_AGENT_E2E_BATCH_KNOWLEDGE_NAME="${COMMON_AGENT_E2E_BATCH_KNOWLEDGE_NAME}" \
      COMMON_AGENT_E2E_BATCH_EMPLOYEE_NAME="${COMMON_AGENT_E2E_BATCH_EMPLOYEE_NAME}" \
        "${UV_RUNNER}" run --frozen python -m tests.support.knowledge_batch_e2e_cleanup
    ); then
      echo "知识库批量上传 E2E 数据清理失败，保留验收产物：${ARTIFACT_ROOT}" >&2
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
        "${UV_RUNNER}" run --frozen python -m tests.support.platform_e2e_cleanup
    ); then
      echo "平台 E2E 数据清理失败，保留验收产物：${ARTIFACT_ROOT}" >&2
      cleanup_status=1
    fi
  fi

  if ! (
    cd "${BACKEND_ROOT}"
    COMMON_AGENT_DATABASE_URL="${COMMON_AGENT_DATABASE_URL}" \
      "${UV_RUNNER}" run --frozen python -m tests.support.auth_e2e_state reset
  ); then
    echo "平台 E2E 认证状态清理失败，保留验收产物：${ARTIFACT_ROOT}" >&2
    cleanup_status=1
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
ensure_colima_profile
if [[ "$(docker --context "${DOCKER_CONTEXT_NAME}" inspect \
  --format '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' \
  common-agent-platform-mysql 2>/dev/null || true)" != "running healthy" ]]; then
  PLATFORM_DOCKER_CONTEXT="${DOCKER_CONTEXT_NAME}" \
    "${REPOSITORY_ROOT}/infra/platform/manage.sh" up
fi
export COMMON_AGENT_DATABASE_URL
export COMMON_AGENT_E2E_AUTH_BOOTSTRAP_TOKEN
export COMMON_AGENT_E2E_AUTH_EMAIL
export COMMON_AGENT_E2E_AUTH_PASSWORD
export COMMON_AGENT_E2E_TENANT_NAME
export COMMON_AGENT_E2E_TENANT_EMPLOYEE_NAME
export COMMON_AGENT_E2E_VIEWER_EMAIL
export COMMON_AGENT_E2E_VIEWER_PASSWORD
export COMMON_AGENT_E2E_AUDIT_EMPLOYEE_NAME
export COMMON_AGENT_E2E_MODEL_NAME
export COMMON_AGENT_E2E_EMPLOYEE_MODEL_NAME
export COMMON_AGENT_E2E_EMPLOYEE_MODEL_EMPLOYEE_NAME
export COMMON_AGENT_E2E_GENERIC_CHAT_MODEL_NAME
export COMMON_AGENT_AUTH_BOOTSTRAP_TOKEN="${COMMON_AGENT_E2E_AUTH_BOOTSTRAP_TOKEN}"
export COMMON_AGENT_API_PORT="${API_PORT}"
export COMMON_AGENT_CORS_ORIGINS="http://127.0.0.1:${FRONTEND_PORT}"
export COMMON_AGENT_E2E_API_URL="http://127.0.0.1:${API_PORT}/api/v1"
export COMMON_AGENT_E2E_TRUSTED_ORIGIN="http://127.0.0.1:${FRONTEND_PORT}"
if [[ "${E2E_SUITE}" == "employee-default-model" ]]; then
  export BAILIAN_MODEL="common-agent-invalid-model"
fi
if [[ "${E2E_SUITE}" != "auth" && "${E2E_SUITE}" != "tenant-rbac" && "${E2E_SUITE}" != "audit" && "${E2E_SUITE}" != "demo-chat" && "${E2E_SUITE}" != "frontend-loading" && "${E2E_SUITE}" != "design-system" && "${E2E_SUITE}" != "managed-tools" && "${E2E_SUITE}" != "list-pagination" ]]; then
  export COMMON_AGENT_INTEGRATION_MODE="real"
  if ! curl --fail --silent --show-error \
    "${RAGFLOW_BASE_URL}/api/v1/system/version" >/dev/null 2>&1; then
    "${REPOSITORY_ROOT}/infra/ragflow/manage.sh" up
  fi
  RAGFLOW_API_KEY="$(provision_ragflow_api_key)"
  export RAGFLOW_API_KEY
  export RAGFLOW_BASE_URL
  export RAGFLOW_EXPECTED_VERSION="v0.26.4"
  export RAGFLOW_TIMEOUT_SECONDS="120"
  if [[ "${E2E_SUITE}" == "mvp-acceptance" ]]; then
    (
      cd "${BACKEND_ROOT}"
      COMMON_AGENT_DATABASE_URL="${COMMON_AGENT_DATABASE_URL}" \
      RAGFLOW_BASE_URL="${RAGFLOW_BASE_URL}" \
      RAGFLOW_API_KEY="${RAGFLOW_API_KEY}" \
        "${UV_RUNNER}" run --frozen python -m tests.support.mvp_acceptance_empty
    )
  fi
else
  export COMMON_AGENT_INTEGRATION_MODE="demo"
fi

(
  cd "${BACKEND_ROOT}"
  exec "${UV_RUNNER}" run --frozen python -m common_agent
) >"${BACKEND_LOG}" 2>&1 &
BACKEND_PID=$!
wait_for_url "http://127.0.0.1:${API_PORT}/api/v1/system/health"
(
  cd "${BACKEND_ROOT}"
  "${UV_RUNNER}" run --frozen python -m tests.support.auth_e2e_state reset
)
(
  cd "${BACKEND_ROOT}"
  exec "${UV_RUNNER}" run --frozen python -m common_agent.worker_main
) >"${WORKER_LOG}" 2>&1 &
WORKER_PID=$!
sleep 1
if ! kill -0 "${WORKER_PID}" >/dev/null 2>&1; then
  echo "平台 E2E 独立 Worker 启动失败：${WORKER_LOG}" >&2
  exit 1
fi

(
  cd "${FRONTEND_ROOT}"
  unset RAGFLOW_API_KEY
  if [[ "${E2E_SUITE}" == "frontend-loading" || "${E2E_SUITE}" == "design-system" || "${E2E_SUITE}" == "managed-tools" || "${E2E_SUITE}" == "model-configurations" || "${E2E_SUITE}" == "employee-default-model" || "${E2E_SUITE}" == "generic-chat-models" || "${E2E_SUITE}" == "knowledge-batch" ]]; then
    VITE_API_BASE_URL="http://127.0.0.1:${API_PORT}/api/v1" pnpm build
    exec env VITE_API_BASE_URL="http://127.0.0.1:${API_PORT}/api/v1" \
      pnpm exec vite preview --host 127.0.0.1 --port "${FRONTEND_PORT}" --strictPort
  fi
  exec env VITE_API_BASE_URL="http://127.0.0.1:${API_PORT}/api/v1" \
    pnpm exec vite --host 127.0.0.1 --port "${FRONTEND_PORT}" --strictPort
) >"${FRONTEND_LOG}" 2>&1 &
FRONTEND_PID=$!
wait_for_url "http://127.0.0.1:${FRONTEND_PORT}/knowledge-bases"

(
  cd "${FRONTEND_ROOT}"
  if [[ "${E2E_SUITE}" == "auth" ]]; then
    COMMON_AGENT_E2E_FRONTEND_URL="http://127.0.0.1:${FRONTEND_PORT}" \
    COMMON_AGENT_E2E_ARTIFACT_DIR="${ARTIFACT_ROOT}/playwright" \
      exec pnpm exec playwright test e2e/auth.spec.ts --config playwright.config.ts
  elif [[ "${E2E_SUITE}" == "tenant-rbac" ]]; then
    COMMON_AGENT_E2E_FRONTEND_URL="http://127.0.0.1:${FRONTEND_PORT}" \
    COMMON_AGENT_E2E_ARTIFACT_DIR="${ARTIFACT_ROOT}/playwright" \
      exec pnpm exec playwright test e2e/tenant-rbac.spec.ts --config playwright.config.ts
  elif [[ "${E2E_SUITE}" == "audit" ]]; then
    COMMON_AGENT_E2E_AUDIT_EMPLOYEE_NAME="${COMMON_AGENT_E2E_AUDIT_EMPLOYEE_NAME}" \
    COMMON_AGENT_E2E_FRONTEND_URL="http://127.0.0.1:${FRONTEND_PORT}" \
    COMMON_AGENT_E2E_ARTIFACT_DIR="${ARTIFACT_ROOT}/playwright" \
      exec pnpm exec playwright test e2e/audit.spec.ts --config playwright.config.ts
  elif [[ "${E2E_SUITE}" == "model-configurations" ]]; then
    COMMON_AGENT_E2E_MODEL_NAME="${COMMON_AGENT_E2E_MODEL_NAME}" \
    COMMON_AGENT_E2E_FRONTEND_URL="http://127.0.0.1:${FRONTEND_PORT}" \
    COMMON_AGENT_E2E_ARTIFACT_DIR="${ARTIFACT_ROOT}/playwright" \
      exec pnpm exec playwright test \
        e2e/model-configurations.spec.ts --config playwright.config.ts
  elif [[ "${E2E_SUITE}" == "employee-default-model" ]]; then
    COMMON_AGENT_E2E_EMPLOYEE_MODEL_NAME="${COMMON_AGENT_E2E_EMPLOYEE_MODEL_NAME}" \
    COMMON_AGENT_E2E_EMPLOYEE_MODEL_EMPLOYEE_NAME="${COMMON_AGENT_E2E_EMPLOYEE_MODEL_EMPLOYEE_NAME}" \
    COMMON_AGENT_E2E_FRONTEND_URL="http://127.0.0.1:${FRONTEND_PORT}" \
    COMMON_AGENT_E2E_ARTIFACT_DIR="${ARTIFACT_ROOT}/playwright" \
      exec pnpm exec playwright test \
        e2e/employee-default-model.spec.ts --config playwright.config.ts
  elif [[ "${E2E_SUITE}" == "generic-chat-models" ]]; then
    COMMON_AGENT_E2E_GENERIC_CHAT_MODEL_NAME="${COMMON_AGENT_E2E_GENERIC_CHAT_MODEL_NAME}" \
    COMMON_AGENT_E2E_FRONTEND_URL="http://127.0.0.1:${FRONTEND_PORT}" \
    COMMON_AGENT_E2E_ARTIFACT_DIR="${ARTIFACT_ROOT}/playwright" \
      exec pnpm exec playwright test \
        e2e/generic-chat-models.spec.ts --config playwright.config.ts
  elif [[ "${E2E_SUITE}" == "platform" ]]; then
    COMMON_AGENT_E2E_KNOWLEDGE_NAME="${COMMON_AGENT_E2E_KNOWLEDGE_NAME}" \
    COMMON_AGENT_E2E_EMPLOYEE_NAME="${COMMON_AGENT_E2E_EMPLOYEE_NAME}" \
    COMMON_AGENT_E2E_EMPLOYEE_KNOWLEDGE_NAME="${COMMON_AGENT_E2E_EMPLOYEE_KNOWLEDGE_NAME}" \
    COMMON_AGENT_E2E_FRONTEND_URL="http://127.0.0.1:${FRONTEND_PORT}" \
    COMMON_AGENT_E2E_ARTIFACT_DIR="${ARTIFACT_ROOT}/playwright" \
      exec pnpm exec playwright test \
        e2e/employees.spec.ts e2e/knowledge-bases.spec.ts \
        --config playwright.config.ts
  elif [[ "${E2E_SUITE}" == "frontend-loading" ]]; then
    COMMON_AGENT_E2E_FRONTEND_URL="http://127.0.0.1:${FRONTEND_PORT}" \
    COMMON_AGENT_E2E_ARTIFACT_DIR="${ARTIFACT_ROOT}/playwright" \
      exec pnpm exec playwright test e2e/entry-loading.spec.ts --config playwright.config.ts
  elif [[ "${E2E_SUITE}" == "design-system" ]]; then
    COMMON_AGENT_E2E_FRONTEND_URL="http://127.0.0.1:${FRONTEND_PORT}" \
    COMMON_AGENT_E2E_ARTIFACT_DIR="${ARTIFACT_ROOT}/playwright" \
      exec pnpm exec playwright test \
        e2e/design-system.spec.ts e2e/entry-loading.spec.ts \
        --config playwright.config.ts
  elif [[ "${E2E_SUITE}" == "managed-tools" ]]; then
    COMMON_AGENT_E2E_FRONTEND_URL="http://127.0.0.1:${FRONTEND_PORT}" \
    COMMON_AGENT_E2E_ARTIFACT_DIR="${ARTIFACT_ROOT}/playwright" \
      exec pnpm exec playwright test e2e/tools.spec.ts --config playwright.config.ts
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
  elif [[ "${E2E_SUITE}" == "resource-deletion" ]]; then
    COMMON_AGENT_E2E_DELETE_KNOWLEDGE_NAME="${COMMON_AGENT_E2E_DELETE_KNOWLEDGE_NAME}" \
    COMMON_AGENT_E2E_DELETE_EMPLOYEE_NAME="${COMMON_AGENT_E2E_DELETE_EMPLOYEE_NAME}" \
    COMMON_AGENT_E2E_DELETE_WORKFLOW_NAME="${COMMON_AGENT_E2E_DELETE_WORKFLOW_NAME}" \
    COMMON_AGENT_E2E_FRONTEND_URL="http://127.0.0.1:${FRONTEND_PORT}" \
    COMMON_AGENT_E2E_ARTIFACT_DIR="${ARTIFACT_ROOT}/playwright" \
      exec pnpm exec playwright test e2e/resource-deletion.spec.ts --config playwright.config.ts
  elif [[ "${E2E_SUITE}" == "list-pagination" ]]; then
    COMMON_AGENT_E2E_LIST_PREFIX="${COMMON_AGENT_E2E_LIST_PREFIX}" \
    COMMON_AGENT_E2E_API_URL="http://127.0.0.1:${API_PORT}/api/v1" \
    COMMON_AGENT_E2E_FRONTEND_URL="http://127.0.0.1:${FRONTEND_PORT}" \
    COMMON_AGENT_E2E_ARTIFACT_DIR="${ARTIFACT_ROOT}/playwright" \
      exec pnpm exec playwright test e2e/list-pagination.spec.ts --config playwright.config.ts
  elif [[ "${E2E_SUITE}" == "knowledge-pagination" ]]; then
    COMMON_AGENT_E2E_KNOWLEDGE_PAGE_PREFIX="${COMMON_AGENT_E2E_KNOWLEDGE_PAGE_PREFIX}" \
    COMMON_AGENT_E2E_API_URL="http://127.0.0.1:${API_PORT}/api/v1" \
    COMMON_AGENT_E2E_FRONTEND_URL="http://127.0.0.1:${FRONTEND_PORT}" \
    COMMON_AGENT_E2E_ARTIFACT_DIR="${ARTIFACT_ROOT}/playwright" \
      exec pnpm exec playwright test e2e/knowledge-pagination.spec.ts --config playwright.config.ts
  elif [[ "${E2E_SUITE}" == "knowledge-batch" ]]; then
    COMMON_AGENT_E2E_BATCH_KNOWLEDGE_NAME="${COMMON_AGENT_E2E_BATCH_KNOWLEDGE_NAME}" \
    COMMON_AGENT_E2E_BATCH_EMPLOYEE_NAME="${COMMON_AGENT_E2E_BATCH_EMPLOYEE_NAME}" \
    COMMON_AGENT_E2E_FRONTEND_URL="http://127.0.0.1:${FRONTEND_PORT}" \
    COMMON_AGENT_E2E_ARTIFACT_DIR="${ARTIFACT_ROOT}/playwright" \
      exec pnpm exec playwright test e2e/knowledge-batch.spec.ts --config playwright.config.ts
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
