#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BACKEND_ROOT="${REPOSITORY_ROOT}/backend"
FRONTEND_ROOT="${REPOSITORY_ROOT}/frontend"
BACKEND_REPORT_ROOT="${REPOSITORY_ROOT}/.local/coverage/backend"
ACTION="${1:-all}"

OVERALL_LINE_MINIMUM=90.90
OVERALL_BRANCH_MINIMUM=72.20
CORE_LINE_MINIMUM=93.17
CORE_BRANCH_MINIMUM=74.26

run_backend() {
  mkdir -p "${BACKEND_REPORT_ROOT}"
  (
    cd "${BACKEND_ROOT}"
    uv run --frozen pytest \
      --cov=common_agent \
      --cov-branch \
      --cov-report=term-missing \
      --cov-report=
    uv run --frozen coverage json -o "${BACKEND_REPORT_ROOT}/coverage.json"
    uv run --frozen coverage xml -o "${BACKEND_REPORT_ROOT}/coverage.xml"
    uv run --frozen python "${SCRIPT_DIR}/check-backend-coverage.py" \
      "${BACKEND_REPORT_ROOT}/coverage.json" \
      "${OVERALL_LINE_MINIMUM}" \
      "${OVERALL_BRANCH_MINIMUM}" \
      "${CORE_LINE_MINIMUM}" \
      "${CORE_BRANCH_MINIMUM}"
  )
}

run_frontend() {
  (
    cd "${FRONTEND_ROOT}"
    npx pnpm@11.9.0 test:coverage
  )
}

case "${ACTION}" in
  backend) run_backend ;;
  frontend) run_frontend ;;
  all)
    run_backend
    run_frontend
    ;;
  *)
    echo "用法：scripts/coverage.sh [backend|frontend|all]" >&2
    exit 2
    ;;
esac
