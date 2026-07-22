#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
IMAGE_MANAGER="${SCRIPT_DIR}/image.sh"
IMAGE_METADATA="${SCRIPT_DIR}/image.env"
PATCHSET_METADATA="${SCRIPT_DIR}/patchset.env"
FORK_METADATA="${SCRIPT_DIR}/fork.env"
FORK_DOCKERFILE="${SCRIPT_DIR}/Dockerfile.fork"
SUBMODULE_ROOT="${REPOSITORY_ROOT}/third_party/ragflow"

fail() {
  echo "$1" >&2
  exit 1
}

[[ -x "${IMAGE_MANAGER}" ]] || fail "缺少可执行的 RAGFlow fork 镜像管理脚本"
[[ -f "${IMAGE_METADATA}" ]] || fail "缺少 RAGFlow fork 镜像元数据"
[[ -f "${PATCHSET_METADATA}" ]] || fail "缺少 RAGFlow 补丁集元数据"
[[ -f "${FORK_METADATA}" ]] || fail "缺少 RAGFlow fork 元数据"
[[ -f "${FORK_DOCKERFILE}" ]] || fail "缺少 RAGFlow fork 镜像 Dockerfile"

# shellcheck disable=SC1090
source "${IMAGE_METADATA}"
# shellcheck disable=SC1090
source "${PATCHSET_METADATA}"
# shellcheck disable=SC1090
source "${FORK_METADATA}"

[[ "${RAGFLOW_FORK_IMAGE}" == "common-agent/ragflow:v0.26.4-${RAGFLOW_PATCH_SHORT}" ]] || \
  fail "RAGFlow fork 镜像标签没有绑定补丁短提交"
[[ "${RAGFLOW_FORK_IMAGE_REVISION}" == "${RAGFLOW_PATCH_HEAD}" ]] || \
  fail "RAGFlow fork 镜像 revision 与补丁集 HEAD 不一致"
[[ "${RAGFLOW_FORK_IMAGE_BASE}" == "infiniflow/ragflow:v0.26.4" ]] || \
  fail "RAGFlow fork 镜像基底漂移"
[[ "${RAGFLOW_FORK_IMAGE_BASE_DIGEST}" == "infiniflow/ragflow@sha256:e0048bb5ee60f8bcd2e9a2c4851de80f39a0b7318ad4e55bf7bbcef126eaa9ac" ]] || \
  fail "RAGFlow fork 镜像基底 digest 漂移"
[[ "${RAGFLOW_ELASTICSEARCH_IMAGE}" == "elasticsearch@sha256:58a3a280935d830215802322e9a0373faaacdfd646477aa7e718939c2f29292a" ]] || \
  fail "RAGFlow Elasticsearch 镜像 digest 漂移"
[[ "${RAGFLOW_MYSQL_IMAGE}" == "mysql@sha256:ccb8f749bb5e59f9f8f03bf7282c7ef27a93a1814a24f0a8a926fb4e19b7fb97" ]] || \
  fail "RAGFlow MySQL 镜像 digest 漂移"
[[ "${RAGFLOW_MINIO_IMAGE}" == "pgsty/minio@sha256:a72bf37c235a83a73890d2a46c5b36801fed61c335175e0396070bf84a8bbb98" ]] || \
  fail "RAGFlow MinIO 镜像 digest 漂移"
[[ "${RAGFLOW_VALKEY_IMAGE}" == "valkey/valkey@sha256:3e31dd49b6b742e614975e8ab7b1b19809d00ecac7657c6b34bff23582a433cd" ]] || \
  fail "RAGFlow Valkey 镜像 digest 漂移"
[[ "${RAGFLOW_FORK_IMAGE_SOURCE}" == "https://github.com/masterAventador/common-agent-ragflow" ]] || \
  fail "RAGFlow fork 镜像源码地址漂移"
[[ "${RAGFLOW_FORK_IMAGE_HIGH}" == "75" && "${RAGFLOW_FORK_IMAGE_CRITICAL}" == "5" ]] || \
  fail "RAGFlow fork 镜像漏洞数量基线漂移"
[[ "${RAGFLOW_FORK_IMAGE_FINDINGS_SHA256}" == "725782ab941170431d0c839956ca62a47b8f75828ad701e0db0e614c45fb80ca" ]] || \
  fail "RAGFlow fork 镜像漏洞明细基线漂移"

[[ "$(git config -f "${REPOSITORY_ROOT}/.gitmodules" --get submodule.third_party/ragflow.url)" == "../common-agent-ragflow.git" ]] || \
  fail "RAGFlow submodule 没有使用可随父仓库协议解析的私有相对地址"
[[ "$(git -C "${SUBMODULE_ROOT}" rev-parse HEAD)" == "${RAGFLOW_PATCH_HEAD}" ]] || \
  fail "RAGFlow submodule 没有锁定最终补丁提交"
[[ "$(git -C "${SUBMODULE_ROOT}" rev-parse "refs/tags/${RAGFLOW_UPSTREAM_VERSION}^{commit}")" == "${RAGFLOW_UPSTREAM_COMMIT}" ]] || \
  fail "RAGFlow submodule 的官方基线 tag 漂移"
git -C "${SUBMODULE_ROOT}" merge-base --is-ancestor "${RAGFLOW_UPSTREAM_COMMIT}" "${RAGFLOW_PATCH_HEAD}" || \
  fail "RAGFlow submodule 补丁提交不包含官方基线"
[[ -z "$(git -C "${SUBMODULE_ROOT}" status --short)" ]] || \
  fail "RAGFlow submodule 必须保持未修改状态"

rg --color=never --fixed-strings --quiet 'ARG RAGFLOW_FORK_IMAGE_BASE' "${FORK_DOCKERFILE}" || \
  fail "RAGFlow fork Dockerfile 没有参数化固定基底"
rg --color=never --fixed-strings --quiet 'FROM ${RAGFLOW_FORK_IMAGE_BASE}' "${FORK_DOCKERFILE}" || \
  fail "RAGFlow fork Dockerfile 没有从固定官方镜像构建"
rg --color=never --fixed-strings --quiet 'COPY api /ragflow/api' "${FORK_DOCKERFILE}" || \
  fail "RAGFlow fork Dockerfile 没有覆盖完整 API 源码"
rg --color=never --fixed-strings --quiet 'COPY rag /ragflow/rag' "${FORK_DOCKERFILE}" || \
  fail "RAGFlow fork Dockerfile 没有覆盖完整 RAG 源码"
if rg --color=never --quiet 'curl|wget|git clone|pip install|uv sync|npm install' "${FORK_DOCKERFILE}"; then
  fail "RAGFlow fork 覆盖镜像不得在构建时下载或重解依赖"
fi

SOURCE_STATUS="$(RAGFLOW_IMAGE_SKIP_DOCKER=1 "${IMAGE_MANAGER}" verify-source)"
rg --color=never --fixed-strings --quiet "image=${RAGFLOW_FORK_IMAGE}" <<< "${SOURCE_STATUS}" || \
  fail "RAGFlow fork 镜像源码验证没有输出锁定标签"
rg --color=never --fixed-strings --quiet "revision=${RAGFLOW_PATCH_HEAD}" <<< "${SOURCE_STATUS}" || \
  fail "RAGFlow fork 镜像源码验证没有输出锁定 revision"

if RAGFLOW_IMAGE_SKIP_DOCKER=1 \
  RAGFLOW_IMAGE_EXPECTED_REVISION_OVERRIDE=0000000000000000000000000000000000000000 \
    "${IMAGE_MANAGER}" verify-source >/dev/null 2>&1; then
  fail "RAGFlow fork 镜像源码 revision 漂移仍然被放行"
fi

echo "RAGFlow 私有 submodule、覆盖镜像与安全基线契约通过"
