#!/usr/bin/env bash
# shellcheck disable=SC2016 # Contract assertions intentionally match literal shell expressions.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNNER="${SCRIPT_DIR}/test-platform-e2e.sh"

fail() {
  echo "$1" >&2
  exit 1
}

grep -Fq 'LIGHT_E2E_MEMORY_GIB=12' "${RUNNER}" || \
  fail "轻量 E2E 没有固定 12 GiB Colima 预算"
grep -Fq 'REAL_E2E_MEMORY_GIB=32' "${RUNNER}" || \
  fail "真实 E2E 没有固定 32 GiB Colima 预算"
grep -Fq 'current_memory_bytes=' "${RUNNER}" || \
  fail "E2E 入口没有检查正在运行的 Colima 实际内存"
grep -Fq 'current_memory_bytes + 1073741823' "${RUNNER}" || \
  fail "E2E 入口没有按 GiB 向上折算 Docker 预留内存"
grep -Fq 'colima stop common-agent-dev' "${RUNNER}" || \
  fail "E2E 入口不能在资源档位不符时重启专属 profile"
grep -Fq 'PLATFORM_DOCKER_CONTEXT="${DOCKER_CONTEXT_NAME}"' "${RUNNER}" || \
  fail "E2E 调整内存前没有限定平台栈 Docker context"
grep -Fq 'infra/ragflow/manage.sh" stop' "${RUNNER}" || \
  fail "E2E 调整内存前没有停止本项目 RAGFlow"
grep -Fq '"auth" || "${E2E_SUITE}" == "tenant-rbac" || "${E2E_SUITE}" == "audit" || "${E2E_SUITE}" == "demo-chat"' "${RUNNER}" || \
  fail "认证、租户和审计 E2E 没有归入轻量档位"
grep -Fq 'e2e/audit.spec.ts' "${RUNNER}" || \
  fail "E2E 入口没有执行正式审计页面用例"
grep -Fq 'tests.support.audit_e2e_cleanup' "${RUNNER}" || \
  fail "审计 E2E 没有登记精确业务数据清理器"

echo "平台 E2E 资源档位契约通过"
