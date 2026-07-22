#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DOCKER_CONTEXT="${COMMON_AGENT_SECURITY_DOCKER_CONTEXT:-colima-common-agent-dev}"
REVIEWED_STATIC_SQL="backend/migrations/versions/20260722_0019_employee_default_models.py"
REVIEWED_STATIC_SQL_RULE="python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text"
REVIEWED_STATIC_SQL_CHECKSUMS="security/semgrep-reviewed-static-sql.sha256"
THIRD_PARTY_BASELINE="${COMMON_AGENT_SECURITY_THIRD_PARTY_BASELINE:-security/third-party-images.json}"

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

scan_third_party_images() {
  [[ "$#" -eq 0 ]] || fail "用法：scripts/security-scan.sh third-party"
  require_command docker
  require_command jq
  require_command shasum
  require_command trivy

  local baseline_path="${THIRD_PARTY_BASELINE}"
  if [[ "${baseline_path}" != /* ]]; then
    baseline_path="${REPOSITORY_ROOT}/${baseline_path}"
  fi
  [[ -f "${baseline_path}" ]] || fail "缺少第三方镜像审阅基线：${baseline_path}"
  jq -e '
    .schema_version == 1 and
    (.images | type == "array" and length > 0) and
    all(.images[];
      (.component | type == "string" and length > 0) and
      (.image | type == "string" and length > 0) and
      (.digest | type == "string" and test("@sha256:[0-9a-z]+$")) and
      (.high | type == "number" and . >= 0) and
      (.critical | type == "number" and . >= 0) and
      (.findings_sha256 | type == "string" and test("^[0-9a-f]{64}$")))
  ' "${baseline_path}" >/dev/null || fail "第三方镜像审阅基线格式无效"

  local docker_host scan_root
  docker_host="$(docker context inspect "${DOCKER_CONTEXT}" --format '{{.Endpoints.docker.Host}}')"
  scan_root="$(mktemp -d "${TMPDIR:-/tmp}/common-agent-third-party-scan.XXXXXX")"
  cleanup_third_party_scan() {
    find "${scan_root}" -type f -delete
    rmdir "${scan_root}"
  }
  trap cleanup_third_party_scan EXIT INT TERM

  local component image expected_digest expected_high expected_critical expected_sha
  while IFS=$'\t' read -r component image expected_digest expected_high expected_critical expected_sha; do
    local report normalized actual_artifact actual_high actual_critical actual_sha
    report="${scan_root}/$(printf '%s' "${component}" | tr -cs 'A-Za-z0-9._-' '_').json"
    normalized="${report%.json}.normalized.json"
    DOCKER_HOST="${docker_host}" trivy image \
      --quiet \
      --scanners vuln,secret \
      --severity HIGH,CRITICAL \
      --ignore-unfixed \
      --format json \
      --output "${report}" \
      "${image}"

    actual_artifact="$(jq -r '.ArtifactName // ""' "${report}")"
    [[ "${actual_artifact}" == "${image}" ]] || fail "第三方镜像扫描目标漂移：${component}"
    jq -e --arg digest "${expected_digest}" \
      '(.Metadata.RepoDigests // []) | index($digest) != null' \
      "${report}" >/dev/null || fail "第三方镜像 digest 漂移：${component}"

    jq -cS '
      [.Results[]?.Vulnerabilities[]?
       | select(.Severity == "HIGH" or .Severity == "CRITICAL")
       | {
           id: .VulnerabilityID,
           package: .PkgName,
           installed_version: .InstalledVersion,
           fixed_version: (.FixedVersion // ""),
           severity: .Severity
         }]
      | unique_by([.id, .package, .installed_version, .fixed_version, .severity])
      | sort_by(.severity, .id, .package, .installed_version, .fixed_version)
    ' "${report}" >"${normalized}"
    actual_high="$(jq '[.[] | select(.severity == "HIGH")] | length' "${normalized}")"
    actual_critical="$(jq '[.[] | select(.severity == "CRITICAL")] | length' "${normalized}")"
    actual_sha="$(shasum -a 256 "${normalized}" | awk '{print $1}')"

    [[ "${actual_high}" == "${expected_high}" ]] || fail "第三方镜像 High 结果漂移：${component}"
    [[ "${actual_critical}" == "${expected_critical}" ]] || fail "第三方镜像 Critical 结果漂移：${component}"
    [[ "${actual_sha}" == "${expected_sha}" ]] || fail "第三方镜像漏洞明细漂移：${component}"
    echo "第三方镜像审阅基线通过：${component}（High=${actual_high}, Critical=${actual_critical}）"
  done < <(
    jq -r '.images[] | [.component, .image, .digest, .high, .critical, .findings_sha256] | @tsv' \
      "${baseline_path}"
  )

  cleanup_third_party_scan
  trap - EXIT INT TERM
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
    third-party)
      shift
      scan_third_party_images "$@"
      ;;
    all)
      shift
      scan_source
      scan_images "$@"
      scan_third_party_images
      ;;
    *)
      fail "用法：scripts/security-scan.sh {source|images <api-image> <web-image>|third-party|all <api-image> <web-image>}"
      ;;
  esac
}

main "$@"
