#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SECURITY_SCAN="${SCRIPT_DIR}/security-scan.sh"

fail() {
  echo "$1" >&2
  exit 1
}

[[ -x "${SECURITY_SCAN}" ]] || fail "缺少可执行的安全扫描入口"

TEST_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/common-agent-security-scan-test.XXXXXX")"
TEST_BIN="${TEST_ROOT}/bin"
TEST_LOG="${TEST_ROOT}/calls.log"
TEST_THIRD_PARTY_BASELINE="${TEST_ROOT}/third-party-images.json"
mkdir -p "${TEST_BIN}"
trap 'rm -rf "${TEST_ROOT}"' EXIT INT TERM

cat >"${TEST_BIN}/semgrep" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
printf 'semgrep %s\n' "$*" >>"${COMMON_AGENT_SECURITY_SCAN_TEST_LOG}"
output_file=""
previous=""
for argument in "$@"; do
  if [[ "${previous}" == "--output" ]]; then
    output_file="${argument}"
    break
  fi
  previous="${argument}"
done
if [[ -n "${output_file}" ]]; then
  if [[ "${COMMON_AGENT_SECURITY_SCAN_BAD_REVIEW:-}" == "1" ]]; then
    printf '{"results":[]}\n' >"${output_file}"
  else
    cat >"${output_file}" <<'JSON'
{"results":[{"check_id":"python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text","path":"backend/migrations/versions/20260722_0019_employee_default_models.py","start":{"line":36}},{"check_id":"python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text","path":"backend/migrations/versions/20260722_0019_employee_default_models.py","start":{"line":125}}]}
JSON
  fi
fi
EOF

cat >"${TEST_BIN}/trivy" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
printf 'trivy %s\n' "$*" >>"${COMMON_AGENT_SECURITY_SCAN_TEST_LOG}"
if [[ -n "${COMMON_AGENT_SECURITY_SCAN_FAIL_ON:-}" && "$*" == *"${COMMON_AGENT_SECURITY_SCAN_FAIL_ON}"* ]]; then
  exit 42
fi
output_file=""
previous=""
for argument in "$@"; do
  if [[ "${previous}" == "--output" ]]; then
    output_file="${argument}"
    break
  fi
  previous="${argument}"
done
if [[ -n "${output_file}" ]]; then
  severity="HIGH"
  if [[ "${COMMON_AGENT_SECURITY_SCAN_TAMPER:-}" == "1" ]]; then
    severity="CRITICAL"
  fi
  cat >"${output_file}" <<JSON
{"ArtifactName":"vendor/example:1","Metadata":{"RepoDigests":["vendor/example@sha256:test"]},"Results":[{"Vulnerabilities":[{"VulnerabilityID":"CVE-TEST-0001","PkgName":"test-package","InstalledVersion":"1.0.0","FixedVersion":"1.0.1","Severity":"${severity}"}]}]}
JSON
fi
EOF

chmod +x "${TEST_BIN}/semgrep" "${TEST_BIN}/trivy"

canonical_findings="${TEST_ROOT}/canonical-findings.json"
printf '%s\n' '[{"fixed_version":"1.0.1","id":"CVE-TEST-0001","installed_version":"1.0.0","package":"test-package","severity":"HIGH"}]' >"${canonical_findings}"
findings_sha256="$(shasum -a 256 "${canonical_findings}" | awk '{print $1}')"
cat >"${TEST_THIRD_PARTY_BASELINE}" <<JSON
{
  "schema_version": 1,
  "images": [
    {
      "component": "test-component",
      "image": "vendor/example:1",
      "digest": "vendor/example@sha256:test",
      "high": 1,
      "critical": 0,
      "findings_sha256": "${findings_sha256}"
    }
  ]
}
JSON

PATH="${TEST_BIN}:${PATH}" \
  COMMON_AGENT_SECURITY_SCAN_TEST_LOG="${TEST_LOG}" \
  "${SECURITY_SCAN}" source

grep -Fq 'semgrep scan --config p/default' "${TEST_LOG}" || fail "源码扫描没有执行 Semgrep 默认规则集"
grep -Fq -- '--exclude third_party' "${TEST_LOG}" || fail "Semgrep 没有排除只读第三方源码"
grep -Fq -- '--exclude backend/migrations/versions/20260722_0019_employee_default_models.py' "${TEST_LOG}" || fail "Semgrep 没有隔离已审阅的静态 SQL 误报"
grep -Fq -- '--json --output' "${TEST_LOG}" || fail "Semgrep 没有复扫已审阅的静态 SQL 迁移"
grep -Fq 'trivy fs' "${TEST_LOG}" || fail "源码扫描没有执行 Trivy 文件系统门禁"
grep -Fq -- '--skip-files backend/.env.demo' "${TEST_LOG}" || fail "Trivy 没有遵守获准 Demo Key 的单文件例外"
grep -Fq 'trivy config' "${TEST_LOG}" || fail "源码扫描没有执行 IaC 配置门禁"
grep -Fq 'backend/Dockerfile' "${TEST_LOG}" || fail "IaC 门禁没有覆盖后端 Dockerfile"
grep -Fq 'frontend/Dockerfile' "${TEST_LOG}" || fail "IaC 门禁没有覆盖前端 Dockerfile"
grep -Fq 'infra/production/compose.yaml' "${TEST_LOG}" || fail "IaC 门禁没有覆盖生产 Compose"
grep -Fq 'infra/production/ragflow-node.compose.yaml' "${TEST_LOG}" || fail "IaC 门禁没有覆盖 RAGFlow 边缘 Compose"

if PATH="${TEST_BIN}:${PATH}" \
  COMMON_AGENT_SECURITY_SCAN_TEST_LOG="${TEST_LOG}" \
  COMMON_AGENT_SECURITY_SCAN_BAD_REVIEW=1 \
  "${SECURITY_SCAN}" source >/dev/null 2>&1; then
  fail "静态 SQL 审阅结果漂移被错误放行"
fi

: >"${TEST_LOG}"
PATH="${TEST_BIN}:${PATH}" \
  COMMON_AGENT_SECURITY_SCAN_TEST_LOG="${TEST_LOG}" \
  "${SECURITY_SCAN}" images common-agent-api:test common-agent-web:test

[[ "$(grep -c '^trivy image ' "${TEST_LOG}")" -eq 2 ]] || fail "镜像门禁没有且仅扫描两个业务镜像"
grep -Fq -- '--ignore-unfixed' "${TEST_LOG}" || fail "镜像门禁没有区分可修复与上游未修复漏洞"
grep -Fq 'common-agent-api:test' "${TEST_LOG}" || fail "镜像门禁遗漏 API 镜像"
grep -Fq 'common-agent-web:test' "${TEST_LOG}" || fail "镜像门禁遗漏 Web 镜像"

if PATH="${TEST_BIN}:${PATH}" \
  COMMON_AGENT_SECURITY_SCAN_TEST_LOG="${TEST_LOG}" \
  COMMON_AGENT_SECURITY_SCAN_FAIL_ON='common-agent-api:bad' \
  "${SECURITY_SCAN}" images common-agent-api:bad common-agent-web:test; then
  fail "镜像漏洞扫描失败被错误吞掉"
fi

if "${SECURITY_SCAN}" images common-agent-api:test >/dev/null 2>&1; then
  fail "镜像门禁错误接受缺失的 Web 镜像参数"
fi

: >"${TEST_LOG}"
PATH="${TEST_BIN}:${PATH}" \
  COMMON_AGENT_SECURITY_SCAN_TEST_LOG="${TEST_LOG}" \
  COMMON_AGENT_SECURITY_THIRD_PARTY_BASELINE="${TEST_THIRD_PARTY_BASELINE}" \
  "${SECURITY_SCAN}" third-party

[[ "$(grep -c '^trivy image ' "${TEST_LOG}")" -eq 1 ]] || fail "第三方镜像门禁没有逐个扫描基线镜像"
grep -Fq -- '--format json --output' "${TEST_LOG}" || fail "第三方镜像门禁没有生成结构化扫描报告"
grep -Fq 'vendor/example:1' "${TEST_LOG}" || fail "第三方镜像门禁遗漏基线镜像"

if PATH="${TEST_BIN}:${PATH}" \
  COMMON_AGENT_SECURITY_SCAN_TEST_LOG="${TEST_LOG}" \
  COMMON_AGENT_SECURITY_THIRD_PARTY_BASELINE="${TEST_THIRD_PARTY_BASELINE}" \
  COMMON_AGENT_SECURITY_SCAN_TAMPER=1 \
  "${SECURITY_SCAN}" third-party >/dev/null 2>&1; then
  fail "第三方漏洞结果漂移被错误放行"
fi

: >"${TEST_LOG}"
PATH="${TEST_BIN}:${PATH}" \
  COMMON_AGENT_SECURITY_SCAN_TEST_LOG="${TEST_LOG}" \
  COMMON_AGENT_SECURITY_THIRD_PARTY_BASELINE="${TEST_THIRD_PARTY_BASELINE}" \
  "${SECURITY_SCAN}" all common-agent-api:test common-agent-web:test

[[ "$(grep -c '^trivy image ' "${TEST_LOG}")" -eq 3 ]] || fail "完整安全门禁没有覆盖业务与第三方镜像"

if "${SECURITY_SCAN}" unknown >/dev/null 2>&1; then
  fail "安全扫描入口错误接受未知动作"
fi

echo "安全扫描入口契约通过"
