#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BACKEND_ROOT="${REPOSITORY_ROOT}/backend"
RAGFLOW_SOURCE="${COMMON_AGENT_RAGFLOW_WRITE_SOURCE:-${REPOSITORY_ROOT}/third_party/ragflow}"
RAGFLOW_MANAGER="${REPOSITORY_ROOT}/infra/ragflow/manage.sh"
UV_RUNNER="${SCRIPT_DIR}/uv.sh"
# shellcheck disable=SC1091
source "${REPOSITORY_ROOT}/infra/ragflow/patchset.env"
EXPECTED_RAGFLOW_COMMIT="${COMMON_AGENT_RAGFLOW_WRITE_EXPECTED_COMMIT:-${RAGFLOW_PATCH_HEAD}}"
SOURCE_MODE="${COMMON_AGENT_RAGFLOW_WRITE_SOURCE_MODE:-patched}"
EXPECTED_IMAGE_REVISION="${COMMON_AGENT_RAGFLOW_WRITE_IMAGE_REVISION:-${RAGFLOW_PATCH_HEAD}}"
DOC_BULK_SIZE="${COMMON_AGENT_RAGFLOW_WRITE_DOC_BULK_SIZE:-32}"
EMBEDDING_CONCURRENCY="${COMMON_AGENT_RAGFLOW_WRITE_EMBEDDING_CONCURRENCY:-8}"
TOKEN_FILE="${REPOSITORY_ROOT}/.local/dev/common-agent-dev/secrets/ragflow-api-token"
RUN_ID="$(date -u +%Y%m%d%H%M%S)-$$"
REPORT_ROOT="${REPOSITORY_ROOT}/.local/benchmarks/r2-04/${RUN_ID}"
REPORT_PATH="${COMMON_AGENT_R2_04_REPORT_PATH:-${REPORT_ROOT}/baseline.json}"
DOCUMENT_COUNT="${COMMON_AGENT_R2_04_DOCUMENT_COUNT:-4}"
PARAGRAPHS_PER_DOCUMENT="${COMMON_AGENT_R2_04_PARAGRAPHS_PER_DOCUMENT:-32}"
WORDS_PER_PARAGRAPH="${COMMON_AGENT_R2_04_WORDS_PER_PARAGRAPH:-600}"
ROOT_SCALE_DOCUMENTS="${COMMON_AGENT_R2_04_ROOT_SCALE_DOCUMENTS:-250000}"
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
  echo "R2-04 基准异常后正在恢复当前 RAGFlow API 容器"
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
  echo "RAGFlow API 在 R2-04 基准后未恢复" >&2
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
    echo "R2-04 RAGFlow v0.26.4 写入基准通过：${REPORT_PATH}"
  else
    echo "R2-04 RAGFlow v0.26.4 写入基准失败；检查报告与恢复状态" >&2
  fi
  exit "${original_status}"
}

container_environment_value() {
  local key="$1"
  docker --context colima-common-agent-dev inspect \
    --format '{{range .Config.Env}}{{println .}}{{end}}' \
    common-agent-ragflow-api | awk -F= -v requested_key="${key}" \
      '$1 == requested_key {sub(/^[^=]*=/, ""); print; exit}'
}

validate_positive_integer() {
  local name="$1"
  local value="$2"
  if [[ ! "${value}" =~ ^[1-9][0-9]*$ ]]; then
    echo "${name} 必须是正整数" >&2
    exit 2
  fi
}

if [[ "${SOURCE_MODE}" != "official" && "${SOURCE_MODE}" != "patched" ]]; then
  echo "RAGFlow 写入基准源码模式必须是 official 或 patched" >&2
  exit 1
fi
if [[ "${SOURCE_MODE}" == "patched" && -z "${EXPECTED_IMAGE_REVISION}" ]]; then
  echo "patched 写入基准必须绑定 RAGFlow API 镜像 revision" >&2
  exit 1
fi
for pair in \
  "DOC_BULK_SIZE:${DOC_BULK_SIZE}" \
  "EMBEDDING_CONCURRENCY:${EMBEDDING_CONCURRENCY}" \
  "DOCUMENT_COUNT:${DOCUMENT_COUNT}" \
  "PARAGRAPHS_PER_DOCUMENT:${PARAGRAPHS_PER_DOCUMENT}" \
  "WORDS_PER_PARAGRAPH:${WORDS_PER_PARAGRAPH}" \
  "ROOT_SCALE_DOCUMENTS:${ROOT_SCALE_DOCUMENTS}"; do
  validate_positive_integer "${pair%%:*}" "${pair#*:}"
done
if [[ "$(git -C "${RAGFLOW_SOURCE}" rev-parse HEAD)" != "${EXPECTED_RAGFLOW_COMMIT}" ]]; then
  echo "RAGFlow 写入基准源码不是指定提交：${EXPECTED_RAGFLOW_COMMIT}" >&2
  exit 1
fi
if [[ -n "$(git -C "${RAGFLOW_SOURCE}" status --porcelain)" ]]; then
  echo "RAGFlow 写入基准源码工作区不干净" >&2
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
    echo "RAGFlow API 镜像 revision 与写入基准源码不一致" >&2
    exit 1
  fi
fi

ACTUAL_DOC_BULK_SIZE="$(container_environment_value DOC_BULK_SIZE)"
if [[ -z "${ACTUAL_DOC_BULK_SIZE}" ]]; then
  ACTUAL_DOC_BULK_SIZE=4
fi
ACTUAL_EMBEDDING_CONCURRENCY="$(container_environment_value MAX_CONCURRENT_EMBEDDINGS)"
if [[ -z "${ACTUAL_EMBEDDING_CONCURRENCY}" && "${SOURCE_MODE}" == "official" ]]; then
  ACTUAL_EMBEDDING_CONCURRENCY="$(container_environment_value MAX_CONCURRENT_CHUNK_BUILDERS)"
fi
if [[ -z "${ACTUAL_EMBEDDING_CONCURRENCY}" ]]; then
  ACTUAL_EMBEDDING_CONCURRENCY=1
fi
if [[ "${ACTUAL_DOC_BULK_SIZE}" != "${DOC_BULK_SIZE}" ]]; then
  echo "RAGFlow API 实际 DOC_BULK_SIZE 与基准参数不一致" >&2
  exit 1
fi
if [[ "${ACTUAL_EMBEDDING_CONCURRENCY}" != "${EMBEDDING_CONCURRENCY}" ]]; then
  echo "RAGFlow API 实际 embedding 并发与基准参数不一致" >&2
  exit 1
fi

"${RAGFLOW_MANAGER}" status
"${RAGFLOW_MANAGER}" check-bailian
mkdir -p "$(dirname "${REPORT_PATH}")"
export RAGFLOW_BENCHMARK_MYSQL_PASSWORD="${RAGFLOW_BENCHMARK_MYSQL_PASSWORD:-infini_rag_flow}"
(
  cd "${BACKEND_ROOT}"
  "${UV_RUNNER}" run --frozen python -m tests.performance.ragflow_v0264_write_baseline \
    --api-key-file "${TOKEN_FILE}" \
    --source-root "${RAGFLOW_SOURCE}" \
    --expected-source-commit "${EXPECTED_RAGFLOW_COMMIT}" \
    --source-mode "${SOURCE_MODE}" \
    --output "${REPORT_PATH}" \
    --doc-bulk-size "${DOC_BULK_SIZE}" \
    --embedding-concurrency "${EMBEDDING_CONCURRENCY}" \
    --document-count "${DOCUMENT_COUNT}" \
    --paragraphs-per-document "${PARAGRAPHS_PER_DOCUMENT}" \
    --words-per-paragraph "${WORDS_PER_PARAGRAPH}" \
    --root-scale-documents "${ROOT_SCALE_DOCUMENTS}"
)
