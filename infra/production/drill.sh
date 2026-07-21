#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
MANAGER="${SCRIPT_DIR}/manage.sh"
RAGFLOW_MANAGER="${REPOSITORY_ROOT}/infra/ragflow/manage.sh"
RAGFLOW_TOKEN_FILE="${REPOSITORY_ROOT}/.local/dev/common-agent-dev/secrets/ragflow-api-token"
AUTH_TOKEN_FILE="${REPOSITORY_ROOT}/.local/dev/common-agent-dev/secrets/owner-bootstrap-token"
DEMO_ENV_FILE="${REPOSITORY_ROOT}/backend/.env.demo"
DOCKER_CONTEXT_NAME="${COMMON_AGENT_PRODUCTION_DOCKER_CONTEXT:-colima-common-agent-dev}"
RAGFLOW_WAS_RUNNING=0
STATE_ROOT_IS_TEMPORARY=0
if [[ -n "${COMMON_AGENT_PRODUCTION_STATE_ROOT:-}" ]]; then
  STATE_ROOT="${COMMON_AGENT_PRODUCTION_STATE_ROOT}"
else
  mkdir -p "${REPOSITORY_ROOT}/.local"
  STATE_ROOT="$(mktemp -d "${REPOSITORY_ROOT}/.local/production-drill.XXXXXX")"
  STATE_ROOT_IS_TEMPORARY=1
fi
export COMMON_AGENT_PRODUCTION_STATE_ROOT="${STATE_ROOT}"
export COMMON_AGENT_RAGFLOW_EDGE_MODE=local-shared-network

cleanup() {
  "${MANAGER}" down >/dev/null 2>&1 || true
  docker --context "${DOCKER_CONTEXT_NAME}" volume rm \
    common-agent-production-platform-mysql-data >/dev/null 2>&1 || true
  if ((RAGFLOW_WAS_RUNNING == 0)); then
    RAGFLOW_DOCKER_CONTEXT="${DOCKER_CONTEXT_NAME}" "${RAGFLOW_MANAGER}" stop >/dev/null 2>&1 || true
  fi
  if ((STATE_ROOT_IS_TEMPORARY == 1)); then
    rm -rf -- "${STATE_ROOT}"
  fi
}
trap cleanup EXIT INT TERM

fail() {
  echo "$1" >&2
  exit 1
}

read_demo_value() {
  local key="$1"
  sed -n "s/^${key}=//p" "${DEMO_ENV_FILE}" | tail -n 1
}

write_runtime_configuration() {
  local ragflow_token auth_token database_password database_root_password
  local bailian_api_key bailian_base_url bailian_model
  [[ -f "${RAGFLOW_TOKEN_FILE}" && ! -L "${RAGFLOW_TOKEN_FILE}" ]] || fail "RAGFlow token 不存在"
  [[ -f "${AUTH_TOKEN_FILE}" && ! -L "${AUTH_TOKEN_FILE}" ]] || fail "管理员引导 token 不存在"
  IFS= read -r ragflow_token <"${RAGFLOW_TOKEN_FILE}"
  IFS= read -r auth_token <"${AUTH_TOKEN_FILE}"
  bailian_api_key="$(read_demo_value BAILIAN_API_KEY)"
  bailian_base_url="$(read_demo_value BAILIAN_BASE_URL)"
  bailian_model="$(read_demo_value BAILIAN_MODEL)"
  [[ -n "${ragflow_token}" && -n "${auth_token}" && -n "${bailian_api_key}" ]] || \
    fail "正式依赖凭据不完整"
  database_password="$(openssl rand -hex 24)"
  database_root_password="$(openssl rand -hex 24)"

  mkdir -p "${STATE_ROOT}"
  chmod 700 "${STATE_ROOT}"
  umask 077
  {
    echo 'COMMON_AGENT_INTEGRATION_MODE=real'
    echo 'COMMON_AGENT_CORS_ORIGINS=https://common-agent.test:18443'
    echo 'COMMON_AGENT_AUTH_COOKIE_SECURE=true'
    echo 'COMMON_AGENT_AUTH_SESSION_IDLE_SECONDS=1800'
    echo 'COMMON_AGENT_AUTH_SESSION_ABSOLUTE_SECONDS=43200'
    echo 'RAGFLOW_BASE_URL=https://common-agent-production-ragflow-edge:9443'
    echo 'RAGFLOW_CA_BUNDLE=/run/common-agent/tls/ca-bundle.crt'
    echo 'RAGFLOW_EXPECTED_VERSION=v0.26.4'
    echo 'RAGFLOW_EMBEDDING_MODEL=text-embedding-v4@common-agent-embedding@OpenAI-API-Compatible'
    echo 'RAGFLOW_RERANK_MODEL=qwen3-rerank@common-agent-rerank@OpenAI-API-Compatible'
    echo 'RAGFLOW_TIMEOUT_SECONDS=120'
    printf 'BAILIAN_BASE_URL=%s\n' "${bailian_base_url}"
    printf 'BAILIAN_MODEL=%s\n' "${bailian_model}"
  } >"${STATE_ROOT}/config.env"
  {
    printf 'MYSQL_ROOT_PASSWORD=%s\n' "${database_root_password}"
    echo 'MYSQL_DATABASE=common_agent'
    echo 'MYSQL_USER=common_agent'
    printf 'MYSQL_PASSWORD=%s\n' "${database_password}"
    printf 'COMMON_AGENT_DATABASE_URL=mysql+aiomysql://common_agent:%s@platform-mysql:3306/common_agent?charset=utf8mb4\n' "${database_password}"
    printf 'COMMON_AGENT_AUTH_BOOTSTRAP_TOKEN=%s\n' "${auth_token}"
    printf 'RAGFLOW_API_KEY=%s\n' "${ragflow_token}"
    printf 'BAILIAN_API_KEY=%s\n' "${bailian_api_key}"
  } >"${STATE_ROOT}/secrets.env"
  chmod 600 "${STATE_ROOT}/config.env" "${STATE_ROOT}/secrets.env"
}

run_formal_page_smoke() {
  # 与 S10-06 backup-recovery 正式页面验证保持同一 UI/API 路径，不直连 RAGFlow。
  local response auth_token
  response="$(curl --fail --silent --show-error --noproxy '*' \
    --cacert "${STATE_ROOT}/tls/ca.crt" \
    --resolve 'common-agent.test:18443:127.0.0.1' \
    'https://common-agent.test:18443/knowledge-bases')"
  [[ "${response}" == *'<div id="root">'* ]] || fail "正式页面入口不可用"
  auth_token="$(sed -n 's/^COMMON_AGENT_AUTH_BOOTSTRAP_TOKEN=//p' "${STATE_ROOT}/secrets.env")"
  [[ -n "${auth_token}" ]] || fail "浏览器验收缺少管理员引导 token"
  (
    cd "${REPOSITORY_ROOT}/frontend"
    COMMON_AGENT_E2E_FRONTEND_URL='https://127.0.0.1:18443' \
    COMMON_AGENT_E2E_API_URL='https://127.0.0.1:18443/api/v1' \
    COMMON_AGENT_E2E_TRUSTED_ORIGIN='https://common-agent.test:18443' \
    COMMON_AGENT_E2E_IGNORE_HTTPS_ERRORS=true \
    COMMON_AGENT_E2E_AUTH_BOOTSTRAP_TOKEN="${auth_token}" \
    COMMON_AGENT_E2E_AUTH_EMAIL='production-drill@example.com' \
    COMMON_AGENT_E2E_AUTH_PASSWORD='Production-Drill-2026!' \
      pnpm exec playwright test entry-loading.spec.ts
  )
}

exercise_failure_and_rollback() {
  local active_slot
  "${MANAGER}" build
  "${MANAGER}" init-tls
  "${MANAGER}" preflight
  "${MANAGER}" migrate
  "${MANAGER}" rollout
  "${MANAGER}" verify

  active_slot="$(sed -n 's/^active_slot=//p' "${STATE_ROOT}/deployment.env")"
  [[ "${active_slot}" == "blue" || "${active_slot}" == "green" ]] || fail "active slot 状态无效"
  docker --context "${DOCKER_CONTEXT_NAME}" stop \
    "common-agent-production-api-${active_slot}" >/dev/null
  if curl --fail --silent --show-error --max-time 10 --noproxy '*' \
    --cacert "${STATE_ROOT}/tls/ca.crt" \
    --resolve 'common-agent.test:18443:127.0.0.1' \
    'https://common-agent.test:18443/api/v1/system/health' >/dev/null 2>&1; then
    fail "故障注入后流量仍错误地通过失效 API"
  fi
  "${MANAGER}" rollback
  "${MANAGER}" verify
}

if [[ "$(docker --context "${DOCKER_CONTEXT_NAME}" inspect \
  --format '{{.State.Running}}' common-agent-ragflow-api 2>/dev/null || true)" == "true" ]]; then
  RAGFLOW_WAS_RUNNING=1
fi
RAGFLOW_DOCKER_CONTEXT="${DOCKER_CONTEXT_NAME}" "${RAGFLOW_MANAGER}" prepare
RAGFLOW_DOCKER_CONTEXT="${DOCKER_CONTEXT_NAME}" "${RAGFLOW_MANAGER}" up
write_runtime_configuration
"${MANAGER}" build
"${MANAGER}" init-tls
"${MANAGER}" preflight
"${MANAGER}" migrate
"${MANAGER}" rollout
"${MANAGER}" verify
run_formal_page_smoke
exercise_failure_and_rollback

echo "本地双节点生产同路径演练通过"
