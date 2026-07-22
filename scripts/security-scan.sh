#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DOCKER_CONTEXT="${COMMON_AGENT_SECURITY_DOCKER_CONTEXT:-colima-common-agent-dev}"
REVIEWED_STATIC_SQL="backend/migrations/versions/20260722_0019_employee_default_models.py"
REVIEWED_STATIC_SQL_RULE="python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text"
REVIEWED_STATIC_SQL_CHECKSUMS="security/semgrep-reviewed-static-sql.sha256"

fail() {
  echo "$1" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "缺少安全扫描工具：$1"
}

scan_source() {
  require_command semgrep
  require_command trivy
  require_command jq
  require_command shasum

  (
    cd "${REPOSITORY_ROOT}"
    "${SCRIPT_DIR}/test-secrets.sh"
    shasum -a 256 -c "${REVIEWED_STATIC_SQL_CHECKSUMS}"
    semgrep scan \
      --config p/default \
      --error \
      --metrics=off \
      --quiet \
      --exclude third_party \
      --exclude .local \
      --exclude frontend/node_modules \
      --exclude backend/.venv \
      --exclude "${REVIEWED_STATIC_SQL}" \
      .

    local reviewed_report
    reviewed_report="$(mktemp "${TMPDIR:-/tmp}/common-agent-semgrep-reviewed.XXXXXX.json")"
    trap 'rm -f "${reviewed_report}"' EXIT INT TERM
    semgrep scan \
      --config p/default \
      --metrics=off \
      --quiet \
      --json \
      --output "${reviewed_report}" \
      "${REVIEWED_STATIC_SQL}"
    jq -e \
      --arg rule "${REVIEWED_STATIC_SQL_RULE}" \
      --arg path "${REVIEWED_STATIC_SQL}" \
      '(.results | length == 2) and
       ([.results[]
         | select(.check_id == $rule and .path == $path)
         | .start.line] | sort == [36, 125])' \
      "${reviewed_report}" >/dev/null || fail "静态 SQL 审阅例外发生漂移"
    rm -f "${reviewed_report}"
    trap - EXIT INT TERM

    trivy fs \
      --quiet \
      --scanners vuln,secret \
      --severity HIGH,CRITICAL \
      --ignore-unfixed \
      --exit-code 1 \
      --skip-dirs .git \
      --skip-dirs .local \
      --skip-dirs third_party \
      --skip-dirs frontend/node_modules \
      --skip-dirs backend/.venv \
      --skip-files backend/.env.demo \
      .

    local config_target
    for config_target in \
      backend/Dockerfile \
      frontend/Dockerfile \
      infra/production/compose.yaml \
      infra/production/ragflow-node.compose.yaml; do
      trivy config \
        --quiet \
        --severity HIGH,CRITICAL \
        --exit-code 1 \
        "${config_target}"
    done

    bash infra/production/test-manage.sh
  )
}

scan_images() {
  [[ "$#" -eq 2 ]] || fail "用法：scripts/security-scan.sh images <api-image> <web-image>"
  local api_image="$1"
  local web_image="$2"
  [[ "${api_image}" == common-agent-api:* ]] || fail "API 镜像必须使用 common-agent-api 前缀"
  [[ "${web_image}" == common-agent-web:* ]] || fail "Web 镜像必须使用 common-agent-web 前缀"

  require_command docker
  require_command trivy

  local docker_host
  docker_host="$(docker context inspect "${DOCKER_CONTEXT}" --format '{{.Endpoints.docker.Host}}')"

  DOCKER_HOST="${docker_host}" trivy image \
    --quiet \
    --scanners vuln,secret \
    --severity HIGH,CRITICAL \
    --ignore-unfixed \
    --exit-code 1 \
    "${api_image}"
  DOCKER_HOST="${docker_host}" trivy image \
    --quiet \
    --scanners vuln,secret \
    --severity HIGH,CRITICAL \
    --ignore-unfixed \
    --exit-code 1 \
    "${web_image}"
}

main() {
  local action="${1:-}"
  case "${action}" in
    source)
      [[ "$#" -eq 1 ]] || fail "用法：scripts/security-scan.sh source"
      scan_source
      ;;
    images)
      shift
      scan_images "$@"
      ;;
    all)
      shift
      scan_source
      scan_images "$@"
      ;;
    *)
      fail "用法：scripts/security-scan.sh {source|images <api-image> <web-image>|all <api-image> <web-image>}"
      ;;
  esac
}

main "$@"
