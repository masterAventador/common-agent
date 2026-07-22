#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
FORK_METADATA="${SCRIPT_DIR}/fork.env"
PATCHSET_METADATA="${SCRIPT_DIR}/patchset.env"

fail() {
  echo "$1" >&2
  exit 1
}

[[ -f "${FORK_METADATA}" ]] || fail "缺少 RAGFlow fork 元数据"
[[ -f "${PATCHSET_METADATA}" ]] || fail "缺少 RAGFlow 补丁集元数据"

# shellcheck disable=SC1090
source "${FORK_METADATA}"
# shellcheck disable=SC1090
source "${PATCHSET_METADATA}"

WORKTREE="${RAGFLOW_PATCHSET_WORKTREE_OVERRIDE:-${REPOSITORY_ROOT}/.local/ragflow-fork}"
PATCH_BASE="${RAGFLOW_PATCH_BASE_OVERRIDE:-${RAGFLOW_PATCH_BASE}}"
PATCH_HEAD="${RAGFLOW_PATCH_HEAD_OVERRIDE:-${RAGFLOW_PATCH_HEAD}}"
PATCH_SHORT="${RAGFLOW_PATCH_SHORT_OVERRIDE:-${RAGFLOW_PATCH_SHORT}}"
PATCH_COMMITS="${RAGFLOW_PATCH_COMMITS_OVERRIDE:-${RAGFLOW_PATCH_COMMITS}}"
ALLOWED_ROOTS="${RAGFLOW_PATCH_ALLOWED_ROOTS_OVERRIDE:-${RAGFLOW_PATCH_ALLOWED_ROOTS}}"
UPGRADE_COMMIT="${RAGFLOW_UPGRADE_AUDIT_COMMIT_OVERRIDE:-${RAGFLOW_UPGRADE_AUDIT_COMMIT}}"
EXPECTED_CONFLICTS="${RAGFLOW_UPGRADE_EXPECTED_CONFLICTS_OVERRIDE:-${RAGFLOW_UPGRADE_EXPECTED_CONFLICTS}}"

validate_commit() {
  local name="$1"
  local value="$2"
  [[ "${value}" =~ ^[0-9a-f]{40}$ ]] || fail "${name} 不是完整 Git commit：${value}"
  git -C "${WORKTREE}" cat-file -e "${value}^{commit}" 2>/dev/null || \
    fail "${name} 在补丁工作区不存在：${value}"
}

csv_to_sorted_lines() {
  tr ',' '\n' | sed '/^$/d' | LC_ALL=C sort -u
}

git -C "${WORKTREE}" rev-parse --is-inside-work-tree >/dev/null 2>&1 || \
  fail "RAGFlow 补丁工作区不是 Git 仓库：${WORKTREE}"
validate_commit RAGFLOW_PATCH_BASE "${PATCH_BASE}"
validate_commit RAGFLOW_PATCH_HEAD "${PATCH_HEAD}"
validate_commit RAGFLOW_UPGRADE_AUDIT_COMMIT "${UPGRADE_COMMIT}"

[[ "$(git -C "${WORKTREE}" rev-parse HEAD)" == "${PATCH_HEAD}" ]] || \
  fail "RAGFlow 补丁工作区 HEAD 与锁定补丁集不一致"
[[ "$(git -C "${WORKTREE}" rev-parse --short "${PATCH_HEAD}")" == "${PATCH_SHORT}" ]] || \
  fail "RAGFlow 补丁短标识与 Git 实际短哈希不一致"
[[ -z "$(git -C "${WORKTREE}" status --short)" ]] || \
  fail "RAGFlow 补丁工作区必须保持未修改状态"
git -C "${WORKTREE}" merge-base --is-ancestor "${PATCH_BASE}" "${PATCH_HEAD}" || \
  fail "RAGFlow 补丁集不包含官方基线"
git -C "${WORKTREE}" merge-base --is-ancestor "${PATCH_BASE}" "${UPGRADE_COMMIT}" || \
  fail "RAGFlow 升级审计点不包含官方基线"
[[ -z "$(git -C "${WORKTREE}" rev-list --merges "${PATCH_BASE}..${PATCH_HEAD}")" ]] || \
  fail "RAGFlow 补丁集必须保持无 merge commit 的线性历史"

ACTUAL_COMMITS="$(git -C "${WORKTREE}" rev-list --reverse "${PATCH_BASE}..${PATCH_HEAD}" | paste -sd, -)"
[[ "${ACTUAL_COMMITS}" == "${PATCH_COMMITS}" ]] || \
  fail "RAGFlow 补丁提交顺序或内容发生漂移"
git -C "${WORKTREE}" diff --check "${PATCH_BASE}..${PATCH_HEAD}"

while IFS= read -r changed_path; do
  allowed=0
  while IFS= read -r allowed_root; do
    if [[ "${changed_path}" == "${allowed_root}/"* ]]; then
      allowed=1
      break
    fi
  done < <(printf '%s' "${ALLOWED_ROOTS}" | csv_to_sorted_lines)
  ((allowed == 1)) || fail "RAGFlow 补丁修改了未授权根目录：${changed_path}"
done < <(git -C "${WORKTREE}" diff --name-only "${PATCH_BASE}..${PATCH_HEAD}")

if [[ "${RAGFLOW_PATCHSET_SKIP_REMOTE_VERIFY:-0}" != "1" ]]; then
  origin="$(git -C "${WORKTREE}" remote get-url origin)"
  remote_result="$(git ls-remote --heads "${origin}" "refs/heads/${RAGFLOW_PATCH_BRANCH}")"
  remote_head="$(awk -v ref="refs/heads/${RAGFLOW_PATCH_BRANCH}" '$2 == ref {print $1}' <<< "${remote_result}")"
  [[ "${remote_head}" == "${PATCH_HEAD}" ]] || \
    fail "RAGFlow 远端补丁分支未锁定到补丁集 HEAD"
fi

MERGE_OUTPUT="$(mktemp)"
cleanup() {
  rm -f "${MERGE_OUTPUT}"
}
trap cleanup EXIT
set +e
LC_ALL=C git -C "${WORKTREE}" merge-tree --write-tree --messages \
  "${PATCH_HEAD}" "${UPGRADE_COMMIT}" >"${MERGE_OUTPUT}" 2>&1
merge_status=$?
set -e
((merge_status == 0 || merge_status == 1)) || \
  fail "RAGFlow 升级 merge-tree 审计执行失败"

ACTUAL_CONFLICTS="$(
  awk '$1 ~ /^[0-9]{6}$/ && $3 ~ /^[123]$/ {sub(/^[^\t]*\t/, ""); print}' \
    "${MERGE_OUTPUT}" | LC_ALL=C sort -u | paste -sd, -
)"
NORMALIZED_EXPECTED_CONFLICTS="$(printf '%s' "${EXPECTED_CONFLICTS}" | csv_to_sorted_lines | paste -sd, -)"
[[ "${ACTUAL_CONFLICTS}" == "${NORMALIZED_EXPECTED_CONFLICTS}" ]] || \
  fail "RAGFlow 升级冲突集合发生漂移：${ACTUAL_CONFLICTS:-none}"
if [[ -n "${NORMALIZED_EXPECTED_CONFLICTS}" ]]; then
  ((merge_status == 1)) || fail "RAGFlow 已知升级冲突没有关闭失败"
else
  ((merge_status == 0)) || fail "RAGFlow 无冲突升级审计返回失败"
fi

cleanup
trap - EXIT
echo "RAGFlow 补丁集验证通过：head=${PATCH_HEAD}, upgrade=${UPGRADE_COMMIT}, conflicts=${ACTUAL_CONFLICTS:-none}"
