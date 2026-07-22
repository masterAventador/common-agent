#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BACKEND_ROOT="${REPOSITORY_ROOT}/backend"
RAGFLOW_SOURCE="${COMMON_AGENT_RAGFLOW_RETRIEVAL_SOURCE:-${REPOSITORY_ROOT}/third_party/ragflow}"
RAGFLOW_MANAGER="${REPOSITORY_ROOT}/infra/ragflow/manage.sh"
UV_RUNNER="${SCRIPT_DIR}/uv.sh"
# shellcheck disable=SC1091
source "${REPOSITORY_ROOT}/infra/ragflow/patchset.env"
EXPECTED_RAGFLOW_COMMIT="${COMMON_AGENT_RAGFLOW_RETRIEVAL_EXPECTED_COMMIT:-${RAGFLOW_PATCH_HEAD}}"
SOURCE_MODE="${COMMON_AGENT_RAGFLOW_RETRIEVAL_SOURCE_MODE:-patched}"
EXPECTED_IMAGE_REVISION="${COMMON_AGENT_RAGFLOW_RETRIEVAL_IMAGE_REVISION:-${RAGFLOW_PATCH_HEAD}}"
TOKEN_FILE="${REPOSITORY_ROOT}/.local/dev/common-agent-dev/secrets/ragflow-api-token"
RUN_ID="$(date -u +%Y%m%d%H%M%S)-$$"
REPORT_ROOT="${REPOSITORY_ROOT}/.local/benchmarks/r2-05/${RUN_ID}"
REPORT_PATH="${COMMON_AGENT_R2_05_REPORT_PATH:-${REPORT_ROOT}/baseline.json}"
SCALE_COUNT="${COMMON_AGENT_R2_05_SCALE_COUNT:-12000}"
DEEP_PAGE="${COMMON_AGENT_R2_05_DEEP_PAGE:-110}"
DOCUMENT_COUNT="${COMMON_AGENT_R2_05_DOCUMENT_COUNT:-2}"
PARAGRAPHS_PER_DOCUMENT="${COMMON_AGENT_R2_05_PARAGRAPHS_PER_DOCUMENT:-16}"
WORDS_PER_PARAGRAPH="${COMMON_AGENT_R2_05_WORDS_PER_PARAGRAPH:-300}"
STACK_STARTED_BY_RUNNER=0

api_is_ready() {
  curl -fsS --max-time 3 http://127.0.0.1:19380/api/v1/system/version >/dev/null 2>&1
}

restore_api_if_needed() {
  local oom_killed=""
  oom_killed="$(docker --context colima-common-agent-dev inspect \
    --format '{{.State.OOMKilled}}' common-agent-ragflow-api 2>/dev/null || true)"
  if [[ "${oom_killed}" != "true" ]] && api_is_ready; then
    return
  fi
  echo "R2-05 基准异常后正在恢复当前 RAGFlow API 容器"
  if ! docker --context colima-common-agent-dev restart \
    common-agent-ragflow-api >/dev/null; then
    return 1
  fi
  for _ in {1..120}; do
    if api_is_ready; then
      "${RAGFLOW_MANAGER}" check-bailian
      return
    fi
    sleep 1
  done
  echo "RAGFlow API 在 R2-05 基准后未恢复" >&2
  return 1
}

cleanup() {
  local original_status=$?
  trap - EXIT INT TERM
  if ((STACK_STARTED_BY_RUNNER != 0)); then
    "${RAGFLOW_MANAGER}" stop || original_status=1
  else
    restore_api_if_needed || original_status=1
  fi
  if ((original_status == 0)); then
    echo "R2-05 RAGFlow v0.26.4 检索/读取基准通过：${REPORT_PATH}"
  else
    echo "R2-05 RAGFlow v0.26.4 检索/读取基准失败；检查报告与恢复状态" >&2
  fi
  exit "${original_status}"
}

if [[ "${SOURCE_MODE}" != "official" && "${SOURCE_MODE}" != "patched" ]]; then
  echo "RAGFlow 检索基准源码模式必须是 official 或 patched" >&2
  exit 1
fi
if [[ "${SOURCE_MODE}" == "patched" && -z "${EXPECTED_IMAGE_REVISION}" ]]; then
  echo "patched 检索基准必须绑定 RAGFlow API 镜像 revision" >&2
  exit 1
fi
if [[ "$(git -C "${RAGFLOW_SOURCE}" rev-parse HEAD)" != "${EXPECTED_RAGFLOW_COMMIT}" ]]; then
  echo "RAGFlow 检索基准源码不是指定提交：${EXPECTED_RAGFLOW_COMMIT}" >&2
  exit 1
fi
if [[ -n "$(git -C "${RAGFLOW_SOURCE}" status --porcelain)" ]]; then
  echo "RAGFlow 检索基准源码工作区不干净" >&2
  exit 1
fi
if [[ ! -f "${TOKEN_FILE}" || -L "${TOKEN_FILE}" ]]; then
  echo "RAGFlow 0600 API Token 文件不存在或为符号链接" >&2
  exit 1
fi
if [[ "$(stat -f '%Lp' "${TOKEN_FILE}")" != "600" ]]; then
  echo "RAGFlow API Token 文件权限必须是 0600" >&2
  exit 1
fi
if [[ "$(docker --context colima-common-agent-dev inspect \
  --format '{{.State.Running}}' common-agent-ragflow-api 2>/dev/null || true)" != "true" ]]; then
  "${RAGFLOW_MANAGER}" up
  STACK_STARTED_BY_RUNNER=1
fi
trap cleanup EXIT
trap 'exit 130' INT TERM

if [[ -n "${EXPECTED_IMAGE_REVISION}" ]]; then
  ACTUAL_IMAGE_REVISION="$(docker --context colima-common-agent-dev inspect \
    --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' \
    common-agent-ragflow-api 2>/dev/null || true)"
  if [[ "${ACTUAL_IMAGE_REVISION}" != "${EXPECTED_IMAGE_REVISION}" ]]; then
    echo "RAGFlow API 镜像 revision 与检索基准源码不一致" >&2
    exit 1
  fi
fi

"${RAGFLOW_MANAGER}" status
"${RAGFLOW_MANAGER}" check-bailian
mkdir -p "$(dirname "${REPORT_PATH}")"
export RAGFLOW_BENCHMARK_MYSQL_PASSWORD="${RAGFLOW_BENCHMARK_MYSQL_PASSWORD:-infini_rag_flow}"
export RAGFLOW_BENCHMARK_ELASTIC_PASSWORD="${RAGFLOW_BENCHMARK_ELASTIC_PASSWORD:-infini_rag_flow}"
(
  cd "${BACKEND_ROOT}"
  "${UV_RUNNER}" run --frozen python -m tests.performance.ragflow_v0264_retrieval_baseline \
    --api-key-file "${TOKEN_FILE}" \
    --source-root "${RAGFLOW_SOURCE}" \
    --expected-source-commit "${EXPECTED_RAGFLOW_COMMIT}" \
    --source-mode "${SOURCE_MODE}" \
    --output "${REPORT_PATH}" \
    --scale-count "${SCALE_COUNT}" \
    --deep-page "${DEEP_PAGE}" \
    --document-count "${DOCUMENT_COUNT}" \
    --paragraphs-per-document "${PARAGRAPHS_PER_DOCUMENT}" \
    --words-per-paragraph "${WORDS_PER_PARAGRAPH}"
)
