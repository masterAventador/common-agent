#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BACKEND_ROOT="${REPOSITORY_ROOT}/backend"
PATCHSET_METADATA="${REPOSITORY_ROOT}/infra/ragflow/patchset.env"
UV_RUNNER="${SCRIPT_DIR}/uv.sh"

if [[ ! -f "${PATCHSET_METADATA}" ]]; then
  echo "缺少 RAGFlow 补丁集元数据" >&2
  exit 1
fi
# shellcheck disable=SC1090
source "${PATCHSET_METADATA}"

REPORT_ROOT="${COMMON_AGENT_R2_06_REPORT_ROOT:-${REPOSITORY_ROOT}/.local/benchmarks/r2-06/${RAGFLOW_PATCH_SHORT}}"
LIST_REPORT="${COMMON_AGENT_R2_06_LIST_REPORT:-${REPORT_ROOT}/list-delete.json}"
WRITE_REPORT="${COMMON_AGENT_R2_06_WRITE_REPORT:-${REPORT_ROOT}/write.json}"
RETRIEVAL_REPORT="${COMMON_AGENT_R2_06_RETRIEVAL_REPORT:-${REPORT_ROOT}/retrieval.json}"
OFFICIAL_WRITE_REPORT="${COMMON_AGENT_R2_06_OFFICIAL_WRITE_REPORT:-${REPOSITORY_ROOT}/.local/benchmarks/r2-04/official/baseline.json}"
OFFICIAL_RETRIEVAL_REPORT="${COMMON_AGENT_R2_06_OFFICIAL_RETRIEVAL_REPORT:-${REPOSITORY_ROOT}/.local/benchmarks/r2-05/official/baseline.json}"
SUMMARY_REPORT="${COMMON_AGENT_R2_06_SUMMARY_REPORT:-${REPORT_ROOT}/summary.json}"

for report in \
  "${LIST_REPORT}" \
  "${WRITE_REPORT}" \
  "${RETRIEVAL_REPORT}" \
  "${OFFICIAL_WRITE_REPORT}" \
  "${OFFICIAL_RETRIEVAL_REPORT}"; do
  if [[ ! -f "${report}" || -L "${report}" ]]; then
    echo "R2-06 报告不存在或为符号链接：${report}" >&2
    exit 1
  fi
done

(
  cd "${BACKEND_ROOT}"
  "${UV_RUNNER}" run --frozen python -m tests.performance.ragflow_v0264_patchset_regression \
    --list-report "${LIST_REPORT}" \
    --official-write-report "${OFFICIAL_WRITE_REPORT}" \
    --write-report "${WRITE_REPORT}" \
    --official-retrieval-report "${OFFICIAL_RETRIEVAL_REPORT}" \
    --retrieval-report "${RETRIEVAL_REPORT}" \
    --expected-commit "${RAGFLOW_PATCH_HEAD}" \
    --output "${SUMMARY_REPORT}"
)
echo "R2-06 RAGFlow v0.26.4 补丁集报告门禁通过：${SUMMARY_REPORT}"
